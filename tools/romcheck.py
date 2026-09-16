#!/usr/bin/env python3
"""ROM 식별 및 무결성 확인.

사용법: python3 tools/romcheck.py rom/baserom.gba
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="GBA ROM 정보 출력")
    ap.add_argument("rom")
    ap.add_argument("--json", action="store_true", help="JSON으로 출력")
    ap.add_argument("--expect-sha1", help="기대 SHA-1과 비교")
    args = ap.parse_args()

    rom = common.load(args.rom)
    h = common.header(rom)
    stored, calc = common.header_checksum(rom)
    d = common.digests(rom)

    info = {
        "path": args.rom,
        "title": h.title,
        "game_code": h.game_code,
        "maker": h.maker,
        "version": h.version,
        "size": h.size,
        "size_mbit": h.size * 8 // 1024 // 1024,
        "header_checksum": {"stored": stored, "calculated": calc,
                            "ok": stored == calc},
        **d,
    }

    if args.json:
        print(json.dumps(info, indent=2, ensure_ascii=False))
    else:
        print(f"파일       : {args.rom}")
        print(f"내부 타이틀: {h.title}")
        print(f"게임 코드  : {h.game_code}  (제작사 {h.maker})")
        print(f"버전       : 1.{h.version}")
        print(f"크기       : {h.size:,} 바이트 ({info['size_mbit']} Mbit)")
        print(f"헤더 체크섬: {stored:02X} / 계산값 {calc:02X} "
              f"{'일치' if stored == calc else '불일치!'}")
        print(f"CRC32      : {d['crc32'].upper()}")
        print(f"MD5        : {d['md5']}")
        print(f"SHA-1      : {d['sha1']}")

    if args.expect_sha1:
        if d["sha1"].lower() != args.expect_sha1.lower():
            print("\n[!] SHA-1이 기대값과 다릅니다.", file=sys.stderr)
            return 1
        print("\n[o] SHA-1 일치")
    return 0


if __name__ == "__main__":
    sys.exit(main())
