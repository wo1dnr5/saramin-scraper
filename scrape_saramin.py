import os
import csv
import time
import random

from curl_cffi import requests
from bs4 import BeautifulSoup

# ── 설정 ────────────────────────────────────────────────
_kw_env = os.environ.get('KEYWORDS', '')
SEARCH_KEYWORDS = _kw_env.split(',') if _kw_env else ['솔루션엔지니어', '데이터분석가', '시스템엔지니어']
MAX_PAGES       = int(os.environ.get('MAX_PAGES', 5))  # 검색어당 페이지 수 (페이지당 40개)
LIST_DELAY      = (50, 70)  # 리스트 페이지 요청 간 딜레이(초)
DETAIL_DELAY    = (50, 70)  # 상세 페이지 요청 간 딜레이(초)
LIST_RETRY      = 3        # 리스트 페이지 실패 시 재시도 횟수
DETAIL_RETRY    = 3        # 상세 페이지 실패 시 재시도 횟수
BASE_URL        = "https://www.saramin.co.kr"
LOCATION_CODE   = "101000" # 서울 (경기 102000, 인천 103000)
# ────────────────────────────────────────────────────────

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Referer': 'https://www.saramin.co.kr/',
}


def make_session(keyword: str) -> requests.Session:
    """세션 쿠키 확보를 위해 메인 → 검색 페이지 순서로 방문."""
    session = requests.Session(impersonate="chrome120")
    session.headers.update(HEADERS)
    try:
        session.get(BASE_URL, timeout=15)
        time.sleep(random.uniform(1, 2))
        session.get(
            f"{BASE_URL}/zf_user/search/recruit?searchType=search&searchword={keyword}",
            timeout=15,
        )
        time.sleep(random.uniform(1, 2))
    except Exception:
        pass
    return session


# ── 1단계: 검색 리스트 페이지 수집 ─────────────────────────
def scrape_list_page(session: requests.Session, keyword: str, page: int) -> list[dict]:
    url = (
        f"{BASE_URL}/zf_user/search/recruit"
        f"?searchType=search&searchword={keyword}&recruitPage={page}"
        f"&loc_mcd={LOCATION_CODE}"
    )
    for attempt in range(1, LIST_RETRY + 1):
        try:
            res = session.get(url, timeout=20)
            res.raise_for_status()
            break
        except Exception as e:
            print(f"  [리스트] 페이지 {page} 요청 실패 (시도 {attempt}회): {e}")
            if attempt == LIST_RETRY:
                return []
            wait = random.uniform(50, 70)
            print(f"  {wait:.0f}초 대기 후 재시도...")
            time.sleep(wait)
    else:
        return []

    soup  = BeautifulSoup(res.text, 'lxml')
    items = soup.find_all('div', class_='item_recruit')
    jobs  = []

    for item in items:
        rec_idx  = item.get('value', 'N/A')

        title_tag = item.find('h2', class_='job_tit')
        title_a   = title_tag.find('a') if title_tag else None
        title     = title_a.get_text(strip=True) if title_a else 'N/A'
        job_link  = f"{BASE_URL}/zf_user/jobs/relay/view?rec_idx={rec_idx}" if rec_idx != 'N/A' else 'N/A'

        corp_tag  = item.find('strong', class_='corp_name')
        company   = corp_tag.get_text(strip=True) if corp_tag else 'N/A'

        date_tag  = item.find('span', class_='date')
        deadline  = date_tag.get_text(strip=True) if date_tag else 'N/A'

        day_tag   = item.find('span', class_='job_day')
        modified  = day_tag.get_text(strip=True).replace('수정일 ', '') if day_tag else 'N/A'

        cond_tag   = item.find('div', class_='job_condition')
        conditions = [s.get_text(strip=True) for s in cond_tag.find_all('span')] if cond_tag else []
        location   = conditions[0] if len(conditions) > 0 else 'N/A'
        experience = conditions[1] if len(conditions) > 1 else 'N/A'
        education  = conditions[2] if len(conditions) > 2 else 'N/A'
        job_type   = conditions[3] if len(conditions) > 3 else 'N/A'

        sector_tag  = item.find('div', class_='job_sector')
        sectors     = [a.get_text(strip=True) for a in sector_tag.find_all('a')] if sector_tag else []
        job_sectors = ', '.join(sectors) if sectors else 'N/A'

        badge_tag = item.find('span', class_='badge')
        badge     = badge_tag.get_text(strip=True) if badge_tag else ''

        jobs.append({
            '공고ID':       rec_idx,
            '검색어':       keyword,
            '기업명':       company,
            '공고제목':     title,
            '직무카테고리': job_sectors,
            '마감일':       deadline,
            '수정일':       modified,
            '지역':         location,
            '경력':         experience,
            '학력':         education,
            '고용형태':     job_type,
            '배지':         badge,
            '공고링크':     job_link,
            '급여':         '',
            '공고시작일':   '',
            '공고마감일':   '',
            '대표자명':     '',
            '기업형태':     '',
            '업종':         '',
            '사원수':       '',
            '설립일':       '',
            '매출액':       '',
            '기업홈페이지': '',
            '기업주소':     '',
        })

    return jobs


# ── 2단계: 상세 페이지 파싱 ────────────────────────────────
def parse_detail(html: str) -> dict:
    soup   = BeautifulSoup(html, 'lxml')
    result = {}

    summary = soup.find(class_='jv_summary')
    if summary:
        for dl in summary.find_all('dl'):
            dt = dl.find('dt')
            dd = dl.find('dd')
            if dt and dd:
                if dt.get_text(strip=True) == '급여':
                    result['급여'] = dd.get_text(strip=True)

    period = soup.find(class_='info_period')
    if period:
        parts = [p.strip() for p in period.get_text(separator='|', strip=True).split('|') if p.strip()]
        for i, part in enumerate(parts):
            if '시작일' in part and i + 1 < len(parts):
                result['공고시작일'] = parts[i + 1]
            if '마감일' in part and i + 1 < len(parts):
                result['공고마감일'] = parts[i + 1]

    company_section = soup.find(class_='jv_company')
    if company_section:
        field_map = {
            '대표자명': '대표자명', '기업형태': '기업형태', '업종': '업종',
            '사원수': '사원수', '설립일': '설립일', '매출액': '매출액',
            '홈페이지': '기업홈페이지', '기업주소': '기업주소',
        }
        for dl in company_section.find_all('dl'):
            dt = dl.find('dt')
            dd = dl.find('dd')
            if dt and dd:
                key = dt.get_text(strip=True)
                if key in field_map:
                    result[field_map[key]] = dd.get_text(strip=True)

    return result


# ── 3단계: 상세 페이지 수집 (requests 세션) ──────────────────
def enrich_with_details(session: requests.Session, jobs: list[dict]) -> None:
    total = len(jobs)
    for i, job in enumerate(jobs):
        link = job.get('공고링크', '')
        if not link or link == 'N/A':
            continue

        for attempt in range(1, DETAIL_RETRY + 1):
            try:
                res = session.get(link, timeout=15)
                res.raise_for_status()
                detail = parse_detail(res.text)
                job.update(detail)
                print(f"  [{i+1}/{total}] {job['기업명']} - 급여: {detail.get('급여', '-')}")
                break
            except Exception as e:
                if attempt == DETAIL_RETRY:
                    print(f"  [{i+1}/{total}] {job['기업명']} 상세 실패 (시도 {attempt}회): {e}")
                else:
                    time.sleep(random.uniform(*DETAIL_DELAY))

        time.sleep(random.uniform(*DETAIL_DELAY))


# ── 메인 ─────────────────────────────────────────────────
def main():
    all_jobs = []

    for keyword in SEARCH_KEYWORDS:
        print(f"\n[{keyword}] 세션 초기화 중...")
        session = make_session(keyword)
        print(f"[{keyword}] 리스트 수집 시작...")

        for page in range(1, MAX_PAGES + 1):
            jobs = scrape_list_page(session, keyword, page)
            if not jobs:
                print(f"  페이지 {page}: 공고 없음, 종료")
                break
            all_jobs.extend(jobs)
            print(f"  페이지 {page}: {len(jobs)}개 수집 (누적 {len(all_jobs)}개)")
            time.sleep(random.uniform(*LIST_DELAY))

        print(f"  [{keyword}] 완료. 다음 키워드 전 15초 대기...")
        time.sleep(15)

    print(f"\n리스트 수집 완료. 총 {len(all_jobs)}개")

    print("\n상세 페이지 수집 시작 (requests)...")
    session = make_session(SEARCH_KEYWORDS[0])
    enrich_with_details(session, all_jobs)

    os.makedirs('output', exist_ok=True)
    output_file = 'output/saramin_jobs.csv'
    fieldnames = [
        '공고ID', '검색어', '기업명', '공고제목', '직무카테고리',
        '마감일', '수정일', '공고시작일', '공고마감일',
        '지역', '경력', '학력', '고용형태', '급여', '배지',
        '대표자명', '기업형태', '업종', '사원수', '설립일', '매출액',
        '기업홈페이지', '기업주소', '공고링크',
    ]
    with open(output_file, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_jobs)

    print(f"\n완료! 총 {len(all_jobs)}개 공고 → {output_file}")


if __name__ == '__main__':
    main()
