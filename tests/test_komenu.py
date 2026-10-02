#!/usr/bin/env python3
"""tools/komenu.py — 메뉴 항목 칸 폭 검사."""
from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import komenu  # noqa: E402


class CountTest(unittest.TestCase):
    """메뉴 렌더러는 뒤 코드를 세지 않으므로 음절도 한 칸입니다."""

    def test_음절은_한_칸(self):
        self.assertEqual(komenu.count("소지품"), 3)

    def test_가나와_기호도_한_칸(self):
        self.assertEqual(komenu.count("もちもの"), 4)
        self.assertEqual(komenu.count("Ｂ버튼　취소"), 6)

    def test_제어_코드와_서식은_세지_않는다(self):
        self.assertEqual(komenu.count("<$1F>s의　일기"), 4)

    def test_여러_줄이면_가장_긴_줄(self):
        self.assertEqual(komenu.widest("누구에게\n\n씁니까？"), 4)


class SavePlaceTest(unittest.TestCase):
    """기록 화면의 장소 이름은 바이트 수로 잘립니다 (inserttext.SAVE_PLACE_LIMIT)."""

    def test_장소_이름은_여관표의_세_번째마다(self):
        self.assertEqual(komenu.save_places({1: "여관", 2: "요금", 3: "대도"}),
                         {3: "대도"})

    def test_한도를_넘는_이름을_찾는다(self):
        enc = lambda s: s.encode("utf-8")        # noqa: E731
        self.assertEqual(komenu.long_places({3: "가" * 9, 6: "가"}, enc, 25),
                         [(3, 27, "가" * 9)])


class FieldTest(unittest.TestCase):
    ROM = os.path.join(ROOT, "rom", "baserom.gba")

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(cls.ROM):
            raise unittest.SkipTest("rom/baserom.gba 없음")
        with open(cls.ROM, "rb") as f:
            cls.fields = komenu.label_fields(f.read())

    def test_메뉴_항목_레코드를_모두_찾는다(self):
        self.assertEqual(len(self.fields), 270)

    def test_소지품_칸은_네_칸(self):
        # 0x08092F9C: 필드 메뉴의 「もちもの」(DF3908 #47)
        self.assertIn((0x08092F9C, 47, 4, 1), self.fields)

    def test_원문은_모두_칸에_들어간다(self):
        import script_io
        ja = {e.index: e.text for e in script_io.ScriptFile.read(
            os.path.join(ROOT, "script", "ja", "tDF3908.txt")).entries}
        for at, idx, width, lines in self.fields:
            if komenu.checked(width, lines) and idx in ja:
                self.assertLessEqual(komenu.widest(ja[idx]), width,
                                     f"{at:#x} #{idx}")


if __name__ == "__main__":
    unittest.main()
