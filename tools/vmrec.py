#!/usr/bin/env python3
"""이벤트 VM 레코드 추출 · 대조.

`0x092000`–`0x0A4000` 구간에는 20바이트 고정 레코드가 늘어서 있습니다.
레코드는 THUMB 함수 포인터와 그 인자로 이루어집니다::

    +0   u16  field0      (인덱스/순번으로 추정)
    +2   u16  width       메시지 창 줄당 글자 수
    +4   u16  lines       메시지 창 줄 수
    +6   u32  handler     THUMB 함수 포인터 (최하위 비트 = 1)
    +10  u16  field10
    +12  u16  field12
    +14  u16  field14
    +16  u16  field16
    +18  u16  field18

width/lines 의 의미는 일본판과 영문 팬 번역판을 대조해 확인했습니다.
일본어는 전각 8자 × 2줄, 영어는 반각 16자 × 1줄로, 픽셀 폭이 같습니다.

    python3 tools/vmrec.py rom/baserom.gba --stats
    python3 tools/vmrec.py rom/baserom.gba --fn 0x0803B604
    python3 tools/vmrec.py rom/baserom.gba --diff other.gba --min-count 8
"""
from __future__ import annotations

import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

VM_LO, VM_HI = 0x092000, 0x0A4000
STRIDE = 20
PTR_IN_REC = 6          # 레코드 시작 기준 함수 포인터 위치
CODE_LIMIT = 0x200000   # 핸들러가 존재할 수 있는 코드 영역 상한

FIELDS = [(0, "field0"), (2, "width"), (4, "lines"),
          (10, "field10"), (12, "field12"), (14, "field14"),
          (16, "field16"), (18, "field18")]


def handler_at(rom: bytes, off: int) -> int | None:
    v = common.u32(rom, off)
    if not (v & 1):
        return None
    addr = v & ~1
    if common.ROM_BASE <= addr < common.ROM_BASE + CODE_LIMIT:
        return addr
    return None


def find_records(rom: bytes, lo: int = VM_LO, hi: int = VM_HI,
                 min_chain: int = 4) -> list[int]:
    """레코드 시작 오프셋 목록. STRIDE 간격으로 이어지는 것만 인정합니다."""
    ptrs = [o for o in range(lo, hi - 4, 4) if handler_at(rom, o) is not None]
    if not ptrs:
        return []
    chains, cur = [], [ptrs[0]]
    for a, b in zip(ptrs, ptrs[1:]):
        if b - a == STRIDE:
            cur.append(b)
        else:
            if len(cur) >= min_chain:
                chains.append(cur)
            cur = [b]
    if len(cur) >= min_chain:
        chains.append(cur)
    return [p - PTR_IN_REC for c in chains for p in c
            if p - PTR_IN_REC >= 0 and p - PTR_IN_REC + STRIDE <= len(rom)]


def read_record(rom: bytes, rec: int) -> dict:
    d = {name: common.u16(rom, rec + off) for off, name in FIELDS}
    d["offset"] = rec
    d["handler"] = common.u32(rom, rec + PTR_IN_REC) & ~1
    return d


def main() -> int:
    ap = argparse.ArgumentParser(description="이벤트 VM 레코드 도구")
    ap.add_argument("rom")
    ap.add_argument("--diff", help="대조할 다른 ROM (같은 오프셋 기준)")
    ap.add_argument("--fn", type=common.parse_int, help="특정 핸들러만 출력")
    ap.add_argument("--stats", action="store_true", help="요약 통계")
    ap.add_argument("--min-count", type=int, default=1,
                    help="--stats 시 레코드 수 하한")
    ap.add_argument("--lo", type=common.parse_int, default=VM_LO)
    ap.add_argument("--hi", type=common.parse_int, default=VM_HI)
    ap.add_argument("-o", "--out", help="TSV 저장")
    args = ap.parse_args()

    rom = common.load(args.rom)
    other = common.load(args.diff) if args.diff else None
    recs = find_records(rom, args.lo, args.hi)
    print(f"레코드 {len(recs)}개 (0x{args.lo:06X}~0x{args.hi:06X}, "
          f"{STRIDE}바이트 간격)", file=sys.stderr)

    by_fn = collections.defaultdict(list)
    for r in recs:
        by_fn[common.u32(rom, r + PTR_IN_REC) & ~1].append(r)

    if args.stats:
        print("핸들러\t레코드수\t폭(최빈)\t줄수(최빈)\t변경레코드")
        rows = []
        for fn, ps in by_fn.items():
            if len(ps) < args.min_count:
                continue
            w = collections.Counter(common.u16(rom, p + 2) for p in ps)
            l = collections.Counter(common.u16(rom, p + 4) for p in ps)
            chg = (sum(1 for p in ps
                       if bytes(rom[p:p + STRIDE]) != bytes(other[p:p + STRIDE]))
                   if other else 0)
            rows.append((len(ps), fn, w.most_common(1)[0], l.most_common(1)[0], chg))
        rows.sort(reverse=True)
        for n, fn, w, l, chg in rows:
            print(f"0x{fn:08X}\t{n}\t{w[0]}({w[1]})\t{l[0]}({l[1]})\t{chg}")
        return 0

    targets = by_fn.get(args.fn, []) if args.fn else recs
    if args.fn and not targets:
        print(f"핸들러 0x{args.fn:08X} 에 해당하는 레코드가 없습니다", file=sys.stderr)
        return 1

    head = ["오프셋", "핸들러"] + [n for _, n in FIELDS]
    print("\t".join(head))
    lines_out = []
    for r in targets:
        a = read_record(rom, r)
        row = [f"0x{a['offset']:06X}", f"0x{a['handler']:08X}"] + \
              [str(a[n]) for _, n in FIELDS]
        if other:
            b = read_record(other, r)
            row += ["|"] + [(str(b[n]) if b[n] != a[n] else "=") for _, n in FIELDS]
        lines_out.append(row)
        print("\t".join(row))

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            f.write("\t".join(head) + "\n")
            for row in lines_out:
                f.write("\t".join(row) + "\n")
        print(f"저장: {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
