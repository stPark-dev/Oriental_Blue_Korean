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


class TextTest(unittest.TestCase):
    """번역문은 칸 수와 띄어쓰기 자리를 원문에 맞춰야 합니다."""

    def test_모든_줄에_번역문이_있다(self):
        self.assertEqual(set(konarr.TEXT), set(konarr.LINES))

    def test_글자_수가_칸을_넘지_않는다(self):
        for name, text in konarr.TEXT.items():
            chars = [c for c in text if c != " "]
            self.assertLessEqual(len(chars), len(konarr.LINES[name]), name)

    def test_낫표는_붙은_쪽은_보통_간격_반대쪽만_좁다(self):
        xs = konarr.layout("가「나」다", 0)
        steps = [xs[k] - xs[k + 1] for k in range(len(xs) - 1)]
        # 가→「(좁게) 「→나(보통) 나→」(보통) 」→다(좁게)
        self.assertEqual(steps, [konarr.BRACKET_ADV, konarr.ADV,
                                 konarr.ADV, konarr.BRACKET_ADV])

    def test_앞_세_줄은_요청한_띄어쓰기(self):
        self.assertEqual(konarr.TEXT["L1"], "끝도없이 이어지는 푸른하늘")
        self.assertEqual(konarr.TEXT["L2"], "끝도없이 이어지는 푸른바다를 비춰")
        self.assertEqual(konarr.TEXT["L3"], "여기에 푸른대지가 있다")

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

    def test_낫표는_글자_쪽으로_붙여_그린다(self):
        C = konarr.CELL
        for ch, side in (("「", "right"), ("」", "left")):
            cell = konarr.render_cell(ch, self.font)
            xs = [i % C for i, v in enumerate(cell) if v == konarr.STROKE]
            mid = sum(xs) / len(xs)
            if side == "right":
                self.assertGreater(mid, C / 2, ch)
            else:
                self.assertLess(mid, C / 2, ch)

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

    def test_띄어쓰기대로_다시_배치한다(self):
        out = bytearray(self.rom)
        konarr.translate(out, konarr.TEXT, self.font)
        ob = konarr.read_sprites(self.rom, konarr.TABLES[1])
        nb = konarr.read_sprites(out, konarr.TABLES[1])
        na = konarr.read_sprites(out, konarr.TABLES[0])
        oa = konarr.read_sprites(self.rom, konarr.TABLES[0])
        for name, recs in konarr.LINES.items():
            text = konarr.TEXT[name]
            order = konarr.order_of(ob, recs)          # 원래 읽는 순서
            chars = [c for c in text if c != " "]
            xs = [nb[i]["x"] for i in order[:len(chars)]]
            self.assertEqual(xs, sorted(xs, reverse=True), name)
            self.assertTrue(all(-120 <= x <= 104 for x in xs), name)
            # 띄어쓰기 뒤 간격이 다른 간격보다 넓다
            gaps = [xs[k] - xs[k + 1] for k in range(len(xs) - 1)]
            spaced, k = set(), 0
            for c in text:
                if c == " ":
                    spaced.add(k - 1)
                else:
                    k += 1
            for g in spaced:
                self.assertGreater(gaps[g], max(gaps[j] for j in range(len(gaps))
                                                if j not in spaced and
                                                chars[j] not in "「」" and
                                                chars[j + 1] not in "「」"), name)
            # 두 표의 x 합(밀려 들어오는 거리)과 y 는 레코드마다 원래대로
            for i in recs:
                self.assertEqual(na[i]["x"] + nb[i]["x"],
                                 oa[i]["x"] + ob[i]["x"], f"{name} {i}")
                self.assertEqual(nb[i]["y"], ob[i]["y"])

    def test_x_밖의_속성은_그대로(self):
        out = bytearray(self.rom)
        konarr.translate(out, konarr.TEXT, self.font)
        for table in konarr.TABLES:
            for i in range(konarr.SPRITE_COUNT):
                a = table + i * 8
                self.assertEqual(common.u16(self.rom, a), common.u16(out, a))
                self.assertEqual(common.u16(self.rom, a + 2) & 0xFE00,
                                 common.u16(out, a + 2) & 0xFE00)

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
