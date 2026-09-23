#!/usr/bin/env python3
"""창 폭을 넘는 줄을 단어 사이에서 쪼갭니다.

한글은 한 자가 **칸 두 개**(16픽셀)이고 원문 일본어는 한 자가 한 칸(8픽셀)
입니다. 그래서 글자 수를 줄여도 줄이 쉽게 창 밖으로 나갑니다.

폭 한계는 `kowidth.table_limit` 이 줍니다 — **필드 대사 20칸 · 메뉴/기록
28칸**. 넘기면 음절이 반으로 찢어져 오른쪽 칸이 다음 줄로 밀리고, 뒤 내용이
통째로 어긋납니다.

**문장을 줄이는 것이 먼저입니다** (`tools/kofit.py`). 이 도구는 줄여도
안 들어가거나 아직 손대지 못한 줄을 기계적으로 막아 두는 안전망입니다.
문장을 줄이면 쪼갠 자리가 저절로 사라집니다.

**이 도구가 바꾸는 것은 「단어 사이 구분자 하나가 줄바꿈이 된다」뿐입니다.**
글자도, 들여쓰기도, 줄 끝 전각공백(화면 지우기 장치)도, 반각·전각 구분도
그대로 둡니다.

건드리지 않는 것:

- **제어 코드가 든 줄.** `<$10>` 같은 코드의 뜻을 아직 모르므로, 글자 대비
  자리가 바뀌지 않게 통째로 비켜 갑니다.
- **원문이 한 줄인 항목.** 이름·낱말·메뉴 문구라서 쪼개면 칸이 깨집니다
  (`와카나　공주` -> `와카나` / `공주`).
- **원문 줄 수가 사실상 정해진 표.** 높이가 고정된 칸입니다. 그 표의 원문
  최대 줄 수를 넘기지 않습니다.

    python3 tools/koflow.py                   # 쪼갤 수 있는 항목 보고
    python3 tools/koflow.py --write --grow 8  # 실제로 반영
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kowidth  # noqa: E402
from script_io import ScriptFile  # noqa: E402

TAG_RE = re.compile(r"<\$[0-9A-Fa-f]{2,3}>")
GAP_RE = re.compile(r"[ 　]+")
# 표의 원문 줄 수가 이 가짓수 이하로만 나타나면 「높이가 정해진 칸」으로 봅니다.
FIXED_HEIGHT_KINDS = 2


def pieces(line: str) -> tuple[str, list[str], list[str], str]:
    """`(앞 공백, 단어들, 단어 사이 구분자들, 뒤 공백)`.

    구분자를 그대로 들고 있어야 반각 공백이 전각으로 둔갑하지 않습니다.
    줄 끝 공백은 화면을 지우는 장치라 반드시 살려야 합니다 (docs/HANDOFF.md).
    """
    body = line.strip(" 　")
    if not body:
        return line, [], [], ""
    lead = line[:len(line) - len(line.lstrip(" 　"))]
    trail = line[len(line.rstrip(" 　")):]
    raw_words, raw_gaps = GAP_RE.split(body), GAP_RE.findall(body)
    words, gaps = [raw_words[0]], []
    for gap, word in zip(raw_gaps, raw_words[1:]):
        if len(gap) == 1:
            gaps.append(gap)
            words.append(word)
        else:
            # 여러 칸 띄우기는 단어 사이가 아니라 자리 맞추기입니다 (비문의
            # 오른쪽 정렬 등). 끊으면 정렬이 무너지므로 한 덩어리로 둡니다.
            words[-1] += gap + word
    return lead, words, gaps, trail


def pack(widths: list[int], gaps: list[int], n: int) -> list[int] | None:
    """단어를 **순서 그대로** n 줄로 나눌 때, 각 줄이 시작하는 단어 번호.

    `widths[i]` 는 단어 i 의 칸 수, `gaps[i]` 는 단어 i 와 i+1 사이 구분자의
    칸 수입니다. 가장 넓은 줄이 최소가 되는 나눔을 고릅니다. 못 나누면 `None`.
    """
    m = len(widths)
    if n <= 0 or m < n:
        return None

    def width(i: int, j: int) -> int:
        """단어 i..j-1 을 한 줄에 놓았을 때의 칸 수."""
        return sum(widths[i:j]) + sum(gaps[i:j - 1])

    inf = float("inf")
    dp = [[inf] * (n + 1) for _ in range(m + 1)]
    cut = [[0] * (n + 1) for _ in range(m + 1)]
    dp[0][0] = 0
    for j in range(1, n + 1):
        for i in range(j, m + 1):
            for k in range(j - 1, i):
                if dp[k][j - 1] == inf:
                    continue
                v = max(dp[k][j - 1], width(k, i))
                if v < dp[i][j]:
                    dp[i][j], cut[i][j] = v, k
    if dp[m][n] == inf:
        return None
    starts, i = [], m
    for j in range(n, 0, -1):
        i = cut[i][j]
        starts.append(i)
    return list(reversed(starts))


def join(words: list[str], gaps: list[str], start: int, end: int) -> str:
    """단어 start..end-1 을 원래 구분자로 이어 붙입니다."""
    out = words[start]
    for i in range(start + 1, end):
        out += gaps[i - 1] + words[i]
    return out


def split_line(line: str, limit: int, most: int) -> list[str] | None:
    """한 줄을 `limit` 안에 들도록 **최소 개수**로 쪼갭니다 (최대 `most` 줄).

    앞뒤 공백과 구분자를 그대로 옮기므로, 바뀌는 것은 구분자 하나가 줄바꿈이
    되는 것뿐입니다. 못 하면 `None`.
    """
    lead, words, gaps, trail = pieces(line)
    if len(words) < 2 or most < 2:
        return None
    w = [kowidth.cells(x) for x in words]
    g = [kowidth.cells(x) for x in gaps]
    pad = max(kowidth.cells(lead), kowidth.cells(trail))
    if max(w) + pad > limit:
        return None                      # 단어 하나가 이미 한계를 넘습니다
    for n in range(2, min(most, len(words)) + 1):
        starts = pack(w, g, n)
        if starts is None:
            continue
        out = []
        for j, s in enumerate(starts):
            end = starts[j + 1] if j + 1 < n else len(words)
            text = join(words, gaps, s, end)
            if j == 0:
                text = lead + text
            if j == n - 1:
                text += trail
            out.append(text)
        if all(kowidth.cells(x) <= limit for x in out):
            return out
    return None


def reflow(text: str, limit: int, grow: int) -> str | None:
    """넘치는 줄을 쪼갠 본문. 손댈 게 없거나 못 하면 `None`.

    `grow` 는 이 항목에서 늘려도 되는 줄 수입니다. 0 이면 아무것도 안 합니다.
    """
    out: list[str] = []
    left = grow
    fixed = False
    for line in text.split("\n"):
        if (left <= 0 or not line.strip() or TAG_RE.search(line)
                or kowidth.cells(line) <= limit):
            out.append(line)
            continue
        parts = split_line(line, limit, left + 1)
        if parts is None:
            out.append(line)             # 이 줄은 번역문을 줄여야 합니다
            continue
        left -= len(parts) - 1
        out += parts
        fixed = True
    return "\n".join(out) if fixed else None


def allowed_grow(ja_counts: dict[int, int], ja_lines: int, ko_lines: int,
                 grow: int) -> int:
    """이 항목에서 늘려도 되는 줄 수.

    - **원문이 한 줄이면 0.** 이름·낱말·메뉴 문구라 한 칸에 그려집니다.
    - **표의 원문 줄 수가 몇 가지뿐이면** 높이가 정해진 칸입니다. 그 표의
      원문 최대 줄 수를 넘기지 않습니다 — 폭 한계를 표별 원문에서 얻는 것과
      같은 근거입니다.
    - 그 밖에는 흐르는 본문이므로 `grow` 만큼 허용합니다.
    """
    if ja_lines <= 1:
        return 0
    if 0 < len(ja_counts) <= FIXED_HEIGHT_KINDS:
        return max(0, min(grow, max(ja_counts) - ko_lines))
    return grow


def line_counts(entries: list) -> dict[int, int]:
    """원문 항목의 줄 수 분포. 색인 데이터는 뺍니다."""
    out: dict[int, int] = {}
    for e in entries:
        if e.text.strip() and not kowidth.is_index_data(e.text):
            k = len(e.text.split("\n"))
            out[k] = out.get(k, 0) + 1
    return out


def header_of(path: str) -> str:
    """파일 맨 앞의 `# ` 주석. 표마다 손으로 적어 둔 메모를 지킵니다."""
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.startswith("#"):
                break
            out.append(line[1:].strip())
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="창 폭을 넘는 줄 쪼개기")
    ap.add_argument("--ja", default="script/ja")
    ap.add_argument("--ko", default="script/ko")
    ap.add_argument("--write", action="store_true", help="실제로 파일을 고칩니다")
    ap.add_argument("--list", type=int, default=20,
                    help="손봐야 할 항목을 몇 개까지 보여줄지")
    ap.add_argument("--grow", type=int, default=0,
                    help="항목마다 늘려도 되는 줄 수 (기본 0 = 아무것도 안 함). "
                         "원문 줄 수가 여러 가지인 표에만 적용됩니다.")
    args = ap.parse_args()

    moved = stuck = 0
    touched: list[tuple[str, int]] = []
    worst: list[tuple[int, int, str, int, str]] = []
    for path in sorted(glob.glob(os.path.join(args.ko, "*.txt"))):
        name = os.path.basename(path)
        ja_path = os.path.join(args.ja, name)
        if not os.path.exists(ja_path):
            continue
        ja_entries = ScriptFile.read(ja_path).entries
        limit = kowidth.table_limit(name)
        ja = {e.index: e.text for e in ja_entries}
        counts = line_counts(ja_entries)

        sf = ScriptFile.read(path)
        n = 0
        for e in sf.entries:
            if not e.text.strip() or kowidth.is_index_data(e.text):
                continue
            lines = e.text.split("\n")
            if max((kowidth.cells(l) for l in lines if l.strip()),
                   default=0) <= limit:
                continue
            grow = allowed_grow(counts,
                                len(ja.get(e.index, "").split("\n")),
                                len(lines), args.grow)
            out = reflow(e.text, limit, grow)
            if out is not None:
                moved += 1
                n += 1
                if args.write:
                    e.text = out
            # 부분만 고쳐졌어도 아직 잘리면 손봐야 할 항목입니다.
            over = [l for l in (out or e.text).split("\n")
                    if l.strip() and kowidth.cells(l) > limit]
            if over:
                stuck += 1
                widest = max(over, key=kowidth.cells)
                worst.append((kowidth.cells(widest) - limit,
                              kowidth.cells(widest), name, e.index, widest))
        if n:
            touched.append((name, n))
            if args.write:
                sf.write(path, header_of(path))

    touched.sort(key=lambda x: -x[1])
    for name, n in touched[:20]:
        print(f"  {name}  {n:3}항목")
    if len(touched) > 20:
        print(f"  ... 외 {len(touched) - 20}개 표")

    print(f"\n{'쪼갰습니다' if args.write else '쪼갤 수 있습니다'}: "
          f"{moved:,}항목 / 표 {len(touched)}개")
    if not args.write:
        print("실제로 고치려면 --write 를 붙이세요")

    if stuck:
        print(f"\n[!] 아직 창 밖으로 나가는 항목 {stuck:,}개 "
              "— 번역문 자체를 줄여야 합니다")
        worst.sort(reverse=True)
        for _, wide, name, idx, line in worst[:args.list]:
            print(f"  {wide:2}칸  {name} #{idx:04d}  {line}")
        if len(worst) > args.list:
            print(f"  ... 외 {len(worst) - args.list:,}항목")
    return 0


if __name__ == "__main__":
    sys.exit(main())
