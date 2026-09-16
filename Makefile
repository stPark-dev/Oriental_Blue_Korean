# 오리엔탈블루 청의천외 한글화 — 빌드 스크립트
# 리눅스/macOS 기준. 표준 라이브러리 외 의존성은 Pillow(폰트 생성)뿐입니다.

PYTHON  ?= python3
ROM     ?= rom/baserom.gba
CONFIG  ?= config/blocks.json
BUILD   ?= build
PATCHED := $(BUILD)/patched.gba
PATCH   ?= patch/oriental_blue_ko.bps
SHA1    ?= 414cad1aee67ab20f3c133f0259da7e8c3073bbc

.DEFAULT_GOAL := help

help: ## 사용 가능한 타깃 목록
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

check: ## 원본 ROM 확인 (SHA-1 대조)
	@$(PYTHON) tools/romcheck.py $(ROM) --expect-sha1 $(SHA1)

scan-ptr: ## 포인터 테이블 후보 탐색
	@$(PYTHON) tools/scan.py pointers $(ROM) --min 32 -o $(BUILD)/scan_ptr.tsv

scan-text: ## 평문 Shift-JIS 구간 탐색
	@$(PYTHON) tools/scan.py sjis $(ROM) --min 8 -o $(BUILD)/scan_sjis.tsv

scan-lz: ## 압축 블록 탐색
	@$(PYTHON) tools/gbalz.py scan $(ROM) --min 256 -o $(BUILD)/scan_lz.tsv

dump: ## 원문 스크립트 덤프 -> script/ja/
	@$(PYTHON) tools/dumptext.py $(ROM) --config $(CONFIG) --out script/ja

charset: ## 번역문에서 사용 문자 추출
	@$(PYTHON) tools/charset.py script/ko -o font/charset.txt --freq

font: charset ## 한글 서브셋 폰트 생성 (FONT=... 로 TTF 지정)
	@test -n "$(FONT)" || (echo "FONT=경로/폰트.ttf 를 지정하세요"; exit 1)
	@$(PYTHON) tools/mkfont.py $(FONT) font/charset.txt -o $(BUILD)/kofont \
		--size 12 --cell 12x12 --bpp 1 --preview $(BUILD)/kofont.png

insert: ## 번역문 재삽입 -> build/patched.gba
	@$(PYTHON) tools/inserttext.py $(ROM) $(PATCHED) --config $(CONFIG)

patch: insert ## 배포용 BPS 패치 생성
	@$(PYTHON) tools/patch.py make $(ROM) $(PATCHED) $(PATCH)

build: check insert patch ## 전체 빌드

verify: ## 생성된 패치를 원본에 적용해 검증
	@$(PYTHON) tools/patch.py apply $(ROM) $(PATCH) $(BUILD)/verify.gba
	@cmp $(BUILD)/verify.gba $(PATCHED) && echo "검증 통과"

run: $(PATCHED) ## mGBA로 실행
	@mgba-qt $(PATCHED) || mgba $(PATCHED)

clean: ## 빌드 산출물 삭제
	@rm -rf $(BUILD)/*.gba $(BUILD)/*.tsv $(BUILD)/*.png $(BUILD)/*.log
	@echo "정리 완료"

.PHONY: help check scan-ptr scan-text scan-lz dump charset font insert patch build verify run clean
