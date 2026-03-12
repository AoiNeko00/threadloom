"""병렬 상세 수집(concurrent detail fetching) 모듈.

Playwright asyncio 모드로 self-reply 상세 페이지를 동시에 방문하여
수집 속도를 크게 개선한다.
"""

import asyncio
import random
import re

from playwright.async_api import (
    BrowserContext as AsyncBrowserContext,
    async_playwright,
)

from src.collector.models import ThreadPost
from src.utils.i18n import t
from src.utils.logger import get_logger

_logger = get_logger("collector.async_scraper")

# 동시 접근(concurrency) 제한 — 너무 많으면 봇 감지 위험
_MAX_CONCURRENT = 3
_SCROLL_DELAY_MIN = 1.0
_SCROLL_DELAY_MAX = 3.0


async def enrich_with_replies_async(
    posts: list[ThreadPost],
    cookies: list[dict],
    user_agent: str,
) -> list[ThreadPost]:
    """Playwright async 모드로 self-reply를 병렬 수집한다.

    Args:
        posts: 기본 수집이 완료된 포스트 목록
        cookies: 인증 쿠키(auth cookies) (sync context에서 추출)
        user_agent: 브라우저 User-Agent

    Returns:
        self-reply가 보강된 포스트 목록
    """
    candidates = [p for p in posts if p.url and p.reply_count > 0]
    if not candidates:
        return posts

    _logger.info(
        t("collector.async_start",
          n=len(candidates), concurrent=_MAX_CONCURRENT),
    )

    semaphore = asyncio.Semaphore(_MAX_CONCURRENT)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=user_agent)
        await context.add_cookies(cookies)

        tasks = [
            _fetch_one(context, post, semaphore)
            for post in candidates
        ]
        await asyncio.gather(*tasks)

        await browser.close()

    _logger.info(t("collector.async_done"))
    return posts


async def _fetch_one(
    context: AsyncBrowserContext,
    post: ThreadPost,
    semaphore: asyncio.Semaphore,
) -> None:
    """단일 포스트의 self-reply를 비동기로 수집한다."""
    async with semaphore:
        page = await context.new_page()
        try:
            await page.goto(
                post.url, wait_until="domcontentloaded", timeout=15000,
            )
            delay = random.uniform(_SCROLL_DELAY_MIN, _SCROLL_DELAY_MAX)
            await asyncio.sleep(delay)

            replies = await _extract_replies(page, post)
            if replies:
                post.replies = replies
                full_parts = [post.text] + replies
                post.text = "\n\n---\n\n".join(full_parts)
                _logger.debug(
                    "%s: self-reply %d건 합침",
                    post.post_id[:8], len(replies),
                )
        except Exception as exc:
            _logger.debug(
                "async self-reply 수집 실패 (%s): %s",
                post.post_id[:8], type(exc).__name__,
            )
        finally:
            await page.close()


async def _extract_replies(page, post: ThreadPost) -> list[str]:
    """상세 페이지에서 동일 작성자의 연속 댓글(self-reply)을 추출한다."""
    from src.collector import selector_map

    replies: list[str] = []
    containers = selector_map.post_containers()

    elements = []
    for sel in containers:
        elements = await page.query_selector_all(sel)
        if elements:
            break

    # 첫 번째는 본문(이미 수집됨), 이후부터 확인
    for el in elements[1:]:
        author_el = await el.query_selector(selector_map.author_link())
        reply_author = await _extract_author_async(author_el)
        if reply_author != post.author:
            break  # 다른 사람 댓글이 나오면 중단
        raw = await el.inner_text() or ""
        cleaned = clean_text(raw, post.author)
        if cleaned:
            replies.append(cleaned)

    return replies


async def _extract_author_async(element) -> str:
    """비동기(async) 요소에서 작성자명을 추출한다."""
    if element is None:
        return "unknown"
    href = await element.get_attribute("href") or ""
    if "/@" in href:
        return href.split("/@")[-1].split("/")[0].split("?")[0]
    text = await element.inner_text()
    return (text or "").strip() or "unknown"


def clean_text(raw: str, author: str) -> str:
    """raw 텍스트에서 UI 노이즈(noise)를 제거한다."""
    from src.collector import selector_map

    noise = selector_map.noise_tokens()
    lines = raw.split("\n")
    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped == author or stripped in noise:
            continue
        # 순수 숫자(engagement count) 제거
        if re.fullmatch(r"\d[\d,.]*", stripped):
            continue
        # 타임스탬프(timestamp) 패턴 제거
        if re.fullmatch(r"\d+[dhms]", stripped):
            continue
        if re.fullmatch(r"\d{1,2}/\d{2}/\d{2,4}", stripped):
            continue
        cleaned.append(stripped)
    return "\n".join(cleaned)
