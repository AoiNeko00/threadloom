"""외부 링크(external link) 텍스트 크롤링 모듈.

포스트 본문에 포함된 외부 URL의 제목과 본문 텍스트를 추출한다.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from src.collector.models import ThreadPost
from src.collector.post_parser import extract_external_urls
from src.utils.i18n import t
from src.utils.logger import get_logger

_logger = get_logger("collector.link_fetcher")

_MAX_TEXT_LENGTH: int = 3000

# 차단(block) 대상 도메인 — SNS 및 로그인 필요 사이트
_BLOCKED_DOMAINS: set[str] = {
    "instagram.com", "www.instagram.com",
    "threads.net", "www.threads.net",
    "threads.com", "www.threads.com",
    "twitter.com", "www.twitter.com",
    "x.com", "www.x.com",
    "facebook.com", "www.facebook.com",
    "m.facebook.com",
}

_USER_AGENT: str = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


def fetch_link_text(url: str, timeout: int = 10) -> dict | None:
    """단일 URL에서 제목(title)과 본문 텍스트를 추출한다.

    Returns:
        {"url": ..., "title": ..., "text": ...} 또는 실패 시 None
    """
    try:
        resp = requests.get(
            url, timeout=timeout,
            headers={"User-Agent": _USER_AGENT},
            allow_redirects=True,
        )
        resp.raise_for_status()
    except (requests.RequestException, Exception) as err:
        _logger.debug(t("link.fetch_error", url=url, err=str(err)))
        return None

    content_type = resp.headers.get("Content-Type", "")
    if "text/html" not in content_type:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    title = _extract_title(soup)
    text = _extract_main_text(soup)

    if not text:
        return None

    return {"url": url, "title": title, "text": text}


def _extract_title(soup: BeautifulSoup) -> str:
    """HTML에서 페이지 제목(title)을 추출한다."""
    tag = soup.find("title")
    if tag and tag.string:
        return tag.string.strip()
    return ""


def _extract_main_text(soup: BeautifulSoup) -> str:
    """HTML에서 메인 텍스트(main text)를 추출한다.

    <article> -> <main> -> <body> 순서로 탐색하고,
    <p> 태그 텍스트를 우선 수집한다.
    """
    # 스크립트(script), 스타일(style) 제거
    for tag in soup.find_all(["script", "style", "nav", "footer"]):
        tag.decompose()

    container = (
        soup.find("article")
        or soup.find("main")
        or soup.find("body")
    )
    if container is None:
        return ""

    paragraphs = container.find_all("p")
    if paragraphs:
        text = "\n".join(p.get_text(strip=True) for p in paragraphs)
    else:
        text = container.get_text(separator="\n", strip=True)

    return text[:_MAX_TEXT_LENGTH]


def fetch_links_for_posts(
    posts: list[ThreadPost],
    max_links: int = 3,
    timeout: int = 10,
    blocked_domains: set[str] | None = None,
) -> None:
    """포스트 목록의 외부 링크를 병렬(parallel)로 수집한다.

    각 포스트의 link_contents 필드에 결과를 저장한다.
    """
    blocked = blocked_domains or _BLOCKED_DOMAINS

    # (포스트, URL) 쌍 수집
    tasks: list[tuple[ThreadPost, str]] = []
    for post in posts:
        urls = extract_external_urls(post.text, max_links)
        urls = _filter_blocked(urls, blocked)
        for url in urls:
            tasks.append((post, url))

    if not tasks:
        return

    _logger.info(t("link.fetching_start", n=len(tasks)))
    success = 0
    fail = 0

    with ThreadPoolExecutor(max_workers=5) as executor:
        future_map = {
            executor.submit(fetch_link_text, url, timeout): (post, url)
            for post, url in tasks
        }
        for future in as_completed(future_map):
            post, url = future_map[future]
            try:
                result = future.result()
                if result:
                    post.link_contents.append(result)
                    success += 1
                else:
                    fail += 1
            except Exception:
                fail += 1

    _logger.info(t("link.fetched", success=success, fail=fail))


def _filter_blocked(urls: list[str], blocked: set[str]) -> list[str]:
    """차단 도메인(blocked domain) URL을 필터링한다."""
    result: list[str] = []
    for url in urls:
        domain = urlparse(url).hostname or ""
        if domain not in blocked:
            result.append(url)
    return result
