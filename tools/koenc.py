#!/usr/bin/env python3
"""번역문(`script/ko/*.txt`)을 게임 바이트열로 인코딩합니다.

문자열 형식은 원문과 같습니다::

    한글 음절   코드 두 개 (8×16 칸 두 개로 16×16 을 그립니다)
    그 밖의 문자 원문 대응표에 있는 코드 그대로
    줄바꿈       0x0A
    <$XX>       원시 바이트 (제어 코드 등 원문 보존용)
    문자열 끝    0x00

전개기 `0x0800D4F8` 은 스트림의 구조를 모른 채 선형으로 훑습니다. 따라서
**문자 코드 자리에 `0x00` 이나 `0x08` 이 나오면 문자열이 깨집니다.**
인코딩할 때마다 검사합니다.
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kocode  # noqa: E402

TERMINATOR = 0x00
NEWLINE = 0x0A
ESCAPE = 0x08
TAG_RE = re.compile(r"<\$([0-9A-Fa-f]{2,3})>")


class EncodeError(Exception):
    pass


def tokens(text: str) -> list[tuple[str, object]]:
    """문자열을 ('char'|'raw'|'code'|'newline', 값) 목록으로 나눕니다."""
    out: list[tuple[str, object]] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "<":
            m = TAG_RE.match(text, i)
            if not m:
                raise EncodeError(f"태그를 해석할 수 없습니다: {text[i:i + 8]!r}")
            v = int(m.group(1), 16)
            out.append(("raw" if len(m.group(1)) == 2 else "code", v))
            i = m.end()
            continue
        if ch == "\n":
            out.append(("newline", None))
        else:
            out.append(("char", ch))
        i += 1
    return out


def used_chars(text: str) -> set[str]:
    """태그와 줄바꿈을 뺀 실제 문자들."""
    return {v for kind, v in tokens(text) if kind == "char"}


def _emit(out: bytearray, code: int, where: str) -> None:
    data = kocode.encode_code(code)
    if len(data) == 2 and data[1] in (TERMINATOR, ESCAPE):
        raise EncodeError(
            f"{where}: 코드 0x{code:03X} 의 파라미터가 0x{data[1]:02X} 입니다. "
            "전개기가 종결자/이스케이프로 오해합니다")
    if len(data) == 1 and data[0] in (TERMINATOR, ESCAPE):
        raise EncodeError(
            f"{where}: 코드 0x{code:02X} 는 전개기가 오해하는 값입니다")
    out += data


def encode(text: str, ko_map: dict[str, tuple[int, int]],
           ja_map: dict[str, int]) -> bytes:
    """번역문 한 항목을 바이트열로. 끝에 종결자를 붙입니다."""
    out = bytearray()
    for kind, v in tokens(text):
        if kind == "newline":
            out.append(NEWLINE)
        elif kind in ("raw", "code"):
            if kind == "raw" and v in (TERMINATOR, ESCAPE):
                raise EncodeError(
                    f"원시 바이트 0x{v:02X} 는 넣을 수 없습니다 "
                    "(전개기가 종결자/이스케이프로 읽습니다)")
            if kind == "raw":
                out.append(v)
            else:
                _emit(out, v, f"<${v:03X}>")
        else:
            ch = v
            if ch in ko_map:
                left, right = ko_map[ch]
                _emit(out, left, f"'{ch}' 왼쪽")
                _emit(out, right, f"'{ch}' 오른쪽")
            elif ch in ja_map:
                _emit(out, ja_map[ch], f"'{ch}'")
            else:
                raise EncodeError(f"대응되는 코드가 없는 문자: {ch!r}")
    out.append(TERMINATOR)
    return bytes(out)
