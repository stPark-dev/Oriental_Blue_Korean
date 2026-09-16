#!/usr/bin/env python3
"""ROM 구조 탐색 — 포인터 테이블 / 텍스트 영역 후보 찾기.

    python3 tools/scan.py pointers rom.gba --min 16
    python3 tools/scan.py sjis     rom.gba --min 8
    python3 tools/scan.py bytes    rom.gba --lo 0x20 --hi 0x7E --min 12
    python3 tools/scan.py entropy  rom.gba --block 0x10000
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402


def pointer_runs(rom: bytes, min_count: int = 16, align: int = 4):
    """연속된 ROM 포인터(0x08xxxxxx) 덩어리를 찾습니다."""
    n = len(rom)
    i = 0
    while i + 4 <= n:
        if common.is_ptr(common.u32(rom, i), n):
            start = i
            j = i
            while j + 4 <= n and common.is_ptr(common.u32(rom, j), n):
                j += 4
            count = (j - start) // 4
            if count >= min_count:
                yield start, count
            i = j
        else:
            i += align


def _sjis_pair(lead: int, trail: int) -> bool:
    if not (0x81 <= lead <= 0x9F or 0xE0 <= lead <= 0xFC):
        return False
    return 0x40 <= trail <= 0xFC and trail != 0x7F


def sjis_runs(rom: bytes, min_chars: int = 8):
    """Shift-JIS(cp932) 2바이트 문자가 연속되는 구간."""
    n = len(rom)
    i = 0
    while i + 2 <= n:
        if _sjis_pair(rom[i], rom[i + 1]):
            start = i
            j = i
            while j + 2 <= n and _sjis_pair(rom[j], rom[j + 1]):
                j += 2
            chars = (j - start) // 2
            if chars >= min_chars:
                try:
                    text = bytes(rom[start:j]).decode("cp932")
                except UnicodeDecodeError:
                    text = ""
                yield start, j - start, text
            i = j
        else:
            i += 1


def byte_runs(rom: bytes, lo: int, hi: int, min_len: int = 12):
    """지정한 바이트 범위가 연속되는 구간 (커스텀 인코딩 탐색용)."""
    n = len(rom)
    i = 0
    while i < n:
        if lo <= rom[i] <= hi:
            start = i
            while i < n and lo <= rom[i] <= hi:
                i += 1
            if i - start >= min_len:
                yield start, i - start
        else:
            i += 1


def entropy_map(rom: bytes, block: int = 0x10000):
    """블록별 엔트로피 — 압축/그래픽 영역과 평문 영역 구분용."""
    for off in range(0, len(rom), block):
        chunk = rom[off:off + block]
        if not chunk:
            continue
        counts = Counter(chunk)
        total = len(chunk)
        h = -sum((c / total) * math.log2(c / total) for c in counts.values())
        yield off, len(chunk), h


def main() -> int:
    ap = argparse.ArgumentParser(description="ROM 구조 스캐너")
    ap.add_argument("mode", choices=["pointers", "sjis", "bytes", "entropy"])
    ap.add_argument("rom")
    ap.add_argument("--min", type=int, default=0, help="최소 길이/개수")
    ap.add_argument("--lo", type=common.parse_int, default=0x20)
    ap.add_argument("--hi", type=common.parse_int, default=0x7E)
    ap.add_argument("--block", type=common.parse_int, default=0x10000)
    ap.add_argument("--limit", type=int, default=50, help="출력 개수 (0=전체)")
    ap.add_argument("--preview", type=int, default=40, help="미리보기 글자 수")
    ap.add_argument("-o", "--out", help="결과를 TSV로 저장")
    args = ap.parse_args()

    rom = common.load(args.rom)
    rows: list[tuple] = []

    if args.mode == "pointers":
        m = args.min or 16
        rows = [(f"0x{o:06X}", c, f"0x{common.u32(rom, o) - common.ROM_BASE:06X}",
                 f"0x{common.u32(rom, o + 4 * (c - 1)) - common.ROM_BASE:06X}")
                for o, c in pointer_runs(rom, m)]
        head = ("테이블오프셋", "포인터수", "첫대상", "마지막대상")
    elif args.mode == "sjis":
        m = args.min or 8
        rows = [(f"0x{o:06X}", ln, t[:args.preview].replace("\n", "\n"))
                for o, ln, t in sjis_runs(rom, m)]
        head = ("오프셋", "길이", "미리보기")
    elif args.mode == "bytes":
        m = args.min or 12
        rows = [(f"0x{o:06X}", ln) for o, ln in byte_runs(rom, args.lo, args.hi, m)]
        head = ("오프셋", "길이")
    else:
        rows = [(f"0x{o:06X}", ln, f"{h:.3f}") for o, ln, h in entropy_map(rom, args.block)]
        head = ("오프셋", "크기", "엔트로피")

    print(f"# {args.mode}: {len(rows)}건")
    print("\t".join(head))
    shown = rows if args.limit == 0 else rows[:args.limit]
    for r in shown:
        print("\t".join(str(x) for x in r))
    if args.limit and len(rows) > args.limit:
        print(f"... 외 {len(rows) - args.limit}건 (--limit 0 으로 전체 출력)")

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write("\t".join(head) + "\n")
            for r in rows:
                f.write("\t".join(str(x) for x in r) + "\n")
        print(f"\n저장: {args.out} ({len(rows)}행)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
