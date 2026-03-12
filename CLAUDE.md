# CLAUDE.md — threadloom

## 프로젝트 개요

threadloom은 **AI 자기강화 도구**다.
Threads 저장 포스트에서 유용한 패턴을 발견하고, AI가 스스로 자신의 skills · agents · rules를 생성·수정한다.
Obsidian 아카이빙은 부가 기능이다.

**4-Phase md 파이프라인** (AI CLI 호출 총 2회):
```
Phase 1: 수집 (Python)       → data/raw/{ts}.md
Phase 2: 분석 (AI 1회)       → data/analysis/{ts}.md
Phase 3: 강화 생성 (AI 1회)   → data/pending/*.md
Phase 3.5: 자동 심사 (Python) → 거부 항목 data/rejected/ 이동
Phase 4: 적용 (Python)       → .claude/skills/, agents/, CLAUDE.md
```

상세 구현 명세는 `SPEC.md`를 참조한다.

---

## 절대 규칙

1. credentials, 토큰, 패스워드를 코드에 하드코딩 금지
2. `config.yaml`, `.env`, `auth/`, `data/`, `logs/`는 절대 Git 추적 금지
3. 모든 외부 입력(포스트 텍스트, URL 등)은 sanitize 후 사용
4. Playwright 세션 파일은 `auth/` 폴더에만 저장
5. 테스트 코드는 실제 Threads 접속 없이 mock 데이터만 사용
6. 에러 발생 시 stack trace에 사용자 경로나 ID 노출 금지 (마스킹 처리)
7. 대상 프로젝트 CLAUDE.md 수정 시 `## threadloom-rules` 섹션만 관리 — 기존 규칙 절대 수정 금지

---

## 기술 스택

- **언어**: Python 3.10+
- **수집**: Playwright (headless Chromium)
- **인증**: keyring (OS Keychain)
- **설정**: PyYAML (`config.yaml`)
- **콘솔**: rich (컬러 출력, 진행률)
- **링크 크롤링**: requests + BeautifulSoup4
- **AI**: CLI subprocess 호출 (claude / codex / gemini)
- **테스트**: pytest + mock

---

## 디렉토리 구조

```
src/
├── main.py              # CLI 진입점 + argparse 파서
├── config.py            # 설정 로더
├── cli/                 # CLI 커맨드 핸들러
│   ├── commands.py      # 독립 커맨드 (--setup-auth, --review, --rollback 등)
│   └── status_display.py # 상태 조회 (pending/applied/rejected 건수)
├── pipeline/            # Phase 실행 오케스트레이터
│   ├── runner.py        # Phase 1~4 실행, 전체 파이프라인 조정
│   └── pipeline_output.py # dry-run 시각화, Obsidian 아카이빙, 리포트
├── ai_adapter/          # AI CLI 어댑터 (프롬프트 영어, 응답만 ai.language 따름)
├── collector/           # Threads 수집 + 인증 (checkpointing 포함)
│   ├── models.py        # ThreadPost 데이터 모델 (link_contents 포함)
│   ├── post_parser.py   # DOM 파싱 (텍스트 정제, 미디어/URL 추출)
│   ├── reply_collector.py # self-reply 수집 (순차/병렬)
│   ├── raw_writer.py    # raw markdown 출력 (링크 내용 포함)
│   ├── link_fetcher.py  # 외부 링크 크롤링 (requests + BeautifulSoup)
│   ├── checkpoint.py    # checkpoint 저장/복원
│   ├── selector_map.py  # CSS 셀렉터 로더 (캐시, fallback, reload)
│   ├── selectors.yaml   # CSS 셀렉터 외부 정의 파일
│   └── async_scraper.py # 병렬 상세 수집 (Playwright async + asyncio.Semaphore)
├── processor/           # 분류 + 유용성 판단
├── enhancer/            # ★ 핵심: AI 자기강화 + 자동 심사
│   ├── models.py        # PendingAction 데이터 모델
│   ├── pending_parser.py # pending 파일 파싱
│   ├── action_executor.py # action 적용 분기 + CLAUDE.md 규칙
│   ├── backup_manager.py # 백업/복원/이력 관리
│   ├── pending_manager.py # pending 파일 생명주기
│   ├── response_parser.py # AI 응답 파싱 전략
│   ├── reviewer_config.py # 심사 상수 데이터
│   └── stack_detector.py # 기술 스택 감지
├── writer/              # Obsidian 아카이빙 + 리포트 + review_display.py
└── utils/               # 로깅, 상태 관리, 알림, 진단, 검색
    ├── i18n.py          # 다국어 메시지 (한/영 자동 감지)
    ├── process_lock.py  # 실행 잠금 관리 (PID 기반)
    ├── batch_splitter.py # 배치 분할 (raw md -> 여러 파일)
    ├── frontmatter.py   # YAML frontmatter 파싱
    ├── post_block_parser.py # 포스트 블록 파싱 공통 모듈
    ├── health_check.py  # 의존성 진단
    └── search.py        # 수집 아카이브 검색
```

---

## 코딩 규칙

- 파일명: `snake_case.py`
- 클래스: `PascalCase`, 함수/변수: `camelCase` 아닌 `snake_case` (Python 컨벤션)
- 주석: 한국어, 영어 용어 첫 등장 시 병기 — `# 유용성(relevance) 점수 계산`
- 함수: 20줄 이하, 매개변수 3개 이하
- 타입 힌트 필수 (`def foo(x: str) -> bool:`)
- 로그에 민감정보(경로, ID) 마스킹 필수

---

## 빌드 및 검증

```bash
# 설치
./setup.sh

# 테스트
.venv/bin/python3 -m pytest tests/ -v

# 보안 검증
git ls-files | grep -E "\.env$|config\.yaml$|auth/|data/"
# 출력 없어야 정상

# dry-run (run.sh 사용 권장)
./run.sh --dry-run

# 강화 검토 (--review 모드에서 [e]로 에디터 편집 가능)
./run.sh --review

# 의존성 상태 진단 (7개 항목 OK/WARN/FAIL)
./run.sh --check

# 수집/분석 데이터 검색
./run.sh --search "검색어"

# PYTHONPATH 직접 지정 방식 (동일 동작)
PYTHONPATH=. .venv/bin/python3 src/main.py --dry-run
```

---

## 에러 처리 원칙

- Phase 2 분석 실패 → `_fallback_analysis()`로 최소 분석 결과 생성 (전부 category: 기타)
- Phase 3 생성 실패 → raw 응답을 `data/pending/raw_fallback_{ts}.md`로 저장, 사용자 수동 검토
- 파일 쓰기 실패 → 에러 로그 후 계속 (전체 중단 안 함)
- AI CLI 응답 없음 → 3초 대기 후 1회 재시도, 실패 시 fallback 적용
- 동시 실행 방지: `data/.lock` 파일 기반 실행 잠금 (PID 저장, stale lock 감지)
- 모든 파일 UTF-8 인코딩
