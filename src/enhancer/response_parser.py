"""AI 응답 파싱(response parsing) 모듈.

AI CLI 응답 텍스트를 ---THREADLOOM_FILE_START/END--- 구분자,
코드블록 제거, YAML frontmatter 등 다양한 전략으로 파싱한다.
"""

import re

from src.utils.frontmatter import parse_frontmatter as _parse_fm
from src.utils.frontmatter import safe_yaml_load
from src.utils.i18n import t
from src.utils.logger import get_logger

_logger = get_logger("response_parser")

# 파일 구분자(delimiter) 패턴 - fuzzy matching 적용
_FILE_START_PATTERN = re.compile(
    r"---\s*THREADLOOM[_\s]*FILE[_\s]*START\s*:\s*(.+?)\s*---",
    re.IGNORECASE,
)
_FILE_END_PATTERN = re.compile(
    r"---\s*THREADLOOM[_\s]*FILE[_\s]*END\s*---",
    re.IGNORECASE,
)


def parse_response(response: str) -> list[dict]:
    """AI 응답을 파싱하여 파일 데이터 리스트를 반환한다.

    파싱 전략(strategy) 우선순위:
    1. 구분자(delimiter) 직접 매칭
    2. 코드블록(code block) 제거 후 구분자 재시도
    3. YAML frontmatter 기반 파일 분리
    """
    # 전략 1: 구분자 직접 매칭
    files = parse_by_delimiters(response)
    if files:
        return files

    # 전략 2: 코드블록 제거 후 구분자 재시도
    stripped = strip_code_blocks(response)
    if stripped != response:
        files = parse_by_delimiters(stripped)
        if files:
            _logger.info(t("enhancer.codeblock_parse_ok"))
            return files

    # 전략 3: YAML frontmatter 기반 파일 분리
    files = parse_by_frontmatter(response)
    if files:
        _logger.info(t("enhancer.frontmatter_parse_ok", n=len(files)))
    return files


def parse_by_delimiters(text: str) -> list[dict]:
    """구분자(delimiter) 패턴으로 파일을 추출한다."""
    files: list[dict] = []
    starts = list(_FILE_START_PATTERN.finditer(text))
    if not starts:
        return []
    for start_match in starts:
        file_data = extract_single_file(text, start_match)
        if file_data:
            files.append(file_data)
    return files


def strip_code_blocks(text: str) -> str:
    """코드블록(``` 또는 ~~~) 마커를 제거한다."""
    return re.sub(
        r"^[ \t]*(`{3,}|~{3,}).*$", "", text, flags=re.MULTILINE,
    )


def parse_by_frontmatter(text: str) -> list[dict]:
    """YAML frontmatter 블록 기반으로 파일을 분리한다.

    action_type과 name 키가 있는 frontmatter를 찾아 파싱한다.
    """
    pattern = re.compile(
        r"^---\s*\n(.*?\n)---\s*\n(.*?)(?=^---\s*\n|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    files: list[dict] = []
    for match in pattern.finditer(text):
        yaml_str = match.group(1)
        body = match.group(2).strip()
        metadata = safe_yaml_load(yaml_str)
        # action_type과 name이 있어야 유효한 강화(enhancement) 파일
        if "action_type" not in metadata or "name" not in metadata:
            continue
        content = f"---\n{yaml_str}---\n\n{body}"
        files.append({
            "identifier": f"{metadata['action_type']}_{metadata['name']}",
            "content": content,
            "metadata": metadata,
        })
    return files


def extract_single_file(
    response: str, start_match: re.Match,
) -> dict | None:
    """단일 파일 블록(block)을 추출하고 메타데이터를 파싱한다."""
    identifier = start_match.group(1).strip()
    content_start = start_match.end()

    end_match = _FILE_END_PATTERN.search(response, content_start)
    content_end = end_match.start() if end_match else len(response)
    content = response[content_start:content_end].strip()

    metadata = extract_frontmatter(content)
    metadata.setdefault("action_type", infer_action_type(identifier))
    metadata.setdefault("name", infer_name(identifier))

    return {
        "identifier": identifier,
        "content": content,
        "metadata": metadata,
    }


def extract_frontmatter(content: str) -> dict:
    """md 내용에서 YAML frontmatter를 추출한다."""
    meta, _ = _parse_fm(content)
    return meta


def infer_action_type(identifier: str) -> str:
    """식별자(identifier)에서 action_type을 추론한다."""
    lower = identifier.lower()
    for action in (
        "create_skill", "create_agent", "add_rule", "merge_skill",
    ):
        normalized = action.replace("_", "")
        if normalized in lower.replace("_", "").replace(" ", ""):
            return action
    return "create_skill"


def infer_name(identifier: str) -> str:
    """식별자에서 name을 추론한다."""
    # "create_skill_foo_bar" -> "foo_bar"
    parts = identifier.strip().split("_", 2)
    if len(parts) >= 3:
        return parts[2].strip().replace(" ", "_").replace("-", "_")
    return identifier.strip().replace(" ", "_").replace("-", "_")
