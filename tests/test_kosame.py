#!/usr/bin/env python3
"""tools/kosame.py — 같은 원문에 이미 내린 번역을 퍼뜨립니다.

같은 문장이 표 여러 곳에 그대로 나옵니다 (보물상자 정형문, 가게 인사,
길안내). 한쪽만 번역돼 있으면 다른 쪽은 원문이 그대로 나오고, 손으로
다시 옮기면 표현이 갈립니다. 이미 내린 결정을 그대로 복사합니다.

**새로 번역하지 않습니다.** 판단이 필요한 자리는 손대지 않고 남깁니다.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tools"))
import kosame  # noqa: E402


class SubstantialTest(unittest.TestCase):
    """짧은 조각은 문맥마다 달리 옮깁니다 — 복사하면 안 됩니다."""

    def test_한_글자짜리는_아니다(self):
        for t in ("ず", "ふ", "て", "ま", "べ"):
            self.assertFalse(kosame.substantial(t), t)

    def test_여러_줄이면_맞다(self):
        self.assertTrue(kosame.substantial("いらっしゃい\nどうぞ"))

    def test_제어_코드가_있으면_맞다(self):
        self.assertTrue(kosame.substantial("<$10>あ"))

    def test_충분히_길면_맞다(self):
        self.assertTrue(kosame.substantial("たからばこが　ある"))


class BuildTest(unittest.TestCase):
    """번역이 갈리는 원문은 후보에서 뺍니다."""

    def test_하나뿐이면_후보가_된다(self):
        pairs = [("宝ばこが　ある", "보물상자가　있다")] * 2
        self.assertEqual(kosame.build(pairs),
                         {"宝ばこが　ある": "보물상자가　있다"})

    def test_갈리면_후보에서_뺀다(self):
        pairs = [("またのおこしを　おまちしています", "또　오시길　기다립니다"),
                 ("またのおこしを　おまちしています", "또　오십시오")]
        self.assertEqual(kosame.build(pairs), {})

    def test_짧은_조각은_후보가_아니다(self):
        self.assertEqual(kosame.build([("ず", "울")] * 3), {})

    def test_빈_번역은_세지_않는다(self):
        self.assertEqual(kosame.build([("宝ばこが　ある", "  ")]), {})


class ApplyTest(unittest.TestCase):
    def setUp(self):
        self.known = {"宝ばこが　ある": "보물상자가　있다"}

    def test_비어_있는_항목만_채운다(self):
        rows = [("宝ばこが　ある", ""), ("宝ばこが　ある", "이미　번역")]
        out, n = kosame.apply(rows, self.known)
        self.assertEqual(n, 1)
        self.assertEqual(out, ["보물상자가　있다", "이미　번역"])

    def test_후보에_없으면_그대로_둔다(self):
        rows = [("しらないぶん", "")]
        out, n = kosame.apply(rows, self.known)
        self.assertEqual(n, 0)
        self.assertEqual(out, [""])

    def test_고칠_것이_없으면_０(self):
        out, n = kosame.apply([("宝ばこが　ある", "이미")], self.known)
        self.assertEqual(n, 0)


class RealTest(unittest.TestCase):
    JA = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "..", "script", "ja")

    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(cls.JA):
            raise unittest.SkipTest("script/ja 없음")

    def test_실제_덤프에서_후보가_모인다(self):
        known = kosame.build(kosame.load_pairs("script/ja", "script/ko"))
        self.assertGreater(len(known), 1000)

    def test_끝말잇기_낱말은_후보에_없다(self):
        known = kosame.build(kosame.load_pairs("script/ja", "script/ko"))
        for t in ("ず", "ふ", "て", "ま"):
            self.assertNotIn(t, known)


if __name__ == "__main__":
    unittest.main()
