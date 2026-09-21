#!/usr/bin/env python3
"""오프닝 나레이션 한글화.

프롤로그의 `どこまでもつづく　青い空と…` 는 **문자열 표에 없습니다.** 표
805개를 다 펴 봐도 없고, 대응표로 인코딩한 바이트열도 평문에 없습니다.
정체는 **16×16 스프라이트**입니다.

    글리프 그림   ROM 0x8E3F08 + 타일번호*32   (한 글자 = 타일 4장, 1차원 배치)
    스프라이트표  ROM 0x8E6718 부터 8바이트 × 96

스프라이트 한 칸은 OAM 과 같은 모양입니다 — `attr0`(y·크기) `attr1`(x·반전·크기)
`attr2`(타일·팔레트), 뒤에 2바이트 여백. 게임은 이 표를 그대로 OAM 에 올리고
줄마다 y 를 더해 움직입니다. 그래서 **y 값이 곧 줄 구분**입니다.

글자는 세 가지 색으로 그립니다 (팔레트는 페이드 애니메이션이 돌립니다).

    3 = 획      1 = 획 둘레 1픽셀      2 = 그 바깥 1픽셀

`--probe N` 은 레코드 번호를 두 자리로 새긴 시험용 롬을 만듭니다. 실기에서
찍으면 **화면의 어느 자리가 몇 번 레코드인지** 그대로 읽힙니다. 이걸로 첫
화면의 세 줄을 확정했습니다.

    1줄 どこまでもつづく　青い空と        20 08 19 18 17 09 16 15 | 00 14 22 21
    2줄 どこまでもつづく　青い海をうつし  20 08 19 18 17 09 16 15 | 00 14 13 12 11 09 10
    3줄 ここに　青の大地がある            08 08 07 | 00 06 05 04 03 02 01

**아직 못 푼 것**: 한 레코드가 두 줄에 함께 나옵니다(1·2줄의 앞부분이 같은
번호). 그러니 줄을 이루는 레코드 목록은 이 표가 아니라 **다른 곳**에 있고,
x 도 게임이 따로 계산합니다. 그 목록을 찾아야 번역문을 넣을 수 있습니다.
`layout()` 은 그 목록을 찾은 뒤에 쓸 자리만 잡아 둔 것입니다.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

GLYPH_AT = 0x8E3F08         # 타일 번호 t 의 그림은 여기서 t*32 바이트 뒤
GLYPH_LO = 0x30             # 이 타일부터가 우리가 통째로 쓰는 영역
GLYPH_HI = 0x8E6700         # 글리프 영역 끝 (바로 뒤가 스프라이트 표)
SPRITES_AT = 0x8E6718
SPRITE_COUNT = 96
OFFSCREEN_Y = 200           # 안 쓰는 칸은 화면 밖으로 내립니다

STROKE, EDGE, RIM = 3, 1, 2  # 획 / 획 둘레 / 그 바깥
CELL = 16
FONT_SIZE = 12
FONT_PATH_SMALL = "font/Galmuri7.ttf"


class NarrError(Exception):
    pass


def glyph_slots() -> int:
    """쓸 수 있는 16×16 글리프 칸 수."""
    return (GLYPH_HI - (GLYPH_AT + GLYPH_LO * 32)) // (4 * 32)


def read_sprites(rom: bytes) -> list[dict]:
    """스프라이트 표를 읽습니다."""
    out = []
    for i in range(SPRITE_COUNT):
        a = SPRITES_AT + i * 8
        a0 = common.u16(rom, a)
        a1 = common.u16(rom, a + 2)
        a2 = common.u16(rom, a + 4)
        x = a1 & 0x1FF
        out.append({"i": i, "y": a0 & 0xFF, "x": x - 512 if x >= 256 else x,
                    "tile": a2 & 0x3FF, "a0": a0, "a1": a1, "a2": a2})
    return out


def lines_of(sprites: list[dict]) -> dict[int, list[dict]]:
    """y 값으로 줄을 나눕니다 (게임이 줄마다 y 를 더해 움직입니다)."""
    rows: dict[int, list[dict]] = defaultdict(list)
    for s in sprites:
        rows[s["y"]].append(s)
    return dict(rows)


def render_glyph(ch: str, font) -> bytearray:
    """글자 하나를 16×16 색 번호로. 획 3, 둘레 1, 그 바깥 2."""
    from PIL import Image, ImageDraw
    img = Image.new("L", (CELL, CELL), 0)
    d = ImageDraw.Draw(img)
    w = d.textlength(ch, font=font)
    d.text(((CELL - w) / 2, (CELL - FONT_SIZE) / 2 - 1), ch, font=font, fill=255)
    src = img.load()
    ink = [[1 if src[x, y] > 110 else 0 for x in range(CELL)] for y in range(CELL)]
    out = bytearray(CELL * CELL)
    for r, colour in ((0, STROKE), (1, EDGE), (2, RIM)):
        for y in range(CELL):
            for x in range(CELL):
                if out[y * CELL + x]:
                    continue
                if _within(ink, x, y, r):
                    out[y * CELL + x] = colour
    return out


def _within(ink, x: int, y: int, r: int) -> bool:
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            ny, nx = y + dy, x + dx
            if 0 <= ny < CELL and 0 <= nx < CELL and ink[ny][nx]:
                return True
    return False


def write_glyph(rom: bytearray, tile: int, cell: bytes) -> None:
    """16×16 색 번호를 타일 4장(좌상·우상·좌하·우하)으로 씁니다."""
    for j, (ox, oy) in enumerate(((0, 0), (8, 0), (0, 8), (8, 8))):
        base = GLYPH_AT + (tile + j) * 32
        if base + 32 > GLYPH_HI:
            raise NarrError(f"글리프 영역을 넘습니다 (타일 0x{tile:03X})")
        for y in range(8):
            for x in range(0, 8, 2):
                lo = cell[(oy + y) * CELL + ox + x]
                hi = cell[(oy + y) * CELL + ox + x + 1]
                rom[base + y * 4 + x // 2] = (lo & 0xF) | ((hi & 0xF) << 4)


def write_sprite(rom: bytearray, i: int, y: int, x: int, tile: int) -> None:
    a = SPRITES_AT + i * 8
    common.w16(rom, a, (y & 0xFF) | (0x1 << 14))            # 크기 1 = 16×16
    common.w16(rom, a + 2, (x & 0x1FF) | (0x1 << 14))       # 반전 없음
    common.w16(rom, a + 4, tile & 0x3FF)


def hide_sprite(rom: bytearray, i: int) -> None:
    write_sprite(rom, i, OFFSCREEN_Y, 0, GLYPH_LO)


def layout(rom: bytearray, texts: dict[int, str], font, reverse: bool) -> dict:
    """줄마다 글자를 앉힙니다. `texts` 는 {y: 한글 문장}.

    같은 글자는 글리프를 함께 씁니다. 자리가 모자라면 오류를 냅니다.
    """
    rows = lines_of(read_sprites(rom))
    slots: dict[str, int] = {}
    next_tile = GLYPH_LO
    used = 0
    for y, text in texts.items():
        if y not in rows:
            raise NarrError(f"y={y} 줄이 표에 없습니다")
        cells = rows[y]
        chars = [c for c in text if c != "　"]
        if len(chars) > len(cells):
            raise NarrError(f"y={y}: 글자 {len(chars)}개 > 칸 {len(cells)}개")
        for ch in chars:
            if ch in slots:
                continue
            if next_tile * 32 + GLYPH_AT + 4 * 32 > GLYPH_HI:
                raise NarrError("글리프 칸이 모자랍니다")
            write_glyph(rom, next_tile, render_glyph(ch, font))
            slots[ch] = next_tile
            next_tile += 4
        order = sorted(cells, key=lambda s: -s["x"] if reverse else s["x"])
        span = len(text.replace("　", "　"))
        x0 = -(_width(text) // 2)
        px = x0
        pos = 0
        for ch in text:
            if ch == "　":
                px += CELL // 2
                continue
            s = order[pos]
            write_sprite(rom, s["i"], s["y"], -px - CELL if reverse else px,
                         slots[ch])
            px += CELL
            pos += 1
            used += 1
        for s in order[pos:]:
            hide_sprite(rom, s["i"])
    for y, cells in rows.items():
        if y not in texts:
            continue
    return {"글리프": len(slots), "칸": used, "여유 글리프": glyph_slots() - len(slots)}


def _width(text: str) -> int:
    return sum(CELL // 2 if c == "　" else CELL for c in text)


def probe(rom: bytearray, font, lo: int = 0) -> dict:
    """레코드 번호를 두 자리로 새깁니다 — 화면에서 자리를 읽기 위한 시험용.

    글리프 칸이 레코드보다 적어서 `lo` 부터 채우고 나머지는 숨깁니다.
    """
    from PIL import ImageFont
    small = ImageFont.truetype(FONT_PATH_SMALL, 8)
    n = min(glyph_slots(), SPRITE_COUNT - lo)
    for k in range(n):
        write_glyph(rom, GLYPH_LO + k * 4, _two_digits(lo + k, small))
    for s in read_sprites(rom):
        i = s["i"]
        if lo <= i < lo + n:
            write_sprite(rom, i, s["y"], s["x"], GLYPH_LO + (i - lo) * 4)
        else:
            hide_sprite(rom, i)
    return {"보이는 레코드": f"{lo}~{lo + n - 1}"}


def _two_digits(v: int, font) -> bytearray:
    """두 자리 숫자를 16×16 칸에 (획 3, 둘레 1)."""
    from PIL import Image, ImageDraw
    img = Image.new("L", (CELL, CELL), 0)
    d = ImageDraw.Draw(img)
    d.text((1, 3), f"{v:02d}", font=font, fill=255)
    src = img.load()
    ink = [[1 if src[x, y] > 110 else 0 for x in range(CELL)] for y in range(CELL)]
    out = bytearray(CELL * CELL)
    for y in range(CELL):
        for x in range(CELL):
            if ink[y][x]:
                out[y * CELL + x] = STROKE
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="오프닝 나레이션 한글화")
    ap.add_argument("rom")
    ap.add_argument("-o", "--out")
    ap.add_argument("--font", default="font/Galmuri14.ttf")
    ap.add_argument("--probe", type=int, default=None, metavar="시작",
                help="레코드 번호를 새긴 시험용 롬 (이 번호부터)")
    args = ap.parse_args()

    from PIL import ImageFont
    if not os.path.exists(args.font):
        print(f"[!] 폰트가 없습니다: {args.font}")
        return 1
    font = ImageFont.truetype(args.font, FONT_SIZE)
    rom = bytearray(common.load(args.rom))
    try:
        stats = (probe(rom, font, args.probe) if args.probe is not None
                 else layout(rom, TEXT, font, REVERSE))
    except NarrError as e:
        print(f"[!] {e}")
        return 1
    common.save(args.out or args.rom, bytes(rom))
    print("  오프닝 나레이션  " + " · ".join(f"{k} {v}" for k, v in stats.items()))
    return 0


REVERSE = False
TEXT: dict[int, str] = {}


if __name__ == "__main__":
    sys.exit(main())
