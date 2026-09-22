#!/usr/bin/env python3
"""tools/koaudit.py — 번역문 전수 감사 테스트.

실기에서 터지는 버그는 대부분 눈으로 안 보이는 것들입니다 — 제어 코드가
빠졌거나, 줄 수가 달라졌거나, printf 지정자가 바뀌었거나. 전수로 잡습니다.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tools"))
import koaudit  # noqa: E402


class TagTest(unittest.TestCase):
    """제어 코드는 **개수도 순서도** 원문과 같아야 합니다."""

    def test_태그를_순서대로_뽑는다(self):
        self.assertEqual(koaudit.tags("<$10>가나<$1A>다"), ["$10", "$1A"])

    def test_같으면_문제_없음(self):
        self.assertEqual(koaudit.tag_issues("<$10>あ<$1A>", "<$10>가<$1A>"), [])

    def test_빠진_태그를_잡는다(self):
        bad = koaudit.tag_issues("<$10>あ<$1A>", "<$10>가")
        self.assertEqual(len(bad), 1)
        self.assertIn("$1A", bad[0])

    def test_더_들어간_태그를_잡는다(self):
        bad = koaudit.tag_issues("<$10>あ", "<$10>가<$1A>")
        self.assertEqual(len(bad), 1)

    def test_순서가_바뀌면_잡는다(self):
        bad = koaudit.tag_issues("<$10>あ<$1A>", "<$1A>가<$10>")
        self.assertEqual(len(bad), 1)
        self.assertIn("순서", bad[0])


class LineTest(unittest.TestCase):
    def test_줄_수가_같으면_문제_없음(self):
        self.assertEqual(koaudit.line_issues("가\n나", "다\n라"), [])

    def test_줄이_줄면_앞_글자가_남는다고_알린다(self):
        bad = koaudit.line_issues("가\n나", "다")
        self.assertEqual(len(bad), 1)
        self.assertIn("줄었습니다", bad[0])

    def test_줄이_늘면_창_용량_확인이라고_알린다(self):
        bad = koaudit.line_issues("가", "다\n라")
        self.assertEqual(len(bad), 1)
        self.assertIn("늘었습니다", bad[0])


class PrintfTest(unittest.TestCase):
    """`<$1F>` 뒤의 지정자는 한 글자도 바뀌면 안 됩니다."""

    def test_같으면_문제_없음(self):
        self.assertEqual(koaudit.printf_issues("<$1F>s개", "<$1F>s개"), [])

    def test_지정자가_바뀌면_잡는다(self):
        bad = koaudit.printf_issues("<$1F>-3d", "<$1F>d")
        self.assertEqual(len(bad), 1)

    def test_여러_개도_순서대로_본다(self):
        self.assertEqual(
            koaudit.printf_issues("<$1F>s와 <$1F>d", "<$1F>s과 <$1F>d"), [])
        self.assertEqual(
            len(koaudit.printf_issues("<$1F>s와 <$1F>d", "<$1F>d과 <$1F>s")), 2)


class JosaTest(unittest.TestCase):
    """이름 코드 뒤에는 조사를 병기해야 합니다 (받침을 알 수 없으므로)."""

    def test_병기했으면_문제_없음(self):
        self.assertEqual(koaudit.josa_issues("<$12>은（는）왔다"), [])
        self.assertEqual(koaudit.josa_issues("<$1F>s（으）로 갔다"), [])

    def test_맨_조사는_잡는다(self):
        bad = koaudit.josa_issues("<$12>은 왔다")
        self.assertEqual(len(bad), 1)
        self.assertIn("은", bad[0])

    def test_이름_코드가_아니면_보지_않는다(self):
        self.assertEqual(koaudit.josa_issues("텐란은 왔다"), [])

    def test_낱말_일부는_잡지_않는다(self):
        """「<$12>과자」 의 '과' 는 조사가 아니라 낱말입니다."""
        self.assertEqual(koaudit.josa_issues("「<$12>과자」가 대박"), [])
        self.assertEqual(koaudit.josa_issues("<$12>이름을 불렀다"), [])

    def test_문장_끝의_맨_조사도_잡는다(self):
        self.assertEqual(len(koaudit.josa_issues("<$14>을")), 1)

    def test_반각_괄호는_잡는다(self):
        """원문 표기와 맞추어 전각 괄호를 씁니다."""
        bad = koaudit.josa_issues("<$12>은(는) 왔다")
        self.assertEqual(len(bad), 1)


class SeverityTest(unittest.TestCase):
    """줄이 늘어난 것은 확인 대상이고, 나머지는 고쳐야 할 오류입니다."""

    def test_줄이_늘어난_것은_경고(self):
        self.assertTrue(koaudit.is_warning("줄이 늘었습니다 (3→4): 창 용량 확인 필요"))

    def test_나머지는_오류(self):
        self.assertFalse(koaudit.is_warning("제어 코드 <$1A> 가 빠졌습니다"))
        self.assertFalse(koaudit.is_warning("줄이 줄었습니다 (2→1): 그 줄에 이전 글자가 남습니다"))


class PadTest(unittest.TestCase):
    """원문 끝의 공백 줄은 **앞 화면을 지우는 용도**라 빠뜨리면 글자가 남습니다."""

    def test_빠진_공백_줄을_되살린다(self):
        ja = "あ\n\u3000\u3000\u3000"
        self.assertEqual(koaudit.pad_tail(ja, "가"), "가\n\u3000\u3000\u3000")

    def test_이미_맞으면_그대로(self):
        ja = "あ\n\u3000\u3000"
        self.assertEqual(koaudit.pad_tail(ja, "가\n\u3000\u3000"), "가\n\u3000\u3000")

    def test_공백_줄이_없으면_그대로(self):
        self.assertEqual(koaudit.pad_tail("あ\nい", "가"), "가")

    def test_번역이_더_길면_그대로(self):
        self.assertEqual(koaudit.pad_tail("あ\n\u3000", "가\n나\n다"), "가\n나\n다")

    def test_빈_번역은_건드리지_않는다(self):
        self.assertEqual(koaudit.pad_tail("あ\n\u3000", ""), "")


class EntryTest(unittest.TestCase):
    def test_문제_없는_항목은_빈_목록(self):
        self.assertEqual(koaudit.check_entry("<$10>あ<$1A>", "<$10>가<$1A>"), [])

    def test_번역하지_않은_항목은_건너뛴다(self):
        self.assertEqual(koaudit.check_entry("<$10>あ<$1A>", ""), [])

    def test_여러_문제를_모두_낸다(self):
        bad = koaudit.check_entry("<$10>あ<$1A>\nい", "<$10>가")
        self.assertGreaterEqual(len(bad), 2)


if __name__ == "__main__":
    unittest.main()
