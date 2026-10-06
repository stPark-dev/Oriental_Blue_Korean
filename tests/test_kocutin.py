#!/usr/bin/env python3
"""tools/kocutin.py — 대도 초반 연출의 「たすけて」 글자 그림을 한글로."""
from __future__ import annotations

import hashlib
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import kocutin  # noqa: E402

ROM = os.path.join(ROOT, "rom", "baserom.gba")
ART = os.path.join(ROOT, "art", "tasukete_ko.png")


class LayoutTest(unittest.TestCase):
    """72×16 그림 = 스프라이트 셋 (OBJ 타일 24~41, 1D 매핑).

    왼쪽 32×16 은 타일 34~41, 가운데 32×16 은 26~33, 오른쪽 8×16 은 24·25.
    ROM 에는 타일 24 부터 차례로 들어 있습니다.
    """

    def _pixels(self, fill):
        return [fill(x, y) for y in range(kocutin.H) for x in range(kocutin.W)]

    def test_크기는_576바이트(self):
        data = kocutin.to_tiles(self._pixels(lambda x, y: 1))
        self.assertEqual(len(data), kocutin.SIZE)
        self.assertEqual(kocutin.SIZE, 18 * 32)

    def test_왼쪽_위_화소는_타일_34의_첫_화소(self):
        px = self._pixels(lambda x, y: 6 if (x, y) == (0, 0) else 1)
        data = kocutin.to_tiles(px)
        o = (34 - 24) * 32
        self.assertEqual(data[o] & 15, 6)

    def test_오른쪽_끝_아래는_타일_25(self):
        px = self._pixels(lambda x, y: 5 if (x, y) == (71, 15) else 1)
        data = kocutin.to_tiles(px)
        o = (25 - 24) * 32 + 7 * 4 + 3
        self.assertEqual(data[o] >> 4, 5)

    def test_되돌리면_같은_그림(self):
        px = self._pixels(lambda x, y: 1 + (x * 7 + y * 3) % 6)
        self.assertEqual(kocutin.from_tiles(kocutin.to_tiles(px)), px)


@unittest.skipUnless(os.path.exists(ART), "art/tasukete_ko.png 없음")
class ArtTest(unittest.TestCase):
    def test_그림은_72x16_색은_1부터_6(self):
        px = kocutin.load_art(ART)
        self.assertEqual(len(px), kocutin.W * kocutin.H)
        self.assertTrue(set(px) <= set(range(1, 7)))
        self.assertGreater(sum(1 for v in px if v >= 5), 40)   # 글자가 있다


@unittest.skipUnless(os.path.exists(ROM), "rom/baserom.gba 없음")
class InstallTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(ROM, "rb") as f:
            cls.rom = f.read()

    def test_원본_두_자리는_같은_그림(self):
        a, b = (self.rom[o:o + kocutin.SIZE] for o in kocutin.SITES)
        self.assertEqual(a, b)
        self.assertEqual(hashlib.sha1(a).hexdigest(), kocutin.ORIG_SHA1)

    @unittest.skipUnless(os.path.exists(ART), "art/tasukete_ko.png 없음")
    def test_두_자리만_바꾼다(self):
        rom = bytearray(self.rom)
        kocutin.install(rom, ART)
        want = kocutin.to_tiles(kocutin.load_art(ART))
        for o in kocutin.SITES:
            self.assertEqual(bytes(rom[o:o + kocutin.SIZE]), want)
        changed = [i for i in range(len(rom)) if rom[i] != self.rom[i]]
        self.assertTrue(all(any(o <= i < o + kocutin.SIZE
                                for o in kocutin.SITES) for i in changed))

    @unittest.skipUnless(os.path.exists(ART), "art/tasukete_ko.png 없음")
    def test_원본이_아니면_멈춘다(self):
        rom = bytearray(self.rom)
        rom[kocutin.SITES[0]] ^= 0xFF
        with self.assertRaises(kocutin.CutinError):
            kocutin.install(rom, ART)


if __name__ == "__main__":
    unittest.main()
