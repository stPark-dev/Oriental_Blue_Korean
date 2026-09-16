#!/usr/bin/env python3
"""ROM에서 텍스트를 덤프해 번역용 텍스트 파일로 만듭니다.

블록 정의는 config/blocks.json 에 둡니다. 예::

    {
      "rom": {"sha1": "414cad..."},
      "blocks": [
        {"name": "items", "type": "pointer_table",
         "table": "tables/ja.tbl",
         "ptr_table": "0x091C64", "count": 85}
      ]
    }

    python3 tools/dumptext.py rom/baserom.gba --config config/blocks.json
    python3 tools/dumptext.py rom/baserom.gba --raw 0x91C64 --count 85 --table tables/ja.tbl
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
from script_io import Entry, ScriptFile  # noqa: E402
from tbl import Table  # noqa: E402


def dump_pointer_table(rom: bytes, table: Table, ptr_off: int, count: int,
                       max_len: int = 4096) -> list[Entry]:
    entries = []
    for i in range(count):
        ptr = common.u32(rom, ptr_off + i * 4)
        if not common.is_ptr(ptr, len(rom)):
            entries.append(Entry(i, 0, f"<$ERR 포인터 아님 0x{ptr:08X}>"))
            continue
        off = common.ptr_to_off(ptr, len(rom))
        text, _ = table.decode(rom, off, min(off + max_len, len(rom)))
        entries.append(Entry(i, off, text))
    return entries


def dump_sequential(rom: bytes, table: Table, start: int, count: int,
                    max_len: int = 4096) -> list[Entry]:
    """포인터 없이, 종결자로 끊어가며 연속으로 읽습니다."""
    entries = []
    off = start
    for i in range(count):
        if off >= len(rom):
            break
        text, nxt = table.decode(rom, off, min(off + max_len, len(rom)))
        entries.append(Entry(i, off, text))
        off = nxt
    return entries


def run_block(rom: bytes, blk: dict, out_dir: str, rom_path: str) -> int:
    table = Table.load(blk["table"])
    kind = blk.get("type", "pointer_table")
    count = int(blk["count"])
    if kind == "pointer_table":
        off = common.parse_int(str(blk["ptr_table"]))
        entries = dump_pointer_table(rom, table, off, count,
                                     blk.get("max_len", 4096))
        src = f"포인터 테이블 0x{off:06X}, {count}개"
    elif kind == "sequential":
        off = common.parse_int(str(blk["start"]))
        entries = dump_sequential(rom, table, off, count, blk.get("max_len", 4096))
        src = f"연속 텍스트 0x{off:06X}, {count}개"
    else:
        raise SystemExit(f"알 수 없는 블록 타입: {kind}")

    sf = ScriptFile(blk["name"], entries)
    path = os.path.join(out_dir, blk["name"] + ".txt")
    sf.write(path, header_comment=(
        f"블록: {blk['name']}\n원본: {os.path.basename(rom_path)}\n{src}\n"
        f"테이블: {blk['table']}\n"
        f"항목 {len(entries)}개 — 이 파일은 자동 생성됩니다. 직접 수정하지 마세요."))
    print(f"  {blk['name']:<16} {len(entries):>5}개 -> {path}")
    return len(entries)


def main() -> int:
    ap = argparse.ArgumentParser(description="ROM 텍스트 덤프")
    ap.add_argument("rom")
    ap.add_argument("--config", help="블록 정의 JSON")
    ap.add_argument("--out", default="script/ja", help="출력 디렉터리")
    ap.add_argument("--table", help="단일 블록 덤프용 .tbl")
    ap.add_argument("--raw", type=common.parse_int, help="포인터 테이블 오프셋")
    ap.add_argument("--start", type=common.parse_int, help="연속 덤프 시작 오프셋")
    ap.add_argument("--count", type=int, default=0)
    ap.add_argument("--name", default="dump")
    args = ap.parse_args()

    rom = common.load(args.rom)

    if args.config:
        with open(args.config, encoding="utf-8") as f:
            cfg = json.load(f)
        want = cfg.get("rom", {}).get("sha1")
        if want:
            got = common.digests(rom)["sha1"]
            if got.lower() != want.lower():
                print(f"[!] ROM SHA-1 불일치\n    기대 {want}\n    실제 {got}",
                      file=sys.stderr)
                return 1
        print(f"블록 {len(cfg['blocks'])}개 덤프:")
        total = sum(run_block(rom, b, args.out, args.rom) for b in cfg["blocks"])
        print(f"합계 {total}개 항목")
        return 0

    if not args.table or not args.count:
        ap.error("--config 또는 (--table 과 --count) 가 필요합니다")
    blk = {"name": args.name, "table": args.table, "count": args.count}
    if args.raw is not None:
        blk |= {"type": "pointer_table", "ptr_table": args.raw}
    elif args.start is not None:
        blk |= {"type": "sequential", "start": args.start}
    else:
        ap.error("--raw 또는 --start 가 필요합니다")
    run_block(rom, blk, args.out, args.rom)
    return 0


if __name__ == "__main__":
    sys.exit(main())
