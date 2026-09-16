#!/usr/bin/env python3
"""번역 스크립트 텍스트 파일의 읽기/쓰기 형식.

파일 형식 (UTF-8)::

    ## 0000 @0x1234AB
    안녕하세요.<LINE>
    반갑습니다.<END>

    ## 0001 @0x1234C0
    ...

- `## <인덱스> @<원본오프셋>` 이 한 항목의 시작입니다.
- 그 아래부터 다음 헤더 전까지가 본문이며, 마지막 빈 줄은 제거됩니다.
- `#` 으로 시작하는 그 밖의 줄은 주석입니다.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

HEADER_RE = re.compile(r"^##\s+(\d+)\s+@(0x[0-9A-Fa-f]+)\s*$")


@dataclass
class Entry:
    index: int
    offset: int
    text: str
    note: str = ""


@dataclass
class ScriptFile:
    name: str
    entries: list[Entry] = field(default_factory=list)

    def write(self, path: str, header_comment: str = "") -> None:
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            if header_comment:
                for line in header_comment.strip().splitlines():
                    f.write(f"# {line}\n")
                f.write("\n")
            for e in self.entries:
                f.write(f"## {e.index:04d} @0x{e.offset:06X}\n")
                f.write(e.text.rstrip("\n") + "\n\n")

    @classmethod
    def read(cls, path: str) -> "ScriptFile":
        sf = cls(name=os.path.splitext(os.path.basename(path))[0])
        cur: Entry | None = None
        buf: list[str] = []
        with open(path, "r", encoding="utf-8") as f:
            for lineno, raw in enumerate(f, 1):
                line = raw.rstrip("\n")
                m = HEADER_RE.match(line)
                if m:
                    if cur is not None:
                        cur.text = "\n".join(buf).strip("\n")
                        sf.entries.append(cur)
                    cur = Entry(int(m.group(1)), int(m.group(2), 16), "")
                    buf = []
                    continue
                if cur is None:
                    continue  # 파일 상단 주석
                buf.append(line)
        if cur is not None:
            cur.text = "\n".join(buf).strip("\n")
            sf.entries.append(cur)
        return sf


def pair(ja_path: str, ko_path: str) -> list[tuple[Entry, Entry | None]]:
    """원문과 번역문을 인덱스로 짝지어 줍니다."""
    ja = ScriptFile.read(ja_path)
    ko_map = {e.index: e for e in ScriptFile.read(ko_path).entries} \
        if os.path.exists(ko_path) else {}
    return [(e, ko_map.get(e.index)) for e in ja.entries]
