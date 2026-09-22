#!/usr/bin/env python3
"""tools/koprog.py — 번역 진행률.

분모가 틀리면 진행률이 통째로 거짓말이 됩니다. 실제로 `--min-count 32`
때문에 표 423개가 덤프에서 빠져 83.5% 로 부풀어 있었습니다. 이번에는
**게임이 쓰지 않는 표**가 분모에 들어가 반대로 깎이고 있었습니다.

제외 대상은 다음과 같습니다.

  DFBEE4  비-JPN 낱말표 — 읽는 코드가 없습니다 (tools/koshiri.py 참고)
  DF9080  끝말잇기 낱말 조각 — koshiri.py 가 롬을 직접 고칩니다
  DF809C  CAST 자막 · DF8494  STAFF 자막 — 제작진 실명이라 원문 유지
  DFEB94 · DFED60 · DFF16C · DFFE9C · E011C8 · E0255C
          개발용 장면 라벨 ("E074 ニンジャ船にのる" 꼴). 457항목이
          제어 코드를 하나도 쓰지 않습니다 — 표시되는 표는 모두 씁니다.
  4670DC · 467F9C · 89094C · 8A42C4 · 8C0148 · 9B3F14 · B185B0
          표가 아닌 자리. 덤프 필터를 통과했지만 내용이 글이 아닙니다.
          눈으로 하나씩 확인했습니다 — 자동 판정에 맡기면 F62D1C
          (세 항목이 똑같은 진짜 대사) 같은 것을 잘못 버립니다.
  220020 · 26CAC8 · CAE740 · D7DE5C · DAAA70 · DAAB68 · E02DA4 ·
  E3DC5C · E5A3D0 · E7E6E0 · E9D308 · EBEB48 · EE8E58 · EF54D0 ·
  F0C118 · F2E98C
          크기 접두 바이너리 블롭. 문자열표가 아닙니다.

DE1AF8 은 **표째로 빼면 안 됩니다.** 화면에 나오는 아이템 이름표라
738항목이 이미 번역돼 있습니다. 빼야 할 것은 그 안의 '0' 자리뿐입니다.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tools"))
import koprog  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
JA = os.path.join(ROOT, "script", "ja")
KO = os.path.join(ROOT, "script", "ko")


class ExcludeTest(unittest.TestCase):
    def test_게임이_쓰지_않는_표는_제외한다(self):
        for name in ("DFBEE4", "DF9080"):
            self.assertIn(name, koprog.EXCLUDED)

    def test_아이템_이름표는_표째로_빼지_않는다(self):
        """번역한 738항목이 분자에서 같이 사라집니다."""
        self.assertNotIn("DE1AF8", koprog.EXCLUDED)

    def test_제작진_자막도_제외한다(self):
        for name in ("DF809C", "DF8494"):
            self.assertIn(name, koprog.EXCLUDED)

    def test_글이_아닌_자리도_제외한다(self):
        for name in ("4670DC", "467F9C", "89094C", "8A42C4",
                     "8C0148", "9B3F14", "B185B0"):
            self.assertIn(name, koprog.EXCLUDED)

    def test_바이너리_블롭_표도_제외한다(self):
        for name in ("220020", "26CAC8", "CAE740", "D7DE5C",
                     "DAAA70", "DAAB68", "E02DA4", "E3DC5C",
                     "E5A3D0", "E7E6E0", "E9D308", "EBEB48",
                     "EE8E58", "EF54D0", "F0C118", "F2E98C"):
            self.assertIn(name, koprog.EXCLUDED)

    def test_항목이_다_같아도_진짜_대사는_남긴다(self):
        """tF62D1C 는 세 항목이 똑같지만 멀쩡한 대사입니다."""
        self.assertNotIn("F62D1C", koprog.EXCLUDED)

    def test_개발용_장면_라벨도_제외한다(self):
        for name in ("DFEB94", "DFED60", "DFF16C",
                     "DFFE9C", "E011C8", "E0255C"):
            self.assertIn(name, koprog.EXCLUDED)

    def test_본편_대사_표는_제외하지_않는다(self):
        for name in ("F4C354", "F0E0F8", "E2C6B0", "DF3908", "DE1AF8"):
            self.assertNotIn(name, koprog.EXCLUDED)

    def test_제외_이유가_모두_적혀_있다(self):
        for name, why in koprog.EXCLUDED.items():
            self.assertTrue(why.strip(), f"{name} 에 제외 이유가 없습니다")


class CountTest(unittest.TestCase):
    def test_빈_원문은_세지_않는다(self):
        rows = koprog.count({"tAAA111.txt": [("", ""), ("  ", "가"), ("あ", "")]})
        self.assertEqual(rows["AAA111"], (1, 0))

    def test_０_자리는_세지_않는다(self):
        """아이템 이름표의 빈 자리입니다. 화면에 나오지 않습니다."""
        rows = koprog.count({"tDE1AF8.txt": [("0", ""), ("0", ""), ("かぶと", "투구")]})
        self.assertEqual(rows["DE1AF8"], (1, 1))

    def test_전각_０_자리도_세지_않는다(self):
        """tCA8DE0 은 17항목이 전부 전각 '０' 입니다."""
        rows = koprog.count({"tCA8DE0.txt": [("\uff10", ""), ("\uff10", "")]})
        self.assertEqual(rows["CA8DE0"], (0, 0))

    def test_０_자리는_어느_표에서나_뺀다(self):
        rows = koprog.count({"tAAA111.txt": [("0", ""), ("あ", "가")]})
        self.assertEqual(rows["AAA111"], (1, 1))

    def test_번역이_있으면_완료로_센다(self):
        rows = koprog.count({"tAAA111.txt": [("あ", "가"), ("い", "")]})
        self.assertEqual(rows["AAA111"], (2, 1))

    def test_제외한_표는_결과에_없다(self):
        rows = koprog.count({"tDFBEE4.txt": [("あ", "")]})
        self.assertEqual(rows, {})


class FormatTest(unittest.TestCase):
    """가나·한자가 하나도 없으면 옮길 것이 없습니다.

    DF3908 에는 printf 서식과 기호만 든 항목이 수백 개 있습니다.
    서식은 원문 그대로여야 하고(바꾸면 값이 틀리거나 튕깁니다),
    기호와 영문 라벨은 옮길 말이 없습니다.
    """

    def test_서식만_있으면_대상이_아니다(self):
        for t in ("<$1F>-7dＧ", "<$1F>d／<$1F>d", "<$1F>-3d：<$1F>-02d"):
            self.assertFalse(koprog.translatable(t), t)

    def test_기호와_영문_라벨도_대상이_아니다(self):
        for t in ("Ｇ", "＋", "×", "：", "ＥＸＰ", "ＮＥＸＴ", "[", "%"):
            self.assertFalse(koprog.translatable(t), t)

    def test_가나나_한자가_있으면_대상이다(self):
        for t in ("はい", "天帝", "<$1F>dコ", "バングル"):
            self.assertTrue(koprog.translatable(t), t)

    def test_서식을_낀_본문도_대상이다(self):
        self.assertTrue(koprog.translatable("<$1F>dかい\u3000こうげき"))

    def test_세지_않는다(self):
        rows = koprog.count({"tAAA111.txt": [("Ｇ", ""), ("はい", "예")]})
        self.assertEqual(rows["AAA111"], (1, 1))


class TotalTest(unittest.TestCase):
    def test_합계는_표별_합과_같다(self):
        rows = {"A": (10, 4), "B": (5, 5)}
        self.assertEqual(koprog.totals(rows), (15, 9))

    def test_대상이_없으면_０으로_나눈다고_터지지_않는다(self):
        self.assertEqual(koprog.totals({}), (0, 0))
        self.assertEqual(koprog.percent(0, 0), 0.0)

    def test_비율을_낸다(self):
        self.assertAlmostEqual(koprog.percent(4, 8), 50.0)


class RealTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(JA):
            raise unittest.SkipTest("script/ja 없음 — `make script` 를 먼저")

    def test_실제_덤프에서_진행률이_나온다(self):
        rows = koprog.count(koprog.load(JA, KO))
        total, done = koprog.totals(rows)
        self.assertGreater(total, 10000)
        self.assertLessEqual(done, total)

    def test_제외한_표가_분모에서_빠졌다(self):
        rows = koprog.count(koprog.load(JA, KO))
        for name in koprog.EXCLUDED:
            self.assertNotIn(name, rows)


if __name__ == "__main__":
    unittest.main()
