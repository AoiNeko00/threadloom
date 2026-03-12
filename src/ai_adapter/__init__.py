"""AI 어댑터(adapter) 팩토리(factory) 모듈."""

from .base import BaseAIAdapter

# 지원되는 프로바이더(provider) 매핑
_PROVIDERS: dict[str, type[BaseAIAdapter]] = {}


def _load_providers() -> dict[str, type[BaseAIAdapter]]:
    """지연 로딩(lazy loading)으로 프로바이더 클래스 매핑 반환."""
    if not _PROVIDERS:
        from .claude_code import ClaudeCodeAdapter
        from .codex import CodexAdapter
        from .gemini import GeminiAdapter

        _PROVIDERS["claude_code"] = ClaudeCodeAdapter
        _PROVIDERS["codex"] = CodexAdapter
        _PROVIDERS["gemini"] = GeminiAdapter
    return _PROVIDERS


def get_adapter(provider: str) -> BaseAIAdapter:
    """config의 provider 값으로 적절한 어댑터 인스턴스(instance)를 반환한다.

    Args:
        provider: "claude_code" | "codex" | "gemini"

    Raises:
        ValueError: 지원되지 않는 프로바이더인 경우
    """
    providers = _load_providers()
    adapter_cls = providers.get(provider)
    if adapter_cls is None:
        supported = ", ".join(sorted(providers.keys()))
        raise ValueError(
            f"지원되지 않는 AI 프로바이더: '{provider}'. "
            f"사용 가능: {supported}"
        )
    return adapter_cls()
