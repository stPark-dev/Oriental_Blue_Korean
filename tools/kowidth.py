#!/usr/bin/env python3
"""번역문이 원문보다 넓지 않은지 검사합니다.

이 게임은 **모든 글자가 8픽셀 폭 칸 하나**를 씁니다 (작은 폰트 8×8,
큰 폰트 8×16 — 높이만 다릅니다). 한글은 16×16 이라 **칸 두 개**를 씁니다.

그래서 글자 수를 줄여도 폭은 넘칠 수 있습니다::

    こうげき力   5글자 = 5칸
    공격력을     4글자 = 8칸   <- 더 넓다

메시지 창 폭을 넘기면 글자가 잘리므로, 삽입 전에 원문 폭과 비교합니다.

    python3 tools/kowidth.py            # script/ko 전체 검사
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


MIN_LIMIT = 6          # 한글 두 자도 못 넣는 표는 폭 규칙을 적용하지 않습니다


def table_limit(ja_texts: list[str]) -> int:
    """이 표의 창 폭 — 원문이 실제로 쓴 가장 넓은 줄.

    원문은 그 창에 맞춰 쓰였으므로, 그보다 넓은 줄은 잘립니다.
    """
    best = 0
    for text in ja_texts:
        if is_index_data(text):
            continue
        for line in text.split("\n"):
            if line.strip():
                best = max(best, cells(line))
    return best


def limit_samples(ja_texts: list[str], limit: int) -> int:
    """한계에 도달한 원문 줄이 몇 개인지. 1 이면 그 한계는 믿기 어렵습니다."""
    n = 0
    for text in ja_texts:
        if is_index_data(text):
            continue
        n += sum(1 for line in text.split("\n")
                 if line.strip() and cells(line) == limit)
    return n


def line_cells(text: str) -> list[int]:
    return [cells(line) for line in text.split("\n")]


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
    ap.add_argument("--strict", action="store_true",
                    help="잘리는 줄이 있으면 1 로 끝냅니다 (기본은 보고만)")
    ap.add_argument("--max-cells", type=int, default=0,
                    help="한 줄 절대 한계. 0 이면 표마다 원문이 실제로 쓴 "
                         "가장 넓은 줄을 한계로 씁니다 (본문 표는 대개 20칸).")
    args = ap.parse_args()

    total = over = 0
    shown = 0
    hard: list[tuple[str, int, int, str, int, bool]] = []
    for path in sorted(glob.glob(os.path.join(args.ko, "*.txt"))):
        name = os.path.basename(path)
        ja_path = os.path.join(args.ja, name)
        if not os.path.exists(ja_path):
            continue
        ja_entries = ScriptFile.read(ja_path).entries
        ja = {e.index: e.text for e in ja_entries}
        # 원문은 그 창에 맞춰 쓰였습니다. 원문이 쓴 가장 넓은 줄이 곧 창 폭입니다.
        texts = [e.text for e in ja_entries]
        limit = args.max_cells or table_limit(texts)
        if limit < MIN_LIMIT:
            continue
        thin = not args.max_cells and limit_samples(texts, limit) == 1
        for e in ScriptFile.read(path).entries:
            if not e.text.strip():
                continue
            total += 1
            if not is_index_data(e.text):
                lines = e.text.split("\n")
                for ln, w in too_wide(ja.get(e.index, ""), e.text, limit):
                    hard.append((name, e.index, w, lines[ln], limit, thin))
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

    if hard:
        print(f"\n[!] 창 폭을 넘겨 확실히 잘리는 줄 {len(hard):,}개")
        print("    `python3 tools/koflow.py` 로 줄바꿈만 옮겨 고칠 수 있는지 보세요.")
        for name, idx, w, line, lim, thin in sorted(
                hard, key=lambda x: x[4] - x[2])[:args.limit]:
            print(f"  {w}칸 > {lim}칸{'?' if thin else ' '} {name} #{idx:04d}  {line}")
        if len(hard) > args.limit:
            print(f"  ... 외 {len(hard) - args.limit:,}줄")
        if any(h[5] for h in hard):
            print("    (`?` 는 한계를 정한 원문 줄이 하나뿐이라 믿기 어려운 표입니다)")
    else:
        print("\n창 폭을 넘기는 줄 없음 "
              "(`이름／읽기` 색인 데이터는 검사에서 뺍니다)")
    return 1 if (hard and args.strict) else 0


if __name__ == "__main__":
    sys.exit(main())
