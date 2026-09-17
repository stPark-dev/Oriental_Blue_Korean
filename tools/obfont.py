#!/usr/bin/env python3
"""오리엔탈블루 폰트 도구 — 글리프 추출·검증.

mGBA GDB 스텁으로 출력 경로를 역추적해 확정한 사양입니다.
자세한 근거는 `docs/ROM_NOTES.md` 의 "폰트와 글자 출력 경로" 를 보세요.

본문 폰트 두 벌은 **문자 코드로 바로 색인**하는 비압축 1bpp 배열입니다.

    반각  0x0D7DFB8   8×8  / 8바이트  / 586자
    전각  0x0D7FFBC   8×16 / 16바이트 / 494자 (ASCII 구간은 비어 있음)

둘 다 행당 1바이트, MSB가 왼쪽 픽셀입니다. 실행 중에는 베이스 주소가 EWRAM
`0x02001A48`(반각) `0x02001A4C`(전각) 에 들어 있어, **폰트를 ROM 빈 공간으로
옮기고 이 포인터만 바꾸면 크기 제한 없이 교체**할 수 있습니다.

시스템 폰트는 별개입니다 — 본문에 쓰이지 않습니다.

    시스템 0x00BD7E0  8×8 / 4bpp / 32바이트 / JIS X 0201 색인
           팔레트 0x00BD7C0 (16색 BGR555), VRAM 0x0600E000 으로 직접 복사

    python3 tools/obfont.py verify  rom/baserom.gba
    python3 tools/obfont.py extract rom/baserom.gba -o build/font.png
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402


@dataclass(frozen=True)
class Font:
    name: str
    base: int
    width: int
    height: int
    stride: int          # 글리프 한 개의 바이트 수
    count: int = 0x300   # 코드 0x000-0x2FF
    first: int = 0


# 본문 폰트 (1bpp, 문자 코드 색인)
SMALL = Font("반각", 0x0D7DFB8, 8, 8, 8)
WIDE = Font("전각", 0x0D7FFBC, 8, 16, 16)
# 시스템 폰트 (4bpp, JIS X 0201 색인) — 본문 경로와 무관
SYSTEM = Font("시스템", 0x00BD7E0, 8, 8, 32, count=0xE0, first=0x20)
SYSTEM_PALETTE = 0x00BD7C0

# 실행 중 폰트 베이스가 들어 있는 EWRAM 변수
EWRAM_SMALL_PTR = 0x02001A48
EWRAM_WIDE_PTR = 0x02001A4C

GRID_BASE = 0x008ADEC          # 이름 입력 문자 그리드 (셀당 2바이트)


def glyph(rom: bytes, font: Font, code: int) -> list[list[int]]:
    """1bpp 글리프를 0/1 픽셀 행렬로. 행당 1바이트, MSB가 왼쪽입니다."""
    off = font.base + (code - font.first) * font.stride
    return [[(b >> (7 - x)) & 1 for x in range(font.width)]
            for b in rom[off:off + font.stride]]


def system_glyph(rom: bytes, code: int) -> list[list[int]]:
    """시스템 폰트(4bpp)를 0/1 픽셀 행렬로. 니블 값은 0 또는 F 입니다."""
    off = SYSTEM.base + (code - SYSTEM.first) * SYSTEM.stride
    data = rom[off:off + SYSTEM.stride]
    rows = []
    for y in range(SYSTEM.height):
        rows.append([1 if ((data[y * 4 + x // 2] >> (4 * (x & 1))) & 0xF) else 0
                     for x in range(SYSTEM.width)])
    return rows


def is_empty(rom: bytes, font: Font, code: int) -> bool:
    off = font.base + (code - font.first) * font.stride
    return not any(rom[off:off + font.stride])


def populated(rom: bytes, font: Font) -> list[int]:
    return [c for c in range(font.first, font.first + font.count)
            if not is_empty(rom, font, c)]


def grid_is_blank(rom: bytes, code: int) -> bool:
    off = GRID_BASE + code * 2
    return rom[off:off + 2] == b"\x20\x20"


def verify(rom: bytes) -> dict:
    """그리드와 폰트가 같은 색인 체계인지 대조합니다."""
    agree = mismatch = 0
    for c in range(WIDE.count):
        if 0x20 <= c <= 0x9F:
            continue          # ASCII·전각영숫자 구간은 반각 폰트가 담당
        if grid_is_blank(rom, c) == is_empty(rom, WIDE, c):
            agree += 1
        else:
            mismatch += 1
    return {
        "반각 글리프": len(populated(rom, SMALL)),
        "전각 글리프": len(populated(rom, WIDE)),
        "전각 ASCII 빈 글리프": sum(1 for c in range(0x21, 0x7F)
                               if is_empty(rom, WIDE, c)),
        "그리드 일치": agree,
        "그리드 불일치": mismatch,
    }


def _sheet(glyphs, w, h, cols=32, scale=3):
    from PIL import Image
    img = Image.new("L", (cols * (w + 1),
                          ((len(glyphs) + cols - 1) // cols) * (h + 1)), 30)
    px = img.load()
    for i, rows in enumerate(glyphs):
        gx, gy = (i % cols) * (w + 1), (i // cols) * (h + 1)
        for y, row in enumerate(rows):
            for x, v in enumerate(row):
                if v:
                    px[gx + x, gy + y] = 255
    return img.resize((img.width * scale, img.height * scale), Image.NEAREST)


def main() -> int:
    ap = argparse.ArgumentParser(description="오리엔탈블루 폰트 도구")
    sub = ap.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("verify", help="폰트와 문자 그리드 대조")
    v.add_argument("rom")

    e = sub.add_parser("extract", help="글리프 시트 PNG 출력")
    e.add_argument("rom")
    e.add_argument("-o", "--out", default="build/font.png")
    e.add_argument("--font", choices=("wide", "small", "system"),
                   default="wide")
    e.add_argument("--raw", help="글리프 원본 바이트를 이 파일로 저장")

    args = ap.parse_args()
    rom = common.load(args.rom)

    if args.cmd == "verify":
        for k, val in verify(rom).items():
            print(f"  {k:<18} {val}")
        for f in (SMALL, WIDE, SYSTEM):
            bpp = 4 if f is SYSTEM else 1
            print(f"\n{f.name:<4} 0x{f.base:07X} / {f.width}×{f.height} {bpp}bpp"
                  f" / {f.stride}바이트 / {f.count * f.stride:,}바이트")
        return 0

    font = {"wide": WIDE, "small": SMALL, "system": SYSTEM}[args.font]
    if font is SYSTEM:
        glyphs = [system_glyph(rom, c)
                  for c in range(font.first, font.first + font.count)]
    else:
        glyphs = [glyph(rom, font, c)
                  for c in range(font.first, font.first + font.count)]
    raw = rom[font.base:font.base + font.count * font.stride]

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    _sheet(glyphs, font.width, font.height).save(args.out)
    print(f"저장: {args.out} ({font.name} 글리프 {len(glyphs)}개)")
    if args.raw:
        common.save(args.raw, raw)
        print(f"저장: {args.raw} ({len(raw):,}바이트)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
