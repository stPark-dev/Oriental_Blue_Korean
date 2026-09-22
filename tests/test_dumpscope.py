#!/usr/bin/env python3
"""덤프 범위 — 작은 표를 빠뜨리지도, 쓰레기를 주워 오지도 않는지.

`make script` 는 오랫동안 항목 32개 이상인 표만 덤프했습니다. 그 아래 표에도
본편 대사가 들어 있어(여관 아가씨, 성문 병사 등) 번역 대상에서 통째로
빠져 있었습니다. 문턱을 낮추면 표가 아닌 것도 딸려 오므로 걸러냅니다.

가르는 기준은 **일본어 비율이 아닙니다.** 아이템 이름·끝말잇기 낱말처럼
가나 한두 글자짜리 표도 멀쩡한 번역 대상이기 때문입니다. 대신 모르는
제어 코드가 섞였는지와 항목당 바이트 간격을 봅니다.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tools"))
import common  # noqa: E402
import dumpscript  # noqa: E402
import mktbl  # noqa: E402
import obtext  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
ROM = os.path.join(ROOT, "rom", "baserom.gba")

# 실기에서 미번역으로 확인된 대사가 들어 있던 표들
MISSED = {0xF0E0F8: "おきてください", 0xF4C354: "でるのか", 0xF30214: "あさですよ"}
# 가나가 거의 없어도 번역해야 하는 표 (아이템·인명·메뉴·끝말잇기·스태프롤)
SHORT = (0xDF9080, 0xDF3908, 0xDFBEE4, 0xDF809C, 0xDF9088, 0xDF8494, 0xDE865C)
# 표처럼 보이지만 텍스트가 아닌 자리
JUNK = (0x74DDF0, 0x946A28, 0xC820D0, 0x716F2C, 0x0C1844, 0x8A2250, 0xC9FE4C)


class CleanTest(unittest.TestCase):
    def test_아는_글자와_제어_코드만이면_깨끗하다(self):
        self.assertTrue(dumpscript.is_clean("おきてください！"))
        self.assertTrue(dumpscript.is_clean("<$10>あ<$12>い"))
        self.assertTrue(dumpscript.is_clean("toruku"))

    def test_모르는_코드가_섞이면_아니다(self):
        self.assertFalse(dumpscript.is_clean("ペペペ<$100>"))
        self.assertFalse(dumpscript.is_clean("3<F3:00>"))
        self.assertFalse(dumpscript.is_clean("<$FF><$FF>"))


class ScopeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.exists(ROM):
            raise unittest.SkipTest("rom/baserom.gba 없음")
        cls.rom = bytes(common.load(ROM))
        cls.table = mktbl.build(cls.rom)

    def test_기본_최소_항목수는_32보다_작다(self):
        self.assertLessEqual(dumpscript.DEFAULT_MIN_COUNT, 8)

    def test_빠졌던_표가_텍스트로_판정된다(self):
        for base in MISSED:
            self.assertTrue(
                dumpscript.looks_like_text(self.rom, base, self.table),
                f"0x{base:X} 가 텍스트로 잡히지 않습니다")

    def test_낱말만_있는_표도_텍스트로_판정된다(self):
        for base in SHORT:
            self.assertTrue(
                dumpscript.looks_like_text(self.rom, base, self.table),
                f"0x{base:X} 가 텍스트로 잡히지 않습니다")

    def test_텍스트가_아닌_자리는_걸러낸다(self):
        for base in JUNK:
            self.assertFalse(
                dumpscript.looks_like_text(self.rom, base, self.table),
                f"0x{base:X} 가 텍스트로 잘못 잡혔습니다")

    def test_빠졌던_대사가_실제로_들어_있다(self):
        for base, needle in MISSED.items():
            _, entries = obtext.read_table(self.rom, base)
            texts = [dumpscript.decode(obtext.expand(self.rom, a), self.table)
                     for a in entries]
            self.assertTrue(any(needle in t for t in texts),
                            f"0x{base:X} 에 {needle!r} 가 없습니다")

    def test_이미_덤프한_표도_텍스트로_잡힌다(self):
        for base in (0xE2C6B0, 0xF4B3F4):
            self.assertTrue(dumpscript.looks_like_text(self.rom, base, self.table))


if __name__ == "__main__":
    unittest.main()
