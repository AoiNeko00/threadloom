"""Obsidian vault에 분석 결과를 마크다운(markdown) 파일로 저장하는 모듈.

analysis md를 파싱하여 daily, by-tag, archive 파일을 생성한다.
"""

import re
from datetime import date
from pathlib import Path

from src.config import Config
from src.utils.i18n import t
from src.utils.logger import get_logger
from src.utils.paths import PROJECT_ROOT, RAW_DIR
from src.utils.post_block_parser import parse_post_blocks, parse_tag_list

# 중앙 경로(centralized path) 모듈에서 가져옴
_PROJECT_ROOT: Path = PROJECT_ROOT
_RAW_DIR: Path = RAW_DIR

_logger = get_logger("writer.obsidian")


class ObsidianWriter:
    """Obsidian vault에 .md 파일을 생성하는 작성기(writer)."""

    def __init__(self, config: Config) -> None:
        self._vault = Path(config.vault_path)
        self._folders = config.obsidian_folders

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def write_all(
        self, analysis_md_path: Path,
    ) -> dict[str, list[Path]]:
        """analysis md를 파싱하여 daily, by-tag, archive 파일 생성.

        Returns:
            {"daily": [Path], "by_tag": [Path], "archive": [Path]}
        """
        posts = self._parse_analysis_md(analysis_md_path)
        raw_meta = self._load_raw_metadata(analysis_md_path)
        for post in posts:
            pid = post.get("post_id", "")
            # raw의 post_id에는 'post-' 접두사가 없으므로 양쪽 모두 시도
            meta = raw_meta.get(pid) or raw_meta.get(
                pid.removeprefix("post-"),
            )
            # 순차 ID(post-001 등)는 해시 매칭 불가 → 작성자 기반 매칭
            if not meta:
                meta = self._fuzzy_match_raw(post, raw_meta)
            if not meta:
                continue
            post["raw_body"] = meta.get("body", "")
            if not post.get("author") or post["author"] == "unknown":
                post["author"] = meta.get("author", "unknown")
            # 헤더 작성자(header_author)가 있으면 우선 적용
            if post.get("header_author"):
                # "olive.r_327 — 설명" 형태에서 작성자만 추출
                ha = post["header_author"].split("—")[0].split("–")[0].strip()
                if ha and ha != post.get("author", "unknown"):
                    post["author"] = ha
            if not post.get("url"):
                post["url"] = meta.get("url", "")
        today = date.today()
        result: dict[str, list[Path]] = {
            "daily": [], "by_tag": [], "archive": [],
        }

        if not posts:
            _logger.info(t("writer.no_posts"))
            return result

        # daily 파일 (하루 전체)
        daily_path = self.write_daily(today, posts)
        result["daily"].append(daily_path)

        # by-tag 파일 (태그별)
        tags = self._collect_tags(posts)
        for tag in tags:
            tagged = [p for p in posts if tag in p.get("tags", [])]
            path = self.write_by_tag(tag, tagged)
            result["by_tag"].append(path)

        # archive 파일 (포스트별)
        for post in posts:
            path = self.write_archive(post)
            result["archive"].append(path)

        _logger.info(
            t("writer.obsidian_done",
              daily=len(result["daily"]),
              by_tag=len(result["by_tag"]),
              archive=len(result["archive"])),
        )
        return result

    def write_daily(
        self, target_date: date, posts: list[dict],
    ) -> Path:
        """threadloom/daily/YYYY-MM-DD.md 파일을 생성한다."""
        folder = self._vault / self._folders.get("daily", "threadloom/daily")
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{target_date.isoformat()}.md"

        content = self._build_daily_content(target_date, posts)
        self._safe_append(path, content)
        _logger.info(t("writer.daily_saved", name=path.name))
        return path

    def write_by_tag(
        self, tag: str, posts: list[dict],
    ) -> Path:
        """threadloom/by-tag/{태그명}.md 파일에 추가(append)한다."""
        folder = self._vault / self._folders.get("by_tag", "threadloom/by-tag")
        folder.mkdir(parents=True, exist_ok=True)
        # 파일명에 슬래시(slash)가 있으면 하이픈으로 치환
        safe_name = tag.replace("/", "-")
        path = folder / f"{safe_name}.md"

        content = self._build_by_tag_section(tag, posts)
        self._safe_append(path, content)
        _logger.info(t("writer.bytag_saved", name=path.name))
        return path

    def write_archive(self, post: dict) -> Path:
        """archive/{category}/{post_id}.md 파일을 생성한다.

        카테고리별 하위 폴더에 저장하며, 이미 존재하면 건너뛴다.
        """
        base_folder = self._vault / self._folders.get(
            "archive", "threadloom/archive",
        )
        # 카테고리별 하위 폴더(subfolder) 생성
        category = post.get("category", "other")
        safe_cat = category.replace("/", "-")
        folder = base_folder / safe_cat
        folder.mkdir(parents=True, exist_ok=True)

        post_id = post.get("post_id", "unknown")
        path = folder / f"{post_id}.md"

        if path.exists():
            _logger.debug(t("writer.archive_skip", id=post_id))
            return path

        content = self._build_archive_content(post)
        path.write_text(content, encoding="utf-8")
        _logger.info(t("writer.archive_saved", id=post_id))
        return path

    def dry_run_report(self, analysis_md_path: Path) -> str:
        """실제 쓰기 없이 요약 문자열(summary string)을 반환한다."""
        posts = self._parse_analysis_md(analysis_md_path)
        if not posts:
            return t("writer.no_posts_for_report")

        tags = self._collect_tags(posts)
        categories = self._count_categories(posts)

        lines = [
            t("writer.dry_run_title"),
            f"  {t('writer.post_count', n=len(posts))}",
            f"  {t('writer.daily_file_count', n=1)}",
            f"  {t('writer.bytag_file_count', n=len(tags), tags=', '.join(tags))}",
            f"  {t('writer.archive_file_count', n=len(posts))}",
            f"  {t('writer.category_dist')}",
        ]
        for cat, count in sorted(
            categories.items(), key=lambda x: -x[1],
        ):
            lines.append(f"    {cat}: {count}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # analysis md 파싱(parsing)
    # ------------------------------------------------------------------

    def _parse_analysis_md(self, path: Path) -> list[dict]:
        """analysis md에서 포스트별 데이터를 추출한다.

        각 포스트 블록은 `## post-NNN` 헤더로 시작하며,
        `- **필드명**: 값` 형식의 항목을 파싱한다.
        """
        text = path.read_text(encoding="utf-8")
        # raw md 원문 참조를 위해 source 파일 경로 추출
        source_match = re.search(r"^source:\s*(.+)$", text, re.MULTILINE)
        source_name = source_match.group(1).strip() if source_match else ""

        return self._extract_post_blocks(text, source_name)

    def _extract_post_blocks(
        self, text: str, source_name: str,
    ) -> list[dict]:
        """텍스트에서 `## post-NNN` 블록들을 추출한다."""
        posts = parse_post_blocks(text)
        for post in posts:
            post["source"] = source_name
            # 태그(tags) 파싱: "[태그1, 태그2]" -> list
            raw_tags = post.get("tags", "")
            post["tags"] = parse_tag_list(raw_tags)
        return posts

    @staticmethod
    def _parse_tag_list(raw: str) -> list[str]:
        """하위 호환(backward compatibility)용 위임 메서드."""
        return parse_tag_list(raw)

    # ------------------------------------------------------------------
    # 콘텐츠 빌더(content builder)
    # ------------------------------------------------------------------

    def _build_daily_content(
        self, target_date: date, posts: list[dict],
    ) -> str:
        """daily md 파일 콘텐츠를 생성한다."""
        all_tags = self._collect_tags(posts)
        categories = self._count_categories(posts)

        lines = [
            "---",
            f"date: {target_date.isoformat()}",
            f"collected: {len(posts)}",
            f"tags: [{', '.join(all_tags)}]",
            "source: threadloom",
            "---",
            "",
            f"# Threads Collection — {target_date.isoformat()}",
            "",
        ]

        # 카테고리별 그룹핑(grouping)
        for category, count in sorted(
            categories.items(), key=lambda x: -x[1],
        ):
            lines.append(f"## {category} ({count})")
            lines.append("")
            cat_posts = [
                p for p in posts if p.get("category", "other") == category
            ]
            for post in cat_posts:
                lines.extend(self._format_daily_post(post))

        return "\n".join(lines)

    def _format_daily_post(self, post: dict) -> list[str]:
        """daily md 내 단일 포스트 블록을 생성한다."""
        post_id = post.get("post_id", "unknown")
        title = self._make_title(post)
        author = post.get("author", "unknown")
        summary = post.get("summary", "")
        tags = post.get("tags", [])
        category = post.get("category", "other")
        safe_cat = category.replace("/", "-")
        tag_str = " ".join(f"#{t}" for t in tags)

        return [
            f"### [[archive/{safe_cat}/{post_id}|{title}]]",
            f"> **Author**: @{author}",
            f"> **Source**: {post.get('url', '')}",
            ">",
            f"> {summary}",
            "",
            f"**Tags**: {tag_str}",
            "",
            "---",
            "",
        ]

    def _build_by_tag_section(
        self, tag: str, posts: list[dict],
    ) -> str:
        """by-tag md 내 날짜 섹션을 생성한다."""
        today = date.today().isoformat()
        lines = [
            "",
            f"## {today}",
            "",
        ]
        for post in posts:
            post_id = post.get("post_id", "unknown")
            title = self._make_title(post)
            summary = post.get("summary", "")
            category = post.get("category", "other")
            safe_cat = category.replace("/", "-")
            lines.append(
                f"- [[archive/{safe_cat}/{post_id}|{title}]]: {summary}",
            )

        lines.append("")
        return "\n".join(lines)

    def _build_archive_content(self, post: dict) -> str:
        """archive md 파일 콘텐츠를 생성한다.

        원문 본문(raw body)이 있으면 함께 저장한다.
        """
        post_id = post.get("post_id", "unknown")
        author = post.get("author", "unknown")
        url = post.get("url", "")
        tags = post.get("tags", [])
        category = post.get("category", "other")
        summary = post.get("summary", "")
        relevance = post.get("relevance", "0.0")
        enhance_type = post.get("enhance_type", "none")
        raw_body = post.get("raw_body", "")

        lines = [
            "---",
            f"post_id: {post_id}",
            f"author: {author}",
            f"url: {url}",
            f"tags: [{', '.join(tags)}]",
            f"category: {category}",
            "---",
            "",
            f"# {self._make_title(post)}",
            "",
            f"**Category**: {category}",
            f"**Summary**: {summary}",
            f"**Relevance**: {relevance}",
            f"**Enhancement type**: {enhance_type}",
            "",
        ]

        # 원문 본문(raw body) 포함
        if raw_body:
            lines.extend([
                "---",
                "",
                "## Original",
                "",
                raw_body,
                "",
            ])

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # raw 본문(body) 로더
    # ------------------------------------------------------------------

    def _load_raw_metadata(
        self, analysis_md_path: Path,
    ) -> dict[str, dict]:
        """analysis md의 source 필드에서 raw md를 찾아 메타+본문을 추출한다.

        Returns:
            {post_id: {"author": str, "url": str, "body": str}} 매핑
        """
        text = analysis_md_path.read_text(encoding="utf-8")
        source_match = re.search(
            r"^source:\s*(.+)$", text, re.MULTILINE,
        )
        if not source_match:
            return {}

        raw_name = source_match.group(1).strip()
        # source 값이 상대경로(data/raw/xxx.md)일 수 있으므로 프로젝트 루트 기준 우선 시도
        raw_path = _PROJECT_ROOT / raw_name
        if not raw_path.exists():
            # 파일명만 있는 경우 폴백(fallback)
            raw_path = _RAW_DIR / Path(raw_name).name
        if not raw_path.exists():
            _logger.debug("raw 파일 없음: %s", raw_path)
            return {}

        return self._parse_raw_blocks(raw_path)

    @staticmethod
    def _parse_raw_blocks(raw_path: Path) -> dict[str, dict]:
        """raw md 파일에서 post_id별 메타데이터와 본문을 추출한다."""
        raw_text = raw_path.read_text(encoding="utf-8")
        blocks = raw_text.split("\n---\n")
        result: dict[str, dict] = {}

        for block in blocks:
            pid_match = re.search(
                r"\*\*post_id\*\*:\s*(\S+)", block,
            )
            if not pid_match:
                continue

            post_id = pid_match.group(1)
            # 작성자(author) 추출
            # 영문 필드명 우선, 한국어(하위 호환) 폴백
            author_match = re.search(
                r"\*\*(?:author|작성자)\*\*:\s*@?(\S+)", block,
            )
            author = author_match.group(1) if author_match else "unknown"
            # URL 추출
            url_match = re.search(
                r"\*\*URL\*\*:\s*(\S+)", block,
            )
            url = url_match.group(1) if url_match else ""
            # 메타 필드 이후 본문(body) 추출
            lines = block.strip().split("\n")
            body_lines: list[str] = []
            in_body = False
            for line in lines:
                if in_body:
                    body_lines.append(line)
                elif not line.startswith("**") and line.strip() == "":
                    in_body = True

            result[post_id] = {
                "author": author,
                "url": url,
                "body": "\n".join(body_lines).strip(),
            }

        return result

    # ------------------------------------------------------------------
    # 퍼지 매칭(fuzzy matching) — 순차 ID 포스트를 raw와 대조
    # ------------------------------------------------------------------

    @staticmethod
    def _fuzzy_match_raw(
        post: dict, raw_meta: dict[str, dict],
    ) -> dict | None:
        """순차 ID 포스트를 raw 메타데이터와 작성자/본문 기반으로 매칭한다."""
        # 헤더 작성자(header_author)로 매칭
        header_author = post.get("header_author", "")
        if header_author:
            # "olive.r_327 — 설명" 형태에서 작성자만 추출
            author_part = (
                header_author.split("—")[0].split("–")[0].strip()
            )
            for meta in raw_meta.values():
                if meta["author"] == author_part:
                    return meta

        return None

    # ------------------------------------------------------------------
    # 유틸리티(utility) 헬퍼
    # ------------------------------------------------------------------

    def _make_title(self, post: dict) -> str:
        """포스트 요약에서 제목(title)을 생성한다 (최대 30자)."""
        summary = post.get("summary", "")
        if not summary:
            return post.get("post_id", "unknown")
        # 첫 줄의 앞 30자
        first_line = summary.split("\n")[0]
        if len(first_line) > 30:
            return first_line[:27] + "..."
        return first_line

    def _collect_tags(self, posts: list[dict]) -> list[str]:
        """전체 포스트에서 고유 태그(unique tags)를 수집한다."""
        tags: set[str] = set()
        for post in posts:
            for tag in post.get("tags", []):
                tags.add(tag)
        return sorted(tags)

    def _count_categories(self, posts: list[dict]) -> dict[str, int]:
        """카테고리별 포스트 수를 집계한다."""
        counts: dict[str, int] = {}
        for post in posts:
            cat = post.get("category", "other")
            counts[cat] = counts.get(cat, 0) + 1
        return counts

    def _safe_append(self, path: Path, content: str) -> None:
        """파일이 있으면 내용 추가(append), 없으면 새로 생성한다."""
        if path.exists():
            with open(path, "a", encoding="utf-8") as f:
                f.write(content)
        else:
            path.write_text(content, encoding="utf-8")
