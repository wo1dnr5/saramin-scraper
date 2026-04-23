import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import csv
import time
import random

# ── 설정 ────────────────────────────────────────────────
SEARCH_KEYWORDS = ['회계', '세무', '세무사', '회계사', '재무회계', '세무회계']
MAX_PAGES       = 5        # 검색어당 페이지 수 (페이지당 40개)
DETAIL_DELAY    = (2, 4)   # 상세 페이지 요청 간 딜레이(초)
DETAIL_RETRY    = 3        # 상세 페이지 실패 시 재시도 횟수
HEADLESS        = True     # False 로 바꾸면 브라우저 화면 표시
BASE_URL        = "https://www.saramin.co.kr"
# ────────────────────────────────────────────────────────

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/120.0.0.0 Safari/537.36'
}


# ── 1단계: 검색 리스트 페이지 수집 (requests) ──────────────
def scrape_list_page(keyword: str, page: int) -> list[dict]:
    url = (
        f"{BASE_URL}/zf_user/search/recruit"
        f"?searchType=search&searchword={keyword}&recruitPage={page}"
    )
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.raise_for_status()
    except requests.RequestException as e:
        print(f"  [리스트] 페이지 {page} 요청 실패: {e}")
        return []

    soup  = BeautifulSoup(res.text, 'lxml')
    items = soup.find_all('div', class_='item_recruit')
    jobs  = []

    for item in items:
        rec_idx  = item.get('value', 'N/A')

        title_tag = item.find('h2', class_='job_tit')
        title_a   = title_tag.find('a') if title_tag else None
        title     = title_a.get_text(strip=True) if title_a else 'N/A'
        job_link  = BASE_URL + title_a['href'] if (title_a and title_a.get('href')) else 'N/A'

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

        sector_tag = item.find('div', class_='job_sector')
        sectors    = [a.get_text(strip=True) for a in sector_tag.find_all('a')] if sector_tag else []
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
            # 상세 페이지에서 채워질 필드
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


# ── 2단계: 상세 페이지 파싱 (BeautifulSoup) ────────────────
def parse_detail(html: str) -> dict:
    soup   = BeautifulSoup(html, 'lxml')
    result = {}

    # 핵심 정보 (급여, 근무지역 등)
    summary = soup.find(class_='jv_summary')
    if summary:
        for dl in summary.find_all('dl'):
            dt = dl.find('dt')
            dd = dl.find('dd')
            if dt and dd:
                key = dt.get_text(strip=True)
                val = dd.get_text(strip=True)
                if key == '급여':
                    result['급여'] = val

    # 공고 기간
    period = soup.find(class_='info_period')
    if period:
        text = period.get_text(separator='|', strip=True)
        parts = [p.strip() for p in text.split('|') if p.strip()]
        for i, part in enumerate(parts):
            if '시작일' in part and i + 1 < len(parts):
                result['공고시작일'] = parts[i + 1]
            if '마감일' in part and i + 1 < len(parts):
                result['공고마감일'] = parts[i + 1]

    # 기업 정보
    company_section = soup.find(class_='jv_company')
    if company_section:
        field_map = {
            '대표자명': '대표자명',
            '기업형태': '기업형태',
            '업종':     '업종',
            '사원수':   '사원수',
            '설립일':   '설립일',
            '매출액':   '매출액',
            '홈페이지': '기업홈페이지',
            '기업주소': '기업주소',
        }
        for dl in company_section.find_all('dl'):
            dt = dl.find('dt')
            dd = dl.find('dd')
            if dt and dd:
                key = dt.get_text(strip=True)
                val = dd.get_text(strip=True)
                if key in field_map:
                    result[field_map[key]] = val

    return result


# ── 3단계: Playwright로 상세 페이지 방문 ──────────────────
def enrich_with_details(jobs: list[dict], pw_page) -> None:
    total = len(jobs)
    for i, job in enumerate(jobs):
        link = job.get('공고링크', '')
        if not link or link == 'N/A':
            continue

        for attempt in range(1, DETAIL_RETRY + 1):
            try:
                pw_page.goto(link, wait_until='domcontentloaded', timeout=30000)
                pw_page.wait_for_timeout(3000)
                detail = parse_detail(pw_page.content())
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
    # 1단계: 리스트 수집
    all_jobs = []
    seen_ids = set()

    for keyword in SEARCH_KEYWORDS:
        print(f"\n[{keyword}] 리스트 수집 시작...")
        for page in range(1, MAX_PAGES + 1):
            jobs = scrape_list_page(keyword, page)
            if not jobs:
                print(f"  페이지 {page}: 공고 없음, 종료")
                break
            # 중복 공고 제거 (동일 공고ID)
            new_jobs = [j for j in jobs if j['공고ID'] not in seen_ids]
            seen_ids.update(j['공고ID'] for j in new_jobs)
            all_jobs.extend(new_jobs)
            print(f"  페이지 {page}: {len(jobs)}개 수집 (신규 {len(new_jobs)}개, 누적 {len(all_jobs)}개)")
            time.sleep(random.uniform(1, 3))

    print(f"\n리스트 수집 완료. 총 {len(all_jobs)}개")

    # 2단계: 상세 페이지 수집
    print("\n상세 페이지 수집 시작 (Playwright)...")
    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=HEADLESS)
        pw_page = browser.new_page(
            user_agent=HEADERS['User-Agent'],
            viewport={"width": 1280, "height": 800},
        )
        enrich_with_details(all_jobs, pw_page)
        browser.close()

    # 3단계: CSV 저장
    output_file = 'saramin_accounting_tax_jobs.csv'
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
