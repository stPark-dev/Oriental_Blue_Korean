#!/usr/bin/env python3
"""tools/koenc.py — 번역문을 게임 바이트열로 인코딩하는 테스트."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tools"))
import koenc  # noqa: E402

KO = {"한": (0x301, 0x302), "글": (0x303, 0x304)}
JA = {"A": 0x41, " ": 0x20, "、": 0x121, "！": 0x129}


def enc(text):
    return koenc.encode(text, KO, JA)


class TokenTest(unittest.TestCase):
    def test_원시_바이트_태그를_읽는다(self):
        self.assertEqual(koenc.tokens("<$10>가<$1F>"),
                         [("raw", 0x10), ("char", "가"), ("raw", 0x1F)])

    def test_세_자리_코드_태그도_읽는다(self):
        self.assertEqual(koenc.tokens("<$142>"), [("code", 0x142)])

    def test_줄바꿈은_따로_구분한다(self):
        self.assertEqual(koenc.tokens("가\n나"),
                         [("char", "가"), ("newline", None), ("char", "나")])

    def test_닫히지_않은_태그는_오류(self):
        with self.assertRaises(koenc.EncodeError):
            koenc.tokens("<$10")


class EncodeTest(unittest.TestCase):
    def test_음절은_코드_두_개로_나간다(self):
        self.assertEqual(enc("한"), bytes([0x03, 0x01, 0x03, 0x02, 0x00]))

    def test_여러_음절(self):
        self.assertEqual(enc("한글"),
                         bytes([0x03, 0x01, 0x03, 0x02,
                                0x03, 0x03, 0x03, 0x04, 0x00]))

    def test_원문_문자는_기존_코드를_쓴다(self):
        self.assertEqual(enc("A"), bytes([0x41, 0x00]))
        self.assertEqual(enc("、"), bytes([0x01, 0x21, 0x00]))

    def test_줄바꿈과_공백(self):
        self.assertEqual(enc("A A"), bytes([0x41, 0x20, 0x41, 0x00]))
        self.assertEqual(enc("A\nA"), bytes([0x41, 0x0A, 0x41, 0x00]))

    def test_원시_바이트_태그는_그대로_나간다(self):
        self.assertEqual(enc("<$10>한"),
                         bytes([0x10, 0x03, 0x01, 0x03, 0x02, 0x00]))

    def test_종결자는_한_번만_붙는다(self):
        self.assertEqual(enc("A").count(0x00), 1)

    def test_대응되지_않는_문자는_오류로_알려준다(self):
        with self.assertRaises(koenc.EncodeError) as cm:
            enc("あ")
        self.assertIn("あ", str(cm.exception))

    def test_빈_문자열은_종결자만(self):
        self.assertEqual(enc(""), b"\x00")


class SafetyTest(unittest.TestCase):
    """전개기가 오해하는 바이트가 나오면 안 됩니다."""

    def test_파라미터에_0x00_이_나오면_거부(self):
        with self.assertRaises(koenc.EncodeError):
            koenc.encode("가", {"가": (0x300, 0x301)}, JA)

    def test_파라미터에_0x08_이_나오면_거부(self):
        with self.assertRaises(koenc.EncodeError):
            koenc.encode("가", {"가": (0x308, 0x301)}, JA)

    def test_원시_바이트로_0x08_을_넣어도_거부(self):
        with self.assertRaises(koenc.EncodeError):
            enc("<$08>")


class UsedCharsTest(unittest.TestCase):
    def test_태그와_줄바꿈은_문자에서_빠진다(self):
        self.assertEqual(koenc.used_chars("<$10>한글\nA"),
                         {"한", "글", "A"})


if __name__ == "__main__":
    unittest.main()
