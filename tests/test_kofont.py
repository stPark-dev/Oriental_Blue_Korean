#!/usr/bin/env python3
"""tools/kofont.py — 한글 폰트 생성 테스트."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tools"))
import kofont  # noqa: E402
import obfont  # noqa: E402


class HalvesTest(unittest.TestCase):
    def test_16x16을_8x16_두_장으로_가른다(self):
        grid = [[0] * 16 for _ in range(16)]
        grid[0][0] = 1          # 왼쪽 맨 위
        grid[1][8] = 1          # 오른쪽 둘째 줄 맨 위
        grid[2][15] = 1         # 오른쪽 맨 끝
        left, right = kofont.halves(grid)
        self.assertEqual(len(left), 16)
        self.assertEqual(len(right), 16)
        self.assertEqual(left[0], 0x80)
        self.assertEqual(right[1], 0x80)
        self.assertEqual(right[2], 0x01)
        self.assertEqual(left[1], 0x00)


class BuildTest(unittest.TestCase):
    def test_원본_글리프를_보존하고_한글만_덮어쓴다(self):
        rom = bytearray(obfont.LARGE.base + 0x400 * 16)
        # 코드 0x0AB(あ) 자리에 표식을 넣어 보존되는지 본다
        keep = obfont.LARGE.base + 0xAB * 16
        rom[keep:keep + 16] = bytes(range(1, 17))
        glyphs = {0x301: bytes([0xFF] * 16), 0x302: bytes([0x0F] * 16)}
        blob = kofont.build_large(bytes(rom), glyphs)

        self.assertEqual(len(blob), kofont.LARGE_CODES * 16)
        self.assertEqual(blob[0xAB * 16:0xAB * 16 + 16], bytes(range(1, 17)))
        self.assertEqual(blob[0x301 * 16:0x301 * 16 + 16], bytes([0xFF] * 16))
        self.assertEqual(blob[0x302 * 16:0x302 * 16 + 16], bytes([0x0F] * 16))
        # 배정하지 않은 뱅크 4 자리는 비어 있어야 한다
        self.assertEqual(blob[0x401 * 16:0x401 * 16 + 16], bytes(16))

    def test_코드가_범위를_넘으면_거부(self):
        rom = bytearray(obfont.LARGE.base + 0x400 * 16)
        with self.assertRaises(ValueError):
            kofont.build_large(bytes(rom), {0x600: bytes(16)})


class InstallTest(unittest.TestCase):
    """폰트 재배치는 아카이브 오프셋 워드 하나만 바꾸면 됩니다."""

    ROM = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "rom", "baserom.gba")

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(cls.ROM):
            raise unittest.SkipTest("rom/baserom.gba 없음")
        with open(cls.ROM, "rb") as f:
            cls.rom = f.read()

    def test_원본_아카이브가_예상_위치를_가리킨다(self):
        self.assertEqual(kofont.entry_addr(self.rom, kofont.LARGE_ENTRY),
                         obfont.LARGE.base)
        self.assertEqual(kofont.entry_addr(self.rom, kofont.SMALL_ENTRY),
                         obfont.SMALL.base)

    def test_설치하면_아카이브가_새_위치를_가리킨다(self):
        rom = bytearray(self.rom)
        blob = bytes(kofont.LARGE_CODES * 16)
        at = 0xF00000
        kofont.install(rom, blob, at, kofont.LARGE_ENTRY)
        self.assertEqual(kofont.entry_addr(rom, kofont.LARGE_ENTRY), at + 4)
        self.assertEqual(int.from_bytes(rom[at:at + 4], "little"), len(blob))
        # 작은 폰트는 건드리지 않는다
        self.assertEqual(kofont.entry_addr(rom, kofont.SMALL_ENTRY),
                         obfont.SMALL.base)


if __name__ == "__main__":
    unittest.main()
