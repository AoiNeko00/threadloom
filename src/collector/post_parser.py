"""DOM 파싱(parsing) 로직 모듈.

Playwright 요소(element)에서 포스트 데이터를 추출하는 독립 함수들이다.
"""

import hashlib
import re
from datetime import datetime
from urllib.parse import urlparse

from src.collector import selector_map
from src.collector.models import ThreadPost


def parse_visible_posts(page, selectors: list[str]) -> list[ThreadPost]:
    """현재 화면에 보이는 포스트를 파싱(parsing)한다."""
    posts: list[ThreadPost] = []
    elements = query_elements(page, selectors)

    for el in elements:
        post = parse_single_post(el)
        if post:
            posts.append(post)

    return posts


def parse_single_post(element) -> ThreadPost | None:
    """단일 포스트 요소(element)에서 데이터를 추출한다."""
    try:
        raw_text = element.inner_text() or ""
        # 작성자(author) 추출
        author_el = element.query_selector(selector_map.author_link())
        author = extract_author(author_el)
        # 댓글 수(reply count) 추출 (정제 전 raw 텍스트에서)
        reply_count = extract_reply_count(raw_text)
        # 본문만 추출 (UI 노이즈 제거)
        text = clean_post_text(raw_text, author)
        # URL 추출
        link_el = element.query_selector(selector_map.post_link())
        url = extract_url(link_el)
        post_id = generate_post_id(url, text)
        # 미디어(media) URL 추출
        media_urls = extract_media(element)

        return ThreadPost(
            post_id=post_id,
            author=author,
            text=text.strip(),
            url=url,
            saved_at=datetime.now(),
            media_urls=media_urls,
            reply_count=reply_count,
        )
    except Exception:
        return None


def extract_author(element) -> str:
    """작성자명을 추출한다."""
    if element is None:
        return "unknown"
    href = element.get_attribute("href") or ""
    # /@username 형식에서 추출
    if "/@" in href:
        return href.split("/@")[-1].split("/")[0].split("?")[0]
    return element.inner_text().strip() or "unknown"


def extract_url(element, threads_url: str = "https://www.threads.com") -> str:
    """포스트 URL을 추출한다."""
    if element is None:
        return ""
    href = element.get_attribute("href") or ""
    if href.startswith("/"):
        return f"{threads_url}{href}"
    return href


def extract_media(element) -> list[str]:
    """이미지/비디오 URL을 추출한다."""
    urls: list[str] = []
    for img in element.query_selector_all(selector_map.media_image()):
        src = img.get_attribute("src") or ""
        if src and "profile" not in src.lower():
            urls.append(src)
    for vid in element.query_selector_all(selector_map.media_video()):
        src = vid.get_attribute("src") or ""
        if src:
            urls.append(src)
    return urls


def clean_post_text(raw: str, author: str) -> str:
    """inner_text()에서 UI 노이즈를 제거하고 본문만 추출한다."""
    lines = raw.split("\n")
    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if is_noise_line(stripped, author):
            continue
        cleaned.append(stripped)
    return "\n".join(cleaned)


def is_noise_line(line: str, author: str) -> bool:
    """UI 노이즈(noise) 라인인지 판별한다."""
    # 작성자명, 라벨
    if line == author:
        return True
    # 순수 숫자 (좋아요, 댓글, 리포스트, 공유 수)
    if re.fullmatch(r"\d[\d,.]*", line):
        return True
    # 타임스탬프 패턴 (1d, 2h, 3m, 12/01/25 등)
    if re.fullmatch(r"\d+[dhms]", line):
        return True
    if re.fullmatch(r"\d{1,2}/\d{2}/\d{2,4}", line):
        return True
    # UI 버튼/라벨
    if line in selector_map.noise_tokens():
        return True
    return False


def extract_reply_count(raw_text: str) -> int:
    """raw 텍스트에서 댓글 수(reply count)를 추출한다.

    inner_text()의 trailing 숫자 라인이 engagement counts
    (좋아요, 댓글, 리포스트, 공유 순)라고 가정하고,
    두 번째 숫자를 댓글 수로 사용한다.
    """
    trailing_nums = re.findall(r"^(\d[\d,.]*)$", raw_text, re.MULTILINE)
    if len(trailing_nums) >= 2:
        # 쉼표/점 제거 후 정수 변환
        cleaned = trailing_nums[1].replace(",", "").replace(".", "")
        try:
            return int(cleaned)
        except ValueError:
            return 0
    return 0


def generate_post_id(url: str, text: str) -> str:
    """URL 또는 텍스트 해시(hash)로 post_id를 생성한다."""
    source = url if url else text[:200]
    return hashlib.sha256(source.encode()).hexdigest()[:16]


def query_elements(page, selectors: list[str]) -> list:
    """여러 선택자를 순서대로 시도하여 요소를 반환한다."""
    for selector in selectors:
        elements = page.query_selector_all(selector)
        if elements:
            return elements
    return []


# SNS 내부(internal) URL 도메인 — 외부 링크 추출 시 제외
_INTERNAL_DOMAINS: set[str] = {
    "instagram.com", "www.instagram.com",
    "threads.net", "www.threads.net",
    "threads.com", "www.threads.com",
    "twitter.com", "www.twitter.com",
    "x.com", "www.x.com",
    "facebook.com", "www.facebook.com",
    "m.facebook.com",
}


def extract_external_urls(text: str, max_links: int = 3) -> list[str]:
    """본문에서 외부 URL(external URL)을 추출한다.

    SNS 내부 링크는 제외하고 최대 max_links개까지 반환한다.
    """
    raw_urls = re.findall(r"https?://[^\s)>\]\"']+", text)
    seen: set[str] = set()
    result: list[str] = []
    for url in raw_urls:
        if url in seen:
            continue
        seen.add(url)
        domain = urlparse(url).hostname or ""
        if domain in _INTERNAL_DOMAINS:
            continue
        result.append(url)
        if len(result) >= max_links:
            break
    return result
