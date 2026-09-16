#!/usr/bin/env python3
"""Thingy 형식 테이블(.tbl) 파서 — 바이트 <-> 문자 변환.

지원하는 줄 형식::

    41=A                # 1바이트
    8140=　             # 멀티바이트 (길이 제한 없음)
    FF=<END>            # 제어 코드는 <...> 로 표기
    FE=<LINE>\n         # 줄바꿈을 함께 넣고 싶을 때
    /FF                 # 종결자 지정 (덤프 시 문자열을 끊는 바이트)
    *FE                 # 개행 코드 지정
    #                   # 주석

디코딩은 항상 '가장 긴 일치'를 먼저 시도합니다.
"""
from __future__ import annotations

import sys


class Table:
    def __init__(self) -> None:
        self.dec: dict[bytes, str] = {}
        self.enc: dict[str, bytes] = {}
        self.terminators: set[bytes] = set()
        self.linebreaks: set[bytes] = set()
        self.max_len = 1

    # -- 로딩 ----------------------------------------------------------
    @classmethod
    def load(cls, path: str) -> "Table":
        t = cls()
        with open(path, "r", encoding="utf-8") as f:
            for lineno, raw in enumerate(f, 1):
                line = raw.rstrip("\r\n")
                if not line or line.lstrip().startswith("#"):
                    continue
                try:
                    t._add_line(line)
                except ValueError as e:
                    raise ValueError(f"{path}:{lineno}: {e}") from None
        return t

    def _add_line(self, line: str) -> None:
        if line[0] in "/*":
            code = bytes.fromhex(line[1:].strip())
            (self.terminators if line[0] == "/" else self.linebreaks).add(code)
            self.dec.setdefault(code, "<END>" if line[0] == "/" else "\n")
            self.max_len = max(self.max_len, len(code))
            return

        if "=" not in line:
            raise ValueError(f"'=' 가 없는 줄: {line!r}")
        hex_part, value = line.split("=", 1)
        hex_part = hex_part.strip()
        if len(hex_part) % 2 or not hex_part:
            raise ValueError(f"16진수 길이가 잘못됨: {hex_part!r}")
        code = bytes.fromhex(hex_part)
        value = value.replace("\n", "\n")

        self.dec[code] = value
        self.enc.setdefault(value, code)
        self.max_len = max(self.max_len, len(code))

    # -- 변환 ----------------------------------------------------------
    def decode(self, data: bytes, start: int = 0, end: int | None = None,
               stop_at_terminator: bool = True) -> tuple[str, int]:
        """(문자열, 소비한 마지막 오프셋+1) 을 반환합니다."""
        end = len(data) if end is None else end
        out: list[str] = []
        i = start
        while i < end:
            for n in range(min(self.max_len, end - i), 0, -1):
                code = bytes(data[i:i + n])
                if code in self.dec:
                    out.append(self.dec[code])
                    i += n
                    if stop_at_terminator and code in self.terminators:
                        return "".join(out), i
                    break
            else:
                out.append(f"<${data[i]:02X}>")
                i += 1
        return "".join(out), i

    def encode(self, text: str) -> bytes:
        """테이블에 없는 문자는 ValueError. <$XX> 는 원시 바이트로 처리."""
        out = bytearray()
        i = 0
        while i < len(text):
            if text[i] == "<":
                close = text.find(">", i)
                if close == -1:
                    raise ValueError(f"닫히지 않은 태그: {text[i:i + 20]!r}")
                tag = text[i:close + 1]
                if tag.startswith("<$"):
                    out += bytes.fromhex(tag[2:-1])
                elif tag in self.enc:
                    out += self.enc[tag]
                else:
                    raise ValueError(f"테이블에 없는 제어 코드: {tag}")
                i = close + 1
                continue

            for n in range(min(8, len(text) - i), 0, -1):
                chunk = text[i:i + n]
                if chunk in self.enc:
                    out += self.enc[chunk]
                    i += n
                    break
            else:
                raise ValueError(f"테이블에 없는 문자: {text[i]!r} (U+{ord(text[i]):04X})")
        return bytes(out)

    def missing(self, text: str) -> set[str]:
        """인코딩 불가능한 문자만 모아서 반환합니다."""
        bad = set()
        i = 0
        while i < len(text):
            if text[i] == "<":
                close = text.find(">", i)
                if close != -1:
                    i = close + 1
                    continue
            for n in range(min(8, len(text) - i), 0, -1):
                if text[i:i + n] in self.enc:
                    i += n
                    break
            else:
                bad.add(text[i])
                i += 1
        return bad


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 1
    t = Table.load(argv[1])
    print(f"항목 {len(t.dec)}개, 최대 코드 길이 {t.max_len}바이트")
    print(f"종결자: {[c.hex().upper() for c in t.terminators] or '없음'}")
    print(f"개행:   {[c.hex().upper() for c in t.linebreaks] or '없음'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
