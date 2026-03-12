"""threadloom 상태(state) 관리 모듈.

data/state.json을 읽고 쓰며 동기화(sync) 이력을 추적한다.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

# 프로젝트 루트 기준 상태 파일(state file) 경로
_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
_DATA_DIR: Path = _PROJECT_ROOT / "data"
_STATE_FILE: Path = _DATA_DIR / "state.json"


def _read_state() -> dict[str, Any]:
    """state.json을 읽어 딕셔너리로 반환한다."""
    if not _STATE_FILE.exists():
        return {}
    text = _STATE_FILE.read_text(encoding="utf-8")
    if not text.strip():
        return {}
    return json.loads(text)


def _write_state(state: dict[str, Any]) -> None:
    """딕셔너리를 state.json에 저장한다."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_last_sync() -> datetime | None:
    """마지막 동기화(last sync) 시각을 반환한다.

    state.json이 없거나 last_sync가 없으면 None.
    """
    state = _read_state()
    last_sync = state.get("last_sync")
    if last_sync is None:
        return None
    return datetime.fromisoformat(last_sync)


def update_last_sync(dt: datetime, post_count: int, last_id: str) -> None:
    """동기화 상태를 갱신한다.

    Args:
        dt: 동기화 시각
        post_count: 이번에 수집한 포스트 수
        last_id: 마지막 포스트 ID
    """
    state = _read_state()
    prev_total = state.get("total_collected", 0)
    state["last_sync"] = dt.isoformat()
    state["total_collected"] = prev_total + post_count
    state["last_post_id"] = last_id
    _write_state(state)


def get_total_collected() -> int:
    """누적 수집(total collected) 포스트 수를 반환한다."""
    state = _read_state()
    return state.get("total_collected", 0)


# 최대 보관할 seen_post_ids 개수
_MAX_SEEN_IDS: int = 1000


def get_seen_post_ids() -> set[str]:
    """이전에 수집한 포스트 ID(seen post IDs) 집합을 반환한다."""
    state = _read_state()
    return set(state.get("seen_post_ids", []))


def update_seen_post_ids(new_ids: set[str]) -> None:
    """신규 포스트 ID를 seen_post_ids에 추가한다.

    최근 _MAX_SEEN_IDS개만 유지하여 state.json 비대화를 방지한다.
    """
    state = _read_state()
    existing = list(state.get("seen_post_ids", []))
    merged = existing + [pid for pid in new_ids if pid not in set(existing)]
    # 최근 N개만 유지 (오래된 항목 앞쪽 제거)
    state["seen_post_ids"] = merged[-_MAX_SEEN_IDS:]
    _write_state(state)
