#!/usr/bin/env python3
"""끝말잇기(しりとり) 낱말표 분석·검증.

낱말표 `0xDF9088` 은 오래 **번역 보류**였습니다. 한글 음절은 코드 두 개라서,
낱말을 잇는 비교 루틴이 "한 글자 = 코드 하나"를 가정하고 있으면 종성이
떨어진 채 맞춰질 위험이 있었기 때문입니다 (`강` == `가`).

비교 루틴을 찾아 확인한 결과 **그런 가정은 없습니다.**

    0x0801B8A8   두 문자열을 바이트 단위로 종결자까지 비교. 길이 제한 없음.
                 같으면 0, 다르면 1.

앞뒤 글자는 길이가 아니라 **버퍼 크기**에만 걸립니다. 비교 직전에 스택으로
복사되는데, 가장 좁은 자리가 8바이트입니다 (`0x0801861C`, `0x080189D0`).
한글 음절 하나는 코드 두 개 = 4바이트 + 종결자 = **5바이트**라 들어갑니다.
두 음절(9바이트)은 넘칩니다 — 앞뒤 글자는 **한 음절까지**입니다.

자료 구조 (주소는 전부 아카이브에서 계산합니다. ROM 안에 이 표를 가리키는
리터럴 포인터는 없습니다)::

    0x08000324   arc_get(arc, id) = arc + 4 + u32[arc + 4 + 4*id]
                 id > arc[0] 이면 0

    0x220000 ──4──▶ 마스터 표 ──25──▶ 낱말 레코드 530개 (12바이트)
                            ├──58──▶ 낱말 문자열표 0xDF9088 (1,590항목)
                            ├───5──▶ 아이템 레코드 (32바이트)
                            └──30──▶ 아이템 이름표 0xDE1AF8

    레코드 12바이트:  +0 자기 번호  +2 앞 글자  +4 낱말  +6 뒤 글자
                      +8 재사용 한도  +0xA 「지는 낱말」 표식

문자열 세 개는 모두 `0xDF9088` 의 항목 번호이며, 레코드 i 는 항상
`3i+1`(앞 글자) `3i+2`(낱말) `3i+3`(뒤 글자) 을 씁니다.

    python3 tools/koshiri.py info   rom/baserom.gba
    python3 tools/koshiri.py dump   rom/baserom.gba
    python3 tools/koshiri.py check  rom/baserom.gba
    python3 tools/koshiri.py items  rom/baserom.gba [--write]
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import dumpscript  # noqa: E402
import inserttext  # noqa: E402
import kocode  # noqa: E402
import koenc  # noqa: E402
import mktbl  # noqa: E402
import obtext  # noqa: E402
from script_io import ScriptFile  # noqa: E402

ROOT_ARCHIVE = 0x220000         # 0x0800CDDE / 0x0800CEFE 의 리터럴
ARC_MASTER = 4                  # 마스터 문자열표 아카이브
IDX_RECORDS = 25                # 낱말 레코드 (JPN)
IDX_RECORDS_INTL = 26           # 낱말 레코드 (비-JPN, 이 ROM 에서는 미사용)
IDX_WORDS = 58                  # 낱말 문자열표 0xDF9088
IDX_WORDS_INTL = 59             # 0xDFBEE4 — 쓰이지 않습니다 (아래 참고)
IDX_ITEM_RECORDS = 5            # 아이템 레코드
IDX_ITEM_NAMES = 30             # 아이템 이름표 0xDE1AF8

RECORD_SIZE = 12
RECORD_COUNT = 0x211 + 1        # 0x080182CA 의 상한 검사
ITEM_FIRST = 0xBF               # 0x08018388 (JPN). 이 번호부터 아이템 낱말
ITEM_RECORD_SIZE = 32           # 0x0801038C

# 앞뒤 글자를 복사해 두는 가장 좁은 스택 버퍼 (0x0801861C, 0x080189D0).
HEAD_TAIL_BUFFER = 8


class ShiritoriError(Exception):
    pass


# --- ROM 자료 읽기 ------------------------------------------------------

def arc_get(rom: bytes, arc: int, index: int) -> int:
    """`0x08000324` 의 아카이브 조회. 돌려주는 값은 ROM 오프셋입니다."""
    count = common.u32(rom, arc)
    if index > count:
        raise ShiritoriError(f"아카이브 0x{arc:06X}: 색인 {index} 범위 밖")
    return arc + 4 + common.u32(rom, arc + 4 + 4 * index)


def addresses(rom: bytes) -> dict[str, int]:
    """끝말잇기가 쓰는 표들의 ROM 오프셋."""
    master = arc_get(rom, ROOT_ARCHIVE, ARC_MASTER)
    return {
        "master": master,
        "records": arc_get(rom, master, IDX_RECORDS),
        "records_intl": arc_get(rom, master, IDX_RECORDS_INTL),
        "words": arc_get(rom, master, IDX_WORDS),
        "words_intl": arc_get(rom, master, IDX_WORDS_INTL),
        "item_records": arc_get(rom, master, IDX_ITEM_RECORDS),
        "item_names": arc_get(rom, master, IDX_ITEM_NAMES),
    }


def string(rom: bytes, table: int, index: int, chars: dict) -> str:
    """문자열표 항목 하나를 사람이 읽는 텍스트로."""
    count = common.u32(rom, table)
    if not 0 < index < count:
        return ""
    off = table + common.u32(rom, table + 4 * index)
    return dumpscript.decode(obtext.expand(rom, off), chars)


class Record:
    """낱말 레코드 하나."""

    __slots__ = ("index", "head_id", "word_id", "tail_id", "limit", "losing")

    def __init__(self, index: int, raw: bytes):
        def s16(at: int) -> int:
            v = common.u16(raw, at)
            return v - 0x10000 if v & 0x8000 else v

        self.index = index
        self.head_id = s16(2)
        self.word_id = s16(4)
        self.tail_id = s16(6)
        self.limit = s16(8)       # 0 이면 제한 없음 (0x08018686)
        self.losing = s16(10)     # 0 이 아니면 내면 지는 낱말 (0x08018A42)

    @property
    def is_item(self) -> bool:
        return self.index >= ITEM_FIRST

    @property
    def item_id(self) -> int:
        return self.index - ITEM_FIRST


def records(rom: bytes, base: int | None = None) -> list[Record]:
    if base is None:
        base = addresses(rom)["records"]
    return [Record(i, rom[base + RECORD_SIZE * i:base + RECORD_SIZE * (i + 1)])
            for i in range(RECORD_COUNT)]


def item_name_id(rom: bytes, item_records: int, item_id: int) -> int:
    """아이템 레코드의 이름 문자열 번호 (`0x08010404` 의 `+2`)."""
    at = item_records + ITEM_RECORD_SIZE * item_id + 2
    v = common.u16(rom, at)
    return v - 0x10000 if v & 0x8000 else v


# --- 번역문 ------------------------------------------------------------

def read_ko(path: str) -> dict[int, str]:
    if not os.path.exists(path):
        return {}
    return {e.index: e.text for e in ScriptFile.read(path).entries
            if e.text.strip()}


def encoded_length(text: str, ko_map: dict, ja_rev: dict) -> int:
    """삽입될 바이트 수 (종결자 포함)."""
    return len(koenc.encode(text, ko_map, ja_rev))


def syllables(text: str) -> list[str]:
    return [c for c in text if kocode.is_syllable(c)]


# --- 하위 명령 ----------------------------------------------------------

def cmd_info(rom: bytes, _args) -> int:
    a = addresses(rom)
    print("아카이브 사슬 (ROM 안에 이 표들을 가리키는 리터럴 포인터는 없습니다)")
    print(f"  루트 아카이브        0x{ROOT_ARCHIVE:06X}")
    print(f"  마스터 문자열표      0x{a['master']:06X}  (루트 #{ARC_MASTER})")
    print()
    print(f"  낱말 레코드          0x{a['records']:06X}  "
          f"(마스터 #{IDX_RECORDS}) {RECORD_COUNT}개 × {RECORD_SIZE}바이트")
    print(f"  낱말 문자열표        0x{a['words']:06X}  "
          f"(마스터 #{IDX_WORDS}) 항목 {common.u32(rom, a['words']) - 1}개")
    print(f"  아이템 레코드        0x{a['item_records']:06X}  "
          f"(마스터 #{IDX_ITEM_RECORDS})")
    print(f"  아이템 이름표        0x{a['item_names']:06X}  "
          f"(마스터 #{IDX_ITEM_NAMES})")
    print()
    print(f"  비-JPN 레코드        0x{a['records_intl']:06X}  "
          f"(마스터 #{IDX_RECORDS_INTL})")
    print(f"  비-JPN 낱말표        0x{a['words_intl']:06X}  "
          f"(마스터 #{IDX_WORDS_INTL}) — 읽는 코드가 없습니다")
    print()
    print("비교 루틴  0x0801B8A8 — 종결자까지 바이트 비교, 길이 제한 없음")
    print(f"앞뒤 글자 버퍼  {HEAD_TAIL_BUFFER}바이트 "
          f"(종결자 포함) -> 한글 한 음절(5바이트)까지")
    return 0


def _rows(rom: bytes, ko: dict[int, str], chars: dict):
    a = addresses(rom)
    for r in records(rom):
        ja = tuple(string(rom, a["words"], i, chars)
                   for i in (r.head_id, r.word_id, r.tail_id))
        kr = tuple(ko.get(i, "") for i in (r.head_id, r.word_id, r.tail_id))
        yield r, ja, kr


def cmd_dump(rom: bytes, args) -> int:
    chars = mktbl.build(rom)
    ko = read_ko(os.path.join(args.ko, "tDF9088.txt"))
    for r, ja, kr in _rows(rom, ko, chars):
        flag = ("R" if r.limit else "-") + ("X" if r.losing else "-")
        kind = "아이템" if r.is_item else "일반  "
        line = (f"{r.index:4d} {kind} {flag} "
                f"[{ja[0]}] [{ja[1]}] [{ja[2]}]")
        if any(kr):
            line += f"   ->  [{kr[0]}] [{kr[1]}] [{kr[2]}]"
        print(line)
    return 0


def cmd_check(rom: bytes, args) -> int:
    """번역문이 사슬로 이어지는지, 버퍼에 들어가는지 검사합니다."""
    chars = mktbl.build(rom)
    ko = read_ko(os.path.join(args.ko, "tDF9088.txt"))
    if not ko:
        print(f"{args.ko}/tDF9088.txt 에 채워진 항목이 없습니다 — 원문으로 검사합니다.")

    ja_rev = inserttext.reverse_table(chars)
    ko_map = inserttext.syllable_codes("".join(ko.values()))

    errors: list[str] = []
    warnings: list[str] = []
    heads: set[str] = set()
    tails: dict[str, list[int]] = {}
    filled = partial = 0

    for r, ja, kr in _rows(rom, ko, chars):
        text = kr if any(kr) else ja
        if any(kr):
            if all(kr):
                filled += 1
            else:
                partial += 1
                errors.append(
                    f"#{r.index}: 앞 글자·낱말·뒤 글자 중 일부만 번역됨 "
                    f"(항목 {r.head_id}/{r.word_id}/{r.tail_id})")
        head, word, tail = text
        if not word:
            continue                      # 빈 레코드 (아이템 이름으로 대체됨)

        for label, s, index in (("앞 글자", head, r.head_id),
                                ("뒤 글자", tail, r.tail_id)):
            if not s:
                errors.append(f"#{r.index}: {label}가 비었습니다 (항목 {index})")
                continue
            size = encoded_length(s, ko_map, ja_rev)
            if size > HEAD_TAIL_BUFFER:
                errors.append(
                    f"#{r.index}: {label} {s!r} 이 {size}바이트 — 버퍼 "
                    f"{HEAD_TAIL_BUFFER}바이트를 넘습니다 (항목 {index})")
            if len(s) > 1:
                warnings.append(f"#{r.index}: {label} {s!r} 이 두 글자 이상입니다")

        heads.add(head)
        tails.setdefault(tail, []).append(r.index)

        syl = syllables(word)
        if syl:
            if head != syl[0]:
                warnings.append(
                    f"#{r.index}: 앞 글자 {head!r} 가 낱말 {word!r} 의 "
                    f"첫 음절 {syl[0]!r} 과 다릅니다")
            if tail != syl[-1]:
                warnings.append(
                    f"#{r.index}: 뒤 글자 {tail!r} 가 낱말 {word!r} 의 "
                    f"끝 음절 {syl[-1]!r} 과 다릅니다")

    dead = sorted(t for t in tails if t and t not in heads)
    losing = {r.index for r in records(rom) if r.losing}

    print(f"레코드 {RECORD_COUNT}개 / 세 항목 모두 번역됨 {filled}개"
          + (f" / 일부만 번역됨 {partial}개" if partial else ""))
    print(f"앞 글자 {len(heads)}종 · 뒤 글자 {len(tails)}종")
    print(f"막다른 글자 {len(dead)}종: {' '.join(dead) if dead else '없음'}")
    for t in dead:
        ids = tails[t]
        marked = sum(1 for i in ids if i in losing)
        print(f"  {t!r}: 낱말 {len(ids)}개 · 「지는 낱말」 표식 {marked}개")

    if warnings:
        print(f"\n경고 {len(warnings)}건")
        for w in warnings[:args.limit]:
            print(f"  {w}")
        if len(warnings) > args.limit:
            print(f"  … 외 {len(warnings) - args.limit}건")
    if errors:
        print(f"\n오류 {len(errors)}건")
        for e in errors[:args.limit]:
            print(f"  {e}")
        if len(errors) > args.limit:
            print(f"  … 외 {len(errors) - args.limit}건")
        return 1
    print("\n오류 없음")
    return 0


def cmd_items(rom: bytes, args) -> int:
    """아이템 낱말 339개를 번역된 아이템 이름에서 채웁니다.

    레코드 191번부터는 낱말이 아이템 이름과 같은 글자입니다. 번역된 이름을
    그대로 가져오고 앞뒤 글자는 첫·끝 음절로 잡습니다. **일반 낱말 191개를
    함께 옮기지 않으면 사슬이 한·일로 갈라지므로** 기본은 미리보기입니다.
    """
    chars = mktbl.build(rom)
    a = addresses(rom)
    path = os.path.join(args.ko, "tDF9088.txt")
    ko_items = read_ko(os.path.join(args.ko, "tDE1AF8.txt"))

    filled: dict[int, str] = {}
    skipped: list[str] = []
    for r in records(rom):
        if not r.is_item:
            continue
        ja_word = string(rom, a["words"], r.word_id, chars)
        if not ja_word:
            continue              # 빈 레코드 — 아이템 이름으로 대체됩니다
        name = ko_items.get(item_name_id(rom, a["item_records"], r.item_id), "")
        if not name:
            skipped.append(f"#{r.index}: 아이템 {r.item_id} 이름이 아직 번역 전")
            continue
        syl = syllables(name)
        if not syl:
            skipped.append(f"#{r.index}: {name!r} 에 한글 음절이 없습니다")
            continue
        filled[r.head_id] = syl[0]
        filled[r.word_id] = name
        filled[r.tail_id] = syl[-1]

    print(f"채울 항목 {len(filled)}개 (아이템 낱말 {len(filled) // 3}개)")
    for why in skipped[:args.limit]:
        print(f"  건너뜀 — {why}")
    if len(skipped) > args.limit:
        print(f"  … 외 {len(skipped) - args.limit}건")

    # 아이템 낱말만으로 생기는 막다른 글자. 일반 낱말 191개로 메워야 합니다.
    heads = {filled[r.head_id] for r in records(rom)
             if r.is_item and r.head_id in filled}
    dead: dict[str, int] = {}
    for r in records(rom):
        if r.is_item and r.tail_id in filled:
            t = filled[r.tail_id]
            if t not in heads:
                dead[t] = dead.get(t, 0) + 1
    if dead:
        total = sum(dead.values())
        print(f"\n아이템 낱말만으로는 막다른 글자가 {len(dead)}종 생깁니다 "
              f"(낱말 {total}개가 내면 지는 낱말이 됩니다).")
        print("  " + " ".join(sorted(dead)))
        print("일반 낱말 191개 자리에 이 글자로 시작하는 낱말을 넣어 메우세요.")

    if not args.write:
        print("\n미리보기입니다. 실제로 쓰려면 --write 를 주세요.")
        print("일반 낱말 191개를 함께 옮기기 전에는 쓰지 마세요 — "
              "사슬이 한국어와 일본어로 갈라집니다.")
        return 0

    sf = ScriptFile.read(path)
    for e in sf.entries:
        if e.index in filled and not e.text.strip():
            e.text = filled[e.index]
    sf.write(path,
             f"테이블 0x{a['words']:06X} / 항목 {len(sf.entries)}개\n"
             f"원문은 script/ja/tDF9088.txt 를 나란히 놓고 보세요.\n"
             "본문이 비어 있는 항목은 삽입 시 건너뜁니다 (원문 유지).\n"
             "세 항목이 한 벌입니다: 앞 글자 / 낱말 / 뒤 글자.\n"
             "앞뒤 글자는 한 음절까지만 넣을 수 있습니다 (버퍼 8바이트).")
    print(f"\n{path} 에 반영했습니다.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="끝말잇기 낱말표 분석·검증")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn, help_ in (("info", cmd_info, "표 위치와 제약 요약"),
                            ("dump", cmd_dump, "레코드 전체 출력"),
                            ("check", cmd_check, "번역문 사슬·버퍼 검사"),
                            ("items", cmd_items, "아이템 낱말 자동 채우기")):
        s = sub.add_parser(name, help=help_)
        s.add_argument("rom")
        s.add_argument("--ko", default="script/ko")
        s.add_argument("--limit", type=int, default=20)
        if name == "items":
            s.add_argument("--write", action="store_true")
        s.set_defaults(fn=fn)
    args = p.parse_args()
    rom = common.load(args.rom)
    return args.fn(rom, args)


if __name__ == "__main__":
    sys.exit(main())
