"""checkpoint(부분 저장) 관리 모듈.

수집 중 비정상 종료에 대비하여 중간 결과를 저장하고 복원한다.
"""

import json
from pathlib import Path

from src.collector.models import ThreadPost
from src.utils.i18n import t
from src.utils.logger import get_logger

_logger = get_logger("collector.checkpoint")


def save_checkpoint(posts: list[ThreadPost], path: Path) -> None:
    """현재까지 수집된 포스트를 checkpoint 파일에 저장한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [p.to_dict() for p in posts]
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def load_checkpoint(path: Path) -> list[ThreadPost]:
    """checkpoint 파일에서 포스트 목록을 로드(load)한다."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return [ThreadPost.from_dict(d) for d in data]


def find_checkpoint(raw_dir: Path) -> Path | None:
    """가장 최근 checkpoint 파일을 반환한다. 없으면 None."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    checkpoints = sorted(raw_dir.glob(".checkpoint_*.json"))
    return checkpoints[-1] if checkpoints else None


def cleanup_checkpoint(path: Path) -> None:
    """정상 완료 시 checkpoint 파일을 삭제한다."""
    if path.exists():
        path.unlink()
        _logger.info(t("collector.checkpoint_cleaned"))
