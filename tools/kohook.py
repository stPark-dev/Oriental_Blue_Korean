#!/usr/bin/env python3
"""한글 출력 훅 — 음절 글리프를 찾아 8×16 칸 두 개로 나눠 씁니다.

본문 렌더 루프는 칸마다 코드 하나를 처리하고, 큰 폰트 경로에서
`0x0801C904` 의 `bl get_wide(dst, code)` 로 16바이트 글리프를 받아 갑니다.
**그 `bl` 의 대상 주소만 이 훅으로 바꿉니다.** 루프도 다른 코드도 그대로입니다.

호출 시점에 스트림 포인터 `r6` 이 살아 있습니다. `r6` 은 방금 읽은 토큰
**바로 뒤**를 가리키므로, 앞뒤 코드를 모두 볼 수 있습니다.

    앞 코드 차례   뒤 코드는 [r6], [r6+1]      (아직 안 읽음)
    뒤 코드 차례   앞 코드는 [r6-4], [r6-3]    (이미 읽음)

덕분에 **상태 변수가 필요 없습니다.** 두 칸이 각자 음절 전체를 알아냅니다.

코드 배치 — 파라미터는 `0x09` 부터 써서 `0x00`(종결자) 과 `0x08`(이스케이프)
를 피합니다.

    뱅크 3  파라미터 0x09–0xFF   앞 코드 0–246
    뱅크 4  파라미터 0x09–0xA0   앞 코드 247–398
    뱅크 5  파라미터 0x09–0x24   뒤 코드 0–27

    앞 = (뱅크-3)×247 + (파라미터-9)      = 초성×21 + 중성
    뒤 = 파라미터-9                        = 종성
    음절 번호 = 앞×28 + 뒤                 0–11,171
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import thumb  # noqa: E402

GET_WIDE = 0x0801C2EC          # 큰 글리프 인출 (16바이트)
GET_HALF = 0x0801C2D0          # 작은 글리프 인출 (8바이트)

# 본문 렌더 루프의 큰 폰트 경로. dst 가 16바이트 버퍼 그대로입니다.
CALL_SITE = 0x0801C904
# 두 번째 렌더 루프(0x0801CAC8)의 큰 코드 경로. 여기서는 작은 폰트를 부르고
# dst 가 버퍼+8 이라, 8을 되돌려 16행을 통째로 씁니다.
CALL_SITE_HALF = 0x0801CBF0
# 세 번째 렌더러(메뉴 항목). 스트림 포인터가 r6 이 아니라 **r8** 입니다.
CALL_SITE_MENU = 0x0801C5E8

LEAD_BANKS = (3, 4)
TRAIL_BANK = 5
PARAM_FIRST = 0x09             # 0x00·0x08 을 피한 첫 파라미터
PER_BANK = 0x100 - PARAM_FIRST  # 뱅크당 247개
LEAD_COUNT, TRAIL_COUNT = 19 * 21, 28
SYLLABLES = LEAD_COUNT * TRAIL_COUNT
GLYPH_BYTES = 32               # 16행 × 2바이트 (16픽셀 폭)


def lead_code(lead: int) -> int:
    """앞 코드 자리번호(0–398) -> 문자 코드."""
    if not 0 <= lead < LEAD_COUNT:
        raise ValueError(f"앞 코드 범위 밖: {lead}")
    return ((LEAD_BANKS[0] + lead // PER_BANK) << 8) | (
        PARAM_FIRST + lead % PER_BANK)


def trail_code(trail: int) -> int:
    """뒤 코드 자리번호(0–27) -> 문자 코드."""
    if not 0 <= trail < TRAIL_COUNT:
        raise ValueError(f"뒤 코드 범위 밖: {trail}")
    return (TRAIL_BANK << 8) | (PARAM_FIRST + trail)


def decode_pair(lead_c: int, trail_c: int) -> int:
    """문자 코드 두 개 -> 음절 번호. 훅이 하는 계산과 같습니다."""
    lead = ((lead_c >> 8) - LEAD_BANKS[0]) * PER_BANK + (
        (lead_c & 0xFF) - PARAM_FIRST)
    return lead * TRAIL_COUNT + ((trail_c & 0xFF) - PARAM_FIRST)


def build(at: int, slot_table: int, glyphs: int,
          fallback: int = GET_WIDE, dst_back: int = 0,
          stream_reg: int = 6, small: bool = False) -> bytes:
    """훅 코드를 만듭니다. 주소는 모두 0x08000000 기준입니다.

    `fallback` 은 한글이 아닌 코드를 넘길 원래 함수입니다.
    `dst_back` 은 쓰기 전에 dst 에서 뺄 바이트 수입니다 — 호출자가 버퍼
    중간을 가리키는 자리에서 16행을 통째로 쓰기 위한 것입니다.
    `stream_reg` 는 그 호출 지점에서 스트림 포인터가 든 레지스터입니다.
    렌더러마다 다릅니다 (본문 루프는 r6, 메뉴 렌더러는 r8).
    `small` 은 8행 렌더러용입니다 — 글리프가 8바이트이고, 음절을 앞 코드 칸에
    만 그리고 뒤 코드 칸은 비웁니다 (8×8 에 16×16 이 안 들어가므로).
    """
    rows = 8 if small else 16
    gshift = 3 if small else 5            # 슬롯 × 8 또는 × 32
    gstep = 1 if small else 2
    a = thumb.Asm(at)
    a.push([4, 5, 6], lr=True)
    if stream_reg != 6:
        a.mov_hi(6, stream_reg)
    a.lsrs(2, 1, 8)                      # r2 = 뱅크
    a.lsls(3, 1, 24)
    a.lsrs(3, 3, 24)                     # r3 = 파라미터
    a.cmp_imm(2, TRAIL_BANK)
    a.beq("trail")
    a.cmp_imm(2, LEAD_BANKS[0])
    a.blt("orig")
    a.cmp_imm(2, LEAD_BANKS[-1])
    a.bgt("orig")

    # --- 앞 코드: 뒤 코드를 미리 본다 ---
    a.lsls(4, 2, 0)                      # r4 = 앞 뱅크
    a.lsls(5, 3, 0)                      # r5 = 앞 파라미터
    a.ldrb_imm(3, 6, 1)                  # r3 = 뒤 파라미터 ([r6+1])
    a.movs(2, 0)                         # r2 = 왼쪽 절반
    a.b("compute")

    # --- 뒤 코드: 앞 코드를 되짚는다 ---
    a.mark("trail")
    if small:
        a.b("blank")                     # 8×8 에서는 뒤 칸을 비운다
    a.subs_imm3(2, 6, 4)
    a.ldrb_imm(4, 2, 0)                  # r4 = 앞 뱅크   ([r6-4])
    a.ldrb_imm(5, 2, 1)                  # r5 = 앞 파라미터([r6-3])
    a.movs(2, 1)                         # r2 = 오른쪽 절반

    # --- 음절 번호 ---
    a.mark("compute")
    a.subs_imm8(4, LEAD_BANKS[0])
    a.movs(1, PER_BANK)
    a.muls(4, 1)
    a.adds(4, 4, 5)
    a.subs_imm8(4, PARAM_FIRST)          # r4 = 앞 자리번호
    a.movs(1, TRAIL_COUNT)
    a.muls(4, 1)
    a.adds(4, 4, 3)
    a.subs_imm8(4, PARAM_FIRST)          # r4 = 음절 번호
    a.ldr_pool(1, SYLLABLES)
    a.cmp_reg(4, 1)
    a.bcond("ge", "blank")               # 범위 밖이면 빈 칸

    # --- 글리프 찾기 ---
    a.ldr_pool(1, slot_table)
    a.lsls(4, 4, 1)
    a.ldrh_reg(4, 1, 4)                  # r4 = 슬롯
    a.cmp_imm(4, 0)
    a.beq("blank")                       # 쓰지 않는 음절
    a.ldr_pool(1, glyphs)
    a.lsls(4, 4, gshift)                 # 슬롯 × 글리프 크기
    a.adds(1, 1, 4)
    if not small:
        a.adds(1, 1, 2)                  # + 절반 (0 왼쪽 / 1 오른쪽)

    # --- 16행을 한 바이트씩, 두 바이트 간격으로 ---
    if dst_back:
        a.subs_imm8(0, dst_back)
    a.movs(3, 0)
    a.mark("copy")
    a.ldrb_imm(5, 1, 0)
    a.strb_imm(5, 0, 0)
    a.adds_imm8(1, gstep)
    a.adds_imm8(0, 1)
    a.adds_imm8(3, 1)
    a.cmp_imm(3, rows)
    a.blt("copy")
    a.pop([4, 5, 6], pc=True)

    a.mark("blank")
    if dst_back:
        a.subs_imm8(0, dst_back)
    a.movs(5, 0)
    a.movs(3, 0)
    a.mark("clear")
    a.strb_imm(5, 0, 0)
    a.adds_imm8(0, 1)
    a.adds_imm8(3, 1)
    a.cmp_imm(3, rows)
    a.blt("clear")
    a.pop([4, 5, 6], pc=True)

    a.mark("orig")
    a.bl(fallback)
    a.pop([4, 5, 6], pc=True)
    return a.assemble()
