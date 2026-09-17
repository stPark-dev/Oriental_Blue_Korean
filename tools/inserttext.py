#!/usr/bin/env python3
"""번역문을 ROM에 삽입하고 한글 폰트를 만들어 넣습니다.

    python3 tools/inserttext.py rom/baserom.gba build/patched.gba \
        --ttf font/Galmuri14.ttf

하는 일
  1. `script/ko/*.txt` 에서 채워진 항목을 모읍니다.
  2. 쓰인 음절의 16×16 글리프와 색인 테이블을 만듭니다.
  3. 출력 훅(`tools/kohook.py`)을 자유 공간에 놓고, 렌더러 세 곳
     (`0x0801C904`, `0x0801CBF0`, `0x0801C5E8`)의 `bl` 대상만 바꿉니다.
     메뉴 렌더러는 8행 칸이라 8×8 글리프를 따로 씁니다.
  4. 번역문을 인코딩해 빈 공간에 쓰고, 문자열 테이블의 상대 오프셋을
     다시 씁니다.

음절은 **코드 두 개**로 나가고 훅이 글리프를 찾아 두 칸에 나눠 씁니다.
코드가 고정이라 **음절 수에 한도가 없습니다**. 원본 폰트도 문자열 자리도
건드리지 않으므로 부분 번역 상태로도 빌드됩니다.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import koenc  # noqa: E402
import kofont  # noqa: E402
import kohook  # noqa: E402
import kosyl  # noqa: E402
import mktbl  # noqa: E402
import obtext  # noqa: E402
import thumb  # noqa: E402
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

    def alloc(self, size: int, align: int = 4, near: int | None = None,
              reach: int = 1 << 21) -> int:
        """`near` 를 주면 그 주소에서 `reach` 안쪽에만 잡습니다 (bl 사거리)."""
        for reg in self.regions:
            start = reg[0] + ((-reg[0]) % align)
            if start + size > reg[1]:
                continue
            if near is not None and abs(
                    common.off_to_ptr(start) - near) > reach:
                continue
            reg[0] = start + size
            self.used += size
            return start
        raise InsertError(f"자유 공간 부족: {size:,}바이트를 넣을 곳이 없습니다"
                          + (f" (0x{near:08X} 에서 bl 사거리 안)"
                             if near is not None else ""))

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


def syllable_codes(text: str) -> dict[str, tuple[int, int]]:
    """쓰인 음절 -> (앞 코드, 뒤 코드). 배정이 아니라 계산이라 한도가 없습니다."""
    out = {}
    for ch in text:
        if ch in out or not (kosyl.FIRST <= ord(ch) <= kosyl.LAST):
            continue
        lead, trail = kosyl.to_pair(ch)
        out[ch] = (kohook.lead_code(lead), kohook.trail_code(trail))
    return out


def build_patch(rom: bytearray, ko_dir: str, tables: list[int],
                ttf: str, size: int, top: int,
                ttf8: str | None = None, size8: int = 8, top8: int = 0
                ) -> tuple[bytearray, dict]:
    """번역문·글리프·훅을 넣은 ROM과 통계를 돌려줍니다."""
    translated = read_translations(ko_dir, tables)
    if not translated:
        raise InsertError(f"{ko_dir} 에 채워진 항목이 없습니다")

    ja_rev = reverse_table(mktbl.build(rom))
    text_all = "".join(t for rows in translated.values() for t in rows.values())
    ko_map = syllable_codes(text_all)

    slot, glyphs, count = kofont.build_syllable_tables(
        ttf, ko_map, size, top)
    # 8행 렌더러(메뉴)용 8×8 글리프. 슬롯 번호는 큰 표와 같습니다.
    glyphs8 = kofont.build_small_glyphs(ttf8 or ttf, ko_map, size8, top8)

    arena = Arena(rom, auto_regions(rom))
    # 훅은 호출 지점에서 bl 사거리 안에 있어야 합니다.
    sites = [(kohook.CALL_SITE, kohook.GET_WIDE, 0, 6, False),
             (kohook.CALL_SITE_HALF, kohook.GET_HALF, 8, 6, False),
             (kohook.CALL_SITE_MENU, kohook.GET_HALF, 0, 8, True)]
    hooks = [arena.alloc(256, align=2, near=s[0]) for s in sites]
    slot_at = arena.alloc(len(slot))
    glyph_at = arena.alloc(len(glyphs))
    glyph8_at = arena.alloc(len(glyphs8))
    slot_p = common.off_to_ptr(slot_at)
    glyph_p = common.off_to_ptr(glyph_at)
    glyph8_p = common.off_to_ptr(glyph8_at)

    rom[slot_at:slot_at + len(slot)] = slot
    rom[glyph_at:glyph_at + len(glyphs)] = glyphs
    rom[glyph8_at:glyph8_at + len(glyphs8)] = glyphs8

    # 렌더러마다 원래 부르던 함수·dst 위치·스트림 레지스터가 다릅니다.
    for at, (site, fb, back, sreg, small) in zip(hooks, sites):
        code = kohook.build(common.off_to_ptr(at), slot_p,
                            glyph8_p if small else glyph_p,
                            fallback=fb, dst_back=back, stream_reg=sreg,
                            small=small)
        rom[at:at + len(code)] = code
        o = site - common.ROM_BASE
        rom[o:o + 4] = thumb.bl_bytes(site, common.off_to_ptr(at))

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
        "음절": count,
        "문자열 바이트": written,
        "훅": [common.off_to_ptr(a) for a in hooks],
        "색인": common.off_to_ptr(slot_at),
        "글리프": common.off_to_ptr(glyph_at),
        "글리프8": common.off_to_ptr(glyph8_at),
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
    ap.add_argument("--ttf8", default="font/Galmuri7.ttf",
                    help="8행 렌더러(메뉴)용 8×8 한글 TTF")
    ap.add_argument("--size8", type=int, default=8)
    ap.add_argument("--top8", type=int, default=0)
    args = ap.parse_args()

    rom = common.load(args.rom)
    if not os.path.exists(args.tables):
        print(f"[!] {args.tables} 가 없습니다. 먼저 make strings 를 실행하세요.",
              file=sys.stderr)
        return 1
    tables = [int(l.split("\t")[0], 16) for l in
              open(args.tables, encoding="utf-8").read().splitlines()[1:]]
    tables = [t for t in tables if not obtext.is_blob_table(rom, t)]

    try:
        rom, stats = build_patch(rom, args.ko, tables, args.ttf,
                                 args.size, args.top,
                                 args.ttf8 if os.path.exists(args.ttf8) else None,
                                 args.size8, args.top8)
    except InsertError as e:
        print(f"[!] {e}", file=sys.stderr)
        return 1

    print(f"  번역 항목        {stats['번역 항목']:,}개")
    print(f"  한글 음절        {stats['음절']:,}자 (한도 없음)")
    print(f"  문자열           {stats['문자열 바이트']:,}바이트")
    print("  훅               " + " ".join(f"0x{h:08X}" for h in stats['훅']))
    print(f"  색인 테이블      0x{stats['색인']:08X} "
          f"({kofont.SYLLABLES * 2:,}바이트)")
    print(f"  글리프 16×16     0x{stats['글리프']:08X} "
          f"({(stats['음절'] + 1) * 32:,}바이트)")
    print(f"  글리프 8×8       0x{stats['글리프8']:08X} "
          f"({(stats['음절'] + 1) * 8:,}바이트)")
    print(f"  남은 자유 공간   {stats['남은 자유 공간']:,}바이트")

    common.save(args.out, bytes(rom))
    print(f"\n출력: {args.out}  SHA-1 {common.digests(rom)['sha1']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
