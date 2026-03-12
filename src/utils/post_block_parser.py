"""포스트 블록(post block) 파싱 공통 모듈.

analysis md의 `## post-NNN` 블록을 파싱하는 공통 로직을 제공한다.
ObsidianWriter와 ReportWriter에서 공유한다.
"""

import re

# 필드명 → 영문 키(key) 매핑 (한국어 + 영어 모두 지원)
_KEY_MAP: dict[str, str] = {
    # 한국어
    "분류": "category",
    "태그": "tags",
    "요약": "summary",
    "유용성": "relevance",
    "actionable": "actionable",
    "강화 유형": "enhance_type",
    "제안 이름": "suggest_name",
    "판단 근거": "reason",
    # 영어 (AI가 영문 응답 시)
    "Classification": "category",
    "Tags": "tags",
    "Summary": "summary",
    "Relevance": "relevance",
    "Actionable": "actionable",
    "Enhancement type": "enhance_type",
    "Proposed name": "suggest_name",
    "Reasoning": "reason",
}

# 포스트 블록(post block) 분리 정규식(regex)
# post_id: 숫자 또는 16진수 해시 (post-001, post-25905b5a9fb97e2a)
# 헤더 전체를 캡처하여 `(author)` 추출 가능
_BLOCK_PATTERN = re.compile(
    r"^##\s+(post-[\w]+)(.*?)$(.*?)(?=^##\s|\Z)",
    re.MULTILINE | re.DOTALL,
)

# 헤더 괄호 안 작성자(author) 추출 — `## post-002 (olive.r_327)`
_HEADER_AUTHOR_PATTERN = re.compile(r"\(\s*([^)]+?)\s*\)")

# 필드(field) 추출 정규식
_FIELD_PATTERN = re.compile(r"-\s+\*\*(.+?)\*\*:\s*(.+)")


def parse_post_blocks(text: str) -> list[dict]:
    """텍스트에서 `## post-NNN` 블록들을 파싱하여 dict 리스트로 반환한다.

    각 dict에는 post_id와 정규화된 필드 키가 포함된다.
    tags 필드는 문자열 그대로 유지한다 (호출부에서 후처리).
    헤더에 `(author)` 정보가 있으면 header_author 필드에 저장한다.
    """
    matches = _BLOCK_PATTERN.findall(text)
    return [
        _parse_single_block(pid, header_rest, block)
        for pid, header_rest, block in matches
    ]


def _parse_single_block(
    post_id: str, header_rest: str, block: str,
) -> dict:
    """단일 포스트 블록에서 필드를 추출한다."""
    post: dict = {"post_id": post_id}
    # 헤더에서 작성자(author) 추출 — `## post-002 (olive.r_327)`
    author_match = _HEADER_AUTHOR_PATTERN.search(header_rest)
    if author_match:
        post["header_author"] = author_match.group(1).strip()
    for match in _FIELD_PATTERN.finditer(block):
        raw_key = match.group(1).strip()
        key = _KEY_MAP.get(raw_key, raw_key)
        post[key] = match.group(2).strip()
    return post


def parse_tag_list(raw: str) -> list[str]:
    """'[태그1, 태그2]' 형식 문자열을 리스트로 변환한다."""
    if not raw or raw == "[]":
        return []
    cleaned = raw.strip("[] ")
    return [t.strip() for t in cleaned.split(",") if t.strip()]
