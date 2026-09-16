#!/usr/bin/env python3
"""번역 스크립트에서 실제로 쓰인 문자 집합을 뽑아냅니다.

한글 음절은 11,172자 전부를 넣을 수 없으므로, 사용된 글자만 골라
서브셋 폰트를 만드는 데 씁니다.

    python3 tools/charset.py script/ko -o font/charset.txt
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from collections import Counter

TAG_RE = re.compile(r"<[^>\n]{1,32}>")
HEADER_RE = re.compile(r"^#\s*\[")


def collect(paths: list[str], strip_tags: bool = True) -> Counter:
    counter: Counter = Counter()
    for path in paths:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if HEADER_RE.match(line):
                    continue
                if strip_tags:
                    line = TAG_RE.sub("", line)
                counter.update(c for c in line.rstrip("\n") if c not in "\r\t")
    return counter


def iter_files(targets: list[str], ext: str) -> list[str]:
    out = []
    for t in targets:
        if os.path.isdir(t):
            for root, _, files in os.walk(t):
                out += [os.path.join(root, f) for f in sorted(files)
                        if f.endswith(ext)]
        else:
            out.append(t)
    return out


def block_of(ch: str) -> str:
    o = ord(ch)
    if 0xAC00 <= o <= 0xD7A3:
        return "한글음절"
    if 0x1100 <= o <= 0x11FF or 0x3130 <= o <= 0x318F:
        return "한글자모"
    if 0x4E00 <= o <= 0x9FFF:
        return "한자"
    if o < 0x80:
        return "ASCII"
    return unicodedata.category(ch)


def main() -> int:
    ap = argparse.ArgumentParser(description="스크립트에서 사용 문자 추출")
    ap.add_argument("paths", nargs="+", help="파일 또는 디렉터리")
    ap.add_argument("--ext", default=".txt")
    ap.add_argument("-o", "--out", help="문자 집합 저장 경로")
    ap.add_argument("--keep-tags", action="store_true", help="<...> 태그도 집계")
    ap.add_argument("--freq", action="store_true", help="빈도순 출력")
    args = ap.parse_args()

    files = iter_files(args.paths, args.ext)
    if not files:
        print("대상 파일이 없습니다.", file=sys.stderr)
        return 1

    counter = collect(files, strip_tags=not args.keep_tags)
    chars = sorted(counter)

    by_block: Counter = Counter()
    for c in chars:
        by_block[block_of(c)] += 1

    print(f"파일 {len(files)}개 / 고유 문자 {len(chars)}자 / 총 {sum(counter.values()):,}자")
    for block, n in by_block.most_common():
        print(f"  {block:<10} {n:>6}자")

    if args.freq:
        print("\n상위 40자:")
        for c, n in counter.most_common(40):
            print(f"  {c!r:<8} {n:>7}")

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write("".join(chars))
        print(f"\n저장: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
