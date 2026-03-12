"""self-reply(이어쓰기) 수집 모듈.

포스트 상세 페이지에서 동일 작성자의 연속 댓글을 수집한다.
"""

import random
import time

from playwright.sync_api import Page

from src.collector import selector_map
from src.collector.models import ThreadPost
from src.collector.post_parser import clean_post_text, extract_author, query_elements
from src.utils.i18n import t
from src.utils.logger import get_logger

_SCROLL_DELAY_MIN: float = 1.0
_SCROLL_DELAY_MAX: float = 3.0

_logger = get_logger("collector.reply")


def should_fetch_replies(post: ThreadPost) -> bool:
    """상세 페이지 진입이 필요한지 판단한다."""
    return post.reply_count > 0


def enrich_with_replies(
    page: Page,
    posts: list[ThreadPost],
    get_user_agent: callable,
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
    if try_async_enrich(page, posts, get_user_agent):
        return posts

    # 폴백: 기존 순차(sequential) 수집
    return enrich_sequential(page, posts, candidates)


def try_async_enrich(
    page: Page,
    posts: list[ThreadPost],
    get_user_agent: callable,
) -> bool:
    """병렬(async) self-reply 수집을 시도한다. 성공 시 True.

    Playwright sync API가 이벤트 루프(event loop)를 점유하므로,
    별도 스레드(thread)에서 새 루프를 생성하여 async 수집을 실행한다.
    """
    try:
        import asyncio
        import concurrent.futures

        from src.collector.async_scraper import enrich_with_replies_async

        # sync context에서 쿠키(cookie) 추출
        cookies = page.context.cookies()
        user_agent = get_user_agent()

        def _run_in_thread() -> list[ThreadPost]:
            """별도 스레드에서 새 이벤트 루프를 생성하여 async 수집 실행."""
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(
                    enrich_with_replies_async(posts, cookies, user_agent),
                )
            finally:
                loop.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_run_in_thread)
            future.result(timeout=300)  # 5분 타임아웃

        return True
    except Exception as exc:
        _logger.warning(
            t("collector.async_fail", err=type(exc).__name__),
        )
        return False


def enrich_sequential(
    page: Page,
    posts: list[ThreadPost],
    candidates: list[ThreadPost],
) -> list[ThreadPost]:
    """기존 순차(sequential) 방식으로 self-reply를 수집한다."""
    for post in candidates:
        replies = fetch_self_replies(page, post)
        if replies:
            post.replies = replies
            # 본문 + self-reply를 합쳐서 전체 텍스트 구성
            full_parts = [post.text] + replies
            post.text = "\n\n---\n\n".join(full_parts)
            _logger.debug(
                "%s: self-reply %d건 합침", post.post_id[:8], len(replies),
            )
    return posts


def fetch_self_replies(
    page: Page, post: ThreadPost,
) -> list[str]:
    """포스트 상세 페이지에서 동일 작성자의 이어쓰기를 추출한다."""
    replies: list[str] = []
    try:
        page.goto(post.url, wait_until="domcontentloaded", timeout=15000)
        time.sleep(random.uniform(_SCROLL_DELAY_MIN, _SCROLL_DELAY_MAX))

        reply_elements = query_elements(
            page, selector_map.post_containers(),
        )

        # 첫 번째는 본문(이미 수집됨), 이후부터 확인
        for el in reply_elements[1:]:
            reply_author = extract_reply_author(el)
            if reply_author != post.author:
                break  # 다른 사람 댓글이 나오면 중단
            raw_reply = (el.inner_text() or "")
            reply_text = clean_post_text(raw_reply, post.author)
            if reply_text:
                replies.append(reply_text)

    except Exception as exc:
        _logger.debug(
            "self-reply 수집 실패 (%s): %s",
            post.post_id[:8], type(exc).__name__,
        )
    finally:
        # 저장 페이지로 복귀
        page.go_back(wait_until="domcontentloaded", timeout=15000)

    return replies


def extract_reply_author(element) -> str:
    """댓글 요소에서 작성자명을 추출한다."""
    author_el = element.query_selector(selector_map.author_link())
    return extract_author(author_el)
