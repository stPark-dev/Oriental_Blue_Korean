#!/usr/bin/env python3
"""IPS / BPS 패치 생성 및 적용 (순수 파이썬, flips 불필요).

    python3 tools/patch.py make  base.gba build/patched.gba patch/ko.bps
    python3 tools/patch.py apply base.gba patch/ko.bps  out.gba
"""
from __future__ import annotations

import argparse
import os
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

IPS_MAX = 0x1000000  # IPS 오프셋 한계 16MB


# --- BPS ---------------------------------------------------------------

def _bps_num(n: int) -> bytes:
    out = bytearray()
    while True:
        x = n & 0x7F
        n >>= 7
        if n == 0:
            out.append(0x80 | x)
            return bytes(out)
        out.append(x)
        n -= 1


def _bps_read_num(data: bytes, pos: int) -> tuple[int, int]:
    value, shift = 0, 1
    while True:
        b = data[pos]
        pos += 1
        value += (b & 0x7F) * shift
        if b & 0x80:
            return value, pos
        shift <<= 7
        value += shift


RUN_MIN = 32   # 이만큼 같은 바이트가 이어지면 TargetCopy 로 늘립니다


def bps_make(source: bytes, target: bytes, metadata: bytes = b"") -> bytes:
    """SourceRead / TargetRead / TargetCopy 인코더.

    변경되지 않은 구간은 SourceRead 한 번, 바뀐 구간은 TargetRead 로 담습니다.
    바뀐 구간 안에서 같은 바이트가 `RUN_MIN` 이상 이어지면 첫 바이트만 담고
    나머지는 바로 앞 바이트를 겹쳐 복사(TargetCopy)합니다 — ROM 을 32MB 로
    늘린 뒤쪽 `0xFF` 16MB 가 몇 바이트로 줄어듭니다.
    """
    out = bytearray(b"BPS1")
    out += _bps_num(len(source))
    out += _bps_num(len(target))
    out += _bps_num(len(metadata))
    out += metadata

    dst_rel = 0

    def target_read(a: int, b: int) -> None:
        if b > a:
            out.extend(_bps_num(((b - a - 1) << 2) | 1))
            out.extend(target[a:b])

    def changed(a: int, b: int) -> None:
        nonlocal dst_rel
        k = a
        while k < b:
            r = k
            while r < b and target[r] == target[k]:
                r += 1
            if r - k >= RUN_MIN:
                target_read(a, k + 1)              # 첫 바이트까지 담고
                delta = k - dst_rel                # 그 바이트를 겹쳐 복사
                out.extend(_bps_num(((r - k - 2) << 2) | 3))
                out.extend(_bps_num((abs(delta) << 1) | (delta < 0)))
                dst_rel = k + (r - k - 1)
                a = k = r
            else:
                k = r
        target_read(a, b)

    i = 0
    n = len(target)
    while i < n:
        same = i < len(source) and target[i] == source[i]
        j = i
        while j < n and ((j < len(source) and target[j] == source[j]) == same):
            if same and j >= len(source):
                break
            j += 1
        if same:
            out += _bps_num(((j - i - 1) << 2) | 0)  # SourceRead
        else:
            changed(i, j)
        i = j

    out += (zlib.crc32(source) & 0xFFFFFFFF).to_bytes(4, "little")
    out += (zlib.crc32(target) & 0xFFFFFFFF).to_bytes(4, "little")
    out += (zlib.crc32(bytes(out)) & 0xFFFFFFFF).to_bytes(4, "little")
    return bytes(out)


def bps_apply(source: bytes, patch: bytes) -> bytes:
    if patch[:4] != b"BPS1":
        raise ValueError("BPS 시그니처가 아닙니다")
    if zlib.crc32(patch[:-4]) & 0xFFFFFFFF != int.from_bytes(patch[-4:], "little"):
        raise ValueError("패치 파일이 손상되었습니다 (CRC 불일치)")

    pos = 4
    src_size, pos = _bps_read_num(patch, pos)
    dst_size, pos = _bps_read_num(patch, pos)
    meta_size, pos = _bps_read_num(patch, pos)
    pos += meta_size

    if len(source) != src_size:
        raise ValueError(f"원본 크기 불일치: {len(source)} != {src_size}")
    expect_src_crc = int.from_bytes(patch[-12:-8], "little")
    if zlib.crc32(source) & 0xFFFFFFFF != expect_src_crc:
        raise ValueError("원본 ROM의 CRC32가 패치와 맞지 않습니다")

    target = bytearray(dst_size)
    out_off = src_rel = dst_rel = 0
    end = len(patch) - 12
    while pos < end:
        data, pos = _bps_read_num(patch, pos)
        action, length = data & 3, (data >> 2) + 1
        if action == 0:
            target[out_off:out_off + length] = source[out_off:out_off + length]
            out_off += length
        elif action == 1:
            target[out_off:out_off + length] = patch[pos:pos + length]
            pos += length
            out_off += length
        elif action in (2, 3):
            raw, pos = _bps_read_num(patch, pos)
            delta = (-1 if raw & 1 else 1) * (raw >> 1)
            if action == 2:
                src_rel += delta
                for _ in range(length):
                    target[out_off] = source[src_rel]
                    out_off += 1
                    src_rel += 1
            else:
                dst_rel += delta
                gap = out_off - dst_rel
                if gap >= length:                   # 겹치지 않으면 한 번에
                    target[out_off:out_off + length] = \
                        target[dst_rel:dst_rel + length]
                elif gap == 1:                      # 바로 앞 바이트 늘이기
                    target[out_off:out_off + length] = \
                        bytes([target[dst_rel]]) * length
                else:
                    for k in range(length):
                        target[out_off + k] = target[dst_rel + k]
                out_off += length
                dst_rel += length
    return bytes(target)


# --- IPS ---------------------------------------------------------------

def ips_make(source: bytes, target: bytes) -> bytes:
    if len(target) > IPS_MAX:
        raise ValueError("IPS는 16MB를 넘는 파일을 다룰 수 없습니다. BPS를 쓰세요.")
    out = bytearray(b"PATCH")
    i, n = 0, len(target)
    while i < n:
        if i < len(source) and target[i] == source[i]:
            i += 1
            continue
        start = i
        gap = 0
        while i < n and gap < 6:
            if i < len(source) and target[i] == source[i]:
                gap += 1
            else:
                gap = 0
            i += 1
        end = i - gap
        for off in range(start, end, 0xFFFF):
            chunk = target[off:min(off + 0xFFFF, end)]
            real = off + 1 if off == 0x454F46 else off  # "EOF" 충돌 회피
            if real != off:
                chunk = target[real:min(real + 0xFFFF, end)]
            out += real.to_bytes(3, "big") + len(chunk).to_bytes(2, "big") + chunk
    out += b"EOF"
    if len(target) != len(source):
        out += len(target).to_bytes(3, "big")
    return bytes(out)


def ips_apply(source: bytes, patch: bytes) -> bytes:
    if patch[:5] != b"PATCH":
        raise ValueError("IPS 시그니처가 아닙니다")
    out = bytearray(source)
    pos = 5
    while True:
        if patch[pos:pos + 3] == b"EOF":
            pos += 3
            if len(patch) - pos >= 3:
                out = out[:int.from_bytes(patch[pos:pos + 3], "big")]
            return bytes(out)
        off = int.from_bytes(patch[pos:pos + 3], "big")
        size = int.from_bytes(patch[pos + 3:pos + 5], "big")
        pos += 5
        if size == 0:  # RLE
            rle = int.from_bytes(patch[pos:pos + 2], "big")
            byte = patch[pos + 2]
            pos += 3
            data = bytes([byte]) * rle
        else:
            data = patch[pos:pos + size]
            pos += size
        if off + len(data) > len(out):
            out += bytes(off + len(data) - len(out))
        out[off:off + len(data)] = data


# --- CLI ---------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="IPS/BPS 패치 도구")
    sub = ap.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("make", help="원본과 수정본의 차이로 패치 생성")
    m.add_argument("source")
    m.add_argument("target")
    m.add_argument("out")
    m.add_argument("--format", choices=["bps", "ips", "auto"], default="auto")

    a = sub.add_parser("apply", help="패치 적용")
    a.add_argument("source")
    a.add_argument("patch")
    a.add_argument("out")

    args = ap.parse_args()

    if args.cmd == "make":
        src = common.load(args.source)
        dst = common.load(args.target)
        fmt = args.format
        if fmt == "auto":
            fmt = "ips" if args.out.lower().endswith(".ips") else "bps"
        data = ips_make(src, dst) if fmt == "ips" else bps_make(src, dst)
        common.save(args.out, data)
        diff = sum(1 for x, y in zip(src, dst) if x != y) + abs(len(src) - len(dst))
        print(f"{fmt.upper()} 생성: {args.out} ({len(data):,} 바이트)")
        print(f"변경된 바이트: {diff:,}")

        check = (ips_apply if fmt == "ips" else bps_apply)(bytes(src), data)
        print("검증:", "통과" if check == bytes(dst) else "실패!")
        return 0 if check == bytes(dst) else 1

    src = common.load(args.source)
    pat = common.load(args.patch)
    fn = ips_apply if pat[:5] == b"PATCH" else bps_apply
    out = fn(bytes(src), bytes(pat))
    common.save(args.out, out)
    print(f"적용 완료: {args.out} ({len(out):,} 바이트)")
    print(f"SHA-1: {common.digests(out)['sha1']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
