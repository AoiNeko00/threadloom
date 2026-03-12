"""심사(review) 상수 및 설정 데이터 모듈.

reviewer.py에서 사용하는 상수 데이터를 분리하여 관리한다.
"""

# 기술 스택(tech stack) 감지용 파일 → 키워드 매핑
STACK_DETECTORS: dict[str, list[str]] = {
    "requirements.txt": ["python", "pip", "django", "flask", "fastapi"],
    "pyproject.toml": ["python", "pip", "django", "flask", "fastapi"],
    "setup.py": ["python", "pip"],
    "package.json": ["javascript", "typescript", "node", "react", "vue",
                      "angular", "nextjs", "express"],
    "pubspec.yaml": ["flutter", "dart"],
    "Cargo.toml": ["rust", "cargo", "axum", "actix"],
    "go.mod": ["go", "golang"],
    "Gemfile": ["ruby", "rails"],
    "pom.xml": ["java", "maven", "spring"],
    "build.gradle": ["java", "kotlin", "gradle", "android"],
}

# 기술 스택별 관련 키워드(related keywords)
STACK_KEYWORDS: dict[str, list[str]] = {
    "python": [
        "python", "pip", "django", "flask", "fastapi", "pytest", "mypy",
        "poetry", "venv", "pydantic",
    ],
    "javascript": [
        "javascript", "typescript", "node", "npm", "yarn", "react", "vue",
        "angular", "nextjs", "express", "jsx", "tsx", "css", "tailwind",
        "component", "webpack", "vite",
    ],
    "flutter": [
        "flutter", "dart", "widget", "pubspec", "build_runner",
    ],
    "rust": [
        "rust", "cargo", "crate", "axum", "actix", "tokio",
    ],
    "go": [
        "go", "golang", "goroutine", "gin",
    ],
    "ruby": [
        "ruby", "rails", "gem", "bundler",
    ],
    "java": [
        "java", "spring", "maven", "gradle", "kotlin", "android",
    ],
}

# AI 메타 응답(meta response) 감지 패턴
META_RESPONSE_PATTERNS: list[str] = [
    r"권한\s*요청",
    r"파일\s*쓰기를\s*허용",
    r"허가해\s*주",
    r"실행\s*권한",
    r"도구\s*호출",
    r"tool\s*use",
    r"file\s*write.*permission",
    r"allow\s*me\s*to",
]

# 약한 표현(weak expression) — 감점 대상 (한/영 모두 지원)
WEAK_EXPRESSIONS: list[str] = [
    # 한국어
    "일반적", "참고", "교양", "정보성", "알아두면",
    "참고하면 좋", "도움이 될 수",
    # 영어
    "general", "reference", "informational", "good to know",
    "might be useful", "for reference",
]

# 강한 표현(strong expression) — 가점 대상 (한/영 모두 지원)
STRONG_EXPRESSIONS: list[str] = [
    # 한국어
    "즉시 적용", "구체적 패턴", "워크플로우", "반드시",
    "구체적 조건", "행동 매핑",
    # 영어
    "immediately applicable", "specific pattern", "workflow",
    "must", "concrete condition", "action mapping",
]
