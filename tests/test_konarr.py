#!/usr/bin/env python3
"""tools/konarr.py — 오프닝 나레이션 한글화 테스트.

나레이션은 문자열이 아니라 **16×16 스프라이트**입니다. 표의 `attr2` 만 바꿔
글자를 갈아끼웁니다.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tools"))
import common  # noqa: E402
import konarr  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
ROM = os.path.join(ROOT, "rom", "baserom.gba")
FONT = os.path.join(ROOT, "font", "Galmuri14.ttf")

# 원문에서 칸 사이가 두 배로 벌어지는 자리 (그 앞까지의 글자 수)
GAP_AFTER = {"L1": 8, "L2": 8, "L3": 3, "L4": 4,
             "L5": 3, "L6": 7, "L7": 3, "L8": 6}


class TextTest(unittest.TestCase):
    """번역문은 칸 수와 띄어쓰기 자리를 원문에 맞춰야 합니다."""

    def test_모든_줄에_번역문이_있다(self):
        self.assertEqual(set(konarr.TEXT), set(konarr.LINES))

    def test_글자_수가_칸을_넘지_않는다(self):
        for name, text in konarr.TEXT.items():
            chars = [c for c in text if c != " "]
            self.assertLessEqual(len(chars), len(konarr.LINES[name]), name)

    def test_띄어쓰기_자리가_원문과_같다(self):
        """틈은 원문 간격에서 오므로, 번역문도 같은 자리에서 끊어야 합니다."""
        for name, text in konarr.TEXT.items():
            before = text.index(" ")
            self.assertEqual(before, GAP_AFTER[name], name)
            self.assertEqual(text.count(" "), 1, f"{name}: 띄어쓰기는 한 번만")

    def test_레코드는_겹치지_않는다(self):
        seen: set[int] = set()
        for records in konarr.LINES.values():
            self.assertFalse(seen & set(records))
            seen |= set(records)
        self.assertFalse(seen & set(konarr.DOTS))


class CellTest(unittest.TestCase):
    def setUp(self):
        if not os.path.exists(FONT):
            raise unittest.SkipTest("font/Galmuri14.ttf 없음")
        from PIL import ImageFont
        self.font = ImageFont.truetype(FONT, konarr.FONT_SIZE)

    def test_획을_그리고_둘레를_두른다(self):
        cell = konarr.render_cell("가", self.font)
        self.assertEqual(len(cell), konarr.CELL * konarr.CELL)
        self.assertIn(konarr.STROKE, cell)
        self.assertIn(konarr.EDGE, cell)
        self.assertNotIn(konarr.RIM, cell)     # 한글은 한 겹만 두릅니다

    def test_둘레는_획에_붙어_있다(self):
        cell = konarr.render_cell("가", self.font)
        C = konarr.CELL
        for i, v in enumerate(cell):
            if v != konarr.EDGE:
                continue
            y, x = divmod(i, C)
            near = any(cell[(y + dy) * C + x + dx] == konarr.STROKE
                       for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                       if 0 <= y + dy < C and 0 <= x + dx < C)
            self.assertTrue(near, f"({x},{y}) 둘레가 획에서 떨어져 있습니다")


class RomTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for p, why in ((ROM, "rom/baserom.gba 없음"), (FONT, "font/Galmuri14.ttf 없음")):
            if not os.path.exists(p):
                raise unittest.SkipTest(why)
        cls.rom = common.load(ROM)
        from PIL import ImageFont
        cls.font = ImageFont.truetype(FONT, konarr.FONT_SIZE)

    def test_두_표의_줄_구성이_같다(self):
        """두 표는 같은 글의 두 프레임이라 레코드마다 글리프가 같아야 합니다."""
        a = konarr.read_sprites(self.rom, konarr.TABLES[0])
        b = konarr.read_sprites(self.rom, konarr.TABLES[1])
        for i in range(konarr.SPRITE_COUNT):
            self.assertEqual(a[i]["tile"], b[i]["tile"], f"레코드 {i}")

    def test_읽는_순서는_x_내림차순(self):
        sp = konarr.read_sprites(self.rom, konarr.TABLES[1])
        order = konarr.order_of(sp, konarr.LINES["L3"])
        xs = [sp[i]["x"] for i in order]
        self.assertEqual(xs, sorted(xs, reverse=True))

    def test_글리프와_자리만_바뀐다(self):
        out = bytearray(self.rom)
        konarr.translate(out, konarr.TEXT, self.font)
        # 글리프 영역과 두 표 밖은 그대로
        self.assertEqual(bytes(self.rom[:konarr.TABLES[0]]),
                         bytes(out[:konarr.TABLES[0]]))
        end = konarr.TABLES[1] + konarr.SPRITE_COUNT * 8
        self.assertEqual(bytes(self.rom[end:]), bytes(out[end:]))

    def test_자리와_플래그는_그대로(self):
        out = bytearray(self.rom)
        konarr.translate(out, konarr.TEXT, self.font)
        for table in konarr.TABLES:
            a = konarr.read_sprites(self.rom, table)
            b = konarr.read_sprites(out, table)
            for i in range(konarr.SPRITE_COUNT):
                self.assertEqual(a[i]["x"], b[i]["x"], f"레코드 {i} x")
                self.assertEqual(a[i]["y"], b[i]["y"], f"레코드 {i} y")

    def test_점_세_개는_건드리지_않는다(self):
        out = bytearray(self.rom)
        konarr.translate(out, konarr.TEXT, self.font)
        a = konarr.read_sprites(self.rom, konarr.TABLES[1])
        b = konarr.read_sprites(out, konarr.TABLES[1])
        for i in konarr.DOTS:
            self.assertEqual(a[i]["tile"], b[i]["tile"])

    def test_같은_글자는_글리프를_함께_쓴다(self):
        out = bytearray(self.rom)
        stats = konarr.translate(out, konarr.TEXT, self.font)
        chars = {c for t in konarr.TEXT.values() for c in t if c != " "}
        self.assertEqual(stats["글리프"], len(chars))
        self.assertGreaterEqual(stats["여유 칸"], 0)


if __name__ == "__main__":
    unittest.main()
