#!/usr/bin/env python3
"""tools/mktbl.py — 문자 대응표 생성 테스트."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tools"))
import mktbl  # noqa: E402


class SupplementTest(unittest.TestCase):
    """이름 입력 그리드에 없지만 폰트에는 있는 문자."""

    ROM = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "rom", "baserom.gba")

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(cls.ROM):
            raise unittest.SkipTest("rom/baserom.gba 없음")
        with open(cls.ROM, "rb") as f:
            cls.rom = f.read()
        cls.table = mktbl.build(cls.rom)

    def test_전각_소문자_a부터_z까지_대응된다(self):
        # 그리드에는 대문자 Ａ-Ｚ 만 있고, 소문자는 폰트 0x151-0x16A 에만 있다
        for i, ch in enumerate("ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ"):
            self.assertEqual(self.table.get(0x151 + i), ch,
                             f"코드 0x{0x151 + i:03X}")

    def test_코드_0x20_은_공백이다(self):
        # 그리드에서는 빈칸이지만 본문에서 865회 쓰이고,
        # 작은 폰트의 글리프가 완전히 비어 있다 = 공백
        self.assertEqual(self.table.get(0x20), " ")

    def test_코드_0x2E6_은_한자_宿_이다(self):
        # 그리드 밖 한자. 글리프를 직접 확인했고 본문에서 4회 쓰인다
        self.assertEqual(self.table.get(0x2E6), "宿")

    def test_그리드에서_읽은_문자는_그대로_유지된다(self):
        self.assertEqual(self.table[0xAB], "あ")
        self.assertEqual(self.table[0xB5], "さ")
        self.assertEqual(self.table[0x41], "A")

    def test_보충이_그리드_값을_덮어쓰지_않는다(self):
        # 0x91-0xAA 는 그리드의 전각 대문자 구간이다
        self.assertEqual(self.table[0x91], "Ａ")


if __name__ == "__main__":
    unittest.main()
