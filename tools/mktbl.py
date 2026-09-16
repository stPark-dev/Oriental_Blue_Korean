#!/usr/bin/env python3
"""ROM의 문자표에서 코드-문자 대응표(.tbl)를 생성합니다.

ROM 분석으로 확인한 사양::

    문자표  0x08ADEC 부터 셀당 2바이트가 연속으로 늘어섭니다.
              20 20      빈칸 (해당 코드 미사용)
              20 XX      반각 ASCII
              그 외      Shift-JIS 2바이트

    문자코드 = 셀 인덱스
              0x00–0xFF   본문에 1바이트로 그대로 등장
              0x100–0x1FF `01 XX` 2바이트로 등장
              0x200–0x2FF `02 XX` 2바이트로 등장

    제어코드 01–05 는 뒤에 1바이트를 동반합니다. 01/02 는 위와 같이 문자
    뱅크 선택자이고, 03/04/05 는 서식 제어로 보입니다.
    0x00 은 문자열 종결자, 0x0A 는 개행입니다.

검증: 이 대응표로 문자열을 디코딩하면 몬스터·인물 이름이 정상적인 일본어로
읽힙니다. 뱅크 기준점을 다른 값으로 두면 의미 없는 한자 나열이 됩니다.

    python3 tools/mktbl.py rom/baserom.gba -o build/ja.tbl
    python3 tools/mktbl.py rom/baserom.gba --coverage
"""
from __future__ import annotations

import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

CHARSET_BASE = 0x08ADEC
MAX_CODE = 0x300
TERMINATOR = 0x00
NEWLINE = 0x0A
BANK_CODES = (1, 2)
FORMAT_CODES = (3, 4, 5)


def cell(rom: bytes, index: int, base: int = CHARSET_BASE) -> str | None:
    """셀 하나를 문자로. 빈칸이면 None."""
    off = base + index * 2
    if off + 2 > len(rom):
        return None
    a, b = rom[off], rom[off + 1]
    if a == 0x20:
        return None if b == 0x20 else chr(b)
    try:
        return bytes([a, b]).decode("cp932")
    except UnicodeDecodeError:
        return None


def build(rom: bytes, base: int = CHARSET_BASE, max_code: int = MAX_CODE) -> dict:
    """{코드: 문자} — 코드는 (뱅크<<8)|인덱스 형태의 정수입니다."""
    out = {}
    for code in range(max_code):
        ch = cell(rom, code, base)
        if ch is not None:
            out[code] = ch
    return out


def encode_bytes(code: int) -> bytes:
    """문자 코드를 본문 바이트열로."""
    if code < 0x100:
        return bytes([code])
    return bytes([code >> 8, code & 0xFF])


def write_tbl(path: str, table: dict, rom_name: str) -> int:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    skipped = 0
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"# {os.path.basename(rom_name)} 에서 자동 생성 "
                f"(tools/mktbl.py)\n")
        f.write(f"# 문자표 0x{CHARSET_BASE:06X}, 코드 = (뱅크<<8)|인덱스\n")
        f.write("# 직접 수정하지 말고 make tbl 로 재생성하세요.\n#\n")
        f.write(f"/{TERMINATOR:02X}\n")
        f.write(f"*{NEWLINE:02X}\n\n")
        for code in sorted(table):
            if code in (TERMINATOR, NEWLINE):
                continue
            if code < 0x100 and (code in BANK_CODES or code in FORMAT_CODES):
                skipped += 1        # 제어 코드와 충돌하므로 문자로 쓰지 않음
                continue
            hexcode = encode_bytes(code).hex().upper()
            f.write(f"{hexcode}={table[code]}\n")
        f.write("\n# 서식 제어 (파라미터 1바이트 동반, 의미 미확인)\n")
        for c in FORMAT_CODES:
            f.write(f"# {c:02X}XX=<FMT{c}:XX>\n")
    return skipped


def main() -> int:
    ap = argparse.ArgumentParser(description="문자 대응표 생성")
    ap.add_argument("rom")
    ap.add_argument("-o", "--out", default="build/ja.tbl")
    ap.add_argument("--base", type=common.parse_int, default=CHARSET_BASE)
    ap.add_argument("--max-code", type=common.parse_int, default=MAX_CODE)
    ap.add_argument("--coverage", action="store_true",
                    help="실제 텍스트에 쓰인 코드가 모두 대응되는지 확인")
    args = ap.parse_args()

    rom = common.load(args.rom)
    table = build(rom, args.base, args.max_code)

    banks = collections.Counter(c >> 8 for c in table)
    print(f"문자표 0x{args.base:06X}: 대응 {len(table)}자")
    for b in sorted(banks):
        label = "직접(1바이트)" if b == 0 else f"뱅크 {b:02X}"
        print(f"  {label:<16} {banks[b]:>4}자")

    if args.coverage:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import obtext
        tsv = "build/strtables.tsv"
        if not os.path.exists(tsv):
            print(f"[!] {tsv} 가 없습니다. 먼저 make strings 를 실행하세요.",
                  file=sys.stderr)
            return 1
        used = collections.Counter()
        rows = [l.split("\t") for l in
                open(tsv, encoding="utf-8").read().splitlines()[1:]]
        for off, _ in rows:
            _, entries = obtext.read_table(rom, int(off, 16))
            for e in entries:
                try:
                    d = obtext.expand(rom, e)
                except Exception:
                    continue
                i = 0
                while i < len(d):
                    c = d[i]
                    if c == TERMINATOR:
                        i += 1
                        continue
                    if c in BANK_CODES:
                        used[(c << 8) | d[i + 1]] += 1
                        i += 2
                    elif c in FORMAT_CODES:
                        i += 2
                    else:
                        used[c] += 1
                        i += 1
        missing = {c: n for c, n in used.items() if c not in table
                   and c != NEWLINE}
        total = sum(used.values())
        lost = sum(missing.values())
        print(f"\n실제 사용 코드 {len(used)}종 / 총 {total:,}회")
        print(f"대응 실패 {len(missing)}종 / {lost:,}회 "
              f"(전체의 {lost / max(total, 1) * 100:.3f}%)")
        if missing:
            top = sorted(missing.items(), key=lambda x: -x[1])[:12]
            print("  미대응 상위:", ', '.join(f'0x{c:03X}×{n}' for c, n in top))

    skipped = write_tbl(args.out, table, args.rom)
    print(f"\n저장: {args.out}")
    if skipped:
        print(f"  (제어 코드와 충돌해 제외한 항목 {skipped}개)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
