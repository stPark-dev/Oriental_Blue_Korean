#!/usr/bin/env python3
"""한글 음절 분해와 코드 쌍 인코딩.

본문 코드 공간(1,398개)으로는 음절을 직접 담을 수 없습니다. 대신 음절 하나를
**코드 두 개**로 쪼개면 11,172자를 전부 표현할 수 있습니다.

본문 인코딩은 음절 하나에 코드 두 개입니다 (16×16 = 8픽셀 칸 두 개).

    앞 코드  초성×중성 = 399가지
    뒤 코드  종성      = 28가지 (없음 포함)

둘을 합치면 11,172음절 전부를 표현합니다.
"""
from __future__ import annotations

FIRST, LAST = 0xAC00, 0xD7A3

CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
JONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"


def decompose(ch: str) -> tuple[int, int, int]:
    """음절 하나를 (초성, 중성, 종성) 색인으로. 종성 0 은 없음입니다."""
    if len(ch) != 1 or not (FIRST <= ord(ch) <= LAST):
        raise ValueError(f"완성형 한글 음절이 아닙니다: {ch!r}")
    n = ord(ch) - FIRST
    return n // (21 * 28), (n // 28) % 21, n % 28


def compose_char(cho: int, jung: int, jong: int) -> str:
    return chr(FIRST + (cho * 21 + jung) * 28 + jong)


def to_pair(ch: str) -> tuple[int, int]:
    """음절 -> (앞 코드 자리번호 0..398, 뒤 코드 자리번호 0..27)."""
    cho, jung, jong = decompose(ch)
    return cho * 21 + jung, jong


def from_pair(lead: int, trail: int) -> str:
    return compose_char(lead // 21, lead % 21, trail)
