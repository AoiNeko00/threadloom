"""백업(backup) 및 이력(log) 관리 모듈.

적용 전 기존 파일 백업, 복원(rollback), enhance_log.json 이력 기록을 담당한다.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path

from src.enhancer.action_executor import resolve_target_path
from src.enhancer.models import PendingAction
from src.utils.i18n import t
from src.utils.logger import get_logger
from src.utils.paths import BACKUPS_DIR, ENHANCE_LOG

_logger = get_logger("backup_manager")

# 중앙 경로(centralized path) 모듈에서 가져옴
_BACKUPS_DIR = BACKUPS_DIR
_ENHANCE_LOG = ENHANCE_LOG


def collect_backup_targets(
    actions: list[PendingAction],
    project_map: dict[str, str],
    default_root: Path,
) -> list[str]:
    """적용 대상 파일 경로(path) 리스트를 수집한다."""
    paths: list[str] = []
    for action in actions:
        target = resolve_target_path(action, project_map, default_root)
        if target and target.exists():
            paths.append(str(target))
    return paths


def backup(
    paths: list[str],
    project_map: dict[str, str],
    default_root: Path,
) -> Path:
    """기존 파일을 data/backups/{timestamp}/ 에 백업한다."""
    timestamp = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    backup_dir = _BACKUPS_DIR / timestamp
    backup_dir.mkdir(parents=True, exist_ok=True)

    for path_str in paths:
        src = Path(path_str)
        if not src.exists():
            continue
        # 상대경로(relative path) 유지 — 다중 프로젝트 대응
        rel = safe_relative_to(src, project_map, default_root)
        dest = backup_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dest))

    return backup_dir


def safe_relative_to(
    path: Path,
    project_map: dict[str, str],
    default_root: Path,
) -> Path:
    """다중 프로젝트(multi-project)를 고려한 상대경로를 반환한다."""
    for project_path in project_map.values():
        try:
            return Path(path).relative_to(project_path)
        except ValueError:
            continue
    try:
        return path.relative_to(default_root)
    except ValueError:
        return Path(path.name)


def find_latest_backup() -> Path | None:
    """가장 최근 백업 디렉토리를 찾는다."""
    if not _BACKUPS_DIR.is_dir():
        return None
    dirs = sorted(_BACKUPS_DIR.iterdir(), reverse=True)
    for d in dirs:
        if d.is_dir():
            return d
    return None


def restore_backup(backup_dir: Path, target_root: Path) -> None:
    """백업 디렉토리의 파일을 원래 위치로 복원(restore)한다."""
    for backup_file in backup_dir.rglob("*"):
        if not backup_file.is_file():
            continue
        rel = backup_file.relative_to(backup_dir)
        dest = target_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(backup_file), str(dest))


def rollback(target_root: Path) -> None:
    """최근 백업(backup)에서 복원한다."""
    latest = find_latest_backup()
    if not latest:
        _logger.warning(t("enhancer.no_backup"))
        return
    restore_backup(latest, target_root)
    mark_rolled_back(latest.name)
    _logger.info(t("enhancer.backup_restored", name=latest.name))


# ------------------------------------------------------------------
# 이력(log) 관리
# ------------------------------------------------------------------

def log_enhancement(action: PendingAction, result: str) -> None:
    """data/enhance_log.json에 이력을 추가한다."""
    log = read_log()
    log.append({
        "timestamp": datetime.now().isoformat(),
        "action_type": action.action_type,
        "name": action.name,
        "target": action.target,
        "source_posts": action.source_posts,
        "result": result,
    })
    write_log(log)


def read_log() -> list[dict]:
    """enhance_log.json을 읽는다."""
    if not _ENHANCE_LOG.exists():
        return []
    try:
        text = _ENHANCE_LOG.read_text(encoding="utf-8")
        return json.loads(text)
    except (json.JSONDecodeError, OSError):
        return []


def write_log(log: list[dict]) -> None:
    """enhance_log.json에 기록한다."""
    _ENHANCE_LOG.parent.mkdir(parents=True, exist_ok=True)
    _ENHANCE_LOG.write_text(
        json.dumps(log, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def mark_rolled_back(backup_name: str) -> None:
    """enhance_log.json에서 해당 백업 항목 상태를 rolled_back으로 변경."""
    log = read_log()
    for entry in log:
        if entry.get("backup", "").endswith(backup_name + "/"):
            entry["result"] = "rolled_back"
    write_log(log)
