"""자동 심사(auto-review) 모듈 테스트.

hard reject, 기술 스택 필터, 품질 게이트, 중복 검사, 범위 필터, 통합 시나리오를 검증한다.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.enhancer.reviewer import EnhancementReviewer
from src.enhancer.reviewer_config import classify_scope


# ------------------------------------------------------------------
# mock Config 헬퍼
# ------------------------------------------------------------------

def _make_mock_config(target_path: str = "/tmp/test_project") -> MagicMock:
    """테스트용 Config mock 객체를 생성한다."""
    config = MagicMock()
    config.target_project_path = target_path
    config.data = {
        "reviewer": {
            "min_relevance_score": 0.7,
            "max_pending_items": 20,
            "reject_generic_advice": True,
        },
    }
    return config


# ------------------------------------------------------------------
# pending md 생성 헬퍼
# ------------------------------------------------------------------

def _write_pending(
    directory: Path,
    name: str = "test_skill",
    action_type: str = "create_skill",
    relevance_score: float = 0.8,
    body: str = "",
) -> Path:
    """테스트용 pending md 파일을 생성한다."""
    if not body:
        body = (
            "# test_skill\n\n"
            "이것은 테스트용 강화 내용입니다. "
            "구체적 패턴을 포함하며 즉시 적용 가능합니다. "
            "함수가 20줄을 초과하면 분리하라는 규칙을 담고 있습니다. "
            "이 규칙은 코드 품질을 높이고 유지보수성을 개선하는 데 기여합니다. "
            "추가 설명을 포함하여 충분한 길이를 확보합니다."
        )
    content = (
        f"---\n"
        f"action_type: {action_type}\n"
        f"name: {name}\n"
        f"target: .claude/skills/{name}.md\n"
        f"relevance_score: {relevance_score}\n"
        f"---\n\n"
        f"{body}\n"
    )
    path = directory / f"{action_type}_{name}.md"
    path.write_text(content, encoding="utf-8")
    return path


# ------------------------------------------------------------------
# Hard Reject 테스트
# ------------------------------------------------------------------

class TestHardReject:
    """즉시 거부(hard reject) 조건을 검증한다."""

    def test_reject_raw_fallback(self, tmp_path, monkeypatch):
        """raw_fallback action_type은 즉시 거부되어야 한다."""
        monkeypatch.setattr(
            "src.enhancer.reviewer._PENDING_DIR", tmp_path,
        )
        monkeypatch.setattr(
            "src.enhancer.reviewer._REJECTED_DIR", tmp_path / "rejected",
        )
        path = _write_pending(
            tmp_path, name="fallback_123",
            action_type="raw_fallback",
            body="# 원본 응답\n\n파싱 실패한 AI 응답 원문이 여기에 있습니다. 매우 긴 텍스트입니다.",
        )
        reviewer = EnhancementReviewer(_make_mock_config(str(tmp_path)))
        result = reviewer.review([path])

        assert len(result.approved) == 0
        assert len(result.rejected) == 1
        assert "raw_fallback" in result.rejected[0][1]

    def test_reject_missing_action_type(self, tmp_path, monkeypatch):
        """action_type이 없는 항목은 거부되어야 한다."""
        monkeypatch.setattr(
            "src.enhancer.reviewer._PENDING_DIR", tmp_path,
        )
        monkeypatch.setattr(
            "src.enhancer.reviewer._REJECTED_DIR", tmp_path / "rejected",
        )
        # frontmatter에 action_type 없이 생성
        path = tmp_path / "no_action.md"
        path.write_text(
            "---\nname: test\n---\n\n"
            "내용이 충분히 길어야 합니다. 이 텍스트는 100자를 초과하도록 작성되었으며 "
            "테스트 목적으로 사용됩니다. 추가 텍스트를 더 넣어서 길이를 확보합니다.\n",
            encoding="utf-8",
        )
        reviewer = EnhancementReviewer(_make_mock_config(str(tmp_path)))
        result = reviewer.review([path])

        assert len(result.approved) == 0
        assert "action_type 누락" in result.rejected[0][1]

    def test_reject_missing_name(self, tmp_path, monkeypatch):
        """name이 없는 항목은 거부되어야 한다."""
        monkeypatch.setattr(
            "src.enhancer.reviewer._PENDING_DIR", tmp_path,
        )
        monkeypatch.setattr(
            "src.enhancer.reviewer._REJECTED_DIR", tmp_path / "rejected",
        )
        path = tmp_path / "no_name.md"
        path.write_text(
            "---\naction_type: create_skill\n---\n\n"
            "내용이 충분히 길어야 합니다. 이 텍스트는 100자를 초과하도록 작성되었으며 "
            "테스트 목적으로 사용됩니다. 추가 텍스트를 더 넣어서 길이를 확보합니다.\n",
            encoding="utf-8",
        )
        reviewer = EnhancementReviewer(_make_mock_config(str(tmp_path)))
        result = reviewer.review([path])

        assert len(result.approved) == 0
        assert "name 누락" in result.rejected[0][1]

    def test_reject_short_content(self, tmp_path, monkeypatch):
        """100자 미만 내용은 거부되어야 한다."""
        monkeypatch.setattr(
            "src.enhancer.reviewer._PENDING_DIR", tmp_path,
        )
        monkeypatch.setattr(
            "src.enhancer.reviewer._REJECTED_DIR", tmp_path / "rejected",
        )
        path = _write_pending(
            tmp_path, body="짧은 내용",
        )
        reviewer = EnhancementReviewer(_make_mock_config(str(tmp_path)))
        result = reviewer.review([path])

        assert len(result.approved) == 0
        assert "최소 100자" in result.rejected[0][1]

    def test_reject_meta_response(self, tmp_path, monkeypatch):
        """AI 메타 응답(권한 요청 등)이 포함된 항목은 거부되어야 한다."""
        monkeypatch.setattr(
            "src.enhancer.reviewer._PENDING_DIR", tmp_path,
        )
        monkeypatch.setattr(
            "src.enhancer.reviewer._REJECTED_DIR", tmp_path / "rejected",
        )
        path = _write_pending(
            tmp_path,
            body=(
                "# 스킬 내용\n\n"
                "파일 쓰기를 허용해주시면 아래 내용을 생성하겠습니다. "
                "이 내용은 AI가 권한 요청을 포함한 메타 응답입니다. "
                "충분한 길이의 텍스트를 포함합니다. "
                "실제로 이 응답은 강화 내용이 아니라 AI의 도구 호출 시도이므로 "
                "즉시 거부되어야 합니다. 추가 텍스트로 길이를 확보합니다."
            ),
        )
        reviewer = EnhancementReviewer(_make_mock_config(str(tmp_path)))
        result = reviewer.review([path])

        assert len(result.approved) == 0
        assert "메타 응답" in result.rejected[0][1]


# ------------------------------------------------------------------
# 기술 스택 필터(relevance filter) 테스트
# ------------------------------------------------------------------

class TestRelevanceFilter:
    """대상 프로젝트 기술 스택과의 관련성 검증."""

    def test_reject_react_for_python_project(self, tmp_path, monkeypatch):
        """Python 프로젝트에 React 관련 skill은 거부되어야 한다."""
        monkeypatch.setattr(
            "src.enhancer.reviewer._PENDING_DIR", tmp_path,
        )
        monkeypatch.setattr(
            "src.enhancer.reviewer._REJECTED_DIR", tmp_path / "rejected",
        )
        # Python 프로젝트 시뮬레이션(simulation)
        (tmp_path / "requirements.txt").write_text("flask\n", encoding="utf-8")

        path = _write_pending(
            tmp_path,
            name="react_component_pattern",
            body=(
                "# React 컴포넌트 패턴\n\n"
                "React component에서 useState와 useEffect를 활용한 "
                "상태 관리 패턴입니다. JSX에서 conditional rendering을 "
                "구현하는 구체적인 방법을 제시합니다."
            ),
        )
        reviewer = EnhancementReviewer(_make_mock_config(str(tmp_path)))
        result = reviewer.review([path])

        assert len(result.approved) == 0
        assert "기술 스택 불일치" in result.rejected[0][1]

    def test_approve_python_for_python_project(self, tmp_path, monkeypatch):
        """Python 프로젝트에 Python 관련 skill은 통과해야 한다."""
        monkeypatch.setattr(
            "src.enhancer.reviewer._PENDING_DIR", tmp_path,
        )
        monkeypatch.setattr(
            "src.enhancer.reviewer._REJECTED_DIR", tmp_path / "rejected",
        )
        (tmp_path / "requirements.txt").write_text("flask\n", encoding="utf-8")

        path = _write_pending(
            tmp_path,
            name="python_error_handling",
            body=(
                "# Python 에러 핸들링\n\n"
                "Python에서 pytest를 활용한 에러 핸들링 패턴입니다. "
                "구체적 패턴을 포함하며 즉시 적용 가능한 코드입니다. "
                "fastapi에서의 예외 처리 방법도 포함합니다."
            ),
        )
        reviewer = EnhancementReviewer(_make_mock_config(str(tmp_path)))
        result = reviewer.review([path])

        assert len(result.approved) == 1

    def test_approve_generic_for_no_stack_mention(
        self, tmp_path, monkeypatch,
    ):
        """특정 스택을 언급하지 않는 범용 강화는 통과해야 한다."""
        monkeypatch.setattr(
            "src.enhancer.reviewer._PENDING_DIR", tmp_path,
        )
        monkeypatch.setattr(
            "src.enhancer.reviewer._REJECTED_DIR", tmp_path / "rejected",
        )
        (tmp_path / "requirements.txt").write_text("flask\n", encoding="utf-8")

        path = _write_pending(
            tmp_path,
            name="code_review_checklist",
            body=(
                "# 코드 리뷰 체크리스트\n\n"
                "코드 리뷰 시 반드시 확인할 항목 목록입니다. "
                "변수 이름, 함수 길이, 에러 처리 등 범용적으로 "
                "적용 가능한 워크플로우 개선 패턴입니다. "
                "각 항목에 대해 구체적 조건과 행동 매핑을 정의하여 "
                "일관성 있는 코드 리뷰를 보장합니다."
            ),
        )
        reviewer = EnhancementReviewer(_make_mock_config(str(tmp_path)))
        result = reviewer.review([path])

        assert len(result.approved) == 1

    def test_reject_cargo_for_flutter_project(self, tmp_path, monkeypatch):
        """Flutter 프로젝트에 Cargo(Rust) 관련 rule은 거부되어야 한다."""
        monkeypatch.setattr(
            "src.enhancer.reviewer._PENDING_DIR", tmp_path,
        )
        monkeypatch.setattr(
            "src.enhancer.reviewer._REJECTED_DIR", tmp_path / "rejected",
        )
        (tmp_path / "pubspec.yaml").write_text(
            "name: test\n", encoding="utf-8",
        )

        path = _write_pending(
            tmp_path,
            name="cargo_optimization",
            action_type="add_rule",
            body=(
                "# Cargo.toml 최적화\n\n"
                "Rust crate 의존성 관리에서 Cargo.toml의 "
                "features 플래그를 최적화하는 구체적 패턴입니다. "
                "tokio runtime 설정 방법도 포함합니다."
            ),
        )
        reviewer = EnhancementReviewer(_make_mock_config(str(tmp_path)))
        result = reviewer.review([path])

        assert len(result.approved) == 0
        assert "기술 스택 불일치" in result.rejected[0][1]


# ------------------------------------------------------------------
# 품질 게이트(quality gate) 테스트
# ------------------------------------------------------------------

class TestQualityGate:
    """품질 점수 기반 거부/통과를 검증한다."""

    def test_reject_low_relevance_score(self, tmp_path, monkeypatch):
        """relevance_score 0.7 미만은 거부되어야 한다."""
        monkeypatch.setattr(
            "src.enhancer.reviewer._PENDING_DIR", tmp_path,
        )
        monkeypatch.setattr(
            "src.enhancer.reviewer._REJECTED_DIR", tmp_path / "rejected",
        )
        path = _write_pending(
            tmp_path, relevance_score=0.5,
            body=(
                "# 낮은 점수 스킬\n\n"
                "이 강화는 관련성 점수가 낮습니다. "
                "일반적 조언 수준에 그치며 구체적 패턴이 부족합니다. "
                "충분히 긴 텍스트를 포함하고 있습니다. "
                "실질적인 코드 개선 효과가 미미하며 "
                "토큰 대비 가치가 낮은 내용입니다."
            ),
        )
        reviewer = EnhancementReviewer(_make_mock_config(str(tmp_path)))
        result = reviewer.review([path])

        assert len(result.approved) == 0
        assert "relevance_score" in result.rejected[0][1]

    def test_approve_high_relevance_score(self, tmp_path, monkeypatch):
        """relevance_score 0.7 이상은 통과해야 한다."""
        monkeypatch.setattr(
            "src.enhancer.reviewer._PENDING_DIR", tmp_path,
        )
        monkeypatch.setattr(
            "src.enhancer.reviewer._REJECTED_DIR", tmp_path / "rejected",
        )
        path = _write_pending(
            tmp_path, relevance_score=0.85,
            body=(
                "# 높은 점수 스킬\n\n"
                "즉시 적용 가능한 구체적 패턴입니다. "
                "워크플로우 개선에 직접 기여하며 "
                "충분히 긴 내용을 담고 있습니다. "
                "함수가 20줄을 초과하면 반드시 분리하고 "
                "단일 책임 원칙을 준수하도록 합니다."
            ),
        )
        reviewer = EnhancementReviewer(_make_mock_config(str(tmp_path)))
        result = reviewer.review([path])

        assert len(result.approved) == 1

    def test_weak_expressions_reduce_score(self, tmp_path, monkeypatch):
        """약한 표현이 많으면 최종 점수가 낮아져 거부될 수 있다."""
        monkeypatch.setattr(
            "src.enhancer.reviewer._PENDING_DIR", tmp_path,
        )
        monkeypatch.setattr(
            "src.enhancer.reviewer._REJECTED_DIR", tmp_path / "rejected",
        )
        # 경계값(0.7) 근처에서 약한 표현 감점으로 0.6 미만 도달 가능
        path = _write_pending(
            tmp_path, relevance_score=0.70,
            body=(
                "# 일반적 참고 내용\n\n"
                "이것은 일반적 참고 교양 정보성 알아두면 좋은 내용입니다. "
                "참고하면 좋은 수준의 도움이 될 수 있는 일반적 조언입니다. "
                "추가로 충분한 길이를 위한 텍스트입니다."
            ),
        )
        reviewer = EnhancementReviewer(_make_mock_config(str(tmp_path)))
        result = reviewer.review([path])

        assert len(result.approved) == 0
        assert "최종 점수" in result.rejected[0][1]


# ------------------------------------------------------------------
# 중복 검사(dedup) 테스트
# ------------------------------------------------------------------

class TestDedup:
    """기존 파일 대비 중복 및 배치 내 중복을 검증한다."""

    def test_reject_existing_skill_name(self, tmp_path, monkeypatch):
        """기존 skill과 동일 이름은 거부되어야 한다."""
        monkeypatch.setattr(
            "src.enhancer.reviewer._PENDING_DIR", tmp_path,
        )
        monkeypatch.setattr(
            "src.enhancer.reviewer._REJECTED_DIR", tmp_path / "rejected",
        )
        # 기존 skill 파일 생성
        skills_dir = tmp_path / ".claude" / "skills"
        skills_dir.mkdir(parents=True)
        (skills_dir / "existing_skill.md").write_text(
            "---\ndescription: 기존 스킬\n---\n# existing_skill\n",
            encoding="utf-8",
        )

        path = _write_pending(
            tmp_path, name="existing_skill",
            body=(
                "# existing_skill\n\n"
                "이 스킬은 기존에 이미 존재하는 이름입니다. "
                "중복 검사에서 거부되어야 합니다. "
                "충분히 긴 내용을 담고 있으며 "
                "구체적 패턴과 워크플로우를 포함하지만 "
                "이미 동일한 이름의 스킬이 프로젝트에 존재합니다."
            ),
        )
        reviewer = EnhancementReviewer(_make_mock_config(str(tmp_path)))
        result = reviewer.review([path])

        assert len(result.approved) == 0
        assert "동일 이름" in result.rejected[0][1]

    def test_batch_dedup_keeps_higher_score(self, tmp_path, monkeypatch):
        """배치 내 중복 시 높은 점수의 항목만 유지해야 한다."""
        monkeypatch.setattr(
            "src.enhancer.reviewer._PENDING_DIR", tmp_path,
        )
        monkeypatch.setattr(
            "src.enhancer.reviewer._REJECTED_DIR", tmp_path / "rejected",
        )
        path_low = _write_pending(
            tmp_path, name="dup_skill", relevance_score=0.75,
            action_type="create_skill",
            body=(
                "# dup_skill (낮은 점수)\n\n"
                "이 강화는 중복 스킬의 낮은 점수 버전입니다. "
                "배치 내 중복 검사에서 제거되어야 합니다. "
                "충분히 긴 내용을 담고 있으며 "
                "구체적인 코드 패턴과 적용 가이드를 포함합니다."
            ),
        )
        # 같은 이름으로 두 번째 파일 (다른 파일명)
        path_high = tmp_path / "merge_skill_dup_skill.md"
        path_high.write_text(
            "---\n"
            "action_type: merge_skill\n"
            "name: dup_skill\n"
            "target: .claude/skills/dup_skill.md\n"
            "relevance_score: 0.9\n"
            "---\n\n"
            "# dup_skill (높은 점수)\n\n"
            "이 강화는 중복 스킬의 높은 점수 버전입니다. "
            "배치 내 중복 검사에서 유지되어야 합니다. "
            "충분히 긴 내용을 담고 있으며 "
            "구체적인 코드 패턴과 워크플로우를 포함합니다.\n",
            encoding="utf-8",
        )
        reviewer = EnhancementReviewer(_make_mock_config(str(tmp_path)))
        result = reviewer.review([path_low, path_high])

        assert len(result.approved) == 1
        # 높은 점수(0.9) 파일이 유지되어야 함
        assert result.approved[0] == path_high


# ------------------------------------------------------------------
# 통합 테스트(integration test)
# ------------------------------------------------------------------

class TestIntegration:
    """여러 항목 중 일부만 통과하는 시나리오를 검증한다."""

    def test_mixed_items(self, tmp_path, monkeypatch):
        """다양한 항목 중 유효한 것만 통과해야 한다."""
        monkeypatch.setattr(
            "src.enhancer.reviewer._PENDING_DIR", tmp_path,
        )
        monkeypatch.setattr(
            "src.enhancer.reviewer._REJECTED_DIR", tmp_path / "rejected",
        )
        paths: list[Path] = []

        # 1. 통과해야 할 유효 항목
        paths.append(_write_pending(
            tmp_path, name="valid_skill", relevance_score=0.85,
            body=(
                "# valid_skill\n\n"
                "즉시 적용 가능한 구체적 패턴입니다. "
                "워크플로우 개선에 직접 기여하며 "
                "충분히 긴 내용을 담고 있습니다. "
                "함수가 20줄을 초과하면 반드시 분리하고 "
                "단일 책임 원칙을 준수하도록 합니다."
            ),
        ))

        # 2. raw_fallback → 거부
        paths.append(_write_pending(
            tmp_path, name="fallback_item",
            action_type="raw_fallback",
            body=(
                "# 원본 응답\n\n파싱 실패한 AI 응답이며 "
                "충분히 긴 텍스트를 포함하고 있습니다. "
                "자동 파싱이 실패했습니다. "
                "이 내용은 수동 검토가 필요하며 "
                "자동 적용 대상이 아닙니다."
            ),
        ))

        # 3. 낮은 점수 → 거부
        paths.append(_write_pending(
            tmp_path, name="low_score",
            relevance_score=0.3,
            body=(
                "# low_score\n\n"
                "관련성이 낮은 정보성 콘텐츠입니다. "
                "AI 워크플로우 개선과 무관한 내용이며 "
                "충분히 긴 텍스트를 담고 있습니다. "
                "실질적 코드 개선 효과가 미미하고 "
                "토큰 대비 가치가 낮은 내용입니다."
            ),
        ))

        # 4. 짧은 내용 → 거부
        paths.append(_write_pending(
            tmp_path, name="short_content", body="짧다",
        ))

        reviewer = EnhancementReviewer(_make_mock_config(str(tmp_path)))
        result = reviewer.review(paths)

        assert len(result.approved) == 1
        assert result.approved[0].stem.endswith("valid_skill")
        assert len(result.rejected) == 3

    def test_rejected_files_moved(self, tmp_path, monkeypatch):
        """거부된 파일은 rejected/ 디렉토리로 이동되어야 한다."""
        rejected_dir = tmp_path / "rejected"
        monkeypatch.setattr(
            "src.enhancer.reviewer._PENDING_DIR", tmp_path,
        )
        monkeypatch.setattr(
            "src.enhancer.reviewer._REJECTED_DIR", rejected_dir,
        )
        path = _write_pending(
            tmp_path, name="bad_item",
            action_type="raw_fallback",
            body=(
                "# 원본 응답\n\n파싱 실패한 AI 응답 원문이 여기에 있으며 "
                "충분히 긴 텍스트를 포함하고 있습니다."
            ),
        )
        reviewer = EnhancementReviewer(_make_mock_config(str(tmp_path)))
        reviewer.review([path])

        # 원본은 삭제됨
        assert not path.exists()
        # rejected/에 이동됨
        rejected_files = list(rejected_dir.glob("*.md"))
        assert len(rejected_files) == 1

    def test_rejected_file_has_reason_in_frontmatter(
        self, tmp_path, monkeypatch,
    ):
        """거부된 파일의 frontmatter에 rejection_reason이 추가되어야 한다."""
        rejected_dir = tmp_path / "rejected"
        monkeypatch.setattr(
            "src.enhancer.reviewer._PENDING_DIR", tmp_path,
        )
        monkeypatch.setattr(
            "src.enhancer.reviewer._REJECTED_DIR", rejected_dir,
        )
        path = _write_pending(
            tmp_path, name="rejected_item",
            action_type="raw_fallback",
            body=(
                "# 원본 응답\n\n파싱 실패한 AI 응답 원문이 여기에 있으며 "
                "충분히 긴 텍스트를 포함하고 있습니다."
            ),
        )
        reviewer = EnhancementReviewer(_make_mock_config(str(tmp_path)))
        reviewer.review([path])

        rejected_file = list(rejected_dir.glob("*.md"))[0]
        content = rejected_file.read_text(encoding="utf-8")
        assert "rejection_reason" in content

    def test_empty_list_returns_empty(self, tmp_path, monkeypatch):
        """빈 리스트 입력 시 빈 결과를 반환해야 한다."""
        monkeypatch.setattr(
            "src.enhancer.reviewer._PENDING_DIR", tmp_path,
        )
        monkeypatch.setattr(
            "src.enhancer.reviewer._REJECTED_DIR", tmp_path / "rejected",
        )
        reviewer = EnhancementReviewer(_make_mock_config(str(tmp_path)))
        result = reviewer.review([])

        assert len(result.approved) == 0
        assert len(result.rejected) == 0


# ------------------------------------------------------------------
# classify_scope 단위 테스트
# ------------------------------------------------------------------

class TestClassifyScope:
    """classify_scope() 함수의 broad/narrow 분류를 검증한다."""

    def test_classify_scope_broad(self):
        """broad 지표(indicator)가 포함된 본문은 'broad'를 반환한다."""
        body = (
            "함수 분리와 에러 처리를 개선하는 범용 패턴입니다. "
            "단일 책임 원칙을 준수하고 코드 리뷰 시 확인할 항목입니다."
        )
        assert classify_scope(body, "code_quality") == "broad"

    def test_classify_scope_narrow(self):
        """narrow 지표가 포함된 본문은 'narrow'를 반환한다."""
        body = (
            "pandas.dataframe의 apply 메서드와 torch.nn 레이어 설정, "
            "tf.keras 모델 컴파일 시 --no-cache-dir 플래그를 사용한다."
        )
        assert classify_scope(body, "ml_pipeline") == "narrow"

    def test_classify_scope_default_broad(self):
        """지표가 전혀 없는 본문은 기본값 'broad'를 반환한다."""
        body = "이것은 특별한 키워드가 없는 일반 텍스트입니다."
        assert classify_scope(body, "generic") == "broad"


# ------------------------------------------------------------------
# _check_scope 범위 필터(scope filter) 테스트
# ------------------------------------------------------------------

class TestCheckScope:
    """reviewer._check_scope()의 범위 기반 거부/통과를 검증한다."""

    @pytest.fixture(autouse=True)
    def _patch_dirs(self, tmp_path, monkeypatch):
        """reviewer 경로를 tmp_path로 패치한다."""
        monkeypatch.setattr(
            "src.enhancer.reviewer._PENDING_DIR", tmp_path,
        )
        monkeypatch.setattr(
            "src.enhancer.reviewer._REJECTED_DIR", tmp_path / "rejected",
        )

    def test_check_scope_rejects_narrow_rule(self, tmp_path):
        """add_rule에 narrow 내용이면 거부되어야 한다."""
        path = _write_pending(
            tmp_path,
            name="pandas_tips",
            action_type="add_rule",
            body=(
                "# pandas 최적화 규칙\n\n"
                "pandas.dataframe에서 apply 대신 vectorize를 사용하고 "
                "numpy.array로 변환 후 torch.nn 레이어에 전달한다. "
                "tf.keras 모델 학습 시 --no-cache-dir 플래그를 설정한다. "
                "python 3.12의 새로운 기능을 활용하여 성능을 개선한다."
            ),
        )
        reviewer = EnhancementReviewer(_make_mock_config(str(tmp_path)))
        result = reviewer.review([path])

        assert len(result.approved) == 0
        assert any("scope_filter" in r[1] for r in result.rejected)

    def test_check_scope_allows_broad_rule(self, tmp_path):
        """add_rule에 broad 내용이면 통과해야 한다."""
        path = _write_pending(
            tmp_path,
            name="clean_code_rule",
            action_type="add_rule",
            body=(
                "# 클린 코드 규칙\n\n"
                "함수 분리 원칙을 준수하고 에러 처리를 강화한다. "
                "테스트 작성 시 단일 책임 원칙을 지키며 "
                "코드 리뷰에서 네이밍과 가독성을 확인한다. "
                "의존성 주입으로 관심사 분리를 달성한다."
            ),
        )
        reviewer = EnhancementReviewer(_make_mock_config(str(tmp_path)))
        result = reviewer.review([path])

        assert len(result.approved) == 1

    def test_check_scope_allows_narrow_skill(self, tmp_path):
        """create_skill은 narrow 내용이어도 scope 필터를 통과해야 한다."""
        path = _write_pending(
            tmp_path,
            name="pandas_skill",
            action_type="create_skill",
            body=(
                "# pandas 데이터 처리 스킬\n\n"
                "pandas.dataframe에서 apply 대신 vectorize를 사용하고 "
                "numpy.array로 변환 후 torch.nn 레이어에 전달한다. "
                "tf.keras 모델 학습 시 --no-cache-dir 플래그를 설정한다. "
                "python 3.12의 새로운 기능을 활용하여 성능을 개선한다."
            ),
        )
        # Python 프로젝트로 시뮬레이션(simulation)하여 스택 불일치 필터를 통과시킴
        (tmp_path / "requirements.txt").write_text("pandas\n", encoding="utf-8")

        reviewer = EnhancementReviewer(_make_mock_config(str(tmp_path)))
        result = reviewer.review([path])

        # scope_filter 사유로 거부되지 않아야 함
        scope_rejects = [r for r in result.rejected if "scope_filter" in r[1]]
        assert len(scope_rejects) == 0

    def test_check_scope_rejects_narrow_reasoning_rule(self, tmp_path):
        """reasoning_rule에 narrow 내용이면 거부되어야 한다."""
        path = _write_pending(
            tmp_path,
            name="react_hooks_reasoning",
            action_type="reasoning_rule",
            body=(
                "# React Hooks 추론 규칙\n\n"
                "react.useeffect 의존성 배열에서 vue.computed와 "
                "angular.module 패턴을 참고하여 최적화한다. "
                "express.router 미들웨어 체인과 --legacy-peer-deps "
                "플래그 설정으로 호환성을 확보한다."
            ),
        )
        reviewer = EnhancementReviewer(_make_mock_config(str(tmp_path)))
        result = reviewer.review([path])

        assert len(result.approved) == 0
        assert any("scope_filter" in r[1] for r in result.rejected)
