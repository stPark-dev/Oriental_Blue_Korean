#!/usr/bin/env python3
"""TTF/OTF/BDF 를 GBA 타일 폰트로 변환합니다 (Pillow 필요).

한글 서브셋 비트맵 폰트를 만들 때 씁니다. 출력은
  - <out>.bin   : 글리프 비트맵 (1bpp 또는 4bpp, 글자당 고정 크기)
  - <out>.wid   : 글자별 실제 폭 (VWF용, 1바이트씩)
  - <out>.json  : 코드 <-> 문자 매핑

    python3 tools/mkfont.py font/Galmuri9.ttf font/charset.txt \
        -o build/kofont --size 12 --cell 12x12 --bpp 1
"""
from __future__ import annotations

import argparse
import json
import os
import sys

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("Pillow가 필요합니다:  pip install Pillow")


def parse_cell(text: str) -> tuple[int, int]:
    w, _, h = text.lower().partition("x")
    return int(w), int(h)


def render(font, ch: str, cw: int, chh: int, baseline: int,
           threshold: int) -> tuple[list[list[int]], int]:
    img = Image.new("L", (cw * 2, chh * 2), 0)
    d = ImageDraw.Draw(img)
    d.text((0, baseline), ch, font=font, fill=255, anchor="ls")

    px = img.load()
    rows = [[1 if px[x, y] >= threshold else 0 for x in range(cw)]
            for y in range(chh)]

    width = 0
    for y in range(chh):
        for x in range(cw * 2):
            if px[x, y] >= threshold and x + 1 > width:
                width = x + 1
    return rows, min(width, cw)


def pack_1bpp(rows: list[list[int]]) -> bytes:
    out = bytearray()
    for row in rows:
        for i in range(0, len(row), 8):
            byte = 0
            for b, v in enumerate(row[i:i + 8]):
                byte |= v << (7 - b)
            out.append(byte)
    return bytes(out)


def pack_4bpp(rows: list[list[int]], level: int = 15) -> bytes:
    """GBA 4bpp: 한 바이트에 픽셀 2개, 낮은 니블이 먼저."""
    out = bytearray()
    for row in rows:
        for i in range(0, len(row), 2):
            lo = level if row[i] else 0
            hi = level if i + 1 < len(row) and row[i + 1] else 0
            out.append((hi << 4) | lo)
    return bytes(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="한글 서브셋 GBA 폰트 생성")
    ap.add_argument("font", help="TTF/OTF/BDF 경로")
    ap.add_argument("charset", help="문자 집합 파일 (UTF-8, tools/charset.py 산출물)")
    ap.add_argument("-o", "--out", required=True, help="출력 경로 접두사")
    ap.add_argument("--size", type=int, default=12, help="폰트 픽셀 크기")
    ap.add_argument("--cell", default="12x12", help="셀 크기 WxH")
    ap.add_argument("--baseline", type=int, default=None, help="베이스라인 Y")
    ap.add_argument("--bpp", type=int, choices=[1, 4], default=1)
    ap.add_argument("--threshold", type=int, default=128)
    ap.add_argument("--preview", help="미리보기 PNG 경로")
    args = ap.parse_args()

    cw, chh = parse_cell(args.cell)
    baseline = args.baseline if args.baseline is not None else chh - 2

    with open(args.charset, "r", encoding="utf-8") as f:
        chars = sorted(set(f.read()) - set("\r\n"))
    if not chars:
        sys.exit("문자 집합이 비어 있습니다.")

    try:
        font = ImageFont.truetype(args.font, args.size)
    except OSError:
        font = ImageFont.load(args.font)

    pack = pack_1bpp if args.bpp == 1 else pack_4bpp
    data = bytearray()
    widths = bytearray()
    blanks: list[str] = []

    for ch in chars:
        rows, w = render(font, ch, cw, chh, baseline, args.threshold)
        if w == 0 and not ch.isspace():
            blanks.append(ch)
        data += pack(rows)
        widths.append(max(w + 1, 3) if not ch.isspace() else max(cw // 2, 3))

    glyph_size = len(data) // len(chars)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out + ".bin", "wb") as f:
        f.write(data)
    with open(args.out + ".wid", "wb") as f:
        f.write(widths)
    with open(args.out + ".json", "w", encoding="utf-8") as f:
        json.dump({
            "cell": [cw, chh], "bpp": args.bpp, "glyph_bytes": glyph_size,
            "count": len(chars), "source": os.path.basename(args.font),
            "chars": "".join(chars),
        }, f, ensure_ascii=False, indent=2)

    print(f"글자 {len(chars)}자 / 글리프 {glyph_size}바이트 / 전체 {len(data):,}바이트")
    print(f"평균 폭 {sum(widths) / len(widths):.1f}px")
    if blanks:
        print(f"[!] 글립이 비어 있는 문자 {len(blanks)}자: {''.join(blanks[:30])}")

    if args.preview:
        cols = 32
        rows_n = (len(chars) + cols - 1) // cols
        img = Image.new("L", (cols * cw, rows_n * chh), 0)
        d = ImageDraw.Draw(img)
        for i, ch in enumerate(chars):
            d.text(((i % cols) * cw, (i // cols) * chh + baseline), ch,
                   font=font, fill=255, anchor="ls")
        img.point(lambda v: 255 if v >= args.threshold else 0).save(args.preview)
        print(f"미리보기: {args.preview}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
