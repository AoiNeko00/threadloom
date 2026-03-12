"""강화(enhancement) 데이터 모델 정의."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PendingAction:
    """승인 대기 중인 강화 항목."""

    file_path: Path
    action_type: str
    name: str
    target: str
    content: str
    source_posts: list[str] = field(default_factory=list)
    duplicate_check: str = "create_new"
