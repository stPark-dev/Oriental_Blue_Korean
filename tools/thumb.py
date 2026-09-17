#!/usr/bin/env python3
"""최소 THUMB-1 어셈블러 — ROM 패치용.

필요한 명령만 담았습니다. 텍스트를 파싱하지 않고 메서드로 쌓습니다.

    a = Asm(0x081BDA40)
    a.push([4, 5, 6, 7], lr=True)
    a.lsrs(2, 1, 8)
    a.cmp_imm(2, 5)
    a.beq("trail")
    ...
    a.mark("trail")
    code = a.assemble()

라벨은 앞뒤 어느 쪽이든 참조할 수 있습니다. `ldr_pool` 은 32비트 상수를
코드 뒤 리터럴 풀에 넣고 `ldr Rd, [pc, #N]` 으로 읽습니다.
"""
from __future__ import annotations

LO = range(8)


class AsmError(Exception):
    pass


def _chk(cond, msg):
    if not cond:
        raise AsmError(msg)


class Asm:
    """base 주소에 놓일 코드를 만듭니다 (THUMB, 하프워드 단위)."""

    COND = {"eq": 0, "ne": 1, "cs": 2, "cc": 3, "mi": 4, "pl": 5,
            "vs": 6, "vc": 7, "hi": 8, "ls": 9, "ge": 10, "lt": 11,
            "gt": 12, "le": 13}

    def __init__(self, base: int):
        _chk(base % 2 == 0, "base 는 짝수여야 합니다")
        self.base = base
        self.hw: list[int] = []
        self.labels: dict[str, int] = {}
        self.fix: list[tuple[int, str, str]] = []   # (위치, 종류, 라벨)
        self.pool: list[int] = []
        self.pool_fix: list[tuple[int, int]] = []   # (위치, 풀 인덱스)

    # --- 기본 ---
    def _e(self, v: int) -> int:
        _chk(0 <= v <= 0xFFFF, f"하프워드 범위 밖: {v:#x}")
        self.hw.append(v)
        return len(self.hw) - 1

    def mark(self, name: str) -> None:
        _chk(name not in self.labels, f"라벨 중복: {name}")
        self.labels[name] = len(self.hw)

    @property
    def here(self) -> int:
        return self.base + len(self.hw) * 2

    # --- 명령 ---
    def push(self, regs: list[int], lr: bool = False) -> None:
        self._e(0xB400 | (0x100 if lr else 0) | sum(1 << r for r in regs))

    def pop(self, regs: list[int], pc: bool = False) -> None:
        self._e(0xBC00 | (0x100 if pc else 0) | sum(1 << r for r in regs))

    def movs(self, rd: int, imm: int) -> None:
        _chk(rd in LO and 0 <= imm <= 0xFF, "movs 범위")
        self._e(0x2000 | (rd << 8) | imm)

    def lsls(self, rd: int, rm: int, imm: int) -> None:
        _chk(0 <= imm <= 31, "lsls 범위")
        self._e(0x0000 | (imm << 6) | (rm << 3) | rd)

    def lsrs(self, rd: int, rm: int, imm: int) -> None:
        _chk(1 <= imm <= 32, "lsrs 범위")
        self._e(0x0800 | ((imm & 31) << 6) | (rm << 3) | rd)

    def cmp_imm(self, rn: int, imm: int) -> None:
        _chk(rn in LO and 0 <= imm <= 0xFF, "cmp 범위")
        self._e(0x2800 | (rn << 8) | imm)

    def cmp_reg(self, rn: int, rm: int) -> None:
        self._e(0x4280 | (rm << 3) | rn)

    def adds_imm3(self, rd: int, rn: int, imm: int) -> None:
        _chk(0 <= imm <= 7, "adds imm3 범위")
        self._e(0x1C00 | (imm << 6) | (rn << 3) | rd)

    def subs_imm3(self, rd: int, rn: int, imm: int) -> None:
        _chk(0 <= imm <= 7, "subs imm3 범위")
        self._e(0x1E00 | (imm << 6) | (rn << 3) | rd)

    def adds_imm8(self, rd: int, imm: int) -> None:
        _chk(0 <= imm <= 0xFF, "adds imm8 범위")
        self._e(0x3000 | (rd << 8) | imm)

    def subs_imm8(self, rd: int, imm: int) -> None:
        _chk(0 <= imm <= 0xFF, "subs imm8 범위")
        self._e(0x3800 | (rd << 8) | imm)

    def adds(self, rd: int, rn: int, rm: int) -> None:
        self._e(0x1800 | (rm << 6) | (rn << 3) | rd)

    def subs(self, rd: int, rn: int, rm: int) -> None:
        self._e(0x1A00 | (rm << 6) | (rn << 3) | rd)

    def muls(self, rd: int, rm: int) -> None:
        self._e(0x4340 | (rm << 3) | rd)

    def mov_hi(self, rd: int, rm: int) -> None:
        """hi 레지스터를 포함한 이동 (플래그 안 바뀜)."""
        self._e(0x4600 | ((rd & 8) << 4) | ((rm & 15) << 3) | (rd & 7))

    def ldrb_imm(self, rd: int, rn: int, off: int) -> None:
        _chk(0 <= off <= 31, "ldrb 범위")
        self._e(0x7800 | (off << 6) | (rn << 3) | rd)

    def strb_imm(self, rd: int, rn: int, off: int) -> None:
        _chk(0 <= off <= 31, "strb 범위")
        self._e(0x7000 | (off << 6) | (rn << 3) | rd)

    def ldrh_reg(self, rd: int, rn: int, rm: int) -> None:
        self._e(0x5A00 | (rm << 6) | (rn << 3) | rd)

    def ldrb_reg(self, rd: int, rn: int, rm: int) -> None:
        self._e(0x5C00 | (rm << 6) | (rn << 3) | rd)

    def ldr_imm(self, rd: int, rn: int, off: int) -> None:
        _chk(off % 4 == 0 and 0 <= off <= 124, "ldr 범위")
        self._e(0x6800 | ((off >> 2) << 6) | (rn << 3) | rd)

    def str_imm(self, rd: int, rn: int, off: int) -> None:
        _chk(off % 4 == 0 and 0 <= off <= 124, "str 범위")
        self._e(0x6000 | ((off >> 2) << 6) | (rn << 3) | rd)

    def bx(self, rm: int) -> None:
        self._e(0x4700 | (rm << 3))

    def b(self, label: str) -> None:
        self.fix.append((self._e(0xE000), "b", label))

    def bcond(self, cond: str, label: str) -> None:
        _chk(cond in self.COND, f"모르는 조건: {cond}")
        self.fix.append((self._e(0xD000 | (self.COND[cond] << 8)), "bc", label))

    def beq(self, l): self.bcond("eq", l)

    def bne(self, l): self.bcond("ne", l)

    def blt(self, l): self.bcond("lt", l)

    def bgt(self, l): self.bcond("gt", l)

    def bhi(self, l): self.bcond("hi", l)

    def bls(self, l): self.bcond("ls", l)

    def bl(self, target: int) -> None:
        off = target - (self.here + 4)
        _chk(-(1 << 22) <= off < (1 << 22), f"bl 범위 밖: {off:#x}")
        self._e(0xF000 | ((off >> 12) & 0x7FF))
        self._e(0xF800 | ((off >> 1) & 0x7FF))

    def ldr_pool(self, rd: int, value: int) -> None:
        """32비트 상수를 리터럴 풀에서 읽습니다."""
        if value in self.pool:
            i = self.pool.index(value)
        else:
            self.pool.append(value & 0xFFFFFFFF)
            i = len(self.pool) - 1
        self.pool_fix.append((self._e(0x4800 | (rd << 8)), i))

    # --- 마무리 ---
    def assemble(self) -> bytes:
        n = len(self.hw)
        pool_at = n + (n % 2)                      # 리터럴 풀은 워드 정렬
        for pos, i in self.pool_fix:
            pc = ((self.base + pos * 2 + 4) & ~3)
            addr = self.base + pool_at * 2 + i * 4
            off = addr - pc
            _chk(0 <= off <= 1020 and off % 4 == 0,
                 f"리터럴 풀이 너무 멀거나 정렬이 어긋남: {off}")
            self.hw[pos] |= off >> 2
        for pos, kind, name in self.fix:
            _chk(name in self.labels, f"없는 라벨: {name}")
            off = (self.labels[name] - pos - 2) * 2
            if kind == "b":
                _chk(-2048 <= off < 2048, f"b 범위 밖: {off}")
                self.hw[pos] |= (off >> 1) & 0x7FF
            else:
                _chk(-256 <= off < 256, f"조건 분기 범위 밖: {off}")
                self.hw[pos] |= (off >> 1) & 0xFF
        out = bytearray()
        for h in self.hw:
            out += h.to_bytes(2, "little")
        if self.pool and n % 2:
            out += b"\x00\x00"          # 리터럴 풀 워드 정렬용
        for v in self.pool:
            out += v.to_bytes(4, "little")
        return bytes(out)


def bl_bytes(site: int, target: int) -> bytes:
    """`site` 에 놓을 `bl target` 4바이트."""
    off = target - (site + 4)
    _chk(-(1 << 22) <= off < (1 << 22), f"bl 범위 밖: {off:#x}")
    h1 = 0xF000 | ((off >> 12) & 0x7FF)
    h2 = 0xF800 | ((off >> 1) & 0x7FF)
    return h1.to_bytes(2, "little") + h2.to_bytes(2, "little")
