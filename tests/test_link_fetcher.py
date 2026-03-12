"""외부 링크 크롤링(link fetching) 테스트.

실제 HTTP 요청 없이 mock 데이터만 사용한다.
"""

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.collector.link_fetcher import (
    _extract_main_text,
    _extract_title,
    fetch_link_text,
    fetch_links_for_posts,
)
from src.collector.models import ThreadPost


# ------------------------------------------------------------------
# fixture
# ------------------------------------------------------------------

@pytest.fixture
def sample_html() -> str:
    """테스트용 HTML 문자열을 반환한다."""
    return """
    <html>
    <head><title>테스트 페이지</title></head>
    <body>
    <article>
        <p>첫 번째 단락입니다.</p>
        <p>두 번째 단락입니다.</p>
    </article>
    </body>
    </html>
    """


@pytest.fixture
def sample_post() -> ThreadPost:
    """외부 URL이 포함된 테스트 포스트를 반환한다."""
    return ThreadPost(
        post_id="link01",
        author="user1",
        text="좋은 글 https://example.com/article 참고하세요",
        url="https://threads.net/@user1/post/link01",
        saved_at=datetime(2026, 3, 12, 10, 0),
    )


# ------------------------------------------------------------------
# fetch_link_text 정상 케이스
# ------------------------------------------------------------------

@patch("src.collector.link_fetcher.requests.get")
def test_fetch_link_text_success(mock_get, sample_html):
    """정상 HTML 응답 시 title과 text를 추출한다."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = sample_html
    mock_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    result = fetch_link_text("https://example.com/article")
    assert result is not None
    assert result["url"] == "https://example.com/article"
    assert result["title"] == "테스트 페이지"
    assert "첫 번째 단락" in result["text"]


# ------------------------------------------------------------------
# fetch_link_text 타임아웃(timeout) 케이스
# ------------------------------------------------------------------

@patch("src.collector.link_fetcher.requests.get")
def test_fetch_link_text_timeout(mock_get):
    """타임아웃 발생 시 None을 반환한다."""
    import requests
    mock_get.side_effect = requests.Timeout("timeout")

    result = fetch_link_text("https://example.com/slow", timeout=1)
    assert result is None


# ------------------------------------------------------------------
# fetch_link_text 에러 케이스
# ------------------------------------------------------------------

@patch("src.collector.link_fetcher.requests.get")
def test_fetch_link_text_http_error(mock_get):
    """HTTP 에러(404 등) 시 None을 반환한다."""
    import requests
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = requests.HTTPError("404")
    mock_get.return_value = mock_resp

    result = fetch_link_text("https://example.com/missing")
    assert result is None


@patch("src.collector.link_fetcher.requests.get")
def test_fetch_link_text_non_html(mock_get):
    """HTML이 아닌 Content-Type이면 None을 반환한다."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"Content-Type": "application/pdf"}
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    result = fetch_link_text("https://example.com/file.pdf")
    assert result is None


# ------------------------------------------------------------------
# _extract_title / _extract_main_text 단위 테스트
# ------------------------------------------------------------------

def test_extract_title_from_html():
    """<title> 태그에서 제목을 추출한다."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup("<html><head><title>My Title</title></head></html>", "html.parser")
    assert _extract_title(soup) == "My Title"


def test_extract_title_missing():
    """<title> 태그가 없으면 빈 문자열을 반환한다."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup("<html><head></head></html>", "html.parser")
    assert _extract_title(soup) == ""


def test_extract_main_text_from_article():
    """<article> 내 <p> 태그 텍스트를 우선 추출한다."""
    from bs4 import BeautifulSoup
    html = "<html><body><article><p>본문1</p><p>본문2</p></article></body></html>"
    soup = BeautifulSoup(html, "html.parser")
    text = _extract_main_text(soup)
    assert "본문1" in text
    assert "본문2" in text


def test_extract_main_text_fallback_to_body():
    """<article>과 <main>이 없으면 <body>에서 추출한다."""
    from bs4 import BeautifulSoup
    html = "<html><body><p>바디 텍스트</p></body></html>"
    soup = BeautifulSoup(html, "html.parser")
    text = _extract_main_text(soup)
    assert "바디 텍스트" in text


def test_extract_main_text_max_length():
    """추출된 텍스트는 3000자를 초과하지 않는다."""
    from bs4 import BeautifulSoup
    long_p = "<p>" + "가" * 5000 + "</p>"
    html = f"<html><body>{long_p}</body></html>"
    soup = BeautifulSoup(html, "html.parser")
    text = _extract_main_text(soup)
    assert len(text) <= 3000


# ------------------------------------------------------------------
# fetch_links_for_posts 병렬 수집 테스트
# ------------------------------------------------------------------

@patch("src.collector.link_fetcher.fetch_link_text")
def test_fetch_links_for_posts_populates_link_contents(
    mock_fetch, sample_post,
):
    """포스트의 link_contents에 수집 결과가 저장된다."""
    mock_fetch.return_value = {
        "url": "https://example.com/article",
        "title": "예제",
        "text": "본문 텍스트",
    }

    fetch_links_for_posts([sample_post], max_links=3, timeout=5)
    assert len(sample_post.link_contents) == 1
    assert sample_post.link_contents[0]["title"] == "예제"


@patch("src.collector.link_fetcher.fetch_link_text")
def test_fetch_links_for_posts_handles_failure(mock_fetch, sample_post):
    """크롤링 실패 시 link_contents는 비어 있다."""
    mock_fetch.return_value = None

    fetch_links_for_posts([sample_post], max_links=3, timeout=5)
    assert len(sample_post.link_contents) == 0


@patch("src.collector.link_fetcher.fetch_link_text")
def test_fetch_links_skips_posts_without_urls(mock_fetch):
    """외부 URL이 없는 포스트는 건너뛴다."""
    post = ThreadPost(
        post_id="no_url",
        author="user1",
        text="URL이 없는 일반 텍스트",
        url="https://threads.net/@user1/post/no_url",
        saved_at=datetime(2026, 3, 12, 10, 0),
    )

    fetch_links_for_posts([post], max_links=3, timeout=5)
    mock_fetch.assert_not_called()
    assert len(post.link_contents) == 0
