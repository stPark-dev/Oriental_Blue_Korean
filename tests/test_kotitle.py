#!/usr/bin/env python3
"""tools/kotitle.py — 타이틀 로고 한글화 테스트.

타이틀 타일은 돌벽 위에 글자를 **투명하게 파낸** 그림입니다. 그래서 글자를
바꾸려면 원래 글자 자리를 벽으로 메운 뒤 새 글자를 파야 합니다.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tools"))
import common  # noqa: E402
import gbalz  # noqa: E402
import kotitle  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
ROM = os.path.join(ROOT, "rom", "baserom.gba")
LOGO = os.path.join(ROOT, "art", "title_ko.png")
FONT = os.path.join(ROOT, "font", "Galmuri7.ttf")


class ConstTest(unittest.TestCase):
    """상수는 분석 결과입니다 — 서로 어긋나면 안 됩니다."""

    def test_띠_맵은_6행_32열(self):
        self.assertEqual(len(kotitle.BAND_MAP), 6)
        for row in kotitle.BAND_MAP:
            self.assertEqual(len(row.split()), 32)

    def test_칠할_타일은_모두_띠_안에_있다(self):
        used = {int(e, 16) & 0x3FF
                for row in kotitle.BAND_MAP for e in row.split()}
        self.assertTrue(kotitle.PAINTABLE <= used)

    def test_칠할_타일은_블롭_범위_안이다(self):
        for t in kotitle.PAINTABLE:
            self.assertGreaterEqual(t, kotitle.TILE_BASE)

    def test_부제와_워드마크는_겹치지_않는다(self):
        self.assertFalse(kotitle.PAINTABLE & set(kotitle.SUBTITLE_TILES))


class WallTest(unittest.TestCase):
    """벽 복원: 투명(0)·흰색(15)·모르는 칸을 주변 벽 색으로 메웁니다."""

    def test_글자_자리를_주변_벽으로_메운다(self):
        w = h = 3
        canvas = bytearray([5, 5, 5,
                            5, 0, 5,
                            5, 5, 5])
        known = bytearray([1] * 9)
        out = kotitle.restore_wall(canvas, known, w, h)
        self.assertEqual(out[4], 5)

    def test_흰_테두리도_메운다(self):
        w = h = 3
        canvas = bytearray([6, 6, 6, 6, 15, 6, 6, 6, 6])
        out = kotitle.restore_wall(canvas, known=bytearray([1] * 9), w=w, h=h)
        self.assertEqual(out[4], 6)

    def test_모르는_칸도_메운다(self):
        w = h = 3
        canvas = bytearray([7, 7, 7, 7, 0, 7, 7, 7, 7])
        known = bytearray([1, 1, 1, 1, 0, 1, 1, 1, 1])
        out = kotitle.restore_wall(canvas, known, w, h)
        self.assertEqual(out[4], 7)

    def test_벽뿐이면_그대로(self):
        canvas = bytearray([2, 3, 4, 5])
        out = kotitle.restore_wall(canvas, bytearray([1] * 4), 2, 2)
        self.assertEqual(bytes(out), bytes(canvas))


class MaskTest(unittest.TestCase):
    def test_테두리는_1픽셀_고리(self):
        w = h = 5
        m = bytearray(w * h)
        m[2 * w + 2] = 1
        ring = kotitle.outline_of(m, w, h)
        self.assertEqual(sum(ring), 8)          # 3x3 에서 가운데를 뺀 8칸
        self.assertEqual(ring[2 * w + 2], 0)    # 글자 자리는 테두리가 아니다

    def test_2x2_열림으로_부스러기를_지운다(self):
        w = h = 6
        m = bytearray(w * h)
        m[0] = 1                                    # 외딴 점
        m[1 * w + 4] = m[2 * w + 4] = 1             # 1픽셀 폭 선
        for y in (3, 4):                            # 꽉 찬 2x2 블록
            for x in (1, 2):
                m[y * w + x] = 1
        out = kotitle.despeckle(m, w, h)
        self.assertEqual(out[0], 0)
        self.assertEqual(out[1 * w + 4], 0)
        self.assertEqual(out[3 * w + 1], 1)
        self.assertEqual(out[4 * w + 2], 1)


class RomTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for p, why in ((ROM, "rom/baserom.gba 없음"),
                       (LOGO, "art/title_ko.png 없음"),
                       (FONT, "font/Galmuri7.ttf 없음")):
            if not os.path.exists(p):
                raise unittest.SkipTest(why)
        cls.rom = common.load(ROM)

    def test_타일셋은_460타일(self):
        tiles = kotitle.load_tiles(self.rom)
        self.assertEqual(len(tiles), 460 * 32)

    def test_칠할_수_있는_타일만_바뀐다(self):
        before = kotitle.load_tiles(self.rom)
        out = bytearray(self.rom)
        kotitle.apply(out, LOGO, FONT)
        after = kotitle.load_tiles(out)
        allowed = kotitle.PAINTABLE | set(kotitle.SUBTITLE_TILES)
        for t in range(len(before) // 32):
            idx = t + kotitle.TILE_BASE
            if idx in allowed:
                continue
            self.assertEqual(before[t * 32:(t + 1) * 32],
                             after[t * 32:(t + 1) * 32],
                             f"건드리면 안 되는 타일 0x{idx:03X}")

    def test_부제_여섯_타일이_바뀐다(self):
        before = kotitle.load_tiles(self.rom)
        out = bytearray(self.rom)
        kotitle.apply(out, LOGO, FONT)
        after = kotitle.load_tiles(out)
        changed = [t for t in kotitle.SUBTITLE_TILES
                   if before[(t - kotitle.TILE_BASE) * 32:
                             (t - kotitle.TILE_BASE + 1) * 32]
                   != after[(t - kotitle.TILE_BASE) * 32:
                            (t - kotitle.TILE_BASE + 1) * 32]]
        self.assertEqual(len(changed), len(kotitle.SUBTITLE_TILES))

    def test_재압축이_원본_자리에_들어간다(self):
        packed, stats = kotitle.build(self.rom, LOGO, FONT)
        self.assertLessEqual(len(packed), kotitle.TILES_LEN)
        self.assertGreater(stats["칠한 타일"], 100)

    def test_패치한_롬을_다시_풀면_같다(self):
        packed, _ = kotitle.build(self.rom, LOGO, FONT)
        out = bytearray(self.rom)
        kotitle.apply(out, LOGO, FONT)
        raw, _ = gbalz.decompress(bytes(out), kotitle.TILES_AT)
        self.assertEqual(raw, gbalz.decompress(bytes(packed) + b"\x00" * 8, 0)[0])

    def test_타일셋_밖_롬은_그대로다(self):
        out = bytearray(self.rom)
        kotitle.apply(out, LOGO, FONT)
        lo, hi = kotitle.TILES_AT, kotitle.TILES_AT + kotitle.TILES_LEN
        self.assertEqual(bytes(self.rom[:lo]), bytes(out[:lo]))
        self.assertEqual(bytes(self.rom[hi:]), bytes(out[hi:]))


if __name__ == "__main__":
    unittest.main()
