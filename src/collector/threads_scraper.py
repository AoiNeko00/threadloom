"""Threads 저장 포스트(saved posts) 수집 모듈.

Playwright 기반 브라우저 자동화로 Threads 저장 포스트를 스크래핑한다.
playwright-stealth를 적용하여 봇 탐지(bot detection)를 우회한다.

Threads 특성상 본문 뒤에 작성자가 self-reply로 이어쓰기(thread)하므로,
포스트 상세 페이지에 진입하여 동일 작성자의 연속 댓글을 함께 수집한다.
"""

import random
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page, sync_playwright
from playwright_stealth import Stealth

from src.collector import selector_map
from src.collector.auth_manager import AuthExpiredError, AuthManager
from src.collector.checkpoint import (
    cleanup_checkpoint,
    find_checkpoint,
    load_checkpoint,
    save_checkpoint,
)
from src.collector.models import ThreadPost
from src.collector.post_parser import (
    clean_post_text,
    extract_reply_count,
    generate_post_id,
    parse_visible_posts,
)
from src.collector.raw_writer import format_post_md, write_raw_md
from src.collector.reply_collector import should_fetch_replies
from src.utils.i18n import t
from src.utils.logger import get_logger

# 프로젝트 루트(project root)
_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
_RAW_DIR: Path = _PROJECT_ROOT / "data" / "raw"

_THREADS_URL: str = "https://www.threads.com"
_SCROLL_DELAY_MIN: float = 1.0
_SCROLL_DELAY_MAX: float = 3.0
_MAX_SCROLL_ATTEMPTS: int = 30

_logger = get_logger("collector.scraper")


class ThreadsScraper:
    """Threads 저장 포스트 수집기(scraper).

    Playwright headless 브라우저로 저장 포스트를 수집하고
    raw markdown 파일로 저장한다.
    """

    def __init__(self, auth_manager: AuthManager | None = None) -> None:
        self._auth = auth_manager or AuthManager()

    def collect(
        self,
        since: datetime | None = None,
        seen_ids: set[str] | None = None,
    ) -> Path:
        """Phase 1 전체 실행: 수집 -> 중복 제거 -> seen_ids 필터 -> raw md 저장.

        Args:
            since: 이 시점 이후 포스트만 수집 (None이면 전체)
            seen_ids: 이전 수집에서 본 포스트 ID 집합 (중복 제거용)

        Returns:
            저장된 raw markdown 파일 경로
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 이전 checkpoint(부분 저장) 복원
        resumed_posts: list[ThreadPost] = []
        existing_cp = self._find_checkpoint()
        if existing_cp:
            resumed_posts = self._load_checkpoint(existing_cp)
            _logger.info(
                t("collector.checkpoint_save", n=len(resumed_posts)),
            )

        cp_path = existing_cp or (_RAW_DIR / f".checkpoint_{timestamp}.json")
        posts = self._scrape_saved_posts(since, resumed_posts, cp_path)
        posts = self._deduplicate(posts)

        # seen_ids 기반 신규 포스트 필터링(dedup by seen IDs)
        if seen_ids:
            before = len(posts)
            posts = [p for p in posts if p.post_id not in seen_ids]
            filtered = before - len(posts)
            if filtered > 0:
                _logger.info(t("collector.seen_filtered", n=filtered))

        _logger.info(t("collector.collect_done", n=len(posts)))

        result = self._write_raw_md(posts, timestamp)
        self._cleanup_checkpoint(cp_path)
        return result

    def _scrape_saved_posts(
        self,
        since: datetime | None = None,
        resumed_posts: list[ThreadPost] | None = None,
        checkpoint_path: Path | None = None,
    ) -> list[ThreadPost]:
        """Playwright로 저장 포스트를 수집한다.

        Args:
            since: 이 시점 이후 포스트만 필터링
            resumed_posts: checkpoint에서 복원된 포스트 목록
            checkpoint_path: checkpoint 파일 경로

        Returns:
            수집된 ThreadPost 목록
        """
        posts: list[ThreadPost] = list(resumed_posts or [])

        stealth = Stealth()
        with stealth.use_sync(sync_playwright()) as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=self._get_user_agent(),
            )

            if not self._auth.load_session(context):
                browser.close()
                raise AuthExpiredError(
                    t("collector.session_load_failed")
                )

            page = context.new_page()

            self._navigate_to_saved(page)
            posts = self._extract_posts(page, since, posts, checkpoint_path)

            # 각 포스트 상세 페이지에서 self-reply(이어쓰기) 수집
            posts = self._enrich_with_replies(page, posts)

            # 외부 링크(external link) 텍스트 수집
            self._enrich_with_link_contents(posts)

            browser.close()

        return posts

    def _navigate_to_saved(self, page: Page) -> None:
        """저장 포스트 페이지로 이동한다.

        Threads는 SPA이므로 직접 URL 접근 시 429를 반환할 수 있다.
        메인 페이지 진입 후 SPA 라우트 변경(pushState)으로 이동한다.
        """
        page.goto(
            f"{_THREADS_URL}/", wait_until="domcontentloaded", timeout=15000,
        )

        # 세션 만료(session expired) 감지: 로그인 페이지 리다이렉트
        if "login" in page.url.lower():
            raise AuthExpiredError(
                t("collector.session_expired")
            )

        # 메인 페이지 SPA 로드 대기 후 /saved 라우트로 전환
        time.sleep(3)
        page.evaluate("window.history.pushState({}, '', '/saved/')")
        page.evaluate(
            "window.dispatchEvent(new PopStateEvent('popstate'))",
        )
        time.sleep(3)
        _logger.info(t("collector.nav_done"))

    def _extract_posts(
        self,
        page: Page,
        since: datetime | None,
        existing_posts: list[ThreadPost] | None = None,
        checkpoint_path: Path | None = None,
    ) -> list[ThreadPost]:
        """스크롤하며 포스트를 추출(extract)하고 checkpoint에 저장한다."""
        posts: list[ThreadPost] = list(existing_posts or [])
        prev_count = len(posts)
        no_new_count = 0

        if prev_count > 0:
            _logger.info(
                t("collector.checkpoint_save", n=prev_count),
            )

        try:
            for _ in range(_MAX_SCROLL_ATTEMPTS):
                new_posts = self._parse_visible_posts(page)
                posts = self._merge_posts(posts, new_posts)

                if len(posts) > prev_count and checkpoint_path:
                    self._save_checkpoint(posts, checkpoint_path)
                    _logger.info(t("collector.checkpoint_save", n=len(posts)))

                if len(posts) == prev_count:
                    no_new_count += 1
                    if no_new_count >= 3:
                        break
                else:
                    no_new_count = 0
                    prev_count = len(posts)

                self._scroll_down(page)
        except Exception:
            # 비정상 종료(abnormal exit) 시 현재까지 수집분 저장
            if checkpoint_path:
                self._save_checkpoint(posts, checkpoint_path)
                _logger.info(t("collector.checkpoint_error", n=len(posts)))
            raise

        if since:
            posts = [p for p in posts if p.saved_at > since]

        return posts

    # ------------------------------------------------------------------
    # 위임(delegation) 메서드: 분리된 모듈 함수 호출
    # ------------------------------------------------------------------

    def _parse_visible_posts(self, page: Page) -> list[ThreadPost]:
        """현재 화면에 보이는 포스트를 파싱(parsing)한다."""
        selectors = selector_map.post_containers()
        return parse_visible_posts(page, selectors)

    def _merge_posts(
        self,
        existing: list[ThreadPost],
        new: list[ThreadPost],
    ) -> list[ThreadPost]:
        """기존 목록에 신규 포스트를 병합(merge)한다."""
        seen_ids = {p.post_id for p in existing}
        for post in new:
            if post.post_id not in seen_ids:
                existing.append(post)
                seen_ids.add(post.post_id)
        return existing

    def _scroll_down(self, page: Page) -> None:
        """페이지를 아래로 스크롤한다 (랜덤 딜레이 적용)."""
        page.evaluate("window.scrollBy(0, window.innerHeight)")
        delay = random.uniform(_SCROLL_DELAY_MIN, _SCROLL_DELAY_MAX)
        time.sleep(delay)

    def _deduplicate(self, posts: list[ThreadPost]) -> list[ThreadPost]:
        """post_id 기준으로 중복을 제거한다.

        URL과 post_id를 모두 seen 세트에 등록하여
        checkpoint 복구 시 동일 포스트가 다른 키로 중복되는 것을 방지한다.
        """
        seen_ids: set[str] = set()
        seen_urls: set[str] = set()
        unique: list[ThreadPost] = []
        for post in posts:
            if post.post_id in seen_ids:
                continue
            if post.url and post.url in seen_urls:
                continue
            seen_ids.add(post.post_id)
            if post.url:
                seen_urls.add(post.url)
            unique.append(post)
        return unique

    # -- post_parser 위임 --

    def _clean_post_text(self, raw: str, author: str) -> str:
        """inner_text()에서 UI 노이즈를 제거하고 본문만 추출한다."""
        return clean_post_text(raw, author)

    def _extract_reply_count(self, raw_text: str) -> int:
        """raw 텍스트에서 댓글 수(reply count)를 추출한다."""
        return extract_reply_count(raw_text)

    def _generate_post_id(self, url: str, text: str) -> str:
        """URL 또는 텍스트 해시(hash)로 post_id를 생성한다."""
        return generate_post_id(url, text)

    # -- reply_collector 위임 --

    def _enrich_with_replies(
        self, page: Page, posts: list[ThreadPost],
    ) -> list[ThreadPost]:
        """각 포스트 상세 페이지에서 작성자 self-reply를 수집한다.

        reply_count > 0인 포스트가 있으면 병렬(concurrent) 수집을 시도하고,
        실패 시 기존 순차 수집으로 폴백(fallback)한다.
        """
        candidates = [p for p in posts if p.url and should_fetch_replies(p)]
        _logger.info(
            t("collector.self_reply_candidates",
              candidates=len(candidates), total=len(posts)),
        )

        if not candidates:
            return posts

        # 병렬(async) 수집 시도
        if self._try_async_enrich(page, posts):
            return posts

        # 폴백: 기존 순차(sequential) 수집
        return self._enrich_sequential(page, posts, candidates)

    def _try_async_enrich(
        self, page: Page, posts: list[ThreadPost],
    ) -> bool:
        """병렬(async) self-reply 수집을 시도한다. 성공 시 True."""
        from src.collector.reply_collector import try_async_enrich
        return try_async_enrich(page, posts, self._get_user_agent)

    def _enrich_sequential(
        self,
        page: Page,
        posts: list[ThreadPost],
        candidates: list[ThreadPost],
    ) -> list[ThreadPost]:
        """기존 순차(sequential) 방식으로 self-reply를 수집한다."""
        from src.collector.reply_collector import enrich_sequential
        return enrich_sequential(page, posts, candidates)

    def _should_fetch_replies(self, post: ThreadPost) -> bool:
        """상세 페이지 진입이 필요한지 판단한다."""
        return should_fetch_replies(post)

    # -- raw_writer 위임 --

    def _write_raw_md(
        self, posts: list[ThreadPost], timestamp: str,
    ) -> Path:
        """ThreadPost 목록을 raw markdown 파일로 저장한다."""
        return write_raw_md(posts, timestamp, _RAW_DIR)

    def _format_post_md(self, post: ThreadPost) -> list[str]:
        """단일 포스트를 markdown 블록으로 변환한다."""
        return format_post_md(post)

    # -- checkpoint 위임 --

    def _save_checkpoint(
        self, posts: list[ThreadPost], path: Path,
    ) -> None:
        """현재까지 수집된 포스트를 checkpoint 파일에 저장한다."""
        save_checkpoint(posts, path)

    def _load_checkpoint(self, path: Path) -> list[ThreadPost]:
        """checkpoint 파일에서 포스트 목록을 로드(load)한다."""
        return load_checkpoint(path)

    def _find_checkpoint(self) -> Path | None:
        """가장 최근 checkpoint 파일을 반환한다. 없으면 None."""
        return find_checkpoint(_RAW_DIR)

    def _cleanup_checkpoint(self, path: Path) -> None:
        """정상 완료 시 checkpoint 파일을 삭제한다."""
        cleanup_checkpoint(path)

    # -- link_fetcher 위임 --

    def _enrich_with_link_contents(self, posts: list[ThreadPost]) -> None:
        """포스트 본문의 외부 링크(external link) 텍스트를 수집한다."""
        try:
            from src.config import Config
            cfg = Config()
            enabled = cfg.link_fetching_enabled
            max_links = cfg.max_links_per_post
            timeout = cfg.link_fetch_timeout
        except Exception:
            enabled = True
            max_links = 3
            timeout = 10

        if not enabled:
            _logger.info(t("link.disabled"))
            return

        from src.collector.link_fetcher import fetch_links_for_posts
        fetch_links_for_posts(posts, max_links, timeout)

    # -- 유틸 --

    def _get_user_agent(self) -> str:
        """일반 브라우저 User-Agent 문자열을 반환한다."""
        return (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        )
