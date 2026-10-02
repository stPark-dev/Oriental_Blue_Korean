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
SUBFONT = os.path.join(ROOT, "font", "Galmuri11-Condensed.ttf")


class ConstTest(unittest.TestCase):
    """상수는 분석 결과입니다 — 서로 어긋나면 안 됩니다."""

    def test_띠_맵은_8행_32열(self):
        self.assertEqual(len(kotitle.BAND_MAP), 8)
        for row in kotitle.BAND_MAP:
            self.assertEqual(len(row.split()), 32)
        self.assertEqual(kotitle.H, len(kotitle.BAND_MAP) * 8)

    def test_칠할_타일은_모두_띠_안에_있다(self):
        used = {int(e, 16) & 0x3FF
                for row in kotitle.BAND_MAP for e in row.split()}
        self.assertTrue(kotitle.PAINTABLE <= used)

    def test_칠할_타일은_블롭_범위_안이다(self):
        for t in kotitle.PAINTABLE:
            self.assertGreaterEqual(t, kotitle.TILE_BASE)

    def test_부제와_워드마크는_겹치지_않는다(self):
        self.assertFalse(kotitle.PAINTABLE & set(kotitle.SUBTITLE_TILES))

    def test_거울_쌍은_따로_다룬다(self):
        """거울 쌍은 두 칸이 한 타일을 나눠 쓰므로 보통 칸과 섞으면 안 됩니다."""
        self.assertFalse(kotitle.PAINTABLE & set(kotitle.MIRROR_TILES))
        used = [e for row in kotitle.BAND_MAP for e in row.split()]
        for t in kotitle.MIRROR_TILES:
            n = sum(1 for e in used if int(e, 16) & 0x3FF == t)
            self.assertEqual(n, 2, f"0x{t:03X} 는 띠에 두 번 나와야 합니다")


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


class TextureWallTest(unittest.TestCase):
    """무늬 복사: 구멍은 같은 줄에서 가장 가까운 온전한 돌벽 칸의 같은
    자리 화소로 메웁니다 (옆 화소를 번지게 칠하면 가로 줄무늬가 납니다)."""

    def _canvas(self):
        w, h = 32, 8                       # 8x8 칸 4개가 한 줄
        canvas = bytearray(w * h)
        for y in range(h):
            for x in range(w):
                canvas[y * w + x] = 1 + (x * 3 + y * 5) % 13   # 1~13 무늬
        return w, h, canvas

    def test_구멍은_가까운_온전한_칸의_같은_자리로(self):
        w, h, canvas = self._canvas()
        src = bytes(canvas)
        for y in range(2, 6):              # 칸 1 에 구멍
            for x in range(10, 14):
                canvas[y * w + x] = kotitle.TRANSPARENT
        out = kotitle.restore_wall_texture(canvas, bytearray([1] * (w * h)),
                                           w, h)
        for y in range(2, 6):
            for x in range(10, 14):
                # 이웃 칸 0 또는 2 의 같은 자리 화소
                self.assertIn(out[y * w + x],
                              (src[y * w + x - 8], src[y * w + x + 8]))
        self.assertNotIn(kotitle.TRANSPARENT, out)

    def test_모르는_칸은_통째로_복사한다(self):
        w, h, canvas = self._canvas()
        src = bytes(canvas)
        known = bytearray([1] * (w * h))
        for y in range(h):
            for x in range(16, 24):
                known[y * w + x] = 0
        out = kotitle.restore_wall_texture(canvas, known, w, h)
        cell = [out[y * w + x] for y in range(h) for x in range(16, 24)]
        left = [src[y * w + x] for y in range(h) for x in range(8, 16)]
        right = [src[y * w + x] for y in range(h) for x in range(24, 32)]
        self.assertIn(cell, (left, right))

    def test_밝기가_비슷한_칸을_고른다(self):
        # 가장 가까운 칸이 어두운 테두리라도, 남은 화소의 밝기가 비슷한
        # 조금 먼 칸을 고릅니다 (가장자리에 어두운 네모가 생겼습니다).
        w, h = 32, 8
        canvas = bytearray(w * h)
        for y in range(h):
            for x in range(w):
                c = x // 8
                canvas[y * w + x] = (2 if c == 0 else 12 if c in (1, 3)
                                     else 11)
        canvas[0 * w + 8 + 3] = kotitle.TRANSPARENT     # 칸 1 에 구멍 하나
        # 칸 0(어두움 2, 거리 1) 보다 칸 3(밝음 12, 거리 2)이 맞습니다
        canvas = bytearray(canvas)
        for y in range(h):
            for x in range(16, 24):
                canvas[y * w + x] = kotitle.WHITE       # 칸 2 는 구멍
        out = kotitle.restore_wall_texture(canvas, bytearray([1] * (w * h)),
                                           w, h)
        self.assertEqual(out[0 * w + 8 + 3], 12)

    def test_같은_칸을_되풀이해_쓰지_않는다(self):
        # 한 칸을 여러 번 가져오면 같은 질감이 띠처럼 반복됩니다.
        w, h = 64, 16                      # 8칸 x 2줄
        canvas = bytearray(w * h)
        for y in range(h):
            for x in range(w):
                # 칸마다 배치는 다르고 평균 밝기는 같은 무늬
                canvas[y * w + x] = (5 + (x + y + 3 * (x // 8)) % 3
                                     if y < 8 else 0)
        out = kotitle.restore_wall_texture(canvas, bytearray([1] * (w * h)),
                                           w, h)
        tiles = {bytes(out[(8 + y) * w + c * 8 + x]
                       for y in range(8) for x in range(8)) for c in range(8)}
        self.assertGreaterEqual(len(tiles), 3)   # 아래 줄이 여러 칸에서 옴

    def test_멀리_있어도_번지기보다_무늬를_쓴다(self):
        w, h = 64, 48                      # 6줄 — 맨 위 줄만 온전
        canvas = bytearray(w * h)
        for y in range(h):
            for x in range(w):
                canvas[y * w + x] = 3 + (x + y) % 7 if y < 8 else 0
        out = kotitle.restore_wall_texture(canvas, bytearray([1] * (w * h)),
                                           w, h)
        # 3줄 아래 칸도 맨 위 줄의 무늬(번짐이면 같은 색이 가로로 이어짐)
        row = out[30 * w:30 * w + 8]
        self.assertGreater(len(set(row)), 2)

    def test_가져온_무늬의_밝기를_원래_칸에_맞춘다(self):
        # 온전한 칸이 어두운 것뿐이어도, 남은 화소가 밝으면 무늬를 밝게
        # 옮겨 계단처럼 끊기지 않게 합니다 (돌벽 색 번호 1~10 은 밝기순).
        w, h = 16, 8
        canvas = bytearray(w * h)
        for y in range(h):
            for x in range(w):
                canvas[y * w + x] = 2 + (x + y) % 2 if x < 8 else 6
        for y in range(2, 8):                       # 칸 1: 밝은(6) 화소 둘만 남김
            for x in range(8, 16):
                canvas[y * w + x] = kotitle.TRANSPARENT
        out = kotitle.restore_wall_texture(canvas, bytearray([1] * (w * h)),
                                           w, h)
        filled = [out[y * w + x] for y in range(2, 8) for x in range(8, 16)]
        self.assertGreaterEqual(sum(filled) / len(filled), 5.5)
        self.assertGreater(len(set(filled)), 1)     # 무늬는 살아 있음

    def test_거울_자리가_멀쩡하면_그_화소로_메운다(self):
        # 띠의 돌벽은 좌우 대칭(맵이 오른쪽 절반을 뒤집어 씀)이라, 한쪽 구멍은
        # 반대쪽 같은 자리의 원본 화소가 가장 자연스럽습니다.
        w, h = 96, 8                       # 양 끝 40화소 안쪽에 구멍
        canvas = bytearray(w * h)
        for y in range(h):
            for x in range(w // 2):
                v = 1 + (x * 7 + y * 3) % 10
                canvas[y * w + x] = v
                canvas[y * w + w - 1 - x] = v
        for y in range(2, 6):
            for x in range(1, 5):
                canvas[y * w + x] = kotitle.TRANSPARENT
        out = kotitle.restore_wall_texture(canvas, bytearray([1] * (w * h)),
                                           w, h, mirror=True)
        for y in range(2, 6):
            for x in range(1, 5):
                self.assertEqual(out[y * w + x], canvas[y * w + w - 1 - x])

    def test_밝기를_옮겨도_돌벽_색_안에_머문다(self):
        self.assertEqual(kotitle.shift_tone(9, 4), 10)
        self.assertEqual(kotitle.shift_tone(2, -4), 1)
        self.assertEqual(kotitle.shift_tone(12, 3), 12)   # 문장 색은 그대로

    def test_온전한_칸이_없으면_번지게_메운다(self):
        w, h = 8, 8
        canvas = bytearray([5] * 64)
        canvas[27] = kotitle.WHITE
        out = kotitle.restore_wall_texture(canvas, bytearray([1] * 64), w, h)
        self.assertEqual(out[27], 5)


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
        allowed = (kotitle.PAINTABLE | set(kotitle.SUBTITLE_TILES)
                   | set(kotitle.MIRROR_TILES) | set(kotitle.OVERLAY_TILES))
        for t in range(len(before) // 32):
            idx = t + kotitle.TILE_BASE
            if idx in allowed:
                continue
            self.assertEqual(before[t * 32:(t + 1) * 32],
                             after[t * 32:(t + 1) * 32],
                             f"건드리면 안 되는 타일 0x{idx:03X}")

    @unittest.skipUnless(os.path.exists(SUBFONT), "Galmuri11-Condensed 없음")
    def test_부제_글꼴은_원래_픽셀_크기(self):
        from PIL import Image, ImageDraw, ImageFont
        face = ImageFont.truetype(SUBFONT, kotitle.SUBTITLE_SIZE)
        img = Image.new("L", (64, 24), 0)
        ImageDraw.Draw(img).text((2, 2), kotitle.SUBTITLE_TEXT, font=face, fill=255)
        self.assertEqual([v for v in img.getdata() if 40 < v < 215], [])

    def test_부제는_두_줄_열두_타일(self):
        # 원본 「青の天外」는 16화소 높이 — 위 줄 0x140~ 와 아래 줄 0x160~.
        # 아래 줄만 고치면 위 줄에 일본어 글자 윗부분이 남습니다.
        self.assertEqual(len(kotitle.SUBTITLE_TILES), 12)
        self.assertIn(0x140, kotitle.SUBTITLE_TILES)
        self.assertIn(0x165, kotitle.SUBTITLE_TILES)

    @unittest.skipUnless(os.path.exists(SUBFONT), "Galmuri11-Condensed 없음")
    def test_부제에_원본_글자가_남지_않고_한글이_두_줄에_걸친다(self):
        tiles = kotitle.load_tiles(self.rom)
        stats = kotitle.render_subtitle(tiles, SUBFONT)
        canvas = kotitle.subtitle_canvas(tiles)
        mask = kotitle.subtitle_text_mask(SUBFONT, kotitle.SUBTITLE_TEXT)
        w = kotitle.SUBTITLE_W
        for i, v in enumerate(canvas):
            if v == kotitle.WHITE:
                self.assertTrue(mask[i], f"원본 흰 화소가 남음 {i % w},{i // w}")
        rows = {i // w for i, m in enumerate(mask) if m}
        self.assertTrue(any(r < 8 for r in rows) and any(r >= 8 for r in rows))
        self.assertGreater(stats["부제 화소"], 60)

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

    def test_스프라이트_모드는_띠를_돌벽으로만_메운다(self):
        # 로고는 kologo 가 OBJ 로 얹습니다. 띠의 칠할 칸에는 파낸 자리
        # (투명)·흰 테두리가 남지 않아야 합니다.
        out = bytearray(self.rom)
        stats = kotitle.apply(out, LOGO, FONT, sprite=True)
        tiles = kotitle.load_tiles(out)
        for idx in kotitle.PAINTABLE:
            px = kotitle.tile_pixels(tiles, idx)
            self.assertNotIn(kotitle.TRANSPARENT, px, f"0x{idx:03X}")
            self.assertNotIn(kotitle.WHITE, px, f"0x{idx:03X}")
        self.assertGreater(stats["부제 화소"], 0)   # 부제는 원래 판에 한글로

    def test_덮개_칸은_못_칠하는_칸뿐이고_돌벽만_담는다(self):
        cells = kotitle.cover_cells(kotitle.load_tiles(self.rom))
        self.assertGreater(len(cells), 0)
        for sx, sy, px in cells:
            self.assertEqual(len(px), 64)
            self.assertNotIn(kotitle.TRANSPARENT, px)
            self.assertNotIn(kotitle.WHITE, px)
            self.assertEqual((sx % 8, sy % 8), (0, 0))
            self.assertTrue(0 <= sx < 240 and 0 <= sy < 64)
        # 물결 창 타일(0x01~0x0E)로 된 아래 두 줄 끝 획과 거울 쌍이 들어갑니다
        pos = {(sx, sy) for sx, sy, _ in cells}
        self.assertIn((28 * 8 - 8, 6 * 8), pos)          # 오른쪽 끝 획
        self.assertIn((15 * 8 - 8, 4 * 8), pos)          # 거울 쌍
        self.assertIn((16 * 8 - 8, 5 * 8), pos)
        self.assertIn((30 * 8 - 8, 6 * 8), pos)          # 오른쪽 끝 흰 점
        self.assertIn((24 * 8 - 8, 1 * 8), pos)          # 「블」 위 흰 점

    def test_두_블록_밖_롬은_그대로다(self):
        out = bytearray(self.rom)
        kotitle.apply(out, LOGO, FONT)
        lo = kotitle.INTRO_AT
        mid = kotitle.INTRO_AT + kotitle.INTRO_LEN
        hi = kotitle.TILES_AT + kotitle.TILES_LEN
        self.assertEqual(kotitle.TILES_AT, mid, "두 블록은 붙어 있습니다")
        self.assertEqual(bytes(self.rom[:lo]), bytes(out[:lo]))
        self.assertEqual(bytes(self.rom[hi:]), bytes(out[hi:]))


class IntroTest(unittest.TestCase):
    """오프닝 끝의 영문 로고 — 맵이 순차라 칸을 통째로 쓸 수 있습니다."""

    @classmethod
    def setUpClass(cls):
        for p, why in ((ROM, "rom/baserom.gba 없음"), (LOGO, "art/title_ko.png 없음")):
            if not os.path.exists(p):
                raise unittest.SkipTest(why)
        cls.rom = common.load(ROM)

    def test_타일은_254장(self):
        self.assertEqual(len(kotitle.load_intro(self.rom)), 254 * 64)

    def test_그림을_폈다_되돌리면_같다(self):
        tiles = kotitle.load_intro(self.rom)
        canvas = kotitle.intro_canvas(tiles)
        self.assertEqual(len(canvas), kotitle.INTRO_W * kotitle.INTRO_H)
        out = bytearray(len(tiles))
        kotitle.set_intro_canvas(out, canvas)
        self.assertEqual(bytes(out), bytes(tiles))

    def test_재압축이_원본_자리에_들어간다(self):
        packed, stats = kotitle.build_intro(self.rom, LOGO)
        self.assertLessEqual(len(packed), kotitle.INTRO_LEN)
        self.assertGreater(stats["오프닝 화소"], 1000)

    def test_판_색은_그대로_두고_글자만_판다(self):
        packed, _ = kotitle.build_intro(self.rom, LOGO)
        out = bytearray(self.rom)
        out[kotitle.INTRO_AT:kotitle.INTRO_AT + len(packed)] = packed
        canvas = kotitle.intro_canvas(kotitle.load_intro(out))
        colours = set(canvas)
        self.assertLessEqual(colours, {0, 1, kotitle.INTRO_PLATE})
        self.assertIn(0, colours)          # 글자 구멍
        self.assertIn(1, colours)          # 흰 테두리


if __name__ == "__main__":
    unittest.main()
