"""AI 프롬프트 템플릿(prompt templates).

모든 어댑터가 공유하는 프롬프트 빌더.
프롬프트는 영어로 작성하고, 응답 언어만 config의 ai.language를 따른다.
"""

# 언어 코드(language code) → 표시명 매핑
_LANG_NAMES: dict[str, str] = {
    "ko": "Korean",
    "en": "English",
    "ja": "Japanese",
    "zh": "Chinese",
}


def _lang_instruction(language: str) -> str:
    """응답 언어 지시(instruction) 문자열을 생성한다."""
    name = _LANG_NAMES.get(language, language)
    return f"Respond in {name}. All summaries, descriptions, and analysis text must be in {name}."


# ── Phase 2 분석(analyze) 프롬프트 헬퍼 ──


def _analyze_instructions() -> str:
    """분석 지시사항(instructions) 섹션을 생성한다."""
    return """## Instructions
For each post, analyze the following:
- Classification (category, tags)
- Summary (3 lines or less)
- Relevance score (0.0~1.0): how useful this is for enhancing an AI coding assistant
  Anchor criteria:
  - 0.9: Immediately applicable, specific code patterns or CLI usage
  - 0.7: Workflow improvement ideas (requires some adaptation)
  - 0.4: General advice or tips (lacking specificity)
  - 0.2: Low-relevance informational content
- Actionable: does it contain concrete code patterns, workflows, or configuration methods?
- Enhancement type:
  - skill: repeatable single-task pattern (e.g., "Playwright session save/restore", "test automation")
  - agent: multi-step specialized role definition (e.g., "security code reviewer", "performance optimizer")
  - rule: coding rule, convention, or restriction (e.g., "no bare except", "max 20 lines per function")
  - none: informational content that doesn't fit any of the above
- Proposed name (snake_case)
- Reasoning

At the end, add an "Enhancement Proposal Summary" table.
Group posts on the same topic into a single enhancement unit.
A single post can be proposed as an enhancement candidate if it's specific enough."""


def _analyze_output_format() -> str:
    """분석 결과 출력 형식(output format) 섹션을 생성한다."""
    return """Respond in the following markdown format:

---
source: (raw md file path)
analyzed_at: (current timestamp)
total: (total post count)
actionable: (actionable post count)
enhance_candidates: (enhancement candidate count)
---

# Analysis Results — (date)

## post-{ORIGINAL_ID}
- **Classification**: (category)
- **Tags**: [(tag list)]
- **Summary**: (3 lines or less)
- **Relevance**: (0.0~1.0)
- **Actionable**: (true/false)
- **Enhancement type**: (skill/agent/rule/none)
- **Proposed name**: (snake_case name)
- **Reasoning**: (justification)

IMPORTANT: post-{ORIGINAL_ID} must use the EXACT post_id from the raw data (e.g., post-25905b5a9fb97e2a).
Do NOT replace original IDs with sequential numbers like post-001, post-002.

---

(repeat...)

## Enhancement Proposal Summary

| # | Type | Name | Source Posts | Score |
|---|------|------|-------------|-------|
| 1 | ... | ... | ... | ... |"""


def build_analyze_prompt(
    raw_content: str, context_summary: str, language: str,
) -> str:
    """Phase 2 분석 프롬프트(prompt) 생성."""
    return f"""Analyze the following saved Threads posts.

{_lang_instruction(language)}

## Existing AI Configuration Summary
{context_summary}

## Collected Posts (Raw)
{raw_content}

{_analyze_instructions()}

{_analyze_output_format()}
"""


# ── Phase 3 강화(enhance) 프롬프트 헬퍼 ──


def _build_target_projects_section(
    target_projects: list[dict],
) -> str:
    """다중 프로젝트(multi-project) 라우팅용 프롬프트 섹션을 생성한다."""
    if len(target_projects) < 2:
        return ""
    lines = [
        "\n## Available Target Projects",
        "Each enhancement MUST include a `target_project` field in its frontmatter.",
        "Choose the most relevant project for each enhancement:\n",
    ]
    for proj in target_projects:
        name = proj.get("name", "unknown")
        tags = proj.get("tags", [])
        tag_str = ", ".join(tags) if tags else "none"
        lines.append(f'- "{name}": tags=[{tag_str}]')
    return "\n".join(lines) + "\n"


def _enhance_instructions() -> str:
    """강화 생성 지시사항(instructions) 섹션을 생성한다."""
    return """## Instructions
For each item in the "Enhancement Proposal Summary" table:

1. Compare with existing files to determine duplication:
   - Exact duplicate (no new insight) -> skip (do not generate)
   - Partial overlap or can enhance existing -> refine (evolve based on existing content)
     - When refining, MUST include the entire existing file content, integrating new insights
     - Do NOT delete existing instructions; instead add more specific conditions or examples
     - Mark changed sections with `<!-- refined: {{date}} | source: {{post ID}} -->` comments
   - New -> create_new (generate full file content)

   When refining, do NOT degrade the existing skill's quality.
   Preserve the specificity of existing content while adding new conditions/examples/edge cases only.
   Summarizing or abstracting existing content is FORBIDDEN.

2. For non-skip items, generate file content in the following format.
   Each file starts with `---THREADLOOM_FILE_START: {{action_type}}_{{name}}---`
   and ends with `---THREADLOOM_FILE_END---`."""


def _enhance_file_formats() -> str:
    """강화 파일 형식(file format) 섹션을 생성한다."""
    return """3. Skill file format:
   ---
   description: (one-line description)
   source: threadloom
   created: (date)
   ---
   # (name)
   (specific instructions for the AI to follow)
   ## Source
   (source post information)

4. Agent file format:
   ---
   description: (one-line role description)
   source: threadloom
   created: (date)
   ---
   # (name)
   (role, tools, behavioral rules)

5. Rules generate content for the ## threadloom-rules section of CLAUDE.md only:
   ### (rule name)
   <!-- threadloom: (date) | source: (post ID) -->
   (rule content)

6. You MUST check for **conflicts** with existing rules:
   - If semantically conflicting with an existing rule, mark as `conflict` + explain the conflict
   - Do NOT generate conflicting items; record the conflict reason only

Include frontmatter with action_type, name, target, duplicate_check, and conflict result for each file."""


def _enhance_verification() -> str:
    """자기 검증(self-verification) 기준 섹션을 생성한다."""
    return """## Mandatory Self-Verification Criteria (do NOT generate if these fail)

1. **Tech stack match**: Is this directly relevant to the target project's tech stack?
   - Do NOT generate patterns for unrelated tech stacks, no matter how good they are
2. **Immediate applicability**: Will the AI coding assistant's behavior improve the moment this is applied?
   - "Good to know" level content should NOT be generated
   - Must be at the level of "when X, always do Y"
3. **Specificity**: Does it contain concrete condition->action mappings, not vague advice?
   - "Write clean code" <- REJECT
   - "Split functions exceeding 20 lines" <- PASS
4. **Cost-benefit**: Is this enhancement worth the tokens it will occupy in .claude/ context?
   - Do NOT generate if the content is already common knowledge

Include relevance_score (0.0~1.0) in each file's frontmatter.
Skip any item scoring below 0.7."""


def build_enhance_prompt(
    analysis_content: str,
    existing_summary: str,
    language: str,
    target_projects: list[dict] | None = None,
) -> str:
    """Phase 3 강화 생성 프롬프트 생성."""
    project_section = ""
    if target_projects:
        project_section = _build_target_projects_section(target_projects)
    return f"""Generate AI configuration enhancement files based on the analysis below.

{_lang_instruction(language)}

## Analysis Results
{analysis_content}

## Existing Configuration Files (for duplicate checking)
{existing_summary}
{project_section}
{_enhance_instructions()}

{_enhance_file_formats()}

{_enhance_verification()}
"""
