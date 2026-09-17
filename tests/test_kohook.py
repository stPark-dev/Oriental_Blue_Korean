#!/usr/bin/env python3
"""tools/kohook.py — 코드 배치와 훅 코드 생성 테스트."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tools"))
import kohook  # noqa: E402
import kosyl  # noqa: E402

try:
    from capstone import CS_ARCH_ARM, CS_MODE_THUMB, Cs
    MD = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
except ImportError:  # pragma: no cover
    MD = None

AT, SLOT, GLYPH = 0x081BDA44, 0x081C0000, 0x081C6000


class CodeLayoutTest(unittest.TestCase):
    def test_파라미터는_0x00_과_0x08_을_피한다(self):
        codes = ([kohook.lead_code(i) for i in range(kohook.LEAD_COUNT)]
                 + [kohook.trail_code(i) for i in range(kohook.TRAIL_COUNT)])
        for c in codes:
            self.assertNotIn(c & 0xFF, (0x00, 0x08), f"0x{c:03X}")
            self.assertGreaterEqual(c & 0xFF, kohook.PARAM_FIRST)

    def test_앞_코드는_뱅크_3과_4에_걸친다(self):
        self.assertEqual(kohook.lead_code(0), 0x309)
        self.assertEqual(kohook.lead_code(246), 0x3FF)
        self.assertEqual(kohook.lead_code(247), 0x409)
        self.assertEqual(kohook.lead_code(398), 0x4A0)

    def test_뒤_코드는_뱅크_5(self):
        self.assertEqual(kohook.trail_code(0), 0x509)
        self.assertEqual(kohook.trail_code(27), 0x524)

    def test_코드가_모두_다르다(self):
        codes = ([kohook.lead_code(i) for i in range(kohook.LEAD_COUNT)]
                 + [kohook.trail_code(i) for i in range(kohook.TRAIL_COUNT)])
        self.assertEqual(len(set(codes)), len(codes))
        self.assertEqual(len(codes), 399 + 28)

    def test_범위를_벗어나면_거부(self):
        for fn, n in ((kohook.lead_code, kohook.LEAD_COUNT),
                      (kohook.trail_code, kohook.TRAIL_COUNT)):
            with self.assertRaises(ValueError):
                fn(n)
            with self.assertRaises(ValueError):
                fn(-1)

    def test_훅의_계산과_음절이_맞아떨어진다(self):
        """모든 음절에 대해 코드 쌍 -> 음절 번호가 왕복해야 합니다."""
        for code in range(0xAC00, 0xD7A4):
            ch = chr(code)
            lead, trail = kosyl.to_pair(ch)
            idx = kohook.decode_pair(kohook.lead_code(lead),
                                     kohook.trail_code(trail))
            self.assertEqual(idx, code - 0xAC00, ch)

    def test_음절_수가_코드_쌍_수와_같다(self):
        self.assertEqual(kohook.SYLLABLES, 0xD7A4 - 0xAC00)


class BuildTest(unittest.TestCase):
    def setUp(self):
        if MD is None:
            self.skipTest("capstone 없음")
        self.code = kohook.build(AT, SLOT, GLYPH)
        self.dis = [f"{i.mnemonic} {i.op_str}".strip()
                    for i in MD.disasm(self.code, AT)]

    def test_짝수_길이이고_너무_크지_않다(self):
        self.assertEqual(len(self.code) % 4, 0)
        self.assertLess(len(self.code), 256)

    def test_레지스터를_지키고_돌아온다(self):
        self.assertEqual(self.dis[0], "push {r4, r5, r6, lr}")
        self.assertEqual(self.dis.count("pop {r4, r5, r6, pc}"), 3)

    def test_대응하지_않는_코드는_원래_함수로_넘긴다(self):
        self.assertIn(f"bl #{kohook.GET_WIDE:#x}", self.dis)

    def test_뒤_코드는_스트림을_되짚는다(self):
        self.assertIn("subs r2, r6, #4", self.dis)

    def test_앞_코드는_다음_바이트를_엿본다(self):
        self.assertIn("ldrb r3, [r6, #1]", self.dis)

    def test_테이블_주소가_리터럴_풀에_들어간다(self):
        pool = [int.from_bytes(self.code[i:i + 4], "little")
                for i in range(len(self.code) - 12, len(self.code), 4)]
        self.assertIn(SLOT, pool)
        self.assertIn(GLYPH, pool)

    def test_호출_지점을_바꿀_바이트를_만든다(self):
        import thumb
        b = thumb.bl_bytes(kohook.CALL_SITE, AT)
        d = [f"{i.mnemonic} {i.op_str}" for i in MD.disasm(b, kohook.CALL_SITE)]
        self.assertEqual(d[0], f"bl #{AT:#x}")



class HalfVariantTest(unittest.TestCase):
    """두 번째 렌더 루프는 작은 폰트를 부르고 dst 가 버퍼+8 입니다."""

    def setUp(self):
        if MD is None:
            self.skipTest("capstone 없음")
        self.code = kohook.build(AT, SLOT, GLYPH,
                                 fallback=kohook.GET_HALF, dst_back=8)
        self.dis = [f"{i.mnemonic} {i.op_str}".strip()
                    for i in MD.disasm(self.code, AT)]

    def test_한글이_아니면_작은_폰트_함수로_넘긴다(self):
        self.assertIn(f"bl #{kohook.GET_HALF:#x}", self.dis)
        self.assertNotIn(f"bl #{kohook.GET_WIDE:#x}", self.dis)

    def test_쓰기_전에_dst_를_되돌린다(self):
        self.assertEqual(self.dis.count("subs r0, #8"), 2)   # 복사·빈칸 양쪽

    def test_스트림_레지스터를_바꿀_수_있다(self):
        code = kohook.build(AT, SLOT, GLYPH, stream_reg=8)
        d = [f"{i.mnemonic} {i.op_str}".strip() for i in MD.disasm(code, AT)]
        self.assertEqual(d[1], "mov r6, r8")
        base = kohook.build(AT, SLOT, GLYPH)
        db = [f"{i.mnemonic} {i.op_str}".strip() for i in MD.disasm(base, AT)]
        self.assertNotIn("mov r6, r8", db)

    def test_기본_훅은_dst_를_건드리지_않는다(self):
        base = kohook.build(AT, SLOT, GLYPH)
        d = [f"{i.mnemonic} {i.op_str}".strip() for i in MD.disasm(base, AT)]
        self.assertNotIn("subs r0, #8", d)

if __name__ == "__main__":
    unittest.main()
