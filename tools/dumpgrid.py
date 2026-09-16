#!/usr/bin/env python3
"""이름 입력 화면의 2바이트 문자 그리드를 추출합니다.

셀 형식 (ROM에서 확인됨):
  - `20 20`  빈칸
  - `20 XX`  반각 ASCII (XX = 문자 코드)
  - SJIS 2바이트  전각 문자

    python3 tools/dumpgrid.py rom/baserom.gba --find
    python3 tools/dumpgrid.py rom/baserom.gba 0x08B142 --count 597 --cols 16
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

BLANK = "　"  # 표시용 빈칸


def cell_ok(a: int, b: int) -> bool:
    if a == 0x20:
        return b == 0x20 or 0x21 <= b <= 0x7E
    return ((0x81 <= a <= 0x9F or 0xE0 <= a <= 0xEF)
            and 0x40 <= b <= 0xFC and b != 0x7F)


def decode_cell(a: int, b: int) -> str:
    if a == 0x20:
        return BLANK if b == 0x20 else chr(b)
    try:
        return bytes([a, b]).decode("cp932")
    except UnicodeDecodeError:
        return "�"


def find_grids(rom: bytes, min_cells: int = 32, start: int = 0,
               end: int | None = None):
    """셀 조건이 연속으로 성립하는 구간을 찾습니다."""
    end = len(rom) - 1 if end is None else end
    i = start
    while i < end:
        if cell_ok(rom[i], rom[i + 1]):
            s = i
            while i + 2 <= end and cell_ok(rom[i], rom[i + 1]):
                i += 2
            cells = (i - s) // 2
            if cells >= min_cells:
                yield s, cells
        else:
            i += 1


def main() -> int:
    ap = argparse.ArgumentParser(description="문자 그리드 추출")
    ap.add_argument("rom")
    ap.add_argument("offset", nargs="?", type=common.parse_int)
    ap.add_argument("--count", type=int, default=0, help="셀 개수")
    ap.add_argument("--cols", type=int, default=16, help="행당 셀 수")
    ap.add_argument("--find", action="store_true", help="그리드 후보 탐색")
    ap.add_argument("--min-cells", type=int, default=32)
    ap.add_argument("--start", type=common.parse_int, default=0)
    ap.add_argument("--end", type=common.parse_int, default=None)
    ap.add_argument("--tbl", help=".tbl 조각으로 저장 (코드=문자)")
    args = ap.parse_args()

    rom = common.load(args.rom)

    if args.find:
        rows = list(find_grids(rom, args.min_cells, args.start, args.end))
        rows.sort(key=lambda r: -r[1])
        print(f"# 그리드 후보 {len(rows)}건 (셀 {args.min_cells}개 이상)")
        print("오프셋\t셀수\t미리보기")
        for off, cells in rows[:30]:
            pv = "".join(decode_cell(rom[off + i * 2], rom[off + i * 2 + 1])
                         for i in range(min(cells, 12)))
            print(f"0x{off:06X}\t{cells}\t{pv}")
        return 0

    if args.offset is None:
        ap.error("오프셋 또는 --find 가 필요합니다")

    count = args.count
    if not count:
        off = args.offset
        while off + 2 <= len(rom) and cell_ok(rom[off], rom[off + 1]):
            off += 2
        count = (off - args.offset) // 2

    cells = [(args.offset + i * 2,
              decode_cell(rom[args.offset + i * 2], rom[args.offset + i * 2 + 1]))
             for i in range(count)]
    real = [c for _, c in cells if c != BLANK]
    print(f"0x{args.offset:06X}: {count}셀 / 문자 {len(real)}자 / 빈칸 {count - len(real)}칸")
    for r in range(0, count, args.cols):
        row = "".join(c for _, c in cells[r:r + args.cols])
        if row.strip(BLANK):
            print(f"  0x{args.offset + r * 2:06X}  |{row}|")

    if args.tbl:
        os.makedirs(os.path.dirname(os.path.abspath(args.tbl)) or ".", exist_ok=True)
        with open(args.tbl, "w", encoding="utf-8", newline="\n") as f:
            f.write(f"# 0x{args.offset:06X} 그리드에서 자동 추출 ({len(real)}자)\n")
            f.write("# tools/dumpgrid.py 로 재생성할 수 있습니다.\n")
            seen = set()
            for off, ch in cells:
                if ch == BLANK or ch in seen:
                    continue
                seen.add(ch)
                f.write(f"{rom[off]:02X}{rom[off + 1]:02X}={ch}\n")
        print(f"저장: {args.tbl} ({len(seen)}항목)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
