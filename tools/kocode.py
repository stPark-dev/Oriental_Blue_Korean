#!/usr/bin/env python3
"""한글 코드 공간 모델과 할당.

본문 렌더러(`0x0801C7D8`)의 코드 계산은 `01`–`05` 에 대해 일반적입니다::

    code = (byte << 8) | param        byte 가 1..5 일 때
    code = byte                       그 밖에는 그대로
    code <= 0x7F 면 작은 폰트(8×8), 초과면 큰 폰트(8×16)

따라서 쓸 수 있는 코드는 `0x000`–`0x5FF` 입니다. 한글은 8픽셀 폭 칸 **두 개**
(16×16)를 쓰므로 음절 하나가 코드 두 개를 차지합니다.

피해야 하는 값이 있습니다. 전개기 `0x0800D4F8` 은 스트림의 구조를 모른 채
선형으로 훑기 때문입니다.

    파라미터 0x00   종결자로 해석 — 문자열이 끊깁니다
    파라미터 0x08   역참조 이스케이프로 해석 — 뒤 2바이트를 먹습니다

직접 코드는 `0x80`–`0xFF` 만 씁니다. `0x7F` 이하는 작은 폰트로 그려지고,
`0x00`–`0x20` 은 제어 코드 자리입니다.
"""
from __future__ import annotations

MAX_CODE = 0x600
BANKS = (1, 2, 3, 4, 5)
BAD_PARAMS = (0x00, 0x08)          # 전개기가 오해하는 값
DIRECT_FIRST, DIRECT_LAST = 0x80, 0xFF

SYLLABLE_FIRST, SYLLABLE_LAST = 0xAC00, 0xD7A3


class OutOfCodes(Exception):
    pass


def is_syllable(ch: str) -> bool:
    """완성형 한글 음절(가–힣)인지."""
    return len(ch) == 1 and SYLLABLE_FIRST <= ord(ch) <= SYLLABLE_LAST


def encode_code(code: int) -> bytes:
    """문자 코드를 본문 바이트열로."""
    if not (0 <= code < MAX_CODE):
        raise ValueError(f"코드 범위 밖: 0x{code:X}")
    if code < 0x100:
        return bytes([code])
    return bytes([code >> 8, code & 0xFF])


def usable_codes(banks: tuple[int, ...] = BANKS,
                 include_direct: bool = True) -> list[int]:
    """한글 글리프를 둘 수 있는 코드 목록 (큰 폰트로 그려지는 것만)."""
    out = []
    if include_direct:
        out.extend(range(DIRECT_FIRST, DIRECT_LAST + 1))
    for bank in banks:
        out.extend((bank << 8) | p for p in range(0x100)
                   if p not in BAD_PARAMS)
    return out


def allocate(text: str, pool: list[int],
             reserved: set[int] | None = None) -> dict[str, tuple[int, int]]:
    """텍스트에 쓰인 음절마다 코드 두 개를 배정합니다.

    등장 순서를 유지하므로 같은 입력이면 항상 같은 결과가 나옵니다.
    """
    reserved = reserved or set()
    free = [c for c in pool if c not in reserved]
    want = [c for c in dict.fromkeys(text) if is_syllable(c)]
    out: dict[str, tuple[int, int]] = {}
    i = 0
    for ch in want:
        if i + 1 >= len(free):
            raise OutOfCodes(
                f"코드 공간 부족 — 음절 {len(want)}자가 필요한데 {len(free) // 2}자만 "
                f"들어갑니다 ({len(want) - len(free) // 2}자 초과). "
                f"'{ch}' 부터 배정하지 못했습니다. "
                f"절대 상한은 {len(pool) // 2}자이고, 미번역 원문이 "
                f"코드 {len([c for c in pool if c in reserved])}개를 예약 중입니다")
        out[ch] = (free[i], free[i + 1])
        i += 2
    return out


def capacity(banks: tuple[int, ...] = BANKS,
             include_direct: bool = True,
             reserved: set[int] | None = None) -> int:
    """배정 가능한 음절 수."""
    n = len(usable_codes(banks, include_direct))
    if reserved:
        n -= sum(1 for c in usable_codes(banks, include_direct) if c in reserved)
    return n // 2
