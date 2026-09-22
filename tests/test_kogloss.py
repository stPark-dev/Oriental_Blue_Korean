#!/usr/bin/env python3
"""tools/kogloss.py — 아이템 이름이 본문에서 달리 쓰인 곳을 찾습니다.

아이템 이름표는 **화면에 뜨는 이름**이라 본문도 그 표기를 따라야
합니다. 안 그러면 소지품에는 「빛의 문」인데 대사에서는 「빛의
게이트」라 부르는 일이 생깁니다 (실제로 있었습니다).

어려운 점은 **정당한 축약**과 가르는 것입니다. 「귀신의 뿔」을
문맥이 분명할 때 「뿔」이라 쓰는 건 자연스럽고, 26칸 제한 탓에
오히려 그래야 할 때도 있습니다. 표준 표기의 **마지막 낱말**이
남아 있으면 축약으로 보고 넘깁니다.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tools"))
import kogloss  # noqa: E402


class GlossaryTest(unittest.TestCase):
    def test_이름과_번역을_짝짓는다(self):
        rows = [("ひかりのゲート", "빛의　문")]
        self.assertEqual(kogloss.glossary(rows), {"ひかりのゲート": "빛의　문"})

    def test_색인_항목은_뺀다(self):
        """`이름／읽기` 는 정렬용이라 화면에 그대로 안 나옵니다."""
        rows = [("さか太刀／さかだち", "역태도／역태도")]
        self.assertEqual(kogloss.glossary(rows), {})

    def test_너무_짧은_이름은_뺀다(self):
        self.assertEqual(kogloss.glossary([("玉", "옥")]), {})

    def test_번역이_비면_뺀다(self):
        self.assertEqual(kogloss.glossary([("ひかりのゲート", "  ")]), {})


class NormTest(unittest.TestCase):
    def test_줄바꿈과_전각공백을_지운다(self):
        self.assertEqual(kogloss.norm("푸른\n열쇠　꾸러미"), "푸른열쇠꾸러미")


class CheckTest(unittest.TestCase):
    GLOSS = {"ひかりのゲート": "빛의　문", "鬼のツノ": "귀신의　뿔"}

    def test_표준_표기를_쓰면_통과(self):
        self.assertEqual(
            kogloss.check("ひかりのゲートで", "「빛의　문」으로", self.GLOSS), [])

    def test_줄바꿈으로_갈려도_통과(self):
        self.assertEqual(
            kogloss.check("ひかりのゲートで", "「빛의\n문」으로", self.GLOSS), [])

    def test_축약은_통과(self):
        """문맥이 분명하면 「귀신의 뿔」을 「뿔」로 줄여도 됩니다."""
        self.assertEqual(
            kogloss.check("鬼のツノを", "뿔을　보여주마", self.GLOSS), [])

    def test_다르게_옮기면_잡는다(self):
        bad = kogloss.check("ひかりのゲートで", "「빛의　게이트」로", self.GLOSS)
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0][0], "ひかりのゲート")

    def test_원문에_없으면_보지_않는다(self):
        self.assertEqual(kogloss.check("こんにちは", "안녕", self.GLOSS), [])


class RealTest(unittest.TestCase):
    JA = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "..", "script", "ja")

    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(cls.JA):
            raise unittest.SkipTest("script/ja 없음")

    def test_아이템표에서_용어집이_모인다(self):
        g = kogloss.load_glossary("script/ja", "script/ko")
        self.assertGreater(len(g), 300)
        self.assertEqual(g.get("ひかりのゲート"), "빛의　문")

    def test_지금은_불일치가_없다(self):
        """고칠 때마다 이 테스트가 지켜 줍니다.

        넘기기로 한 자리는 `kogloss.ALLOWED` 에 이유와 함께 적어 둡니다.
        """
        found = kogloss.audit("script/ja", "script/ko")
        self.assertEqual(found, [], f"용어 불일치 {len(found)}건")

    def test_넘긴_자리마다_이유가_적혀_있다(self):
        """빈 예외 목록은 검사를 무력화합니다."""
        self.assertTrue(kogloss.ALLOWED)
        src = open(os.path.join(os.path.dirname(kogloss.__file__),
                                "kogloss.py"), encoding="utf-8").read()
        block = src.split("ALLOWED = {")[1].split("}")[0]
        self.assertGreaterEqual(block.count("#"), 3, "예외에 이유가 없습니다")


if __name__ == "__main__":
    unittest.main()
