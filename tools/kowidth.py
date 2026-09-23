#!/usr/bin/env python3
"""번역문이 원문보다 넓지 않은지 검사합니다.

이 게임은 **모든 글자가 8픽셀 폭 칸 하나**를 씁니다 (작은 폰트 8×8,
큰 폰트 8×16 — 높이만 다릅니다). 한글은 16×16 이라 **칸 두 개**를 씁니다.

그래서 글자 수를 줄여도 폭은 넘칠 수 있습니다::

    こうげき力   5글자 = 5칸
    공격력을     4글자 = 8칸   <- 더 넓다

메시지 창 폭을 넘기면 글자가 잘리므로, 삽입 전에 원문 폭과 비교합니다.

## 창 폭은 20칸입니다 (필드 대사)

실기 화면에서 확인했습니다. 20칸을 넘기면 **음절이 반으로 찢어집니다** —
왼쪽 8×16 칸만 그려지고 오른쪽 칸은 다음 줄로 밀립니다::

    「１０００인　기원」이　안　끝나면      25칸
      -> 「１０００인　기원」이　안　ㄱ     19칸 + 「끝」의 왼쪽 칸
         (ㅌ)나면                          나머지가 다음 줄로

원문도 이 한계를 지킵니다. 필드 대사(표 주소 0xE00000 이상) 원문
44,970줄 중 20칸을 넘는 줄이 **하나도 없습니다.**

메뉴·기록·아이템 표(0xE00000 미만)는 창이 더 넓어 원문이 28칸까지
갑니다. 그래서 한계를 표에 따라 다르게 잡습니다.

    python3 tools/kowidth.py                  # script/ko 전체 검사
    python3 tools/kowidth.py --max-cells 20   # 한계를 직접 주려면
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kocode  # noqa: E402
from script_io import ScriptFile  # noqa: E402

# 필드 대사 창은 20칸(160픽셀)입니다 — 실기 확인.
FIELD_CELLS = 20
# 메뉴·기록 창은 더 넓습니다. 원문이 실제로 쓰는 최대폭이 28칸입니다.
MENU_CELLS = 28
# 이 주소 이상이 필드 대사 표입니다.
FIELD_TABLE_FROM = 0xE00000

TAG_RE = re.compile(r"<\$([0-9A-Fa-f]{2,3})>")
# <$1F> 뒤에 붙는 printf 서식: -, 0, 자리수, 변환문자
FMT_RE = re.compile(r"-?0?(\d*)([a-zA-Z])")
# 고대 문자 (build/ja.tbl 0x180~0x1AA): `\A` 두 글자가 한 칸짜리 글리프 하나
ANCIENT_RE = re.compile(r"\\[0-9A-Z]")


def cells(text: str) -> int:
    """한 줄이 차지하는 칸 수 (8픽셀 단위)."""
    total = 0
    i = 0
    while i < len(text):
        m = TAG_RE.match(text, i)
        if m:
            i = m.end()
            if int(m.group(1), 16) != 0x1F:
                continue          # 그려지지 않는 제어 코드
            f = FMT_RE.match(text, i)
            if f:
                total += int(f.group(1)) if f.group(1) else (
                    0 if f.group(2) in "sc" else 1)
                i = f.end()
            continue
        if ANCIENT_RE.match(text, i):
            total += 1
            i += 2
            continue
        total += 2 if kocode.is_syllable(text[i]) else 1
        i += 1
    return total


def line_cells(text: str) -> list[int]:
    return [cells(line) for line in text.split("\n")]


def is_field(name: str) -> bool:
    """필드 대사 표인지 (파일 이름 `tE27024.txt` 의 주소로 갈립니다).

    필드 대사 창은 **스크롤합니다** — 원문 항목의 줄 수가 1~63줄까지 고르게
    있습니다. 메뉴·기록·아이템 표는 높이가 정해진 칸이라 다릅니다.
    """
    try:
        return int(os.path.basename(name)[1:-4], 16) >= FIELD_TABLE_FROM
    except ValueError:
        return False


def table_limit(name: str) -> int:
    """파일 이름(`tE27024.txt`)으로 그 표가 쓰는 창 폭을 정합니다."""
    return FIELD_CELLS if is_field(name) else MENU_CELLS


def is_index_data(text: str) -> bool:
    """`이름／읽기` 형태인지. 정렬용 색인이라 화면에 그대로 나오지 않습니다."""
    return "／" in text


def too_wide(ja: str, ko: str, limit: int) -> list[tuple[int, int]]:
    """`limit` 칸을 넘는 **번역한** 줄을 (줄번호, 칸) 으로 돌려줍니다.

    원문과 똑같은 줄은 뺍니다 — 손대지 않았으니 게임이 이미 그리고 있고,
    고대문자 이스케이프(`\\A`) 처럼 한 글자가 두 코드인 표기도 있어서
    칸 수 계산이 실제 폭과 어긋납니다.
    """
    src = ja.split("\n")
    out = []
    for i, line in enumerate(ko.split("\n")):
        if i < len(src) and line == src[i]:
            continue
        w = cells(line)
        if w > limit:
            out.append((i, w))
    return out


def check(ja: str, ko: str) -> list[tuple[int, int, int]]:
    """원문보다 넓은 줄을 (줄번호, 번역 칸, 원문 칸) 으로 돌려줍니다."""
    a, b = line_cells(ja), line_cells(ko)
    out = []
    for i, w in enumerate(b):
        limit = a[i] if i < len(a) else 0
        if w > limit:
            out.append((i, w, limit))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="번역문 폭 검사")
    ap.add_argument("--ja", default="script/ja")
    ap.add_argument("--ko", default="script/ko")
    ap.add_argument("--limit", type=int, default=30, help="출력할 최대 건수")
    ap.add_argument("--max-cells", type=int, default=None,
                    help=f"한 줄 한계를 직접 지정 (기본: 필드 대사 "
                         f"{FIELD_CELLS}칸 · 메뉴/기록 {MENU_CELLS}칸)")
    args = ap.parse_args()

    total = over = 0
    shown = 0
    hard: list[tuple[str, int, int, str]] = []
    for path in sorted(glob.glob(os.path.join(args.ko, "*.txt"))):
        name = os.path.basename(path)
        ja_path = os.path.join(args.ja, name)
        if not os.path.exists(ja_path):
            continue
        ja = {e.index: e.text for e in ScriptFile.read(ja_path).entries}
        for e in ScriptFile.read(path).entries:
            if not e.text.strip():
                continue
            total += 1
            if not is_index_data(e.text):
                lines = e.text.split("\n")
                limit = (args.max_cells if args.max_cells is not None
                         else table_limit(name))
                for ln, w in too_wide(ja.get(e.index, ""), e.text, limit):
                    hard.append((name, e.index, w, lines[ln]))
            bad = check(ja.get(e.index, ""), e.text)
            if not bad:
                continue
            over += 1
            if shown < args.limit:
                shown += 1
                for ln, w, lim in bad:
                    print(f"  {name} #{e.index:04d} {ln + 1}번째 줄: "
                          f"{w}칸 > 원문 {lim}칸")
                    print(f"      원문 {ja.get(e.index, '').splitlines()[ln] if ln < len(ja.get(e.index, '').splitlines()) else ''!r}")
                    print(f"      번역 {e.text.splitlines()[ln]!r}")
    print(f"\n검사 {total:,}개 / 원문보다 넓은 항목 {over:,}개")
    if shown < over:
        print(f"(…외 {over - shown}건)")
    print("  (원문 폭은 참고값입니다. 실제 한계는 메시지 창 폭입니다.)")

    lim_txt = (f"{args.max_cells}칸" if args.max_cells is not None
               else f"창 폭(대사 {FIELD_CELLS}칸 · 메뉴 {MENU_CELLS}칸)")
    if hard:
        print(f"\n[!] {lim_txt}을 넘겨 확실히 잘리는 줄 {len(hard):,}개")
        for name, idx, w, line in sorted(hard, key=lambda x: -x[2])[:args.limit]:
            print(f"  {w}칸  {name} #{idx:04d}  {line}")
        if len(hard) > args.limit:
            print(f"  (…외 {len(hard) - args.limit:,}건)")
    else:
        print(f"\n{lim_txt}을 넘기는 줄 없음 "
              "(`이름／읽기` 색인 데이터는 검사에서 뺍니다)")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
