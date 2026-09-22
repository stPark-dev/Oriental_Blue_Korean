#!/usr/bin/env python3
"""tools/koprog.py — 번역 진행률.

분모가 틀리면 진행률이 통째로 거짓말이 됩니다. 실제로 `--min-count 32`
때문에 표 423개가 덤프에서 빠져 83.5% 로 부풀어 있었습니다. 이번에는
**게임이 쓰지 않는 표**가 분모에 들어가 반대로 깎이고 있었습니다.

제외 대상은 넷입니다.

  DFBEE4  비-JPN 낱말표 — 읽는 코드가 없습니다 (tools/koshiri.py 참고)
  DF9080  끝말잇기 낱말 조각 — koshiri.py 가 롬을 직접 고칩니다
  DF809C  CAST 자막 · DF8494  STAFF 자막 — 제작진 실명이라 원문 유지

DE1AF8 은 **표째로 빼면 안 됩니다.** 화면에 나오는 아이템 이름표라
738항목이 이미 번역돼 있습니다. 빼야 할 것은 그 안의 '0' 자리뿐입니다.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tools"))
import koprog  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
JA = os.path.join(ROOT, "script", "ja")
KO = os.path.join(ROOT, "script", "ko")


class ExcludeTest(unittest.TestCase):
    def test_게임이_쓰지_않는_표는_제외한다(self):
        for name in ("DFBEE4", "DF9080"):
            self.assertIn(name, koprog.EXCLUDED)

    def test_아이템_이름표는_표째로_빼지_않는다(self):
        """번역한 738항목이 분자에서 같이 사라집니다."""
        self.assertNotIn("DE1AF8", koprog.EXCLUDED)

    def test_제작진_자막도_제외한다(self):
        for name in ("DF809C", "DF8494"):
            self.assertIn(name, koprog.EXCLUDED)

    def test_본편_대사_표는_제외하지_않는다(self):
        for name in ("F4C354", "F0E0F8", "E2C6B0", "DF3908", "DE1AF8"):
            self.assertNotIn(name, koprog.EXCLUDED)

    def test_제외_이유가_모두_적혀_있다(self):
        for name, why in koprog.EXCLUDED.items():
            self.assertTrue(why.strip(), f"{name} 에 제외 이유가 없습니다")


class CountTest(unittest.TestCase):
    def test_빈_원문은_세지_않는다(self):
        rows = koprog.count({"tAAA111.txt": [("", ""), ("  ", "가"), ("あ", "")]})
        self.assertEqual(rows["AAA111"], (1, 0))

    def test_０_자리는_세지_않는다(self):
        """아이템 이름표의 빈 자리입니다. 화면에 나오지 않습니다."""
        rows = koprog.count({"tDE1AF8.txt": [("0", ""), ("0", ""), ("かぶと", "투구")]})
        self.assertEqual(rows["DE1AF8"], (1, 1))

    def test_０_자리는_어느_표에서나_뺀다(self):
        rows = koprog.count({"tAAA111.txt": [("0", ""), ("あ", "가")]})
        self.assertEqual(rows["AAA111"], (1, 1))

    def test_번역이_있으면_완료로_센다(self):
        rows = koprog.count({"tAAA111.txt": [("あ", "가"), ("い", "")]})
        self.assertEqual(rows["AAA111"], (2, 1))

    def test_제외한_표는_결과에_없다(self):
        rows = koprog.count({"tDFBEE4.txt": [("あ", "")]})
        self.assertEqual(rows, {})


class TotalTest(unittest.TestCase):
    def test_합계는_표별_합과_같다(self):
        rows = {"A": (10, 4), "B": (5, 5)}
        self.assertEqual(koprog.totals(rows), (15, 9))

    def test_대상이_없으면_０으로_나눈다고_터지지_않는다(self):
        self.assertEqual(koprog.totals({}), (0, 0))
        self.assertEqual(koprog.percent(0, 0), 0.0)

    def test_비율을_낸다(self):
        self.assertAlmostEqual(koprog.percent(4, 8), 50.0)


class RealTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(JA):
            raise unittest.SkipTest("script/ja 없음 — `make script` 를 먼저")

    def test_실제_덤프에서_진행률이_나온다(self):
        rows = koprog.count(koprog.load(JA, KO))
        total, done = koprog.totals(rows)
        self.assertGreater(total, 10000)
        self.assertLessEqual(done, total)

    def test_제외한_표가_분모에서_빠졌다(self):
        rows = koprog.count(koprog.load(JA, KO))
        for name in koprog.EXCLUDED:
            self.assertNotIn(name, rows)


if __name__ == "__main__":
    unittest.main()
