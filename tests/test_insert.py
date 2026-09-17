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
import obtext  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
TTF = "/home/stpark/다운로드/hanguel2/galmuri/Galmuri14.ttf"

# 메뉴 설명문 "さいしょから　はじめます"
TABLE, INDEX = 0xDF3908, 506


class ReverseTableTest(unittest.TestCase):
    def test_같은_문자가_여러_코드면_짧은_쪽을_고른다(self):
        rev = inserttext.reverse_table({0x41: "A", 0x141: "A", 0xAB: "あ"})
        self.assertEqual(rev["A"], 0x41)
        self.assertEqual(rev["あ"], 0xAB)


class RomPatchTest(unittest.TestCase):
    ROM = os.path.join(ROOT, "rom", "baserom.gba")

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(cls.ROM):
            raise unittest.SkipTest("rom/baserom.gba 없음")
        if not os.path.exists(TTF):
            raise unittest.SkipTest("갈무리 폰트 없음")
        cls.rom = common.load(cls.ROM)

    def _ko_dir(self, tmp: str, text: str) -> str:
        ko = os.path.join(tmp, "ko")
        os.makedirs(ko)
        with open(os.path.join(ko, f"t{TABLE:06X}.txt"), "w",
                  encoding="utf-8", newline="\n") as f:
            f.write(f"# 테스트\n\n## {INDEX:04d} @0x000000\n{text}\n\n")
        return ko

    def test_번역문이_실제로_들어가고_원문이_그대로_읽힌다(self):
        with tempfile.TemporaryDirectory() as tmp:
            ko = self._ko_dir(tmp, "한글")
            out, stats = inserttext.build_patch(
                bytearray(self.rom), ko, [TABLE], TTF, 14, 2)

            self.assertEqual(stats["번역 항목"], 1)
            self.assertEqual(stats["음절"], 2)

            # 테이블 엔트리가 새 위치를 가리키고, 전개하면 코드 4개 + 종결자
            data = obtext.expand(out, inserttext.entry_addr(out, TABLE, INDEX))
            self.assertEqual(data[-1], 0x00)
            self.assertEqual(inserttext.decode_codes(data),
                             [c for ch in "한글" for c in stats["배정"][ch]])

            # 번역하지 않은 이웃 항목은 그대로여야 한다
            for idx in (INDEX - 1, INDEX + 1):
                before = obtext.expand(
                    self.rom, inserttext.entry_addr(self.rom, TABLE, idx))
                after = obtext.expand(
                    out, inserttext.entry_addr(out, TABLE, idx))
                self.assertEqual(before, after, f"#{idx}")

    def test_폰트가_재배치되고_글리프가_들어간다(self):
        with tempfile.TemporaryDirectory() as tmp:
            ko = self._ko_dir(tmp, "한글")
            out, stats = inserttext.build_patch(
                bytearray(self.rom), ko, [TABLE], TTF, 14, 2)

            base = kofont.entry_addr(out, kofont.LARGE_ENTRY)
            self.assertNotEqual(base, kofont.entry_addr(self.rom,
                                                        kofont.LARGE_ENTRY))
            # 새 배열은 뱅크 5 까지 담을 크기여야 한다
            size = common.u32(out, base - 4)
            self.assertEqual(size, kofont.LARGE_CODES * 16)

            # 배정된 코드 자리에 글리프가 실제로 있다
            for c in [x for ch in "한글" for x in stats["배정"][ch]]:
                off = base + c * 16
                self.assertTrue(any(out[off:off + 16]), f"코드 0x{c:03X} 가 빔")

            # 원문 글리프(あ = 0xAB)는 보존되어야 한다
            orig = kofont.entry_addr(self.rom, kofont.LARGE_ENTRY)
            self.assertEqual(out[base + 0xAB * 16:base + 0xAB * 16 + 16],
                             self.rom[orig + 0xAB * 16:orig + 0xAB * 16 + 16])

    def test_원문에_쓰이는_코드는_한글에_넘기지_않는다(self):
        with tempfile.TemporaryDirectory() as tmp:
            ko = self._ko_dir(tmp, "한글")
            out, stats = inserttext.build_patch(
                bytearray(self.rom), ko, [TABLE], TTF, 14, 2)
            codes = {x for ch in "한글" for x in stats["배정"][ch]}
            self.assertTrue(codes.isdisjoint(stats["예약 코드"]))

    def test_한글은_큰_폰트_코드만_받는다(self):
        with tempfile.TemporaryDirectory() as tmp:
            ko = self._ko_dir(tmp, "한글")
            _, stats = inserttext.build_patch(
                bytearray(self.rom), ko, [TABLE], TTF, 14, 2)
            for ch, pair in stats["배정"].items():
                for c in pair:
                    self.assertGreater(c, 0x7F, f"'{ch}' 코드 0x{c:03X}")

    def test_대응되지_않는_문자는_중단시킨다(self):
        with tempfile.TemporaryDirectory() as tmp:
            ko = self._ko_dir(tmp, "☃")
            with self.assertRaises(inserttext.InsertError):
                inserttext.build_patch(bytearray(self.rom), ko, [TABLE],
                                       TTF, 14, 2)


if __name__ == "__main__":
    unittest.main()
