#!/usr/bin/env python3
"""tools/obfont.py — 폰트 글리프 해석 테스트."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tools"))
import obfont  # noqa: E402


def art(rows) -> list[str]:
    return ["".join("#" if v else "." for v in r) for r in rows]


class GlyphDecodeTest(unittest.TestCase):
    def test_전각은_1bpp_MSB_우선_16행이다(self):
        rom = bytearray(obfont.WIDE.base + 16)
        rom[obfont.WIDE.base:obfont.WIDE.base + 16] = bytes(
            [0x80, 0x01, 0xFF, 0x00] + [0] * 12)
        rows = art(obfont.glyph(bytes(rom), obfont.WIDE, 0))
        self.assertEqual(rows[0], "#.......")
        self.assertEqual(rows[1], ".......#")
        self.assertEqual(rows[2], "########")
        self.assertEqual(rows[3], "........")
        self.assertEqual(len(rows), 16)

    def test_반각은_같은_형식의_8행이다(self):
        rom = bytearray(obfont.SMALL.base + 8)
        rom[obfont.SMALL.base:obfont.SMALL.base + 8] = bytes(
            [0x18, 0x24] + [0] * 6)
        rows = art(obfont.glyph(bytes(rom), obfont.SMALL, 0))
        self.assertEqual(rows[0], "...##...")
        self.assertEqual(rows[1], "..#..#..")
        self.assertEqual(len(rows), 8)

    def test_시스템_폰트는_4bpp_하위_니블이_왼쪽_픽셀이다(self):
        rom = bytearray(obfont.SYSTEM.base + 32)
        rom[obfont.SYSTEM.base:obfont.SYSTEM.base + 4] = bytes([0x0F, 0xF0, 0, 0])
        rows = art(obfont.system_glyph(bytes(rom), obfont.SYSTEM.first))
        self.assertEqual(rows[0], "#..#....")


class RomFontTest(unittest.TestCase):
    """실제 ROM이 있을 때만 도는 회귀 테스트."""

    ROM = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "rom", "baserom.gba")

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(cls.ROM):
            raise unittest.SkipTest("rom/baserom.gba 없음")
        with open(cls.ROM, "rb") as f:
            cls.rom = f.read()

    def test_전각_코드_0xB5_가_히라가나_さ_모양이다(self):
        # 에뮬레이터 VRAM에서 확인한 실제 출력과 같은 비트열
        rows = art(obfont.glyph(self.rom, obfont.WIDE, 0xB5))
        self.assertEqual(rows[6:15], [
            "....#...",
            "....#...",
            ".#######",
            ".....#..",
            ".....#..",
            "..#####.",
            ".#....#.",
            ".#......",
            "..####..",
        ])

    def test_전각_폰트에는_ASCII가_없다(self):
        # 0x21-0x7E 는 반각 폰트(0x0D7DFB8)가 담당한다
        for c in range(0x21, 0x7F):
            self.assertTrue(obfont.is_empty(self.rom, obfont.WIDE, c),
                            f"코드 0x{c:02X} 에 전각 글리프가 있으면 안 된다")

    def test_반각_폰트에는_ASCII가_있다(self):
        for c in (0x41, 0x61, 0x30):
            self.assertFalse(obfont.is_empty(self.rom, obfont.SMALL, c),
                             f"코드 0x{c:02X} 에 반각 글리프가 있어야 한다")
        self.assertTrue(obfont.is_empty(self.rom, obfont.SMALL, 0x20))

    def test_두_폰트의_글리프_수(self):
        # 반각 586자는 문자 대응표(mktbl) 자수와 정확히 같다
        self.assertEqual(len(obfont.populated(self.rom, obfont.SMALL)), 586)
        self.assertEqual(len(obfont.populated(self.rom, obfont.WIDE)), 494)

    def test_전각_소문자_구간에_글리프가_있다(self):
        for c in range(0x151, 0x16B):
            self.assertFalse(obfont.is_empty(self.rom, obfont.WIDE, c),
                             f"코드 0x{c:03X} 에 소문자 글리프가 있어야 한다")

    def test_시스템_폰트는_JIS_X_0201_배열이다(self):
        self.assertTrue(any(any(r) for r in obfont.system_glyph(self.rom, 0x41)))
        self.assertFalse(any(any(r) for r in obfont.system_glyph(self.rom, 0x20)))

    def test_그리드와_폰트가_같은_색인_체계다(self):
        r = obfont.verify(self.rom)
        self.assertEqual(r["전각 ASCII 빈 글리프"], 94)
        # 불일치 31건은 원인이 전부 확인되었습니다:
        #   0x151-0x16A(26) 전각 소문자 — 그리드가 대문자만 제공
        #   0x150, 0x190      あ 중복 글리프 (본문 미사용)
        #   0x2E6             宿 (그리드 밖 한자)
        #   0x120, 0x122      전각 공백·， — 글리프가 비어 있음
        self.assertEqual(r["그리드 불일치"], 31)


if __name__ == "__main__":
    unittest.main()
