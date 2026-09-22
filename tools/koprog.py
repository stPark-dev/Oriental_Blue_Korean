#!/usr/bin/env python3
"""번역 진행률.

분모가 틀리면 진행률은 통째로 거짓말이 됩니다. 실제로 두 번 틀렸습니다.

1. `make script` 가 `--min-count 32` 로 돌아 표 423개가 덤프에 없었습니다.
   16,674항목 기준 83.5% 로 부풀어 있었습니다. (tools/dumpscript.py 에서 수정)
2. 문턱을 내리고 나니 이번에는 **게임이 쓰지 않는 표**가 분모에 들어와
   진행률이 반대로 깎였습니다. 그래서 여기서 덜어냅니다.

    python3 tools/koprog.py          # 전체 진행률
    python3 tools/koprog.py --left   # 남은 표를 많은 순으로
"""
from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from script_io import ScriptFile  # noqa: E402

# 번역해도 화면에 나오지 않거나, 번역하면 안 되는 **표**.
#
# 아이템 이름표 DE1AF8 은 여기 넣으면 안 됩니다. 화면에 나오는 표라
# 738항목이 이미 번역돼 있어서, 표째로 빼면 그 번역이 분자에서도
# 사라집니다. 그 표에서 뺄 것은 아래 PLACEHOLDER 자리뿐입니다.
EXCLUDED: dict[str, str] = {
    "DFBEE4": "비-JPN 낱말표 — 읽는 코드가 없습니다 (tools/koshiri.py)",
    "DF9080": "끝말잇기 낱말 조각 — koshiri.py 가 롬을 직접 고칩니다",
    "DF809C": "ＣＡＳＴ 자막 — 제작진 실명이라 원문을 그대로 둡니다",
    "DF8494": "ＳＴＡＦＦ 자막 — 제작진 실명이라 원문을 그대로 둡니다",
    # 개발용 장면 라벨. "E074 ニンジャ船にのる" 처럼 이벤트 번호가 앞에
    # 붙고, 여섯 표 457항목이 제어 코드를 **하나도** 쓰지 않습니다.
    # 화면에 나오는 표는 예외 없이 <$10> 계열을 씁니다.
    "DFEB94": "개발용 장면 라벨 — 제어 코드가 없습니다",
    "DFED60": "개발용 장면 라벨 — 제어 코드가 없습니다",
    "DFF16C": "개발용 장면 라벨 — 제어 코드가 없습니다",
    "DFFE9C": "개발용 장면 라벨 — 제어 코드가 없습니다",
    "E011C8": "개발용 장면 라벨 — 제어 코드가 없습니다",
    "E0255C": "개발용 장면 라벨 — 제어 코드가 없습니다",
    # 표가 아닌 자리. 덤프 필터를 통과했지만 내용이 글이 아닙니다.
    # 눈으로 하나씩 확인했습니다. 자동으로 가르려 들면 F62D1C 처럼
    # 세 항목이 똑같은 멀쩡한 대사를 잘못 버립니다.
    "4670DC": "글이 아닌 자리 — 같은 기호열 4벌",
    "467F9C": "글이 아닌 자리 — 같은 기호열 4벌",
    "89094C": "글이 아닌 자리 — 한두 글자짜리 잡음",
    "8A42C4": "글이 아닌 자리 — 한두 글자짜리 잡음",
    "8C0148": "글이 아닌 자리 — 같은 기호열 반복",
    "9B3F14": "글이 아닌 자리 — 한두 글자짜리 잡음",
    "B185B0": "글이 아닌 자리 — 같은 기호열 4벌",
    # [u32 길이][데이터] 구조의 크기 접두 바이너리 블롭. dumpscript.py는
    # 이 주소들을 원문 덤프에서 제외하지만, 예전 script/ja 파일이 남아 있어도
    # 진행률에 들어오지 않도록 여기서도 명시적으로 제외합니다.
    "220020": "크기 접두 바이너리 블롭 — 문자열표가 아닙니다",
    "26CAC8": "크기 접두 바이너리 블롭 — 문자열표가 아닙니다",
    "CAE740": "크기 접두 바이너리 블롭 — 문자열표가 아닙니다",
    "D7DE5C": "크기 접두 바이너리 블롭 — 문자열표가 아닙니다",
    "DAAA70": "크기 접두 바이너리 블롭 — 문자열표가 아닙니다",
    "DAAB68": "크기 접두 바이너리 블롭 — 문자열표가 아닙니다",
    "E02DA4": "크기 접두 바이너리 블롭 — 문자열표가 아닙니다",
    "E3DC5C": "크기 접두 바이너리 블롭 — 문자열표가 아닙니다",
    "E5A3D0": "크기 접두 바이너리 블롭 — 문자열표가 아닙니다",
    "E7E6E0": "크기 접두 바이너리 블롭 — 문자열표가 아닙니다",
    "E9D308": "크기 접두 바이너리 블롭 — 문자열표가 아닙니다",
    "EBEB48": "크기 접두 바이너리 블롭 — 문자열표가 아닙니다",
    "EE8E58": "크기 접두 바이너리 블롭 — 문자열표가 아닙니다",
    "EF54D0": "크기 접두 바이너리 블롭 — 문자열표가 아닙니다",
    "F0C118": "크기 접두 바이너리 블롭 — 문자열표가 아닙니다",
    "F2E98C": "크기 접두 바이너리 블롭 — 문자열표가 아닙니다",
}

# 제어 코드와 printf 서식. 서식은 원문 그대로여야 합니다 — 바꾸면
# 엉뚱한 값이 찍히거나 튕깁니다 (tools/koaudit.py 가 따로 검사합니다).
TAG_RE = re.compile(r"<\$[0-9A-F]{2,4}>|<F\d:[0-9A-F]{2}>")
FMT_RE = re.compile(r"<\$1F>[-+ #0-9.]*[a-zA-Z]")
JP_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")


def translatable(text: str) -> bool:
    """옮길 말이 들어 있는지.

    서식과 제어 코드를 걷어내고도 가나·한자가 남아야 번역 대상입니다.
    DF3908 에는 `<$1F>-7dＧ` 같은 서식과 `Ｇ` `×` `ＥＸＰ` 같은 기호·
    영문 라벨만 든 항목이 313개 있습니다. 옮길 말이 없습니다.
    """
    rest = TAG_RE.sub("", FMT_RE.sub("", text))
    return bool(JP_RE.search(rest))


# 표 안의 빈 자리. 아이템 이름표에서 279개, CA8DE0 에서 17개가 이 꼴입니다.
# 반각 '0' 과 전각 '０' 둘 다 씁니다.
PLACEHOLDERS = frozenset(("0", "\uff10"))


def load(ja_dir: str, ko_dir: str) -> dict[str, list[tuple[str, str]]]:
    """표마다 (원문, 번역) 목록을 모읍니다."""
    out = {}
    for name in sorted(os.listdir(ja_dir)):
        if not name.startswith("t") or not name.endswith(".txt"):
            continue
        ja = ScriptFile.read(os.path.join(ja_dir, name))
        ko_path = os.path.join(ko_dir, name)
        ko = ({e.index: e.text for e in ScriptFile.read(ko_path).entries}
              if os.path.exists(ko_path) else {})
        out[name] = [(e.text, ko.get(e.index, "")) for e in ja.entries]
    return out


def count(files: dict[str, list[tuple[str, str]]]) -> dict[str, tuple[int, int]]:
    """표마다 (번역 대상, 완료). 빈 원문과 제외 표는 빼고 셉니다."""
    out = {}
    for name, pairs in files.items():
        table = name[1:-4] if name.startswith("t") else name
        if table in EXCLUDED:
            continue
        total = done = 0
        for ja, ko in pairs:
            if not ja.strip() or ja.strip() in PLACEHOLDERS:
                continue
            if not translatable(ja):
                continue
            total += 1
            if ko.strip():
                done += 1
        out[table] = (total, done)
    return out


def totals(rows: dict[str, tuple[int, int]]) -> tuple[int, int]:
    return (sum(t for t, _ in rows.values()), sum(d for _, d in rows.values()))


def percent(done: int, total: int) -> float:
    return done / total * 100 if total else 0.0


def main() -> int:
    ap = argparse.ArgumentParser(description="번역 진행률")
    ap.add_argument("--ja", default="script/ja")
    ap.add_argument("--ko", default="script/ko")
    ap.add_argument("--left", action="store_true", help="남은 표를 많은 순으로")
    args = ap.parse_args()

    if not os.path.isdir(args.ja):
        print(f"[!] 원문이 없습니다: {args.ja} — `make script` 를 먼저 돌리세요")
        return 1
    rows = count(load(args.ja, args.ko))
    total, done = totals(rows)
    print(f"번역 대상 {total:,}항목 / 완료 {done:,} "
          f"({percent(done, total):.1f}%) / 남음 {total - done:,}")
    print(f"표 {len(rows)}개 · 손대지 않은 표 "
          f"{sum(1 for t, d in rows.values() if d == 0)}개")
    print("\n분모에서 뺀 표 (그 밖에 각 표의 '0' 빈 자리도 뺍니다):")
    for name, why in EXCLUDED.items():
        print(f"  {name}  {why}")
    if args.left:
        left = sorted(((t - d, n) for n, (t, d) in rows.items() if t > d),
                      reverse=True)
        print(f"\n남은 표 {len(left)}개:")
        for n, name in left[:40]:
            print(f"  {name}  {n:5}항목")
    return 0


if __name__ == "__main__":
    sys.exit(main())
