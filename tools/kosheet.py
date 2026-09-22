#!/usr/bin/env python3
"""표 하나를 옮길 때 필요한 것을 한 파일에 모읍니다.

번역하면서 매번 손이 가는 일이 셋입니다.

  1. 이 줄에 한글 몇 자가 들어가나 — 26칸 한도, 한글은 한 자에 2칸
  2. 이 문장에 든 아이템 이름을 뭐라고 옮기기로 했더라
  3. 앞뒤 대사가 뭐였나 — 말투를 맞추려면 필요합니다

셋을 미리 뽑아 `build/sheet/` 에 둡니다. **번역은 하지 않습니다.**

    python3 tools/kosheet.py            # 손대지 않은 표부터
    python3 tools/kosheet.py F2F2FC     # 표 하나만
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kogloss  # noqa: E402
import koprog  # noqa: E402
import kowidth  # noqa: E402
from script_io import ScriptFile  # noqa: E402

LIMIT = 26                       # 메시지 창 폭 (8픽셀 칸)
TAG_RE = re.compile(r"<\$[0-9A-Fa-f]{2,4}>|<F\d:[0-9A-Fa-f]{2}>")
JP_RE = re.compile(r"[぀-ヿ一-鿿]")
OUT_DIR = "build/sheet"

# 표 전체를 빼지는 않지만 주의가 필요한 곳. 시트 맨 위에 띄웁니다.
NOTES = {
    "DF3908": (
        "**남은 항목 대부분은 번역 대상이 아닙니다.** 대사가 아니라 "
        "이름 입력 화면의 가나 문자판(`あいうえお…`)과 구분선(`ーーーー`)"
        "입니다. 실제 문자 선택 그리드는 롬 `0x08ADEC`·`0x08B142` 의 "
        "Shift-JIS 이진 표라 문자열표와 별개이고, 한글 이름 입력으로 "
        "바꾸는 것은 그리드 재작성과 이름 버퍼 처리가 필요한 **역공학 "
        "과제**입니다. docs/HANDOFF.md 참고."
    ),
}


def budget(line: str) -> int:
    """이 줄에 들어가는 한글 글자 수.

    가나·한자는 한글이 됩니다 (한 자에 2칸). 나머지 기호·공백·숫자는
    번역해도 그대로 남으므로 미리 자리를 뺍니다.
    """
    kept = TAG_RE.sub("", line)                       # 제어 코드는 0칸
    kept = "".join(c for c in kept if not JP_RE.match(c))
    return max(0, (LIMIT - kowidth.cells(kept)) // 2)


def show_width(text: str) -> int:
    """터미널에서 차지하는 칸. 전각 문자는 두 칸입니다."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1
               for c in text)


def pad(text: str, width: int) -> str:
    """전각을 감안해 오른쪽을 채웁니다."""
    return text + " " * max(1, width - show_width(text))


def terms(text: str, gloss: dict[str, str]) -> list[tuple[str, str]]:
    """문장에 든 아이템 이름을 나온 순서대로."""
    found = [(text.index(t), t, std) for t, std in gloss.items() if t in text]
    return [(t, std) for _, t, std in sorted(found)]


def neighbours(rows: dict[int, str], idx: int) -> tuple[str, str]:
    """앞뒤로 가장 가까운 **번역된** 항목."""
    keys = sorted(rows)
    before = after = ""
    for k in reversed([k for k in keys if k < idx]):
        if rows[k].strip():
            before = rows[k]
            break
    for k in [k for k in keys if k > idx]:
        if rows[k].strip():
            after = rows[k]
            break
    return before, after


@dataclass
class Entry:
    index: int
    source: str
    budgets: list[int]
    terms: list[tuple[str, str]]
    before: str
    after: str


def collect(table: str, ja_dir: str, ko_dir: str,
            gloss: dict[str, str]) -> list[Entry]:
    ja = ScriptFile.read(os.path.join(ja_dir, f"t{table}.txt"))
    ko_path = os.path.join(ko_dir, f"t{table}.txt")
    ko = ({e.index: e.text for e in ScriptFile.read(ko_path).entries}
          if os.path.exists(ko_path) else {})
    out = []
    for e in ja.entries:
        if not e.text.strip() or not koprog.translatable(e.text):
            continue
        if ko.get(e.index, "").strip():
            continue
        before, after = neighbours(ko, e.index)
        out.append(Entry(e.index, e.text,
                         [budget(l) for l in e.text.split("\n")],
                         terms(e.text, gloss), before, after))
    return out


def render(table: str, entries: list[Entry]) -> str:
    lines = [f"# {table} — 남은 {len(entries)}항목", ""]
    if table in NOTES:
        lines += ["> ⚠️ " + NOTES[table], ""]
    lines += ["각 줄 오른쪽 숫자가 **한글 최대 글자 수**입니다 "
              f"(창 폭 {LIMIT}칸, 한글 한 자 = 2칸).", ""]
    for e in entries:
        lines.append(f"## {e.index:04d}")
        if e.before:
            lines.append(f"앞: {e.before.splitlines()[-1]}")
        lines.append("")
        lines.append("```")
        for src, b in zip(e.source.split("\n"), e.budgets):
            lines.append(pad(src, 44) + f"| 한글 {b}자")
        lines.append("```")
        if e.terms:
            lines.append("용어: " + " · ".join(f"{t} → {s}" for t, s in e.terms))
        if e.after:
            lines.append(f"뒤: {e.after.splitlines()[0]}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="번역 작업 시트 생성")
    ap.add_argument("table", nargs="?", help="표 이름 (예: F2F2FC). 없으면 전부")
    ap.add_argument("--ja", default="script/ja")
    ap.add_argument("--ko", default="script/ko")
    ap.add_argument("--out", default=OUT_DIR)
    args = ap.parse_args()

    if not os.path.isdir(args.ja):
        print(f"[!] 원문이 없습니다: {args.ja} — `make script` 를 먼저 돌리세요")
        return 1
    gloss = kogloss.load_glossary(args.ja, args.ko)
    os.makedirs(args.out, exist_ok=True)

    if args.table:
        tables = [args.table.upper()]
    else:
        tables = []
        for name in sorted(os.listdir(args.ja)):
            if not name.startswith("t") or not name.endswith(".txt"):
                continue
            t = name[1:-4]
            if t not in koprog.EXCLUDED:
                tables.append(t)

    made = total = 0
    for t in tables:
        entries = collect(t, args.ja, args.ko, gloss)
        if not entries:
            continue
        path = os.path.join(args.out, f"t{t}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(render(t, entries))
        made += 1
        total += len(entries)
    print(f"시트 {made}개 / 항목 {total:,} -> {args.out}/")
    print("원문이 들어가므로 커밋하지 않습니다 (build/ 는 .gitignore 대상)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
