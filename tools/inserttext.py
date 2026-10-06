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
import kologo  # noqa: E402
import kolz  # noqa: E402
import koname  # noqa: E402
import kosyl  # noqa: E402
import mktbl  # noqa: E402
import obtext  # noqa: E402
import thumb  # noqa: E402
from script_io import ScriptFile  # noqa: E402

# 기록 화면의 장소 이름. `0x0801550A movs r2,#0x10` 으로 기록 머리(+4)에
# 16바이트까지만 복사합니다. 한글은 음절당 4바이트라 「대도・천」에서 잘렸습니다.
# 그 자리는 +4~+0x1D 26바이트(+0x1E 는 레벨)라 25바이트 + 종결자까지 됩니다.
SAVE_PLACE_SITE = 0x0801550A
SAVE_PLACE_LIMIT = 25

# ROM 을 GBA 최대 크기 32MB 로 늘립니다. 원래 16MB 는 번역문으로 거의 찼습니다.
# 문자열표는 32비트 상대 오프셋이라 0x09xxxxxx 도 가리킬 수 있습니다.
EXPAND_TO = 0x2000000

# 대화창 선택지 「はい／いいえ」(`<$15>`). 0x080204D8 이 DF3908 #3·#4 를
# 3칸(6바이트)짜리 RAM 버퍼 0x02001D54·0x02001D5C 에 가운데 맞춰 복사하고,
# 0x080205CE 가 리터럴 0x08020634 의 0x02001D5C 를 그립니다. 한글 「아니오」는
# 12바이트라 「아」에서 잘렸고, 버퍼 뒤 0x02001D64 는 다른 루틴이 씁니다.
# 그래서 버퍼는 두고, 그리는 쪽 리터럴을 ROM 에 넣은 문자열로 돌립니다.
CHOICE_NO_LITERAL = 0x08020634
CHOICE_NO_RAM = 0x02001D5C
CHOICE_TABLE, CHOICE_NO_INDEX = 0xDF3908, 4

# 이름 입력에서 글자 덧붙이기(0x0804AC0C). 판 글자를 sp 4바이트에 받고 sp+4 에
# 이름을 복사한 뒤 이어 붙입니다. 한글 음절은 4바이트라 종결자가 sp+4 로 넘쳐
# 이름 복사에 덮이고, 이어 붙이기가 제 꼬리를 끝없이 베꼈습니다. 프레임을
# 0x20 으로 늘려 글자 8바이트, 이름 24바이트(12+4+종결자)를 줍니다.
NAME_ADD_PATCH = (
    (0x0804AC0E, bytes.fromhex("85B0"), bytes.fromhex("88B0")),   # sub sp,#0x20
    (0x0804AC2A, bytes.fromhex("01AC"), bytes.fromhex("02AC")),   # add r4,sp,#8
    (0x0804AC70, bytes.fromhex("05B0"), bytes.fromhex("08B0")),   # add sp,#0x20
)

# 메뉴 설명문을 스택 64바이트(`sub sp,#0x40`)에 복사해 그리는 함수 셋.
# 일본어는 많아야 42바이트였지만 한글은 91바이트까지라 넘쳐 복귀 주소를
# 덮었습니다 (타이틀에서 TRADE 에 커서를 두면 멈춤). 128바이트로 넓힙니다.
#   0x0803ADDC 타이틀 메뉴 설명  DF3908 0x1FA+커서, 0x202+상태
#   0x0803AE50 세이브 오류 안내  DF3908 0x205·0x206+커서
#   0x08058518 교환 메뉴 설명    DF3908 0x1B4+커서 (커서 5 까지)
DESC_BUFFER = 0x80
DESC_IDS = frozenset(range(0x1B4, 0x1BA)) | frozenset(range(0x1FA, 0x20A))
DESC_BUFFER_PATCH = (
    (0x0803ADDE, bytes.fromhex("90B0"), bytes.fromhex("A0B0")),   # sub sp,#0x80
    (0x0803AE44, bytes.fromhex("10B0"), bytes.fromhex("20B0")),   # add sp,#0x80
    (0x0803AE52, bytes.fromhex("90B0"), bytes.fromhex("A0B0")),
    (0x0803AEC0, bytes.fromhex("10B0"), bytes.fromhex("20B0")),
    (0x0805851A, bytes.fromhex("90B0"), bytes.fromhex("A0B0")),
    (0x08058556, bytes.fromhex("10B0"), bytes.fromhex("20B0")),
)


def desc_overflows(encoded: dict[int, bytes]) -> list[tuple[int, int]]:
    """설명문 버퍼를 넘는 (DF3908 번호, 종결자 포함 바이트 수)."""
    return [(i, len(d)) for i, d in sorted(encoded.items())
            if i in DESC_IDS and len(d) > DESC_BUFFER]


class InsertError(Exception):
    pass


class Arena:
    """0xFF 로 채워진 자유 공간 할당기.

    `ext` 는 ROM 을 32MB 로 늘린 뒤쪽 16MB 입니다. 원래 자리가 모자랄 때만
    쓰고(`alloc`), 일부러 그곳에 둘 것은 `alloc_ext` 로 받습니다.
    """

    def __init__(self, rom: bytearray, regions: list[tuple[int, int]],
                 ext: tuple[int, int] | None = None):
        self.rom = rom
        # 뒤쪽 구간부터 씁니다. 문자열 테이블과 아카이브가 ROM 앞쪽에 몰려
        # 있어서, 뒤에 두면 상대 오프셋이 양수로 나옵니다.
        self.regions = [list(r) for r in sorted(regions, reverse=True)]
        self.ext = list(ext) if ext else None
        self.used = 0

    def alloc_ext(self, size: int, align: int = 4) -> int:
        """늘린 자리에서 받습니다."""
        if self.ext is None:
            raise InsertError("늘린 자리가 없습니다")
        start = self.ext[0] + ((-self.ext[0]) % align)
        if start + size > self.ext[1]:
            raise InsertError(f"늘린 자리도 모자랍니다: {size:,}바이트")
        self.ext[0] = start + size
        self.used += size
        return start

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
        if near is None and self.ext is not None:
            return self.alloc_ext(size, align)
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


def read_set(rom: bytes, src: int, budget: int = obtext.OUT_LIMIT) -> set[int]:
    """전개하면서 **읽은** 바이트 주소. 되참조한 앞쪽 바이트도 들어갑니다."""
    seen: set[int] = set()

    def run(p: int, remaining: int, depth: int) -> bool:
        if depth > obtext.MAX_DEPTH:
            raise obtext.ExpandError("재귀 한계 초과")
        while remaining > 0:
            if not (0 <= p < len(rom)):
                raise obtext.ExpandError(f"범위 밖 소스 0x{p:X}")
            seen.add(p)
            b = rom[p]
            p += 1
            if b == obtext.ESCAPE:
                if p + 1 >= len(rom):
                    raise obtext.ExpandError("이스케이프 뒤 데이터 부족")
                seen.add(p)
                seen.add(p + 1)
                b1, b2 = rom[p], rom[p + 1]
                p += 2
                length = min((b1 >> 4) + 4, remaining)
                dist = ((b1 & 0x0F) << 8) | b2
                if run(p - dist, length, depth + 1):
                    return True
                remaining -= length
            else:
                if b == obtext.TERMINATOR:
                    return True
                remaining -= 1
        return False

    run(src, budget, 0)
    return seen


def spans(addrs, min_size: int = 16) -> list[tuple[int, int]]:
    """정렬된 주소들을 이어붙여 `min_size` 이상인 (시작, 끝) 목록으로."""
    out: list[tuple[int, int]] = []
    start = prev = None
    for a in addrs:
        if prev is not None and a == prev + 1:
            prev = a
            continue
        if start is not None and prev + 1 - start >= min_size:
            out.append((start, prev + 1))
        start = prev = a
    if start is not None and prev + 1 - start >= min_size:
        out.append((start, prev + 1))
    return out


def dead_regions(rom: bytes, translated: dict[int, dict[int, str]],
                 min_size: int = 16) -> list[tuple[int, int]]:
    """번역으로 버려지는 원문 문자열 자리.

    이 형식의 LZ 는 **앞서 나온 바이트를 되참조**하므로, 번역하지 않은
    항목이 전개 중에 읽는 바이트는 빼고 돌려줍니다.
    """
    dead: set[int] = set()
    live: set[int] = set()
    for base, rows in translated.items():
        _, entries = obtext.read_table(rom, base)
        for idx, addr in enumerate(entries, 1):
            try:
                got = read_set(rom, addr)
            except obtext.ExpandError:
                continue
            (dead if idx in rows else live).update(got)
    return spans(sorted(dead - live), min_size)


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
                ttf8: str | None = None, size8: int = 8, top8: int = 0,
                logo: str | None = None) -> tuple[bytearray, dict]:
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

    # 번역으로 쓸모없어진 원문 문자열 자리도 자유 공간에 더합니다.
    regions = auto_regions(rom) + dead_regions(rom, translated)
    ext = None
    if len(rom) < EXPAND_TO:
        ext = (len(rom), EXPAND_TO - 4)
        rom.extend(b"\xff" * (EXPAND_TO - len(rom)))
    arena = Arena(rom, regions, ext)
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

    # 메뉴 렌더러는 뒤 코드를 건너뜁니다 — 음절이 한 칸이 되어 칸 폭에 들어갑니다.
    skip = kohook.build_menu_skip(0)
    skip_at = arena.alloc(len(skip), align=4, near=kohook.MENU_SKIP_SITE)
    skip_p = common.off_to_ptr(skip_at)
    skip = kohook.build_menu_skip(skip_p)
    rom[skip_at:skip_at + len(skip)] = skip
    o = kohook.MENU_SKIP_SITE - common.ROM_BASE
    rom[o:o + 4] = kohook.menu_skip_site_bytes(skip_p)

    o = SAVE_PLACE_SITE - common.ROM_BASE
    if bytes(rom[o:o + 2]) != b"\x10\x22":
        raise InsertError(f"0x{SAVE_PLACE_SITE:08X} 가 movs r2,#0x10 이 아닙니다")
    rom[o] = SAVE_PLACE_LIMIT

    # 이름 입력 지우기는 한글 음절을 4바이트째로 지웁니다.
    o = kohook.NAME_DELETE_SITE - common.ROM_BASE
    if bytes(rom[o:o + 4]) != kohook.NAME_DELETE_ORIG:
        raise InsertError(f"0x{kohook.NAME_DELETE_SITE:08X} 가 원래 명령이 아닙니다")
    nd = kohook.build_name_delete(0)
    nd_at = arena.alloc(len(nd), align=4, near=kohook.NAME_DELETE_SITE)
    name_delete = common.off_to_ptr(nd_at)
    nd = kohook.build_name_delete(name_delete)
    rom[nd_at:nd_at + len(nd)] = nd
    rom[o:o + 4] = kohook.name_delete_site_bytes(name_delete)

    # 이름 입력 커서는 한글 음절을 화면 칸(2)으로 세어 자리를 잡습니다.
    o = kohook.NAME_WIDTH_SITE - common.ROM_BASE
    if bytes(rom[o:o + 4]) != kohook.NAME_WIDTH_ORIG:
        raise InsertError(f"0x{kohook.NAME_WIDTH_SITE:08X} 가 원래 명령이 아닙니다")
    nw = kohook.build_name_width(0)
    nw_at = arena.alloc(len(nw), align=4, near=kohook.NAME_WIDTH_SITE)
    name_width = common.off_to_ptr(nw_at)
    nw = kohook.build_name_width(name_width)
    rom[nw_at:nw_at + len(nw)] = nw
    rom[o:o + 4] = kohook.name_width_site_bytes(name_width)

    koname.install(rom)                    # 이름 입력판 10x8 가나다 순

    for at, orig, new in NAME_ADD_PATCH + DESC_BUFFER_PATCH:
        o = at - common.ROM_BASE
        if bytes(rom[o:o + 2]) != orig:
            raise InsertError(f"0x{at:08X} 가 {orig.hex()} 가 아닙니다")
        rom[o:o + 2] = new

    choice_no = None
    no_text = translated.get(CHOICE_TABLE, {}).get(CHOICE_NO_INDEX)
    if no_text:
        o = CHOICE_NO_LITERAL - common.ROM_BASE
        if int.from_bytes(rom[o:o + 4], "little") != CHOICE_NO_RAM:
            raise InsertError(f"0x{CHOICE_NO_LITERAL:08X} 가 0x{CHOICE_NO_RAM:08X} 가 아닙니다")
        data = koenc.encode(no_text, ko_map, ja_rev)      # 비압축 — 그대로 그립니다
        at = arena.alloc(len(data), align=4)
        rom[at:at + len(data)] = data
        choice_no = common.off_to_ptr(at)
        common.w32(rom, o, choice_no)

    # 타이틀 한글 로고는 스프라이트로 얹습니다 (tools/kologo.py).
    title_logo = None
    if logo:
        title_logo = kologo.install(
            rom, lambda n, a, near: (arena.alloc(n, align=a, near=near) if near
                                  else arena.alloc_ext(n, align=a)), logo)

    written = entries = 0
    for base, rows in translated.items():
        desc = {}
        for idx, text in sorted(rows.items()):
            try:
                data = koenc.encode(text, ko_map, ja_rev)
            except koenc.EncodeError as e:
                raise InsertError(f"테이블 0x{base:06X} #{idx}: {e}") from e
            if base == CHOICE_TABLE:
                desc[idx] = data
            # 게임은 읽을 때마다 전개하므로 눌러 넣습니다. 누르지 않으면
            # ROM 이 모자랍니다 (한글은 음절당 코드 두 개).
            data = kolz.compress_checked(data)
            off = arena.alloc(len(data), align=1)
            rom[off:off + len(data)] = data
            common.w32(rom, base + idx * 4, (off - base) & 0xFFFFFFFF)
            written += len(data)
            entries += 1
        for idx, n in desc_overflows(desc):
            raise InsertError(f"DF3908 #{idx}: 설명문 {n}바이트가 "
                              f"버퍼 {DESC_BUFFER}바이트를 넘습니다")

    return rom, {
        "번역 항목": entries,
        "음절": count,
        "문자열 바이트": written,
        "훅": [common.off_to_ptr(a) for a in hooks],
        "메뉴 건너뛰기": skip_p,
        "이름 지우기": name_delete,
        "이름 커서 폭": name_width,
        "선택지 아니오": choice_no,
        "타이틀 로고": title_logo,
        "늘린 자리 남음": (arena.ext[1] - arena.ext[0]) if arena.ext else 0,
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
    ap.add_argument("--logo", default=None,
                    help="타이틀 한글 로고 그림 (스프라이트로 얹음)")
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
                                 args.size8, args.top8, args.logo)
    except InsertError as e:
        print(f"[!] {e}", file=sys.stderr)
        return 1

    print(f"  번역 항목        {stats['번역 항목']:,}개")
    print(f"  한글 음절        {stats['음절']:,}자 (한도 없음)")
    print(f"  문자열           {stats['문자열 바이트']:,}바이트")
    print("  훅               " + " ".join(f"0x{h:08X}" for h in stats['훅']))
    print(f"  메뉴 건너뛰기    0x{stats['메뉴 건너뛰기']:08X}")
    print(f"  이름 입력        지우기 0x{stats['이름 지우기']:08X}"
          f" · 커서 0x{stats['이름 커서 폭']:08X}")
    if stats["타이틀 로고"]:
        t = stats["타이틀 로고"]
        print(f"  타이틀 로고      스프라이트 {t['조각']}조각 · 타일 {t['타일']}개 · "
              f"{t['바이트']:,}바이트 (훅 0x{t['훅']:08X})")
    print(f"  색인 테이블      0x{stats['색인']:08X} "
          f"({kofont.SYLLABLES * 2:,}바이트)")
    print(f"  글리프 16×16     0x{stats['글리프']:08X} "
          f"({(stats['음절'] + 1) * 32:,}바이트)")
    print(f"  글리프 8×8       0x{stats['글리프8']:08X} "
          f"({(stats['음절'] + 1) * 8:,}바이트)")
    print(f"  남은 자유 공간   {stats['남은 자유 공간']:,}바이트 "
          f"(+ 늘린 자리 {stats['늘린 자리 남음']:,}바이트)")

    common.save(args.out, bytes(rom))
    print(f"\n출력: {args.out}  SHA-1 {common.digests(rom)['sha1']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
