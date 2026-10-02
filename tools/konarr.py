#!/usr/bin/env python3
"""오프닝 나레이션 한글화.

프롤로그의 `どこまでもつづく　青い空と…` 는 **문자열 표에 없습니다.** 표
805개를 다 펴 봐도 없고, 대응표로 인코딩한 바이트열도 평문에 없습니다.
정체는 **16×16 스프라이트**입니다.

    글리프 그림   ROM 0x8E4508 + attr2*32   (한 글자 = 타일 4장, 1차원 배치)
    스프라이트표  ROM 0x8E6718 부터 8바이트 × 96
    같은 표 사본  ROM 0x8E4208 (x 만 다름 — 미끄러져 들어오는 애니메이션)

한 칸은 OAM 과 같은 모양입니다 — `attr0`(y·크기) `attr1`(x·반전·크기)
`attr2`(글리프), 뒤에 2바이트 여백.

구조를 푸는 데 쓴 방법:

1. `--probe` 로 글리프 칸마다 번호를 새긴 롬을 만들어 실기에서 찍었습니다.
   화면에 뜬 숫자가 곧 그 자리의 글리프 번호입니다.
2. 거기서 얻은 글리프↔글자 대응으로 표 전체를 해독했습니다.

결론은 이렇습니다.

    한 줄     = 레코드 묶음 (`LINES`)
    글자 순서 = **x 내림차순** (표에는 오른쪽 글자가 먼저 들어 있습니다)
    글리프    = `attr2` (VRAM 에 올릴 때 타일 0x30 이 더해집니다)

한글화는 `attr2`(글리프)와 x 를 바꿉니다. 원문보다 짧은 줄은 남는 칸에
빈 글리프를 넣습니다.

x 는 한국어 띄어쓰기에 맞춰 다시 계산합니다 (`layout`). 원문 x 는 가나 폭의
가변 간격이라 그대로 쓰면 줄마다 한 곳밖에 띄울 수 없어, 「끝도없이이어지는」
처럼 붙어 보였습니다. 두 표는 같은 글을 서로 반대 방향으로 담은 두 프레임
(한쪽에서 밀려 들어오는 애니메이션)이고, 레코드마다 **A.x + B.x 가 일정**
합니다. 그래서 B 표에 새 x 를 쓰고 A 표는 그 합을 지켜 옮깁니다.

「」 는 칸 한쪽(「 는 오른쪽, 」 는 왼쪽)에 붙여 그리고, 반대쪽 간격만
좁힙니다.

글자는 세 가지 색으로 그립니다 (팔레트는 페이드 애니메이션이 돌립니다).

    3 = 획      1 = 획 둘레 1픽셀   (원본은 바깥에 2 를 한 겹 더 두르지만,
                                    한글은 획이 촘촘해서 한 겹만 두릅니다)
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

TABLES = (0x8E4208, 0x8E6718)   # 같은 글을 담은 두 프레임
SPRITE_COUNT = 96
GLYPH_AT = 0x8E4508             # attr2 == 0 인 글리프
GLYPH_END = 0x8E6700            # 여기까지가 글리프 (바로 뒤가 표)
CELL = 16
FONT_SIZE = 14
STROKE, EDGE, RIM = 3, 1, 2

# 줄을 이루는 레코드. x 내림차순이 곧 읽는 순서입니다.
LINES: dict[str, list[int]] = {
    "L1": list(range(25, 37)),                     # どこまでもつづく　青い空と
    "L2": list(range(10, 25)),                     # どこまでもつづく　青い海をうつし
    "L3": list(range(0, 10)),                      # ここに　青の大地がある
    "L4": [47] + list(range(67, 75)),              # この地に　すむものは
    "L5": list(range(51, 66)),                     # たとえ　それが小さな命であろうと
    "L6": list(range(37, 47)) + [48, 49, 50, 66],  # ＜青＞のいみを　しるものである
    "L7": [85, 89, 90, 92, 93, 94, 95],            # ここは　青の大地
    "L8": list(range(78, 85)) + [86, 87, 88, 91],  # すべての命が　いきる大地
}
DOTS = [75, 76, 77]             # 「・・・」 — 건드리지 않습니다

# 띄어쓰기는 한국어대로 합니다. 원문 간격(가나 폭)을 그대로 쓰던 때는 줄마다
# 한 곳밖에 띄울 수 없어 「끝도없이이어지는」처럼 붙어 보였습니다. 지금은
# 자리(x)를 다시 계산합니다 (`layout`).
TEXT: dict[str, str] = {
    "L1": "끝도없이 이어지는 푸른하늘",
    "L2": "끝도없이 이어지는 푸른바다를 비춰",
    "L3": "여기에 푸른대지가 있다",
    "L4": "이 땅에서 사는 것들은",
    "L5": "그것이 비록 작디작은 목숨일지라도",
    "L6": "「푸름」의 뜻을 아는 존재들이다",
    "L7": "여기는 푸른 대지",
    "L8": "모든 목숨들이 살아가는 땅",
}

# 배치. x 는 B 표(0x8E6718) 기준 — 읽는 순서로 줄어듭니다. A 표는 줄마다
# A.x + B.x 가 일정한 사본(반대쪽에서 밀려 들어오는 프레임)이라 그 합을
# 지켜 따라 옮깁니다.
ADV = 14                # 글자 사이
SPACE = 8               # 띄어쓰기 자리에 더하는 간격
BRACKET_ADV = 9         # 「 앞·」 뒤 간격 (낫표는 칸 한쪽에 붙여 그림)
X_MIN, X_MAX = -120, 104
BRACKETS = "「」"


def layout(text: str, center: float) -> list[int]:
    """띄어쓴 줄 → 글자마다 x (읽는 순서, 내림차순). 화면에 안 들면 좁힙니다."""
    chars = [c for c in text if c != " "]
    spaced, k = set(), 0
    for c in text:
        if c == " ":
            spaced.add(k - 1)
        else:
            k += 1
    for adv, space in ((ADV, SPACE), (ADV - 1, SPACE), (ADV - 1, SPACE - 2)):
        steps = []
        for j in range(len(chars) - 1):
            # 「 는 칸 오른쪽, 」 는 왼쪽에 그리므로 붙은 쪽(「 다음, 」 앞)은
            # 보통 간격이어야 겹치지 않고, 반대쪽만 좁힐 수 있습니다.
            a, b = chars[j], chars[j + 1]
            step = BRACKET_ADV if b == "「" or a == "」" else adv
            steps.append(step + (space if j in spaced else 0))
        span = sum(steps)
        first = round(center + span / 2)
        xs = [first]
        for st in steps:
            xs.append(xs[-1] - st)
        if xs[0] > X_MAX:
            xs = [x - (xs[0] - X_MAX) for x in xs]
        if xs[-1] < X_MIN:
            xs = [x + (X_MIN - xs[-1]) for x in xs]
        if xs[0] <= X_MAX and xs[-1] >= X_MIN:
            return xs
    raise NarrError(f"줄이 화면에 들지 않습니다: {text}")


class NarrError(Exception):
    pass


def glyph_slots() -> int:
    """쓸 수 있는 16×16 글리프 칸 수."""
    return (GLYPH_END - GLYPH_AT) // (4 * 32)


def read_sprites(rom: bytes, table: int) -> list[dict]:
    out = []
    for i in range(SPRITE_COUNT):
        a = table + i * 8
        a1 = common.u16(rom, a + 2)
        x = a1 & 0x1FF
        out.append({"i": i, "y": common.u8(rom, a), "x": x - 512 if x >= 256 else x,
                    "tile": common.u16(rom, a + 4) & 0x3FF})
    return out


def order_of(sprites: list[dict], records: list[int]) -> list[int]:
    """한 줄의 레코드를 **읽는 순서**(x 내림차순)로."""
    return [s["i"] for s in sorted((sprites[i] for i in records),
                                   key=lambda s: -s["x"])]


def render_cell(ch: str, font) -> bytearray:
    """글자 하나를 16×16 색 번호로. 획 3, 둘레 1, 그 바깥 2."""
    from PIL import Image, ImageDraw
    img = Image.new("L", (CELL, CELL), 0)
    d = ImageDraw.Draw(img)
    w = d.textlength(ch, font=font)
    x = (CELL - w) / 2
    if ch in BRACKETS:                  # 낫표는 글자 쪽(「 는 오른쪽, 」 는 왼쪽)에
        x0, _, x1, _ = d.textbbox((0, 0), ch, font=font)
        x = CELL - 2 - x1 if ch == "「" else 2 - x0
    d.text((x, (CELL - FONT_SIZE) / 2 - 1), ch, font=font, fill=255)
    src = img.load()
    ink = [[1 if src[x, y] > 110 else 0 for x in range(CELL)] for y in range(CELL)]
    out = bytearray(CELL * CELL)
    for r, colour in ((0, STROKE), (1, EDGE)):
        for y in range(CELL):
            for x in range(CELL):
                if not out[y * CELL + x] and _within(ink, x, y, r):
                    out[y * CELL + x] = colour
    return out


def _within(ink, x: int, y: int, r: int) -> bool:
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            ny, nx = y + dy, x + dx
            if 0 <= ny < CELL and 0 <= nx < CELL and ink[ny][nx]:
                return True
    return False


def write_cell(rom: bytearray, slot: int, cell: bytes) -> None:
    """16×16 색 번호를 타일 4장(좌상·우상·좌하·우하)으로 씁니다."""
    for j, (ox, oy) in enumerate(((0, 0), (8, 0), (0, 8), (8, 8))):
        base = GLYPH_AT + (slot + j) * 32
        if base + 32 > GLYPH_END:
            raise NarrError(f"글리프 영역을 넘습니다 (attr2 0x{slot:03X})")
        for y in range(8):
            for x in range(0, 8, 2):
                lo = cell[(oy + y) * CELL + ox + x]
                hi = cell[(oy + y) * CELL + ox + x + 1]
                rom[base + y * 4 + x // 2] = (lo & 0xF) | ((hi & 0xF) << 4)


def set_x(rom: bytearray, table: int, record: int, x: int) -> None:
    """레코드의 x 만 바꿉니다 (attr1 의 반전·크기 비트는 그대로)."""
    a = table + record * 8 + 2
    common.w16(rom, a, (common.u16(rom, a) & 0xFE00) | (x & 0x1FF))


def set_glyph(rom: bytearray, table: int, record: int, slot: int) -> None:
    """레코드의 글리프만 바꿉니다 (자리·플래그는 그대로)."""
    common.w16(rom, table + record * 8 + 4, slot & 0x3FF)


def translate(rom: bytearray, texts: dict[str, str], font) -> dict:
    """줄마다 한글을 앉힙니다. 글리프(`attr2`)와 자리(x)를 고칩니다."""
    sprites = read_sprites(rom, TABLES[1])
    limit = min(sprites[i]["tile"] for i in DOTS)   # 「・・・」 글리프는 남겨 둡니다
    slots: dict[str, int] = {}
    nxt = 0

    def slot_for(ch: str) -> int:
        nonlocal nxt
        if ch not in slots:
            if nxt + 4 > limit:
                raise NarrError(f"글리프 칸 부족 (0x{limit:03X} 앞까지만 쓸 수 있습니다)")
            write_cell(rom, nxt, render_cell(ch, font))
            slots[ch] = nxt
            nxt += 4
        return slots[ch]

    plan: dict[int, int] = {}
    moves: dict[int, int] = {}          # 레코드 -> B 표 x 이동량
    other = read_sprites(rom, TABLES[0])
    for name, records in LINES.items():
        text = texts.get(name)
        if text is None:
            continue
        chars = [c for c in text if c != " "]
        if len(chars) > len(records):
            raise NarrError(f"{name}: 글자 {len(chars)}개 > 칸 {len(records)}개")
        order = order_of(sprites, records)
        xs0 = [sprites[i]["x"] for i in order]
        xs = layout(text, (xs0[0] + xs0[-1]) / 2)
        for pos, rec in enumerate(order):
            plan[rec] = slot_for(chars[pos]) if pos < len(chars) else -1
            if pos < len(chars):
                moves[rec] = xs[pos] - sprites[rec]["x"]
    blank = -1
    if any(v == -1 for v in plan.values()):
        blank = nxt
        write_cell(rom, blank, bytearray(CELL * CELL))
        nxt += 4
    for rec, slot in plan.items():
        for table in TABLES:
            set_glyph(rom, table, rec, blank if slot == -1 else slot)
    for rec, dx in moves.items():       # B 는 더하고, A 는 합을 지켜 뺍니다
        set_x(rom, TABLES[1], rec, sprites[rec]["x"] + dx)
        set_x(rom, TABLES[0], rec, other[rec]["x"] - dx)
    return {"줄": sum(1 for n in LINES if n in texts),
            "글자": sum(1 for v in plan.values() if v != -1),
            "글리프": len(slots), "여유 칸": (limit - nxt) // 4}


def probe(rom: bytearray) -> dict:
    """글리프 칸마다 번호를 새깁니다 — 화면에서 자리를 읽기 위한 시험용."""
    from PIL import Image, ImageDraw, ImageFont
    small = ImageFont.truetype("font/Galmuri7.ttf", 8)
    n = glyph_slots()
    for k in range(n):
        img = Image.new("L", (CELL, CELL), 0)
        ImageDraw.Draw(img).text((1, 3), f"{k:02d}", font=small, fill=255)
        src = img.load()
        cell = bytearray(CELL * CELL)
        for y in range(CELL):
            for x in range(CELL):
                if src[x, y] > 110:
                    cell[y * CELL + x] = STROKE
        write_cell(rom, k * 4, cell)
    return {"칸": n}


def main() -> int:
    ap = argparse.ArgumentParser(description="오프닝 나레이션 한글화")
    ap.add_argument("rom")
    ap.add_argument("-o", "--out")
    ap.add_argument("--font", default="font/Galmuri14.ttf")
    ap.add_argument("--probe", action="store_true", help="칸 번호를 새긴 시험용 롬")
    args = ap.parse_args()

    from PIL import ImageFont
    if not os.path.exists(args.font):
        print(f"[!] 폰트가 없습니다: {args.font}")
        return 1
    rom = bytearray(common.load(args.rom))
    try:
        stats = (probe(rom) if args.probe
                 else translate(rom, TEXT, ImageFont.truetype(args.font, FONT_SIZE)))
    except NarrError as e:
        print(f"[!] {e}")
        return 1
    common.save(args.out or args.rom, bytes(rom))
    print("  오프닝 나레이션  " + " · ".join(f"{k} {v}" for k, v in stats.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
