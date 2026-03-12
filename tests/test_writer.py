"""Obsidian 파일 생성(writer) 테스트.

daily, by-tag, archive 파일 생성 및 append 동작을 검증한다.
"""

import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.writer.obsidian_writer import ObsidianWriter

_FIXTURE_DIR = Path(__file__).parent / "fixtures"


# ------------------------------------------------------------------
# mock Config 헬퍼
# ------------------------------------------------------------------

def _make_config(vault_path: str) -> MagicMock:
    """테스트용 Config mock."""
    config = MagicMock()
    config.vault_path = vault_path
    config.obsidian_folders = {
        "daily": "Threads/daily",
        "by_tag": "Threads/by-tag",
        "archive": "Threads/archive",
        "reports": "Reports/threadloom",
    }
    return config


# ------------------------------------------------------------------
# fixture
# ------------------------------------------------------------------

@pytest.fixture
def vault(tmp_path) -> Path:
    """테스트용 Obsidian vault 디렉토리."""
    vault_path = tmp_path / "vault"
    vault_path.mkdir()
    return vault_path


@pytest.fixture
def writer(vault) -> ObsidianWriter:
    """vault가 설정된 ObsidianWriter 인스턴스."""
    config = _make_config(str(vault))
    return ObsidianWriter(config)


@pytest.fixture
def sample_posts() -> list[dict]:
    """테스트용 포스트 데이터."""
    return [
        {
            "post_id": "post-001",
            "category": "개발도구",
            "tags": ["Playwright", "세션관리"],
            "summary": "storageState로 세션 관리",
            "author": "user1",
            "url": "https://threads.net/post/001",
            "relevance": "0.85",
            "enhance_type": "skill",
        },
        {
            "post_id": "post-002",
            "category": "AI/ML",
            "tags": ["보안", "코드리뷰"],
            "summary": "보안 관점 코드 리뷰 체크리스트",
            "author": "user2",
            "url": "https://threads.net/post/002",
            "relevance": "0.80",
            "enhance_type": "agent",
        },
        {
            "post_id": "post-003",
            "category": "기타",
            "tags": ["투자"],
            "summary": "비트코인 반감기 이후 가격 전망",
            "author": "user3",
            "url": "https://threads.net/post/003",
            "relevance": "0.10",
            "enhance_type": "none",
        },
    ]


# ------------------------------------------------------------------
# write_daily 테스트
# ------------------------------------------------------------------

def test_write_daily_creates_file(writer, sample_posts, vault):
    """daily 파일이 정상 생성되어야 한다."""
    today = date(2026, 3, 12)
    path = writer.write_daily(today, sample_posts)

    assert path.exists()
    assert path.name == "2026-03-12.md"


def test_write_daily_contains_frontmatter(writer, sample_posts):
    """daily 파일에 YAML frontmatter가 포함되어야 한다."""
    today = date(2026, 3, 12)
    path = writer.write_daily(today, sample_posts)
    content = path.read_text(encoding="utf-8")

    assert "---" in content
    assert "date: 2026-03-12" in content
    assert "source: threadloom" in content


def test_write_daily_groups_by_category(writer, sample_posts):
    """daily 파일에 카테고리별 그룹이 표시되어야 한다."""
    today = date(2026, 3, 12)
    path = writer.write_daily(today, sample_posts)
    content = path.read_text(encoding="utf-8")

    assert "## 개발도구" in content
    assert "## AI/ML" in content


def test_write_daily_contains_post_links(writer, sample_posts):
    """daily 파일에 archive 링크가 포함되어야 한다."""
    today = date(2026, 3, 12)
    path = writer.write_daily(today, sample_posts)
    content = path.read_text(encoding="utf-8")

    # 카테고리별 하위 경로 포함 (archive/{category}/{post_id})
    assert "archive/개발도구/post-001" in content


def test_write_daily_contains_tags(writer, sample_posts):
    """daily 파일에 태그가 표시되어야 한다."""
    today = date(2026, 3, 12)
    path = writer.write_daily(today, sample_posts)
    content = path.read_text(encoding="utf-8")

    assert "#Playwright" in content or "#세션관리" in content


# ------------------------------------------------------------------
# write_by_tag 테스트
# ------------------------------------------------------------------

def test_write_by_tag_creates_file(writer, sample_posts, vault):
    """by-tag 파일이 정상 생성되어야 한다."""
    path = writer.write_by_tag("Playwright", sample_posts[:1])
    assert path.exists()


def test_write_by_tag_filename_escapes_slash(writer, sample_posts, vault):
    """태그명의 슬래시(/)가 하이픈(-)으로 치환되어야 한다."""
    path = writer.write_by_tag("AI/ML", sample_posts[1:2])
    assert "AI-ML" in path.name


def test_write_by_tag_append_mode(writer, sample_posts, vault):
    """같은 태그 파일에 추가(append) 시 기존 내용이 유지되어야 한다."""
    writer.write_by_tag("Playwright", sample_posts[:1])
    writer.write_by_tag("Playwright", sample_posts[:1])

    # by-tag 폴더에서 Playwright.md 확인
    tag_dir = vault / "Threads" / "by-tag"
    path = tag_dir / "Playwright.md"
    content = path.read_text(encoding="utf-8")

    # 두 번 append된 내용 확인
    assert content.count("post-001") >= 2


# ------------------------------------------------------------------
# write_archive 테스트
# ------------------------------------------------------------------

def test_write_archive_creates_file(writer, sample_posts, vault):
    """archive 파일이 정상 생성되어야 한다."""
    path = writer.write_archive(sample_posts[0])
    assert path.exists()
    assert path.name == "post-001.md"


def test_write_archive_contains_frontmatter(writer, sample_posts):
    """archive 파일에 frontmatter가 포함되어야 한다."""
    path = writer.write_archive(sample_posts[0])
    content = path.read_text(encoding="utf-8")

    assert "post_id: post-001" in content
    assert "author: user1" in content
    assert "category: 개발도구" in content


def test_write_archive_skips_duplicate(writer, sample_posts, vault):
    """이미 존재하는 archive 파일은 덮어쓰지 않아야 한다."""
    path1 = writer.write_archive(sample_posts[0])
    original_content = path1.read_text(encoding="utf-8")

    # 다른 내용의 같은 post_id
    modified = sample_posts[0].copy()
    modified["summary"] = "변경된 요약"
    path2 = writer.write_archive(modified)

    assert path1 == path2
    content = path2.read_text(encoding="utf-8")
    assert content == original_content  # 원본 유지


def test_write_archive_contains_analysis(writer, sample_posts):
    """archive 파일에 분석 결과(요약, 유용성 등)가 포함되어야 한다."""
    path = writer.write_archive(sample_posts[0])
    content = path.read_text(encoding="utf-8")

    assert "storageState" in content
    assert "0.85" in content


# ------------------------------------------------------------------
# write_all 통합 테스트
# ------------------------------------------------------------------

def test_write_all_creates_all_file_types(writer, vault):
    """write_all이 daily, by-tag, archive 파일을 모두 생성해야 한다."""
    analysis_path = _FIXTURE_DIR / "sample_analysis.md"
    result = writer.write_all(analysis_path)

    assert len(result["daily"]) >= 1
    assert len(result["by_tag"]) >= 1
    assert len(result["archive"]) >= 1


def test_write_all_daily_file_exists(writer, vault):
    """write_all 후 daily 파일이 존재해야 한다."""
    analysis_path = _FIXTURE_DIR / "sample_analysis.md"
    result = writer.write_all(analysis_path)

    for path in result["daily"]:
        assert path.exists()


def test_write_all_archive_files_exist(writer, vault):
    """write_all 후 archive 파일들이 존재해야 한다."""
    analysis_path = _FIXTURE_DIR / "sample_analysis.md"
    result = writer.write_all(analysis_path)

    for path in result["archive"]:
        assert path.exists()


# ------------------------------------------------------------------
# dry_run_report 테스트
# ------------------------------------------------------------------

def test_dry_run_report_contains_count(writer):
    """dry-run 리포트에 포스트 수가 포함되어야 한다."""
    analysis_path = _FIXTURE_DIR / "sample_analysis.md"
    report = writer.dry_run_report(analysis_path)

    assert "포스트 수:" in report


def test_dry_run_report_contains_tag_list(writer):
    """dry-run 리포트에 태그 목록이 포함되어야 한다."""
    analysis_path = _FIXTURE_DIR / "sample_analysis.md"
    report = writer.dry_run_report(analysis_path)

    assert "by-tag" in report


def test_dry_run_report_no_file_created(writer, vault):
    """dry-run은 실제 파일을 생성하지 않아야 한다."""
    analysis_path = _FIXTURE_DIR / "sample_analysis.md"
    writer.dry_run_report(analysis_path)

    daily_dir = vault / "Threads" / "daily"
    if daily_dir.exists():
        assert len(list(daily_dir.glob("*.md"))) == 0


# ------------------------------------------------------------------
# 유틸리티 메서드 테스트
# ------------------------------------------------------------------

def test_make_title_truncates_long_summary(writer):
    """30자 초과 요약은 27자 + '...'으로 잘려야 한다."""
    post = {"summary": "a" * 50}
    title = writer._make_title(post)
    assert len(title) == 30
    assert title.endswith("...")


def test_make_title_short_summary(writer):
    """30자 이하 요약은 그대로 반환해야 한다."""
    post = {"summary": "짧은 요약"}
    title = writer._make_title(post)
    assert title == "짧은 요약"


def test_collect_tags_returns_unique_sorted(writer):
    """태그 수집 시 중복 제거 후 정렬되어야 한다."""
    posts = [
        {"tags": ["Python", "AI"]},
        {"tags": ["AI", "Rust"]},
    ]
    tags = writer._collect_tags(posts)
    assert tags == ["AI", "Python", "Rust"]


def test_parse_tag_list_empty(writer):
    """빈 태그 문자열은 빈 리스트를 반환해야 한다."""
    assert writer._parse_tag_list("[]") == []
    assert writer._parse_tag_list("") == []
