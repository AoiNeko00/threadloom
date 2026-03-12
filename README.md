# 🧵 threadloom

> Threads 저장 포스트에서 유용한 패턴을 발견하고, AI가 스스로 자신의 skills · agents · rules를 강화하는 로컬 자동화 도구

베틀(loom)이 실(thread)을 엮어 천을 만들듯,
흘러가는 Threads 피드에서 저장한 인사이트를 엮어 AI의 능력을 자가 강화합니다.

---

## ✨ 주요 기능

- **수동 실행 기반**: 사용자가 원할 때 실행 — 서버나 상시 수집 없음
- **스레드 전체 수집**: 본문 + 작성자 이어쓰기(self-reply)를 함께 수집하여 전체 맥락 보존
- **Checkpointing**: 스크롤 수집 중 비정상 종료 시 `data/raw/.checkpoint_*.json`에서 이어서 재개
- **AI 자기강화**: 수집된 포스트에서 actionable한 패턴을 감지하여 `.claude/skills/`, `.claude/agents/`, `CLAUDE.md` rules를 자동 생성·수정
- **skill/agent 진화 (refine)**: 기존 파일을 더 정교하게 발전시키는 `refine` 액션 지원 — 이전 버전은 `.prev.md`로 자동 보존
- **유용성 판단**: AI가 "이 포스트가 실제로 워크플로우를 개선하는가?" 평가 후 적용 여부 결정
- **중복 검사**: 기존 agents/skills/rules와 의미적 대조 — 이미 존재하면 skip 또는 보강
- **AI 분류**: Claude Code / Codex / Gemini CLI로 주제 분류, 요약, 태그 자동 생성
- **rich Diff 뷰**: `--review` 시 기존 파일 vs 변경 후를 Side-by-Side로 비교
- **데스크탑 알림**: 파이프라인 완료 또는 오류 발생 시 macOS 시스템 알림
- **Obsidian 아카이빙**: 수집 원문과 분석 결과를 Obsidian vault에 날짜별·태그별로 보존
- **보안 우선**: 모든 credentials는 OS Keychain에 저장, Git에 민감정보 없음
- **Interactive Edit**: `--review` 모드에서 `[e]`로 pending 파일을 에디터($EDITOR)로 즉시 편집 — 저장 후 자동 재파싱 + diff 재표시
- **의존성 진단**: `--check`로 config·AI CLI·인증·버전·keyring·Playwright·Obsidian vault 7개 항목을 Rich 테이블로 진단
- **Selector Map 외부화**: CSS 셀렉터를 `src/collector/selectors.yaml`로 분리 — Threads UI 변경 시 YAML만 수정
- **병렬 상세 수집**: Playwright async + `asyncio.Semaphore(3)`으로 self-reply 병렬 수집 (60~70% 속도 개선)
- **시맨틱 검색**: `--search "검색어"`로 data/raw/, data/analysis/ 전체를 태그/요약/본문 점수 기반으로 검색. 결과 후 대화형 프롬프트로 파일 열기·경로 복사 가능
- **다중 프로젝트 라우팅**: `config.yaml`의 `target_projects` 리스트로 여러 프로젝트에 강화를 자동 분배 — 미설정 시 단일 프로젝트로 동작

---

## 🔄 핵심 흐름: 4-Phase md 파이프라인

모든 중간 결과를 md 파일로 저장하고, AI CLI는 **총 2회만** 호출합니다.

```
Phase 1: 수집 (Python)        → data/raw/{ts}.md
         Playwright로 저장 포스트 + 이어쓰기(self-reply) 수집 → md 파일로 저장
              ↓
Phase 2: 분석 (AI 1회 호출)    → data/analysis/{ts}.md
         전체 포스트 + 기존 설정 요약 → 분류·유용성·강화 제안 한번에
              ↓
Phase 3: 강화 생성 (AI 1회 호출) → data/pending/*.md
         분석 결과 + 기존 파일 → 중복 검사 + skill/agent/rule 초안 생성
              ↓
Phase 4: 적용 (Python)        → .claude/skills/, agents/, CLAUDE.md
         승인 후 적용 (auto_apply=false) 또는 즉시 적용 (auto_apply=true)
              ↓
         Obsidian 아카이빙 (선택)
```

각 Phase는 `--phase N`으로 독립 재실행 가능합니다.

**AI 강화 대상:**
| 대상 | 경로 | 설명 |
|------|------|------|
| Skills | `{target}/.claude/skills/*.md` | 반복 가능한 작업 패턴 자동화 |
| Agents | `{target}/.claude/agents/*.md` | 특화된 서브에이전트 정의 |
| Rules | `{target}/CLAUDE.md` | 코딩 규칙·컨벤션 추가/보강 |

---

## 📋 사전 요구사항

| 항목 | 버전 | 확인 방법 |
|------|------|----------|
| Python | 3.10+ | `python3 --version` |
| Claude Code CLI | 최신 | `claude --version` |
| Git | 2.0+ | `git --version` |
| Obsidian | 설치됨 (선택) | 아카이빙 미사용 시 불필요 |

> AI CLI는 Claude Code 외에 **Codex CLI** 또는 **Gemini CLI**도 선택 가능합니다.
> 각 CLI는 별도 구독/설치 필요. API 키 불필요 (구독 모델 사용).

---

## 🚀 설치 및 초기 설정

### 1단계: 저장소 클론

```bash
git clone https://github.com/AoiNeko00/threadloom.git
cd threadloom
```

### 2단계: 자동 설치 실행

```bash
chmod +x setup.sh
./setup.sh
```

`setup.sh`가 하는 일:
1. Python 가상환경 생성 (`.venv/`)
2. 의존성 설치 (`pip install -r requirements.txt`)
3. Playwright 브라우저 설치 (`playwright install chromium`)
4. `config.yaml` 생성 (없는 경우 `config.example.yaml`에서 복사)
5. `.env` 생성 (없는 경우 `.env.example`에서 복사)
6. `logs/`, `data/` 디렉토리 생성 (`data/raw/`, `data/analysis/`, `data/pending/`, `data/backups/` 포함)
7. `.gitignore` 검증 (민감 파일 추적 여부 확인)

### 3단계: config.yaml 설정

```yaml
# config.yaml (개인 설정 - Git에 올라가지 않음)

# AI 강화 대상 프로젝트 (필수)
target_project:
  path: "/Users/YOUR_USERNAME/your-project"  # .claude/ 가 있는 프로젝트 루트
  enhance:
    skills: true       # .claude/skills/ 자동 생성
    agents: true       # .claude/agents/ 자동 생성
    rules: true        # CLAUDE.md 규칙 추가
  auto_apply: false    # true: 즉시 적용, false: 승인 후 적용 (권장)

# 다중 프로젝트 라우팅 (선택) — AI가 항목별로 적합한 프로젝트에 자동 분배
# target_projects:
#   - name: "flutter-app"
#     path: "/Users/YOUR_USERNAME/projects/flutter-app"
#     tags: ["Flutter", "모바일"]
#   - name: "api-server"
#     path: "/Users/YOUR_USERNAME/projects/api-server"
#     tags: ["Rust", "API"]

# Obsidian 아카이빙 (선택)
obsidian:
  enabled: true
  vault_path: "/Users/YOUR_USERNAME/Documents/Obsidian"
  folders:
    daily: "Threads/daily"
    by_tag: "Threads/by-tag"
    archive: "Threads/archive"
    reports: "Reports/threadloom"

ai:
  provider: "claude_code"   # claude_code | codex | gemini
  language: "ko"            # 요약/태그 생성 언어

# AI provider별 사전 준비:
#   claude_code → claude CLI 설치 + 구독 로그인
#   codex       → npm i -g @openai/codex + ChatGPT 구독 로그인
#   gemini      → gemini CLI 설치 + Google 구독 로그인

classification:
  min_relevance_score: 0.7  # 유용성 점수 임계값 (0.0~1.0)
  max_posts_per_batch: 50   # 배치당 최대 포스트 수 (초과 시 자동 분할)
  max_chars_per_batch: 80000 # 배치당 최대 글자 수 (이중 안전장치)
  tags:
    - AI/ML
    - 개발도구
    - 프로덕트
    - 비즈니스
    - 디자인
    - 생산성
    - 기타
```

### 4단계: 최초 Threads 로그인 (1회만)

```bash
./run.sh --setup-auth
```

브라우저가 열리면 수동으로 Threads에 로그인합니다.
로그인 완료 후 세션이 로컬 OS Keychain에 암호화 저장됩니다.
이후 실행부터는 자동 로그인됩니다.

### 5단계: 첫 실행 테스트

```bash
./run.sh --dry-run
```

`--dry-run`: 실제 파일을 쓰지 않고 콘솔에만 출력합니다.

### 6단계: 실행

```bash
# 기본 실행 — 수동으로 원할 때 실행
./run.sh
```

---

## 📁 생성되는 파일 구조

### AI 강화 파일 (핵심)

```
{target_project}/
├── .claude/
│   ├── skills/
│   │   └── {skill_name}.md       ← 자동 생성된 skill 정의
│   ├── agents/
│   │   └── {agent_name}.md       ← 자동 생성된 agent 정의
│   └── ...
└── CLAUDE.md                      ← 규칙 추가 (## threadloom-rules 섹션)
```

### Obsidian 아카이브 (선택)

```
Obsidian/
├── Threads/
│   ├── daily/
│   │   └── 2026-03-12.md     ← 오늘 수집된 포스트 목록
│   ├── by-tag/
│   │   └── AI-ML.md          ← 태그별 포스트 목록 (append)
│   └── archive/
│       └── {post_id}.md      ← 포스트 원문 보존
└── Reports/
    └── threadloom/
        └── 2026-03-12-report.md
```

---

## 🔒 보안 정책

### Git에 절대 올라가지 않는 것들
```
.env                  # 환경변수
config.yaml           # 개인 설정 (경로, 분류 규칙)
auth/                 # Playwright 세션 파일
data/state.json       # last_sync 타임스탬프
logs/                 # 실행 로그
```

### Credentials 저장 방식
- Threads 세션: **OS Keychain** (Mac: macOS Keychain, Linux: GNOME Keyring)
- 평문 `.env`에 패스워드 저장 안 함
- Playwright 세션 쿠키: 로컬 `auth/` 폴더 (암호화, gitignore)

### 오픈소스 사용 시 주의
- `config.yaml`과 `auth/` 폴더는 절대 공유하지 마세요
- `data/state.json`에 사용자 ID가 포함될 수 있습니다
- PR/Issue에 개인정보 포함 주의

---

## 🛠️ 실행 옵션

```bash
# 기본 실행 — Phase 1~4 전체 실행
./run.sh

# dry-run — Phase 1~3 실행, Phase 4(적용) 건너뛰기
./run.sh --dry-run

# 전체 재수집 (처음부터)
./run.sh --full-sync

# 특정 날짜 이후만
./run.sh --since 2026-03-01

# 특정 Phase만 재실행 (이전 Phase 결과 파일 필요)
./run.sh --phase 2    # 분석만 다시
./run.sh --phase 3    # 강화 생성만 다시

# 강화 결과 검토 및 승인 (auto_apply: false일 때)
# rich 기반 Side-by-Side Diff 뷰로 기존 파일과 비교하며 검토
# [y] 승인  [n] 거부  [s] 건너뛰기  [d] 전체 내용 보기  [e] 에디터 편집  [q] 종료
./run.sh --review

# 최근 auto_apply 적용 되돌리기
./run.sh --rollback

# 의존성 상태 진단 (config, AI CLI, 인증, 버전, keyring, Playwright, Obsidian vault)
./run.sh --check

# 수집/분석 데이터 검색 (태그/요약/본문 점수 기반)
# 결과 표시 후 대화형 프롬프트: 번호→에디터 열기, c번호→경로 복사, q→종료
./run.sh --search "검색어"

# 오래된 pending 파일 정리
./run.sh --clean-pending

# 인증 관리
./run.sh --setup-auth
./run.sh --clear-auth

# 상태 확인
./run.sh --status

# PYTHONPATH를 직접 지정하는 방식도 동일하게 동작
PYTHONPATH=. .venv/bin/python3 src/main.py --review
```

---

## 📦 의존성

```text
playwright          # 브라우저 자동화
playwright-stealth  # 봇 탐지 회피
keyring             # OS Keychain 연동
pyyaml              # config.yaml 파싱
python-dateutil     # 날짜 처리
rich                # 콘솔 출력 (진행상황)
```

AI CLI는 시스템에 별도 설치된 것을 subprocess로 호출합니다.  
Python 패키지로 설치하지 않습니다.

---

## ⚠️ 안전장치

- **`auto_apply: false` (기본값)**: AI가 생성한 강화 내용을 `data/pending/`에 저장하고, `--review`로 사람이 검토 후 승인해야 실제 적용
- **`auto_apply: true`**: 즉시 적용하되, 적용 전 자동 백업 (`data/backups/`)
- **CLAUDE.md 수정**: `## threadloom-rules` 섹션만 관리 — 기존 규칙은 절대 수정하지 않음
- **강화 이력**: 모든 생성·수정 내역을 `data/enhance_log.json`에 기록

---

## 🤝 기여 방법

1. Fork → Branch → PR
2. 민감정보 포함 여부 반드시 확인 후 PR
3. 새 AI CLI 어댑터 추가 시 `src/ai_adapter/` 참고
4. 테스트는 반드시 mock 데이터로 (`tests/fixtures/`)

---

## 📄 라이선스

MIT License - 자유롭게 사용, 수정, 배포 가능
