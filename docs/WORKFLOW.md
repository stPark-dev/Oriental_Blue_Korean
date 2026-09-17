# 작업 흐름

주 작업 환경은 **리눅스**입니다. 모든 툴은 파이썬 3.10+ 표준 라이브러리로 동작하며,
폰트 생성에만 Pillow가 필요합니다. 외부 ROM 해킹 유틸(flips 등)은 필요 없습니다.

## 준비

```bash
git clone https://github.com/stPark-dev/Oriental_Blue_Korean.git
cd Oriental_Blue_Korean

make hooks          # ROM·대용량 파일 커밋 차단 훅 설치 (권장)

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 본인이 덤프한 일본판 ROM을 배치 (저장소에 포함되지 않습니다)
cp /경로/오리엔탈블루.gba rom/baserom.gba
make check          # SHA-1 대조
```

`make` 만 치면 사용 가능한 타깃이 나옵니다.

## 사이클

```
 ROM ──scan──▶ 구조 파악 ──dump──▶ script/ja/*.txt
                                      │
                                   (번역)
                                      ▼
 patch ◀──insert──  script/ko/*.txt ──┘
```

| 단계 | 명령 | 설명 |
| --- | --- | --- |
| 1. 확인 | `make check` | ROM 식별·무결성 |
| 2. 탐색 | `make scan-ptr` / `scan-text` / `scan-lz` | 포인터·텍스트·압축 블록 후보 |
| 3. 정의 | `config/blocks.json` 편집 | 찾은 오프셋을 블록으로 등록 |
| 4. 덤프 | `make script` | `script/ja/` 원문 + `script/ko/` 번역 골격 생성 |
| 5. 번역 | `script/ko/` 편집 | 아래 형식 참고 |
| 6. 폰트 | `make font FONT=font/Galmuri9.ttf` | 사용 문자만 서브셋 |
| 7. 삽입 | `make insert` | `build/patched.gba` |
| 8. 패치 | `make patch` | `patch/*.bps` |
| 9. 검증 | `make verify` / `make run` | 재적용 대조 · mGBA 실행 |

## 스크립트 덤프

```bash
make script      # 문자열 테이블 스캔 -> 대응표 생성 -> 전체 덤프
```

| 항목 | 수 |
| --- | --- |
| 테이블 후보 | 133개 |
| 바이너리 블롭 테이블(제외) | 16개 / 3,758항목 |
| **텍스트 테이블** | **117개** |
| 전체 항목 | 18,547개 |
| 전개 성공 | 18,547개 (100%) |
| 빈 문자열(번역 대상 아님) | 1,871개 |
| **실질 번역 대상** | **16,676개** |

`script/ja/` 는 **커밋하지 않습니다.** 게임 원문이므로 각자 자기 ROM에서
재생성하세요. `script/ko/` 의 골격 파일은 저장소에 들어 있으며, 헤더만 있고
본문이 비어 있습니다.

## 스크립트 파일 형식

`script/ja/*.txt` (자동 생성)와 `script/ko/*.txt` (사람이 작성)는 같은 형식입니다.

```
## 0000 @0x1234AB
안녕하세요.<LINE>
반갑습니다.<END>

## 0001 @0x1234C0
...
```

- `## <인덱스> @<원본오프셋>` 이 항목 시작. **인덱스를 바꾸지 마세요** — 삽입 시 포인터 대응에 씁니다.
- `<...>` 는 제어 코드. `<$XX>` 는 원시 바이트를 직접 넣습니다.
- `script/ko/` 에는 헤더만 있는 골격이 이미 있습니다. 같은 이름의 `script/ja/`
  파일을 나란히 놓고 ko 쪽 본문을 채우세요.
- `<F3:XX>` `<F4:XX>` `<F5:XX>` 는 서식 제어입니다. 위치를 바꾸지 마세요.
- `<$10>` 처럼 `<$` 로 시작하는 태그는 아직 의미를 모르는 코드를 원본 그대로
  보존한 것입니다. 삭제하지 말고 그대로 두세요.
- 항목을 빈 줄로 두면 삽입 시 건너뜁니다 (원문 유지).

## 한글 폰트

한글 음절 11,172자를 전부 넣을 수는 없으므로 **사용된 글자만 서브셋**합니다.

```bash
make charset                              # script/ko 에서 사용 문자 추출
make font FONT=font/Galmuri9.ttf          # 서브셋 폰트 + 미리보기 PNG
```

권장 비트맵 폰트 (라이선스 확인 후 `font/` 에 직접 배치, 저장소에는 미포함):

- **갈무리 (Galmuri)** — OFL, 9/11px 픽셀 폰트. GBA 해상도(240×160)에 적합
- **둥근모꼴 / Neo둥근모** — 자유 이용, 16px 고정폭

번역이 늘어나면 문자 집합이 바뀌므로, `make font` 는 **삽입 직전에 다시 돌립니다**.

## 규칙

- **ROM과 패치 결과물은 커밋하지 않습니다.** `.gitignore` 와 pre-commit 훅으로 이중 차단합니다.
  - `.gitignore` 는 *이미 추적 중인 파일에는 적용되지 않으므로*, 훅이 마지막 방어선입니다.
  - 훅은 `.githooks/pre-commit` 에 있고 `make hooks` 로 설치합니다 (`core.hooksPath` 는
    로컬 설정이라 clone 한 사람마다 한 번씩 실행해야 합니다).
  - 차단 대상: ROM/패치 확장자(`gba` `nds` `ips` `bps` 등)와 1MB 초과 파일.
  - 용량 제한만 임시 해제: `ALLOW_BIG=1 git commit ...` (ROM 확장자는 해제되지 않습니다).
- 텍스트 파일은 전부 LF (`.gitattributes` 로 강제).
- `script/ja/` 는 자동 생성물이므로 직접 수정하지 않습니다.
- 새로 알아낸 ROM 구조는 `docs/ROM_NOTES.md` 에 근거와 함께 남깁니다.

## 번역 지침

- 고유명사는 첫 등장 시 표기를 정하고 이후 통일합니다.
- 메시지 창 폭 제한이 확인되기 전까지는 원문보다 길어지지 않게 씁니다.
- 제어 코드 `<...>` 는 위치를 바꾸지 말고 그대로 두세요. 삭제하면 게임이 멈출 수 있습니다.
