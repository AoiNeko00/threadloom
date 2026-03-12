"""셀렉터 맵(Selector Map) 로더.

selectors.yaml을 읽어 CSS 셀렉터를 제공한다.
Threads UI 변경 시 YAML 파일만 수정하면 된다.
"""

from pathlib import Path
from typing import Any

import yaml

from src.utils.i18n import t
from src.utils.logger import get_logger

_logger = get_logger("collector.selectors")

_SELECTOR_FILE = Path(__file__).resolve().parent / "selectors.yaml"

# 캐시(cache) — 모듈 레벨 싱글턴
_cache: dict[str, Any] | None = None


def _load() -> dict[str, Any]:
    """selectors.yaml을 로드한다."""
    global _cache
    if _cache is not None:
        return _cache
    if not _SELECTOR_FILE.exists():
        _logger.error(t("util.selectors_missing", path=str(_SELECTOR_FILE)))
        return _defaults()
    with open(_SELECTOR_FILE, encoding="utf-8") as f:
        _cache = yaml.safe_load(f) or {}
    return _cache


def _defaults() -> dict[str, Any]:
    """파일 없을 때 fallback 기본값."""
    return {
        "post_containers": [
            "[data-pressable-container]",
            "[data-testid='post-container']",
            "article",
        ],
        "author_link": "a[href*='/@']",
        "post_link": "a[href*='/post/']",
        "media": {"image": "img[src]", "video": "video source[src]"},
        "noise_tokens": [
            "Translate", "Like", "Reply", "Repost", "Share",
            "Follow", "Edited", "Author", "·", "Loading...",
        ],
    }


def post_containers() -> list[str]:
    """포스트 컨테이너(post container) 셀렉터 목록을 반환한다."""
    return _load().get("post_containers", _defaults()["post_containers"])


def author_link() -> str:
    """작성자(author) 링크 셀렉터를 반환한다."""
    return _load().get("author_link", "a[href*='/@']")


def post_link() -> str:
    """포스트 URL 링크 셀렉터를 반환한다."""
    return _load().get("post_link", "a[href*='/post/']")


def media_image() -> str:
    """이미지(image) 미디어 셀렉터를 반환한다."""
    return _load().get("media", {}).get("image", "img[src]")


def media_video() -> str:
    """비디오(video) 미디어 셀렉터를 반환한다."""
    return _load().get("media", {}).get("video", "video source[src]")


def noise_tokens() -> set[str]:
    """UI 노이즈(noise) 토큰 세트를 반환한다."""
    tokens = _load().get("noise_tokens", _defaults()["noise_tokens"])
    return set(tokens)


def reload() -> None:
    """캐시를 초기화하여 다음 호출 시 파일을 다시 읽는다 (테스트용)."""
    global _cache
    _cache = None
