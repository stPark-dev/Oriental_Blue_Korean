#!/usr/bin/env python3
"""GBA BIOS 표준 압축(LZ77 / RLE) 디코더 · 인코더.

헤더 4바이트: [타입][원본크기 3바이트 LE]
  0x10 = LZ77, 0x30 = RLE

    python3 tools/gbalz.py scan   rom.gba --min 256      # 유효 블록 탐색
    python3 tools/gbalz.py unpack rom.gba 0x1A3C out.bin
    python3 tools/gbalz.py pack   in.bin out.bin
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

LZ77 = 0x10
RLE = 0x30


class LzError(Exception):
    pass


def decompress(data: bytes, off: int = 0, max_size: int = 1 << 22) -> tuple[bytes, int]:
    """(원본 데이터, 소비한 바이트 수). 실패 시 LzError."""
    if off + 4 > len(data):
        raise LzError("헤더 부족")
    kind = data[off] & 0xF0
    size = int.from_bytes(data[off + 1:off + 4], "little")
    if size == 0 or size > max_size:
        raise LzError(f"비정상 크기 {size}")

    pos = off + 4
    out = bytearray()

    if kind == LZ77:
        while len(out) < size:
            if pos >= len(data):
                raise LzError("입력 조기 종료")
            flags = data[pos]
            pos += 1
            for bit in range(8):
                if len(out) >= size:
                    break
                if flags & (0x80 >> bit):
                    if pos + 2 > len(data):
                        raise LzError("입력 조기 종료")
                    b0, b1 = data[pos], data[pos + 1]
                    pos += 2
                    length = (b0 >> 4) + 3
                    disp = (((b0 & 0x0F) << 8) | b1) + 1
                    if disp > len(out):
                        raise LzError(f"역참조 범위 초과 (disp={disp}, out={len(out)})")
                    start = len(out) - disp
                    for i in range(length):
                        out.append(out[start + i])
                else:
                    if pos >= len(data):
                        raise LzError("입력 조기 종료")
                    out.append(data[pos])
                    pos += 1
    elif kind == RLE:
        while len(out) < size:
            if pos >= len(data):
                raise LzError("입력 조기 종료")
            flag = data[pos]
            pos += 1
            if flag & 0x80:
                n = (flag & 0x7F) + 3
                if pos >= len(data):
                    raise LzError("입력 조기 종료")
                out += bytes([data[pos]]) * n
                pos += 1
            else:
                n = (flag & 0x7F) + 1
                out += data[pos:pos + n]
                pos += n
    else:
        raise LzError(f"지원하지 않는 압축 타입 0x{data[off]:02X}")

    return bytes(out[:size]), pos - off


def compress(raw: bytes, kind: int = LZ77) -> bytes:
    """LZ77 인코더. VRAM 안전( disp >= 2 )하게 만듭니다."""
    if kind != LZ77:
        raise LzError("LZ77만 지원합니다")
    out = bytearray(bytes([LZ77]) + len(raw).to_bytes(3, "little"))
    pos = 0
    n = len(raw)
    while pos < n:
        flag_at = len(out)
        out.append(0)
        flags = 0
        for bit in range(8):
            if pos >= n:
                break
            best_len, best_disp = 0, 0
            window = max(0, pos - 0x1000)
            for disp_start in range(pos - 2, window - 1, -1):
                length = 0
                while (length < 18 and pos + length < n
                       and raw[disp_start + length] == raw[pos + length]):
                    length += 1
                if length > best_len:
                    best_len, best_disp = length, pos - disp_start
                    if length == 18:
                        break
            if best_len >= 3:
                flags |= 0x80 >> bit
                out.append(((best_len - 3) << 4) | (((best_disp - 1) >> 8) & 0x0F))
                out.append((best_disp - 1) & 0xFF)
                pos += best_len
            else:
                out.append(raw[pos])
                pos += 1
        out[flag_at] = flags
    while len(out) % 4:
        out.append(0)
    return bytes(out)


def scan(rom: bytes, min_size: int = 256, max_size: int = 1 << 20,
         align: int = 4, kinds: tuple[int, ...] = (LZ77, RLE)):
    """헤더 후보를 전부 실제로 풀어 보고, 성공한 것만 돌려줍니다."""
    n = len(rom)
    for off in range(0, n - 4, align):
        if (rom[off] & 0xF0) not in kinds:
            continue
        size = int.from_bytes(rom[off + 1:off + 4], "little")
        if not (min_size <= size <= max_size):
            continue
        try:
            raw, used = decompress(rom, off, max_size)
        except (LzError, IndexError):
            continue
        if len(raw) == size:
            yield off, used, raw


def main() -> int:
    ap = argparse.ArgumentParser(description="GBA LZ77/RLE 도구")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan")
    s.add_argument("rom")
    s.add_argument("--min", type=common.parse_int, default=256)
    s.add_argument("--max", type=common.parse_int, default=1 << 20)
    s.add_argument("--align", type=int, default=4)
    s.add_argument("--limit", type=int, default=40)
    s.add_argument("-o", "--out", help="TSV 저장")
    s.add_argument("--dump-dir", help="풀린 블록을 이 디렉터리에 저장")

    u = sub.add_parser("unpack")
    u.add_argument("rom")
    u.add_argument("offset", type=common.parse_int)
    u.add_argument("out")

    p = sub.add_parser("pack")
    p.add_argument("src")
    p.add_argument("out")

    args = ap.parse_args()

    if args.cmd == "unpack":
        rom = common.load(args.rom)
        raw, used = decompress(rom, args.offset)
        common.save(args.out, raw)
        print(f"0x{args.offset:06X}: 압축 {used:,}B -> 원본 {len(raw):,}B  ({args.out})")
        return 0

    if args.cmd == "pack":
        raw = common.load(args.src)
        data = compress(bytes(raw))
        common.save(args.out, data)
        chk, _ = decompress(data, 0)
        print(f"원본 {len(raw):,}B -> 압축 {len(data):,}B "
              f"({len(data) / max(len(raw), 1) * 100:.1f}%)  "
              f"검증 {'통과' if chk == bytes(raw) else '실패!'}")
        return 0

    rom = common.load(args.rom)
    found = []
    for off, used, raw in scan(rom, args.min, args.max, args.align):
        found.append((off, used, len(raw), raw))
        if args.dump_dir:
            common.save(os.path.join(args.dump_dir, f"{off:06X}.bin"), raw)

    print(f"# 유효 압축 블록 {len(found)}개")
    print("오프셋\t압축크기\t원본크기\t압축률")
    for off, used, size, _ in found[:args.limit or len(found)]:
        print(f"0x{off:06X}\t{used}\t{size}\t{used / size * 100:.0f}%")
    if args.limit and len(found) > args.limit:
        print(f"... 외 {len(found) - args.limit}개")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write("오프셋\t압축크기\t원본크기\n")
            for off, used, size, _ in found:
                f.write(f"0x{off:06X}\t{used}\t{size}\n")
        print(f"저장: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
