"""배치 분할(batch splitting) 모듈.

raw md 파일이 배치 한도를 초과하면 여러 파일로 분할한다.
"""

from pathlib import Path

from src.utils.i18n import t
from src.utils.logger import get_logger

_logger = get_logger("batch_splitter")


def split_raw_file(
    raw_path: Path, max_posts: int, max_chars: int,
) -> list[Path]:
    """raw md 파일이 배치 한도를 초과하면 분할한다.

    Returns:
        분할된 파일 경로 리스트 (한도 이하면 원본 1개 반환)
    """
    text = raw_path.read_text(encoding="utf-8")
    blocks = split_into_post_blocks(text)

    if len(blocks) <= max_posts and len(text) <= max_chars:
        return [raw_path]

    return write_batch_files(raw_path, blocks, max_posts, max_chars)


def split_into_post_blocks(text: str) -> list[str]:
    """raw md에서 '---' 구분자 기준 포스트 블록을 분리한다."""
    parts = text.split("\n---\n")
    # 첫 블록은 헤더(header) 포함
    if len(parts) <= 1:
        return [text]
    header = parts[0]
    return [header] + parts[1:]


def write_batch_files(
    raw_path: Path,
    blocks: list[str],
    max_posts: int,
    max_chars: int,
) -> list[Path]:
    """포스트 블록들을 배치 한도에 맞춰 여러 파일로 분할 저장한다."""
    stem = raw_path.stem
    batch_paths: list[Path] = []
    batch_blocks: list[str] = [blocks[0]]  # 헤더(header) 유지
    batch_chars = len(blocks[0])
    batch_count = 0
    batch_idx = 1

    for block in blocks[1:]:
        block_len = len(block)

        # 단일 포스트(single post)가 max_chars 초과 시 경고 후 단독 배치 처리
        if block_len > max_chars:
            _logger.warning(
                t("batch.oversized_post",
                  max_chars=max_chars, actual=block_len),
            )
            # 현재 배치에 내용이 있으면 먼저 저장
            if batch_count > 0:
                path = save_batch(
                    raw_path.parent, stem, batch_idx, batch_blocks,
                )
                batch_paths.append(path)
                batch_idx += 1

            # 초과 포스트를 단독 배치로 저장
            path = save_batch(
                raw_path.parent, stem, batch_idx, [blocks[0], block],
            )
            batch_paths.append(path)
            batch_blocks = [blocks[0]]
            batch_chars = len(blocks[0])
            batch_count = 0
            batch_idx += 1
            continue

        # 한도 초과 시 현재 배치 저장 후 새 배치 시작
        if batch_count >= max_posts or batch_chars + block_len > max_chars:
            path = save_batch(raw_path.parent, stem, batch_idx, batch_blocks)
            batch_paths.append(path)
            batch_blocks = [blocks[0]]  # 헤더 재포함
            batch_chars = len(blocks[0])
            batch_count = 0
            batch_idx += 1

        batch_blocks.append(block)
        batch_chars += block_len
        batch_count += 1

    # 마지막 배치 저장
    if batch_count > 0:
        path = save_batch(raw_path.parent, stem, batch_idx, batch_blocks)
        batch_paths.append(path)

    _logger.info(t("util.batch_split_done", n=len(batch_paths)))
    return batch_paths


def save_batch(
    directory: Path, stem: str, idx: int, blocks: list[str],
) -> Path:
    """단일 배치를 파일로 저장한다."""
    path = directory / f"{stem}_batch{idx}.md"
    path.write_text("\n---\n".join(blocks), encoding="utf-8")
    return path
