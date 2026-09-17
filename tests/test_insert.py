#!/usr/bin/env python3
"""tools/inserttext.py — 번역문 삽입 테스트."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tools"))
import common  # noqa: E402
import inserttext  # noqa: E402
import kofont  # noqa: E402
import kohook  # noqa: E402
import kosyl  # noqa: E402
import obtext  # noqa: E402
import thumb  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
TTF = "/home/stpark/다운로드/hanguel2/galmuri/Galmuri14.ttf"

# 메뉴 설명문 "さいしょから　はじめます"
TABLE, INDEX = 0xDF3908, 506


class ReverseTableTest(unittest.TestCase):
    def test_같은_문자가_여러_코드면_짧은_쪽을_고른다(self):
        rev = inserttext.reverse_table({0x41: "A", 0x141: "A", 0xAB: "あ"})
        self.assertEqual(rev["A"], 0x41)
        self.assertEqual(rev["あ"], 0xAB)


class SyllableCodeTest(unittest.TestCase):
    def test_음절은_고정된_코드_쌍을_받는다(self):
        m = inserttext.syllable_codes("한글")
        self.assertEqual(set(m), {"한", "글"})
        for ch, (lead, trail) in m.items():
            l, t = kosyl.to_pair(ch)
            self.assertEqual(lead, kohook.lead_code(l))
            self.assertEqual(trail, kohook.trail_code(t))

    def test_배정이_아니라_계산이라_한도가_없다(self):
        m = inserttext.syllable_codes(
            "".join(chr(c) for c in range(0xAC00, 0xD7A4)))
        self.assertEqual(len(m), 11172)


class RomPatchTest(unittest.TestCase):
    ROM = os.path.join(ROOT, "rom", "baserom.gba")

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(cls.ROM):
            raise unittest.SkipTest("rom/baserom.gba 없음")
        if not os.path.exists(TTF):
            raise unittest.SkipTest("갈무리 폰트 없음")
        cls.rom = common.load(cls.ROM)

    def _build(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            ko = os.path.join(tmp, "ko")
            os.makedirs(ko)
            with open(os.path.join(ko, f"t{TABLE:06X}.txt"), "w",
                      encoding="utf-8", newline="\n") as f:
                f.write(f"# 테스트\n\n## {INDEX:04d} @0x000000\n{text}\n\n")
            return inserttext.build_patch(bytearray(self.rom), ko, [TABLE],
                                          TTF, 14, 2)

    def test_번역문이_코드_쌍으로_들어간다(self):
        out, stats = self._build("한글")
        self.assertEqual(stats["번역 항목"], 1)
        self.assertEqual(stats["음절"], 2)
        data = obtext.expand(out, inserttext.entry_addr(out, TABLE, INDEX))
        want = []
        for ch in "한글":
            lead, trail = kosyl.to_pair(ch)
            want += [kohook.lead_code(lead), kohook.trail_code(trail)]
        self.assertEqual(inserttext.decode_codes(data), want)

    def test_번역하지_않은_항목은_그대로다(self):
        out, _ = self._build("한글")
        for idx in (INDEX - 1, INDEX + 1):
            before = obtext.expand(
                self.rom, inserttext.entry_addr(self.rom, TABLE, idx))
            after = obtext.expand(
                out, inserttext.entry_addr(out, TABLE, idx))
            self.assertEqual(before, after, f"#{idx}")

    SITES = (kohook.CALL_SITE, kohook.CALL_SITE_HALF, kohook.CALL_SITE_MENU)

    def test_렌더러_세_곳이_훅을_가리킨다(self):
        out, stats = self._build("한글")
        self.assertEqual(len(stats["훅"]), 3)
        for site, at in zip(self.SITES, stats["훅"]):
            o = site - common.ROM_BASE
            self.assertEqual(bytes(out[o:o + 4]),
                             thumb.bl_bytes(site, at), hex(site))
            self.assertLess(abs(at - site), 1 << 22)

    def test_훅과_테이블이_제자리에_놓인다(self):
        out, stats = self._build("한글")
        for at, (fb, back, sreg, sm) in zip(stats["훅"],
                                            ((kohook.GET_WIDE, 0, 6, False),
                                             (kohook.GET_HALF, 8, 6, False),
                                             (kohook.GET_HALF, 0, 8, True))):
            hook = kohook.build(at, stats["색인"],
                                stats["글리프8"] if sm else stats["글리프"],
                                fallback=fb, dst_back=back, stream_reg=sreg,
                                small=sm)
            o = at - common.ROM_BASE
            self.assertEqual(bytes(out[o:o + len(hook)]), hook, hex(at))

        for ch in "한글":
            i = ord(ch) - kosyl.FIRST
            off = stats["색인"] - common.ROM_BASE + i * 2
            slot = int.from_bytes(out[off:off + 2], "little")
            self.assertNotEqual(slot, 0, ch)
            g = stats["글리프"] - common.ROM_BASE + slot * 32
            self.assertTrue(any(out[g:g + 32]), ch)

    def test_8행_렌더러용_8x8_글리프도_만든다(self):
        out, stats = self._build("한글")
        for ch in "한글":
            i = ord(ch) - kosyl.FIRST
            off = stats["색인"] - common.ROM_BASE + i * 2
            slot = int.from_bytes(out[off:off + 2], "little")
            g8 = stats["글리프8"] - common.ROM_BASE + slot * 8
            self.assertTrue(any(out[g8:g8 + 8]), ch)

    def test_폰트는_옮기지_않는다(self):
        """훅이 한글을 가로채므로 원본 폰트를 건드릴 이유가 없습니다."""
        out, _ = self._build("한글")
        for entry in (kofont.LARGE_ENTRY, kofont.SMALL_ENTRY):
            self.assertEqual(kofont.entry_addr(out, entry),
                             kofont.entry_addr(self.rom, entry))

    def test_음절_수에_한도가_없다(self):
        many = "".join(chr(c) for c in range(0xAC00, 0xAC00 + 2000))
        _, stats = self._build(many)
        self.assertEqual(stats["음절"], 2000)

    def test_대응되지_않는_문자는_중단시킨다(self):
        with self.assertRaises(inserttext.InsertError):
            self._build("☃")


if __name__ == "__main__":
    unittest.main()
