#!/usr/bin/env python3
"""번역문을 ROM에 삽입하고 한글 폰트를 만들어 넣습니다.

    python3 tools/inserttext.py rom/baserom.gba build/patched.gba \
        --ttf font/Galmuri14.ttf

하는 일
  1. `script/ko/*.txt` 에서 채워진 항목을 모읍니다.
  2. 번역하지 않은 항목이 쓰는 원문 코드를 **예약**합니다 (글리프 보존).
  3. 남은 코드 공간에 한글 음절을 배정합니다 (음절당 두 칸).
  4. TTF 를 16×16 으로 렌더해 왼쪽/오른쪽 8×16 글리프를 만듭니다.
  5. 큰 폰트 배열을 `0x600` 엔트리로 늘려 빈 공간에 놓고, 아카이브 오프셋
     워드 하나만 바꿔 가리키게 합니다 (**코드 패치 없음**).
  6. 번역문을 인코딩해 빈 공간에 쓰고, 문자열 테이블의 상대 오프셋을
     다시 씁니다.

원본 문자열 자리는 건드리지 않으므로 부분 번역 상태로도 빌드됩니다.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import kocode  # noqa: E402
import koenc  # noqa: E402
import kofont  # noqa: E402
import mktbl  # noqa: E402
import obtext  # noqa: E402
from script_io import ScriptFile  # noqa: E402


class InsertError(Exception):
    pass


class Arena:
    """0xFF 로 채워진 자유 공간 할당기."""

    def __init__(self, rom: bytearray, regions: list[tuple[int, int]]):
        self.rom = rom
        # 뒤쪽 구간부터 씁니다. 문자열 테이블과 아카이브가 ROM 앞쪽에 몰려
        # 있어서, 뒤에 두면 상대 오프셋이 양수로 나옵니다.
        self.regions = [list(r) for r in sorted(regions, reverse=True)]
        self.used = 0

    def alloc(self, size: int, align: int = 4) -> int:
        for reg in self.regions:
            start = reg[0] + ((-reg[0]) % align)
            if start + size <= reg[1]:
                reg[0] = start + size
                self.used += size
                return start
        raise InsertError(f"자유 공간 부족: {size:,}바이트를 넣을 곳이 없습니다")

    @property
    def remaining(self) -> int:
        return sum(r[1] - r[0] for r in self.regions)


def auto_regions(rom: bytes, fill: int = 0xFF,
                 min_size: int = 0x1000) -> list[tuple[int, int]]:
    out, start = [], None
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


def entry_addr(rom: bytes, table: int, index: int) -> int:
    """문자열 테이블 엔트리의 절대 ROM 오프셋.

    오프셋은 테이블 기준 부호 없는 32비트이고, 하드웨어는 `adds` 로 더하므로
    대상이 테이블보다 앞이면 한 바퀴 돕니다 (`0x0800D574`).
    """
    return (table + common.u32(rom, table + index * 4)) & 0xFFFFFFFF


def decode_codes(data: bytes) -> list[int]:
    """전개된 바이트열을 문자 코드 목록으로 (종결자 제외)."""
    out, i = [], 0
    while i < len(data) and data[i] != 0:
        b = data[i]
        if b in (1, 2, 3, 4, 5) and i + 1 < len(data):
            out.append((b << 8) | data[i + 1])
            i += 2
        else:
            out.append(b)
            i += 1
    return out


def reverse_table(table: dict[int, str]) -> dict[str, int]:
    """{코드: 문자} -> {문자: 코드}. 같은 문자면 짧은(작은) 코드를 씁니다."""
    out: dict[str, int] = {}
    for code in sorted(table):
        out.setdefault(table[code], code)
    return out


def read_translations(ko_dir: str, tables: list[int]) -> dict[int, dict[int, str]]:
    """{테이블: {인덱스: 번역문}} — 본문이 빈 항목은 뺍니다."""
    out: dict[int, dict[int, str]] = {}
    for base in tables:
        path = os.path.join(ko_dir, f"t{base:06X}.txt")
        if not os.path.exists(path):
            continue
        rows = {e.index: e.text for e in ScriptFile.read(path).entries
                if e.text.strip()}
        if rows:
            out[base] = rows
    return out


def reserved_codes(rom: bytes, tables: list[int],
                   translated: dict[int, dict[int, str]]) -> set[int]:
    """번역하지 않은 항목이 쓰는 문자 코드 — 글리프를 지우면 안 됩니다."""
    used: set[int] = set()
    for base in tables:
        done = translated.get(base, {})
        count = common.u32(rom, base)
        for idx in range(1, count):
            if idx in done:
                continue
            try:
                data = obtext.expand(rom, base + common.u32(rom, base + idx * 4))
            except Exception:
                continue
            i = 0
            while i < len(data):
                b = data[i]
                if b in (1, 2, 3, 4, 5) and i + 1 < len(data):
                    used.add((b << 8) | data[i + 1])
                    i += 2
                else:
                    used.add(b)
                    i += 1
    return used


def build_patch(rom: bytearray, ko_dir: str, tables: list[int],
                ttf: str, size: int, top: int) -> tuple[bytearray, dict]:
    """번역문과 한글 폰트를 넣은 ROM과 통계를 돌려줍니다."""
    translated = read_translations(ko_dir, tables)
    if not translated:
        raise InsertError(f"{ko_dir} 에 채워진 항목이 없습니다")

    ja_rev = reverse_table(mktbl.build(rom))
    reserved = reserved_codes(rom, tables, translated)

    text_all = "".join(t for rows in translated.values() for t in rows.values())
    syllables = [c for c in dict.fromkeys(text_all) if kocode.is_syllable(c)]
    pool = kocode.usable_codes()
    try:
        ko_map = kocode.allocate("".join(syllables), pool, reserved)
    except kocode.OutOfCodes as e:
        raise InsertError(str(e)) from e

    grids = kofont.render(ttf, ko_map, size, top)
    blob = kofont.build_large(rom, kofont.glyphs_for(ko_map, grids))

    arena = Arena(rom, auto_regions(rom))
    at = arena.alloc(len(blob) + 4, align=4)
    kofont.install(rom, blob, at, kofont.LARGE_ENTRY)

    written = entries = 0
    for base, rows in translated.items():
        for idx, text in sorted(rows.items()):
            try:
                data = koenc.encode(text, ko_map, ja_rev)
            except koenc.EncodeError as e:
                raise InsertError(f"테이블 0x{base:06X} #{idx}: {e}") from e
            off = arena.alloc(len(data), align=1)
            rom[off:off + len(data)] = data
            common.w32(rom, base + idx * 4, (off - base) & 0xFFFFFFFF)
            written += len(data)
            entries += 1

    return rom, {
        "번역 항목": entries,
        "음절": len(ko_map),
        "배정": ko_map,
        "예약 코드": reserved,
        "문자열 바이트": written,
        "폰트 위치": at + 4,
        "남은 자유 공간": arena.remaining,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="번역문 재삽입")
    ap.add_argument("rom")
    ap.add_argument("out")
    ap.add_argument("--ko", default="script/ko")
    ap.add_argument("--tables", default="build/strtables.tsv")
    ap.add_argument("--ttf", required=True, help="한글 비트맵 TTF")
    ap.add_argument("--size", type=int, default=14)
    ap.add_argument("--top", type=int, default=2, help="16행 중 글자 시작 행")
    args = ap.parse_args()

    rom = common.load(args.rom)
    if not os.path.exists(args.tables):
        print(f"[!] {args.tables} 가 없습니다. 먼저 make strings 를 실행하세요.",
              file=sys.stderr)
        return 1
    tables = [int(l.split("\t")[0], 16) for l in
              open(args.tables, encoding="utf-8").read().splitlines()[1:]]
    tables = [t for t in tables if not obtext.is_blob_table(rom, t)]

    print(f"배정 가능 음절 {kocode.capacity()}개")
    try:
        rom, stats = build_patch(rom, args.ko, tables, args.ttf,
                                 args.size, args.top)
    except InsertError as e:
        print(f"[!] {e}", file=sys.stderr)
        return 1

    print(f"  번역 항목        {stats['번역 항목']:,}개")
    print(f"  한글 음절        {stats['음절']:,}자 "
          f"/ 여유 {kocode.capacity() - len(stats['예약 코드']) // 2:,}")
    print(f"  예약 코드        {len(stats['예약 코드']):,}개 (원문 글리프 보존)")
    print(f"  문자열           {stats['문자열 바이트']:,}바이트")
    print(f"  폰트             0x{stats['폰트 위치']:07X} "
          f"({kofont.LARGE_CODES * 16:,}바이트)")
    print(f"  남은 자유 공간   {stats['남은 자유 공간']:,}바이트")

    common.save(args.out, bytes(rom))
    print(f"\n출력: {args.out}  SHA-1 {common.digests(rom)['sha1']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
