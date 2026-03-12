"""Phase 4: 강화 초안의 승인(approval) 및 적용(apply)을 담당하는 모듈.

data/pending/*.md 파일을 읽어 대화형 검토 또는 자동 적용을 수행하고,
적용 전 기존 파일 백업 및 이력 기록을 관리한다.
"""

import os
import subprocess
from pathlib import Path

from src.config import Config
from src.enhancer.action_executor import apply_one as _exec_apply_one
from src.enhancer.backup_manager import (
    backup as _bk_backup,
    collect_backup_targets as _bk_collect,
    log_enhancement as _bk_log,
    rollback as _bk_rollback,
)
from src.enhancer.models import PendingAction
from src.enhancer.pending_manager import (
    clean_pending as _pm_clean,
    mark_approved as _pm_mark_approved,
    move_to_rejected as _pm_move_rejected,
    remove_pending as _pm_remove,
)
from src.enhancer.pending_parser import parse_pending_file as _pp_parse
from src.utils.i18n import t
from src.utils.logger import get_logger
from src.utils.paths import PENDING_DIR

_logger = get_logger("applier")

# 중앙 경로(centralized path) 모듈에서 가져옴
_PENDING_DIR = PENDING_DIR


class Applier:
    """Phase 4: pending 파일의 승인 흐름 + 실제 적용."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._target_root = Path(config.target_project_path)
        # 다중 프로젝트(multi-project) 라우팅 맵
        self._project_map: dict[str, str] = {
            p["name"]: p["path"] for p in config.target_projects
        }

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def load_pending(self) -> list[PendingAction]:
        """data/pending/*.md 를 읽어 PendingAction 리스트를 반환한다."""
        if not _PENDING_DIR.is_dir():
            return []
        actions: list[PendingAction] = []
        for md_file in sorted(_PENDING_DIR.glob("*.md")):
            action = _pp_parse(md_file)
            if action:
                actions.append(action)
        return actions

    def apply(self, actions: list[PendingAction]) -> None:
        """auto_apply 설정에 따라 즉시 적용 또는 대기."""
        if not actions:
            _logger.info(t("enhancer.no_items"))
            return

        if self._config.auto_apply:
            self._auto_apply(actions)
        else:
            _logger.info(t("enhancer.pending_waiting", n=len(actions)))

    def review(self) -> tuple[list[PendingAction], list[PendingAction]]:
        """대화형 검토: rich 기반 Diff 뷰로 항목 표시 -> y/n/s/d/q 입력.

        Returns:
            (승인 리스트, 거절 리스트)
        """
        actions = self.load_pending()
        if not actions:
            _logger.info(t("enhancer.no_review"))
            return [], []

        from src.writer.review_display import (
            display_diff,
            display_full_content,
            display_header,
            display_new_file,
            display_prompt,
        )

        approved: list[PendingAction] = []
        rejected: list[PendingAction] = []
        total = len(actions)

        for i, action in enumerate(actions, 1):
            display_header(i, total, action)
            self._show_content_preview(action, display_diff, display_new_file)
            while True:
                choice = self._prompt_rich_choice(
                    action, display_full_content, display_prompt,
                )
                if choice != "e":
                    break
                # 편집기(editor)로 pending 파일 수정 후 재파싱
                self._open_editor(action.file_path)
                updated = _pp_parse(action.file_path)
                if updated:
                    action = updated
                    actions[i - 1] = updated
                self._show_content_preview(action, display_diff, display_new_file)

            if choice == "y":
                _pm_mark_approved(action)
                approved.append(action)
            elif choice == "n":
                rejected.append(action)
            elif choice == "q":
                break
            # "s" = skip (이번 검토에서 건너뜀)

        return approved, rejected

    def apply_approved(self, approved: list[PendingAction]) -> None:
        """승인된 항목만 적용하고 pending 파일을 삭제한다."""
        if not approved:
            return
        backup_paths = _bk_collect(
            approved, self._project_map, self._target_root,
        )
        backup_dir = _bk_backup(
            backup_paths, self._project_map, self._target_root,
        )

        applied, failed = self._apply_actions(approved)

        _logger.info(
            t("enhancer.apply_done", n=applied, backup=backup_dir),
        )
        if failed:
            _logger.warning(
                t("enhancer.partial_fail", n=failed),
            )

    def reject(self, rejected: list[PendingAction]) -> None:
        """거절된 항목을 data/rejected/로 이동(move)한다."""
        for action in rejected:
            _pm_move_rejected(action)
            _bk_log(action, "rejected")
            _logger.info(
                t("enhancer.rejected",
                  action_type=action.action_type, name=action.name),
            )

    def count_pending_remaining(
        self,
        approved: list[PendingAction],
        rejected: list[PendingAction],
    ) -> int:
        """검토 후 건너뛴(skipped) 항목 수를 계산한다."""
        total = len(self.load_pending())
        return max(0, total - len(approved) - len(rejected))

    def rollback(self) -> None:
        """최근 백업(backup)에서 복원한다."""
        _bk_rollback(self._target_root)

    def clean_pending(self, days: int = 30) -> None:
        """오래된 pending 파일을 정리한다."""
        _pm_clean(days)

    # ------------------------------------------------------------------
    # 내부: 적용 분기(dispatch)
    # ------------------------------------------------------------------

    def _apply_one(self, action: PendingAction) -> None:
        """단일 강화 항목을 action_type에 따라 적용한다."""
        _exec_apply_one(
            action, self._target_root,
            self._project_map, self._target_root,
        )

    def _apply_actions(
        self, actions: list[PendingAction],
    ) -> tuple[int, int]:
        """액션 리스트를 순회하며 개별 실패(failure)를 허용한다.

        Returns:
            (성공 건수, 실패 건수)
        """
        applied = 0
        failed = 0
        for action in actions:
            try:
                _exec_apply_one(
                    action, self._target_root,
                    self._project_map, self._target_root,
                )
                _bk_log(action, "applied")
                _pm_remove(action)
                applied += 1
                _logger.info(
                    t("enhancer.applied",
                      action_type=action.action_type, name=action.name),
                )
            except Exception as exc:
                _bk_log(action, f"failed: {type(exc).__name__}")
                failed += 1
                _logger.error(
                    t("enhancer.apply_error",
                      action_type=action.action_type, name=action.name),
                    exc_info=True,
                )
        return applied, failed

    def _auto_apply(self, actions: list[PendingAction]) -> None:
        """auto_apply=true 시 전체 항목을 즉시 적용한다."""
        backup_paths = _bk_collect(
            actions, self._project_map, self._target_root,
        )
        backup_dir = _bk_backup(
            backup_paths, self._project_map, self._target_root,
        )
        _logger.info(t("enhancer.backup_done", dir=backup_dir))

        applied, failed = self._apply_actions(actions)

        _logger.info(t("enhancer.auto_apply_done", n=applied))
        if failed:
            _logger.warning(
                t("enhancer.partial_fail", n=failed),
            )

    # ------------------------------------------------------------------
    # 내부: 대화형 검토 (interactive review)
    # ------------------------------------------------------------------

    def _show_content_preview(
        self,
        action: PendingAction,
        diff_fn: object,
        new_fn: object,
    ) -> None:
        """action_type에 따라 Diff 뷰 또는 새 파일 미리보기를 표시한다."""
        is_modify = action.duplicate_check in ("merge", "refine")
        is_modify = is_modify or action.action_type in (
            "merge_skill", "refine_skill", "refine_agent", "add_rule",
        )
        if is_modify:
            diff_fn(action, self._target_root)
        else:
            new_fn(action)

    def _prompt_rich_choice(
        self,
        action: PendingAction,
        detail_fn: object,
        prompt_fn: object,
    ) -> str:
        """사용자 입력(y/n/s/e/d/q)을 받는다."""
        while True:
            prompt_fn()
            choice = input("").strip().lower()
            if choice == "d":
                detail_fn(action)
                continue
            if choice in ("y", "n", "s", "e", "q"):
                return choice
            print(t("review.invalid_choice"))

    def _open_editor(self, file_path: Path) -> None:
        """$EDITOR(없으면 vim)로 파일을 열어 편집(edit)한다."""
        editor = os.environ.get("EDITOR", "vim")
        subprocess.run([editor, str(file_path)], check=False)
