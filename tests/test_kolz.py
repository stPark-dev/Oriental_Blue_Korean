#!/usr/bin/env python3
"""tools/kolz.py — 삽입 문자열 압축 테스트.

    python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tools"))
import kolz  # noqa: E402
import obtext  # noqa: E402


class RoundTripTest(unittest.TestCase):
    """무엇을 넣든 되풀면 원본이어야 합니다."""

    def check(self, data: bytes) -> bytes:
        packed = kolz.compress_checked(data)
        self.assertEqual(kolz.expand(packed), data)
        self.assertLessEqual(len(packed), len(data))
        return packed

    def test_짧으면_누르지_않는다(self):
        for d in (b"\x00", b"A\x00", b"ABC\x00"):
            self.assertEqual(self.check(d), d)

    def test_되풀이되면_줄어든다(self):
        data = b"ABCD" * 20 + b"\x00"
        self.assertLess(len(self.check(data)), len(data))

    def test_같은_바이트가_길게_이어져도_된다(self):
        self.check(b"\x41" * 500 + b"\x00")

    def test_종결자는_참조에_들어가지_않는다(self):
        # 종결자를 품은 구간을 가리키면 전개가 그 자리에서 끝나 버립니다.
        data = b"ABCDABCD" + b"\x00"
        packed = self.check(data)
        self.assertEqual(kolz.expand(packed), data)

    def test_이스케이프_바이트가_리터럴로_오면_원본을_그대로_둔다(self):
        # 0x08 은 스트림 제어 바이트라 리터럴로 쓸 수 없습니다. koenc 가
        # 막지만, 뚫고 들어와도 압축기가 원본을 그대로 돌려줘야 합니다.
        data = b"AB\x08CD\x00"
        self.assertEqual(kolz.compress_checked(data), data)

    def test_무작위_입력_왕복(self):
        rnd = random.Random(1234)
        alphabet = [b for b in range(1, 256) if b != obtext.ESCAPE]
        for _ in range(300):
            n = rnd.randint(1, 400)
            body = bytes(rnd.choice(alphabet) for _ in range(n))
            self.check(body + b"\x00")

    def test_치우친_입력은_실제로_줄어든다(self):
        rnd = random.Random(99)
        words = [b"\x01\x02\x03\x04", b"\x11\x12", b"\x21\x22\x23"]
        body = b"".join(rnd.choice(words) for _ in range(300))
        self.assertLess(len(self.check(body + b"\x00")), len(body) + 1)


class FormatTest(unittest.TestCase):
    def test_거리와_길이가_형식_범위를_넘지_않는다(self):
        data = (b"ABCDEFGH" * 400) + b"\x00"
        packed = kolz.compress_checked(data)
        i = 0
        while i < len(packed):
            if packed[i] == obtext.ESCAPE:
                b1, b2 = packed[i + 1], packed[i + 2]
                length = (b1 >> 4) + 4
                dist = ((b1 & 0x0F) << 8) | b2
                self.assertGreaterEqual(length, kolz.MIN_LEN)
                self.assertLessEqual(length, kolz.MAX_LEN)
                # 거리 0 은 전개기의 특수 동작이라 압축기가 내면 안 됩니다.
                self.assertGreater(dist, 0)
                self.assertLessEqual(dist, kolz.MAX_DIST)
                # 참조는 스트림 안쪽을 가리켜야 합니다.
                self.assertLessEqual(dist, i + 3)
                i += 3
            else:
                i += 1

    def test_참조가_가리키는_곳은_리터럴뿐이다(self):
        """중첩 참조는 만들지 않는다 — 검증이 어려워 쓰지 않기로 했습니다."""
        data = (b"\x31\x32\x33\x34\x35" * 200) + b"\x00"
        packed = kolz.compress_checked(data)
        # 이스케이프가 차지한 3바이트 자리를 표시해 둡니다.
        marks, i = set(), 0
        while i < len(packed):
            if packed[i] == obtext.ESCAPE:
                marks.update((i, i + 1, i + 2))
                i += 3
            else:
                i += 1
        i = 0
        while i < len(packed):
            if packed[i] == obtext.ESCAPE:
                b1, b2 = packed[i + 1], packed[i + 2]
                length = (b1 >> 4) + 4
                dist = ((b1 & 0x0F) << 8) | b2
                src = i + 3 - dist
                for k in range(src, src + length):
                    self.assertNotIn(k, marks,
                                     f"참조 0x{i:X} 가 이스케이프 자리를 가리킵니다")
                i += 3
            else:
                i += 1


if __name__ == "__main__":
    unittest.main()
