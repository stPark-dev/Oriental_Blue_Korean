#!/usr/bin/env python3
"""스크립트 전체를 번역 작업용 텍스트 파일로 덤프합니다.

문자열 테이블마다 파일 하나를 만듭니다.

  script/ja/<이름>.txt   원문. **ROM 파생물이라 커밋하지 않습니다.**
  script/ko/<이름>.txt   번역본 골격. 헤더만 있고 본문은 비어 있습니다.

번역자는 두 파일을 나란히 놓고 ko 쪽 본문을 채웁니다. 비어 있는 항목은
삽입 시 건너뛰므로, 부분 번역 상태로도 빌드할 수 있습니다.

    python3 tools/dumpscript.py rom/baserom.gba
    python3 tools/dumpscript.py rom/baserom.gba --min-count 32 --force-ko
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import mktbl  # noqa: E402
import obtext  # noqa: E402

TERMINATOR = 0x00
NEWLINE = 0x0A
BANKS = (1, 2)
FORMATS = (3, 4, 5)


def decode(data: bytes, table: dict) -> str:
    """전개된 바이트열을 사람이 읽고 고칠 수 있는 텍스트로."""
    out = []
    i = 0
    n = len(data)
    while i < n:
        c = data[i]
        if c == TERMINATOR:
            break
        if c == NEWLINE:
            out.append("\n")
            i += 1
            continue
        if c in BANKS:
            if i + 1 >= n:
                out.append(f"<${c:02X}>")
                break
            code = (c << 8) | data[i + 1]
            out.append(table.get(code) or f"<${code:03X}>")
            i += 2
            continue
        if c in FORMATS:
            if i + 1 >= n:
                out.append(f"<${c:02X}>")
                break
            out.append(f"<F{c}:{data[i + 1]:02X}>")
            i += 2
            continue
        out.append(table.get(c) or f"<${c:02X}>")
        i += 1
    return "".join(out)


def write_files(name: str, base: int, rows: list[tuple[int, int, str]],
                ja_dir: str, ko_dir: str, force_ko: bool) -> None:
    os.makedirs(ja_dir, exist_ok=True)
    os.makedirs(ko_dir, exist_ok=True)

    ja_path = os.path.join(ja_dir, name + ".txt")
    with open(ja_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"# 테이블 0x{base:06X} / 항목 {len(rows)}개\n")
        f.write("# tools/dumpscript.py 자동 생성 — 직접 수정하지 마세요.\n\n")
        for idx, off, text in rows:
            f.write(f"## {idx:04d} @0x{off:06X}\n")
            f.write(text.rstrip("\n") + "\n\n")

    ko_path = os.path.join(ko_dir, name + ".txt")
    if os.path.exists(ko_path) and not force_ko:
        return
    with open(ko_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"# 테이블 0x{base:06X} / 항목 {len(rows)}개\n")
        f.write(f"# 원문은 script/ja/{name}.txt 를 나란히 놓고 보세요.\n")
        f.write("# 본문이 비어 있는 항목은 삽입 시 건너뜁니다 (원문 유지).\n")
        f.write("# <F3:XX> 같은 서식 태그는 위치를 바꾸지 말고 그대로 두세요.\n\n")
        for idx, off, _ in rows:
            f.write(f"## {idx:04d} @0x{off:06X}\n\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="스크립트 전체 덤프")
    ap.add_argument("rom")
    ap.add_argument("--ja", default="script/ja")
    ap.add_argument("--ko", default="script/ko")
    ap.add_argument("--tables", default="build/strtables.tsv",
                    help="테이블 목록 TSV (없으면 직접 스캔)")
    ap.add_argument("--min-count", type=int, default=32)
    ap.add_argument("--force-ko", action="store_true",
                    help="기존 번역 파일도 덮어씁니다 (주의)")
    args = ap.parse_args()

    rom = common.load(args.rom)
    table = mktbl.build(rom)
    print(f"문자 대응표 {len(table)}자")

    if os.path.exists(args.tables):
        bases = [int(l.split("\t")[0], 16) for l in
                 open(args.tables, encoding="utf-8").read().splitlines()[1:]]
        print(f"테이블 목록: {args.tables} ({len(bases)}개)")
    else:
        print("테이블 스캔 중...")
        bases = [b for b, _ in obtext.scan_tables(rom, args.min_count)]

    total = ok = fail = 0
    empty = 0
    files = 0
    for base in sorted(bases):
        try:
            count, entries = obtext.read_table(rom, base)
        except Exception:
            continue
        rows = []
        for idx, off in enumerate(entries, 1):
            total += 1
            try:
                raw = obtext.expand(rom, off)
            except Exception:
                fail += 1
                continue
            ok += 1
            text = decode(raw, table)
            if not text.strip():
                empty += 1
            rows.append((idx, off - common.ROM_BASE if off > common.ROM_BASE
                         else off, text))
        if not rows:
            continue
        write_files(f"t{base:06X}", base, rows, args.ja, args.ko, args.force_ko)
        files += 1

    print(f"\n파일 {files}개 생성")
    print(f"항목 {total:,} / 전개 성공 {ok:,} / 실패 {fail:,}")
    print(f"빈 문자열 {empty:,}개 (번역 대상 아님)")
    print(f"실질 번역 대상 {ok - empty:,}개")
    print(f"\n  원문   {args.ja}/   (ROM 파생물 — 커밋하지 않습니다)")
    print(f"  번역   {args.ko}/   (여기를 채우세요)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
