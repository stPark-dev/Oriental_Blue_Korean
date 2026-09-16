#!/usr/bin/env python3
"""오리엔탈블루 전용 텍스트 압축 해제 및 문자열 테이블 탐색.

ROM 코드에서 확인한 사양입니다.

전개 루틴 `0x0800D4F8` — 출력 바이트 수를 예산으로 삼는 LZ 계열::

    0x08  이스케이프. 뒤에 2바이트가 따라옵니다.
              길이 = (b1 >> 4) + 4
              거리 = ((b1 & 0x0F) << 8) | b2
          현재 소스 위치에서 거리만큼 뒤로 간 지점을 길이만큼 **재귀 전개**합니다.
          참조 대상이 압축 스트림 자체이므로 중첩될 수 있습니다.
    0x00  종결자. 출력에 기록한 뒤 즉시 종료합니다.
    그 외  문자 코드 그대로 출력.

테이블 조회 `0x0800D574`::

    count = table[0]
    유효 범위는 0 < id < count
    주소 = table + table[id]        (엔트리는 테이블 기준 상대 오프셋)
    범위를 벗어나면 빈 문자열 0x08089D44 를 돌려줍니다.

    python3 tools/obtext.py scan   rom/baserom.gba
    python3 tools/obtext.py expand rom/baserom.gba 0x123456
    python3 tools/obtext.py table  rom/baserom.gba 0x123456 --limit 20
"""
from __future__ import annotations

import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

ESCAPE = 0x08
TERMINATOR = 0x00
OUT_LIMIT = 0x1000          # 게임이 쓰는 작업 버퍼 크기 (0x02002E60, 4KB)
MAX_DEPTH = 64


class ExpandError(Exception):
    pass


def expand(rom: bytes, src: int, budget: int = OUT_LIMIT) -> bytes:
    """압축 해제. 종결자를 만나거나 예산을 소진하면 멈춥니다."""
    out = bytearray()

    def run(p: int, remaining: int, depth: int) -> bool:
        if depth > MAX_DEPTH:
            raise ExpandError("재귀 한계 초과")
        while remaining > 0:
            if not (0 <= p < len(rom)):
                raise ExpandError(f"범위 밖 소스 0x{p:X}")
            b = rom[p]
            p += 1
            if b == ESCAPE:
                if p + 1 >= len(rom):
                    raise ExpandError("이스케이프 뒤 데이터 부족")
                b1, b2 = rom[p], rom[p + 1]
                p += 2
                length = (b1 >> 4) + 4
                dist = ((b1 & 0x0F) << 8) | b2
                if dist == 0:
                    raise ExpandError("거리 0")
                if length > remaining:
                    length = remaining
                if run(p - dist, length, depth + 1):
                    return True
                remaining -= length
            else:
                out.append(b)
                if b == TERMINATOR:
                    return True
                remaining -= 1
        return False

    run(src, budget, 0)
    return bytes(out)


def read_table(rom: bytes, base: int):
    """(개수, [엔트리 절대 오프셋]) — 유효 id 는 1..count-1 입니다."""
    count = common.u32(rom, base)
    entries = []
    for i in range(1, count):
        off = common.u32(rom, base + i * 4)
        entries.append(base + off)
    return count, entries


def plausible_table(rom: bytes, base: int, min_count: int = 16,
                    max_count: int = 30000) -> int | None:
    """문자열 테이블 시그니처 검사. 성공하면 개수를 반환합니다."""
    if base + 8 > len(rom):
        return None
    count = common.u32(rom, base)
    if not (min_count <= count <= max_count):
        return None
    if base + count * 4 > len(rom):
        return None
    header = count * 4
    prev = 0
    for i in range(1, count):
        off = common.u32(rom, base + i * 4)
        # 엔트리는 헤더 뒤쪽을 가리켜야 하고, ROM 범위 안이어야 합니다
        if off < header or base + off >= len(rom):
            return None
        # 대체로 증가합니다. 완전 단조는 아니므로 크게 역행하면 탈락
        if off + 0x4000 < prev:
            return None
        prev = max(prev, off)
    return count


def scan_tables(rom: bytes, min_count: int = 16, align: int = 4):
    for base in range(0, len(rom) - 8, align):
        c = plausible_table(rom, base, min_count)
        if c:
            yield base, c


def text_score(data: bytes) -> float:
    """제어 코드 1-5 와 문자 코드가 섞인 정도 — 텍스트다움."""
    if not data:
        return 0.0
    body = data[:-1] if data and data[-1] == 0 else data
    if not body:
        return 0.0
    ctrl = sum(1 for b in body if 1 <= b <= 5)
    chars = sum(1 for b in body if b >= 6)
    return (ctrl + chars) / len(body)


def main() -> int:
    ap = argparse.ArgumentParser(description="오리엔탈블루 텍스트 도구")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="문자열 테이블 후보 탐색")
    s.add_argument("rom")
    s.add_argument("--min-count", type=int, default=16)
    s.add_argument("--limit", type=int, default=40)
    s.add_argument("-o", "--out", help="TSV 저장")

    e = sub.add_parser("expand", help="한 엔트리 압축 해제")
    e.add_argument("rom")
    e.add_argument("offset", type=common.parse_int)
    e.add_argument("--budget", type=common.parse_int, default=OUT_LIMIT)

    t = sub.add_parser("table", help="테이블의 엔트리들을 전개해 통계 출력")
    t.add_argument("rom")
    t.add_argument("base", type=common.parse_int)
    t.add_argument("--limit", type=int, default=20)
    t.add_argument("--dump", help="전개 결과를 이 파일에 바이너리로 저장")

    args = ap.parse_args()
    rom = common.load(args.rom)

    if args.cmd == "expand":
        data = expand(rom, args.offset, args.budget)
        print(f"0x{args.offset:06X}: {len(data)}바이트 전개")
        print("바이트:", ' '.join(f'{b:02X}' for b in data[:64]),
              "..." if len(data) > 64 else "")
        print(f"텍스트다움 점수: {text_score(data):.3f}")
        return 0

    if args.cmd == "table":
        count, entries = read_table(rom, args.base)
        print(f"테이블 0x{args.base:06X}: 엔트리 {count}개 (유효 id 1..{count - 1})")
        ok = fail = 0
        lens = []
        dump = bytearray()
        for i, off in enumerate(entries, 1):
            try:
                data = expand(rom, off)
            except (ExpandError, RecursionError, IndexError):
                fail += 1
                continue
            ok += 1
            lens.append(len(data))
            dump += data
            if i <= args.limit:
                print(f"  id {i:>5}  0x{off:06X}  {len(data):>4}B  "
                      f"점수 {text_score(data):.2f}  "
                      + ' '.join(f'{b:02X}' for b in data[:16]))
        print(f"\n전개 성공 {ok} / 실패 {fail}")
        if lens:
            print(f"길이 평균 {sum(lens) / len(lens):.1f}B / 최대 {max(lens)}B")
            hist = collections.Counter()
            for b in dump:
                hist[b] += 1
            print(f"고유 바이트 {len(hist)}종, 최빈: "
                  + ', '.join(f'{v:02X}×{n}' for v, n in hist.most_common(8)))
        if args.dump and dump:
            common.save(args.dump, bytes(dump))
            print(f"저장: {args.dump} ({len(dump):,}바이트)")
        return 0

    rows = list(scan_tables(rom, args.min_count))
    print(f"# 테이블 후보 {len(rows)}건")
    print("오프셋\t엔트리수")
    for base, c in rows[:args.limit or len(rows)]:
        print(f"0x{base:06X}\t{c}")
    if args.limit and len(rows) > args.limit:
        print(f"... 외 {len(rows) - args.limit}건")
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            f.write("오프셋\t엔트리수\n")
            for base, c in rows:
                f.write(f"0x{base:06X}\t{c}\n")
        print(f"저장: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
