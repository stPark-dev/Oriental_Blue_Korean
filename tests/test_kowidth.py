#!/usr/bin/env python3
"""tools/kowidth.py — 번역문 폭 검사 테스트.

모든 글자가 8픽셀 폭 칸 하나를 씁니다. 한글 음절만 두 칸(16픽셀)입니다.
따라서 원문보다 **글자 수가 적어도 폭은 넘칠 수 있습니다.**
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tools"))
import kowidth  # noqa: E402


class CellsTest(unittest.TestCase):
    def test_한글_음절은_두_칸(self):
        self.assertEqual(kowidth.cells("가"), 2)
        self.assertEqual(kowidth.cells("한글"), 4)

    def test_그_밖의_문자는_한_칸(self):
        self.assertEqual(kowidth.cells("あ"), 1)
        self.assertEqual(kowidth.cells("A"), 1)
        self.assertEqual(kowidth.cells("　"), 1)

    def test_태그는_폭에서_뺀다(self):
        # <$10> 같은 제어 코드는 그려지지 않습니다
        self.assertEqual(kowidth.cells("<$10>가"), 2)

    def test_서식_지정자는_자리수만큼_센다(self):
        # <$1F>-3d 는 숫자 세 자리 -> 세 칸
        self.assertEqual(kowidth.cells("<$1F>-3d"), 3)
        self.assertEqual(kowidth.cells("<$1F>d"), 1)
        # %s 는 길이를 알 수 없으므로 0 으로 봅니다
        self.assertEqual(kowidth.cells("<$1F>s"), 0)
        self.assertEqual(kowidth.cells("<$1F>8s"), 8)

    def test_줄마다_따로_잰다(self):
        self.assertEqual(kowidth.line_cells("가나\n다"), [4, 2])


class CheckTest(unittest.TestCase):
    def test_원문보다_넓으면_잡아낸다(self):
        # 원문 6칸, 번역 8칸
        over = kowidth.check("こうげき力", "공격력을")
        self.assertEqual(len(over), 1)
        self.assertEqual(over[0], (0, 8, 5))

    def test_원문보다_좁으면_통과(self):
        self.assertEqual(kowidth.check("こうげきりょく", "공격력"), [])

    def test_줄별로_따로_본다(self):
        # 0번째 줄 4칸=4칸, 1번째 줄 2칸=2칸 -> 통과
        self.assertEqual(kowidth.check("ああああ\nいい", "가가\n나"), [])
        # 1번째 줄만 초과
        over = kowidth.check("ああああ\nいい", "가가\n나나")
        self.assertEqual([o[0] for o in over], [1])

    def test_번역이_줄이_더_많으면_잡아낸다(self):
        over = kowidth.check("ああ", "가\n나")
        self.assertEqual([o[0] for o in over], [1])


if __name__ == "__main__":
    unittest.main()
