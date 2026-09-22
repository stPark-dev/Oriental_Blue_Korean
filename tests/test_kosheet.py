#!/usr/bin/env python3
"""tools/kosheet.py — 표 하나를 옮길 때 필요한 것을 한 파일에 모읍니다.

번역하면서 매번 손이 가는 일이 셋입니다.

  1. 이 줄에 한글 몇 자가 들어가나 (26칸 한도, 한글은 한 자에 2칸)
  2. 이 문장에 든 아이템 이름을 뭐라고 옮기기로 했더라
  3. 앞뒤 대사가 뭐라 이 말투가 맞나

셋을 미리 뽑아 둡니다. 번역은 하지 않습니다.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tools"))
import kosheet  # noqa: E402


class BudgetTest(unittest.TestCase):
    """한글은 한 자에 2칸. 그대로 남는 기호를 뺀 나머지를 나눕니다."""

    def test_기호가_없으면_１３자(self):
        self.assertEqual(kosheet.budget("あいうえお"), 13)

    def test_전각공백이_자리를_먹는다(self):
        self.assertEqual(kosheet.budget("あい　うえ"), 12)

    def test_괄호와_느낌표도_먹는다(self):
        self.assertEqual(kosheet.budget("「あい」！"), 11)

    def test_제어코드는_안_먹는다(self):
        self.assertEqual(kosheet.budget("<$10>あい"), 13)

    def test_빈_줄은_１３자(self):
        self.assertEqual(kosheet.budget(""), 13)


class TermTest(unittest.TestCase):
    GLOSS = {"ひかりのゲート": "빛의　문", "鬼のツノ": "귀신의　뿔"}

    def test_문장에_든_이름을_찾는다(self):
        self.assertEqual(kosheet.terms("ひかりのゲートで", self.GLOSS),
                         [("ひかりのゲート", "빛의　문")])

    def test_없으면_빈_목록(self):
        self.assertEqual(kosheet.terms("こんにちは", self.GLOSS), [])

    def test_여러_개면_나온_순서대로(self):
        got = kosheet.terms("鬼のツノとひかりのゲート", self.GLOSS)
        self.assertEqual([t for t, _ in got], ["鬼のツノ", "ひかりのゲート"])


class NeighbourTest(unittest.TestCase):
    def test_앞뒤_번역된_항목을_가져온다(self):
        rows = {1: "앞", 2: "", 3: "뒤"}
        self.assertEqual(kosheet.neighbours(rows, 2), ("앞", "뒤"))

    def test_없으면_빈_문자열(self):
        self.assertEqual(kosheet.neighbours({2: ""}, 2), ("", ""))

    def test_번역이_빈_이웃은_건너뛴다(self):
        rows = {1: "앞", 2: "", 3: "", 4: "뒤"}
        self.assertEqual(kosheet.neighbours(rows, 3), ("앞", "뒤"))


class PadTest(unittest.TestCase):
    """전각 문자는 터미널에서 두 칸을 먹습니다."""

    def test_전각은_두_칸(self):
        self.assertEqual(kosheet.show_width("あい"), 4)

    def test_반각은_한_칸(self):
        self.assertEqual(kosheet.show_width("ab"), 2)

    def test_전각을_감안해_채운다(self):
        self.assertEqual(kosheet.show_width(kosheet.pad("あい", 10)), 10)

    def test_넘치면_최소_한_칸은_띄운다(self):
        self.assertTrue(kosheet.pad("あいうえお", 4).endswith(" "))


class RenderTest(unittest.TestCase):
    def test_항목마다_번호와_원문이_들어간다(self):
        out = kosheet.render("AAA111", [
            kosheet.Entry(7, "あい", [13], [], "", ""),
        ])
        self.assertIn("AAA111", out)
        self.assertIn("0007", out)
        self.assertIn("あい", out)

    def test_한글_자수가_표시된다(self):
        out = kosheet.render("A", [kosheet.Entry(1, "あ", [13], [], "", "")])
        self.assertIn("13", out)

    def test_용어가_표시된다(self):
        out = kosheet.render("A", [
            kosheet.Entry(1, "ひかりのゲート", [13],
                          [("ひかりのゲート", "빛의　문")], "", ""),
        ])
        self.assertIn("빛의　문", out)


if __name__ == "__main__":
    unittest.main()
