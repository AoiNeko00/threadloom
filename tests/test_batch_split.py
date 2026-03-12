"""배치 분할(batch split) 로직 테스트.

포스트 단위 분할, 초과 포스트 단독 배치 처리 등을 검증한다.
"""

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.utils.batch_splitter import split_into_post_blocks as _split_into_post_blocks
from src.utils.batch_splitter import write_batch_files as _write_batch_files


# ------------------------------------------------------------------
# 헬퍼(helper)
# ------------------------------------------------------------------

def _make_block(size: int, label: str = "post") -> str:
    """지정 크기의 테스트 블록 생성."""
    return f"# {label}\n" + "x" * (size - len(f"# {label}\n"))


# ------------------------------------------------------------------
# _split_into_post_blocks
# ------------------------------------------------------------------

class TestSplitIntoPostBlocks:
    def test_single_block_no_separator(self):
        text = "헤더\n내용만 있는 파일"
        assert _split_into_post_blocks(text) == [text]

    def test_multiple_blocks(self):
        text = "헤더\n---\npost1\n---\npost2"
        blocks = _split_into_post_blocks(text)
        assert len(blocks) == 3
        assert blocks[0] == "헤더"
        assert blocks[1] == "post1"
        assert blocks[2] == "post2"


# ------------------------------------------------------------------
# _write_batch_files — 일반(normal) 분할
# ------------------------------------------------------------------

class TestWriteBatchFiles:
    def test_splits_by_post_count(self, tmp_path):
        raw_path = tmp_path / "raw.md"
        header = "# 헤더"
        blocks = [header, "post1", "post2", "post3", "post4"]
        raw_path.write_text("\n---\n".join(blocks), encoding="utf-8")

        # max_posts=2 → 배치 2개 (2+2)
        paths = _write_batch_files(raw_path, blocks, max_posts=2, max_chars=999999)
        assert len(paths) == 2

        # 각 배치에 헤더 포함 확인
        for p in paths:
            content = p.read_text(encoding="utf-8")
            assert header in content

    def test_splits_by_char_count(self, tmp_path):
        raw_path = tmp_path / "raw.md"
        header = "H"
        blocks = [header, _make_block(100, "p1"), _make_block(100, "p2")]
        raw_path.write_text("\n---\n".join(blocks), encoding="utf-8")

        # max_chars=150 → 헤더(1) + post(100) = 101, 두번째 추가 시 201 > 150
        paths = _write_batch_files(raw_path, blocks, max_posts=999, max_chars=150)
        assert len(paths) == 2

    def test_oversized_single_post(self, tmp_path):
        """단일 포스트가 max_chars 초과 시 단독 배치로 처리."""
        raw_path = tmp_path / "raw.md"
        header = "H"
        small = _make_block(50, "small")
        huge = _make_block(500, "huge")  # max_chars=200 초과
        blocks = [header, small, huge, small]
        raw_path.write_text("\n---\n".join(blocks), encoding="utf-8")

        paths = _write_batch_files(raw_path, blocks, max_posts=999, max_chars=200)
        # small → batch1, huge → batch2 (단독), small → batch3
        assert len(paths) == 3

        # 초과 포스트 배치에 해당 내용 포함 확인
        huge_batch = paths[1].read_text(encoding="utf-8")
        assert "huge" in huge_batch

    def test_oversized_post_at_start(self, tmp_path):
        """첫 포스트가 초과해도 정상 처리."""
        raw_path = tmp_path / "raw.md"
        header = "H"
        huge = _make_block(500, "huge")
        small = _make_block(50, "small")
        blocks = [header, huge, small]
        raw_path.write_text("\n---\n".join(blocks), encoding="utf-8")

        paths = _write_batch_files(raw_path, blocks, max_posts=999, max_chars=200)
        assert len(paths) == 2
