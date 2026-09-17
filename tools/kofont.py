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

한글은 출력 훅(`tools/kohook.py`)이 가로채므로 **원본 폰트는 건드리지
않습니다.** 이 파일의 `entry_addr` 는 폰트 위치 확인용으로 남겨 둡니다.

    python3 tools/kofont.py rom/baserom.gba --preview build/kofont.png
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import kocode  # noqa: E402
import kosyl  # noqa: E402
import obfont  # noqa: E402

FONT_ARCHIVE = 0x0D7DE5C
SMALL_ENTRY, LARGE_ENTRY = 0, 1
CELL_W, CELL_H = 16, 16                # 음절 한 개가 차지하는 픽셀


def entry_addr(rom: bytes, index: int, archive: int = FONT_ARCHIVE) -> int:
    """아카이브 엔트리의 데이터 주소 (ROM 오프셋).

    오프셋 워드는 부호 없는 32비트이고 하드웨어는 `adds` 로 더하므로,
    대상이 아카이브보다 앞이면 값이 한 바퀴 돕니다. 같은 식으로 계산합니다.
    """
    off = common.u32(rom, archive + 4 + index * 4)
    return ((archive + off) & 0xFFFFFFFF) + 4


SYLLABLES = 0xD7A4 - 0xAC00        # 11,172


def pack_glyph(grid: list[list[int]]) -> bytes:
    """16×16 격자를 32바이트로. 행마다 (왼쪽 8픽셀, 오른쪽 8픽셀) 입니다.

    훅이 `half` 부터 두 바이트 간격으로 16번 읽으므로 이 순서여야 합니다.
    """
    out = bytearray()
    for row in grid:
        out.append(sum(row[x] << (7 - x) for x in range(8)))
        out.append(sum(row[8 + x] << (7 - x) for x in range(8)))
    return bytes(out)


def used_syllables(syllables) -> list[str]:
    """슬롯 번호의 근거가 되는 정렬 순서. 표마다 같아야 합니다."""
    return sorted({c for c in syllables if kosyl.FIRST <= ord(c) <= kosyl.LAST})


def pack_glyph8(grid: list[list[int]]) -> bytes:
    """8×8 격자를 8바이트로. 행마다 1바이트, MSB 가 왼쪽입니다."""
    return bytes(sum(row[x] << (7 - x) for x in range(8)) for row in grid[:8])


def build_small_glyphs(ttf: str, syllables, size: int, top: int) -> bytes:
    """8행 렌더러용 8×8 글리프. 슬롯 번호는 큰 표와 같습니다."""
    used = used_syllables(syllables)
    grids = render(ttf, used, size, top, cell=8)
    out = bytearray(8)                         # 0번 슬롯 = 빈 글리프
    for ch in used:
        out += pack_glyph8(grids[ch])
    return bytes(out)


def build_syllable_tables(ttf: str, syllables, size: int, top: int
                          ) -> tuple[bytes, bytes, int]:
    """쓰는 음절만 글리프로 만들고 색인 테이블과 함께 돌려줍니다.

    (색인 테이블, 글리프, 음절 수). 색인은 음절 번호 -> 슬롯(u16) 이고
    슬롯 0 은 "쓰지 않음" 입니다. 글리프 0번 자리는 비워 둡니다.
    """
    used = used_syllables(syllables)
    grids = render(ttf, used, size, top)
    slot = bytearray(SYLLABLES * 2)
    glyphs = bytearray(32)                     # 0번 슬롯 = 빈 글리프
    for n, ch in enumerate(used, start=1):
        i = ord(ch) - kosyl.FIRST
        slot[i * 2:i * 2 + 2] = n.to_bytes(2, "little")
        glyphs += pack_glyph(grids[ch])
    return bytes(slot), bytes(glyphs), len(used)


def render(ttf: str, chars, size: int, top: int, left: int = 0,
           cell: int = CELL_W):
    """{문자: cell×cell 격자}. 픽셀 폰트이므로 크기를 정확히 맞춰야 선명합니다."""
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype(ttf, size)
    out = {}
    for ch in chars:
        im = Image.new("1", (cell, cell), 0)
        ImageDraw.Draw(im).text((left, top), ch, font=font, fill=1)
        out[ch] = [[1 if im.getpixel((x, y)) else 0 for x in range(cell)]
                   for y in range(cell)]
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
