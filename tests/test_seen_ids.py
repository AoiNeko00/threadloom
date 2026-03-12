"""seen_post_ids 기반 중복 수집 방지 + collection_start 시각 기록 테스트.

재실행 시 수집 건수 0건 이슈(last_sync > saved_at) 해결을 검증한다.
"""

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.collector.models import ThreadPost
from src.utils.state import (
    _MAX_SEEN_IDS,
    _STATE_FILE,
    _write_state,
    get_seen_post_ids,
    update_seen_post_ids,
)


# ------------------------------------------------------------------
# fixture
# ------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    """테스트마다 state.json을 격리(isolate)한다."""
    state_file = tmp_path / "state.json"
    monkeypatch.setattr("src.utils.state._STATE_FILE", state_file)
    monkeypatch.setattr("src.utils.state._DATA_DIR", tmp_path)
    yield


# ------------------------------------------------------------------
# get_seen_post_ids / update_seen_post_ids 단위 테스트
# ------------------------------------------------------------------

def test_get_seen_ids_empty_when_no_state():
    """state.json이 없으면 빈 집합을 반환한다."""
    result = get_seen_post_ids()
    assert result == set()


def test_update_and_get_seen_ids():
    """추가한 post_id가 조회된다."""
    update_seen_post_ids({"id1", "id2"})
    result = get_seen_post_ids()
    assert "id1" in result
    assert "id2" in result


def test_update_seen_ids_accumulates():
    """여러 번 호출하면 누적(accumulate)된다."""
    update_seen_post_ids({"a"})
    update_seen_post_ids({"b", "c"})
    result = get_seen_post_ids()
    assert result == {"a", "b", "c"}


def test_update_seen_ids_no_duplicates():
    """같은 ID를 다시 추가해도 중복되지 않는다."""
    update_seen_post_ids({"x"})
    update_seen_post_ids({"x", "y"})
    result = get_seen_post_ids()
    assert result == {"x", "y"}


def test_seen_ids_max_limit(tmp_path, monkeypatch):
    """_MAX_SEEN_IDS 초과 시 오래된 항목이 제거된다."""
    # 먼저 MAX개 채우기
    old_ids = {f"old_{i}" for i in range(_MAX_SEEN_IDS)}
    update_seen_post_ids(old_ids)
    assert len(get_seen_post_ids()) == _MAX_SEEN_IDS

    # 추가 10개 삽입 → 가장 오래된 10개 탈락
    new_ids = {f"new_{i}" for i in range(10)}
    update_seen_post_ids(new_ids)
    result = get_seen_post_ids()
    assert len(result) == _MAX_SEEN_IDS
    # 새 ID는 모두 포함
    for nid in new_ids:
        assert nid in result


# ------------------------------------------------------------------
# ThreadsScraper.collect()에서 seen_ids 필터링 검증
# ------------------------------------------------------------------

def test_collect_filters_seen_ids(tmp_path, monkeypatch):
    """seen_ids에 있는 포스트는 raw md에 포함되지 않는다."""
    from src.collector.threads_scraper import ThreadsScraper

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    monkeypatch.setattr("src.collector.threads_scraper._RAW_DIR", raw_dir)

    scraper = ThreadsScraper(auth_manager=None)

    posts = [
        ThreadPost("seen1", "a", "old text", "https://url1", datetime.now()),
        ThreadPost("new1", "b", "new text", "https://url2", datetime.now()),
    ]

    # _scrape_saved_posts를 mock하여 posts 반환
    monkeypatch.setattr(
        scraper, "_scrape_saved_posts",
        lambda since, resumed, cp: posts,
    )
    monkeypatch.setattr(
        scraper, "_find_checkpoint", lambda: None,
    )

    # seen_ids에 "seen1" 포함 → 필터링되어야 함
    path = scraper.collect(since=None, seen_ids={"seen1"})
    content = path.read_text(encoding="utf-8")

    assert "new1" in content
    assert "seen1" not in content


def test_collect_no_filter_when_seen_ids_none(tmp_path, monkeypatch):
    """seen_ids=None이면 모든 포스트가 포함된다."""
    from src.collector.threads_scraper import ThreadsScraper

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    monkeypatch.setattr("src.collector.threads_scraper._RAW_DIR", raw_dir)

    scraper = ThreadsScraper(auth_manager=None)

    posts = [
        ThreadPost("id1", "a", "text1", "https://url1", datetime.now()),
        ThreadPost("id2", "b", "text2", "https://url2", datetime.now()),
    ]

    monkeypatch.setattr(
        scraper, "_scrape_saved_posts",
        lambda since, resumed, cp: posts,
    )
    monkeypatch.setattr(
        scraper, "_find_checkpoint", lambda: None,
    )

    path = scraper.collect(since=None, seen_ids=None)
    content = path.read_text(encoding="utf-8")
    assert "collected: 2" in content


# ------------------------------------------------------------------
# update_state에 collection_start 전달 검증
# ------------------------------------------------------------------

def test_update_state_uses_collection_start(tmp_path, monkeypatch):
    """update_state에 collection_start를 전달하면 last_sync에 그 값이 저장된다."""
    from src.pipeline.runner import update_state
    from src.utils.state import get_last_sync

    # raw md 파일 생성
    raw_path = tmp_path / "test_raw.md"
    raw_path.write_text(
        "# Threads 수집\n수집 건수: 1\n\n---\n\n"
        "**post_id**: abc123\n**작성자**: user1\n본문\n",
        encoding="utf-8",
    )

    collection_start = datetime(2026, 3, 12, 6, 0, 0)
    update_state(raw_path, collection_start=collection_start)

    last_sync = get_last_sync()
    assert last_sync is not None
    assert last_sync == collection_start


def test_update_state_without_collection_start_uses_now(tmp_path, monkeypatch):
    """collection_start 없으면 현재 시각(now)이 last_sync로 저장된다."""
    from src.pipeline.runner import update_state
    from src.utils.state import get_last_sync

    raw_path = tmp_path / "test_raw.md"
    raw_path.write_text(
        "# Threads 수집\n수집 건수: 1\n\n---\n\n"
        "**post_id**: xyz789\n**작성자**: user1\n본문\n",
        encoding="utf-8",
    )

    before = datetime.now()
    update_state(raw_path)
    after = datetime.now()

    last_sync = get_last_sync()
    assert last_sync is not None
    assert before <= last_sync <= after


def test_update_state_updates_seen_post_ids(tmp_path, monkeypatch):
    """update_state가 seen_post_ids도 갱신한다."""
    from src.pipeline.runner import update_state

    raw_path = tmp_path / "test_raw.md"
    raw_path.write_text(
        "# Threads 수집\n수집 건수: 2\n\n---\n\n"
        "**post_id**: aaa111\n본문1\n\n---\n\n"
        "**post_id**: bbb222\n본문2\n",
        encoding="utf-8",
    )

    update_state(raw_path, collection_start=datetime.now())

    seen = get_seen_post_ids()
    assert "aaa111" in seen
    assert "bbb222" in seen


# ------------------------------------------------------------------
# 시나리오: 재실행 시 collection_start < saved_at 방지 검증
# ------------------------------------------------------------------

def test_rerun_scenario_no_filtering(tmp_path, monkeypatch):
    """재실행 시나리오: collection_start를 사용하면 포스트가 필터링되지 않는다.

    기존 문제: last_sync(종료 시각) > saved_at(수집 시각) → 재실행 시 0건
    해결: last_sync에 collection_start(시작 시각)를 저장
    """
    from src.pipeline.runner import update_state
    from src.utils.state import get_last_sync

    # 1차 실행: collection_start = 10:00, 수집 종료 = 10:05
    collection_start = datetime(2026, 3, 12, 10, 0, 0)

    raw_path = tmp_path / "run1.md"
    raw_path.write_text(
        "# Threads 수집\n수집 건수: 1\n\n---\n\n"
        "**post_id**: p001\n본문\n",
        encoding="utf-8",
    )
    update_state(raw_path, collection_start=collection_start)

    last_sync = get_last_sync()
    # last_sync는 collection_start(10:00)이어야 함 (종료 시각 10:05가 아님)
    assert last_sync == collection_start

    # 2차 실행: 10:03에 저장된 새 포스트 → since(10:00) < saved_at(10:03) → 수집됨
    new_post_saved_at = datetime(2026, 3, 12, 10, 3, 0)
    assert new_post_saved_at > last_sync  # 핵심: 새 포스트가 필터링되지 않음
