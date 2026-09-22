#!/usr/bin/env python3
"""창 폭을 넘는 줄을 단어 경계에서 쪼갭니다.

한글은 한 자가 **칸 두 개**(16픽셀)이고 원문 일본어는 한 자가 한 칸(8픽셀)
입니다. 그래서 글자 수를 줄여도 줄이 쉽게 창 밖으로 나갑니다.

한계는 **표마다 원문이 실제로 쓴 가장 넓은 줄**입니다. 원문은 그 창에 맞춰
쓰였으므로 그보다 넓은 줄은 잘립니다. 본문 표는 대개 20칸(160픽셀)입니다.

지키는 것:

- **글자를 한 자도 바꾸지 않습니다.** 단어 사이 공백에서만 나눕니다.
- **번역자가 잡아 둔 줄바꿈을 살립니다.** 줄끼리 글자를 섞지 않고, 한계를
  넘는 줄만 그 자리에서 여러 줄로 쪼갭니다. 절 단위로 끊어 둔 줄바꿈이
  뭉개지면 읽기가 나빠집니다.
- **제어 코드가 든 줄은 건드리지 않습니다.** `<$10>` 같은 코드의 뜻을 아직
  모르므로, 글자 대비 자리가 바뀌지 않게 통째로 비켜 갑니다.

줄이 늘어납니다. 원문 항목의 줄 수가 1~12 로 전부 나타나므로 메시지 창은
줄 수를 가리지 않지만, `--grow` 로 항목마다 늘릴 수 있는 줄 수를 막아
둡니다. 그래도 안 되는 항목은 손대지 않고 목록으로 보고합니다 — 번역문
자체를 줄여야 하는 것들입니다.

    python3 tools/koflow.py                   # 쪼갤 수 있는 항목 보고
    python3 tools/koflow.py --write --grow 4  # 실제로 반영
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
SEP = "　"          # 번역문이 쓰는 단어 사이 전각 공백 (한 칸)


def tokens(line: str) -> list[str]:
    """단어 목록. 전각·반각 공백 모두 경계로 봅니다."""
    return [t for t in re.split(r"[ 　]", line) if t]


def pack(toks: list[str], n: int) -> tuple[int, list[str]] | None:
    """단어를 **순서 그대로** n 줄로 나눕니다. 가장 넓은 줄이 최소가 되게.

    `(가장 넓은 줄의 칸 수, 줄 목록)`. 단어가 n 개보다 적으면 `None`.
    """
    m = len(toks)
    if m < n or n <= 0:
        return None
    w = [kowidth.cells(t) for t in toks]
    pre = [0] * (m + 1)
    for i, x in enumerate(w):
        pre[i + 1] = pre[i] + x

    def width(i: int, j: int) -> int:
        return pre[j] - pre[i] + (j - i - 1)      # 사이 공백이 한 칸씩

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
    parts, i = [], m
    for j in range(n, 0, -1):
        k = cut[i][j]
        parts.append(SEP.join(toks[k:i]))
        i = k
    return int(dp[m][n]), list(reversed(parts))


def split_line(line: str, limit: int) -> list[str] | None:
    """한 줄을 `limit` 안에 들도록 **최소 개수**로 쪼갭니다. 못 하면 `None`."""
    toks = tokens(line)
    for n in range(1, len(toks) + 1):
        got = pack(toks, n)
        if got is not None and got[0] <= limit:
            return got[1]
    return None


def reflow(text: str, limit: int, grow: int) -> str | None:
    """넘치는 줄을 쪼갠 본문. 손댈 게 없거나 못 하면 `None`.

    `grow` 는 이 항목에서 늘려도 되는 줄 수입니다.
    """
    out: list[str] = []
    extra = 0
    fixed = False
    for line in text.split("\n"):
        if (not line.strip() or TAG_RE.search(line)
                or kowidth.cells(line) <= limit):
            out.append(line)
            continue
        parts = split_line(line, limit)
        if parts is None or extra + len(parts) - 1 > grow:
            out.append(line)             # 이 줄은 번역문을 줄여야 합니다
            continue
        extra += len(parts) - 1
        out += parts
        fixed = True
    return "\n".join(out) if fixed else None


def allowed_grow(ja_lines: int, grow: int) -> int:
    """이 항목에서 늘려도 되는 줄 수.

    **원문이 한 줄이면 0** 입니다. 한 줄짜리는 이름·낱말·메뉴 문구라서
    이름칸 하나에 그려집니다 — 쪼개면 뒷줄이 통째로 사라지거나 칸이 깨집니다.
    원문이 여러 줄이면 흐르는 본문이므로 줄이 늘어도 괜찮습니다.
    """
    return grow if ja_lines > 1 else 0


def table_limit(ja_texts: list[str]) -> int:
    """이 표의 창 폭 — 원문이 실제로 쓴 가장 넓은 줄."""
    best = 0
    for text in ja_texts:
        if kowidth.is_index_data(text):
            continue
        for line in text.split("\n"):
            if line.strip():
                best = max(best, kowidth.cells(line))
    return best


HEADER = ("테이블 0x{table} / 항목 {count}개\n"
          "원문은 script/ja/{name} 를 나란히 놓고 보세요.\n"
          "본문이 비어 있는 항목은 삽입 시 건너뜁니다 (원문 유지).\n"
          "<F3:XX> 같은 서식 태그는 위치를 바꾸지 말고 그대로 두세요.")


def main() -> int:
    ap = argparse.ArgumentParser(description="창 폭을 넘는 줄 쪼개기")
    ap.add_argument("--ja", default="script/ja")
    ap.add_argument("--ko", default="script/ko")
    ap.add_argument("--write", action="store_true", help="실제로 파일을 고칩니다")
    ap.add_argument("--list", type=int, default=20,
                    help="못 고친 항목을 몇 개까지 보여줄지")
    ap.add_argument("--grow", type=int, default=0,
                    help="항목마다 늘려도 되는 줄 수 (기본 0 = 줄 수 유지 = "
                         "아무것도 못 쪼갬). 원문 항목의 줄 수가 1~12 로 전부 "
                         "나타나므로 메시지 창은 줄 수를 가리지 않습니다.")
    args = ap.parse_args()

    moved = stuck = 0
    touched: list[tuple[str, int]] = []
    worst: list[tuple[int, int, str, int, str]] = []
    for path in sorted(glob.glob(os.path.join(args.ko, "*.txt"))):
        name = os.path.basename(path)
        ja_path = os.path.join(args.ja, name)
        if not os.path.exists(ja_path):
            continue
        limit = table_limit([e.text for e in ScriptFile.read(ja_path).entries])
        if not limit:
            continue
        ja = {e.index: e.text
              for e in ScriptFile.read(ja_path).entries}
        sf = ScriptFile.read(path)
        n = 0
        for e in sf.entries:
            if not e.text.strip() or kowidth.is_index_data(e.text):
                continue
            wide = max((kowidth.cells(l) for l in e.text.split("\n")
                        if l.strip()), default=0)
            if wide <= limit:
                continue
            grow = allowed_grow(len(ja.get(e.index, "").split("\n")), args.grow)
            out = reflow(e.text, limit, grow)
            if out is None:
                stuck += 1
                worst.append((wide - limit, wide, name, e.index,
                              max(e.text.split("\n"), key=kowidth.cells)))
                continue
            moved += 1
            n += 1
            if args.write:
                e.text = out
        if n:
            touched.append((name, n))
            if args.write:
                sf.write(path, HEADER.format(table=name[1:-4],
                                             count=len(sf.entries),
                                             name=name))

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
        print(f"\n[!] 쪼개도 안 되는 항목 {stuck:,}개 "
              "— 번역문 자체를 줄여야 합니다")
        worst.sort(reverse=True)
        for _, wide, name, idx, line in worst[:args.list]:
            print(f"  {wide:2}칸  {name} #{idx:04d}  {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
