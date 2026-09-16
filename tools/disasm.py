#!/usr/bin/env python3
"""GBA THUMB 디스어셈블러 (capstone 기반).

리터럴 풀 로드(`ldr rX, [pc, #imm]`)를 해석해 **함수가 참조하는 주소**를
함께 보여 줍니다. 텍스트 버퍼나 테이블 위치를 추적하는 것이 목적입니다.

    pip install capstone
    python3 tools/disasm.py rom/baserom.gba 0x08039CCC
    python3 tools/disasm.py rom/baserom.gba 0x08039CCC --refs-only
    python3 tools/disasm.py rom/baserom.gba 0x08039CCC --follow 1
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

try:
    from capstone import CS_ARCH_ARM, CS_MODE_THUMB, Cs
except ImportError:
    sys.exit("capstone이 필요합니다:  pip install capstone")

IWRAM = (0x03000000, 0x03008000)
EWRAM = (0x02000000, 0x02040000)
VRAM = (0x06000000, 0x06018000)
IO = (0x04000000, 0x04000400)


def region(addr: int, rom_len: int) -> str:
    if common.ROM_BASE <= addr < common.ROM_BASE + rom_len:
        return f"ROM+0x{addr - common.ROM_BASE:06X}"
    for name, (lo, hi) in (("IWRAM", IWRAM), ("EWRAM", EWRAM),
                           ("VRAM", VRAM), ("IO", IO)):
        if lo <= addr < hi:
            return name
    return ""


def disasm(rom: bytes, addr: int, max_insn: int = 400):
    """(명령어 목록, 리터럴 참조 목록). 함수 끝에서 멈춥니다."""
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    md.detail = False
    off = addr - common.ROM_BASE
    code = bytes(rom[off:off + max_insn * 2 + 8])

    insns = []
    refs = []
    for insn in md.disasm(code, addr):
        lit = None
        if insn.mnemonic.startswith("ldr") and "[pc," in insn.op_str.replace(" ", ""):
            try:
                imm = int(insn.op_str.split("#")[-1].rstrip("]"), 0)
                pool = ((insn.address + 4) & ~3) + imm
                pool_off = pool - common.ROM_BASE
                if 0 <= pool_off + 4 <= len(rom):
                    value = common.u32(rom, pool_off)
                    lit = (pool, value)
                    refs.append((insn.address, pool, value))
            except (ValueError, IndexError):
                pass
        insns.append((insn.address, insn.bytes, insn.mnemonic, insn.op_str, lit))
        if len(insns) >= max_insn:
            break
        m, o = insn.mnemonic, insn.op_str
        if (m == "pop" and "pc" in o) or (m == "bx" and o.strip() == "lr"):
            break
    return insns, refs


def main() -> int:
    ap = argparse.ArgumentParser(description="GBA THUMB 디스어셈블러")
    ap.add_argument("rom")
    ap.add_argument("addr", type=common.parse_int, help="함수 주소 (0x08...)")
    ap.add_argument("--max", type=int, default=400, help="최대 명령어 수")
    ap.add_argument("--refs-only", action="store_true", help="참조 주소만 출력")
    ap.add_argument("--follow", type=int, default=0, help="bl 대상을 N단계까지 추적")
    args = ap.parse_args()

    rom = common.load(args.rom)
    seen: set[int] = set()
    queue = [(args.addr & ~1, 0)]

    while queue:
        addr, depth = queue.pop(0)
        if addr in seen:
            continue
        seen.add(addr)
        insns, refs = disasm(rom, addr, args.max)
        print(f"\n===== 0x{addr:08X} (ROM+0x{addr - common.ROM_BASE:06X}) "
              f"명령어 {len(insns)}개 =====")

        if not args.refs_only:
            for a, b, m, o, lit in insns:
                hexb = b.hex().upper()
                line = f"  {a:08X}  {hexb:<8}  {m:<8} {o}"
                if lit:
                    pool, value = lit
                    tag = region(value, len(rom))
                    line += f"    ; = 0x{value:08X}" + (f" ({tag})" if tag else "")
                print(line)

        if refs:
            print(f"  --- 리터럴 참조 {len(refs)}건 ---")
            for site, pool, value in refs:
                tag = region(value, len(rom))
                print(f"    0x{site:08X} -> 0x{value:08X}" + (f"  [{tag}]" if tag else ""))

        if depth < args.follow:
            for a, b, m, o, lit in insns:
                if m == "bl" and o.startswith("#"):
                    try:
                        t = int(o[1:], 0) & ~1
                    except ValueError:
                        continue
                    if common.ROM_BASE <= t < common.ROM_BASE + len(rom):
                        queue.append((t, depth + 1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
