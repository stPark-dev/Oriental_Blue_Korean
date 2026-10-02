#!/usr/bin/env python3
"""메뉴 항목이 제 칸에 들어가는지 검사합니다.

메뉴 화면의 항목 하나하나는 이벤트 VM 레코드(20바이트)로 놓입니다.
핸들러 `0x08039CCD` 레코드는 `DF3908` 의 문자열 번호와 **칸 수**를 갖고,
메뉴 렌더러(`0x0801C574`)는 그 칸 수만큼 코드를 그린 뒤 멈춥니다.
넘친 글자는 소리 없이 잘립니다 (필드 메뉴의 「소지품」이 「소지」로 나왔습니다).

    +4  u16 열   +6  u16 행   +8  u16 칸 수   +10 u16 줄 수
    +12 u32 핸들러   +16 u32 문자열 번호

메뉴 렌더러는 한글 뒤 코드를 그리지도 세지도 않으므로
(`kohook.build_menu_skip`) 음절도 가나처럼 한 칸입니다.
칸 수가 0 이거나 여러 줄짜리 레코드는 칸 수의 뜻이 달라 검사하지 않습니다.

기록 화면의 장소 이름(여관표 DE7C30 의 3번째마다)은 칸이 아니라
**바이트**로 잘리므로 따로 봅니다 (`inserttext.SAVE_PLACE_LIMIT`).

    python3 tools/komenu.py
"""
from __future__ import annotations

import argparse
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import inserttext  # noqa: E402
import koenc  # noqa: E402
import mktbl  # noqa: E402
from script_io import ScriptFile  # noqa: E402

HANDLER = 0x08039CCD
VM_FROM, VM_TO = 0x092000, 0x0A4000
TABLE = "tDF3908.txt"

TAG_RE = re.compile(r"<\$[0-9A-Fa-f]{2,3}>(?:[-+ #0-9.]*[a-zA-Z])?")


def count(line: str) -> int:
    """메뉴 렌더러가 세는 칸 수. 제어 코드·서식은 0, 나머지는 글자당 1."""
    return len(TAG_RE.sub("", line))


def widest(text: str) -> int:
    return max(count(line) for line in text.split("\n"))


def checked(width: int, lines: int) -> bool:
    """칸 수가 글자 수 한도로 쓰이는 레코드인지."""
    return width > 0 and lines == 1


# 여관표. 세 항목이 한 벌(이름·요금·장소)이고, 장소가 기록 화면에 나옵니다.
PLACE_TABLE = "tDE7C30.txt"


def save_places(rows: dict[int, str]) -> dict[int, str]:
    """여관표에서 기록 화면에 나오는 장소 이름(3번째마다)."""
    return {i: t for i, t in rows.items() if i % 3 == 0}


def long_places(places: dict[int, str], encode, limit: int
                ) -> list[tuple[int, int, str]]:
    """바이트로 `limit` 을 넘는 장소 이름 (번호, 바이트, 글)."""
    out = []
    for i, t in sorted(places.items()):
        n = len(encode(t))
        if n > limit:
            out.append((i, n, t))
    return out


def label_fields(rom: bytes) -> list[tuple[int, int, int, int]]:
    """(레코드 주소, 문자열 번호, 칸 수, 줄 수) 목록."""
    out = []
    want = struct.pack("<I", HANDLER)
    for a in range(VM_FROM, VM_TO, 4):
        if rom[a:a + 4] != want:
            continue
        r = a - 12
        _col, _row, width, lines = struct.unpack_from("<HHHH", rom, r + 4)
        idx = struct.unpack_from("<I", rom, r + 16)[0]
        out.append((0x08000000 + r, idx, width, lines))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="메뉴 항목 칸 폭 검사")
    ap.add_argument("rom", nargs="?", default="rom/baserom.gba")
    ap.add_argument("--ja", default="script/ja")
    ap.add_argument("--ko", default="script/ko")
    args = ap.parse_args()

    with open(args.rom, "rb") as f:
        rom = f.read()
    fields = label_fields(rom)
    ja = {e.index: e.text for e in
          ScriptFile.read(os.path.join(args.ja, TABLE)).entries}
    ko = {e.index: e.text for e in
          ScriptFile.read(os.path.join(args.ko, TABLE)).entries}

    bad: dict[int, tuple[int, int, str]] = {}
    for _at, idx, width, lines in fields:
        if not checked(width, lines) or idx not in ja:
            continue
        text = ko.get(idx, "").strip() and ko[idx] or ja[idx]
        w = widest(text)
        if w > width:
            prev = bad.get(idx)
            if prev is None or width < prev[0]:
                bad[idx] = (width, w, text)

    print(f"메뉴 항목 레코드 {len(fields)}개")
    if not bad:
        print("모든 항목이 제 칸에 들어갑니다")
    else:
        print(f"[!] 칸을 넘겨 잘리는 항목 {len(bad)}개")
        for idx, (width, w, text) in sorted(bad.items()):
            print(f"  #{idx:04d}  {w}칸 > {width}칸  {text!r}")

    long = check_places(rom, args.ko)
    limit = inserttext.SAVE_PLACE_LIMIT
    if not long:
        print(f"기록 화면 장소 이름이 모두 {limit}바이트 안에 듭니다")
    else:
        print(f"[!] 기록 화면에서 잘리는 장소 이름 {len(long)}개 "
              f"({limit}바이트 초과)")
        for i, n, t in long:
            print(f"  #{i:04d}  {n}바이트  {t!r}")
    return 1 if bad or long else 0


def check_places(rom: bytes, ko_dir: str) -> list[tuple[int, int, str]]:
    path = os.path.join(ko_dir, PLACE_TABLE)
    rows = {e.index: e.text for e in ScriptFile.read(path).entries
            if e.text.strip()}
    ja_rev = inserttext.reverse_table(mktbl.build(rom))

    def encode(text: str) -> bytes:
        return koenc.encode(text, inserttext.syllable_codes(text), ja_rev)[:-1]
    return long_places(save_places(rows), encode, inserttext.SAVE_PLACE_LIMIT)


if __name__ == "__main__":
    sys.exit(main())
