"""셀렉터 맵(Selector Map) 로더 테스트.

selectors.yaml 로드, fallback 기본값, reload 동작을 검증한다.
실제 Threads 접속 없이 mock 데이터만 사용한다.
"""

import sys
from pathlib import Path

import pytest
import yaml

# 프로젝트 루트를 sys.path에 추가
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.collector import selector_map


# ------------------------------------------------------------------
# fixture
# ------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_cache():
    """각 테스트 전후로 캐시를 초기화한다."""
    selector_map.reload()
    yield
    selector_map.reload()


# ------------------------------------------------------------------
# _defaults() 검증
# ------------------------------------------------------------------

class TestDefaults:
    """fallback 기본값(defaults) 검증."""

    def test_defaults_has_all_keys(self):
        """기본값에 필수 키가 모두 존재한다."""
        d = selector_map._defaults()
        assert "post_containers" in d
        assert "author_link" in d
        assert "post_link" in d
        assert "media" in d
        assert "noise_tokens" in d

    def test_defaults_post_containers_type(self):
        """post_containers는 list[str]이다."""
        containers = selector_map._defaults()["post_containers"]
        assert isinstance(containers, list)
        assert all(isinstance(s, str) for s in containers)

    def test_defaults_noise_tokens_type(self):
        """noise_tokens는 list[str]이다."""
        tokens = selector_map._defaults()["noise_tokens"]
        assert isinstance(tokens, list)
        assert len(tokens) > 0


# ------------------------------------------------------------------
# YAML 파일 로드 검증
# ------------------------------------------------------------------

class TestYamlLoad:
    """selectors.yaml 파일 로드(load) 검증."""

    def test_load_from_real_file(self):
        """실제 selectors.yaml을 로드한다."""
        data = selector_map._load()
        assert isinstance(data, dict)
        assert "post_containers" in data

    def test_load_caches_result(self):
        """두 번째 호출은 캐시된 결과를 반환한다."""
        first = selector_map._load()
        second = selector_map._load()
        assert first is second

    def test_load_custom_yaml(self, tmp_path, monkeypatch):
        """커스텀(custom) YAML 파일 로드를 검증한다."""
        custom = {
            "post_containers": ["div.custom"],
            "author_link": "a.author",
            "post_link": "a.post",
            "media": {"image": "img.custom", "video": "video.custom"},
            "noise_tokens": ["CustomNoise"],
        }
        yaml_path = tmp_path / "selectors.yaml"
        yaml_path.write_text(
            yaml.dump(custom, allow_unicode=True), encoding="utf-8",
        )
        monkeypatch.setattr(selector_map, "_SELECTOR_FILE", yaml_path)
        selector_map.reload()

        assert selector_map.post_containers() == ["div.custom"]
        assert selector_map.author_link() == "a.author"
        assert selector_map.post_link() == "a.post"
        assert selector_map.media_image() == "img.custom"
        assert selector_map.media_video() == "video.custom"
        assert selector_map.noise_tokens() == {"CustomNoise"}


# ------------------------------------------------------------------
# fallback (파일 없음) 검증
# ------------------------------------------------------------------

class TestFallback:
    """YAML 파일 없을 때 fallback 동작 검증."""

    def test_missing_file_uses_defaults(self, monkeypatch):
        """selectors.yaml이 없으면 기본값을 사용한다."""
        monkeypatch.setattr(
            selector_map, "_SELECTOR_FILE",
            Path("/nonexistent/selectors.yaml"),
        )
        selector_map.reload()

        defaults = selector_map._defaults()
        assert selector_map.post_containers() == defaults["post_containers"]
        assert selector_map.author_link() == defaults["author_link"]
        assert selector_map.noise_tokens() == set(defaults["noise_tokens"])


# ------------------------------------------------------------------
# reload() 검증
# ------------------------------------------------------------------

class TestReload:
    """reload() 캐시 초기화 검증."""

    def test_reload_clears_cache(self):
        """reload() 호출 후 캐시가 None이 된다."""
        selector_map._load()
        assert selector_map._cache is not None
        selector_map.reload()
        assert selector_map._cache is None


# ------------------------------------------------------------------
# 접근자 함수(accessor) 반환 타입 검증
# ------------------------------------------------------------------

class TestAccessors:
    """각 접근자 함수의 반환 타입(return type) 검증."""

    def test_post_containers_returns_list(self):
        result = selector_map.post_containers()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_author_link_returns_str(self):
        result = selector_map.author_link()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_post_link_returns_str(self):
        result = selector_map.post_link()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_media_image_returns_str(self):
        result = selector_map.media_image()
        assert isinstance(result, str)

    def test_media_video_returns_str(self):
        result = selector_map.media_video()
        assert isinstance(result, str)

    def test_noise_tokens_returns_set(self):
        result = selector_map.noise_tokens()
        assert isinstance(result, set)
        assert "Like" in result
        assert "Reply" in result
