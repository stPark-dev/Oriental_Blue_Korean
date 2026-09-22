#!/usr/bin/env python3
"""번역문 전수 감사.

실기에서 터지는 버그는 대부분 눈으로 안 보입니다. 제어 코드가 하나 빠지면
메시지가 멈추고, `<$1F>` 뒤의 printf 지정자가 바뀌면 엉뚱한 값이 찍히거나
튕깁니다. 줄 수가 달라지면 창 밖으로 밀립니다. 전부 전수로 잡습니다.

    python3 tools/koaudit.py            # script/ja 와 script/ko 를 통째로
    python3 tools/koaudit.py DEC698     # 표 하나만

`make width` 가 보는 **폭**과는 겹치지 않습니다. 이쪽은 구조만 봅니다.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import script_io  # noqa: E402

TAG_RE = re.compile(r"<(\$[0-9A-Fa-f]{2,4}|[A-Za-z]\d:[0-9A-Fa-f]{2}|[A-Z]+)>")
# `<$1F>` 뒤에 붙는 printf 지정자. 원문 그대로여야 합니다.
PRINTF_RE = re.compile(r"<\$1F>([-+ #0-9.]*[a-zA-Z])")
# 이름이 들어가는 자리 — 받침을 미리 알 수 없어 조사를 병기해야 합니다.
NAME_RE = re.compile(r"<\$1[24]>|<\$1F>s")
JOSA_PAIRS = {"은": "（는）", "는": "（은）", "을": "（를）", "를": "（을）",
              "이": "（가）", "가": "（이）", "와": "（과）", "과": "（와）",
              "아": "（야）", "야": "（아）"}
JOSA_RO = "（으）로"


def tags(text: str) -> list[str]:
    """제어 코드를 나온 순서대로."""
    return TAG_RE.findall(text)


def tag_issues(ja: str, ko: str) -> list[str]:
    a, b = tags(ja), tags(ko)
    if a == b:
        return []
    from collections import Counter
    ca, cb = Counter(a), Counter(b)
    out = []
    for t in sorted((ca - cb).elements()):
        out.append(f"제어 코드 <{t}> 가 빠졌습니다")
    for t in sorted((cb - ca).elements()):
        out.append(f"제어 코드 <{t}> 가 더 들어갔습니다")
    if not out:
        out.append(f"제어 코드 순서가 다릅니다: {a} -> {b}")
    return out


def line_issues(ja: str, ko: str) -> list[str]:
    """줄 수 차이. 줄어든 쪽이 더 위험합니다.

    원문보다 **줄면** 그 줄이 안 지워져 이전 글자가 남습니다. **늘면** 창
    용량을 넘지 않는지 봐야 합니다 (원문에도 13줄짜리가 있어 여러 줄은 됩니다).
    """
    a, b = ja.count("\n") + 1, ko.count("\n") + 1
    if a == b:
        return []
    if b < a:
        return [f"줄이 줄었습니다 ({a}→{b}): 그 줄에 이전 글자가 남습니다"]
    return [f"줄이 늘었습니다 ({a}→{b}): 창 용량 확인 필요"]


def printf_issues(ja: str, ko: str) -> list[str]:
    a, b = PRINTF_RE.findall(ja), PRINTF_RE.findall(ko)
    if a == b:
        return []
    out = []
    for i in range(max(len(a), len(b))):
        x = a[i] if i < len(a) else None
        y = b[i] if i < len(b) else None
        if x != y:
            out.append(f"printf 지정자가 다릅니다: {i + 1}번째 %{x} -> %{y}")
    return out


def josa_issues(ko: str) -> list[str]:
    """이름 코드 바로 뒤에 맨 조사가 오면 잡습니다."""
    out = []
    for m in NAME_RE.finditer(ko):
        rest = ko[m.end():]
        if rest.startswith(JOSA_RO):
            continue
        if not rest:
            continue
        head = rest[0]
        if head not in JOSA_PAIRS:
            continue
        if rest[1:].startswith(JOSA_PAIRS[head]):
            continue
        # 뒤에 한글이 이어지면 조사가 아니라 낱말입니다 (「<$12>과자」 의 '과').
        if len(rest) > 1 and "가" <= rest[1] <= "힣":
            continue
        out.append(f"조사 병기가 없습니다: {m.group(0)}{head}"
                   f" (→ {m.group(0)}{head}{JOSA_PAIRS[head]})")
    return out


def pad_tail(ja: str, ko: str) -> str:
    """원문 끝의 공백 줄을 번역문에도 붙입니다.

    원문은 줄 끝에 전각 공백만 있는 줄을 두어 **앞 화면을 지웁니다.** 번역문에서
    빠뜨리면 그 줄에 이전 글자가 그대로 남습니다.
    """
    if not ko.strip():
        return ko
    a, b = ja.split("\n"), ko.split("\n")
    if len(b) >= len(a):
        return ko
    tail = []
    for line in reversed(a):
        if line.strip("\u3000 ") != "":
            break
        tail.append(line)
    if not tail:
        return ko
    need = min(len(a) - len(b), len(tail))
    return "\n".join(b + list(reversed(tail))[len(tail) - need:])


def is_warning(msg: str) -> bool:
    """줄이 늘어난 것은 창 용량만 보면 되는 **확인 대상**입니다.

    원문에도 13줄짜리가 있어 여러 줄은 문제가 안 됩니다. 나머지는 오류입니다.
    """
    return msg.startswith("줄이 늘었습니다")


def check_entry(ja: str, ko: str) -> list[str]:
    """번역한 항목 하나를 봅니다. 빈 번역은 원문 유지이므로 건너뜁니다."""
    if not ko.strip():
        return []
    return (tag_issues(ja, ko) + line_issues(ja, ko)
            + printf_issues(ja, ko) + josa_issues(ko))


def fix_file(ja_path: str, ko_path: str) -> int:
    """되살릴 수 있는 것만 고칩니다 — 끝 공백 줄, `<$20>` 표기. 고친 수."""
    sf = script_io.ScriptFile.read(ko_path)
    ja = {e.index: e.text for e in script_io.ScriptFile.read(ja_path).entries}
    n = 0
    for e in sf.entries:
        before = e.text
        if "<$20>" in e.text:              # 반각 공백과 바이트가 같습니다
            e.text = e.text.replace("<$20>", " ")
        if e.index in ja:
            e.text = pad_tail(ja[e.index], e.text)
        if e.text != before:
            n += 1
    if n:
        sf.write(ko_path)
    return n


def audit(ja_dir: str, ko_dir: str, only: str = "") -> list[tuple[str, int, str]]:
    """(표, 항목 번호, 문제) 목록. 순서는 파일·번호순입니다."""
    out = []
    for name in sorted(os.listdir(ja_dir)):
        if not name.startswith("t") or not name.endswith(".txt"):
            continue
        if only and only.upper() not in name.upper():
            continue
        ko_path = os.path.join(ko_dir, name)
        if not os.path.exists(ko_path):
            continue
        for ja, ko in script_io.pair(os.path.join(ja_dir, name), ko_path):
            if ko is None:
                continue
            for msg in check_entry(ja.text, ko.text):
                out.append((name[1:-4], ja.index, msg))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="번역문 전수 감사")
    ap.add_argument("only", nargs="?", default="", help="표 이름 일부 (예: DEC698)")
    ap.add_argument("--ja", default="script/ja")
    ap.add_argument("--ko", default="script/ko")
    ap.add_argument("--fix", action="store_true",
                    help="되살릴 수 있는 것만 고칩니다 (끝 공백 줄, <$20> 표기)")
    args = ap.parse_args()

    if not os.path.isdir(args.ja):
        print(f"[!] 원문이 없습니다: {args.ja} — `make script` 를 먼저 돌리세요")
        return 1
    if args.fix:
        total = 0
        for name in sorted(os.listdir(args.ja)):
            if not name.startswith("t") or not name.endswith(".txt"):
                continue
            if args.only and args.only.upper() not in name.upper():
                continue
            ko_path = os.path.join(args.ko, name)
            if os.path.exists(ko_path):
                total += fix_file(os.path.join(args.ja, name), ko_path)
        print(f"{total}개 항목을 고쳤습니다")
    found = audit(args.ja, args.ko, args.only)
    if not found:
        print("구조 문제 없음 (제어 코드·줄 수·printf 지정자·조사 병기)")
        return 0
    from collections import Counter
    kinds = Counter(m.split(":")[0].split(" (")[0] for _, _, m in found)
    for table, idx, msg in found:
        print(f"{table} [{idx}] {msg}")
    print()
    for kind, n in kinds.most_common():
        print(f"  {kind} {n}건")
    bad = [f for f in found if not is_warning(f[2])]
    print(f"  합계 {len(found)}건 (오류 {len(bad)} · 확인 {len(found) - len(bad)})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
