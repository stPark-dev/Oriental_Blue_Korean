#!/usr/bin/env python3
"""tools/patch.py — 원본과 크기가 다른 패치 왕복 검사.

ROM 확장(`tools/inserttext.py --expand`)을 넣으면서 **처음으로 원본과 결과의
크기가 달라졌습니다.** 그 경로를 고정해 둡니다.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tools"))
import patch  # noqa: E402

SRC = bytes(range(256)) * 64          # 16,384바이트


class BpsRoundTripTest(unittest.TestCase):
    def _round(self, target: bytes) -> bytes:
        return patch.bps_apply(SRC, patch.bps_make(SRC, target))

    def test_크기가_같으면_그대로_돌아온다(self):
        tgt = bytearray(SRC)
        tgt[100:110] = b"\xAA" * 10
        self.assertEqual(self._round(bytes(tgt)), bytes(tgt))

    def test_뒤가_늘어나도_돌아온다(self):
        tgt = bytes(SRC) + b"\xFF" * 4096
        self.assertEqual(self._round(tgt), tgt)

    def test_뒤가_줄어도_돌아온다(self):
        tgt = bytes(SRC[:8192])
        self.assertEqual(self._round(tgt), tgt)

    def test_늘어난_자리에_내용이_있어도_돌아온다(self):
        tgt = bytes(SRC) + bytes(range(256)) * 4
        self.assertEqual(self._round(tgt), tgt)

    def test_원본이_다르면_거부한다(self):
        p = patch.bps_make(SRC, SRC + b"\x00")
        with self.assertRaises(ValueError):
            patch.bps_apply(SRC[:-1], p)

    def test_손상된_패치를_거부한다(self):
        p = bytearray(patch.bps_make(SRC, SRC + b"\x00"))
        p[20] ^= 0xFF
        with self.assertRaises(ValueError):
            patch.bps_apply(SRC, bytes(p))


class IpsLimitTest(unittest.TestCase):
    def test_16MB를_넘으면_BPS를_쓰라고_알린다(self):
        with self.assertRaises(ValueError):
            patch.ips_make(b"", b"\x00" * (patch.IPS_MAX + 1))


if __name__ == "__main__":
    unittest.main()
