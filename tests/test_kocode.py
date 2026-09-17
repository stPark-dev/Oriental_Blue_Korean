#!/usr/bin/env python3
"""tools/kocode.py — 한글 코드 공간 모델과 할당 테스트."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tools"))
import kocode  # noqa: E402


class EncodeTest(unittest.TestCase):
    def test_직접_코드는_1바이트(self):
        self.assertEqual(kocode.encode_code(0x41), b"\x41")
        self.assertEqual(kocode.encode_code(0xFF), b"\xff")

    def test_뱅크_코드는_2바이트(self):
        self.assertEqual(kocode.encode_code(0x301), b"\x03\x01")
        self.assertEqual(kocode.encode_code(0x5FF), b"\x05\xff")

    def test_코드_범위를_벗어나면_거부(self):
        with self.assertRaises(ValueError):
            kocode.encode_code(0x600)


class UsableCodeTest(unittest.TestCase):
    """전개기가 오해하는 바이트를 피해야 합니다.

    0x00 은 종결자, 0x08 은 역참조 이스케이프입니다 (0x0800D4F8).
    """

    def test_파라미터_0x00_과_0x08_은_제외된다(self):
        codes = set(kocode.usable_codes())
        for bank in range(1, 6):
            self.assertNotIn((bank << 8) | 0x00, codes)
            self.assertNotIn((bank << 8) | 0x08, codes)
            self.assertIn((bank << 8) | 0x01, codes)
            self.assertIn((bank << 8) | 0xFF, codes)

    def test_직접_코드는_0x80_이상만_쓴다(self):
        # 0x7F 이하는 작은 폰트(8×8)로 그려져 한글에 못 씁니다
        direct = [c for c in kocode.usable_codes() if c < 0x100]
        self.assertEqual(min(direct), 0x80)
        self.assertEqual(max(direct), 0xFF)
        self.assertEqual(len(direct), 0x80)

    def test_뱅크별_개수(self):
        codes = kocode.usable_codes()
        for bank in range(1, 6):
            n = sum(1 for c in codes if c >> 8 == bank)
            self.assertEqual(n, 254, f"뱅크 {bank}")
        self.assertEqual(len(codes), 0x80 + 254 * 5)

    def test_뱅크를_제한할_수_있다(self):
        codes = kocode.usable_codes(banks=(3, 4, 5), include_direct=False)
        self.assertEqual(len(codes), 254 * 3)
        self.assertTrue(all(c >> 8 in (3, 4, 5) for c in codes))


class AllocateTest(unittest.TestCase):
    def test_음절은_코드_두_개를_받는다(self):
        m = kocode.allocate("한글", pool=[0x301, 0x302, 0x303, 0x304])
        self.assertEqual(m["한"], (0x301, 0x302))
        self.assertEqual(m["글"], (0x303, 0x304))

    def test_공간이_모자라면_알려준다(self):
        with self.assertRaises(kocode.OutOfCodes) as cm:
            kocode.allocate("한글", pool=[0x301, 0x302])
        self.assertIn("글", str(cm.exception))

    def test_예약된_코드는_비켜_간다(self):
        m = kocode.allocate("가", pool=[0x301, 0x302, 0x303, 0x304],
                            reserved={0x301})
        self.assertEqual(m["가"], (0x302, 0x303))

    def test_같은_음절은_한_번만_할당된다(self):
        m = kocode.allocate("가가가", pool=[0x301, 0x302, 0x303, 0x304])
        self.assertEqual(len(m), 1)
        self.assertEqual(m["가"], (0x301, 0x302))

    def test_한글이_아닌_문자는_할당하지_않는다(self):
        m = kocode.allocate("A가!", pool=[0x301, 0x302])
        self.assertEqual(set(m), {"가"})


class SyllableTest(unittest.TestCase):
    def test_한글_음절_판정(self):
        self.assertTrue(kocode.is_syllable("가"))
        self.assertTrue(kocode.is_syllable("힣"))
        self.assertFalse(kocode.is_syllable("ㄱ"))    # 낱자는 음절이 아님
        self.assertFalse(kocode.is_syllable("A"))
        self.assertFalse(kocode.is_syllable("あ"))


if __name__ == "__main__":
    unittest.main()
