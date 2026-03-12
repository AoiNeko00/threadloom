"""수집 아카이브 검색(search) 모듈 테스트."""

from pathlib import Path

import pytest

from src.utils.search import (
    SearchHit,
    _copy_path,
    _open_in_editor,
    _parse_index,
    _parse_md_parts,
    _score_file,
    search,
)


# ======================================================================
# _parse_md_parts 테스트
# ======================================================================

class TestParseMdParts:
    """frontmatter 파싱(parsing) 테스트."""

    def test_with_frontmatter(self) -> None:
        text = "---\ntags: [python, ai]\nsummary: AI 도구 정리\n---\n본문 텍스트"
        tags, summary, body = _parse_md_parts(text)
        assert tags == ["python", "ai"]
        assert summary == "AI 도구 정리"
        assert "본문 텍스트" in body

    def test_without_frontmatter(self) -> None:
        text = "그냥 본문만 있는 파일"
        tags, summary, body = _parse_md_parts(text)
        assert tags == []
        assert summary == ""
        assert body == text

    def test_tags_as_string(self) -> None:
        text = "---\ntags: python, ai\nsummary: test\n---\nbody"
        tags, summary, body = _parse_md_parts(text)
        assert tags == ["python", "ai"]

    def test_empty_frontmatter(self) -> None:
        text = "---\n---\nbody"
        tags, summary, body = _parse_md_parts(text)
        assert tags == []
        assert summary == ""


# ======================================================================
# _score_file 테스트
# ======================================================================

class TestScoreFile:
    """점수 계산(scoring) 테스트."""

    def test_tag_match(self, tmp_path: Path) -> None:
        md = tmp_path / "test.md"
        md.write_text("---\ntags: [python]\nsummary: 없음\n---\n본문", encoding="utf-8")
        hit = _score_file(md, "python", "raw")
        assert hit is not None
        assert hit.score >= 3  # 태그 매칭 +3

    def test_summary_match(self, tmp_path: Path) -> None:
        md = tmp_path / "test.md"
        md.write_text("---\ntags: []\nsummary: flutter 앱 개발\n---\n본문", encoding="utf-8")
        hit = _score_file(md, "flutter", "analysis")
        assert hit is not None
        assert hit.score >= 2  # 요약 매칭 +2

    def test_body_match(self, tmp_path: Path) -> None:
        md = tmp_path / "test.md"
        md.write_text("---\ntags: []\nsummary: 없음\n---\nrust는 좋다\nrust 성능\nrust 안전", encoding="utf-8")
        hit = _score_file(md, "rust", "raw")
        assert hit is not None
        assert hit.score == 3  # 본문 3줄 매칭
        assert len(hit.matched_lines) == 3

    def test_no_match(self, tmp_path: Path) -> None:
        md = tmp_path / "test.md"
        md.write_text("---\ntags: [java]\nsummary: 자바\n---\n자바 코드", encoding="utf-8")
        hit = _score_file(md, "python", "raw")
        assert hit is None

    def test_combined_score(self, tmp_path: Path) -> None:
        """태그 + 요약 + 본문 모두 매칭 시 합산."""
        md = tmp_path / "test.md"
        md.write_text(
            "---\ntags: [ai]\nsummary: ai 모델 비교\n---\nai가 좋다",
            encoding="utf-8",
        )
        hit = _score_file(md, "ai", "raw")
        assert hit is not None
        assert hit.score == 6  # 태그(3) + 요약(2) + 본문(1)

    def test_case_insensitive(self, tmp_path: Path) -> None:
        """대소문자 구분 없이 검색."""
        md = tmp_path / "test.md"
        md.write_text("---\ntags: [Python]\nsummary: 없음\n---\n", encoding="utf-8")
        hit = _score_file(md, "python", "raw")
        assert hit is not None
        assert hit.score >= 3


# ======================================================================
# search 통합 테스트
# ======================================================================

class TestSearch:
    """search() 통합(integration) 테스트."""

    def test_search_with_mock_data(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """mock 데이터로 검색 결과 정렬 확인."""
        raw_dir = tmp_path / "data" / "raw"
        raw_dir.mkdir(parents=True)

        # 높은 점수(high score) 파일
        (raw_dir / "high.md").write_text(
            "---\ntags: [flutter]\nsummary: flutter 위젯\n---\nflutter 개발",
            encoding="utf-8",
        )
        # 낮은 점수(low score) 파일
        (raw_dir / "low.md").write_text(
            "---\ntags: [dart]\nsummary: dart 문법\n---\nflutter도 있다",
            encoding="utf-8",
        )
        # 배치(batch) 파일 — 제외 대상
        (raw_dir / "test_batch1.md").write_text(
            "---\ntags: [flutter]\n---\nflutter",
            encoding="utf-8",
        )

        # 모듈 내부 디렉토리(directory) 경로를 mock으로 교체
        import src.utils.search as search_mod
        monkeypatch.setattr(search_mod, "_RAW_DIR", raw_dir)
        monkeypatch.setattr(search_mod, "_ANALYSIS_DIR", tmp_path / "data" / "analysis")

        hits = search_mod.search("flutter")
        assert len(hits) == 2  # 배치 파일 제외
        assert hits[0].score > hits[1].score  # 점수 내림차순
        assert hits[0].file_path.name == "high.md"


# ======================================================================
# _parse_index 테스트
# ======================================================================

class TestParseIndex:
    """인덱스 파싱(index parsing) 테스트."""

    def test_valid_index(self) -> None:
        """유효한 번호 → 0-based 인덱스 반환."""
        assert _parse_index("1", 5) == 0
        assert _parse_index("5", 5) == 4
        assert _parse_index("3", 10) == 2

    def test_out_of_range(self) -> None:
        """범위 밖 번호 → None 반환."""
        assert _parse_index("0", 5) is None
        assert _parse_index("6", 5) is None
        assert _parse_index("-1", 5) is None

    def test_non_numeric(self) -> None:
        """숫자가 아닌 입력 → None 반환."""
        assert _parse_index("abc", 5) is None
        assert _parse_index("", 5) is None


# ======================================================================
# _open_in_editor 테스트
# ======================================================================

class TestOpenInEditor:
    """에디터(editor) 열기 테스트."""

    def test_opens_with_editor_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """$EDITOR 환경변수(env var) 사용 확인."""
        import subprocess
        from unittest.mock import MagicMock

        mock_run = MagicMock()
        monkeypatch.setattr(subprocess, "run", mock_run)
        monkeypatch.setenv("EDITOR", "nano")

        test_file = tmp_path / "test.md"
        _open_in_editor(test_file)

        mock_run.assert_called_once_with(["nano", str(test_file)])

    def test_default_vim(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """$EDITOR 미설정 시 vim 기본값(default) 확인."""
        import subprocess
        from unittest.mock import MagicMock

        mock_run = MagicMock()
        monkeypatch.setattr(subprocess, "run", mock_run)
        monkeypatch.delenv("EDITOR", raising=False)

        test_file = tmp_path / "test.md"
        _open_in_editor(test_file)

        mock_run.assert_called_once_with(["vim", str(test_file)])


# ======================================================================
# _copy_path 테스트
# ======================================================================

class TestCopyPath:
    """클립보드(clipboard) 복사 테스트."""

    def test_copy_darwin(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """macOS(darwin)에서 pbcopy 호출 확인."""
        import subprocess
        import sys
        from unittest.mock import MagicMock

        mock_run = MagicMock()
        monkeypatch.setattr(subprocess, "run", mock_run)
        monkeypatch.setattr(sys, "platform", "darwin")

        test_file = tmp_path / "test.md"
        _copy_path(test_file)

        mock_run.assert_called_once_with(
            ["pbcopy"], input=str(test_file), text=True, check=True,
        )

    def test_copy_fallback_on_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """클립보드 명령 실패 시 경로 출력으로 폴백(fallback)."""
        import subprocess
        import sys
        from unittest.mock import MagicMock

        mock_run = MagicMock(side_effect=FileNotFoundError)
        monkeypatch.setattr(subprocess, "run", mock_run)
        monkeypatch.setattr(sys, "platform", "darwin")

        test_file = tmp_path / "test.md"
        # 예외 없이 정상 종료 확인
        _copy_path(test_file)
