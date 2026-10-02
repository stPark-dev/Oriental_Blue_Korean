#!/usr/bin/env python3
"""tools/koname.py — 이름 입력판의 가나 칸을 완성형 한글로."""
from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import koname  # noqa: E402

ROM = os.path.join(ROOT, "rom", "baserom.gba")
KO = os.path.join(ROOT, "script", "ko", koname.TABLE)


class SyllableTest(unittest.TestCase):
    def test_두_쪽에_80자씩_가나다_순(self):
        for page in koname.PAGES:
            self.assertEqual(len(page), koname.CELLS)
        flat = [c for page in koname.PAGES for c in page]
        self.assertEqual(flat, sorted(flat))
        self.assertEqual(len(set(flat)), len(flat))

    def test_완성형_음절만(self):
        for page in koname.PAGES:
            for c in page:
                self.assertTrue(0xAC00 <= ord(c) <= 0xD7A3, c)

    def test_기본_이름을_칠_수_있다(self):
        # 기본 이름 「텐란」「아오이」(DF3908 #1·#2).
        flat = "".join(koname.PAGES)
        for ch in "텐란아오이":
            self.assertIn(ch, flat)

    def test_첫_쪽은_ㄱ부터_ㅅ_둘째_쪽은_ㅇ부터(self):
        self.assertEqual(koname.PAGES[0][0], "가")
        self.assertLess(koname.PAGES[0][-1], "아")
        self.assertEqual(koname.PAGES[1][0], "아")


@unittest.skipUnless(os.path.exists(ROM), "rom/baserom.gba 없음")
class BoardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(ROM, "rb") as f:
            cls.rom = f.read()

    def test_판_칸은_쪽마다_80개(self):
        for t in koname.GRIDS:
            self.assertEqual(len(koname.cells(self.rom, t)), koname.CELLS)

    def test_두_쪽_칸은_겹치지_않는다(self):
        a, b = (set(koname.cells(self.rom, t)) for t in koname.GRIDS)
        self.assertFalse(a & b)

    def test_배치는_읽는_순서(self):
        ids = koname.cells(self.rom, koname.GRIDS[0])
        self.assertEqual(ids[:5], [554, 555, 556, 557, 558])
        self.assertEqual(koname.board(self.rom)[554], "가")

    def test_쪽_바꾸기_단추는_가리키는_쪽_이름(self):
        b = koname.board(self.rom)
        self.assertEqual(b[koname.TO_PAGE[0]], koname.LABELS[0])
        self.assertEqual(b[koname.TO_PAGE[1]], koname.LABELS[1])

    def test_새_판은_10x8_에_가나다_순(self):
        for t in koname.GRIDS:
            ids = koname.cells(self.rom, t)
            g = koname.grid(self.rom, t)
            self.assertEqual(len(g), 96)
            main = [g[r * 12 + c] for r in range(8) for c in range(10)]
            self.assertEqual(main, ids)

    def test_옆칸_위는_빈칸_단추는_그대로(self):
        for t in koname.GRIDS:
            old = [int.from_bytes(self.rom[t + i * 2:t + i * 2 + 2], "little")
                   for i in range(96)]
            g = koname.grid(self.rom, t)
            for r in range(8):
                for c in (10, 11):
                    i = r * 12 + c
                    if r < 2:
                        # 커서 점프(0x0B·0x17)가 닿는 칸이라 0 이 아닌 빈칸.
                        self.assertEqual(g[i], koname.BLANK)
                    else:
                        self.assertEqual(g[i], old[i])

    def test_설치는_두_표만_바꾼다(self):
        rom = bytearray(self.rom)
        koname.install(rom)
        for t in koname.GRIDS:
            got = [int.from_bytes(rom[t + i * 2:t + i * 2 + 2], "little")
                   for i in range(96)]
            self.assertEqual(got, koname.grid(self.rom, t))
        changed = [i for i in range(len(rom)) if rom[i] != self.rom[i]]
        lo, hi = min(koname.GRIDS), max(koname.GRIDS) + 192
        self.assertTrue(all(lo <= i < hi for i in changed))

    @unittest.skipUnless(os.path.exists(KO), "번역 파일 없음")
    def test_번역_파일이_배치와_같다(self):
        self.assertEqual(koname.diff(self.rom, KO), [])


if __name__ == "__main__":
    unittest.main()
