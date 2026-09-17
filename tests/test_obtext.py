#!/usr/bin/env python3
"""tools/obtext.py — 전개기와 테이블 분류 테스트.

    python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tools"))
import obtext  # noqa: E402


def esc(length: int, dist: int) -> bytes:
    """이스케이프 3바이트. length 는 4..19, dist 는 0..0x0FFF."""
    b1 = ((length - 4) << 4) | ((dist >> 8) & 0x0F)
    return bytes([obtext.ESCAPE, b1, dist & 0xFF])


class ExpandTest(unittest.TestCase):
    def test_평문은_그대로_나오고_종결자에서_멈춘다(self):
        rom = b"ABC\x00DEF"
        self.assertEqual(obtext.expand(rom, 0), b"ABC\x00")

    def test_예산을_다_쓰면_종결자_없이도_멈춘다(self):
        rom = b"ABCDEFGH"
        self.assertEqual(obtext.expand(rom, 0, budget=3), b"ABC")

    def test_역참조는_이스케이프_다음_위치를_기준으로_거슬러_올라간다(self):
        # 'ABCDEFGH' 출력 뒤, 5바이트를 11 뒤(= 오프셋 0)에서 다시 전개
        rom = b"ABCDEFGH" + esc(5, 11) + b"\x00"
        self.assertEqual(obtext.expand(rom, 0), b"ABCDEFGH" + b"ABCDE" + b"\x00")

    def test_역참조_대상이_이스케이프면_재귀_전개된다(self):
        rom = b"XYZ" + esc(4, 6) + b"\x00"
        # 안쪽 전개: X Y Z 다음이 다시 이스케이프 -> 남은 1바이트만 X
        # 바깥 전개: 이스케이프 다음 바이트(0x00)로 종료
        self.assertEqual(obtext.expand(rom, 0), b"XYZ" + b"XYZX" + b"\x00")

    def test_거리0은_오류가_아니라_다음_출력을_한_번_더_낸다(self):
        # 0x0800D4F8: src = r4 - 0 = r4 — 이스케이프 직후부터 다시 전개한다
        rom = esc(4, 0) + b"ABCDE\x00"
        self.assertEqual(obtext.expand(rom, 0), b"ABCD" + b"ABCDE\x00")

    def test_범위를_벗어나면_예외(self):
        with self.assertRaises(obtext.ExpandError):
            obtext.expand(b"AB" + esc(4, 0x0FFF), 0)


class BlobTableTest(unittest.TestCase):
    """크기 접두 바이너리 블롭 테이블 판별.

    규칙: 엔트리 선두 u32 + 4 == 다음 엔트리까지의 간격.
    ROM의 테이블 133개 중 16개가 이 규칙에 100% 맞고, 나머지는 2% 미만이다.
    """

    @staticmethod
    def build(payloads: list[bytes], size_prefixed: bool = False) -> bytes:
        """테이블 하나짜리 가짜 ROM.

        슬롯 0 은 엔트리 개수, 슬롯 1..n 은 테이블 기준 상대 오프셋입니다.
        size_prefixed 면 각 엔트리 앞에 자기 길이를 u32 로 붙입니다.
        """
        count = len(payloads) + 1
        header = count * 4
        offs, body = [], b""
        for p in payloads:
            offs.append(header + len(body))
            body += (len(p).to_bytes(4, "little") + p) if size_prefixed else p
        out = count.to_bytes(4, "little")
        for o in offs:
            out += o.to_bytes(4, "little")
        return out + body

    def test_텍스트_테이블은_블롭이_아니다(self):
        rom = self.build([b"\xab\xac\xad\x00", b"\xb0\xb1\x00", b"\xc3\x00"] * 4)
        self.assertFalse(obtext.is_blob_table(rom, 0))

    def test_크기_접두_블롭_테이블을_찾아낸다(self):
        payloads = [b"\xde" * 12, b"\xad" * 20, b"\xbe" * 8] * 4
        rom = self.build(payloads, size_prefixed=True)
        self.assertTrue(obtext.is_blob_table(rom, 0))

    def test_엔트리가_너무_적으면_판정하지_않는다(self):
        rom = self.build([b"\xde" * 12, b"\xad" * 20], size_prefixed=True)
        self.assertFalse(obtext.is_blob_table(rom, 0))


class RomRegressionTest(unittest.TestCase):
    """실제 ROM이 있을 때만 도는 회귀 테스트."""

    ROM = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "rom", "baserom.gba")

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(cls.ROM):
            raise unittest.SkipTest("rom/baserom.gba 없음")
        with open(cls.ROM, "rb") as f:
            cls.rom = f.read()

    def test_거리0_엔트리_162건이_모두_전개된다(self):
        # 0x0800D4F8 의 거리 0 동작을 반영하기 전에는 실패하던 항목들
        for base, idx in ((0x220020, 272), (0x26CAC8, 7), (0x26CAC8, 9)):
            off = base + int.from_bytes(
                self.rom[base + idx * 4:base + idx * 4 + 4], "little")
            self.assertTrue(obtext.expand(self.rom, off))

    def test_알려진_블롭_테이블과_텍스트_테이블을_구분한다(self):
        for base in (0x220020, 0x26CAC8, 0xCAE740, 0xDAAB68, 0xF2E98C):
            self.assertTrue(obtext.is_blob_table(self.rom, base),
                            f"0x{base:06X} 는 블롭이어야 한다")
        for base in (0xDDE1E4, 0xDE865C, 0xDE1AF8, 0xDF9088, 0xDFBEE4):
            self.assertFalse(obtext.is_blob_table(self.rom, base),
                             f"0x{base:06X} 는 텍스트여야 한다")


if __name__ == "__main__":
    unittest.main()
