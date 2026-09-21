#!/usr/bin/env python3
"""타이틀 로고 한글화.

타이틀 그래픽은 `0x6BC6D4` 의 LZ77 블록 하나(9,577 -> 14,720바이트, 460타일)에
모여 있고, VRAM `0x8400`(타일 번호 `0x20`)에 실립니다. 팔레트는 `0x6C0470`
부터 비압축으로 있습니다.

**타일맵은 ROM 에 없습니다.** 런타임에 만들어지므로 평문에도, LZ77 블록에도
없습니다. 그래서 워드마크 띠(BG2 맵 18~23행)의 맵을 분석해 `BAND_MAP` 상수로
들고 있습니다. 재현 방법은 `docs/ROM_NOTES.md` 를 보세요.

핵심은 **원본 글자가 색칠된 글자가 아니라는 점**입니다. 돌벽 그림에서 글자
모양만 투명(색 0)으로 파내고 가장자리에 흰색(색 15)을 두른 것이라, 파인 곳으로
뒤 레이어의 물결이 비쳐 파랗게 보입니다. 그러니 한글로 바꾸려면

    1. 일본어 글자가 파인 자리를 주변 돌벽으로 메우고
    2. 한글 모양을 새로 파낸 뒤
    3. 그 가장자리에 흰 테두리를 두릅니다

같은 방식으로 부제(`青の天外` -> `청의 천외`)도 바꿉니다. 부제 타일은 파란
판 위에 흰 글자라, 흰 글자만 지우고 한글을 얹습니다.

    python3 tools/kotitle.py build/patched.gba --logo art/title_ko.png \
        --font font/Galmuri7.ttf
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import gbalz  # noqa: E402

TILES_AT = 0x6BC6D4         # 타이틀 타일셋 LZ77 블록
TILES_LEN = 9577            # 원본 압축 길이 — 이 안에 들어가야 제자리에 쓴다
TILE_BASE = 0x20            # 블롭 타일 0 == VRAM 타일 0x20

W, H = 256, 48              # 워드마크 띠 (32타일 x 6줄)

TRANSPARENT, WHITE = 0, 15

# BG2(화면블록 0) 맵 18~23행. 한 칸은 GBA 타일맵 엔트리(팔레트<<12 | 플립 | 번호).
BAND_MAP = (
    "1420 1040 1041 1042 1043 1004 1005 1006 1047 1008 1009 100A 100B 100C 104D 104E"
    " 140E 140D 140C 1048 1049 104A 104B 104C 106F 108F 1404 1403 2402 2401 1433 1020",
    "1433 1060 1061 1062 1063 1064 1065 1066 1067 1068 1069 106A 106B 106C 106D 106E"
    " 100F 1010 1011 1012 1013 1014 1015 1016 1017 1018 1019 101A 101B 101C 101D 1033",
    "1420 1080 1081 1082 1083 1084 1085 1086 1087 1088 1089 108A 108B 108C 108D 108E"
    " 102F 1030 1031 1032 140A 1034 1035 1036 1037 1038 1039 103A 103B 103C 103D 1020",
    "1433 10A0 10A1 10A2 10A3 10A4 10A5 10A6 10A7 10A8 10A9 10AA 10AB 10AC 10AD 10AE"
    " 104F 1050 1051 1052 142A 1054 1055 1056 1057 1058 1059 105A 105B 105C 105D 1033",
    "1420 10C0 10C1 10C2 10C3 10C4 10C5 10C6 10C7 10C8 10C9 10CA 10CB 10CC 10CD 10CE"
    " 14CE 1070 1071 1072 1073 1074 1075 1076 1077 1078 1079 107A 107B 107C 107D 1020",
    "1433 10E0 10E1 10E2 10E3 10E4 10E5 10E6 10E7 10E8 10E9 10EA 10EB 10EC 10ED 10EE"
    " 14EE 1090 1091 1092 1093 1094 1095 1096 1097 1098 1099 109A 109B 109C 109D 1033",
)

# 이 띠 안에서만 쓰여 덮어써도 안전한 타일. 두 번 쓰이더라도 두 자리 모두
# BG2 자기 맵 안이면 포함했습니다 (짝은 장식 테두리 줄이라 티가 안 납니다).
PAINTABLE = frozenset((
    0x02F, 0x030, 0x031, 0x032, 0x034, 0x035, 0x036, 0x037, 0x038, 0x039, 0x03A, 0x03B,
    0x03C, 0x03D, 0x040, 0x041, 0x042, 0x043, 0x047, 0x048, 0x049, 0x04A, 0x04B, 0x04C,
    0x04D, 0x04E, 0x04F, 0x051, 0x052, 0x054, 0x055, 0x056, 0x057, 0x058, 0x059, 0x05A,
    0x05B, 0x05C, 0x05D, 0x060, 0x061, 0x062, 0x063, 0x064, 0x065, 0x066, 0x067, 0x068,
    0x069, 0x06A, 0x06B, 0x06C, 0x06D, 0x06E, 0x06F, 0x070, 0x071, 0x072, 0x073, 0x074,
    0x075, 0x076, 0x077, 0x078, 0x079, 0x07A, 0x07B, 0x07C, 0x07D, 0x080, 0x081, 0x082,
    0x083, 0x084, 0x085, 0x086, 0x087, 0x088, 0x089, 0x08A, 0x08B, 0x08C, 0x08D, 0x08E,
    0x08F, 0x090, 0x091, 0x092, 0x093, 0x094, 0x095, 0x096, 0x097, 0x098, 0x099, 0x09A,
    0x09B, 0x09C, 0x09D, 0x0A0, 0x0A1, 0x0A2, 0x0A3, 0x0A4, 0x0A5, 0x0A6, 0x0A7, 0x0A8,
    0x0A9, 0x0AA, 0x0AB, 0x0AD, 0x0AE, 0x0C1, 0x0C2, 0x0C3, 0x0C5, 0x0C6, 0x0C7, 0x0C8,
    0x0C9, 0x0CA, 0x0CB, 0x0CC, 0x0CD, 0x0CE, 0x0E0, 0x0E1, 0x0E2, 0x0E3, 0x0E4, 0x0E5,
    0x0E6, 0x0E7, 0x0E8, 0x0E9, 0x0EA, 0x0EB, 0x0EC, 0x0ED, 0x0EE,
))

SUBTITLE_TILES = tuple(range(0x160, 0x166))    # 「青の天外」 48x8
SUBTITLE_TEXT = "청의 천외"
SUBTITLE_GLYPH = 13         # 원본에서 이 색 이상이 글자, 아래는 파란 판

WORDMARK_FRACTION = 0.735   # 로고 그림에서 워드마크가 차지하는 세로 비율
BODY_ALPHA = 200            # 글자 본체로 볼 알파 (아래는 바깥 번짐)
BODY_LUMA = 150             # 이보다 어두우면 글자 속, 밝으면 원본 흰 테두리


class TitleError(Exception):
    pass


# --- 타일 -----------------------------------------------------------------

def load_tiles(rom: bytes) -> bytearray:
    """타이틀 타일셋을 풀어서 돌려줍니다 (타일당 32바이트)."""
    raw, _ = gbalz.decompress(bytes(rom), TILES_AT)
    return bytearray(raw)


def tile_pixels(tiles: bytes, idx: int) -> bytearray:
    """VRAM 타일 번호 -> 8x8 색 번호 64개."""
    off = (idx - TILE_BASE) * 32
    out = bytearray(64)
    for y in range(8):
        for x in range(0, 8, 2):
            b = tiles[off + y * 4 + x // 2]
            out[y * 8 + x] = b & 0xF
            out[y * 8 + x + 1] = b >> 4
    return out


def set_tile(tiles: bytearray, idx: int, px: bytes) -> None:
    off = (idx - TILE_BASE) * 32
    for y in range(8):
        for x in range(0, 8, 2):
            tiles[off + y * 4 + x // 2] = (px[y * 8 + x] & 0xF) | (
                (px[y * 8 + x + 1] & 0xF) << 4)


# --- 띠 캔버스 -------------------------------------------------------------

def band_cells():
    """(줄, 칸, 타일번호, 좌우반전, 상하반전) 을 차례로 냅니다."""
    for r, row in enumerate(BAND_MAP):
        for c, ent in enumerate(row.split()):
            v = int(ent, 16)
            yield r, c, v & 0x3FF, (v >> 10) & 1, (v >> 11) & 1


def band_canvas(tiles: bytes):
    """띠를 256x48 색 번호 그림으로 폅니다.

    타일 번호가 `TILE_BASE` 보다 작은 칸은 이 블롭 밖(공용 배경 타일)이라
    내용을 알 수 없습니다. `known` 으로 표시해 벽 복원의 출처에서 뺍니다.
    """
    canvas = bytearray(W * H)
    known = bytearray(W * H)
    for r, c, idx, hf, vf in band_cells():
        if idx < TILE_BASE:
            continue
        px = tile_pixels(tiles, idx)
        for y in range(8):
            for x in range(8):
                sx = 7 - x if hf else x
                sy = 7 - y if vf else y
                p = (r * 8 + y) * W + c * 8 + x
                canvas[p] = px[sy * 8 + sx]
                known[p] = 1
    return canvas, known


def restore_wall(canvas: bytes, known: bytes, w: int = W, h: int = H) -> bytearray:
    """글자가 파인 자리(투명·흰색)와 모르는 칸을 주변 돌벽 색으로 메웁니다."""
    out = bytearray(canvas)
    todo = [i for i in range(w * h)
            if not known[i] or out[i] in (TRANSPARENT, WHITE)]
    if not todo:
        return out
    hole = bytearray(w * h)
    for i in todo:
        hole[i] = 1
    while todo:
        nxt, moved = [], False
        for i in todo:
            y, x = divmod(i, w)
            for dy, dx in ((0, -1), (0, 1), (-1, 0), (1, 0),
                           (-1, -1), (-1, 1), (1, -1), (1, 1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and not hole[ny * w + nx]:
                    out[i] = out[ny * w + nx]
                    moved = True
                    break
            else:
                nxt.append(i)
                continue
            hole[i] = 0
        if not moved:           # 벽이 하나도 없으면 더 못 메운다
            break
        todo = nxt
    return out


# --- 마스크 도우미 ---------------------------------------------------------

def outline_of(mask: bytes, w: int, h: int) -> bytearray:
    """`mask` 를 1픽셀 두르는 고리."""
    out = bytearray(w * h)
    for y in range(h):
        for x in range(w):
            if mask[y * w + x]:
                continue
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny * w + nx]:
                        out[y * w + x] = 1
                        break
                if out[y * w + x]:
                    break
    return out


def despeckle(mask: bytes, w: int, h: int) -> bytearray:
    """2x2 열림 — 꽉 찬 2x2 블록에 들지 못한 화소를 지웁니다.

    9배로 줄인 그림에는 가장자리마다 반투명 부스러기가 1픽셀씩 남습니다.
    그대로 두면 획이 지저분해지고, 칠하면 안 되는 타일까지 잉크가 번집니다.
    """
    out = bytearray(w * h)
    for y in range(h - 1):
        for x in range(w - 1):
            i = y * w + x
            if mask[i] and mask[i + 1] and mask[i + w] and mask[i + w + 1]:
                out[i] = out[i + 1] = out[i + w] = out[i + w + 1] = 1
    return out


# --- 로고 그림 -------------------------------------------------------------

def _wordmark_body(path: str):
    """로고 PNG 에서 워드마크의 '진한 속' 만 뽑아 흑백 이미지로 돌려줍니다.

    원본 아트는 진한 남색 속 + 굵은 흰 테두리입니다. 실루엣을 통째로 줄이면
    240픽셀에서 테두리가 글자를 다 먹어 버리므로, 속만 글자로 삼고 테두리는
    나중에 1픽셀로 새로 두릅니다.
    """
    from PIL import Image
    im = Image.open(path).convert("RGBA")
    box = im.split()[3].getbbox()
    if box:
        im = im.crop(box)
    im = im.crop((0, 0, im.width, int(im.height * WORDMARK_FRACTION)))
    box = im.split()[3].getbbox()
    if box:
        im = im.crop(box)
    px = im.load()
    body = Image.new("L", im.size, 0)
    bp = body.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            if a >= BODY_ALPHA and (0.30 * r + 0.59 * g + 0.11 * b) < BODY_LUMA:
                bp[x, y] = 255
    return body


def _shape(body, width: int, thr: int):
    """줄여서 (글자 마스크, 테두리, 폭, 높이). 자리와 무관하니 한 번만 만듭니다."""
    from PIL import Image
    h = max(1, round(body.height * width / body.width))
    if h > H - 4:
        h = H - 4
        width = max(1, round(body.width * h / body.height))
    small = body.resize((width, h), Image.BOX)      # 면적 평균 — 가는 획을 살린다
    sp = small.load()
    w2, h2 = width + 2, h + 2                      # 테두리가 나갈 1픽셀 여백
    mask = bytearray(w2 * h2)
    for y in range(h):
        for x in range(width):
            if sp[x, y] >= thr:
                mask[(y + 1) * w2 + x + 1] = 1
    mask = despeckle(mask, w2, h2)
    return mask, outline_of(mask, w2, h2), w2, h2


def _lost(shape, free: bytes, dx: int, dy: int):
    """띠 위 (dx, dy) 에 놓았을 때 (잘린 화소, 전체, 왼쪽 위 모서리)."""
    mask, ring, w2, h2 = shape
    x0 = max(0, min(W - w2, (W - w2) // 2 + dx))
    y0 = max(0, min(H - h2, (H - h2) // 2 + dy))
    lost = total = 0
    for y in range(h2):
        row = (y0 + y) * W + x0
        for x in range(w2):
            i = y * w2 + x
            if mask[i] or ring[i]:
                total += 1
                if not free[row + x]:
                    lost += 1
    return lost, total, x0, y0


def _free_mask() -> bytearray:
    free = bytearray(W * H)
    for r, c, idx, _, _ in band_cells():
        if idx not in PAINTABLE:
            continue
        for y in range(8):
            for x in range(8):
                free[(r * 8 + y) * W + c * 8 + x] = 1
    return free


def render_wordmark(tiles: bytearray, logo: str) -> dict:
    """워드마크 띠를 한글 로고로 바꿉니다."""
    canvas, known = band_canvas(tiles)
    wall = restore_wall(canvas, known)
    free = _free_mask()
    body = _wordmark_body(logo)

    best = None
    for width in (236, 232, 228):
        for thr in (112, 120, 128, 136):
            shape = _shape(body, width, thr)
            if sum(shape[0]) < 1500:
                continue
            for dx in range(-8, 9):
                for dy in range(-4, 5):
                    lost, total, x0, y0 = _lost(shape, free, dx, dy)
                    score = lost / total
                    if best is None or score < best[0]:
                        best = (score, width, thr, dx, dy, lost, total, shape, x0, y0)
    if best is None:
        raise TitleError("로고를 띠에 앉힐 수 없습니다")
    _, width, thr, dx, dy, lost, total, shape, x0, y0 = best
    mask, ring, w2, h2 = shape

    out = bytearray(wall)
    for y in range(h2):
        row = (y0 + y) * W + x0
        for x in range(w2):
            i = y * w2 + x
            if ring[i]:
                out[row + x] = WHITE
    for y in range(h2):
        row = (y0 + y) * W + x0
        for x in range(w2):
            if mask[y * w2 + x]:
                out[row + x] = TRANSPARENT

    painted = 0
    for r, c, idx, hf, vf in band_cells():
        if idx not in PAINTABLE:
            continue
        px = bytearray(64)
        for y in range(8):
            for x in range(8):
                sx = 7 - x if hf else x
                sy = 7 - y if vf else y
                px[sy * 8 + sx] = out[(r * 8 + y) * W + c * 8 + x]
        set_tile(tiles, idx, px)
        painted += 1
    return {"칠한 타일": painted, "잘린 화소": lost, "글자 화소": total,
            "폭": width, "밀기": (dx, dy)}


def render_subtitle(tiles: bytearray, font: str, text: str = SUBTITLE_TEXT) -> dict:
    """부제 여섯 타일(48x8)을 한글로 바꿉니다."""
    from PIL import Image, ImageDraw, ImageFont
    sw, sh = len(SUBTITLE_TILES) * 8, 8
    canvas = bytearray(sw * sh)
    for i, t in enumerate(SUBTITLE_TILES):
        px = tile_pixels(tiles, t)
        for y in range(8):
            for x in range(8):
                canvas[y * sw + i * 8 + x] = px[y * 8 + x]
    known = bytearray([1] * (sw * sh))
    plate = bytearray(canvas)
    for i, v in enumerate(canvas):          # 원본 흰 글자만 지운다
        if v >= SUBTITLE_GLYPH:
            plate[i] = TRANSPARENT
    plate = restore_wall(plate, known, sw, sh)

    img = Image.new("L", (sw, sh), 0)
    draw = ImageDraw.Draw(img)
    face = ImageFont.truetype(font, 8)
    draw.text(((sw - draw.textlength(text, font=face)) / 2, 0),
              text, font=face, fill=255)
    ip = img.load()
    ink = 0
    for y in range(sh):
        for x in range(sw):
            if ip[x, y] > 110:
                plate[y * sw + x] = WHITE
                ink += 1
    for i, t in enumerate(SUBTITLE_TILES):
        px = bytearray(64)
        for y in range(8):
            for x in range(8):
                px[y * 8 + x] = plate[y * sw + i * 8 + x]
        set_tile(tiles, t, px)
    return {"부제 화소": ink}


# --- 빌드 ------------------------------------------------------------------

def build(rom: bytes, logo: str, font: str):
    """(재압축한 타일셋, 통계). ROM 은 건드리지 않습니다."""
    tiles = load_tiles(rom)
    stats = render_wordmark(tiles, logo)
    stats.update(render_subtitle(tiles, font))
    packed = gbalz.compress(bytes(tiles))
    if len(packed) > TILES_LEN:
        raise TitleError(
            f"재압축 {len(packed):,}바이트가 원본 자리 {TILES_LEN:,}바이트를 넘습니다")
    stats["압축"] = len(packed)
    stats["여유"] = TILES_LEN - len(packed)
    return packed, stats


def apply(rom: bytearray, logo: str, font: str) -> dict:
    """ROM 을 제자리에서 고칩니다."""
    packed, stats = build(rom, logo, font)
    rom[TILES_AT:TILES_AT + len(packed)] = packed
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="타이틀 로고 한글화")
    ap.add_argument("rom", help="고칠 ROM (제자리에서 수정)")
    ap.add_argument("-o", "--out", help="따로 저장할 경로")
    ap.add_argument("--logo", default="art/title_ko.png")
    ap.add_argument("--font", default="font/Galmuri7.ttf")
    args = ap.parse_args()

    for p in (args.logo, args.font):
        if not os.path.exists(p):
            print(f"[!] 파일이 없습니다: {p}")
            return 1
    rom = bytearray(common.load(args.rom))
    try:
        stats = apply(rom, args.logo, args.font)
    except TitleError as e:
        print(f"[!] {e}")
        return 1
    common.save(args.out or args.rom, bytes(rom))
    print(f"  타이틀 로고    칠한 타일 {stats['칠한 타일']}개 · "
          f"잘린 화소 {stats['잘린 화소']}/{stats['글자 화소']} "
          f"({stats['잘린 화소'] / stats['글자 화소'] * 100:.1f}%)")
    print(f"  부제           「{SUBTITLE_TEXT}」 {stats['부제 화소']}화소")
    print(f"  타일셋         {stats['압축']:,}바이트 "
          f"(자리 {TILES_LEN:,}, 여유 {stats['여유']:,})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
