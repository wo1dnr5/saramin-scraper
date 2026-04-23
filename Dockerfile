# Playwright 공식 이미지 사용 — Chromium + 의존 라이브러리 포함
FROM python:3.11-slim

WORKDIR /app

# 의존성 먼저 설치 (코드 변경 시 캐시 재활용)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY scrape_saramin.py .
COPY scrape_saramin_accounting.py .
COPY resume_job_advisor.py .

# 결과 CSV 저장 디렉토리
RUN mkdir -p /app/output

# 기본 실행 명령 (docker run 시 override 가능)
CMD ["python", "scrape_saramin.py"]
