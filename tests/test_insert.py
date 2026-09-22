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
TTF = os.path.join(ROOT, "font", "Galmuri14.ttf")

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


class ReadSetTest(unittest.TestCase):
    """전개하며 실제로 읽은 바이트를 모읍니다 (역참조 포함)."""

    def test_압축되지_않은_문자열은_자기_바이트만_읽는다(self):
        rom = bytes([0x41, 0x42, 0x00])
        self.assertEqual(inserttext.read_set(rom, 0), {0, 1, 2})

    def test_뒤로_참조하면_앞쪽_바이트도_읽는다(self):
        # 0x41 0x42 0x43 0x44 뒤에 (길이 4, 거리 7) 이스케이프
        rom = bytes([0x41, 0x42, 0x43, 0x44, 0x08, 0x00, 0x07, 0x00])
        got = inserttext.read_set(rom, 0)
        self.assertEqual(got, {0, 1, 2, 3, 4, 5, 6, 7})

    def test_종결자에서_멈춘다(self):
        rom = bytes([0x41, 0x00, 0x42, 0x43])
        self.assertEqual(inserttext.read_set(rom, 0), {0, 1})


class SpansTest(unittest.TestCase):
    def test_이어진_주소는_한_구간으로_묶는다(self):
        self.assertEqual(inserttext.spans([1, 2, 3, 7, 8], 1),
                         [(1, 4), (7, 9)])

    def test_짧은_구간은_버린다(self):
        self.assertEqual(inserttext.spans([1, 2, 3, 7, 8], 3), [(1, 4)])

    def test_빈_입력(self):
        self.assertEqual(inserttext.spans([], 1), [])


class DeadRegionTest(unittest.TestCase):
    """번역한 항목의 원문 자리는 비우고, 남은 항목이 읽는 곳은 지킵니다."""

    ROM = os.path.join(ROOT, "rom", "baserom.gba")

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(cls.ROM):
            raise unittest.SkipTest("rom/baserom.gba 없음")
        cls.rom = common.load(cls.ROM)

    def test_번역하지_않은_항목이_읽는_바이트는_비우지_않는다(self):
        base = TABLE
        count, entries = obtext.read_table(self.rom, base)
        rows = {1: "가"}                     # 1번만 번역했다고 치고
        dead = inserttext.dead_regions(self.rom, {base: rows})
        live = set()
        for i, addr in enumerate(entries, 1):
            if i in rows:
                continue
            try:
                live |= inserttext.read_set(self.rom, addr)
            except obtext.ExpandError:
                pass
        for a, b in dead:
            self.assertFalse(live & set(range(a, b)),
                             f"0x{a:X}-0x{b:X} 는 남은 항목이 읽는 자리")

    def test_번역한_항목의_자리가_비워진다(self):
        base = TABLE
        _, entries = obtext.read_table(self.rom, base)
        rows = {i: "가" for i in range(1, len(entries) + 1)}
        dead = inserttext.dead_regions(self.rom, {base: rows})
        self.assertTrue(sum(b - a for a, b in dead) > 1000)


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


class ExpandRomTest(unittest.TestCase):
    """GBA 카트리지 주소 공간(32MB) 안에서 ROM 뒤를 0xFF 로 늘립니다."""

    def test_모자란_만큼_0xFF_로_늘린다(self):
        out = inserttext.expand_rom(bytearray(b"\x00" * 8), 16)
        self.assertEqual(len(out), 16)
        self.assertEqual(bytes(out[8:]), b"\xff" * 8)

    def test_이미_크면_그대로_둔다(self):
        out = inserttext.expand_rom(bytearray(b"\x00" * 32), 16)
        self.assertEqual(len(out), 32)

    def test_주소_공간을_넘으면_오류(self):
        with self.assertRaises(inserttext.InsertError):
            inserttext.expand_rom(bytearray(4), inserttext.GBA_MAX + 1)

    def test_늘린_자리를_자유_공간으로_찾아낸다(self):
        rom = inserttext.expand_rom(bytearray(b"\x00" * 0x100), 0x4000)
        regions = inserttext.auto_regions(rom, min_size=0x100)
        self.assertEqual(regions, [(0x104, 0x3FFC)])


class TrimRomTest(unittest.TestCase):
    """늘려 놓고 쓰지 않은 뒤쪽은 잘라냅니다 (패치가 커지지 않도록)."""

    def test_쓴_곳까지만_남기고_경계로_올림한다(self):
        rom = bytearray(b"\xff" * 0x40000)
        self.assertEqual(len(inserttext.trim_rom(rom, 0x10001, 0x10000)),
                         0x20000)

    def test_경계에_딱_맞으면_그대로다(self):
        rom = bytearray(b"\xff" * 0x40000)
        self.assertEqual(len(inserttext.trim_rom(rom, 0x20000, 0x10000)),
                         0x20000)

    def test_이미_작으면_늘리지_않는다(self):
        rom = bytearray(b"\xff" * 0x8000)
        self.assertEqual(len(inserttext.trim_rom(rom, 0x20000, 0x10000)),
                         0x8000)

    def test_기준이_0이면_오류(self):
        """ROM 을 통째로 지우는 사고를 막습니다."""
        with self.assertRaises(inserttext.InsertError):
            inserttext.trim_rom(bytearray(0x1000), 0)


class ArenaTest(unittest.TestCase):
    def test_확장_구간은_원본_빈_공간을_다_쓴_뒤에_쓴다(self):
        a = inserttext.Arena(bytearray(0x200), [(0x00, 0x20)],
                             spill=[(0x100, 0x200)])
        self.assertEqual(a.alloc(0x20), 0x00)
        self.assertEqual(a.alloc(0x10), 0x100)

    def test_가장_뒤까지_쓴_끝을_기록한다(self):
        a = inserttext.Arena(bytearray(0x200), [(0x00, 0x20)],
                             spill=[(0x100, 0x200)])
        a.alloc(0x20)
        a.alloc(0x10)
        self.assertEqual(a.top, 0x110)

    def test_아무것도_안_쓰면_끝이_0이다(self):
        a = inserttext.Arena(bytearray(0x200), [(0x00, 0x20)])
        self.assertEqual(a.top, 0)

    def test_남은_자유_공간은_원본분만_센다(self):
        """확장분까지 더하면 원본이 언제 바닥났는지 안 보입니다."""
        a = inserttext.Arena(bytearray(0x200), [(0x00, 0x20)],
                             spill=[(0x100, 0x200)])
        self.assertEqual(a.remaining, 0x20)
        a.alloc(0x20)
        self.assertEqual(a.remaining, 0)
        self.assertEqual(a.spilled, 0)
        a.alloc(0x10)
        self.assertEqual(a.spilled, 0x10)


if __name__ == "__main__":
    unittest.main()
