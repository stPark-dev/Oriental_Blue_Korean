#!/usr/bin/env python3
"""tools/koshiri.py — 끝말잇기 낱말표 분석 테스트."""
from __future__ import annotations

import contextlib
import io
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tools"))
import common  # noqa: E402
import inserttext  # noqa: E402
import koenc  # noqa: E402
import koshiri  # noqa: E402
import mktbl  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
ROM_PATH = os.path.join(ROOT, "rom", "baserom.gba")


class ArchiveTest(unittest.TestCase):
    """`0x08000324` 의 조회 공식."""

    def test_엔트리는_아카이브_4바이트_뒤를_기준으로_한다(self):
        arc = bytearray(32)
        struct.pack_into("<I", arc, 0, 2)        # count
        struct.pack_into("<I", arc, 4, 0x10)     # id 0
        struct.pack_into("<I", arc, 8, 0x20)     # id 1
        self.assertEqual(koshiri.arc_get(arc, 0, 0), 4 + 0x10)
        self.assertEqual(koshiri.arc_get(arc, 0, 1), 4 + 0x20)

    def test_색인이_count_를_넘으면_거부한다(self):
        arc = bytearray(32)
        struct.pack_into("<I", arc, 0, 1)
        with self.assertRaises(koshiri.ShiritoriError):
            koshiri.arc_get(arc, 0, 2)


class RecordTest(unittest.TestCase):
    def test_레코드는_세_항목_번호와_표식_두_개를_담는다(self):
        raw = struct.pack("<6h", 7, 22, 23, 24, 1, 0)
        r = koshiri.Record(7, raw)
        self.assertEqual((r.head_id, r.word_id, r.tail_id), (22, 23, 24))
        self.assertEqual((r.limit, r.losing), (1, 0))
        self.assertFalse(r.is_item)

    def test_191번부터가_아이템_낱말이다(self):
        raw = struct.pack("<6h", 191, 574, 575, 576, 0, 0)
        r = koshiri.Record(191, raw)
        self.assertTrue(r.is_item)
        self.assertEqual(r.item_id, 0)


class BufferTest(unittest.TestCase):
    """앞뒤 글자는 8바이트 스택 버퍼에 복사된 뒤 비교됩니다."""

    def test_한글_한_음절은_들어가고_두_음절은_넘친다(self):
        # 음절 하나 = 코드 두 개 = 4바이트, 종결자까지 5바이트.
        self.assertLessEqual(4 + 1, koshiri.HEAD_TAIL_BUFFER)
        self.assertGreater(8 + 1, koshiri.HEAD_TAIL_BUFFER)


class RomTest(unittest.TestCase):
    """실 ROM 회귀 — 주소는 전부 아카이브에서 계산합니다."""

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(ROM_PATH):
            raise unittest.SkipTest("rom/baserom.gba 없음")
        cls.rom = common.load(ROM_PATH)
        cls.addr = koshiri.addresses(cls.rom)

    def test_아카이브_사슬이_알려진_주소로_이어진다(self):
        self.assertEqual(self.addr["master"], 0xDAAA70)
        self.assertEqual(self.addr["records"], 0xDDB2FC)
        self.assertEqual(self.addr["words"], 0xDF9088)
        self.assertEqual(self.addr["item_records"], 0xDC88FC)
        self.assertEqual(self.addr["item_names"], 0xDE1AF8)

    def test_레코드_530개가_문자열표_1590항목을_빠짐없이_쓴다(self):
        recs = koshiri.records(self.rom)
        self.assertEqual(len(recs), 530)
        used = set()
        for r in recs:
            self.assertEqual((r.head_id, r.word_id, r.tail_id),
                             (3 * r.index + 1, 3 * r.index + 2, 3 * r.index + 3))
            used.update((r.head_id, r.word_id, r.tail_id))
        count = common.u32(self.rom, self.addr["words"])
        self.assertEqual(used, set(range(1, count)))

    def test_앞뒤_글자는_한_글자_두_바이트다(self):
        chars = mktbl.build(self.rom)
        for r in koshiri.records(self.rom):
            for index in (r.head_id, r.tail_id):
                s = koshiri.string(self.rom, self.addr["words"], index, chars)
                self.assertLessEqual(len(s), 1, f"항목 {index}: {s!r}")

    def test_막다른_글자는_ん_하나뿐이다(self):
        """일본식 규칙 — 「ん」으로 끝나면 이을 낱말이 없어 집니다."""
        chars = mktbl.build(self.rom)
        heads, tails = set(), set()
        for r in koshiri.records(self.rom):
            h = koshiri.string(self.rom, self.addr["words"], r.head_id, chars)
            t = koshiri.string(self.rom, self.addr["words"], r.tail_id, chars)
            if h:
                heads.add(h)
            if t:
                tails.add(t)
        self.assertEqual(sorted(tails - heads), ["ん"])

    def test_아이템_낱말은_아이템_이름과_같은_글자다(self):
        chars = mktbl.build(self.rom)
        same = 0
        total = 0
        for r in koshiri.records(self.rom):
            if not r.is_item:
                continue
            word = koshiri.string(self.rom, self.addr["words"], r.word_id, chars)
            if not word:
                continue                      # 빈 레코드 — 이름으로 대체됩니다
            total += 1
            sid = koshiri.item_name_id(self.rom, self.addr["item_records"],
                                       r.item_id)
            if word == koshiri.string(self.rom, self.addr["item_names"], sid,
                                      chars):
                same += 1
        self.assertEqual(total, 334)
        self.assertGreaterEqual(same, 330)    # 가나 표기만 다른 3건 제외

    def test_비교_루틴은_종결자까지_바이트_비교다(self):
        """`0x0801B8A8` 의 명령어를 그대로 확인합니다."""
        at = 0x01B8A8
        self.assertEqual(bytes(self.rom[at:at + 0x1C]), bytes.fromhex(
            "00b5" "05e0" "002a" "01d1" "0020" "06e0" "0130" "0131"
            "0278" "0b78" "9a42" "f5d0" "0120" "02bc"))


class KoreanTest(unittest.TestCase):
    """번역된 낱말표 — 사슬이 끊기지 않는지, 표식이 자료와 맞는지."""

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(ROM_PATH):
            raise unittest.SkipTest("rom/baserom.gba 없음")
        cls.rom = common.load(ROM_PATH)
        cls.chars = mktbl.build(cls.rom)
        cls.ko = koshiri.read_ko(os.path.join(ROOT, "script", "ko",
                                              "tDF9088.txt"))
        if not cls.ko:
            raise unittest.SkipTest("script/ko/tDF9088.txt 가 비어 있음")
        cls.rows, cls.dead = koshiri.chain(cls.rom, cls.ko, cls.chars)

    def test_한_벌은_세_항목을_모두_채우거나_모두_비운다(self):
        for r, head, word, tail in self.rows:
            filled = [bool(x) for x in (head, word, tail)]
            self.assertIn(set(filled), ({True}, {False}),
                          f"#{r.index}: {head!r} {word!r} {tail!r}")

    def test_앞뒤_글자는_한_음절이라_버퍼에_들어간다(self):
        ja_rev = inserttext.reverse_table(self.chars)
        ko_map = inserttext.syllable_codes("".join(self.ko.values()))
        for r, head, word, tail in self.rows:
            if not word:
                continue
            for s in (head, tail):
                self.assertEqual(len(s), 1, f"#{r.index}: {s!r}")
                size = len(koenc.encode(s, ko_map, ja_rev))
                self.assertLessEqual(size, koshiri.HEAD_TAIL_BUFFER,
                                     f"#{r.index}: {s!r} {size}바이트")

    def test_앞뒤_글자가_낱말의_첫_음절과_끝_음절이다(self):
        for r, head, word, tail in self.rows:
            syl = koshiri.syllables(word)
            if not syl:
                continue
            self.assertEqual(head, syl[0], f"#{r.index}: {word!r}")
            self.assertEqual(tail, syl[-1], f"#{r.index}: {word!r}")

    def test_일반_낱말은_막다른_글자로_끝나지_않는다(self):
        """상대가 내는 낱말이라 이을 수 없으면 플레이어가 부당하게 집니다."""
        for r, _head, word, tail in self.rows:
            if r.is_item or not word:
                continue
            self.assertNotIn(tail, self.dead, f"#{r.index}: {word!r}")

    def test_patch_는_표식을_막다른_글자에_맞춘다(self):
        rom = bytearray(self.rom)
        base = koshiri.addresses(rom)["records"]

        class Args:
            ko = os.path.join(ROOT, "script", "ko")
            out = os.devnull
            rom = None
        with contextlib.redirect_stdout(io.StringIO()):
            koshiri.cmd_patch(rom, Args())
        for r, _head, word, tail in self.rows:
            want = 1 if (r.is_item and word and tail in self.dead) else 0
            got = common.u16(rom, base + koshiri.RECORD_SIZE * r.index + 10)
            self.assertEqual(got, want, f"#{r.index}: {word!r}")

    def test_모든_항목이_게임_바이트열로_인코딩된다(self):
        ja_rev = inserttext.reverse_table(self.chars)
        ko_map = inserttext.syllable_codes("".join(self.ko.values()))
        for index, text in self.ko.items():
            koenc.encode(text, ko_map, ja_rev)   # 예외가 나면 실패
            self.assertTrue(text.strip(), index)


if __name__ == "__main__":
    unittest.main()
