FROM python:3.11-slim

WORKDIR /app

# 시스템 의존성 설치 (ephem 빌드용)
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 앱 코드 복사
COPY . .

# Railway PORT 환경변수 (기본값 8000)
ENV PORT=8000
EXPOSE $PORT

# 실행
CMD sh -c "uvicorn app.main:app --host 0.0.0.0 --port $PORT"
