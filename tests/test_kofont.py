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



class SyllableTableTest(unittest.TestCase):
    """음절 글리프는 16행 × (왼쪽 바이트, 오른쪽 바이트) = 32바이트입니다."""

    TTF = "/home/stpark/다운로드/hanguel2/galmuri/Galmuri14.ttf"

    def test_격자를_32바이트로_묶는다(self):
        grid = [[0] * 16 for _ in range(16)]
        grid[0][0] = 1           # 첫 행 맨 왼쪽
        grid[0][15] = 1          # 첫 행 맨 오른쪽
        grid[15][8] = 1          # 마지막 행 오른쪽 절반 첫 픽셀
        b = kofont.pack_glyph(grid)
        self.assertEqual(len(b), 32)
        self.assertEqual(b[0], 0x80)     # 0행 왼쪽
        self.assertEqual(b[1], 0x01)     # 0행 오른쪽
        self.assertEqual(b[30], 0x00)    # 15행 왼쪽
        self.assertEqual(b[31], 0x80)    # 15행 오른쪽

    def test_훅이_읽는_순서와_맞는다(self):
        """훅은 half 부터 두 바이트 간격으로 16번 읽습니다."""
        grid = [[1 if x < 8 else 0 for x in range(16)] for _ in range(16)]
        b = kofont.pack_glyph(grid)
        left = [b[i * 2] for i in range(16)]
        right = [b[i * 2 + 1] for i in range(16)]
        self.assertEqual(left, [0xFF] * 16)
        self.assertEqual(right, [0x00] * 16)

    def test_쓰는_음절만_저장한다(self):
        if not os.path.exists(self.TTF):
            self.skipTest("갈무리 폰트 없음")
        slot, glyphs, n = kofont.build_syllable_tables(
            self.TTF, ["한", "글"], 14, 2)
        self.assertEqual(n, 2)
        self.assertEqual(len(slot), kofont.SYLLABLES * 2)
        self.assertEqual(len(glyphs), (n + 1) * 32)

        def slot_of(ch):
            i = ord(ch) - 0xAC00
            return int.from_bytes(slot[i * 2:i * 2 + 2], "little")

        self.assertNotEqual(slot_of("한"), 0)
        self.assertNotEqual(slot_of("글"), 0)
        self.assertNotEqual(slot_of("한"), slot_of("글"))
        self.assertEqual(slot_of("가"), 0)          # 쓰지 않은 음절
        # 0번 슬롯은 빈 글리프로 비워 둔다
        self.assertEqual(glyphs[:32], bytes(32))
        self.assertTrue(any(glyphs[slot_of("한") * 32:slot_of("한") * 32 + 32]))

    def test_같은_입력이면_같은_결과(self):
        if not os.path.exists(self.TTF):
            self.skipTest("갈무리 폰트 없음")
        a = kofont.build_syllable_tables(self.TTF, ["한", "글"], 14, 2)
        b = kofont.build_syllable_tables(self.TTF, ["글", "한"], 14, 2)
        self.assertEqual(a, b)

if __name__ == "__main__":
    unittest.main()
