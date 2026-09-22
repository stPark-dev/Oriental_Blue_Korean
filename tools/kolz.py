#!/usr/bin/env python3
"""삽입 문자열을 게임 LZ 형식(`0x0800D4F8`)으로 압축합니다.

게임은 문자열을 읽을 때마다 이 루틴으로 전개하므로, 눌러 넣어도 그대로
읽힙니다. 한글은 음절 하나가 코드 두 개(약 4.9바이트)라 누르지 않으면
ROM 이 모자랍니다.

## 이 형식이 보통 LZ77 과 다른 점

역참조가 **출력이 아니라 압축 스트림 자체**를 가리키고, 그 지점을 다시
전개합니다 (`run(p - dist, length)`). 그래서 참조 대상 안에 이스케이프가
또 들어 있을 수 있습니다 — 중첩 압축이 되는 대신, 아무 데나 가리키면
엉뚱하게 풀립니다.

압축기는 **순수 리터럴 구간만 가리킵니다.** 참조 대상이 리터럴뿐이면
전개 결과가 그 바이트열 그대로라, 보통의 LZ77 과 의미가 같아집니다.
중첩까지 쓰면 조금 더 줄겠지만 검증이 훨씬 까다로워집니다.

## 거리 계산

이스케이프 3바이트를 `P` 에 쓰면 전개기는 `p = P + 3` 에서 `p - dist` 로
갑니다. 참조 대상 압축 위치가 `c` 면 ``dist = P + 3 - c`` 입니다.

거리 0 은 쓰지 않습니다 — 전개기가 이스케이프 바로 뒤를 한 번 더 푸는
특수 동작이라(`docs/ROM_NOTES.md`) 압축에는 쓸모가 없습니다.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import obtext  # noqa: E402

ESCAPE = obtext.ESCAPE
TERMINATOR = obtext.TERMINATOR

MIN_LEN = 4                 # 길이 = (b1 >> 4) + 4
MAX_LEN = 19                # (0x0F) + 4
MAX_DIST = 0x0FFF           # 거리 12비트


class CompressError(Exception):
    pass


def compress(data: bytes) -> bytes:
    """`data` 를 전개하면 원래대로 돌아오는 압축 스트림을 만듭니다.

    이득이 없으면 원본을 그대로 돌려줍니다.
    """
    n = len(data)
    out = bytearray()
    cpos: list[int | None] = [None] * n   # 출력 i 바이트의 압축 위치 (리터럴만)
    index: dict[bytes, list[int]] = {}    # 4바이트 열쇠 -> 리터럴 출력 위치들

    i = 0
    while i < n:
        best_len, best_c = 0, -1
        if i + MIN_LEN <= n:
            key = data[i:i + MIN_LEN]
            here = len(out)
            # 참조 시작 c 는 dist = here + 3 - c <= MAX_DIST 를 만족해야 합니다.
            floor_c = here + 3 - MAX_DIST
            for j in reversed(index.get(key, ())):
                c = cpos[j]
                # 리터럴 위치만 색인하므로 c 는 출력 순서대로 커집니다.
                # 한 번 사거리를 벗어나면 그 앞쪽은 볼 것도 없습니다.
                if c is None or c < floor_c:
                    break
                # 겹치면 안 됩니다 — 참조 대상 압축 바이트가 아직 없습니다.
                limit = min(MAX_LEN, n - i, i - j)
                ln = 0
                while ln < limit and data[j + ln] == data[i + ln]:
                    # 리터럴이 압축 스트림에서도 끊기지 않고 이어져야 합니다.
                    if cpos[j + ln] != c + ln or data[j + ln] == TERMINATOR:
                        break
                    ln += 1
                if ln > best_len:
                    best_len, best_c = ln, c
                    if ln == MAX_LEN:
                        break

        if best_len >= MIN_LEN:
            dist = len(out) + 3 - best_c
            if not (1 <= dist <= MAX_DIST):       # 방어적 — 위에서 걸렀습니다
                raise CompressError(f"거리 {dist} 가 범위를 벗어납니다")
            out += bytes([ESCAPE,
                          ((best_len - MIN_LEN) << 4) | ((dist >> 8) & 0x0F),
                          dist & 0xFF])
            i += best_len
            continue

        b = data[i]
        if b == ESCAPE:
            raise CompressError(f"리터럴에 이스케이프 0x08 이 있습니다 (위치 {i})")
        cpos[i] = len(out)
        out.append(b)
        if i + MIN_LEN <= n and b != TERMINATOR:
            index.setdefault(data[i:i + MIN_LEN], []).append(i)
        i += 1

    return bytes(out) if len(out) < n else data


def expand(data: bytes, budget: int = obtext.OUT_LIMIT) -> bytes:
    """압축 스트림을 게임과 같은 방식으로 되풉니다 (검증용)."""
    return obtext.expand(data, 0, budget)


def compress_checked(data: bytes) -> bytes:
    """압축한 뒤 **되풀어 원본과 대조**합니다. 어긋나면 원본을 돌려줍니다.

    실기에서 한 항목이라도 깨지면 찾기가 매우 어려우므로, 전개기를 통과한
    것만 내보냅니다.
    """
    try:
        packed = compress(data)
    except CompressError:
        return data
    if packed is data:
        return data
    try:
        if expand(packed) != data:
            return data
    except obtext.ExpandError:
        return data
    return packed


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="게임 LZ 형식 압축 자가 점검")
    ap.add_argument("rom", nargs="?", help="원본 ROM — 주면 원문으로 왕복 시험")
    args = ap.parse_args()

    cases = [b"\x00", b"abc\x00", b"abcabcabcabc\x00",
             bytes(range(1, 0x08)) * 8 + b"\x00", b"\x41" * 300 + b"\x00"]
    for c in cases:
        p = compress_checked(c)
        assert expand(p) == c, c
        print(f"  {len(c):5,}바이트 -> {len(p):5,}")

    if args.rom:
        import common
        rom = common.load(args.rom)
        ok = shrunk = raw = 0
        for base, _ in obtext.scan_tables(rom):
            _, entries = obtext.read_table(rom, base)
            for addr in entries[:40]:
                try:
                    text = obtext.expand(rom, addr)
                except obtext.ExpandError:
                    continue
                p = compress_checked(text)
                assert expand(p) == text
                ok += 1
                shrunk += len(p)
                raw += len(text)
            if ok > 4000:
                break
        print(f"\n원문 {ok:,}항목 왕복 통과 — {raw:,} -> {shrunk:,}바이트 "
              f"({100 * shrunk / max(raw, 1):.0f}%)")
    print("\n자가 점검 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
