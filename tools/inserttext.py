#!/usr/bin/env python3
"""번역문을 ROM에 재삽입하고 포인터를 다시 씁니다.

    python3 tools/inserttext.py rom/baserom.gba build/patched.gba \
        --config config/blocks.json

기본 동작
  1. script/ko/<블록>.txt 를 읽어 한글 테이블로 인코딩
  2. 자유 공간(기본: 0xFF 로 채워진 영역)에 문자열을 순서대로 기록
  3. 원본 포인터 테이블의 각 엔트리를 새 주소로 갱신
원본보다 길어져도 되도록 항상 새 영역에 쓰므로, 원본 문자열 자리는 건드리지 않습니다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
from script_io import ScriptFile  # noqa: E402
from tbl import Table  # noqa: E402


class Arena:
    """자유 공간 할당기."""

    def __init__(self, rom: bytearray, regions: list[tuple[int, int]]):
        self.rom = rom
        self.regions = [list(r) for r in regions]
        self.used = 0

    def alloc(self, data: bytes, align: int = 4) -> int:
        for reg in self.regions:
            start = reg[0] + ((-reg[0]) % align)
            if start + len(data) <= reg[1]:
                self.rom[start:start + len(data)] = data
                reg[0] = start + len(data)
                self.used += len(data)
                return start
        raise SystemExit(f"자유 공간 부족: {len(data)}바이트를 넣을 곳이 없습니다")

    @property
    def remaining(self) -> int:
        return sum(r[1] - r[0] for r in self.regions)


def auto_regions(rom: bytes, fill: int = 0xFF, min_size: int = 0x1000) -> list[tuple[int, int]]:
    """0xFF 가 길게 이어지는 구간을 자유 공간으로 잡습니다."""
    out = []
    start = None
    for i, b in enumerate(rom):
        if b == fill:
            if start is None:
                start = i
        else:
            if start is not None and i - start >= min_size:
                out.append((start + 4, i - 4))
            start = None
    if start is not None and len(rom) - start >= min_size:
        out.append((start + 4, len(rom) - 4))
    return out


def insert_block(rom: bytearray, blk: dict, ko_dir: str, arena: Arena,
                 strict: bool) -> tuple[int, int]:
    path = os.path.join(ko_dir, blk["name"] + ".txt")
    if not os.path.exists(path):
        print(f"  {blk['name']:<16} 건너뜀 (번역 파일 없음)")
        return 0, 0

    table = Table.load(blk.get("ko_table", blk["table"]))
    sf = ScriptFile.read(path)
    ptr_off = common.parse_int(str(blk["ptr_table"]))

    written = 0
    errors = 0
    for e in sf.entries:
        if not e.text.strip():
            continue
        try:
            data = table.encode(e.text.replace("\n", ""))
        except ValueError as err:
            errors += 1
            msg = f"  [!] {blk['name']} #{e.index:04d}: {err}"
            if strict:
                raise SystemExit(msg)
            print(msg)
            continue
        new_off = arena.alloc(data)
        common.w32(rom, ptr_off + e.index * 4, common.off_to_ptr(new_off))
        written += len(data)

    print(f"  {blk['name']:<16} {len(sf.entries):>5}개 / {written:,}바이트"
          + (f" / 오류 {errors}건" if errors else ""))
    return written, errors


def main() -> int:
    ap = argparse.ArgumentParser(description="번역문 재삽입")
    ap.add_argument("rom")
    ap.add_argument("out")
    ap.add_argument("--config", required=True)
    ap.add_argument("--ko", default="script/ko")
    ap.add_argument("--strict", action="store_true",
                    help="인코딩 불가 문자가 있으면 즉시 중단")
    args = ap.parse_args()

    rom = common.load(args.rom)
    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)

    want = cfg.get("rom", {}).get("sha1")
    if want and common.digests(rom)["sha1"].lower() != want.lower():
        print("[!] 원본 ROM SHA-1이 config와 다릅니다", file=sys.stderr)
        return 1

    regions = [(common.parse_int(str(r["start"])), common.parse_int(str(r["end"])))
               for r in cfg.get("free_space", [])]
    if not regions:
        regions = auto_regions(rom)
        total = sum(b - a for a, b in regions)
        print(f"자유 공간 자동 탐지: {len(regions)}구간 / {total:,}바이트")

    arena = Arena(rom, regions)
    print("삽입:")
    total_err = 0
    for blk in cfg["blocks"]:
        _, err = insert_block(rom, blk, args.ko, arena, args.strict)
        total_err += err

    common.save(args.out, rom)
    print(f"\n사용한 자유 공간 {arena.used:,}바이트 / 남은 공간 {arena.remaining:,}바이트")
    print(f"출력: {args.out}  SHA-1 {common.digests(rom)['sha1']}")
    if total_err:
        print(f"[!] 인코딩 오류 {total_err}건 — tables/ko.tbl 을 보완하세요")
    return 1 if (total_err and args.strict) else 0


if __name__ == "__main__":
    sys.exit(main())
