#!/usr/bin/env python3
"""tools/thumb.py — capstone 으로 역어셈블해 왕복 검증합니다."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tools"))
import thumb  # noqa: E402

try:
    from capstone import CS_ARCH_ARM, CS_MODE_THUMB, Cs
    MD = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
except ImportError:  # pragma: no cover
    MD = None

BASE = 0x08200000


def dis(code: bytes, base: int = BASE) -> list[str]:
    return [f"{i.mnemonic} {i.op_str}".strip() for i in MD.disasm(code, base)]


class EncodingTest(unittest.TestCase):
    """각 명령이 의도한 대로 인코딩되는지 역어셈블로 확인합니다."""

    def setUp(self):
        if MD is None:
            self.skipTest("capstone 없음")

    def asm(self, fn):
        a = thumb.Asm(BASE)
        fn(a)
        return dis(a.assemble())

    def test_스택_명령(self):
        self.assertEqual(
            self.asm(lambda a: (a.push([4, 5, 6, 7], lr=True),
                                a.pop([4, 5, 6, 7], pc=True))),
            ["push {r4, r5, r6, r7, lr}", "pop {r4, r5, r6, r7, pc}"])

    def test_이동과_시프트(self):
        self.assertEqual(
            self.asm(lambda a: (a.movs(0, 0x1F), a.lsrs(2, 1, 8),
                                a.lsls(3, 2, 5), a.mov_hi(8, 0))),
            ["movs r0, #0x1f", "lsrs r2, r1, #8", "lsls r3, r2, #5",
             "mov r8, r0"])

    def test_비교와_산술(self):
        self.assertEqual(
            self.asm(lambda a: (a.cmp_imm(2, 5), a.cmp_reg(1, 2),
                                a.adds_imm3(0, 1, 3), a.subs_imm3(0, 1, 2),
                                a.adds_imm8(4, 0x20), a.subs_imm8(4, 9),
                                a.adds(0, 1, 2), a.subs(0, 1, 2),
                                a.muls(3, 2))),
            ["cmp r2, #5", "cmp r1, r2", "adds r0, r1, #3", "subs r0, r1, #2",
             "adds r4, #0x20", "subs r4, #9", "adds r0, r1, r2",
             "subs r0, r1, r2", "muls r3, r2, r3"])

    def test_적재와_저장(self):
        self.assertEqual(
            self.asm(lambda a: (a.ldrb_imm(3, 6, 1), a.strb_imm(3, 0, 15),
                                a.ldrh_reg(2, 1, 0), a.ldrb_reg(2, 1, 0),
                                a.ldr_imm(1, 2, 8), a.str_imm(1, 2, 4))),
            ["ldrb r3, [r6, #1]", "strb r3, [r0, #0xf]", "ldrh r2, [r1, r0]",
             "ldrb r2, [r1, r0]", "ldr r1, [r2, #8]", "str r1, [r2, #4]"])

    def test_분기(self):
        out = self.asm(lambda a: (a.b("end"), a.beq("end"), a.movs(0, 0),
                                  a.mark("end"), a.bx(14)))
        self.assertEqual(out[0], "b #0x8200006")
        self.assertEqual(out[1], "beq #0x8200006")
        self.assertEqual(out[3], "bx lr")

    def test_뒤로_가는_분기(self):
        out = self.asm(lambda a: (a.mark("top"), a.movs(0, 0), a.bne("top")))
        self.assertEqual(out[1], "bne #0x8200000")

    def test_bl_은_주소를_맞춘다(self):
        a = thumb.Asm(BASE)
        a.bl(0x0801C2EC)
        self.assertEqual(dis(a.assemble())[0], "bl #0x801c2ec")

    def test_리터럴_풀(self):
        a = thumb.Asm(BASE)
        a.ldr_pool(0, 0x02001A58)
        a.ldr_pool(1, 0xDEADBEEF)
        a.bx(14)
        code = a.assemble()
        out = dis(code)
        self.assertTrue(out[0].startswith("ldr r0, [pc,"))
        self.assertTrue(out[1].startswith("ldr r1, [pc,"))
        # 풀이 코드 뒤에 워드 정렬로 붙는다
        self.assertEqual(len(code), 4 * 2 + 8)
        self.assertEqual(int.from_bytes(code[8:12], "little"), 0x02001A58)
        self.assertEqual(int.from_bytes(code[12:16], "little"), 0xDEADBEEF)

    def test_같은_상수는_풀을_공유한다(self):
        a = thumb.Asm(BASE)
        a.ldr_pool(0, 0x1234)
        a.ldr_pool(1, 0x1234)
        self.assertEqual(len(a.pool), 1)


class ErrorTest(unittest.TestCase):
    def test_없는_라벨은_오류(self):
        a = thumb.Asm(BASE)
        a.b("nowhere")
        with self.assertRaises(thumb.AsmError):
            a.assemble()

    def test_라벨_중복은_오류(self):
        a = thumb.Asm(BASE)
        a.mark("x")
        with self.assertRaises(thumb.AsmError):
            a.mark("x")

    def test_범위를_넘는_즉시값은_오류(self):
        a = thumb.Asm(BASE)
        with self.assertRaises(thumb.AsmError):
            a.movs(0, 0x100)

    def test_bl_사거리_초과는_오류(self):
        a = thumb.Asm(BASE)
        with self.assertRaises(thumb.AsmError):
            a.bl(BASE + (1 << 23))


class BlBytesTest(unittest.TestCase):
    def setUp(self):
        if MD is None:
            self.skipTest("capstone 없음")

    def test_호출_지점_교체용_바이트(self):
        site, target = 0x0801C904, 0x081BDA44
        b = thumb.bl_bytes(site, target)
        self.assertEqual(dis(b, site)[0], f"bl #{target:#x}")

    def test_원본과_같은_bl_을_재현한다(self):
        # ROM 0x0801C904 의 원래 명령은 bl 0x0801C2EC 입니다
        self.assertEqual(thumb.bl_bytes(0x0801C904, 0x0801C2EC),
                         bytes.fromhex("FFF7F2FC"))


if __name__ == "__main__":
    unittest.main()
