"""threadloom 설정(configuration) 로더.

config.yaml을 읽고 검증하며, 싱글턴(singleton) 패턴으로 관리한다.
"""

import sys
from pathlib import Path
from typing import Any

import yaml

from src.utils.i18n import t
from src.utils.logger import get_logger

_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
_CONFIG_FILE: Path = _PROJECT_ROOT / "config.yaml"
_CONFIG_EXAMPLE: Path = _PROJECT_ROOT / "config.example.yaml"

_logger = get_logger("config")


class Config:
    """threadloom 설정을 관리하는 싱글턴 클래스."""

    _instance: "Config | None" = None
    _initialized: bool = False

    def __new__(cls) -> "Config":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if Config._initialized:
            return
        self._data: dict[str, Any] = {}
        self._load()
        self._validate()
        self._ensure_directories()
        Config._initialized = True

    @property
    def data(self) -> dict[str, Any]:
        return self._data

    @property
    def target_project_path(self) -> str:
        return self._data["target_project"]["path"]

    @property
    def auto_apply(self) -> bool:
        return self._data["target_project"].get("auto_apply", False)

    @property
    def enhance_config(self) -> dict[str, bool]:
        return self._data["target_project"].get("enhance", {
            "skills": True, "agents": True, "rules": True,
        })

    @property
    def target_projects(self) -> list[dict[str, Any]]:
        """다중 프로젝트 라우팅(multi-project routing) 설정.

        미설정 시 기존 target_project를 단일 항목으로 반환한다.
        """
        projects = self._data.get("target_projects", [])
        if not projects:
            # 하위 호환(backward compatibility): 단일 프로젝트
            return [{
                "name": Path(self.target_project_path).name,
                "path": self.target_project_path,
                "tags": [],
            }]
        return projects

    @property
    def obsidian_enabled(self) -> bool:
        return self._data.get("obsidian", {}).get("enabled", False)

    @property
    def vault_path(self) -> str:
        return self._data.get("obsidian", {}).get("vault_path", "")

    @property
    def obsidian_folders(self) -> dict[str, str]:
        return self._data.get("obsidian", {}).get("folders", {})

    @property
    def threads_account(self) -> str:
        """Threads 계정 ID. 여러 계정 전환 시 keyring 키 구분에 사용."""
        return self._data.get("threads", {}).get("account", "")

    @property
    def ai_provider(self) -> str:
        return self._data.get("ai", {}).get("provider", "claude_code")

    @property
    def ai_language(self) -> str:
        return self._data.get("ai", {}).get("language", "ko")

    @property
    def classification_tags(self) -> list[str]:
        return self._data.get("classification", {}).get("tags", [])

    @property
    def min_relevance_score(self) -> float:
        return self._data.get("classification", {}).get(
            "min_relevance_score", 0.7,
        )

    @property
    def max_posts_per_batch(self) -> int:
        return self._data.get("classification", {}).get(
            "max_posts_per_batch", 50,
        )

    @property
    def max_chars_per_batch(self) -> int:
        return self._data.get("classification", {}).get(
            "max_chars_per_batch", 80000,
        )

    @property
    def link_fetching_enabled(self) -> bool:
        """외부 링크 크롤링(link fetching) 활성화 여부."""
        return self._data.get("link_fetching", {}).get("enabled", True)

    @property
    def max_links_per_post(self) -> int:
        """포스트당 최대 링크 크롤링 수."""
        return self._data.get("link_fetching", {}).get(
            "max_links_per_post", 3,
        )

    @property
    def link_fetch_timeout(self) -> int:
        """링크 크롤링 타임아웃(timeout) 초."""
        return self._data.get("link_fetching", {}).get("timeout", 10)

    @property
    def reviewer_min_relevance_score(self) -> float:
        """심사(reviewer) 최소 관련성 점수."""
        return self._data.get("reviewer", {}).get(
            "min_relevance_score", 0.7,
        )

    @property
    def reviewer_max_pending_items(self) -> int:
        """심사(reviewer) 한 번에 최대 pending 항목 수."""
        return self._data.get("reviewer", {}).get(
            "max_pending_items", 20,
        )

    @property
    def reviewer_reject_generic_advice(self) -> bool:
        """일반적 조언 자동 거부(generic advice rejection) 여부."""
        return self._data.get("reviewer", {}).get(
            "reject_generic_advice", True,
        )

    def _load(self) -> None:
        """config.yaml을 로드한다. 없으면 안내 후 종료."""
        if not _CONFIG_FILE.exists():
            _logger.error(t("config.no_config_file"))
            sys.exit(1)

        with open(_CONFIG_FILE, encoding="utf-8") as f:
            self._data = yaml.safe_load(f) or {}

    def _validate(self) -> None:
        """필수 설정값을 검증한다."""
        self._validate_target_project()
        if self.obsidian_enabled:
            self._validate_obsidian()

    def _validate_target_project(self) -> None:
        """대상 프로젝트(target project) 경로를 검증한다."""
        tp = self._data.get("target_project", {})
        path = tp.get("path", "")
        if not path:
            _logger.error(t("config.no_target_path"))
            sys.exit(1)

        target_dir = Path(path)
        if not target_dir.is_dir():
            _logger.error(t("config.target_path_missing", path=path))
            sys.exit(1)

        # .claude/ 디렉토리(directory) 자동 생성
        claude_dir = target_dir / ".claude"
        if not claude_dir.exists():
            _logger.info(t("config.claude_dir_created", path=path))
            (claude_dir / "skills").mkdir(parents=True, exist_ok=True)
            (claude_dir / "agents").mkdir(parents=True, exist_ok=True)
            _logger.info(t("config.claude_subdirs_created"))

    def _validate_obsidian(self) -> None:
        """Obsidian vault 경로를 검증한다."""
        vault = self.vault_path
        if not vault:
            _logger.error(t("config.obsidian_no_vault"))
            sys.exit(1)

        if not Path(vault).is_dir():
            _logger.error(t("config.obsidian_vault_missing", vault=vault))
            sys.exit(1)

    def _ensure_directories(self) -> None:
        """필수 하위 폴더(subdirectory)를 자동 생성한다."""
        # data 디렉토리 구조
        data_dir = _PROJECT_ROOT / "data"
        for sub in ("raw", "analysis", "pending", "rejected", "backups"):
            (data_dir / sub).mkdir(parents=True, exist_ok=True)

        # Obsidian 폴더 생성
        if self.obsidian_enabled and self.vault_path:
            vault = Path(self.vault_path)
            for folder in self.obsidian_folders.values():
                (vault / folder).mkdir(parents=True, exist_ok=True)

    @classmethod
    def reset(cls) -> None:
        """싱글턴 인스턴스를 초기화한다 (테스트용)."""
        cls._instance = None
        cls._initialized = False
