#!/usr/bin/env python3
"""타이틀 한글 로고를 스프라이트(OBJ)로 얹습니다.

배경판(BG2)에 로고를 고쳐 그리면 깨집니다 (`docs/ROM_NOTES.md` 「타이틀」).

- 타일맵이 같은 그림의 타일을 여러 자리에서 나눠 써서, 고친 조각이 엉뚱한
  곳에도 찍힙니다.
- 15·16열이 좌우 반전 쌍이라 한쪽을 고치면 다른 쪽이 뒤집혀 나옵니다.
- 세로 스크롤을 HBlank 가 줄마다 바꿔, 글자가 8픽셀 줄 경계에서 어긋납니다.

스프라이트는 셋 다 받지 않습니다. 그래서 배경판의 일본어 로고 자리는
돌벽으로 메우기만 하고(`kotitle.py --sprite`), 한글 로고는 OBJ 로 그립니다.

매 프레임 OAM 사본(IWRAM `0x03003150`)을 DMA 로 보내는 `0x0807AD7E` 의
`ldr r1,=DMA3 / ldr r0,=사본` 을 `bl` 로 바꿉니다. 훅은

    타이틀이면 (BG0~3CNT 와 BG2 맵 한 칸으로 가립니다)
        처음 한 번 로고 타일(LZ77, BIOS SWI 0x12)과 팔레트 15 를 싣고
        사본의 마지막 칸들에 로고 OAM 세 속성을 씁니다
    아니면 사본의 그 칸들 중 로고 것(attr2 가 같은 칸)만 숨깁니다
    두 명령을 되살려 돌아갑니다

타이틀에서 OAM 은 17칸, OBJ 타일은 `0x000`–`0x11F` 만 씁니다. 로고는
`0x200` 부터 둡니다 (원본 타이틀 세이브스테이트로 확인).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import gbalz  # noqa: E402
import kotitle  # noqa: E402
import thumb  # noqa: E402

SITE = 0x0807AD7E
SITE_ORIG = bytes.fromhex("08490848")      # ldr r1,=0x040000D4 / ldr r0,=0x03003150
DMA3 = 0x040000D4
OAM_SHADOW = 0x03003150

# 타이틀 판별. 원본 타이틀 세이브스테이트의 값입니다.
BGCNT = 0x04000008
TITLE_BGCNT01 = 0x020B010B
TITLE_BGCNT23 = 0x03080009
TITLE_MAP_AT = 0x06000506                  # BG2 맵 20행 3열
TITLE_MAP_VAL = 0x2022

OBJ_VRAM = 0x06010000
TILE_BASE = 0x200
PALETTE = 15
OBJ_PAL = 0x05000200 + PALETTE * 32
FIRST_SLOT = 72                            # 사본 72~127칸을 씁니다 (타이틀은 17칸만 씀)

# 반짝임: 원본 로고는 돌벽에서 글자를 파내 뒤의 물결 층(BG0·BG1, 알파 섞기)이
# 비치는 구조라 반짝입니다. 같은 효과를 OBJ 창으로 냅니다 — 글자 안쪽 모양의
# 스프라이트를 OBJ 창 모드로 두고, 창 안에서는 BG2(돌벽)·OBJ(덮개)를 끕니다.
# 게임은 표시 레지스터 사본을 IWRAM 0x03000990 에 두고 매 프레임 복사합니다
# (0x08075D24: +0 -> DISPCNT, +8~+0x4D -> 0x04000008~ DMA). 레지스터에 바로
# 쓰면 다음 복사에 지워져서, 사본을 고칩니다.
IO_SHADOW = 0x03000990
DISPCNT = IO_SHADOW + 0x00
WINOUT = IO_SHADOW + 0x4A
OBJWIN_BIT = 0x8000
# 창 안: BG0·BG1(물결)·효과만 / 창 밖: 전부. BG3 에는 아래 금색 문장이 있어,
# 켜 두면 글자 속에 금색 얼룩이 비칩니다.
WINOUT_TITLE = (0x23 << 8) | 0x3F
# 창을 켰다는 표시. OBJ 팔레트 15 의 0번 색(투명이라 화면에 안 나옴) 자리.
WIN_FLAG = 0x05000200 + PALETTE * 32

# 덮개: 배경판에서 못 칠하는 칸(원본 획이 남는 곳)을 돌벽 그림으로 덮습니다.
# 색은 배경판 팔레트 1 을 OBJ 팔레트 14 로 옮겨 씁니다. 로고 뒤 칸에 두어
# 로고 아래에 깔립니다 (OAM 은 앞 칸이 위).
COVER_PALETTE = 14
COVER_PAL = 0x05000200 + COVER_PALETTE * 32
BG_PAL1 = 0x05000020

# 그림 전체(워드마크 + 「— 청의 천외 —」)를 얹습니다. 둘이 붙어 있어 나눌
# 줄이 없습니다. 이 자리면 그림 속 부제가 배경판 부제 판(x 80~160, y 62~68)
# 위에 겹칩니다 — 판의 일본어 글자는 kotitle --sprite 가 지웁니다.
LOGO_W, LOGO_H = 224, 72
LOGO_X, LOGO_Y = 8, 8

# (폭, 높이) -> (모양, 크기)
SHAPES = {(64, 32): (1, 3), (32, 32): (0, 2), (32, 16): (1, 2), (32, 8): (1, 1),
          (16, 8): (1, 0), (8, 8): (0, 0)}


def layout(w: int, h: int) -> list[tuple[int, int, int, int]]:
    """(x, y, 폭, 높이) 조각. 위에서부터 32·16·8 줄 띠로 나눕니다."""
    out, y = [], 0
    for band in (32, 16, 8):
        while h - y >= band:
            x = 0
            while x < w:
                pw = 64 if band == 32 and w - x >= 64 else 32
                out.append((x, y, pw, band))
                x += pw
            y += band
    if y != h or w % 32:
        raise ValueError(f"{w}x{h} 는 나눌 수 없습니다")
    return out


def attrs(x: int, y: int, w: int, h: int, tile: int,
          palette: int = PALETTE) -> tuple[int, int, int]:
    shape, size = SHAPES[(w, h)]
    return ((y & 0xFF) | (shape << 14),
            (x & 0x1FF) | (size << 14),
            tile | (palette << 12))


def cover_runs(cells: list[tuple[int, int]]) -> list[tuple[int, int, int]]:
    """8×8 칸 자리들을 가로로 이어 (x, y, 폭) 덮개 조각으로. 폭은 32·16·8."""
    out = []
    pos = sorted(set(cells), key=lambda p: (p[1], p[0]))
    i = 0
    while i < len(pos):
        x, y = pos[i]
        j = i
        while j + 1 < len(pos) and pos[j + 1] == (pos[j][0] + 8, y):
            j += 1
        n = j - i + 1                       # 이어진 칸 수
        while n:
            k = 4 if n >= 4 else 2 if n >= 2 else 1
            out.append((x, y, k * 8))
            x += k * 8
            n -= k
        i = j + 1
    return out


def _px_tile(px: bytes) -> bytes:
    """64화소 색 번호 -> 4bpp 타일."""
    return bytes(px[i] | (px[i + 1] << 4) for i in range(0, 64, 2))


def subtitle_box(im) -> tuple[int, int, int, int]:
    """그림 아래쪽 부제(「— 청의 천외 —」) 칸 (x0, y0, x1, y1).

    아래에서부터 불투명한 화소의 가로 폭이 그림 폭의 60% 보다 좁은 줄들이
    부제입니다 (워드마크 줄은 거의 그림 폭 전체).
    """
    a = im.getchannel("A")
    w, h = im.size
    rows = []
    for y in range(h - 1, -1, -1):
        xs = [x for x in range(w) if a.getpixel((x, y)) >= 128]
        if not xs:
            if rows:
                continue
            continue
        if max(xs) - min(xs) >= w * 0.6:
            break
        rows.append((y, min(xs), max(xs)))
    y0, y1 = rows[-1][0], rows[0][0] + 1
    return (min(r[1] for r in rows), y0, max(r[2] for r in rows) + 1, y1)


SUB_EXTRA_TOP = 3        # 부제 글자 윗부분이 워드마크 아랫줄에 걸쳐 있어 위로 조금 더


def _image(art: str):
    """로고 그림 (224×72). 아래쪽 부제는 `subtitle_mask` 로 가려 뺍니다."""
    from PIL import Image
    im = Image.open(art).convert("RGBA")
    im = im.crop(im.getbbox())
    return im.resize((LOGO_W, LOGO_H), Image.LANCZOS)


def subtitle_mask(im) -> list[bool]:
    """부제(「— 청의 천외 —」, 남색 띠 포함) 화소."""
    w, h = im.size
    x0, y0, x1, y1 = subtitle_box(im)
    y0 = max(0, y0 - SUB_EXTRA_TOP)
    a = im.getchannel("A")
    cols = [x for x in range(x0, x1)
            if any(a.getpixel((x, y)) >= 128 for y in range(y0, y1))]
    runs, cur = [], [cols[0]]
    for x in cols[1:]:
        if x - cur[-1] <= 10:               # 줄표와 글자 사이 틈까지 한 덩어리
            cur.append(x)
        else:
            runs.append(cur)
            cur = [x]
    runs.append(cur)
    mid = w // 2
    best = min(runs, key=lambda r: 0 if r[0] <= mid <= r[-1]
               else min(abs(r[0] - mid), abs(r[-1] - mid)))
    gx0, gx1 = best[0], best[-1] + 1
    out = [False] * (w * h)
    for y in range(y0, y1):
        for x in range(gx0, gx1):
            if a.getpixel((x, y)) >= 128:
                out[y * w + x] = True
    return out


def is_body(c) -> bool:
    """글자 몸통 색 — 채도 높은 파랑. 여기를 물결 창으로 바꿉니다.

    로고 그림은 회색 금속 테두리, 아주 어두운 남색 외곽선, 파란 몸통으로
    되어 있습니다. 테두리·외곽선은 그대로 두어야 획이 갈려 보입니다.
    """
    r, g, b, a = c
    return a >= 128 and b >= BODY_MIN_BLUE and b - max(r, g) >= BODY_MIN_SAT


BODY_MIN_BLUE = 90
BODY_MIN_SAT = 60
SPECK_MAX = 12          # 몸통에 둘러싸인 이 크기 이하 덩어리는 몸통으로


EDGE_KEEP = 2           # 글자 가장자리에서 이 거리 안은 외곽선·테두리로 둡니다
DARK_LUM = 80           # 이보다 어두운 안쪽 화소(그림의 금 간 선)는 몸통으로


def fill_interior_dark(body: list, word: list, dark: list, w: int, h: int) -> list:
    """가장자리에서 `EDGE_KEEP` 보다 안쪽의 어두운 화소를 몸통으로.

    그림의 금 간 선은 외곽선과 이어져 있어 `fill_specks` 로는 안 메워집니다.
    외곽선·회색 테두리는 가장자리 가까이에 있으므로 남고, 안쪽의 밝은
    하이라이트도 그대로 둡니다.
    """
    INF = 1 << 20
    dist = [0 if not word[i] else INF for i in range(w * h)]
    frontier = [i for i in range(w * h) if not word[i]]
    d = 0
    while frontier:
        d += 1
        nxt = []
        for i in frontier:
            x, y = i % w, i // w
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < w and 0 <= ny < h:
                        j = ny * w + nx
                        if dist[j] > d:
                            dist[j] = d
                            nxt.append(j)
        frontier = nxt
    # 그림 테두리 밖도 글자 밖으로 봅니다
    for i in range(w * h):
        x, y = i % w, i // w
        dist[i] = min(dist[i], x + 1, y + 1, w - x, h - y)
    return [1 if body[i] or (word[i] and dark[i] and dist[i] > EDGE_KEEP) else 0
            for i in range(w * h)]


def fill_specks(body: list, word: list, w: int, h: int) -> list:
    """몸통 안에 박힌 작은 비몸통 덩어리(그림의 짙은 점)를 몸통으로 메웁니다.

    그대로 두면 물결 속에 검은 얼룩으로 보입니다. 글자 밖과 맞닿았거나
    `SPECK_MAX` 보다 큰 덩어리(획을 가르는 외곽선)는 남깁니다.
    """
    out = list(body)
    seen = [False] * (w * h)
    for start in range(w * h):
        if body[start] or not word[start] or seen[start]:
            continue
        comp, stack, edge = [], [start], False
        seen[start] = True
        while stack:
            i = stack.pop()
            comp.append(i)
            x, y = i % w, i // w
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if not (0 <= nx < w and 0 <= ny < h):
                    edge = True
                    continue
                j = ny * w + nx
                if not word[j]:
                    edge = True
                elif not body[j] and not seen[j]:
                    seen[j] = True
                    stack.append(j)
        if not edge and len(comp) <= SPECK_MAX:
            for i in comp:
                out[i] = 1
    return out


def layers(art: str):
    """(창 마스크, 일반 그림).

    창 마스크는 워드마크 글자 몸통(파란 부분) — 여기로 원본처럼 뒤의
    물결 층이 비칩니다. 일반 그림은 글자의 금속 테두리·외곽선입니다.
    부제는 넣지 않습니다 — 배경판의 원래 부제 판에 한글로 그립니다.
    """
    from PIL import Image
    im = _image(art)
    w, h = im.size
    sub = subtitle_mask(im)
    src = im.load()
    body = [0] * (w * h)
    normal = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dst = normal.load()
    for i in range(w * h):
        x, y = i % w, i // w
        c = src[x, y]
        if c[3] < 128 or sub[i]:
            continue                       # 부제는 배경판 원래 판에 (kotitle)
        if is_body(c):
            body[i] = 1
    word = [src[i % w, i // w][3] >= 128 and not sub[i] for i in range(w * h)]

    def lum(c):
        return (c[0] * 3 + c[1] * 6 + c[2]) / 10
    dark = [lum(src[i % w, i // w]) < DARK_LUM for i in range(w * h)]
    body = fill_interior_dark(body, word, dark, w, h)
    body = fill_specks(body, word, w, h)
    for i in range(w * h):
        if word[i] and not body[i]:
            dst[i % w, i // w] = src[i % w, i // w]
    return body, normal


def _quantize(im):
    """(색 번호 그림, 팔레트 32바이트). 0번은 투명."""
    from PIL import Image
    alpha = im.getchannel("A")
    rgb = Image.new("RGB", im.size, (0, 0, 0))
    rgb.paste(im, mask=alpha)
    q = rgb.quantize(colors=15, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()[:45]
    px = [0 if a < 128 else i + 1
          for i, a in zip(q.getdata(), alpha.getdata())]
    out = bytearray(32)
    for i in range(15):
        r, g, b = pal[i * 3:i * 3 + 3]
        v = (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10)
        out[2 + i * 2:4 + i * 2] = v.to_bytes(2, "little")
    return px, bytes(out)


def _tile(px: list[int], x0: int, y0: int) -> bytes:
    out = bytearray(32)
    for y in range(8):
        for x in range(0, 8, 2):
            a = px[(y0 + y) * LOGO_W + x0 + x]
            b = px[(y0 + y) * LOGO_W + x0 + x + 1]
            out[y * 4 + x // 2] = a | (b << 4)
    return bytes(out)


def build_assets(art: str, covers=()) -> dict:
    """로고 타일·팔레트·OAM 표. ROM 은 건드리지 않습니다.

    `covers` 는 `kotitle.cover_cells` 의 (화면 x, 화면 y, 64화소) 목록입니다.
    OAM 은 [테두리·부제] [창] [덮개] 순서입니다 (앞 칸이 위).
    """
    body, normal = layers(art)
    px, palette = _quantize(normal)
    tiles = bytearray()

    def pieces(src, mode):
        out = []
        for x, y, w, h in layout(LOGO_W, LOGO_H):
            piece = [_tile(src, x + tx * 8, y + ty * 8)
                     for ty in range(h // 8) for tx in range(w // 8)]
            if not any(any(t) for t in piece):
                continue                   # 다 투명한 조각은 건너뜁니다
            a0, a1, a2 = attrs(LOGO_X + x, LOGO_Y + y, w, h,
                               TILE_BASE + len(tiles) // 32)
            out.append((a0 | (mode << 10), a1, a2))
            tiles.extend(b"".join(piece))
        return out
    oam = pieces(px, 0)
    windows = pieces(body, 2)              # OBJ 창 모드
    cell = {(x, y): p for x, y, p in covers}
    cov = []
    for x, y, w in cover_runs(list(cell)):
        cov.append(attrs(x, y, w, 8, TILE_BASE + len(tiles) // 32,
                         COVER_PALETTE))
        tiles += b"".join(_px_tile(cell[(x + k * 8, y)]) for k in range(w // 8))
    total = len(oam) + len(windows) + len(cov)
    if FIRST_SLOT + total > 128:
        raise ValueError(f"OAM 칸이 모자랍니다: {total}")
    if TILE_BASE + len(tiles) // 32 > 0x400:
        raise ValueError(f"OBJ 타일이 모자랍니다: {len(tiles) // 32}")
    sig = next(i for i in range(0, len(tiles), 4) if any(tiles[i:i + 4]))
    return {"tiles": bytes(tiles), "lz": gbalz.compress(bytes(tiles)),
            "palette": palette, "oam": oam, "windows": windows, "covers": cov,
            "sig": (sig, int.from_bytes(tiles[sig:sig + 4], "little"))}


def table_bytes(oam) -> bytes:
    return b"".join(v.to_bytes(2, "little") for e in oam for v in e)


def build_hook(at: int, table: int, count: int, lz: int, palette: int,
               sig: tuple[int, int]) -> bytes:
    dst = OBJ_VRAM + TILE_BASE * 32
    first = OAM_SHADOW + FIRST_SLOT * 8
    a = thumb.Asm(at)
    a.push([4, 5, 6, 7], lr=True)
    a.ldr_pool(0, BGCNT)
    a.ldr_imm(1, 0, 0)
    a.ldr_pool(2, TITLE_BGCNT01)
    a.cmp_reg(1, 2)
    a.bne("hide")
    a.ldr_imm(1, 0, 4)
    a.ldr_pool(2, TITLE_BGCNT23)
    a.cmp_reg(1, 2)
    a.bne("hide")
    a.ldr_pool(0, TITLE_MAP_AT)
    a.ldrh_imm(1, 0, 0)
    a.ldr_pool(2, TITLE_MAP_VAL)
    a.cmp_reg(1, 2)
    a.bne("hide")

    # --- 타일이 아직 없으면 싣는다 (서명 워드로 판단) ---
    a.ldr_pool(0, dst + sig[0])
    a.ldr_imm(1, 0, 0)
    a.ldr_pool(2, sig[1])
    a.cmp_reg(1, 2)
    a.beq("show")
    a.ldr_pool(0, lz)
    a.ldr_pool(1, dst)
    a.swi(0x12)                            # LZ77UnCompReadNormalWrite16bit
    a.ldr_pool(0, palette)
    a.ldr_pool(1, OBJ_PAL)
    a.movs(2, 8)
    a.mark("pal")
    a.ldr_imm(3, 0, 0)
    a.str_imm(3, 1, 0)
    a.adds_imm8(0, 4)
    a.adds_imm8(1, 4)
    a.subs_imm8(2, 1)
    a.bne("pal")

    # --- 덮개 색 = 배경판 팔레트 1. 매 프레임 옮겨 페이드를 따라갑니다
    #     (한 번만 옮기면 흰 화면에서 밝아지는 도중의 색이 굳습니다) ---
    a.mark("show")
    a.ldr_pool(0, BG_PAL1)
    a.ldr_pool(1, COVER_PAL)
    a.movs(2, 8)
    a.mark("pal2")
    a.ldr_imm(3, 0, 0)
    a.str_imm(3, 1, 0)
    a.adds_imm8(0, 4)
    a.adds_imm8(1, 4)
    a.subs_imm8(2, 1)
    a.bne("pal2")

    # --- 로고 OAM: attr0~2 만 (+6 은 게임의 아핀 파라미터) ---
    a.ldr_pool(0, table)
    a.ldr_pool(1, first)
    a.movs(2, count)
    a.mark("put")
    for off in (0, 2, 4):
        a.ldrh_imm(3, 0, off)
        a.strh_imm(3, 1, off)
    a.adds_imm8(0, 6)
    a.adds_imm8(1, 8)
    a.subs_imm8(2, 1)
    a.bne("put")
    # OBJ 창 켜기 — 글자 안쪽으로 물결이 비칩니다
    a.ldr_pool(0, DISPCNT)
    a.ldrh_imm(1, 0, 0)
    a.ldr_pool(2, OBJWIN_BIT)
    a.orrs(1, 2)
    a.strh_imm(1, 0, 0)
    a.ldr_pool(0, WINOUT)
    a.ldr_pool(1, WINOUT_TITLE)
    a.strh_imm(1, 0, 0)
    a.ldr_pool(0, WIN_FLAG)
    a.movs(1, 1)
    a.strh_imm(1, 0, 0)
    a.b("done")

    # --- 타이틀이 아니면 로고 칸만 숨긴다 ---
    a.mark("hide")
    # 타이틀에서 OBJ 창을 켰으면(표시가 있으면) 되돌립니다
    a.ldr_pool(0, WIN_FLAG)
    a.ldrh_imm(1, 0, 0)
    a.cmp_imm(1, 1)
    a.bne("hide2")
    a.movs(1, 0)
    a.strh_imm(1, 0, 0)
    a.ldr_pool(0, DISPCNT)
    a.ldrh_imm(1, 0, 0)
    a.ldr_pool(2, OBJWIN_BIT)
    a.bics(1, 2)
    a.strh_imm(1, 0, 0)
    a.ldr_pool(0, WINOUT)
    a.movs(1, 0)
    a.strh_imm(1, 0, 0)
    a.mark("hide2")
    a.ldr_pool(0, table)
    a.ldr_pool(1, first)
    a.movs(2, count)
    a.movs(5, 2)
    a.lsls(5, 5, 8)                        # attr0 = 0x0200 (숨김)
    a.mark("chk")
    a.ldrh_imm(3, 1, 4)
    a.ldrh_imm(4, 0, 4)
    a.cmp_reg(3, 4)
    a.bne("next")
    a.strh_imm(5, 1, 0)
    a.mark("next")
    a.adds_imm8(0, 6)
    a.adds_imm8(1, 8)
    a.subs_imm8(2, 1)
    a.bne("chk")

    a.mark("done")
    a.pop([4, 5, 6, 7])
    a.pop([3])
    a.ldr_pool(1, DMA3)
    a.ldr_pool(0, OAM_SHADOW)
    a.bx(3)
    return a.assemble()


def install(rom: bytearray, alloc, art: str, covers=None) -> dict:
    """`alloc(크기, align, near)` 로 자리를 받아 ROM 에 넣습니다.

    훅은 `bl` 이 닿도록 호출 지점 가까이(`near=SITE`)에 둡니다.
    """
    o = SITE - common.ROM_BASE
    if bytes(rom[o:o + 4]) != SITE_ORIG:
        raise ValueError(f"0x{SITE:08X} 가 원본 OAM 전송 코드가 아닙니다")
    if covers is None:
        covers = kotitle.cover_cells(kotitle.load_tiles(rom))
    a = build_assets(art, covers)
    entries = a["oam"] + a["windows"] + a["covers"]
    table = table_bytes(entries)
    places = {}
    for name, data in (("lz", a["lz"]), ("palette", a["palette"]),
                       ("table", table)):
        at = alloc(len(data), 4, None)
        rom[at:at + len(data)] = data
        places[name] = common.off_to_ptr(at)
    # 크기는 실제 주소로 잽니다. 임시값(0)을 넣으면 리터럴 풀의 같은 값이
    # 하나로 합쳐져 작게 나오고, 뒤에 받은 자리가 훅 끝을 덮어씁니다.
    size = len(build_hook(common.ROM_BASE, places["table"], len(entries),
                          places["lz"], places["palette"], a["sig"]))
    at = alloc(size, 4, SITE)
    hook = build_hook(common.off_to_ptr(at), places["table"], len(entries),
                      places["lz"], places["palette"], a["sig"])
    if len(hook) != size:
        raise ValueError(f"훅 크기가 달라졌습니다: {len(hook)} != {size}")
    rom[at:at + len(hook)] = hook
    rom[o:o + 4] = thumb.bl_bytes(SITE, common.off_to_ptr(at))
    return {"훅": common.off_to_ptr(at), "자료": places["lz"],
            "표": places["table"], "팔레트": places["palette"],
            "조각": len(entries), "덮개": len(a["covers"]),
            "타일": len(a["tiles"]) // 32, "압축": len(a["lz"]),
            "바이트": len(a["lz"]) + 32 + len(table) + len(hook)}
