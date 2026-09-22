#!/usr/bin/env python3
"""아이템 이름이 본문에서 달리 쓰인 곳을 찾습니다.

아이템 이름표(`0xDE1AF8`)는 **소지품 화면에 뜨는 이름**이라, 본문도
그 표기를 따라야 합니다. 안 그러면 소지품에는 「빛의 문」인데 대사는
「빛의 게이트」라 부르는 일이 생깁니다. 실제로 세 건 있었습니다.

    「빛의 문」   ↔ 「빛의 게이트」
    「보배조개」  ↔ 「타카라가이」
    「<$12>만두」 ↔ 「<$12>만주」

어려운 점은 **정당한 축약**과 가르는 것입니다. 문맥이 분명하면
「귀신의 뿔」을 「뿔」로 줄여도 자연스럽고, 26칸 제한 탓에 오히려
줄여야 할 때도 있습니다. 표준 표기의 **마지막 낱말**이 남아 있으면
축약으로 보고 넘깁니다.

고치지는 않습니다 — 어느 쪽이 맞는지는 사람이 정할 일입니다.

    python3 tools/kogloss.py
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from script_io import ScriptFile  # noqa: E402

ITEM_TABLE = "tDE1AF8.txt"
# 일지는 칸이 좁아 일부러 줄여 씁니다. 여기서 보면 오탐만 납니다.
SKIP = {ITEM_TABLE, "tDEC698.txt"}
MIN_CHARS = 3
SP = "　"

# 눈으로 확인하고 넘기기로 한 자리. 아이템 이름이 아니라 **문장**으로
# 쓰인 곳이라, 아이템표 표기를 그대로 넣으면 오히려 어색합니다.
ALLOWED = {
    # 스킬 설명문입니다. 아이템 이름은 「되돌림」, 설명은 「되돌린다」.
    ("DE605C", 72),
    # 검을 이름으로 부르지 않고 「요도」라고 가리키는 대사입니다.
    ("E93D20", 39), ("E93D20", 95),
    # 「쿠나이」를 집어 말하지 않고 병기 전반을 말하는 대사입니다.
    ("F05E18", 58),
    # 게도의 카타카나 말투 「ヨクナイ」 안에 「クナイ」가 묻혀 잡힌 자리입니다.
    ("E2B8E4", 13),
}


def norm(text: str) -> str:
    """줄바꿈과 전각 공백을 지웁니다 — 이름이 줄에 걸쳐 갈리기 때문입니다."""
    return text.replace("\n", "").replace(SP, "")


def glossary(rows) -> dict[str, str]:
    """(이름, 번역) 목록에서 쓸 만한 것만 남깁니다."""
    out = {}
    for ja, ko in rows:
        ja, ko = ja.strip(), ko.strip()
        if not ja or not ko or "／" in ja or "\n" in ja:
            continue
        if len(ja) < MIN_CHARS:
            continue
        out[ja] = ko
    return out


def _tail(std: str) -> str:
    """표준 표기의 마지막 낱말. 축약해도 이건 남습니다."""
    return norm(std.split(SP)[-1]) if SP in std else norm(std)


def check(ja: str, ko: str, gloss: dict[str, str]) -> list[tuple[str, str]]:
    """이 항목에서 달리 쓰인 이름을 (이름, 표준표기) 로."""
    out = []
    flat = norm(ko)
    for term, std in gloss.items():
        if term not in ja or norm(std) in flat:
            continue
        tail = _tail(std)
        if tail and tail in flat:
            continue                      # 줄여 쓴 것입니다
        out.append((term, std))
    return out


def load_glossary(ja_dir: str, ko_dir: str) -> dict[str, str]:
    ja = ScriptFile.read(os.path.join(ja_dir, ITEM_TABLE))
    ko_path = os.path.join(ko_dir, ITEM_TABLE)
    ko = ({e.index: e.text for e in ScriptFile.read(ko_path).entries}
          if os.path.exists(ko_path) else {})
    return glossary([(e.text, ko.get(e.index, "")) for e in ja.entries])


def audit(ja_dir: str, ko_dir: str) -> list[tuple[str, int, str, str, str]]:
    """(표, 항목, 이름, 표준표기, 실제 번역) 목록."""
    gloss = load_glossary(ja_dir, ko_dir)
    out = []
    for name in sorted(os.listdir(ja_dir)):
        if not name.startswith("t") or not name.endswith(".txt"):
            continue
        if name in SKIP:
            continue
        ko_path = os.path.join(ko_dir, name)
        if not os.path.exists(ko_path):
            continue
        ja = ScriptFile.read(os.path.join(ja_dir, name))
        ko = {e.index: e.text for e in ScriptFile.read(ko_path).entries}
        for e in ja.entries:
            k = ko.get(e.index, "")
            if not k.strip():
                continue
            table = name[1:-4]
            if (table, e.index) in ALLOWED:
                continue
            for term, std in check(e.text, k, gloss):
                out.append((table, e.index, term, std, k))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="아이템 이름 표기 일관성 검사")
    ap.add_argument("--ja", default="script/ja")
    ap.add_argument("--ko", default="script/ko")
    args = ap.parse_args()

    if not os.path.isdir(args.ja):
        print(f"[!] 원문이 없습니다: {args.ja} — `make script` 를 먼저 돌리세요")
        return 1
    gloss = load_glossary(args.ja, args.ko)
    found = audit(args.ja, args.ko)
    print(f"아이템 이름 {len(gloss)}개로 검사했습니다 "
          f"(검토 후 넘기기로 한 자리 {len(ALLOWED)}곳 제외)")
    if not found:
        print("본문이 모두 아이템표 표기를 따릅니다")
        return 0
    for table, idx, term, std, ko in found:
        print(f"\n{table}[{idx}]  {term}")
        print(f"  아이템표 {std!r}")
        print(f"  본문     {ko[:56]!r}")
    print(f"\n합계 {len(found)}건 — 어느 쪽이 맞는지는 직접 정하세요")
    return 1


if __name__ == "__main__":
    sys.exit(main())
