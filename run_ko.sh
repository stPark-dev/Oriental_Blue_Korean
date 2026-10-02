#!/usr/bin/env bash
# 한글 패치 ROM 을 만들어 mGBA 로 실행합니다.
#
#   ./run_ko.sh              빌드(make insert) 후 실행
#   ./run_ko.sh --no-build   이미 만든 build/patched.gba 를 바로 실행
#
# 바꿀 수 있는 것 (환경 변수):
#   VENV=~/myenv                     파이썬 가상환경
#   MGBA=../mgba/mgba.appimage       mGBA 실행 파일
set -euo pipefail
cd "$(dirname "$0")"

VENV=${VENV:-$HOME/myenv}
MGBA=${MGBA:-../mgba/mgba.appimage}
ROM=build/patched.gba

if [ -f "$VENV/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "$VENV/bin/activate"
fi
PY=$(command -v python || command -v python3)

if [ "${1:-}" != "--no-build" ]; then
    if [ ! -f rom/baserom.gba ]; then
        echo "원본 ROM 이 없습니다: rom/baserom.gba" >&2
        exit 1
    fi
    make insert PYTHON="$PY"
fi

if [ ! -f "$ROM" ]; then
    echo "패치 ROM 이 없습니다: $ROM — 빌드부터 하세요 (./run_ko.sh)" >&2
    exit 1
fi

if [ -x "$MGBA" ]; then
    exec "$MGBA" "$ROM"
elif command -v mgba-qt >/dev/null; then
    exec mgba-qt "$ROM"
elif command -v mgba >/dev/null; then
    exec mgba "$ROM"
fi
echo "mGBA 를 찾지 못했습니다. MGBA=/경로/mgba ./run_ko.sh 로 지정하세요" >&2
exit 1
