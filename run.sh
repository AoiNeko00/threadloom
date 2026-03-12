#!/usr/bin/env bash
# threadloom CLI 실행 스크립트(batch script)
# 사용법: ./run.sh --review | --dry-run | --setup-auth

# 스크립트 위치 기준으로 프로젝트 루트(project root) 경로 설정
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 가상환경(virtual environment) 존재 확인
if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    echo "[오류] .venv 디렉토리가 없습니다."
    echo "먼저 setup.sh를 실행해 주세요: ./setup.sh"
    exit 1
fi

# PYTHONPATH 설정 후 모든 인자(arguments) 전달
PYTHONPATH="$SCRIPT_DIR" "$SCRIPT_DIR/.venv/bin/python3" "$SCRIPT_DIR/src/main.py" "$@"
