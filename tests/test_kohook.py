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


class MenuSkipTest(unittest.TestCase):
    """메뉴 렌더러는 뒤 코드를 그리지도, 세지도 않습니다.

    음절이 가나처럼 한 칸이 되어 원래 칸 폭(레코드 width)에 들어가고,
    0x51F 를 넘는 뒤 코드(종성 ㅊㅋㅌㅍㅎ)가 사용자 글리프 경로로
    새지 않습니다.
    """

    def setUp(self):
        if MD is None:
            self.skipTest("capstone 없음")
        self.code = kohook.build_menu_skip(AT)
        self.dis = [f"{i.mnemonic} {i.op_str}".strip()
                    for i in MD.disasm(self.code, AT)]
        self.pool = {int.from_bytes(self.code[i:i + 4], "little")
                     for i in range(0, len(self.code) - 3, 4)}

    def test_뒤_코드_범위를_가린다(self):
        self.assertIn(kohook.trail_code(0), self.pool)
        self.assertIn(kohook.trail_code(kohook.TRAIL_COUNT - 1), self.pool)

    def test_앞_코드_뒤에_올_때만_뒤_코드로_본다(self):
        # 0x520–0x524 는 게임의 사용자 글리프(「Lv」 등)와 겹칩니다.
        # 바로 앞 코드의 뱅크 바이트([r8-4])가 3·4 일 때만 건너뜁니다.
        i = self.dis.index("mov r0, r8")
        self.assertEqual(self.dis[i + 1:i + 3],
                         ["subs r0, #4", "ldrb r0, [r0]"])
        self.assertIn(f"cmp r0, #{kohook.LEAD_BANKS[0]}", self.dis)
        self.assertIn(f"cmp r0, #{kohook.LEAD_BANKS[-1]}", self.dis)

    def test_뒤_코드는_루프의_다음_글자로_건너뛴다(self):
        self.assertIn(kohook.MENU_SKIP_RESUME | 1, self.pool)
        self.assertIn("bx r0", self.dis)

    def test_나머지는_원래_비교를_되살려_돌아간다(self):
        self.assertIn(kohook.MENU_CUSTOM_FROM, self.pool)
        i = self.dis.index("bx lr")
        self.assertEqual(self.dis[i - 1], "cmp r5, r0")

    def test_스택을_건드리지_않는다(self):
        self.assertFalse(any(d.startswith(("push", "pop")) for d in self.dis))

    def test_호출_지점은_ldr_cmp_네_바이트만_바꾼다(self):
        b = kohook.menu_skip_site_bytes(AT)
        self.assertEqual(len(b), 4)
        d = [f"{i.mnemonic} {i.op_str}" for i in
             MD.disasm(b, kohook.MENU_SKIP_SITE)]
        self.assertEqual(d[0], f"bl #{AT:#x}")

class NameDeleteTest(unittest.TestCase):
    """이름 입력 지우기(0x0804AAA0)는 2바이트 단위로 자릅니다.

    한글 음절(앞 코드 + 뒤 코드)은 4바이트라 뒤 코드만 지워지고 앞 코드가
    남았습니다. 끝 단위가 뒤 코드이고 그 앞 2바이트가 앞 코드면 4바이트를
    자릅니다.
    """

    def setUp(self):
        if MD is None:
            self.skipTest("capstone 없음")
        self.code = kohook.build_name_delete(AT)
        self.dis = [f"{i.mnemonic} {i.op_str}".strip()
                    for i in MD.disasm(self.code, AT)]
        self.pool = {int.from_bytes(self.code[i:i + 4], "little")
                     for i in range(0, len(self.code) - 3, 4)}

    def test_원래_두_명령으로_시작한다(self):
        # 0x0804AAD6 adds r0, r0, r5 / subs r0, #2 를 대신합니다.
        self.assertEqual(self.dis[:2], ["adds r0, r0, r5", "subs r0, #2"])

    def test_끝_단위가_뒤_코드일_때만(self):
        self.assertIn(kohook.trail_code(0), self.pool)
        self.assertIn(kohook.trail_code(kohook.TRAIL_COUNT - 1), self.pool)
        self.assertIn("cmp r4, r1", self.dis)

    def test_이름_맨_앞을_넘어_읽지_않는다(self):
        self.assertIn("subs r1, r0, r5", self.dis)
        self.assertIn("cmp r1, #2", self.dis)

    def test_앞_코드면_두_바이트_더_자른다(self):
        self.assertIn("subs r2, r0, #2", self.dis)
        self.assertIn("ldrb r1, [r2]", self.dis)
        self.assertIn(f"cmp r1, #{kohook.LEAD_BANKS[0]}", self.dis)
        self.assertIn(f"cmp r1, #{kohook.LEAD_BANKS[-1]}", self.dis)
        self.assertIn("adds r0, r2, #0", self.dis)

    def test_r0_r1_r2_만_쓰고_돌아간다(self):
        self.assertFalse(any(d.startswith(("push", "pop")) for d in self.dis))
        self.assertEqual(self.dis[-1] if self.dis[-1] == "bx lr" else
                         [d for d in self.dis if d.startswith("bx")][-1],
                         "bx lr")

    def test_호출_지점은_원래_두_명령_자리(self):
        b = kohook.name_delete_site_bytes(AT)
        self.assertEqual(len(b), 4)
        d = [f"{i.mnemonic} {i.op_str}" for i in
             MD.disasm(b, kohook.NAME_DELETE_SITE)]
        self.assertEqual(d[0], f"bl #{AT:#x}")
        self.assertEqual(kohook.NAME_DELETE_ORIG, bytes.fromhex("40190238"))


class NameWidthTest(unittest.TestCase):
    """이름 입력 커서 칸(0x0804A958)은 이름 폭과 같은 번호의 반각 칸입니다.

    폭(0x0801B874)은 한글 음절을 4로 세지만 화면에선 전각 한 칸(2)이라
    커서가 음절마다 한 칸씩 밀렸습니다. 커서 쪽 호출만 앞 코드 뒤의
    뒤 코드를 0 으로 세는 폭으로 바꿉니다. 입력 한도(0x0804AC3E)는 그대로.
    """

    def setUp(self):
        if MD is None:
            self.skipTest("capstone 없음")
        self.code = kohook.build_name_width(AT)
        self.dis = [f"{i.mnemonic} {i.op_str}".strip()
                    for i in MD.disasm(self.code, AT)]

    def test_원래_호출은_폭_함수(self):
        d = [f"{i.mnemonic} {i.op_str}" for i in
             MD.disasm(kohook.NAME_WIDTH_ORIG, kohook.NAME_WIDTH_SITE)]
        self.assertEqual(d[0], f"bl #{kohook.WIDTH_FUNC:#x}")

    def test_이스케이프는_두_바이트_전각은_2_반각은_1(self):
        self.assertIn("cmp r1, #4", self.dis)          # (코드-1) <= 4 -> 이스케이프
        self.assertIn("adds r0, #2", self.dis)
        self.assertIn("adds r0, #1", self.dis)

    def test_앞_코드_뒤의_뒤_코드는_0(self):
        self.assertIn("cmp r1, #5", self.dis)
        self.assertIn(f"cmp r3, #{kohook.LEAD_BANKS[0]}", self.dis)
        self.assertIn(f"cmp r3, #{kohook.LEAD_BANKS[-1]}", self.dis)

    def test_레지스터를_지키고_돌아간다(self):
        self.assertEqual(self.dis[0], "push {r4, lr}")
        self.assertEqual(self.dis[-1] if self.dis[-1].startswith("pop") else
                         [d for d in self.dis if d.startswith("pop")][-1],
                         "pop {r4, pc}")

    def test_호출_지점_바이트(self):
        b = kohook.name_width_site_bytes(AT)
        d = [f"{i.mnemonic} {i.op_str}" for i in
             MD.disasm(b, kohook.NAME_WIDTH_SITE)]
        self.assertEqual(d[0], f"bl #{AT:#x}")


if __name__ == "__main__":
    unittest.main()
