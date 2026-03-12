"""YAML frontmatter(프론트매터) 파싱 공통 유틸리티.

md 파일의 frontmatter 분리, 안전한 YAML 로딩, 필드 설정을 담당한다.
"""

import re

import yaml

from src.utils.i18n import t
from src.utils.logger import get_logger

_logger = get_logger("frontmatter")

# frontmatter 경계(boundary) 패턴
_FM_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """텍스트에서 frontmatter dict와 body를 분리한다.

    frontmatter가 없으면 빈 dict와 원본 텍스트를 반환한다.
    """
    match = _FM_PATTERN.match(text)
    if not match:
        return {}, text
    meta = safe_yaml_load(match.group(1))
    body = text[match.end():]
    return meta, body


def safe_yaml_load(text: str) -> dict:
    """YAML 파싱(parsing) 실패 시 빈 dict를 반환한다."""
    try:
        result = yaml.safe_load(text)
        return result if isinstance(result, dict) else {}
    except yaml.YAMLError:
        _logger.warning(t("util.frontmatter_fail"))
        return {}


def set_frontmatter_field(
    text: str, key: str, value: str,
) -> str:
    """frontmatter에 key: value 필드를 설정(set)한다.

    기존 키가 있으면 교체(replace), 없으면 추가한다.
    frontmatter가 없으면 새로 생성한다.
    """
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return f"---\n{key}: {value}\n---\n{text}"
    fm = match.group(1)
    if re.search(rf"^{key}:", fm, re.MULTILINE):
        fm = re.sub(
            rf"^{key}:.*$", f"{key}: {value}",
            fm, flags=re.MULTILINE,
        )
    else:
        fm = fm.rstrip() + f"\n{key}: {value}"
    return f"---\n{fm}\n---{text[match.end():]}"


def normalize_name(raw: str) -> str:
    """헤더/이름을 snake_case 정규화(normalize)한다.

    영문 소문자, 숫자, 한글만 유지하고 나머지는 언더스코어로 변환한다.
    """
    lowered = raw.strip().lower()
    return re.sub(r"[^a-z0-9가-힣]+", "_", lowered).strip("_")
