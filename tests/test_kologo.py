#!/usr/bin/env python3
"""tools/kologo.py — 타이틀 한글 로고를 스프라이트로 얹기."""
from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import kologo  # noqa: E402

try:
    from capstone import CS_ARCH_ARM, CS_MODE_THUMB, Cs
    MD = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
except ImportError:  # pragma: no cover
    MD = None

ART = os.path.join(ROOT, "art", "title_ko.png")
AT = 0x081BE000


class LayoutTest(unittest.TestCase):
    """224 폭 그림을 GBA 스프라이트 크기로 자릅니다."""

    def test_조각이_그림을_빈틈없이_덮는다(self):
        pieces = kologo.layout(224, 72)
        cover = set()
        for x, y, w, h in pieces:
            for yy in range(y, y + h):
                for xx in range(x, x + w):
                    self.assertNotIn((xx, yy), cover)
                    cover.add((xx, yy))
        self.assertEqual(len(cover), 224 * 72)

    def test_이어진_덮개_칸은_한_스프라이트로_묶는다(self):
        runs = kologo.cover_runs([(0, 48), (8, 48), (16, 48), (24, 48),
                                  (32, 48), (80, 56)])
        self.assertEqual(runs, [(0, 48, 32), (32, 48, 8), (80, 56, 8)])

    def test_쓰는_크기는_스프라이트_모양뿐(self):
        for _x, _y, w, h in kologo.layout(224, 72):
            self.assertIn((w, h), kologo.SHAPES)

    def test_속성_인코딩(self):
        # 64x32 는 가로형(1) 크기 3, 32x8 은 가로형 크기 1
        a0, a1, a2 = kologo.attrs(10, 20, 64, 32, 0x200)
        self.assertEqual(a0, 20 | (1 << 14))
        self.assertEqual(a1, 10 | (3 << 14))
        self.assertEqual(a2, 0x200 | (kologo.PALETTE << 12))
        a0, a1, _ = kologo.attrs(0, 0, 32, 8, 0)
        self.assertEqual((a0 >> 14, a1 >> 14), (1, 1))
        a0, a1, _ = kologo.attrs(0, 0, 32, 32, 0)
        self.assertEqual((a0 >> 14, a1 >> 14), (0, 2))


@unittest.skipUnless(os.path.exists(ART), "art/title_ko.png 없음")
class AssetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        covers = [(48, 48, bytes([3] * 64)),
                  (56, 48, bytes([4] * 64)), (112, 32, bytes([5] * 64))]
        cls.a = kologo.build_assets(ART, covers)

    def test_부제_뒤는_불투명한_띠(self):
        # 부제 글자가 배경판 부제 판보다 커서, 글자 사이로 뒤의 금색
        # 문장이 비쳤습니다. 부제 칸 안쪽은 빈틈 없이 칠해야 합니다.
        from PIL import Image
        raw = Image.open(ART).convert("RGBA")
        raw = raw.crop(raw.getbbox()).resize((kologo.LOGO_W, kologo.LOGO_H),
                                             Image.LANCZOS)
        x0, y0, x1, y1 = kologo.banner_rect(raw)
        self.assertLess(x1 - x0, kologo.LOGO_W // 2)      # 글자 뒤만
        im = kologo._image(ART)
        a = im.getchannel("A")
        for y in range(y0, y1):
            for x in range(x0, x1):
                self.assertGreaterEqual(a.getpixel((x, y)), 128, (x, y))

    def test_글자_몸통은_창_테두리와_부제는_그림(self):
        body, normal = kologo.layers(ART)
        W, H = kologo.LOGO_W, kologo.LOGO_H
        self.assertEqual(len(body), W * H)
        im = kologo._image(ART)
        sub = kologo.subtitle_mask(im)
        src, px = im.load(), normal.load()
        for i in range(W * H):
            x, y = i % W, i // W
            if body[i]:
                self.assertFalse(sub[i])                 # 창은 워드마크만
                self.assertTrue(kologo.is_body(src[x, y]))
                self.assertLess(px[x, y][3], 128)        # 창 자리엔 그림 없음
            elif src[x, y][3] >= 128:
                self.assertEqual(px[x, y], src[x, y])    # 나머지는 그림 그대로
        self.assertGreater(sum(body), 1000)

    def test_창_조각은_OBJ_창_모드(self):
        wins = self.a["windows"]
        self.assertGreater(len(wins), 0)
        for a0, _a1, _a2 in wins:
            self.assertEqual((a0 >> 10) & 3, 2)

    def test_팔레트는_16색_0번은_투명(self):
        self.assertEqual(len(self.a["palette"]), 32)

    def test_빈_조각은_건너뛴다(self):
        self.assertLessEqual(len(self.a["oam"]), len(kologo.layout(
            kologo.LOGO_W, kologo.LOGO_H)))
        self.assertGreater(len(self.a["oam"]), 0)

    def test_타일은_스프라이트_영역_안에_든다(self):
        n = len(self.a["tiles"]) // 32
        self.assertLessEqual(kologo.TILE_BASE + n, 0x400)
        for _a0, _a1, a2 in self.a["oam"]:
            self.assertGreaterEqual(a2 & 0x3FF, kologo.TILE_BASE)

    def test_덮개는_로고_뒤_칸에_팔레트_14로(self):
        covers = self.a["covers"]
        self.assertGreater(len(covers), 0)
        for _a0, _a1, a2 in covers:
            self.assertEqual(a2 >> 12, kologo.COVER_PALETTE)
        self.assertLessEqual(kologo.FIRST_SLOT + len(self.a["oam"])
                             + len(covers), 128)

    def test_압축을_풀면_타일과_같다(self):
        import gbalz
        self.assertEqual(gbalz.decompress(self.a["lz"], 0)[0], self.a["tiles"])

    def test_서명은_타일_안의_0이_아닌_워드(self):
        off, val = self.a["sig"]
        t = self.a["tiles"]
        self.assertEqual(int.from_bytes(t[off:off + 4], "little"), val)
        self.assertNotEqual(val, 0)


@unittest.skipIf(MD is None, "capstone 없음")
class HookTest(unittest.TestCase):
    def setUp(self):
        self.code = kologo.build_hook(AT, table=0x081C0000, count=11,
                                      lz=0x081C1000, palette=0x081C0100,
                                      sig=(0x40, 0x12345678))
        self.dis = [f"{i.mnemonic} {i.op_str}".strip()
                    for i in MD.disasm(self.code, AT)]
        self.pool = {int.from_bytes(self.code[i:i + 4], "little")
                     for i in range(0, len(self.code) - 3, 4)}

    def test_레지스터를_지키고_원래_두_명령을_되살린다(self):
        self.assertEqual(self.dis[0], "push {r4, r5, r6, r7, lr}")
        self.assertIn(0x040000D4, self.pool)
        self.assertIn(0x03003150, self.pool)
        self.assertEqual(self.dis[-1] if self.dis[-1].startswith("bx")
                         else [d for d in self.dis if d.startswith("bx")][-1],
                         "bx r3")

    def test_타이틀을_BG_설정과_맵_값으로_가린다(self):
        self.assertIn(kologo.TITLE_BGCNT01, self.pool)
        self.assertIn(kologo.TITLE_BGCNT23, self.pool)
        self.assertIn(kologo.TITLE_MAP_AT, self.pool)

    def test_타일은_BIOS_로_푼다(self):
        self.assertIn("svc #0x12", self.dis)
        self.assertIn(kologo.OBJ_VRAM + kologo.TILE_BASE * 32, self.pool)

    def test_OAM_은_세_속성만_쓴다(self):
        # 아핀 파라미터(+6)는 게임이 따로 채우므로 건드리지 않습니다.
        self.assertFalse(any("#6]" in d and d.startswith("strh")
                             for d in self.dis))

    def test_설치는_받은_자리만큼만_쓰고_겹치지_않는다(self):
        # 크기를 임시 주소(0)로 재면 리터럴 풀의 0 들이 하나로 합쳐져
        # 실제보다 작게 나옵니다. 그러면 뒤에 받은 자리가 훅을 덮습니다.
        if not os.path.exists(ART):
            self.skipTest("art/title_ko.png 없음")
        import common
        rom = bytearray(b"\xff" * 0x400000)
        o = kologo.SITE - common.ROM_BASE
        rom[o:o + 4] = kologo.SITE_ORIG
        taken = []

        def alloc(n, align, near):
            at = 0x300000 + sum(x[1] for x in taken)
            at += (-at) % align
            taken.append((at, n))
            return at
        stats = kologo.install(rom, alloc, ART, covers=[])
        hook_at = stats["훅"] - common.ROM_BASE
        size = dict(taken)[hook_at]
        hook = kologo.build_hook(stats["훅"], stats["표"], stats["조각"],
                                 stats["자료"], stats["팔레트"],
                                 kologo.build_assets(ART, [])["sig"])
        self.assertEqual(len(hook), size)
        self.assertEqual(bytes(rom[hook_at:hook_at + size]), hook)

    def test_타이틀에서_OBJ_창을_켜고_나가면_되돌린다(self):
        self.assertIn(kologo.DISPCNT, self.pool)
        self.assertIn(kologo.WINOUT, self.pool)
        self.assertIn(kologo.WINOUT_TITLE, self.pool)
        self.assertIn(kologo.WIN_FLAG, self.pool)
        self.assertTrue(any(d.startswith("orrs") for d in self.dis))
        self.assertTrue(any(d.startswith("bics") for d in self.dis))

    def test_창_안에는_돌벽과_스프라이트가_없다(self):
        objwin = kologo.WINOUT_TITLE >> 8
        self.assertEqual(objwin & 0x04, 0)          # BG2(돌벽) 끔
        self.assertEqual(objwin & 0x10, 0)          # OBJ(덮개) 끔
        self.assertEqual(objwin & 0x08, 0)          # BG3(금색 문장) 끔
        self.assertEqual(objwin & 0x03, 0x03)       # BG0·BG1(물결) 켬
        self.assertEqual(kologo.WINOUT_TITLE & 0xFF, 0x3F)   # 창 밖은 그대로

    def test_호출_지점_원본(self):
        self.assertEqual(kologo.SITE_ORIG, bytes.fromhex("08490848"))
