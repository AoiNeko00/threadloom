"""Phase 1 수집(collection) 결과 형식 검증 테스트.

ThreadPost -> raw md 변환 형식, frontmatter 필수 필드,
포스트 구분자(---) 형식을 검증한다.
실제 Threads 접속 없이 mock 데이터만 사용한다.
"""

import sys
from datetime import datetime
from pathlib import Path

import pytest

# 프로젝트 루트를 sys.path에 추가
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.collector.threads_scraper import ThreadPost, ThreadsScraper


# ------------------------------------------------------------------
# fixture
# ------------------------------------------------------------------

@pytest.fixture
def sample_posts() -> list[ThreadPost]:
    """테스트용 ThreadPost 목록을 반환한다."""
    return [
        ThreadPost(
            post_id="abc001",
            author="user1",
            text="Playwright storageState 사용법 정리",
            url="https://threads.net/@user1/post/abc001",
            saved_at=datetime(2026, 3, 11, 10, 0),
            media_urls=[],
        ),
        ThreadPost(
            post_id="abc002",
            author="user2",
            text="타입 힌트 규칙 정리\n여러 줄 텍스트",
            url="https://threads.net/@user2/post/abc002",
            saved_at=datetime(2026, 3, 11, 11, 0),
            media_urls=["https://img.example.com/photo.jpg"],
        ),
    ]


@pytest.fixture
def scraper() -> ThreadsScraper:
    """AuthManager 없이 ThreadsScraper 인스턴스를 생성한다."""
    return ThreadsScraper(auth_manager=None)


# ------------------------------------------------------------------
# _format_post_md 형식 검증
# ------------------------------------------------------------------

def test_format_post_md_contains_author(scraper, sample_posts):
    """포스트 markdown에 작성자(author)가 포함되어야 한다."""
    block = scraper._format_post_md(sample_posts[0])
    text = "\n".join(block)
    assert "**author**: @user1" in text


def test_format_post_md_contains_post_id(scraper, sample_posts):
    """포스트 markdown에 post_id가 포함되어야 한다."""
    block = scraper._format_post_md(sample_posts[0])
    text = "\n".join(block)
    assert "**post_id**: abc001" in text


def test_format_post_md_contains_url(scraper, sample_posts):
    """포스트 markdown에 URL이 포함되어야 한다."""
    block = scraper._format_post_md(sample_posts[0])
    text = "\n".join(block)
    assert "**URL**: https://threads.net/@user1/post/abc001" in text


def test_format_post_md_contains_saved_at(scraper, sample_posts):
    """포스트 markdown에 저장일(saved_at)이 포함되어야 한다."""
    block = scraper._format_post_md(sample_posts[0])
    text = "\n".join(block)
    assert "**saved_at**:" in text


def test_format_post_md_contains_text_body(scraper, sample_posts):
    """포스트 markdown에 본문(text)이 포함되어야 한다."""
    block = scraper._format_post_md(sample_posts[0])
    text = "\n".join(block)
    assert "Playwright storageState 사용법 정리" in text


def test_format_post_md_starts_with_separator(scraper, sample_posts):
    """포스트 markdown은 구분자(---)로 시작해야 한다."""
    block = scraper._format_post_md(sample_posts[0])
    assert block[0] == "---"


def test_format_post_md_includes_media_when_present(scraper, sample_posts):
    """미디어(media) URL이 있으면 포함되어야 한다."""
    block = scraper._format_post_md(sample_posts[1])
    text = "\n".join(block)
    assert "https://img.example.com/photo.jpg" in text
    assert "**media:**" in text


def test_format_post_md_no_media_section_when_empty(scraper, sample_posts):
    """미디어가 없으면 미디어 섹션이 없어야 한다."""
    block = scraper._format_post_md(sample_posts[0])
    text = "\n".join(block)
    assert "**media:**" not in text


# ------------------------------------------------------------------
# _write_raw_md 파일 생성 검증
# ------------------------------------------------------------------

def test_write_raw_md_creates_file(scraper, sample_posts, tmp_path, monkeypatch):
    """raw md 파일이 정상 생성되어야 한다."""
    # _RAW_DIR을 tmp_path로 교체
    monkeypatch.setattr(
        "src.collector.threads_scraper._RAW_DIR", tmp_path,
    )
    path = scraper._write_raw_md(sample_posts, "20260312_070000")
    assert path.exists()
    assert path.suffix == ".md"


def test_write_raw_md_contains_header(scraper, sample_posts, tmp_path, monkeypatch):
    """raw md 파일에 제목 헤더가 포함되어야 한다."""
    monkeypatch.setattr(
        "src.collector.threads_scraper._RAW_DIR", tmp_path,
    )
    path = scraper._write_raw_md(sample_posts, "20260312_070000")
    content = path.read_text(encoding="utf-8")
    assert "# Threads Collection" in content


def test_write_raw_md_contains_count(scraper, sample_posts, tmp_path, monkeypatch):
    """raw md 파일에 수집 건수가 포함되어야 한다."""
    monkeypatch.setattr(
        "src.collector.threads_scraper._RAW_DIR", tmp_path,
    )
    path = scraper._write_raw_md(sample_posts, "20260312_070000")
    content = path.read_text(encoding="utf-8")
    assert "collected: 2" in content


def test_write_raw_md_utf8_encoding(scraper, sample_posts, tmp_path, monkeypatch):
    """raw md 파일은 UTF-8 인코딩이어야 한다."""
    monkeypatch.setattr(
        "src.collector.threads_scraper._RAW_DIR", tmp_path,
    )
    path = scraper._write_raw_md(sample_posts, "20260312_070000")
    # UTF-8로 읽기 시 에러 없어야 함
    content = path.read_text(encoding="utf-8")
    assert len(content) > 0


# ------------------------------------------------------------------
# 중복 제거(deduplication) 검증
# ------------------------------------------------------------------

def test_deduplicate_removes_duplicate_urls(scraper):
    """같은 URL의 포스트는 중복 제거되어야 한다."""
    posts = [
        ThreadPost("id1", "a", "text1", "https://same.url", datetime.now()),
        ThreadPost("id2", "b", "text2", "https://same.url", datetime.now()),
    ]
    result = scraper._deduplicate(posts)
    assert len(result) == 1


def test_deduplicate_keeps_unique_posts(scraper):
    """서로 다른 URL의 포스트는 유지되어야 한다."""
    posts = [
        ThreadPost("id1", "a", "text1", "https://url1", datetime.now()),
        ThreadPost("id2", "b", "text2", "https://url2", datetime.now()),
    ]
    result = scraper._deduplicate(posts)
    assert len(result) == 2


# ------------------------------------------------------------------
# post_id 생성 검증
# ------------------------------------------------------------------

def test_generate_post_id_from_url(scraper):
    """URL 기반 post_id는 16자 해시여야 한다."""
    pid = scraper._generate_post_id("https://threads.net/post/123", "text")
    assert len(pid) == 16
    assert pid.isalnum()


def test_generate_post_id_from_text_when_no_url(scraper):
    """URL이 빈 경우 텍스트 기반 해시를 생성해야 한다."""
    pid = scraper._generate_post_id("", "some text content")
    assert len(pid) == 16


def test_generate_post_id_deterministic(scraper):
    """동일 입력에 대해 동일 post_id를 반환해야 한다."""
    pid1 = scraper._generate_post_id("https://url", "text")
    pid2 = scraper._generate_post_id("https://url", "text")
    assert pid1 == pid2


# ------------------------------------------------------------------
# self-reply(이어쓰기) 관련 검증
# ------------------------------------------------------------------

def test_format_post_md_contains_reply_count(scraper):
    """이어쓰기 건수가 markdown에 표시되어야 한다."""
    post = ThreadPost(
        post_id="r001",
        author="user1",
        text="본문\n\n---\n\n이어쓰기1\n\n---\n\n이어쓰기2",
        url="https://threads.net/@user1/post/r001",
        saved_at=datetime(2026, 3, 11, 10, 0),
        replies=["이어쓰기1", "이어쓰기2"],
    )
    block = scraper._format_post_md(post)
    text = "\n".join(block)
    assert "**replies**: 2" in text


def test_format_post_md_zero_replies(scraper, sample_posts):
    """이어쓰기가 없으면 0건으로 표시되어야 한다."""
    block = scraper._format_post_md(sample_posts[0])
    text = "\n".join(block)
    assert "**replies**: 0" in text


def test_thread_post_replies_default_empty():
    """ThreadPost의 replies 기본값은 빈 리스트여야 한다."""
    post = ThreadPost(
        post_id="x", author="a", text="t",
        url="u", saved_at=datetime.now(),
    )
    assert post.replies == []


def test_thread_post_text_includes_replies():
    """replies가 있는 포스트의 text에 이어쓰기 내용이 포함되어야 한다."""
    post = ThreadPost(
        post_id="x", author="a",
        text="본문\n\n---\n\n이어쓰기 내용",
        url="u", saved_at=datetime.now(),
        replies=["이어쓰기 내용"],
    )
    assert "이어쓰기 내용" in post.text


# ------------------------------------------------------------------
# checkpoint(부분 저장) 관련 검증
# ------------------------------------------------------------------

def test_checkpoint_save_and_load(scraper, sample_posts, tmp_path, monkeypatch):
    """checkpoint 저장 후 로드하면 동일한 포스트가 복원되어야 한다."""
    monkeypatch.setattr("src.collector.threads_scraper._RAW_DIR", tmp_path)
    cp_path = tmp_path / ".checkpoint_test.json"

    scraper._save_checkpoint(sample_posts, cp_path)
    assert cp_path.exists()

    loaded = scraper._load_checkpoint(cp_path)
    assert len(loaded) == len(sample_posts)
    assert loaded[0].post_id == sample_posts[0].post_id
    assert loaded[0].author == sample_posts[0].author
    assert loaded[0].text == sample_posts[0].text
    assert loaded[1].media_urls == sample_posts[1].media_urls


def test_checkpoint_resume_deduplicates(scraper, tmp_path, monkeypatch):
    """이어서 수집 시 이미 checkpoint에 있는 포스트는 중복 추가되지 않아야 한다."""
    monkeypatch.setattr("src.collector.threads_scraper._RAW_DIR", tmp_path)

    existing = [
        ThreadPost("dup01", "a", "text1", "https://url1", datetime.now()),
        ThreadPost("dup02", "b", "text2", "https://url2", datetime.now()),
    ]
    new_posts = [
        ThreadPost("dup01", "a", "text1", "https://url1", datetime.now()),
        ThreadPost("new03", "c", "text3", "https://url3", datetime.now()),
    ]

    merged = scraper._merge_posts(list(existing), new_posts)
    assert len(merged) == 3
    ids = [p.post_id for p in merged]
    assert ids.count("dup01") == 1


def test_checkpoint_cleanup_on_success(scraper, tmp_path, monkeypatch):
    """정상 완료 시 checkpoint 파일이 삭제되어야 한다."""
    monkeypatch.setattr("src.collector.threads_scraper._RAW_DIR", tmp_path)
    cp_path = tmp_path / ".checkpoint_test.json"
    cp_path.write_text("[]", encoding="utf-8")
    assert cp_path.exists()

    scraper._cleanup_checkpoint(cp_path)
    assert not cp_path.exists()


def test_find_checkpoint_returns_latest(scraper, tmp_path, monkeypatch):
    """여러 checkpoint 중 가장 최근 것을 반환해야 한다."""
    monkeypatch.setattr("src.collector.threads_scraper._RAW_DIR", tmp_path)

    (tmp_path / ".checkpoint_20260301_010000.json").write_text("[]")
    (tmp_path / ".checkpoint_20260302_020000.json").write_text("[]")

    result = scraper._find_checkpoint()
    assert result is not None
    assert "20260302" in result.name


def test_find_checkpoint_returns_none_when_empty(scraper, tmp_path, monkeypatch):
    """checkpoint 파일이 없으면 None을 반환해야 한다."""
    monkeypatch.setattr("src.collector.threads_scraper._RAW_DIR", tmp_path)
    result = scraper._find_checkpoint()
    assert result is None


def test_thread_post_to_dict_datetime_format(sample_posts):
    """to_dict()의 saved_at은 ISO 형식(isoformat) 문자열이어야 한다."""
    d = sample_posts[0].to_dict()
    assert isinstance(d["saved_at"], str)
    # 역변환 가능해야 함
    datetime.fromisoformat(d["saved_at"])


def test_thread_post_from_dict_roundtrip(sample_posts):
    """to_dict -> from_dict 왕복(roundtrip) 변환이 정확해야 한다."""
    original = sample_posts[1]
    restored = ThreadPost.from_dict(original.to_dict())
    assert restored.post_id == original.post_id
    assert restored.saved_at == original.saved_at
    assert restored.media_urls == original.media_urls
    assert restored.replies == original.replies


# ------------------------------------------------------------------
# 텍스트 정제(cleaning) 관련 검증
# ------------------------------------------------------------------

def test_clean_removes_engagement_numbers(scraper):
    """좋아요, 댓글, 리포스트, 공유 수 등 순수 숫자를 제거한다."""
    raw = "본문 내용입니다\n45\n3\n6\n16"
    result = scraper._clean_post_text(raw, "author")
    assert result == "본문 내용입니다"


def test_clean_removes_translate_button(scraper):
    """Translate 버튼 텍스트를 제거한다."""
    raw = "Some content\nTranslate\n100"
    result = scraper._clean_post_text(raw, "author")
    assert "Translate" not in result
    assert "Some content" in result


def test_clean_removes_author_name(scraper):
    """작성자명 중복을 제거한다."""
    raw = "daon_k\nTech Threads\n1d\n실제 본문 텍스트"
    result = scraper._clean_post_text(raw, "daon_k")
    assert "daon_k" not in result
    assert "실제 본문 텍스트" in result


def test_clean_removes_timestamp(scraper):
    """타임스탬프(1d, 2h, 12/01/25 등)를 제거한다."""
    raw = "2h\n12/01/25\n1d\n본문"
    result = scraper._clean_post_text(raw, "author")
    assert "2h" not in result
    assert "12/01/25" not in result
    assert "본문" in result


def test_clean_removes_ui_tokens(scraper):
    """UI 라벨(Author, ·, Like 등)을 제거한다."""
    raw = "·\nAuthor\n이어쓰기 내용\nLike\nReply"
    result = scraper._clean_post_text(raw, "author")
    assert result == "이어쓰기 내용"


def test_clean_preserves_numbers_in_text(scraper):
    """본문에 포함된 숫자(포트 번호 등)는 보존한다."""
    raw = "localhost:3000 포트를 사용합니다\n45"
    result = scraper._clean_post_text(raw, "author")
    assert "localhost:3000" in result
    assert "45" not in result


# ------------------------------------------------------------------
# self-reply 상세 페이지 진입 최적화(optimization) 검증
# ------------------------------------------------------------------

def test_should_fetch_replies_with_replies(scraper):
    """reply_count > 0이면 상세 페이지 진입이 필요하다."""
    post = ThreadPost(
        post_id="x", author="a", text="t",
        url="u", saved_at=datetime.now(), reply_count=3,
    )
    assert scraper._should_fetch_replies(post) is True


def test_should_fetch_replies_without_replies(scraper):
    """reply_count == 0이면 상세 페이지 진입이 불필요하다."""
    post = ThreadPost(
        post_id="x", author="a", text="t",
        url="u", saved_at=datetime.now(), reply_count=0,
    )
    assert scraper._should_fetch_replies(post) is False


def test_extract_reply_count_from_trailing_nums(scraper):
    """trailing 숫자의 두 번째 값이 댓글 수(reply count)로 추출된다."""
    # 좋아요: 45, 댓글: 3, 리포스트: 6, 공유: 16
    raw = "본문 내용입니다\n45\n3\n6\n16"
    assert scraper._extract_reply_count(raw) == 3


def test_extract_reply_count_zero_when_insufficient_nums(scraper):
    """trailing 숫자가 2개 미만이면 0을 반환한다."""
    raw = "본문만 있는 포스트\n45"
    assert scraper._extract_reply_count(raw) == 0


def test_extract_reply_count_no_nums(scraper):
    """숫자가 전혀 없으면 0을 반환한다."""
    raw = "숫자 없는 본문"
    assert scraper._extract_reply_count(raw) == 0


def test_extract_reply_count_with_comma_format(scraper):
    """쉼표 포함 숫자(1,234)도 정상 파싱한다."""
    raw = "본문\n1,234\n56\n7\n8"
    assert scraper._extract_reply_count(raw) == 56


def test_reply_count_roundtrip_serialization():
    """reply_count가 to_dict/from_dict 왕복 변환에서 보존된다."""
    post = ThreadPost(
        post_id="x", author="a", text="t",
        url="u", saved_at=datetime.now(), reply_count=5,
    )
    restored = ThreadPost.from_dict(post.to_dict())
    assert restored.reply_count == 5
