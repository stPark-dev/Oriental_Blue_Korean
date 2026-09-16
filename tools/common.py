#!/usr/bin/env python3
"""GBA ROM 공통 유틸 — 로딩/저장, 헤더 파싱, 포인터 변환, 해시.

표준 라이브러리만 사용합니다. 리눅스/윈도우/macOS 동일하게 동작합니다.
"""
from __future__ import annotations

import hashlib
import os
import zlib
from dataclasses import dataclass

ROM_BASE = 0x08000000


class RomError(Exception):
    pass


def load(path: str) -> bytearray:
    with open(path, "rb") as f:
        return bytearray(f.read())


def save(path: str, data: bytes) -> None:
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


@dataclass
class Header:
    title: str
    game_code: str
    maker: str
    version: int
    size: int


def header(rom: bytes) -> Header:
    if len(rom) < 0xC0:
        raise RomError("ROM이 너무 작습니다 (GBA 헤더 미만)")
    title = rom[0xA0:0xAC].split(b"\x00")[0].decode("ascii", "replace")
    return Header(
        title=title,
        game_code=rom[0xAC:0xB0].decode("ascii", "replace"),
        maker=rom[0xB0:0xB2].decode("ascii", "replace"),
        version=rom[0xBC],
        size=len(rom),
    )


def header_checksum(rom: bytes) -> tuple[int, int]:
    """(저장된 값, 계산한 값) — GBA 헤더 체크섬."""
    chk = 0
    for b in rom[0xA0:0xBD]:
        chk = (chk - b) & 0xFF
    return rom[0xBD], (chk - 0x19) & 0xFF


def digests(data: bytes) -> dict:
    return {
        "crc32": f"{zlib.crc32(data) & 0xFFFFFFFF:08x}",
        "md5": hashlib.md5(data).hexdigest(),
        "sha1": hashlib.sha1(data).hexdigest(),
    }


# --- 포인터 -------------------------------------------------------------

def is_ptr(value: int, rom_len: int) -> bool:
    return ROM_BASE <= value < ROM_BASE + rom_len


def ptr_to_off(value: int, rom_len: int | None = None) -> int:
    off = value - ROM_BASE
    if off < 0 or (rom_len is not None and off >= rom_len):
        raise RomError(f"ROM 범위를 벗어난 포인터: 0x{value:08X}")
    return off


def off_to_ptr(off: int) -> int:
    return off + ROM_BASE


# --- 정수 읽기/쓰기 -----------------------------------------------------

def u8(rom: bytes, off: int) -> int:
    return rom[off]


def u16(rom: bytes, off: int) -> int:
    return int.from_bytes(rom[off:off + 2], "little")


def u32(rom: bytes, off: int) -> int:
    return int.from_bytes(rom[off:off + 4], "little")


def w16(rom: bytearray, off: int, value: int) -> None:
    rom[off:off + 2] = (value & 0xFFFF).to_bytes(2, "little")


def w32(rom: bytearray, off: int, value: int) -> None:
    rom[off:off + 4] = (value & 0xFFFFFFFF).to_bytes(4, "little")


def parse_int(text: str) -> int:
    """0x..., 0b..., 10진수를 모두 받습니다."""
    return int(text, 0)


def find_free_space(rom: bytes, size: int, fill: int = 0xFF,
                    start: int = 0, align: int = 4) -> int | None:
    """`fill` 바이트가 `size`만큼 연속된 첫 영역의 오프셋을 반환합니다."""
    run = 0
    for i in range(start, len(rom)):
        if rom[i] == fill:
            run += 1
            if run >= size:
                off = i - size + 1
                pad = (-off) % align
                if run >= size + pad:
                    return off + pad
        else:
            run = 0
    return None
