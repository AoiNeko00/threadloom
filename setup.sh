#!/usr/bin/env bash
set -euo pipefail

echo "🧵 threadloom 설치를 시작합니다..."

# Python 버전 확인
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if python3 -c "import sys; exit(0 if sys.version_info >= (3,10) else 1)"; then
  echo "✅ Python ${PYTHON_VERSION} 확인"
else
  echo "❌ Python 3.10 이상이 필요합니다. 현재: ${PYTHON_VERSION}"
  exit 1
fi

# 가상환경 생성
if [ ! -d ".venv" ]; then
  echo "📦 가상환경 생성 중..."
  python3 -m venv .venv
fi

# 의존성 설치
echo "📦 의존성 설치 중..."
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

# Playwright 브라우저 설치
echo "🌐 Playwright 브라우저 설치 중..."
.venv/bin/playwright install chromium

# 디렉토리 생성
mkdir -p auth data/{raw,analysis,pending,backups} logs

# config.yaml 생성 (없는 경우)
if [ ! -f "config.yaml" ]; then
  cp config.example.yaml config.yaml
  echo "📝 config.yaml 생성됨 - target_project.path를 설정하세요"
fi

# .env 생성 (없는 경우)
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "📝 .env 생성됨"
fi

# .gitignore 검증
echo "🔒 보안 검증 중..."
SENSITIVE_FILES=("config.yaml" ".env" "auth/" "data/" "logs/")
for f in "${SENSITIVE_FILES[@]}"; do
  if git ls-files --error-unmatch "$f" 2>/dev/null; then
    echo "⛔ 경고: ${f}이 Git에 추적되고 있습니다! git rm --cached ${f} 실행 필요"
    exit 1
  fi
done

echo ""
echo "✅ 설치 완료!"
echo ""
echo "📋 다음 단계:"
echo "  1. config.yaml 에서 target_project.path 설정"
echo "  2. python3 src/main.py --setup-auth  (최초 1회 Threads 로그인)"
echo "  3. python3 src/main.py --dry-run     (테스트 실행)"
