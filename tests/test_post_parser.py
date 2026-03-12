"""포스트 파서(post parser) 테스트.

extract_external_urls 함수의 URL 추출 및 필터링을 검증한다.
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.collector.post_parser import extract_external_urls


# ------------------------------------------------------------------
# 정상 추출
# ------------------------------------------------------------------

def test_extract_single_url():
    """단일 외부 URL을 추출한다."""
    text = "이 글 참고하세요 https://example.com/article"
    urls = extract_external_urls(text)
    assert urls == ["https://example.com/article"]


def test_extract_multiple_urls():
    """여러 외부 URL을 추출한다."""
    text = (
        "링크1 https://example.com/a "
        "링크2 https://blog.dev/b "
        "링크3 https://docs.io/c"
    )
    urls = extract_external_urls(text, max_links=5)
    assert len(urls) == 3


def test_extract_respects_max_links():
    """max_links 제한을 준수한다."""
    text = (
        "https://a.com https://b.com "
        "https://c.com https://d.com"
    )
    urls = extract_external_urls(text, max_links=2)
    assert len(urls) == 2


# ------------------------------------------------------------------
# 내부(internal) URL 필터링
# ------------------------------------------------------------------

def test_excludes_threads_urls():
    """Threads 내부 URL을 제외한다."""
    text = "https://www.threads.net/@user/post/123 https://example.com/ext"
    urls = extract_external_urls(text)
    assert len(urls) == 1
    assert "example.com" in urls[0]


def test_excludes_instagram_urls():
    """Instagram 내부 URL을 제외한다."""
    text = "https://www.instagram.com/p/abc https://example.com/ext"
    urls = extract_external_urls(text)
    assert len(urls) == 1
    assert "example.com" in urls[0]


def test_excludes_twitter_urls():
    """Twitter/X 내부 URL을 제외한다."""
    text = "https://twitter.com/user https://x.com/user https://example.com/ext"
    urls = extract_external_urls(text)
    assert len(urls) == 1
    assert "example.com" in urls[0]


def test_excludes_facebook_urls():
    """Facebook 내부 URL을 제외한다."""
    text = "https://www.facebook.com/page https://example.com/ext"
    urls = extract_external_urls(text)
    assert len(urls) == 1


# ------------------------------------------------------------------
# 중복 제거
# ------------------------------------------------------------------

def test_deduplicates_urls():
    """동일 URL 중복을 제거한다."""
    text = "https://example.com/a https://example.com/a https://example.com/a"
    urls = extract_external_urls(text)
    assert len(urls) == 1


# ------------------------------------------------------------------
# 엣지 케이스
# ------------------------------------------------------------------

def test_no_urls_returns_empty():
    """URL이 없으면 빈 리스트를 반환한다."""
    text = "URL 없는 일반 텍스트"
    urls = extract_external_urls(text)
    assert urls == []


def test_only_internal_urls_returns_empty():
    """내부 URL만 있으면 빈 리스트를 반환한다."""
    text = "https://www.threads.net/@user/post/123 https://instagram.com/p/abc"
    urls = extract_external_urls(text)
    assert urls == []
