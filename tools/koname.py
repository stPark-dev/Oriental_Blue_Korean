#!/usr/bin/env python3
"""이름 입력판의 가나 칸을 이름에 잘 쓰는 완성형 한글로 채웁니다.

이름 입력판은 12열 8행이고 쪽이 넷입니다 (히라가나·가타카나·전각·반각).
쪽마다 칸 96개의 `DF3908` 문자열 번호 표가 ROM 에 있고(0 은 빈칸),
A 를 누르면 그 문자열을 이름 뒤에 이어 붙입니다 (`0x0804AC0C`).
자모를 조합하지 않고, 히라가나·가타카나 두 쪽의 가나 칸 160개에
음절 160자를 가나다 순으로 놓습니다. 전각·반각 영숫자 쪽은 그대로입니다.

이름 폭 한도는 12 이고 한글 음절은 4로 세므로(`0x0801B874`) 이름은
세 음절까지입니다.

    python3 tools/koname.py rom/baserom.gba          # 번역 파일과 대조
    python3 tools/koname.py rom/baserom.gba --write  # 번역 파일에 채움
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from script_io import ScriptFile  # noqa: E402

TABLE = "tDF3908.txt"

# 히라가나·가타카나 쪽의 칸 번호 표 (u16 × 96, 행 우선).
GRIDS = (0x09BD58, 0x09BE18)
CELLS = 80
# 가나 칸이 아닌 것: ー(751), 빈칸(780), 쪽 바꾸기·돌아간다·결정 단추.
BLANK = 780
NOT_KANA = {751, BLANK, 549, 550, 551, 552, 553, 334}

# 쪽 바꾸기 단추. 549 는 첫 쪽으로, 550 은 둘째 쪽으로 갑니다.
TO_PAGE = (549, 550)
LABELS = ("가～사", "아～하")

PAGES = (
    "가강건결경고광구군규근금기길"
    "나난남내노누니"
    "다단달담대덕도동두디"
    "라란람로루류륜리린"
    "마만매명모무문미민"
    "바박반배백별병보부비빈빛"
    "사산상서석선설성세소솔송수숙순슬승시신",
    "아안애양여연영예오온완용우운울원월유윤은이인일임"
    "자장재전정제조종주준중지진"
    "차찬창채천철청초춘치"
    "카코키"
    "타탄태택텐토티"
    "파평포표푸피필"
    "하한해향혁현형혜호화환황효훈희히",
)


def cells(rom: bytes, table: int) -> list[int]:
    """한 쪽의 가나 칸 문자열 번호 (읽는 순서)."""
    ids = [int.from_bytes(rom[table + i * 2:table + i * 2 + 2], "little")
           for i in range(96)]
    return [i for i in ids if i and i not in NOT_KANA]


def grid(rom: bytes, table: int) -> list[int]:
    """새 판: 왼쪽 10열 8행에 가나 칸 80개를 읽는 순서로.

    원래 판은 ー·빈칸이 사이사이 끼고 오른쪽 두 열 위에도 글자가 있어
    가나다 순이 끊겼습니다. 오른쪽 두 열 위 두 행은 커서 점프
    (`0x0804AC78`·`0x0804ACC0` 의 0x0B·0x17)가 닿는 칸이라 0(커서가
    건너뜀)이 아닌 빈칸으로 둡니다. 그 아래(빈 칸·단추)는 그대로입니다.
    """
    old = [int.from_bytes(rom[table + i * 2:table + i * 2 + 2], "little")
           for i in range(96)]
    ids = cells(rom, table)
    new = list(old)
    for r in range(8):
        new[r * 12:r * 12 + 10] = ids[r * 10:(r + 1) * 10]
        if r < 2:
            new[r * 12 + 10:r * 12 + 12] = [BLANK, BLANK]
    return new


def install(rom: bytearray) -> None:
    """히라가나·가타카나 쪽 칸 번호 표를 새 판으로 바꿉니다."""
    for table in GRIDS:
        g = grid(rom, table)
        rom[table:table + 192] = b"".join(v.to_bytes(2, "little") for v in g)


def board(rom: bytes) -> dict[int, str]:
    """문자열 번호 -> 넣을 글자."""
    out: dict[int, str] = {}
    for table, page in zip(GRIDS, PAGES):
        ids = cells(rom, table)
        if len(ids) != len(page):
            raise ValueError(f"0x{table:06X} 칸 {len(ids)}개, 글자 {len(page)}자")
        out.update(zip(ids, page))
    out.update(zip(TO_PAGE, LABELS))
    return out


def diff(rom: bytes, ko_path: str) -> list[tuple[int, str, str]]:
    """(번호, 번역 파일, 배치) 가 다른 것."""
    ko = {e.index: e.text for e in ScriptFile.read(ko_path).entries}
    return [(i, ko.get(i, ""), c) for i, c in sorted(board(rom).items())
            if ko.get(i, "") != c]


def write(rom: bytes, ko_path: str) -> int:
    sf = ScriptFile.read(ko_path)
    want = board(rom)
    n = 0
    for e in sf.entries:
        if e.index in want and e.text != want[e.index]:
            e.text = want[e.index]
            n += 1
    with open(ko_path, encoding="utf-8") as f:
        head = []
        for line in f:
            if line.startswith("## "):
                break
            if line.startswith("# "):
                head.append(line[2:].rstrip("\n"))
    sf.write(ko_path, "\n".join(head))
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("rom")
    ap.add_argument("--ko", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "script", "ko", TABLE))
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    with open(args.rom, "rb") as f:
        rom = f.read()
    if args.write:
        print(f"이름 입력판 {write(rom, args.ko)}칸 채움")
        return 0
    bad = diff(rom, args.ko)
    for i, have, want in bad:
        print(f"  #{i}: {have!r} -> {want!r}")
    print(f"이름 입력판 {'맞음' if not bad else f'{len(bad)}칸 다름'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
