#!/usr/bin/env python3
"""tools/koflow.py — 창 폭을 넘는 줄 쪼개기 테스트.

이 도구가 바꾸는 것은 **단어 사이 구분자 하나가 줄바꿈이 되는 것**뿐입니다.
글자·들여쓰기·줄 끝 공백·반각/전각 구분이 모두 그대로여야 합니다.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tools"))
import koflow  # noqa: E402
import kowidth  # noqa: E402

SEP = "　"

# 쪼갠 줄을 원래 구분자로 다시 이으면 원문과 글자 하나까지 같아야 합니다.
# (구분자 하나가 줄바꿈으로 바뀌는 것이 이 도구가 하는 일의 전부입니다.)


class PiecesTest(unittest.TestCase):
    def test_앞뒤_공백과_구분자를_따로_들고_있는다(self):
        lead, words, gaps, trail = koflow.pieces(f"{SEP}가나 다라{SEP}마바{SEP}")
        self.assertEqual(lead, SEP)
        self.assertEqual(words, ["가나", "다라", "마바"])
        self.assertEqual(gaps, [" ", SEP])
        self.assertEqual(trail, SEP)

    def test_공백만_있는_줄은_단어가_없다(self):
        lead, words, gaps, trail = koflow.pieces(f"{SEP}{SEP}")
        self.assertEqual(words, [])
        self.assertEqual(lead, f"{SEP}{SEP}")

    def test_여러_칸_띄우기는_단어_경계가_아니다(self):
        """비문의 오른쪽 정렬 같은 자리 맞추기라 끊으면 무너집니다."""
        lead, words, gaps, trail = koflow.pieces(f"가나{SEP}{SEP}{SEP}다라{SEP}마바")
        self.assertEqual(words, [f"가나{SEP}{SEP}{SEP}다라", "마바"])
        self.assertEqual(gaps, [SEP])

    def test_공백이_없으면_빈_문자열이다(self):
        self.assertEqual(koflow.pieces("가나"), ("", ["가나"], [], ""))


class PackTest(unittest.TestCase):
    def test_요청한_줄_수만큼_시작점을_준다(self):
        self.assertEqual(koflow.pack([2, 2, 2, 2], [1, 1, 1], 2), [0, 2])

    def test_가장_넓은_줄을_최소로_만든다(self):
        # [4,2,2] 를 2줄로: (4)(2 1 2)=5 vs (4 1 2)(2)=7 -> 앞이 낫습니다
        self.assertEqual(koflow.pack([4, 2, 2], [1, 1], 2), [0, 1])

    def test_구분자_폭도_센다(self):
        self.assertEqual(koflow.pack([2, 2], [8], 2), [0, 1])

    def test_경계값(self):
        self.assertIsNone(koflow.pack([2], [], 2))      # 단어 < 줄
        self.assertIsNone(koflow.pack([2], [], 0))      # 줄 0
        self.assertIsNone(koflow.pack([2], [], -1))     # 줄 음수
        self.assertIsNone(koflow.pack([], [], 1))       # 단어 없음


class SplitLineTest(unittest.TestCase):
    LONG = SEP.join(["가나다라"] * 3)                   # 8칸 × 3 + 1 × 2 = 26칸

    def test_한계_안에_드는_최소_줄_수로_쪼갠다(self):
        parts = koflow.split_line(self.LONG, 20, 4)
        self.assertEqual(len(parts), 2)
        for p in parts:
            self.assertLessEqual(kowidth.cells(p), 20)

    def test_들여쓰기를_지우지_않는다(self):
        """`　동굴을…` 의 앞 전각공백을 없애서 폭을 맞추면 안 됩니다."""
        line = f"{SEP}동굴을{SEP}１０００일에{SEP}지나"
        parts = koflow.split_line(line, 20, 4)
        self.assertIsNotNone(parts)
        self.assertTrue(parts[0].startswith(SEP), parts)
        self.assertEqual(SEP.join(parts), line)

    def test_줄_끝_공백을_지우지_않는다(self):
        """줄 끝 전각공백은 화면을 지우는 장치입니다 (docs/HANDOFF.md)."""
        parts = koflow.split_line(self.LONG + SEP, 20, 4)
        self.assertIsNotNone(parts)
        self.assertTrue(parts[-1].endswith(SEP), parts)

    def test_반각_공백이_전각으로_바뀌지_않는다(self):
        line = " ".join(["가나다라"] * 3)
        parts = koflow.split_line(line, 20, 4)
        self.assertNotIn(SEP, "".join(parts))

    def test_단어_하나가_한계보다_넓으면_포기한다(self):
        self.assertIsNone(koflow.split_line(f"가나다라마바{SEP}가", 10, 4))

    def test_자리_맞춤_구간은_끊지_않는다(self):
        """비문의 정렬용 연속 공백은 한 줄 안에 통째로 남아야 합니다."""
        run = SEP * 5
        line = f"{SEP}여기{SEP}잠들다{run}가라샤」"
        parts = koflow.split_line(line, 20, 8)
        self.assertTrue(any(f"잠들다{run}가라샤」" in p for p in parts), parts)

    def test_단어가_하나뿐이면_포기한다(self):
        self.assertIsNone(koflow.split_line("가나다라마바", 10, 4))

    def test_허용한_줄_수를_넘기지_않는다(self):
        wide = SEP.join(["가나다라"] * 9)
        self.assertIsNone(koflow.split_line(wide, 20, 2))

    def test_빈_줄은_포기한다(self):
        self.assertIsNone(koflow.split_line("", 20, 4))
        self.assertIsNone(koflow.split_line(f"{SEP}{SEP}", 20, 4))


class ReflowTest(unittest.TestCase):
    LONG = SEP.join(["가나다라"] * 3)

    def test_넘치는_줄만_쪼갠다(self):
        out = koflow.reflow(f"{self.LONG}\n짧다", 20, 4).split("\n")
        self.assertEqual(out[-1], "짧다")
        for line in out:
            self.assertLessEqual(kowidth.cells(line), 20)

    def test_번역자가_잡은_줄바꿈은_살아_있다(self):
        text = f"첫째{SEP}줄이다\n{self.LONG}\n셋째{SEP}줄이다"
        out = koflow.reflow(text, 20, 4).split("\n")
        self.assertEqual(out[0], f"첫째{SEP}줄이다")
        self.assertEqual(out[-1], f"셋째{SEP}줄이다")

    def test_쪼갠_줄을_다시_이으면_원문과_같다(self):
        """들여쓰기와 구분자가 글자 하나까지 그대로여야 합니다."""
        line = f"{SEP}{self.LONG}"
        out = koflow.reflow(f"{line}\n짧다", 20, 4).split("\n")
        self.assertEqual(SEP.join(out[:-1]), line)
        self.assertEqual(out[-1], "짧다")

    def test_제어코드는_순서도_개수도_그대로다(self):
        text = f"{self.LONG}\n짧다<$10>"
        out = koflow.reflow(text, 20, 4)
        self.assertEqual(koflow.TAG_RE.findall(out),
                         koflow.TAG_RE.findall(text))

    def test_grow_가_0이면_줄을_쪼개지_않는다(self):
        self.assertIsNone(koflow.reflow(f"{SEP}{self.LONG}", 20, 0))

    def test_grow_가_0이어도_넘치는_꼬리는_줄인다(self):
        """꼬리 줄이기는 줄을 늘리지 않으므로 grow 와 상관없습니다."""
        out = koflow.reflow("가나" + "　" * 20, 20, 0)
        self.assertEqual(kowidth.cells(out), 20)

    def test_이미_한계_안이면_손대지_않는다(self):
        self.assertIsNone(koflow.reflow("가나\n다라", 20, 4))

    def test_치환이_아닌_제어코드가_든_줄은_넓어도_그대로_둔다(self):
        self.assertIsNone(koflow.reflow(f"{self.LONG}<$10>", 20, 4))

    def test_치환_코드가_든_줄은_쪼갠다(self):
        """`<$12>` 는 이름이 들어가는 자리라 글자처럼 그려집니다."""
        text = f"<$12>은（는）{SEP}「마야의{SEP}팔찌」를"
        out = koflow.reflow(text, 20, 4)
        self.assertIsNotNone(out)
        for line in out.split("\n"):
            self.assertLessEqual(kowidth.cells(line), 20)
        self.assertEqual(koflow.TAG_RE.findall(out),
                         koflow.TAG_RE.findall(text))

    def test_치환_코드는_붙은_단어와_함께_움직인다(self):
        out = koflow.reflow(f"<$12>은（는）{SEP}「마야의{SEP}팔찌」를", 20, 4)
        self.assertTrue(any(l.startswith("<$12>은（는）")
                            for l in out.split("\n")), out)

    def test_치환_코드와_그_밖의_코드가_섞이면_손대지_않는다(self):
        self.assertIsNone(koflow.reflow(f"<$12>{SEP}{self.LONG}<$10>", 20, 4))

    def test_늘릴_줄_수를_넘으면_그_줄은_포기한다(self):
        self.assertIsNone(koflow.reflow(SEP.join(["가나다라"] * 9), 20, 1))

    def test_쪼갤_수_있는_줄만이라도_쪼갠다(self):
        text = f"{'가' * 12}\n{self.LONG}"
        out = koflow.reflow(text, 20, 4).split("\n")
        self.assertEqual(out[0], "가" * 12)          # 손대지 않음
        self.assertLessEqual(kowidth.cells(out[1]), 20)


class TrimTailTest(unittest.TestCase):
    """꼬리는 그 줄을 지우는 장치라 **지우는 범위**가 창 폭입니다."""

    def test_넘치는_만큼_꼬리를_줄인다(self):
        line = "허나" + "　" * 18                     # 4 + 18 = 22칸
        got = koflow.trim_tail(line, 20)
        self.assertEqual(kowidth.cells(got), 20)
        self.assertTrue(got.startswith("허나"))

    def test_한계_안이면_꼬리를_건드리지_않는다(self):
        line = "허나" + "　" * 16                     # 20칸
        self.assertEqual(koflow.trim_tail(line, 20), line)

    def test_꼬리가_없으면_그대로다(self):
        self.assertEqual(koflow.trim_tail("가나다라", 4), "가나다라")

    def test_글자만으로_이미_넘치면_꼬리를_모두_없앤다(self):
        line = "가" * 12 + "　" * 4                   # 글자만 24칸
        self.assertEqual(koflow.trim_tail(line, 20), "가" * 12)

    def test_reflow_가_꼬리부터_줄인다(self):
        text = "허나" + "　" * 18
        out = koflow.reflow(text, 20, 0)
        self.assertEqual(kowidth.cells(out), 20)


class AllowedGrowTest(unittest.TestCase):
    MANY = {1: 5, 2: 5, 3: 5, 4: 5}            # 줄 수가 여러 가지인 표
    FIELD, MENU = True, False

    def test_필드_대사는_창이_스크롤하므로_늘려도_된다(self):
        """원문 항목의 줄 수가 1~63줄까지 고르게 있습니다."""
        self.assertEqual(koflow.allowed_grow({4: 2, 6: 8}, 6, 6, 8,
                                             self.FIELD), 8)

    def test_필드_대사는_원문이_한_줄이어도_늘려도_된다(self):
        self.assertEqual(koflow.allowed_grow({1: 2, 2: 10}, 1, 1, 8,
                                             self.FIELD), 8)

    def test_메뉴는_원문이_한_줄이면_늘리지_않는다(self):
        self.assertEqual(koflow.allowed_grow(self.MANY, 1, 1, 8, self.MENU), 0)

    def test_메뉴도_줄_수가_여러_가지면_허용한_만큼(self):
        self.assertEqual(koflow.allowed_grow(self.MANY, 3, 3, 8, self.MENU), 8)

    def test_메뉴의_원문_줄_수가_고정이면_그_최대치까지만(self):
        """`tDE8060` 은 원문 74항목이 전부 2줄인 고정 높이 칸입니다."""
        self.assertEqual(koflow.allowed_grow({2: 74}, 2, 2, 8, self.MENU), 0)

    def test_고정_높이_칸도_남는_줄만큼은_늘린다(self):
        self.assertEqual(koflow.allowed_grow({1: 900, 2: 60}, 2, 1, 8,
                                             self.MENU), 1)

    def test_이미_최대치를_넘었으면_0(self):
        self.assertEqual(koflow.allowed_grow({2: 74}, 2, 3, 8, self.MENU), 0)

    def test_분포가_비어_있으면_허용한_만큼(self):
        self.assertEqual(koflow.allowed_grow({}, 3, 3, 8, self.MENU), 8)


class TableLimitTest(unittest.TestCase):
    def test_필드_대사_표는_20칸(self):
        self.assertEqual(kowidth.table_limit("tE06168.txt"), 20)

    def test_메뉴_기록_표는_28칸(self):
        self.assertEqual(kowidth.table_limit("tDE1AF8.txt"), 28)

    def test_표_종류를_주소로_가른다(self):
        self.assertTrue(kowidth.is_field("tE06168.txt"))
        self.assertFalse(kowidth.is_field("tDE1AF8.txt"))


class HeaderTest(unittest.TestCase):
    def test_손으로_적어_둔_주석을_그대로_읽는다(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                         encoding="utf-8") as f:
            f.write("# 첫 줄\n# 손으로 적은 메모\n\n## 0001 @0x1\n가\n")
            path = f.name
        try:
            self.assertEqual(koflow.header_of(path), "첫 줄\n손으로 적은 메모")
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
