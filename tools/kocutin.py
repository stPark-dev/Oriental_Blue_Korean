#!/usr/bin/env python3
"""대도 초반 연출의 글자 그림 「たすけて」를 「도와줘」로 바꿉니다.

성 밖으로 나와 남쪽으로 걸으면 푸른 기운의 소녀 → 검은 화면에
「たすけて」 → 소녀 얼굴이 잠깐 스쳐 갑니다. 글자는 대사가 아니라
그림입니다 — 4bpp 스프라이트 셋(OBJ 타일 24~41, 1D 매핑, 팔레트 0)이고,
ROM 의 압축 안 된 576바이트를 그대로 VRAM 에 올립니다. 같은 그림이 ROM
두 곳에 있어 둘 다 바꿉니다.

    화면 x  84–115  32×16  타일 34–41
            116–147 32×16  타일 26–33
            148–155  8×16  타일 24–25

색 번호: 1 검정 배경(불투명), 2–6 회색에서 흰색. `art/tasukete_ko.png` 는
이 번호를 그대로 담은 72×16 그림입니다 (Noto Serif CJK SemiBold 16px 를
8배로 그려 줄이고 5단계로 나눔).

    python3 tools/kocutin.py build/patched.gba
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys

W, H = 72, 16
SIZE = 18 * 32
SITES = (0x436160, 0x4374A0)
ORIG_SHA1 = "035ceaa436a49df8fdbd990f5cbaa34852bba767"
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "art",
                   "tasukete_ko.png")

# (그림 x, 폭, 첫 타일) — 타일 번호는 ROM 안 순서(24 부터)
PIECES = ((0, 32, 34), (32, 32, 26), (64, 8, 24))
FIRST_TILE = 24


class CutinError(Exception):
    pass


def _tile_xy():
    """ROM 타일 순서대로 (그림 x, 그림 y) 왼쪽 위."""
    out = {}
    for x0, w, first in PIECES:
        cols = w // 8
        for k in range(cols * 2):
            out[first - FIRST_TILE + k] = (x0 + (k % cols) * 8, (k // cols) * 8)
    return [out[i] for i in range(SIZE // 32)]


def to_tiles(px: list[int]) -> bytes:
    """W×H 색 번호 -> 4bpp 타일 576바이트."""
    out = bytearray(SIZE)
    for t, (tx, ty) in enumerate(_tile_xy()):
        for y in range(8):
            for x in range(0, 8, 2):
                lo = px[(ty + y) * W + tx + x]
                hi = px[(ty + y) * W + tx + x + 1]
                out[t * 32 + y * 4 + x // 2] = lo | (hi << 4)
    return bytes(out)


def from_tiles(data: bytes) -> list[int]:
    px = [0] * (W * H)
    for t, (tx, ty) in enumerate(_tile_xy()):
        for y in range(8):
            for x in range(8):
                b = data[t * 32 + y * 4 + x // 2]
                px[(ty + y) * W + tx + x] = (b >> 4) if x & 1 else (b & 15)
    return px


def load_art(path: str) -> list[int]:
    from PIL import Image
    im = Image.open(path)
    if im.mode != "P" or im.size != (W, H):
        raise CutinError(f"{path}: {W}×{H} 색 번호(P) 그림이어야 합니다")
    px = list(im.getdata())
    if not set(px) <= set(range(1, 7)):
        raise CutinError(f"{path}: 색 번호는 1–6 만 씁니다")
    return px


def install(rom: bytearray, art: str = ART) -> None:
    data = to_tiles(load_art(art))
    for o in SITES:
        if hashlib.sha1(rom[o:o + SIZE]).hexdigest() != ORIG_SHA1:
            raise CutinError(f"0x{o:06X} 가 원래 「たすけて」 그림이 아닙니다")
        rom[o:o + SIZE] = data


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("rom")
    ap.add_argument("--art", default=ART)
    args = ap.parse_args()
    with open(args.rom, "rb") as f:
        rom = bytearray(f.read())
    install(rom, args.art)
    with open(args.rom, "wb") as f:
        f.write(rom)
    print(f"  연출 글자 그림  「도와줘」 {len(SITES)}곳")
    return 0


if __name__ == "__main__":
    sys.exit(main())
