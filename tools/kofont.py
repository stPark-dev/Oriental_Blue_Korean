#!/usr/bin/env python3
"""한글 글리프를 원본 폰트 배열에 얹고, 필요하면 폰트를 재배치합니다.

폰트 위치는 **순수 데이터**입니다. 초기화(`0x0801C264`)가 아카이브를 두 번
조회할 뿐이고, 조회 루틴(`0x08000324`)은 이렇게 동작합니다::

    lookup(base, i):
        count = base[0]
        return base + base[i + 1] + 4        # 엔트리는 [u32 크기][데이터]

폰트 아카이브는 `0x0D7DE5C`(엔트리 85개)이고, 엔트리 0 이 작은 폰트,
1 이 큰 폰트입니다. **오프셋 워드 하나만 바꾸면 폰트를 어디로든 옮길 수
있습니다.** 코드 패치가 필요 없습니다.

원본 큰 폰트는 크기 접두가 `0x4000` = 코드 `0x000`–`0x3FF`(뱅크 0–3)입니다.
뱅크 4·5 까지 쓰려면 `0x6000` 으로 늘려 재배치해야 합니다.

    python3 tools/kofont.py rom/baserom.gba --preview build/kofont.png
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import kocode  # noqa: E402
import obfont  # noqa: E402

FONT_ARCHIVE = 0x0D7DE5C
SMALL_ENTRY, LARGE_ENTRY = 0, 1
LARGE_CODES = kocode.MAX_CODE          # 0x600 — 뱅크 5 까지
CELL_W, CELL_H = 16, 16                # 음절 한 개가 차지하는 픽셀


def entry_addr(rom: bytes, index: int, archive: int = FONT_ARCHIVE) -> int:
    """아카이브 엔트리의 데이터 주소 (ROM 오프셋).

    오프셋 워드는 부호 없는 32비트이고 하드웨어는 `adds` 로 더하므로,
    대상이 아카이브보다 앞이면 값이 한 바퀴 돕니다. 같은 식으로 계산합니다.
    """
    off = common.u32(rom, archive + 4 + index * 4)
    return ((archive + off) & 0xFFFFFFFF) + 4


def install(rom: bytearray, blob: bytes, at: int, index: int,
            archive: int = FONT_ARCHIVE) -> None:
    """`at` 에 `[u32 크기][blob]` 을 쓰고 아카이브가 그것을 가리키게 합니다."""
    rom[at:at + 4] = len(blob).to_bytes(4, "little")
    rom[at + 4:at + 4 + len(blob)] = blob
    common.w32(rom, archive + 4 + index * 4, at - archive)


def halves(grid: list[list[int]]) -> tuple[bytes, bytes]:
    """16×16 픽셀 격자를 8×16 두 장(왼쪽, 오른쪽)의 1bpp 바이트열로."""
    left = bytes(sum(row[x] << (7 - x) for x in range(8)) for row in grid)
    right = bytes(sum(row[8 + x] << (7 - x) for x in range(8)) for row in grid)
    return left, right


def build_large(rom: bytes, glyphs: dict[int, bytes]) -> bytes:
    """원본 큰 폰트를 바탕에 깔고 `glyphs` 를 덮어쓴 새 배열."""
    out = bytearray(LARGE_CODES * obfont.LARGE.stride)
    orig = rom[obfont.LARGE.base:
               obfont.LARGE.base + 0x400 * obfont.LARGE.stride]
    out[:len(orig)] = orig
    for code, data in glyphs.items():
        if not (0 <= code < LARGE_CODES):
            raise ValueError(f"코드 범위 밖: 0x{code:X}")
        if len(data) != obfont.LARGE.stride:
            raise ValueError(f"글리프 크기가 {obfont.LARGE.stride}바이트가 아닙니다")
        o = code * obfont.LARGE.stride
        out[o:o + obfont.LARGE.stride] = data
    return bytes(out)


def render(ttf: str, chars, size: int, top: int, left: int = 0):
    """{문자: 16×16 격자}. 픽셀 폰트이므로 크기를 정확히 맞춰야 선명합니다."""
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype(ttf, size)
    out = {}
    for ch in chars:
        im = Image.new("1", (CELL_W, CELL_H), 0)
        ImageDraw.Draw(im).text((left, top), ch, font=font, fill=1)
        out[ch] = [[1 if im.getpixel((x, y)) else 0 for x in range(CELL_W)]
                   for y in range(CELL_H)]
    return out


def glyphs_for(mapping: dict[str, tuple[int, int]], grids) -> dict[int, bytes]:
    """{음절: (좌코드, 우코드)} + {음절: 격자} -> {코드: 16바이트}."""
    out = {}
    for ch, (lc, rc) in mapping.items():
        left, right = halves(grids[ch])
        out[lc] = left
        out[rc] = right
    return out


def preview(grids, path: str, cols: int = 24, scale: int = 3) -> None:
    from PIL import Image
    items = list(grids.values())
    img = Image.new("L", (cols * (CELL_W + 1),
                          ((len(items) + cols - 1) // cols) * (CELL_H + 1)), 30)
    px = img.load()
    for i, grid in enumerate(items):
        gx, gy = (i % cols) * (CELL_W + 1), (i // cols) * (CELL_H + 1)
        for y, row in enumerate(grid):
            for x, v in enumerate(row):
                if v:
                    px[gx + x, gy + y] = 255
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    img.resize((img.width * scale, img.height * scale), Image.NEAREST).save(path)


def main() -> int:
    ap = argparse.ArgumentParser(description="한글 폰트 미리보기")
    ap.add_argument("rom")
    ap.add_argument("--ttf",
                    default="/home/stpark/다운로드/hanguel2/galmuri/Galmuri14.ttf")
    ap.add_argument("--size", type=int, default=14)
    ap.add_argument("--top", type=int, default=2)
    ap.add_argument("--chars", default="가나다라마바사아자차카타파하한글안녕")
    ap.add_argument("--preview", default="build/kofont.png")
    args = ap.parse_args()

    rom = common.load(args.rom)
    print(f"큰 폰트 현재 위치 0x{entry_addr(rom, LARGE_ENTRY):07X}")
    print(f"배정 가능 음절 {kocode.capacity()}개 "
          f"(코드 {len(kocode.usable_codes())}개)")

    grids = render(args.ttf, dict.fromkeys(args.chars), args.size, args.top)
    preview(grids, args.preview)
    print(f"저장: {args.preview} ({len(grids)}자)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
