#!/usr/bin/env python3
"""tools/kosyl.py — 한글 음절 분해와 조합형 벌 규칙 테스트."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tools"))
import kosyl  # noqa: E402


class DecomposeTest(unittest.TestCase):
    def test_받침_없는_음절(self):
        self.assertEqual(kosyl.decompose("가"), (0, 0, 0))
        self.assertEqual(kosyl.decompose("나"), (2, 0, 0))
        self.assertEqual(kosyl.decompose("기"), (0, 20, 0))

    def test_받침_있는_음절(self):
        self.assertEqual(kosyl.decompose("각"), (0, 0, 1))
        self.assertEqual(kosyl.decompose("한"), (18, 0, 4))
        self.assertEqual(kosyl.decompose("힣"), (18, 20, 27))

    def test_음절이_아니면_거부(self):
        for ch in ("ㄱ", "A", "あ"):
            with self.assertRaises(ValueError):
                kosyl.decompose(ch)

    def test_분해와_조합이_왕복한다(self):
        for ch in ("가", "힣", "뷁", "쀍", "똠"):
            self.assertEqual(kosyl.compose_char(*kosyl.decompose(ch)), ch)

    def test_모든_음절을_왕복한다(self):
        for code in range(0xAC00, 0xD7A4):
            ch = chr(code)
            self.assertEqual(kosyl.compose_char(*kosyl.decompose(ch)), ch)


class CodeLayoutTest(unittest.TestCase):
    """음절 하나 = 코드 두 개. 앞 코드가 초성+중성, 뒤 코드가 종성입니다."""

    def test_앞뒤_코드로_음절을_되찾는다(self):
        for ch in ("가", "힣", "뷁", "왕"):
            lead, trail = kosyl.to_pair(ch)
            self.assertEqual(kosyl.from_pair(lead, trail), ch)

    def test_앞_코드는_399가지_뒤_코드는_28가지(self):
        leads = {kosyl.to_pair(chr(c))[0] for c in range(0xAC00, 0xD7A4)}
        trails = {kosyl.to_pair(chr(c))[1] for c in range(0xAC00, 0xD7A4)}
        self.assertEqual(len(leads), 19 * 21)
        self.assertEqual(len(trails), 28)


if __name__ == "__main__":
    unittest.main()
