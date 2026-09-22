#!/usr/bin/env python3
"""tools/koflow.py — 넘치는 줄 쪼개기 테스트.

글자는 한 자도 바뀌지 않아야 하고, 번역자가 잡아 둔 줄바꿈도 살아 있어야
합니다. 한계를 넘는 줄만 쪼갭니다.
"""
from __future__ import annotations

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tools"))
import koflow  # noqa: E402
import kowidth  # noqa: E402

SEP = "　"
strip = lambda s: re.sub(r"[\s　]", "", s)          # noqa: E731


class TokenTest(unittest.TestCase):
    def test_전각_공백과_반각_공백_모두_단어_경계다(self):
        self.assertEqual(koflow.tokens(f"가나{SEP}다라 마바"),
                         ["가나", "다라", "마바"])

    def test_빈_조각은_버린다(self):
        self.assertEqual(koflow.tokens(f"{SEP}{SEP}가나{SEP}"), ["가나"])


class PackTest(unittest.TestCase):
    def test_정확히_요청한_줄_수로_나눈다(self):
        w, lines = koflow.pack(["가", "나", "다", "라"], 2)
        self.assertEqual(len(lines), 2)
        self.assertEqual(SEP.join(lines).replace(SEP, ""), "가나다라")

    def test_가장_넓은_줄을_최소로_만든다(self):
        # '가나다'(6칸) '라'(2칸) 보다 '가나'(5칸) '다라'(5칸) 가 낫습니다
        self.assertEqual(koflow.pack(["가나", "다", "라"], 2)[0], 5)

    def test_단어_순서는_바뀌지_않는다(self):
        _, lines = koflow.pack(["하나", "둘", "셋", "넷", "다섯"], 3)
        self.assertEqual([t for l in lines for t in koflow.tokens(l)],
                         ["하나", "둘", "셋", "넷", "다섯"])

    def test_토큰이_줄_수보다_적으면_못_나눈다(self):
        self.assertIsNone(koflow.pack(["가"], 2))


class SplitLineTest(unittest.TestCase):
    def test_한계_안에_들어가는_최소_줄_수로_쪼갠다(self):
        line = SEP.join(["가나다"] * 4)          # 6칸씩 + 공백 3 = 27칸
        parts = koflow.split_line(line, 14)
        self.assertEqual(len(parts), 2)
        for p in parts:
            self.assertLessEqual(kowidth.cells(p), 14)

    def test_한_단어가_한계보다_넓으면_포기한다(self):
        self.assertIsNone(koflow.split_line("가나다라마바", 10))

    def test_글자는_한_자도_바뀌지_않는다(self):
        line = SEP.join(["가나다"] * 4)
        self.assertEqual(strip("".join(koflow.split_line(line, 14))),
                         strip(line))


class ReflowTest(unittest.TestCase):
    LONG = SEP.join(["가나다라"] * 3)            # 8칸씩 + 공백 2 = 26칸

    def test_넘치는_줄만_쪼갠다(self):
        text = f"{self.LONG}\n짧다"
        out = koflow.reflow(text, 20, grow=4)
        lines = out.split("\n")
        self.assertEqual(lines[-1], "짧다")      # 손대지 않음
        for line in lines:
            self.assertLessEqual(kowidth.cells(line), 20)

    def test_번역자가_잡은_줄바꿈은_살아_있다(self):
        """줄을 섞지 않습니다 — 절 단위 줄바꿈이 뭉개지면 안 됩니다."""
        text = f"첫째{SEP}줄이다\n{self.LONG}\n셋째{SEP}줄이다"
        out = koflow.reflow(text, 20, grow=4).split("\n")
        self.assertEqual(out[0], f"첫째{SEP}줄이다")
        self.assertEqual(out[-1], f"셋째{SEP}줄이다")

    def test_글자와_제어코드는_그대로다(self):
        text = f"{self.LONG}\n짧다<$10>"
        out = koflow.reflow(text, 20, grow=4)
        self.assertEqual(strip(out), strip(text))
        self.assertEqual(koflow.TAG_RE.findall(out),
                         koflow.TAG_RE.findall(text))

    def test_이미_한계_안이면_손대지_않는다(self):
        self.assertIsNone(koflow.reflow("가나\n다라", 20, grow=4))

    def test_제어코드가_든_줄은_넓어도_그대로_둔다(self):
        """코드의 뜻을 모르므로 글자 대비 자리가 바뀌지 않게 비켜 갑니다."""
        self.assertIsNone(koflow.reflow(f"{self.LONG}<$10>", 20, grow=4))

    def test_늘릴_수_있는_줄_수를_넘으면_그_줄은_포기한다(self):
        text = SEP.join(["가나다라"] * 9)        # 세 줄은 되어야 들어갑니다
        self.assertIsNone(koflow.reflow(text, 20, grow=1))

    def test_쪼갤_수_있는_줄만이라도_쪼갠다(self):
        text = f"{'가' * 12}\n{self.LONG}"      # 첫 줄은 한 단어라 못 쪼갬
        out = koflow.reflow(text, 20, grow=4).split("\n")
        self.assertEqual(out[0], "가" * 12)
        self.assertLessEqual(kowidth.cells(out[1]), 20)


class OneLineTest(unittest.TestCase):
    """원문이 한 줄인 항목은 이름·낱말입니다. 쪼개면 안 됩니다.

    `와카나　공주` 가 `와카나` / `공주` 두 줄이 되면 이름칸이 깨집니다.
    """

    def test_늘릴_줄이_없으면_쪼개지_않는다(self):
        self.assertIsNone(koflow.reflow(SEP.join(["가나다라"] * 3), 20, grow=0))

    def test_원문_줄_수를_주면_한_줄짜리는_건드리지_않는다(self):
        wide = SEP.join(["가나다라"] * 3)
        self.assertEqual(koflow.allowed_grow(1, 4), 0)
        self.assertIsNone(koflow.reflow(wide, 20, koflow.allowed_grow(1, 4)))

    def test_여러_줄짜리는_허용한_만큼_늘린다(self):
        self.assertEqual(koflow.allowed_grow(3, 4), 4)


class TableLimitTest(unittest.TestCase):
    def test_원문이_실제로_쓴_최대_줄_폭이_한계다(self):
        self.assertEqual(koflow.table_limit(["가나\n다라마", "바"]), 6)

    def test_이름_읽기_색인은_빼고_센다(self):
        self.assertEqual(koflow.table_limit(["가나다라마바／かな", "가"]), 2)

    def test_원문이_없으면_0(self):
        self.assertEqual(koflow.table_limit([]), 0)


if __name__ == "__main__":
    unittest.main()
