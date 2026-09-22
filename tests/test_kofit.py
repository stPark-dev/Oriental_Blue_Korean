#!/usr/bin/env python3
"""tools/kofit.py — 줄 바꿔넣기 안전장치 테스트.

    python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tools"))
import kofit  # noqa: E402
import kowidth  # noqa: E402

SP = "　"
# 창 폭은 표마다 다릅니다 (kowidth.table_limit). 본문 표는 대개 20칸이라
# 검사 로직만 보는 여기서는 20 을 씁니다.
FIELD = 20


class TableLimitTest(unittest.TestCase):
    """창 폭은 그 표의 원문이 실제로 쓴 가장 넓은 줄입니다."""

    def test_원문이_쓴_가장_넓은_줄이_한계(self):
        # 4칸 · 6칸 -> 6칸
        self.assertEqual(kowidth.table_limit(["ああああ", "いいいいいい"]), 6)

    def test_색인_데이터는_폭에서_뺀다(self):
        self.assertEqual(
            kowidth.table_limit(["ああ", "보통의　검／보통의　검"]), 2)


class CheckTest(unittest.TestCase):
    """바꿔도 되는지 — 하나라도 어긋나면 그 줄은 건너뜁니다."""

    def test_한도_안이면_통과(self):
        self.assertIsNone(kofit.check("가" * 11, "가" * 10, FIELD))

    def test_아직_넘치면_막는다(self):
        self.assertIn("아직", kofit.check("가" * 12, "가" * 11, FIELD))

    def test_제어_코드가_사라지면_막는다(self):
        self.assertIn("제어 코드",
                      kofit.check("<$10>가나다", "가나다", FIELD))

    def test_제어_코드_순서가_바뀌면_막는다(self):
        self.assertIn("제어 코드",
                      kofit.check("<$10><$12>가", "<$12><$10>가", FIELD))

    def test_제어_코드가_그대로면_통과(self):
        self.assertIsNone(
            kofit.check("<$12>은（는）" + SP + "가나다라마", "<$12>은（는）" + SP + "가나",
                        FIELD))

    def test_줄바꿈이_들어가면_막는다(self):
        self.assertIn("줄바꿈", kofit.check("가" * 11, "가\n나", FIELD))

    def test_줄_끝_전각공백을_빠뜨리면_막는다(self):
        self.assertIn("전각공백",
                      kofit.check("가나다라마바사아자차" + SP, "가나다", FIELD))

    def test_줄_끝_전각공백을_지키면_통과(self):
        self.assertIsNone(
            kofit.check("가나다라마바사아자차" + SP, "가나다" + SP, FIELD))


class ShrinkTest(unittest.TestCase):
    """정형 축약 — 한도에 닿을 때까지만, 못 맞추면 None."""

    def test_한도에_맞으면_줄인다(self):
        # 「나는　그것을　손에　넣었다」 23칸 -> 「난　그걸　얻었다」
        line = "나는" + SP + "그것을" + SP + "손에" + SP + "넣었다"
        self.assertGreater(kowidth.cells(line), FIELD)
        got = kofit.shrink(line, FIELD)
        self.assertIsNotNone(got)
        self.assertLessEqual(kowidth.cells(got), FIELD)

    def test_못_맞추면_None(self):
        self.assertIsNone(kofit.shrink("가" * 20, FIELD))

    def test_이미_짧으면_손대지_않는다(self):
        self.assertIsNone(kofit.shrink("가나", FIELD))

    def test_규칙은_줄이는_것만_있다(self):
        for a, b in kofit.RULES:
            self.assertLess(len(b), len(a), f"{a} -> {b} 가 줄지 않습니다")


if __name__ == "__main__":
    unittest.main()
