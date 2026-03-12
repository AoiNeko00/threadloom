"""기술 스택(tech stack) 감지 모듈.

대상 프로젝트의 기술 스택을 파일 시스템 기반으로 감지하고,
텍스트에서 언급된 기술 스택을 추출한다.
"""

from pathlib import Path

from src.enhancer.reviewer_config import STACK_DETECTORS, STACK_KEYWORDS


def detect_stacks(target_root: Path) -> set[str]:
    """대상 프로젝트의 기술 스택(tech stack)을 감지한다."""
    stacks: set[str] = set()
    for filename, stack_keywords in STACK_DETECTORS.items():
        if (target_root / filename).exists():
            stacks.update(stack_keywords)
    return stacks


def extract_mentioned_stacks(text: str) -> set[str]:
    """텍스트에서 언급된 기술 스택을 추출한다."""
    mentioned: set[str] = set()
    for stack, keywords in STACK_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                mentioned.add(stack)
                break
    return mentioned
