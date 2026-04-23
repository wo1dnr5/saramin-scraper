# 사람인 채용공고 스크래퍼

사람인(saramin.co.kr)에서 채용공고 데이터를 수집하고, Claude AI로 이력서를 분석해 맞춤 직무를 추천하는 Python 프로젝트입니다.

---

## 프로젝트 구조

```
saramin_scraper/
├── scrape_saramin.py          # 메인 스크래퍼 (일반 직무)
├── scrape_saramin_accounting.py  # 회계·세무 특화 스크래퍼
├── resume_job_advisor.py      # 이력서 분석 + 직무 추천 (Claude AI)
├── make_excel.py              # 수집 데이터 → 시각화 엑셀 변환
├── requirements.txt           # Python 패키지 목록
├── Dockerfile                 # Docker 이미지 설정
├── docker-compose.yml         # 멀티 서비스 실행 설정
└── .dockerignore
```

---

## 주요 기능

### 1. 채용공고 수집 (`scrape_saramin.py`)

**2단계 파이프라인으로 동작합니다.**

```
1단계: 검색 리스트 수집 (curl_cffi + BeautifulSoup)
   └── 검색 키워드 × 최대 5페이지 × 40개 = 최대 600개 공고
   └── 수집 항목: 공고ID, 기업명, 공고제목, 직무카테고리,
                  마감일, 지역, 경력, 학력, 고용형태, 배지

2단계: 상세 페이지 수집 (curl_cffi + BeautifulSoup)
   └── 각 공고 링크 방문 → 상세 정보 추출
   └── 수집 항목: 급여, 공고기간, 대표자명, 기업형태,
                  업종, 사원수, 설립일, 매출액, 기업홈페이지, 기업주소

결과: output/saramin_jobs.csv 저장
```

**주요 설정값 (`scrape_saramin.py` 상단)**

| 설정 | 기본값 | 설명 |
|------|--------|------|
| `SEARCH_KEYWORDS` | 솔루션엔지니어, 데이터분석가, 시스템엔지니어 | 검색 키워드 (환경변수 `KEYWORDS`로 override 가능) |
| `MAX_PAGES` | 5 | 키워드당 수집 페이지 수 |
| `LOCATION_CODE` | 101000 | 서울 (경기: 102000, 인천: 103000) |
| `LIST_DELAY` | 50~70초 | 리스트 페이지 요청 간 딜레이 |
| `DETAIL_DELAY` | 50~70초 | 상세 페이지 요청 간 딜레이 |

> **딜레이가 긴 이유**: 사람인 서버의 anti-bot 시스템을 우회하기 위해 요청 간 충분한 대기시간을 줍니다.

---

### 2. 이력서 분석 + 직무 추천 (`resume_job_advisor.py`)

PDF / DOCX / TXT 형식의 이력서를 Claude AI(claude-opus-4-7)로 분석해 사람인 구직에 최적화된 키워드와 직무 분야를 추천합니다.

```bash
# 이력서 분석만
python resume_job_advisor.py --resume 이력서.pdf

# 분석 후 추천 키워드로 자동 수집까지
python resume_job_advisor.py --resume 이력서.pdf --scrape
```

**분석 결과 예시 (`resume_analysis.json`)**

```json
{
  "profile_summary": "데이터 분석 및 시스템 운영 경험 보유 엔지니어",
  "key_skills": ["Python", "SQL", "Linux", "데이터 분석", ...],
  "experience_level": "3~5년차",
  "recommended_fields": [
    {
      "field": "데이터분석가",
      "reason": "...",
      "saramin_keywords": ["데이터분석가", "BI분석가", ...],
      "match_score": 92
    }
  ],
  "top_keywords": ["데이터분석가", "시스템엔지니어", ...]
}
```

> Claude API 키 필요: `export ANTHROPIC_API_KEY='your-key'`

---

### 3. 엑셀 시각화 (`make_excel.py`)

수집된 CSV 데이터를 취업준비생이 보기 편한 엑셀 파일로 변환합니다.

```bash
python make_excel.py
# → output/채용공고_서울.xlsx 생성
```

**생성되는 시트 구성**

| 시트 | 내용 |
|------|------|
| 📋 전체 공고 | 전체 공고 목록, 자동 필터, 공고 링크 클릭 가능 |
| 🔍 솔루션엔지니어 | 키워드별 분리 탭 |
| 🔍 데이터분석가 | 키워드별 분리 탭 |
| 🔍 시스템엔지니어 | 키워드별 분리 탭 |
| 📊 통계 | 검색어별·고용형태별·경력별·지역별 분포 |

---

## 설치 및 실행

### 로컬 실행

```bash
# 패키지 설치
pip install -r requirements.txt

# 채용공고 수집
python scrape_saramin.py

# 엑셀 변환
python make_excel.py
```

### Docker 실행

```bash
# 이미지 빌드
docker compose build

# 일반 스크래퍼 실행
docker compose run --rm scraper

# 회계·세무 스크래퍼 실행
docker compose run --rm scraper-accounting

# 이력서 분석 실행 (resume/ 폴더에 이력서 파일 필요)
docker compose run --rm resume-advisor
```

**환경변수로 키워드/페이지 수 변경 가능:**

```bash
docker compose run --rm -e KEYWORDS=백엔드개발자,프론트엔드개발자 -e MAX_PAGES=3 scraper
```

---

## 기술 스택

| 구분 | 라이브러리 | 역할 |
|------|-----------|------|
| HTTP 요청 | `curl_cffi` | Chrome TLS fingerprint 흉내 → anti-bot 우회 |
| HTML 파싱 | `BeautifulSoup4` + `lxml` | 공고 데이터 추출 |
| AI 분석 | `anthropic` (claude-opus-4-7) | 이력서 분석 및 직무 추천 |
| 엑셀 생성 | `openpyxl` | 시각화 엑셀 파일 생성 |
| 컨테이너 | `Docker` + `docker-compose` | 실행환경 통일 |

---

## 주의사항

- 본 프로젝트는 **학습 목적**으로만 사용하세요.
- 사람인 `robots.txt` 및 이용약관을 준수하세요.
- 수집된 데이터(`output/` 폴더)는 개인정보가 포함될 수 있으므로 외부에 공유하지 마세요.
- `output/` 폴더는 `.gitignore`에 등록되어 있어 GitHub에 업로드되지 않습니다.
