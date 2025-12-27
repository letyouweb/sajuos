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

# 🔥 PORT는 Railway가 주입 (하드코딩 금지)
# ENV PORT 제거 - Railway가 동적으로 주입함

# 실행 (Railway가 $PORT 주입)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port $PORT"]
