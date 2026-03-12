"""병렬 self-reply 수집(concurrent detail fetching) 테스트.

async_scraper 모듈의 clean_text, enrich_with_replies_async,
그리고 _try_async_enrich 폴백 동작을 검증한다.
실제 Threads 접속 없이 mock 데이터만 사용한다.
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# 프로젝트 루트를 sys.path에 추가
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.collector.async_scraper import clean_text, enrich_with_replies_async
from src.collector.threads_scraper import ThreadPost, ThreadsScraper


# ------------------------------------------------------------------
# fixture
# ------------------------------------------------------------------

@pytest.fixture
def scraper() -> ThreadsScraper:
    """AuthManager 없이 ThreadsScraper 인스턴스를 생성한다."""
    return ThreadsScraper(auth_manager=None)


def _make_post(
    post_id: str = "abc123",
    author: str = "user1",
    text: str = "본문 텍스트",
    url: str = "https://www.threads.com/@user1/post/abc123",
    reply_count: int = 2,
) -> ThreadPost:
    """테스트용 ThreadPost를 생성하는 헬퍼(helper)."""
    return ThreadPost(
        post_id=post_id,
        author=author,
        text=text,
        url=url,
        saved_at=datetime.now(),
        reply_count=reply_count,
    )


# ------------------------------------------------------------------
# clean_text 단위 테스트
# ------------------------------------------------------------------

class TestCleanText:
    """clean_text 함수 검증."""

    def test_removes_author_name(self):
        """작성자명을 제거한다."""
        raw = "user1\n실제 본문"
        assert clean_text(raw, "user1") == "실제 본문"

    def test_removes_engagement_numbers(self):
        """순수 숫자(engagement count)를 제거한다."""
        raw = "본문 내용\n45\n3\n6"
        assert clean_text(raw, "author") == "본문 내용"

    def test_removes_timestamp_patterns(self):
        """타임스탬프(timestamp) 패턴을 제거한다."""
        raw = "2h\n1d\n3m\n본문"
        assert clean_text(raw, "author") == "본문"

    def test_removes_date_patterns(self):
        """날짜(date) 패턴을 제거한다."""
        raw = "12/01/25\n본문"
        assert clean_text(raw, "author") == "본문"

    def test_removes_noise_tokens(self):
        """UI 노이즈(noise) 토큰을 제거한다."""
        raw = "Translate\nLike\nReply\n실제 텍스트"
        assert clean_text(raw, "author") == "실제 텍스트"

    def test_preserves_normal_text(self):
        """일반 텍스트는 보존한다."""
        raw = "Playwright 사용법 정리\nlocalhost:3000 포트"
        result = clean_text(raw, "author")
        assert "Playwright 사용법 정리" in result
        assert "localhost:3000 포트" in result

    def test_removes_empty_lines(self):
        """빈 줄을 제거한다."""
        raw = "첫 줄\n\n\n둘째 줄"
        result = clean_text(raw, "author")
        assert result == "첫 줄\n둘째 줄"

    def test_empty_input(self):
        """빈 입력에 대해 빈 문자열을 반환한다."""
        assert clean_text("", "author") == ""

    def test_comma_numbers_removed(self):
        """쉼표 포함 숫자(1,234)도 제거한다."""
        raw = "본문\n1,234"
        assert clean_text(raw, "author") == "본문"


# ------------------------------------------------------------------
# enrich_with_replies_async mock 테스트
# ------------------------------------------------------------------

class TestEnrichAsync:
    """enrich_with_replies_async 함수 검증."""

    def test_skips_when_no_candidates(self):
        """reply_count == 0인 포스트만 있으면 수집을 건너뛴다."""
        posts = [_make_post(reply_count=0)]
        result = asyncio.run(
            enrich_with_replies_async(posts, [], "ua"),
        )
        assert result == posts
        assert result[0].replies == []

    def test_skips_when_no_url(self):
        """URL이 없는 포스트는 건너뛴다."""
        posts = [_make_post(url="", reply_count=3)]
        result = asyncio.run(
            enrich_with_replies_async(posts, [], "ua"),
        )
        assert result[0].replies == []

    @patch("src.collector.async_scraper.async_playwright")
    def test_opens_browser_for_candidates(self, mock_pw):
        """후보가 있으면 브라우저(browser)를 열어야 한다."""
        # async_playwright context manager mock 구성
        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_page = AsyncMock()

        # page.query_selector_all이 빈 리스트 반환 (reply 없음)
        mock_page.query_selector_all = AsyncMock(return_value=[])
        mock_page.goto = AsyncMock()
        mock_page.close = AsyncMock()

        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.add_cookies = AsyncMock()

        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.close = AsyncMock()

        mock_pw_instance = AsyncMock()
        mock_pw_instance.chromium.launch = AsyncMock(
            return_value=mock_browser,
        )
        mock_pw_instance.__aenter__ = AsyncMock(
            return_value=mock_pw_instance,
        )
        mock_pw_instance.__aexit__ = AsyncMock(return_value=False)
        mock_pw.return_value = mock_pw_instance

        posts = [_make_post(reply_count=2)]
        asyncio.run(
            enrich_with_replies_async(posts, [{"name": "c"}], "ua"),
        )

        # 브라우저 launch 호출 확인
        mock_pw_instance.chromium.launch.assert_awaited_once()
        mock_context.add_cookies.assert_awaited_once()

    @patch("src.collector.async_scraper.async_playwright")
    def test_handles_page_error_gracefully(self, mock_pw):
        """페이지 로드 에러 시에도 예외 없이 완료되어야 한다."""
        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_page = AsyncMock()

        # goto에서 예외(exception) 발생
        mock_page.goto = AsyncMock(side_effect=TimeoutError("timeout"))
        mock_page.close = AsyncMock()

        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.add_cookies = AsyncMock()

        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.close = AsyncMock()

        mock_pw_instance = AsyncMock()
        mock_pw_instance.chromium.launch = AsyncMock(
            return_value=mock_browser,
        )
        mock_pw_instance.__aenter__ = AsyncMock(
            return_value=mock_pw_instance,
        )
        mock_pw_instance.__aexit__ = AsyncMock(return_value=False)
        mock_pw.return_value = mock_pw_instance

        posts = [_make_post(reply_count=1)]
        # 예외 없이 완료되어야 함
        result = asyncio.run(
            enrich_with_replies_async(posts, [], "ua"),
        )
        assert result[0].replies == []


# ------------------------------------------------------------------
# _try_async_enrich 폴백(fallback) 테스트
# ------------------------------------------------------------------

class TestTryAsyncEnrich:
    """_try_async_enrich 메서드의 폴백 동작 검증."""

    def test_returns_false_on_import_error(self, scraper):
        """async 모듈 임포트 실패 시 False를 반환한다."""
        mock_page = MagicMock()
        mock_page.context.cookies.return_value = []

        with patch(
            "src.collector.async_scraper.enrich_with_replies_async",
            side_effect=ImportError("no module"),
        ):
            result = scraper._try_async_enrich(mock_page, [])
            assert result is False

    def test_returns_false_on_runtime_error(self, scraper):
        """asyncio.run 실행 중 에러 시 False를 반환한다."""
        mock_page = MagicMock()
        mock_page.context.cookies.return_value = []

        with patch(
            "src.collector.async_scraper.enrich_with_replies_async",
            side_effect=RuntimeError("event loop"),
        ):
            result = scraper._try_async_enrich(mock_page, [])
            assert result is False

    def test_returns_true_on_success(self, scraper):
        """정상 실행 시 True를 반환한다."""
        mock_page = MagicMock()
        mock_page.context.cookies.return_value = []

        async def _noop(posts, cookies, ua):
            return posts

        with patch(
            "src.collector.async_scraper.enrich_with_replies_async",
            side_effect=_noop,
        ):
            result = scraper._try_async_enrich(mock_page, [])
            assert result is True


# ------------------------------------------------------------------
# _enrich_with_replies 통합(integration) 검증
# ------------------------------------------------------------------

class TestEnrichWithReplies:
    """_enrich_with_replies 메서드의 분기 동작 검증."""

    def test_returns_early_when_no_candidates(self, scraper):
        """후보가 없으면 즉시 반환한다."""
        posts = [_make_post(reply_count=0)]
        mock_page = MagicMock()
        result = scraper._enrich_with_replies(mock_page, posts)
        assert result == posts

    def test_falls_back_to_sequential(self, scraper):
        """병렬 실패 시 순차(sequential) 수집으로 폴백한다."""
        posts = [_make_post(reply_count=1)]
        mock_page = MagicMock()

        with patch.object(
            scraper, "_try_async_enrich", return_value=False,
        ), patch.object(
            scraper, "_enrich_sequential", return_value=posts,
        ) as mock_seq:
            result = scraper._enrich_with_replies(mock_page, posts)
            mock_seq.assert_called_once()
            assert result == posts

    def test_skips_sequential_on_async_success(self, scraper):
        """병렬 성공 시 순차 수집을 건너뛴다."""
        posts = [_make_post(reply_count=1)]
        mock_page = MagicMock()

        with patch.object(
            scraper, "_try_async_enrich", return_value=True,
        ), patch.object(
            scraper, "_enrich_sequential",
        ) as mock_seq:
            scraper._enrich_with_replies(mock_page, posts)
            mock_seq.assert_not_called()
