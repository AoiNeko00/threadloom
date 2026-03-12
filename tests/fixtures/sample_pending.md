---
action_type: create_skill
name: playwright_session_management
target: .claude/skills/playwright_session_management.md
source_posts: [post-001, post-002, post-003]
analyzed_from: data/analysis/20260312_070000.md
created_at: 2026-03-12T07:02:00
status: pending
duplicate_check: create_new
---

# 적용할 내용

아래 내용이 `{target_project}/.claude/skills/playwright_session_management.md`에 생성됩니다.

---

description: Playwright 세션을 storageState로 저장/복원하여 로그인을 자동화한다
source: threadloom
created: 2026-03-12

# playwright_session_management

Playwright 브라우저 세션을 파일로 관리하는 패턴.

## 사용 시점
사용자가 Playwright 기반 인증이나 세션 관리를 요청할 때 이 skill을 적용한다.

## 지시사항
1. `browser.new_context(storage_state="auth/session.json")` 으로 기존 세션 로드
2. 세션 파일이 없으면 수동 로그인 후 `context.storage_state(path="auth/session.json")` 으로 저장
3. 세션 만료 시 자동 재로그인 시도하지 않고 사용자에게 안내
4. `playwright-stealth`를 적용하여 봇 탐지 우회

## 근거
- 출처: Threads 포스트 3건에서 감지된 패턴 (post-001, post-002, post-003)
- 핵심 인사이트: storageState 활용이 쿠키 수동 관리보다 안정적
