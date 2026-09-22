#!/usr/bin/env python3
"""같은 원문에 이미 내린 번역을 퍼뜨립니다.

같은 문장이 표 여러 곳에 그대로 나옵니다 — 보물상자 정형문, 가게 인사,
길안내. 한쪽만 번역돼 있으면 다른 쪽은 화면에 원문이 그대로 나오고,
손으로 다시 옮기면 표현이 갈립니다 (실제로 「또 오시길」과
「또 오시기를」이 갈려 있었습니다).

**새로 번역하지 않습니다.** 판단이 필요한 자리는 손대지 않고 남깁니다.
안전하게 복사할 수 있는 것만 봅니다.

    번역이 하나로 굳어 있을 것   갈리면 어느 쪽이 맞는지 모릅니다
    문장이라고 할 만큼 길 것     끝말잇기 낱말 조각(「ず」)은 문맥마다
                                 다르게 옮겨져 있습니다

    python3 tools/kosame.py            # 무엇이 바뀔지 보기만 합니다
    python3 tools/kosame.py --write    # 실제로 채웁니다
"""
from __future__ import annotations

import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import koprog  # noqa: E402
from script_io import ScriptFile  # noqa: E402

MIN_CHARS = 6      # 이보다 짧고 한 줄이면 낱말 조각으로 봅니다


def substantial(text: str) -> bool:
    """문맥 없이 그대로 옮겨도 되는 길이인지."""
    return "\n" in text or "<$" in text or len(text.strip()) >= MIN_CHARS


def load_pairs(ja_dir: str, ko_dir: str) -> list[tuple[str, str]]:
    """(원문, 번역) 쌍을 전부 모읍니다. 번역이 빈 것도 그대로 담습니다."""
    out = []
    for name in sorted(os.listdir(ja_dir)):
        if not name.startswith("t") or not name.endswith(".txt"):
            continue
        ja = ScriptFile.read(os.path.join(ja_dir, name))
        ko_path = os.path.join(ko_dir, name)
        ko = ({e.index: e.text for e in ScriptFile.read(ko_path).entries}
              if os.path.exists(ko_path) else {})
        out.extend((e.text, ko.get(e.index, "")) for e in ja.entries)
    return out


def build(pairs) -> dict[str, str]:
    """복사해도 되는 (원문 -> 번역) 만 남깁니다."""
    seen: dict[str, set] = collections.defaultdict(set)
    for ja, ko in pairs:
        if ja.strip() and ko.strip() and substantial(ja):
            seen[ja].add(ko)
    return {ja: next(iter(v)) for ja, v in seen.items() if len(v) == 1}


def apply(rows, known: dict[str, str]) -> tuple[list[str], int]:
    """비어 있는 번역만 채웁니다. (채운 결과, 채운 수)"""
    out, n = [], 0
    for ja, ko in rows:
        if not ko.strip() and ja in known:
            out.append(known[ja])
            n += 1
        else:
            out.append(ko)
    return out, n


def main() -> int:
    ap = argparse.ArgumentParser(description="같은 원문의 기존 번역을 퍼뜨립니다")
    ap.add_argument("--ja", default="script/ja")
    ap.add_argument("--ko", default="script/ko")
    ap.add_argument("--write", action="store_true", help="실제로 파일을 고칩니다")
    args = ap.parse_args()

    if not os.path.isdir(args.ja):
        print(f"[!] 원문이 없습니다: {args.ja} — `make script` 를 먼저 돌리세요")
        return 1
    known = build(load_pairs(args.ja, args.ko))
    print(f"복사할 수 있는 원문 {len(known):,}가지")

    total = 0
    touched = []
    for name in sorted(os.listdir(args.ja)):
        if not name.startswith("t") or not name.endswith(".txt"):
            continue
        table = name[1:-4]
        if table in koprog.EXCLUDED:
            continue
        ja = ScriptFile.read(os.path.join(args.ja, name))
        ko_path = os.path.join(args.ko, name)
        if not os.path.exists(ko_path):
            continue
        sf = ScriptFile.read(ko_path)
        ko = {e.index: e.text for e in sf.entries}
        rows = [(e.text, ko.get(e.index, "")) for e in ja.entries]
        filled, n = apply(rows, known)
        if not n:
            continue
        total += n
        touched.append((table, n))
        if args.write:
            by_index = {e.index: t for e, t in zip(ja.entries, filled)}
            for e in sf.entries:
                if e.index in by_index:
                    e.text = by_index[e.index]
            sf.write(ko_path,
                     f"테이블 0x{table} / 항목 {len(sf.entries)}개\n"
                     f"원문은 script/ja/{name} 를 나란히 놓고 보세요.\n"
                     "본문이 비어 있는 항목은 삽입 시 건너뜁니다 (원문 유지).\n"
                     "<F3:XX> 같은 서식 태그는 위치를 바꾸지 말고 그대로 두세요.")

    touched.sort(key=lambda x: -x[1])
    for table, n in touched[:20]:
        print(f"  {table}  {n:3}항목")
    if len(touched) > 20:
        print(f"  ... 외 {len(touched) - 20}개 표")
    print(f"\n{'채웠습니다' if args.write else '채울 수 있습니다'}: "
          f"{total:,}항목 / 표 {len(touched)}개")
    if not args.write:
        print("실제로 고치려면 --write 를 붙이세요")
    return 0


if __name__ == "__main__":
    sys.exit(main())
