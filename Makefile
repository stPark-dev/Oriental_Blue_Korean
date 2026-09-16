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

hooks: ## git 훅 설치 (ROM·대용량 파일 커밋 차단)
	@git config core.hooksPath .githooks
	@chmod +x .githooks/* 2>/dev/null || true
	@echo "설치 완료: core.hooksPath = .githooks"

check: ## 원본 ROM 확인 (SHA-1 대조)
	@$(PYTHON) tools/romcheck.py $(ROM) --expect-sha1 $(SHA1)

scan-ptr: ## 포인터 테이블 후보 탐색
	@$(PYTHON) tools/scan.py pointers $(ROM) --min 32 -o $(BUILD)/scan_ptr.tsv

scan-text: ## 평문 Shift-JIS 구간 탐색
	@$(PYTHON) tools/scan.py sjis $(ROM) --min 8 -o $(BUILD)/scan_sjis.tsv

scan-lz: ## 압축 블록 탐색
	@$(PYTHON) tools/gbalz.py scan $(ROM) --min 256 -o $(BUILD)/scan_lz.tsv

grid: ## 이름 입력 문자 그리드 -> build/grid_*.tbl (ROM 파생물, 커밋 안 함)
	@$(PYTHON) tools/dumpgrid.py $(ROM) 0x08ADEC --count 384 --tbl $(BUILD)/grid_a.tbl
	@$(PYTHON) tools/dumpgrid.py $(ROM) 0x08B142 --count 597 --tbl $(BUILD)/grid_b.tbl
	@cat $(BUILD)/grid_a.tbl $(BUILD)/grid_b.tbl | grep -v '^#' | sort -u > $(BUILD)/grid_all.tbl
	@echo "통합: $(BUILD)/grid_all.tbl"

strings: ## 문자열 테이블 탐색 -> build/strtables.tsv
	@$(PYTHON) tools/obtext.py scan $(ROM) --min-count 32 -o $(BUILD)/strtables.tsv

vm: ## 이벤트 VM 레코드 요약 (EN=영문판 지정 시 대조)
	@$(PYTHON) tools/vmrec.py $(ROM) --stats --min-count 8 $(if $(EN),--diff $(EN))

grid-find: ## 문자 그리드 후보 탐색
	@$(PYTHON) tools/dumpgrid.py $(ROM) --find --min-cells 40

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

.PHONY: help hooks check scan-ptr scan-text scan-lz strings vm grid grid-find dump charset font insert patch build verify run clean
