#!/usr/bin/env python3
"""문자 코드 공간 모델.

본문 렌더러(`0x0801C7D8`)의 코드 계산은 `01`–`05` 에 대해 일반적입니다::

    code = (byte << 8) | param        byte 가 1..5 일 때
    code = byte                       그 밖에는 그대로
    code <= 0x7F 면 작은 폰트(8×8), 초과면 큰 폰트(8×16)

따라서 쓸 수 있는 코드는 `0x000`–`0x5FF` 입니다.

전개기 `0x0800D4F8` 은 스트림의 구조를 모른 채 선형으로 훑기 때문에,
파라미터가 `0x00`(종결자) 이나 `0x08`(이스케이프) 이면 문자열이 깨집니다.
"""
from __future__ import annotations

MAX_CODE = 0x600                   # 코드 0x000-0x5FF (뱅크 5 까지)
BAD_PARAMS = (0x00, 0x08)          # 전개기가 종결자·이스케이프로 오해하는 값

SYLLABLE_FIRST, SYLLABLE_LAST = 0xAC00, 0xD7A3


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


