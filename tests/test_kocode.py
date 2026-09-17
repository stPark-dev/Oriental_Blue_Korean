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


class SyllableTest(unittest.TestCase):
    def test_한글_음절_판정(self):
        self.assertTrue(kocode.is_syllable("가"))
        self.assertTrue(kocode.is_syllable("힣"))
        self.assertFalse(kocode.is_syllable("ㄱ"))    # 낱자는 음절이 아님
        self.assertFalse(kocode.is_syllable("A"))
        self.assertFalse(kocode.is_syllable("あ"))


if __name__ == "__main__":
    unittest.main()
