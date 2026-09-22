#!/usr/bin/env python3
"""창 폭을 넘기는 줄을 찾아 주고, 줄인 문장으로 안전하게 바꿔 넣습니다.

`kowidth.py` 가 「넘친다」를, `koflow.py` 가 「쪼개서 되는 것」을 맡습니다.
이 도구는 그 둘로 안 되는 것 — **글을 줄여야 하는 자리**를 돕습니다.

    python3 tools/kofit.py list                 # 고칠 문장 목록 (많이 나온 순)
    python3 tools/kofit.py list --start 200 --count 100
    python3 tools/kofit.py apply 고침.json      # 줄인 문장으로 바꿔 넣기
    python3 tools/kofit.py rules                # 정형 축약만 기계로 (시험)
    python3 tools/kofit.py rules --write

창 폭은 `kowidth.table_limit` 이 정합니다 — **표마다 원문이 실제로 쓴
가장 넓은 줄**입니다. 같은 문장이 여러 표에 있으면 가장 좁은 창에
맞춥니다.

## 왜 문장 단위인가

같은 문장이 여러 표에 되풀이됩니다. 한 번 줄여 두면 나오는 곳마다 같이
고쳐지고, 표기도 저절로 통일됩니다.

## apply 가 막아 주는 것

바꾸기 전에 줄마다 검사하고, **걸린 것만 빼고** 나머지를 넣습니다.

  - 제어 코드(`<$XX>`)의 개수와 순서가 같은가
  - 줄바꿈이 들어가지 않았는가 (줄 수가 변하면 화면이 깨집니다)
  - 줄 끝 전각공백 꼬리가 그대로인가 (화면을 지우는 장치입니다)
  - 줄인 쪽이 정말 그 표의 창 폭 안에 들어오는가

고침 파일은 `{"원래 줄": "줄인 줄", ...}` 꼴의 JSON(UTF-8)입니다.
"""
from __future__ import annotations

import argparse
import collections
import glob
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kowidth  # noqa: E402
from script_io import ScriptFile  # noqa: E402

SP = "　"
TAG = re.compile(r"<\$[0-9A-Fa-f]{2,3}>")

# 뜻도 말투도 그대로인 축약만. 판단이 필요한 것은 손으로 합니다.
RULES: list[tuple[str, str]] = [
    ("손에" + SP + "넣었습니다", "얻었습니다"),
    ("손에" + SP + "넣었다", "얻었다"),
    ("손에" + SP + "넣었어", "얻었어"),
    ("하고" + SP + "있습니다", "합니다"),
    ("하고" + SP + "있어요", "해요"),
    ("하고" + SP + "있다", "한다"),
    ("하고" + SP + "있어", "해"),
    ("하고" + SP + "있는", "하는"),
    ("것입니다", "겁니다"),
    ("것이에요", "거예요"),
    ("것이다", "거다"),
    ("것이" + SP + "좋다", "게" + SP + "좋다"),
    ("것이" + SP + "좋아", "게" + SP + "좋아"),
    ("해" + SP + "주십시오", "해" + SP + "주세요"),
    ("그러면", "그럼"),
    ("무엇을", "뭘"),
    ("무엇이", "뭐가"),
    ("무엇인가", "뭔가"),
    ("여기는", "여긴"),
    ("저기는", "저긴"),
    ("거기는", "거긴"),
    ("이것은", "이건"),
    ("그것은", "그건"),
    ("저것은", "저건"),
    ("이것이", "이게"),
    ("그것이", "그게"),
    ("무언가", "뭔가"),
    ("것을", "걸"),
    ("것이", "게"),
    ("것은", "건"),
    ("나는" + SP, "난" + SP),
    ("너는" + SP, "넌" + SP),
    ("저는" + SP, "전" + SP),
    ("우리는", "우린"),
    ("조금", "좀"),
    ("하였", "했"),
    ("에서" + SP, "서" + SP),
    ("너무나", "너무"),
]
# 넣지 않은 것과 이유:
#   에게 -> 께      께는 높임말입니다. 「너에게」가 「너께」가 됩니다.
#   하지만 -> 허나  말투가 예스러워집니다. 인물마다 달라 손으로 봐야 합니다.
#   지금은 -> 이젠  뒤에 「이제」가 또 나오면 겹칩니다.


def overflowing(ja_dir: str = "script/ja", ko_dir: str = "script/ko"):
    """(줄 텍스트, 창 폭, 나온 횟수, 원문 줄) 목록. 많이 나온 순."""
    count: collections.Counter = collections.Counter()
    limit_of: dict[str, int] = {}
    source_of: dict[str, str] = {}
    for path in sorted(glob.glob(os.path.join(ko_dir, "*.txt"))):
        name = os.path.basename(path)
        japath = os.path.join(ja_dir, name)
        if not os.path.exists(japath):
            continue
        ja_entries = ScriptFile.read(japath).entries
        ja = {e.index: e.text for e in ja_entries}
        limit = kowidth.table_limit([e.text for e in ja_entries])
        if limit < kowidth.MIN_LIMIT:
            continue
        for e in ScriptFile.read(path).entries:
            if not e.text.strip() or kowidth.is_index_data(e.text):
                continue
            body = e.text.split("\n")
            src = ja.get(e.index, "").split("\n")
            for ln, _w in kowidth.too_wide(ja.get(e.index, ""), e.text, limit):
                line = body[ln]
                count[line] += 1
                limit_of[line] = min(limit_of.get(line, 99), limit)
                source_of.setdefault(line, src[ln] if ln < len(src) else "")
    return [(t, limit_of[t], n, source_of.get(t, ""))
            for t, n in sorted(count.items(),
                               key=lambda kv: (-kv[1], -kowidth.cells(kv[0])))]


def tail_spaces(s: str) -> int:
    return len(s) - len(s.rstrip(SP))


def check(old: str, new: str, limit: int) -> str | None:
    """바꿔도 되는지. 문제가 없으면 None."""
    if "\n" in new:
        return "줄바꿈이 들어갔습니다"
    if TAG.findall(old) != TAG.findall(new):
        return f"제어 코드가 달라졌습니다 {TAG.findall(old)} -> {TAG.findall(new)}"
    if tail_spaces(old) != tail_spaces(new):
        return "줄 끝 전각공백 개수가 달라졌습니다"
    w = kowidth.cells(new)
    if w > limit:
        return f"아직 {w}칸 (한도 {limit})"
    return None


def apply(fix: dict[str, str], ko_dir: str = "script/ko",
          write: bool = True, ja_dir: str = "script/ja") -> tuple[int, int,
                                                                 list[str]]:
    """(고친 파일 수, 고친 줄 수, 건너뛴 까닭 목록).

    같은 문장이 여러 표에 있으면 **가장 좁은 창**을 기준으로 봅니다.
    """
    limits: dict[str, int] = {}
    for path in sorted(glob.glob(os.path.join(ko_dir, "*.txt"))):
        japath = os.path.join(ja_dir, os.path.basename(path))
        if not os.path.exists(japath):
            continue
        lim = kowidth.table_limit([e.text
                                   for e in ScriptFile.read(japath).entries])
        if lim < kowidth.MIN_LIMIT:
            continue
        for line in io.open(path, encoding="utf-8").read().split("\n"):
            if line in fix:
                limits[line] = min(limits.get(line, 99), lim)

    errs, ok = [], {}
    for old, new in fix.items():
        if old not in limits:
            errs.append(f"찾지 못했습니다: {old!r}")
            continue
        why = check(old, new, limits[old])
        if why:
            errs.append(f"{why}: {old!r} -> {new!r}")
            continue
        ok[old] = new

    files = hits = 0
    for path in sorted(glob.glob(os.path.join(ko_dir, "*.txt"))):
        lines = io.open(path, encoding="utf-8").read().split("\n")
        n = 0
        for i, line in enumerate(lines):
            if line in ok:
                lines[i] = ok[line]
                n += 1
        if n:
            files += 1
            hits += n
            if write:
                io.open(path, "w", encoding="utf-8",
                        newline="\n").write("\n".join(lines))
    return files, hits, errs


def shrink(line: str, limit: int) -> str | None:
    """정형 축약만으로 한도에 맞춰 봅니다. 못 맞추면 None."""
    out = line
    for a, b in RULES:
        if len(b) >= len(a):          # 줄지 않는 규칙은 건너뜁니다
            continue
        while a in out and kowidth.cells(out) > limit:
            before = out
            out = out.replace(a, b, 1)
            if out == before:
                break
    return out if kowidth.cells(out) <= limit and out != line else None


def cmd_list(args) -> int:
    rows = overflowing(args.ja, args.ko)
    total = sum(n for _t, _l, n, _s in rows)
    print(f"넘치는 줄 {total:,}개 / 서로 다른 문장 {len(rows):,}개\n")
    for text, limit, n, src in rows[args.start:args.start + args.count]:
        w = kowidth.cells(text)
        mark = f"{n}회 " if n > 1 else ""
        print(f"[{mark}{w}>{limit}] {text}")
        if w - limit >= 3 and src:
            print(f"    < {src}")
    return 0


def cmd_apply(args) -> int:
    fix = json.load(io.open(args.file, encoding="utf-8"))
    files, hits, errs = apply(fix, args.ko, write=not args.dry,
                              ja_dir=args.ja)
    head = "(시험) " if args.dry else ""
    print(f"{head}문장 {len(fix) - len(errs)}개 -> {hits:,}줄 "
          f"(파일 {files}개)")
    if errs:
        print(f"[!] 건너뛴 {len(errs)}건 — 더 줄여야 합니다")
        for e in errs[:40]:
            print("   ", e)
        if len(errs) > 40:
            print(f"    (…외 {len(errs) - 40}건)")
    return 0


def cmd_rules(args) -> int:
    rows = overflowing(args.ja, args.ko)
    fix = {}
    for text, limit, _n, _s in rows:
        new = shrink(text, limit)
        if new is not None:
            fix[text] = new
    if not fix:
        print("정형 축약으로 해결할 줄이 없습니다")
        return 0
    files, hits, errs = apply(fix, args.ko, write=args.write,
                              ja_dir=args.ja)
    head = "" if args.write else "(시험) "
    print(f"{head}정형 축약으로 {hits:,}줄 해결 (문장 {len(fix)}개 · "
          f"파일 {files}개)")
    for old, new in list(fix.items())[:10]:
        print(f"    {old}\n -> {new}")
    for e in errs[:5]:
        print("   ", e)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="창 폭을 넘긴 줄 고치기")
    ap.add_argument("--ja", default="script/ja")
    ap.add_argument("--ko", default="script/ko")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="고칠 문장 목록")
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--count", type=int, default=100)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("apply", help="고침 JSON 을 넣습니다")
    p.add_argument("file")
    p.add_argument("--dry", action="store_true", help="넣지 않고 검사만")
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("rules", help="정형 축약만 기계로")
    p.add_argument("--write", action="store_true")
    p.set_defaults(func=cmd_rules)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
