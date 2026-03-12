"""국제화(i18n) 유틸리티.

시스템 로캘(locale)에 따라 한국어 또는 영어 메시지를 반환한다.
"""

import os
import subprocess
import sys


def _detect_locale() -> str:
    """시스템 언어를 감지(detect)한다.

    우선순위:
    1. THREADLOOM_LANG 환경변수 (명시적 오버라이드)
    2. macOS: defaults read -g AppleLocale (시스템 환경설정)
    3. LANG / LC_ALL 환경변수
    4. locale.getlocale() (Python 표준)

    macOS에서는 LANG이 셸 프로파일(profile)에 의해 시스템 언어와
    다르게 설정될 수 있으므로, AppleLocale을 LANG보다 우선한다.
    """
    # 명시적 오버라이드(override) — 테스트나 강제 전환용
    override = os.environ.get("THREADLOOM_LANG", "")
    if override:
        return override

    # macOS: AppleLocale이 실제 시스템 언어를 반영
    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleLocale"],
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass

    # Linux / 기타: 환경변수(environment variable) 사용
    env_lang = os.environ.get("LANG", "") or os.environ.get("LC_ALL", "")
    if env_lang:
        return env_lang

    # 폴백: Python locale
    import locale
    try:
        return locale.getlocale()[0] or ""
    except ValueError:
        return ""


_detected = _detect_locale()
_IS_KOREAN = _detected.lower().startswith("ko")


def is_korean() -> bool:
    """현재 시스템이 한국어 로캘(locale)인지 반환한다."""
    return _IS_KOREAN


def t(key: str, **kwargs) -> str:
    """메시지 키(key)에 해당하는 로캘 문자열을 반환한다.

    kwargs가 있으면 str.format()으로 치환한다.
    """
    lang = "ko" if _IS_KOREAN else "en"
    catalog = _MESSAGES.get(key)
    if catalog is None:
        return key
    template = catalog.get(lang, catalog.get("en", key))
    if kwargs:
        return template.format(**kwargs)
    return template


# ── 메시지 카탈로그(message catalog) ──
# 키: 모듈별 네임스페이스 (module.message_id)
_MESSAGES: dict[str, dict[str, str]] = {
    # ── main ──
    "main.interrupted": {
        "ko": "사용자에 의해 중단됨",
        "en": "Interrupted by user",
    },
    "main.pipeline_start": {
        "ko": "threadloom 파이프라인 시작",
        "en": "threadloom pipeline started",
    },

    # ── cli/columns ──
    "cli.col_name": {
        "ko": "이름",
        "en": "Name",
    },
    "cli.col_reject_reason": {
        "ko": "거부 사유",
        "en": "Reject reason",
    },
    "cli.auto_review_rejected": {
        "ko": "자동 심사에서 {n}건이 탈락했습니다. --show-rejected로 확인 가능",
        "en": "{n} items rejected by auto-review. Use --show-rejected to view",
    },
    "cli.confirm_apply": {
        "ko": "승인된 항목을 적용하시겠습니까? [y/n] ",
        "en": "Apply approved items? [y/n] ",
    },

    # ── status_display ──
    "status.none": {
        "ko": "(없음)",
        "en": "(none)",
    },
    "status.read_error": {
        "ko": "(읽기 실패)",
        "en": "(read error)",
    },
    "status.no_frontmatter": {
        "ko": "(frontmatter 없음)",
        "en": "(no frontmatter)",
    },
    "status.no_reason": {
        "ko": "(사유 없음)",
        "en": "(no reason)",
    },
    "status.enhancement_map_title": {
        "ko": "강화 분포 맵",
        "en": "Enhancement Map",
    },
    "status.col_domain": {
        "ko": "분야",
        "en": "Domain",
    },
    "status.col_total": {
        "ko": "합계",
        "en": "Total",
    },

    # ── health_check columns ──
    "health.col_item": {
        "ko": "항목",
        "en": "Item",
    },
    "health.col_status": {
        "ko": "상태",
        "en": "Status",
    },
    "health.col_message": {
        "ko": "메시지",
        "en": "Message",
    },

    # ── cli/commands ──
    "cmd.auth_setup_ok": {
        "ko": "인증 설정 완료",
        "en": "Authentication setup complete",
    },
    "cmd.auth_setup_fail": {
        "ko": "인증 설정 실패: {err}",
        "en": "Authentication setup failed: {err}",
    },
    "cmd.auth_cleared": {
        "ko": "인증 정보가 삭제되었습니다",
        "en": "Authentication credentials cleared",
    },
    "cmd.status_title": {
        "ko": "threadloom 상태",
        "en": "threadloom status",
    },
    "cmd.last_sync": {
        "ko": "마지막 수집: {ts}",
        "en": "Last sync: {ts}",
    },
    "cmd.total_collected": {
        "ko": "누적 수집: {n}건",
        "en": "Total collected: {n}",
    },
    "cmd.pending_count": {
        "ko": "대기 중 강화: {n}건",
        "en": "Pending enhancements: {n}",
    },
    "cmd.applied_count": {
        "ko": "적용된 강화 총: {n}건",
        "en": "Total applied: {n}",
    },
    "cmd.no_rejected": {
        "ko": "거부된 항목이 없습니다",
        "en": "No rejected items",
    },
    "cmd.rejected_title": {
        "ko": "자동 심사 탈락 항목",
        "en": "Auto-review rejected items",
    },
    "cmd.applied_ok": {
        "ko": "{n}건 적용 완료",
        "en": "{n} items applied",
    },
    "cmd.apply_cancelled": {
        "ko": "적용 취소 — 승인 항목은 pending에 유지됩니다",
        "en": "Apply cancelled — approved items remain in pending",
    },
    "cmd.no_changes": {
        "ko": "변경 사항 없음",
        "en": "No changes",
    },
    "cmd.rollback_ok": {
        "ko": "롤백 완료",
        "en": "Rollback complete",
    },
    "cmd.clean_ok": {
        "ko": "정리 완료",
        "en": "Clean complete",
    },

    # ── writer/review_display ──
    "review.no_existing": {
        "ko": "기존 파일 없음 — 전체가 신규 내용",
        "en": "No existing file — all new content",
    },
    "review.truncated": {
        "ko": "... ({total}줄 중 {shown}줄만 표시)",
        "en": "... (showing {shown} of {total} lines)",
    },
    "review.preview_title": {
        "ko": "새 파일 미리보기",
        "en": "New file preview",
    },
    "review.full_content_title": {
        "ko": "전체 내용",
        "en": "Full content",
    },
    "review.prompt_approve": {
        "ko": "승인",
        "en": "approve",
    },
    "review.prompt_reject": {
        "ko": "거부",
        "en": "reject",
    },
    "review.prompt_skip": {
        "ko": "건너뛰기",
        "en": "skip",
    },
    "review.prompt_edit": {
        "ko": "편집",
        "en": "edit",
    },
    "review.prompt_detail": {
        "ko": "상세",
        "en": "detail",
    },
    "review.prompt_quit": {
        "ko": "종료",
        "en": "quit",
    },
    "review.summary": {
        "ko": "검토 완료: 승인 {approved}건, 거부 {rejected}건, 건너뜀 {skipped}건",
        "en": "Review done: {approved} approved, {rejected} rejected, {skipped} skipped",
    },
    "review.existing_col": {
        "ko": "기존",
        "en": "Existing",
    },
    "review.changed_col": {
        "ko": "변경 후",
        "en": "Changed",
    },
    "review.diff_title": {
        "ko": "기존 vs 변경 후",
        "en": "Existing vs Changed",
    },
    "review.invalid_choice": {
        "ko": "y, n, s, e, d, q 중 하나를 입력하세요.",
        "en": "Enter one of y, n, s, e, d, q.",
    },

    # ── utils/health_check ──
    "health.title": {
        "ko": "threadloom 의존성 헬스 체크",
        "en": "threadloom dependency health check",
    },
    "health.config_ok": {
        "ko": "유효한 설정 파일",
        "en": "Valid config file",
    },
    "health.config_fail": {
        "ko": "설정 파일 로드 실패",
        "en": "Config file load failed",
    },
    "health.cli_ok": {
        "ko": "{cmd} 설치 확인",
        "en": "{cmd} installed",
    },
    "health.cli_fail": {
        "ko": "{cmd}를 찾을 수 없습니다",
        "en": "{cmd} not found",
    },
    "health.auth_ok": {
        "ko": "인증 유효",
        "en": "Authentication valid",
    },
    "health.auth_fail": {
        "ko": "인증 실패 또는 CLI 응답 없음",
        "en": "Auth failed or no CLI response",
    },
    "health.version_ok": {
        "ko": "호환 버전",
        "en": "Compatible version",
    },
    "health.version_warn": {
        "ko": "최소 버전 미달 — 업데이트 권장",
        "en": "Below min version — update recommended",
    },
    "health.keyring_ok": {
        "ko": "접근 가능",
        "en": "Accessible",
    },
    "health.keyring_fail": {
        "ko": "접근 불가: {err}",
        "en": "Not accessible: {err}",
    },
    "health.pw_ok": {
        "ko": "Chromium 바이너리 존재",
        "en": "Chromium binary found",
    },
    "health.pw_warn": {
        "ko": "Chromium 바이너리 경로 확인 불가",
        "en": "Cannot locate Chromium binary",
    },
    "health.pw_fail": {
        "ko": "Playwright 오류: {err}",
        "en": "Playwright error: {err}",
    },
    "health.obsidian_disabled": {
        "ko": "비활성화됨 (체크 건너뜀)",
        "en": "Disabled (check skipped)",
    },
    "health.obsidian_ok": {
        "ko": "마운트 확인: {vault}",
        "en": "Mount confirmed: {vault}",
    },
    "health.obsidian_fail": {
        "ko": "경로 없음: {vault}",
        "en": "Path not found: {vault}",
    },
    "health.result_fail": {
        "ko": "FAIL {n}건",
        "en": "FAIL {n} items",
    },
    "health.result_warn": {
        "ko": "WARN {n}건",
        "en": "WARN {n} items",
    },
    "health.result_ok": {
        "ko": "모든 항목 정상",
        "en": "All checks passed",
    },

    # ── utils/search ──
    "search.title": {
        "ko": "검색 결과: '{query}' ({n}건)",
        "en": "Search results: '{query}' ({n} hits)",
    },
    "search.no_results": {
        "ko": "'{query}'에 대한 결과가 없습니다",
        "en": "No results for '{query}'",
    },
    "search.invalid_range": {
        "ko": "1~{max} 범위의 번호를 입력하세요",
        "en": "Enter a number between 1 and {max}",
    },
    "search.path_display": {
        "ko": "경로: {path}",
        "en": "Path: {path}",
    },
    "search.copied": {
        "ko": "복사됨: {path}",
        "en": "Copied: {path}",
    },
    "search.prompt_help": {
        "ko": "번호 입력: 에디터로 열기  c번호: 경로 복사  q 또는 Enter: 종료",
        "en": "Number: open in editor  cN: copy path  q or Enter: quit",
    },
    "search.col_rank": {"ko": "#", "en": "#"},
    "search.col_source": {"ko": "출처", "en": "Source"},
    "search.col_file": {"ko": "파일", "en": "File"},
    "search.col_score": {"ko": "점수", "en": "Score"},
    "search.col_tags": {"ko": "태그", "en": "Tags"},
    "search.col_summary": {"ko": "요약", "en": "Summary"},

    # ── pipeline/pipeline_output ──
    "output.preview_title": {
        "ko": "Phase 3 강화 미리보기",
        "en": "Phase 3 enhancement preview",
    },
    "output.more_lines": {
        "ko": "... ({n}줄 더)",
        "en": "... ({n} more lines)",
    },
    "output.obsidian_preview": {
        "ko": "Obsidian 미리보기",
        "en": "Obsidian preview",
    },
    "output.pipeline_done": {
        "ko": "파이프라인 완료{mode}",
        "en": "Pipeline complete{mode}",
    },
    "output.batch_count": {
        "ko": "배치: {n}개",
        "en": "Batches: {n}",
    },
    "output.analysis_count": {
        "ko": "분석: {n}건",
        "en": "Analysis: {n}",
    },
    "output.pending_count": {
        "ko": "강화 초안: {n}건",
        "en": "Enhancement drafts: {n}",
    },
    "output.report_saved": {
        "ko": "리포트 저장: {name}",
        "en": "Report saved: {name}",
    },

    # ── pipeline/runner ──
    "runner.no_auth": {
        "ko": "인증 세션이 없습니다.",
        "en": "No auth session found.",
    },
    "runner.auth_hint": {
        "ko": "먼저 실행: python3 src/main.py --setup-auth",
        "en": "Run first: python3 src/main.py --setup-auth",
    },
    "runner.phase3_preview": {
        "ko": "Phase 3 미리보기",
        "en": "Phase 3 preview",
    },
    "runner.auto_review_done": {
        "ko": "자동 심사 완료: 통과 {approved}건, 거부 {rejected}건",
        "en": "Auto review done: {approved} passed, {rejected} rejected",
    },
    "runner.rejected_reason": {
        "ko": "거부: {reason}",
        "en": "Rejected: {reason}",
    },
    "runner.dryrun_skip": {
        "ko": "dry-run: Phase 4(적용) 건너뜀",
        "en": "dry-run: skipping Phase 4 (apply)",
    },
    "runner.no_raw": {
        "ko": "data/raw/ 에 파일이 없습니다",
        "en": "No files in data/raw/",
    },
    "runner.rerun_phase2": {
        "ko": "Phase 2 재실행: {name}",
        "en": "Re-running Phase 2: {name}",
    },
    "runner.no_analysis": {
        "ko": "data/analysis/ 에 파일이 없습니다",
        "en": "No files in data/analysis/",
    },
    "runner.rerun_phase3": {
        "ko": "Phase 3 재실행: {name}",
        "en": "Re-running Phase 3: {name}",
    },
    "runner.date_format_error": {
        "ko": "날짜 형식 오류: {val} (YYYY-MM-DD)",
        "en": "Date format error: {val} (YYYY-MM-DD)",
    },
    "runner.no_new_posts": {
        "ko": "신규 포스트가 없습니다",
        "en": "No new posts found",
    },
    "runner.batch_progress": {
        "ko": "배치 {i}/{total}",
        "en": "Batch {i}/{total}",
    },
    "runner.ai_unavailable": {
        "ko": "AI 프로바이더 '{provider}'를 사용할 수 없습니다",
        "en": "AI provider '{provider}' is not available",
    },
    "runner.phase1_done": {
        "ko": "Phase 1 완료: {name}",
        "en": "Phase 1 done: {name}",
    },
    "runner.phase2_done": {
        "ko": "Phase 2 완료: {name}",
        "en": "Phase 2 done: {name}",
    },
    "runner.phase3_done": {
        "ko": "Phase 3 완료: {n}건 생성",
        "en": "Phase 3 done: {n} items generated",
    },
    "runner.phase4_done": {
        "ko": "Phase 4 완료: {n}건 처리",
        "en": "Phase 4 done: {n} items processed",
    },
    "runner.rate_limit": {
        "ko": "Rate limit 방어: {sec}초 대기",
        "en": "Rate limit defense: waiting {sec}s",
    },

    # ── collector ──
    "collector.nav_done": {
        "ko": "저장 포스트 페이지 진입 완료",
        "en": "Navigated to saved posts page",
    },
    "collector.checkpoint_save": {
        "ko": "checkpoint 저장: {n}건",
        "en": "Checkpoint saved: {n} items",
    },
    "collector.checkpoint_error": {
        "ko": "에러 발생 — checkpoint 저장: {n}건",
        "en": "Error — checkpoint saved: {n} items",
    },
    "collector.seen_filtered": {
        "ko": "이전 수집 포스트 {n}건 필터링됨 (seen_ids 기반)",
        "en": "Filtered {n} previously seen posts (by seen_ids)",
    },
    "collector.collect_done": {
        "ko": "수집 완료: {n}건 (중복 제거 후)",
        "en": "Collection done: {n} items (after dedup)",
    },
    "collector.async_done": {
        "ko": "병렬 self-reply 수집 완료",
        "en": "Async self-reply collection done",
    },
    "collector.async_start": {
        "ko": "병렬 self-reply 수집 시작: {n}건 (동시 {concurrent}개)",
        "en": "Async self-reply starting: {n} items ({concurrent} concurrent)",
    },
    "collector.async_fail": {
        "ko": "병렬 수집 실패, 순차 수집으로 폴백: {err}",
        "en": "Async collection failed, falling back to sequential: {err}",
    },
    "collector.self_reply_candidates": {
        "ko": "self-reply 후보: {candidates}건 / 전체 {total}건",
        "en": "Self-reply candidates: {candidates} / total {total}",
    },
    "collector.raw_saved": {
        "ko": "raw markdown 저장: data/raw/{ts}.md",
        "en": "Raw markdown saved: data/raw/{ts}.md",
    },
    "collector.checkpoint_cleaned": {
        "ko": "checkpoint 정리 완료",
        "en": "Checkpoint cleanup done",
    },

    # ── auth ──
    "auth.open_browser": {
        "ko": "브라우저를 열어 Threads 로그인을 시작합니다",
        "en": "Opening browser for Threads login",
    },
    "auth.login_prompt": {
        "ko": "브라우저에서 Threads에 로그인하세요",
        "en": "Please log in to Threads in the browser",
    },
    "auth.press_enter": {
        "ko": "로그인 완료 후 이 터미널에서 Enter를 누르세요",
        "en": "Press Enter in this terminal after login",
    },
    "auth.saved": {
        "ko": "인증 정보가 저장되었습니다 (keyring: {key})",
        "en": "Auth credentials saved (keyring: {key})",
    },
    "auth.no_session": {
        "ko": "저장된 세션 파일이 없습니다",
        "en": "No saved session file",
    },
    "auth.cookies_loaded": {
        "ko": "세션 쿠키(cookies) 로드 완료",
        "en": "Session cookies loaded",
    },
    "auth.session_deleted": {
        "ko": "세션 파일 삭제 완료: {name}",
        "en": "Session file deleted: {name}",
    },
    "auth.keyring_deleted": {
        "ko": "keyring 항목 삭제 완료: {key}",
        "en": "Keyring entry deleted: {key}",
    },
    "auth.keyring_empty": {
        "ko": "keyring에 삭제할 항목이 없습니다",
        "en": "No keyring entry to delete",
    },
    "auth.cookies_saved": {
        "ko": "쿠키 {n}개 저장 완료",
        "en": "{n} cookies saved",
    },
    "auth.session_read_fail": {
        "ko": "세션 파일 읽기 실패: {err}",
        "en": "Session file read failed: {err}",
    },

    # ── enhancer ──
    "enhancer.no_items": {
        "ko": "적용할 강화 항목이 없습니다",
        "en": "No enhancement items to apply",
    },
    "enhancer.no_review": {
        "ko": "검토할 항목이 없습니다",
        "en": "No items to review",
    },
    "enhancer.applied": {
        "ko": "[적용] {action_type}: {name}",
        "en": "[Applied] {action_type}: {name}",
    },
    "enhancer.rejected": {
        "ko": "[거절] {action_type}: {name}",
        "en": "[Rejected] {action_type}: {name}",
    },
    "enhancer.backup_done": {
        "ko": "백업 완료: {dir}",
        "en": "Backup done: {dir}",
    },
    "enhancer.auto_apply_done": {
        "ko": "auto_apply: {n}건 적용 완료",
        "en": "auto_apply: {n} items applied",
    },
    "enhancer.no_proposals": {
        "ko": "강화 제안이 없습니다. Phase 3 건너뜀",
        "en": "No enhancement proposals. Skipping Phase 3",
    },
    "enhancer.existing_collected": {
        "ko": "기존 파일 {n}개 수집 완료",
        "en": "{n} existing files collected",
    },
    "enhancer.ai_response": {
        "ko": "AI 응답 수신: {n}자",
        "en": "AI response received: {n} chars",
    },
    "enhancer.parse_fail_fallback": {
        "ko": "구분자 파싱 실패. fallback 저장 실행",
        "en": "Delimiter parsing failed. Running fallback save",
    },
    "enhancer.self_correction": {
        "ko": "파싱 실패. 자기 수정(self-correction) 시도 중...",
        "en": "Parsing failed. Attempting self-correction...",
    },
    "enhancer.self_correction_fail": {
        "ko": "자기 수정 AI 호출 실패",
        "en": "Self-correction AI call failed",
    },
    "enhancer.self_correction_ok": {
        "ko": "자기 수정 성공: {n}건 파싱 완료",
        "en": "Self-correction success: {n} items parsed",
    },
    "enhancer.self_correction_final_fail": {
        "ko": "자기 수정도 실패. fallback으로 전환",
        "en": "Self-correction also failed. Switching to fallback",
    },
    "enhancer.pending_saved": {
        "ko": "pending 파일 저장: {name}",
        "en": "Pending file saved: {name}",
    },
    "enhancer.fallback_saved": {
        "ko": "fallback 파일 저장: {name}",
        "en": "Fallback file saved: {name}",
    },
    "enhancer.skill_evolve": {
        "ko": "skill 진화: {name}",
        "en": "Skill evolution: {name}",
    },
    "enhancer.file_preserved": {
        "ko": "기존 파일 보존: {name}",
        "en": "Existing file preserved: {name}",
    },
    "enhancer.unknown_action": {
        "ko": "알 수 없는 action_type: {action_type}",
        "en": "Unknown action_type: {action_type}",
    },
    "enhancer.analysis_read_fail": {
        "ko": "분석 파일 읽기 실패: {path}",
        "en": "Analysis file read failed: {path}",
    },
    "enhancer.codeblock_parse_ok": {
        "ko": "코드블록 제거 후 구분자 파싱 성공",
        "en": "Delimiter parsing succeeded after code block removal",
    },
    "enhancer.frontmatter_parse_ok": {
        "ko": "frontmatter 기반 대체 파싱 성공: {n}건",
        "en": "Frontmatter-based fallback parsing success: {n} items",
    },
    "enhancer.reject_log": {
        "ko": "[거부] {name} — {reason}",
        "en": "[Rejected] {name} — {reason}",
    },
    "enhancer.reject_detail": {
        "ko": "  거부: {name} — {reason}",
        "en": "  Rejected: {name} — {reason}",
    },
    "enhancer.reject_read_fail": {
        "ko": "거부 파일 읽기 실패: {name}",
        "en": "Rejected file read failed: {name}",
    },
    "enhancer.no_backup": {
        "ko": "복원할 백업이 없습니다",
        "en": "No backup to restore",
    },
    "enhancer.backup_restored": {
        "ko": "백업 복원 완료: {name}",
        "en": "Backup restored: {name}",
    },
    "enhancer.pending_delete_fail": {
        "ko": "pending 파일 삭제 실패: {name}",
        "en": "Pending file delete failed: {name}",
    },
    "enhancer.old_pending_cleaned": {
        "ko": "{days}일 이상 된 pending 파일 {n}건 삭제",
        "en": "{n} pending files older than {days} days deleted",
    },
    "enhancer.pending_read_fail": {
        "ko": "pending 파일 읽기 실패: {name}",
        "en": "Pending file read failed: {name}",
    },
    "enhancer.pending_waiting": {
        "ko": "{n}건 대기 중. --review로 확인하세요",
        "en": "{n} items pending. Run --review to check",
    },
    "enhancer.apply_done": {
        "ko": "총 {n}건 적용 완료. 백업: {backup}",
        "en": "{n} items applied. Backup: {backup}",
    },
    "enhancer.partial_fail": {
        "ko": "{n}건 적용 실패 — 해당 항목은 pending에 유지됩니다",
        "en": "{n} items failed to apply — they remain in pending",
    },
    "enhancer.apply_error": {
        "ko": "[실패] {action_type}: {name}",
        "en": "[Failed] {action_type}: {name}",
    },
    "enhancer.review_summary": {
        "ko": "심사 완료: 총 {total}건 → 통과 {approved}건, 거부 {rejected}건",
        "en": "Review done: {total} total → {approved} passed, {rejected} rejected",
    },
    "enhancer.reject_detail_log": {
        "ko": "  거부: {name} — {reason}",
        "en": "  Rejected: {name} — {reason}",
    },
    "enhancer.no_proposals_short": {
        "ko": "강화 제안이 없습니다.",
        "en": "No enhancement proposals.",
    },
    "enhancer.ai_no_response": {
        "ko": "AI 응답을 받지 못했습니다.",
        "en": "No AI response received.",
    },
    "enhancer.parse_fail_raw": {
        "ko": "파싱 실패. 원본 응답 길이: {n}자",
        "en": "Parsing failed. Raw response length: {n} chars",
    },
    "enhancer.dryrun_summary_title": {
        "ko": "강화 초안 {n}건 생성 예정:\n",
        "en": "{n} enhancement drafts to be created:\n",
    },
    "enhancer.dryrun_target_unset": {
        "ko": "(미지정)",
        "en": "(unset)",
    },
    "enhancer.dryrun_item": {
        "ko": "  {i}. [{action}] {name}\n     대상: {target}\n     중복검사: {dup}",
        "en": "  {i}. [{action}] {name}\n     Target: {target}\n     Dedup: {dup}",
    },
    "enhancer.ai_call_fail": {
        "ko": "AI CLI 호출 실패",
        "en": "AI CLI call failed",
    },

    # ── processor ──
    "processor.context_done": {
        "ko": "컨텍스트 요약 생성 완료",
        "en": "Context summary generated",
    },
    "processor.analysis_saved": {
        "ko": "분석 결과 저장: {path}",
        "en": "Analysis saved: {path}",
    },
    "processor.analysis_verify_fail": {
        "ko": "분석 결과 검증 실패, 폴백 분석 수행",
        "en": "Analysis verification failed, running fallback",
    },
    "processor.file_read_fail": {
        "ko": "파일 읽기 실패: {path}",
        "en": "File read failed: {path}",
    },
    "processor.claude_md_fail": {
        "ko": "CLAUDE.md 읽기 실패",
        "en": "CLAUDE.md read failed",
    },

    # ── writer ──
    "writer.no_posts": {
        "ko": "분석 결과에 포스트가 없어 Obsidian 쓰기 건너뜀",
        "en": "No posts in analysis — skipping Obsidian write",
    },
    "writer.daily_saved": {
        "ko": "daily 파일 저장: {name}",
        "en": "Daily file saved: {name}",
    },
    "writer.bytag_saved": {
        "ko": "by-tag 파일 저장: {name}",
        "en": "By-tag file saved: {name}",
    },
    "writer.archive_skip": {
        "ko": "archive 중복 건너뜀: {id}",
        "en": "Archive duplicate skipped: {id}",
    },
    "writer.archive_saved": {
        "ko": "archive 파일 저장: {id}",
        "en": "Archive file saved: {id}",
    },
    "writer.report_saved": {
        "ko": "리포트 저장: {name}",
        "en": "Report saved: {name}",
    },

    # ── utils ──
    "util.lock_exists": {
        "ko": "다른 threadloom 프로세스가 실행 중입니다 (lock 존재)",
        "en": "Another threadloom process is running (lock exists)",
    },
    "util.stale_lock": {
        "ko": "stale lock 감지 — 기존 잠금 제거",
        "en": "Stale lock detected — removing old lock",
    },
    "util.batch_split_done": {
        "ko": "배치 {n}개로 분할 완료",
        "en": "Split into {n} batches",
    },
    "util.frontmatter_fail": {
        "ko": "frontmatter YAML 파싱 실패",
        "en": "Frontmatter YAML parsing failed",
    },
    "util.notify_fail": {
        "ko": "시스템 알림 전송 실패",
        "en": "System notification failed",
    },
    "util.version_check_fail": {
        "ko": "버전 확인 실패: {cmd}",
        "en": "Version check failed: {cmd}",
    },
    "util.selectors_missing": {
        "ko": "selectors.yaml이 없습니다: {path}",
        "en": "selectors.yaml not found: {path}",
    },

    # ── link_fetcher ──
    "link.fetching_start": {
        "ko": "링크 크롤링 시작: {n}건",
        "en": "Link crawling starting: {n} items",
    },
    "link.fetched": {
        "ko": "링크 수집 완료: {success}건 성공, {fail}건 실패",
        "en": "Links fetched: {success} success, {fail} failed",
    },
    "link.fetch_error": {
        "ko": "링크 크롤링 실패 ({url}): {err}",
        "en": "Link fetch failed ({url}): {err}",
    },
    "link.disabled": {
        "ko": "링크 크롤링 비활성화",
        "en": "Link crawling disabled",
    },

    # ── main ──
    "main.pipeline_error": {
        "ko": "파이프라인 실행 중 오류 발생",
        "en": "Error during pipeline execution",
    },
    "main.pipeline_error_notify": {
        "ko": "파이프라인 실행 중 오류가 발생했습니다.",
        "en": "An error occurred during pipeline execution.",
    },

    # ── writer/obsidian_writer ──
    "writer.obsidian_done": {
        "ko": "Obsidian 쓰기 완료: daily={daily}, by_tag={by_tag}, archive={archive}",
        "en": "Obsidian write done: daily={daily}, by_tag={by_tag}, archive={archive}",
    },
    "writer.no_posts_for_report": {
        "ko": "분석 결과에 포스트가 없습니다.",
        "en": "No posts in analysis result.",
    },
    "writer.dry_run_title": {
        "ko": "[dry-run] Obsidian 쓰기 미리보기",
        "en": "[dry-run] Obsidian write preview",
    },
    "writer.post_count": {
        "ko": "포스트 수: {n}건",
        "en": "Posts: {n}",
    },
    "writer.daily_file_count": {
        "ko": "daily 파일: {n}개",
        "en": "Daily files: {n}",
    },
    "writer.bytag_file_count": {
        "ko": "by-tag 파일: {n}개 ({tags})",
        "en": "By-tag files: {n} ({tags})",
    },
    "writer.archive_file_count": {
        "ko": "archive 파일: {n}개",
        "en": "Archive files: {n}",
    },
    "writer.category_dist": {
        "ko": "카테고리 분포:",
        "en": "Category distribution:",
    },

    # ── analyzer ──
    "analyzer.ai_call_failed": {
        "ko": "AI 호출 실패, 폴백 분석 수행",
        "en": "AI call failed, running fallback analysis",
    },

    # ── batch_splitter ──
    "batch.oversized_post": {
        "ko": "단일 포스트가 max_chars({max_chars})를 초과합니다 ({actual}자). 단독 배치로 처리합니다.",
        "en": "Single post exceeds max_chars({max_chars}) at {actual} chars. Processing as standalone batch.",
    },

    # ── collector/threads_scraper ──
    "collector.session_load_failed": {
        "ko": "세션 로드 실패 — --setup-auth를 먼저 실행하세요",
        "en": "Session load failed — run --setup-auth first",
    },
    "collector.session_expired": {
        "ko": "세션이 만료되었습니다 — --setup-auth를 다시 실행하세요",
        "en": "Session expired — run --setup-auth again",
    },

    # ── config ──
    "config.no_config_file": {
        "ko": "config.yaml이 없습니다. 아래 명령어로 생성하세요:\n  cp config.example.yaml config.yaml",
        "en": "config.yaml not found. Create it with:\n  cp config.example.yaml config.yaml",
    },
    "config.no_target_path": {
        "ko": "target_project.path가 설정되지 않았습니다.",
        "en": "target_project.path is not configured.",
    },
    "config.target_path_missing": {
        "ko": "target_project.path가 존재하지 않습니다: {path}",
        "en": "target_project.path does not exist: {path}",
    },
    "config.claude_dir_created": {
        "ko": ".claude/ 디렉토리가 없어 자동 생성합니다: {path}",
        "en": ".claude/ directory not found, creating automatically: {path}",
    },
    "config.claude_subdirs_created": {
        "ko": ".claude/skills/, .claude/agents/ 생성 완료. 필요 시 기존 skill/agent 파일을 추가하세요.",
        "en": ".claude/skills/, .claude/agents/ created. Add existing skill/agent files if needed.",
    },
    "config.obsidian_no_vault": {
        "ko": "obsidian.enabled=true이지만 vault_path가 비어있습니다.",
        "en": "obsidian.enabled=true but vault_path is empty.",
    },
    "config.obsidian_vault_missing": {
        "ko": "obsidian.vault_path가 존재하지 않습니다: {vault}",
        "en": "obsidian.vault_path does not exist: {vault}",
    },

    # ── auth ──
    "auth.input_prompt": {
        "ko": "\n>>> 로그인 완료 후 Enter 입력: ",
        "en": "\n>>> Press Enter after login: ",
    },
}
