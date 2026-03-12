"""테스트 공통 설정 — playwright_stealth import 호환성(compatibility) 처리."""

import sys
from types import ModuleType
from unittest.mock import MagicMock


def _ensure_stealth_sync():
    """playwright_stealth.stealth_sync이 없으면 mock으로 패치한다."""
    try:
        from playwright_stealth import stealth_sync  # noqa: F401
    except ImportError:
        # v2에서 이름이 변경된 경우 mock 삽입
        mod = sys.modules.get("playwright_stealth")
        if mod is None:
            mod = ModuleType("playwright_stealth")
            sys.modules["playwright_stealth"] = mod
        if not hasattr(mod, "stealth_sync"):
            mod.stealth_sync = MagicMock()


_ensure_stealth_sync()
