"""프로젝트 경로(path) 상수 중앙 정의.

모든 모듈이 이 파일에서 경로를 import하여 중복 선언을 방지한다.
"""

from pathlib import Path

# 프로젝트 루트(project root) — src/ 의 상위
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent

# 데이터 디렉토리(data directories)
DATA_DIR: Path = PROJECT_ROOT / "data"
RAW_DIR: Path = DATA_DIR / "raw"
ANALYSIS_DIR: Path = DATA_DIR / "analysis"
PENDING_DIR: Path = DATA_DIR / "pending"
REJECTED_DIR: Path = DATA_DIR / "rejected"
BACKUPS_DIR: Path = DATA_DIR / "backups"
ENHANCE_LOG: Path = DATA_DIR / "enhance_log.json"
