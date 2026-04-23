"""
이력서를 Claude AI로 분석해 사람인에서 지원할 직무 분야를 추천해주는 스크립트.

사용법:
    python resume_job_advisor.py --resume 이력서.pdf
    python resume_job_advisor.py --resume 이력서.txt
    python resume_job_advisor.py --resume 이력서.docx
    python resume_job_advisor.py --resume 이력서.pdf --scrape   # 추천 키워드로 바로 수집까지
"""

import argparse
import base64
import json
import os
import sys

import anthropic


# ── 이력서 파일 읽기 ────────────────────────────────────────────────

def read_resume(path: str) -> tuple[str, str]:
    """
    이력서 파일을 읽어 (content_type, content) 반환.
    - PDF  → base64 인코딩된 문서 블록으로 전달
    - DOCX → python-docx로 텍스트 추출
    - 나머지 → 일반 텍스트로 읽기
    """
    ext = os.path.splitext(path)[1].lower()

    if ext == ".pdf":
        with open(path, "rb") as f:
            data = base64.standard_b64encode(f.read()).decode("utf-8")
        return "pdf", data

    if ext == ".docx":
        try:
            from docx import Document
        except ImportError:
            sys.exit("DOCX 지원을 위해 pip install python-docx 를 실행하세요.")
        doc = Document(path)
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        return "text", text

    # .txt, .md, 기타 텍스트
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return "text", f.read()


# ── Claude 분석 ─────────────────────────────────────────────────────

SYSTEM_PROMPT = """당신은 한국 채용 시장 전문가입니다.
사용자가 이력서를 제공하면 핵심 역량, 경력, 기술 스택을 파악하고,
사람인(saramin.co.kr) 구직 플랫폼에서 지원하기 좋은 직무 분야를 추천해주세요.

반드시 JSON 형식으로만 응답하세요. 다른 텍스트는 포함하지 마세요.
"""

ANALYSIS_PROMPT = """아래 이력서를 분석해서 다음 JSON 구조로만 응답하세요:

{
  "profile_summary": "지원자 프로필 한 줄 요약 (한국어)",
  "key_skills": ["핵심 기술/역량 목록 (최대 10개)"],
  "experience_level": "신입 | 1~3년차 | 3~5년차 | 5~10년차 | 10년이상",
  "recommended_fields": [
    {
      "field": "직무 분야명",
      "reason": "추천 이유 (이력서 근거 포함)",
      "saramin_keywords": ["사람인 검색에 쓸 키워드 3~5개"],
      "match_score": 95
    }
  ],
  "top_keywords": ["사람인 검색 최우선 키워드 (최대 5개, 가장 적합한 순)"]
}

recommended_fields는 5개, match_score는 0~100 정수로 작성하세요.
"""


def analyze_resume(resume_path: str) -> dict:
    """Claude에게 이력서를 분석시키고 결과 dict 반환."""
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    content_type, content = read_resume(resume_path)

    if content_type == "pdf":
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": content,
                        },
                    },
                    {"type": "text", "text": ANALYSIS_PROMPT},
                ],
            }
        ]
    else:
        messages = [
            {
                "role": "user",
                "content": f"[이력서 내용]\n{content}\n\n{ANALYSIS_PROMPT}",
            }
        ]

    with client.messages.stream(
        model="claude-opus-4-7",
        max_tokens=4096,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=messages,
    ) as stream:
        response = stream.get_final_message()

    raw = next(
        (b.text for b in response.content if b.type == "text"), ""
    ).strip()

    # JSON 코드 블록 제거
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    return json.loads(raw)


# ── 결과 출력 ────────────────────────────────────────────────────────

def print_results(result: dict) -> None:
    print("\n" + "=" * 60)
    print("📋 이력서 분석 결과")
    print("=" * 60)

    print(f"\n👤 프로필: {result.get('profile_summary', '-')}")
    print(f"📈 경력 수준: {result.get('experience_level', '-')}")

    skills = result.get("key_skills", [])
    if skills:
        print(f"\n🔧 핵심 역량: {', '.join(skills)}")

    print("\n" + "-" * 60)
    print("🎯 추천 직무 분야 (match_score 순)")
    print("-" * 60)

    fields = sorted(
        result.get("recommended_fields", []),
        key=lambda x: x.get("match_score", 0),
        reverse=True,
    )
    for i, f in enumerate(fields, 1):
        score = f.get("match_score", 0)
        bar = "█" * (score // 10) + "░" * (10 - score // 10)
        print(f"\n  {i}. {f['field']}  [{bar}] {score}점")
        print(f"     이유: {f.get('reason', '-')}")
        kws = f.get("saramin_keywords", [])
        if kws:
            print(f"     검색 키워드: {', '.join(kws)}")

    top = result.get("top_keywords", [])
    if top:
        print("\n" + "=" * 60)
        print(f"🔑 최우선 검색 키워드: {', '.join(top)}")
        print("=" * 60)


# ── 스크래핑 연동 ────────────────────────────────────────────────────

def run_scraper_with_keywords(keywords: list[str]) -> None:
    """추천 키워드로 saramin 스크래퍼를 바로 실행."""
    import importlib.util, pathlib

    scraper_path = pathlib.Path(__file__).parent / "scrape_saramin.py"
    spec = importlib.util.spec_from_file_location("scrape_saramin", scraper_path)
    scrape_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scrape_mod)

    scrape_mod.SEARCH_KEYWORDS = keywords
    print(f"\n🚀 사람인 수집 시작 — 키워드: {keywords}")
    scrape_mod.main()


# ── 메인 ─────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="이력서를 분석해 사람인 구직 키워드를 추천합니다."
    )
    parser.add_argument(
        "--resume", required=True, help="이력서 파일 경로 (PDF / DOCX / TXT)"
    )
    parser.add_argument(
        "--scrape",
        action="store_true",
        help="추천 키워드로 사람인 데이터 즉시 수집",
    )
    parser.add_argument(
        "--output",
        default="resume_analysis.json",
        help="분석 결과 JSON 저장 경로 (기본: resume_analysis.json)",
    )
    args = parser.parse_args()

    if not os.path.exists(args.resume):
        sys.exit(f"파일을 찾을 수 없습니다: {args.resume}")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit(
            "ANTHROPIC_API_KEY 환경 변수가 설정되지 않았습니다.\n"
            "export ANTHROPIC_API_KEY='your-key' 로 설정 후 다시 실행하세요."
        )

    print(f"📄 이력서 분석 중: {args.resume}")
    result = analyze_resume(args.resume)

    print_results(result)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n💾 결과 저장: {args.output}")

    if args.scrape:
        top_keywords = result.get("top_keywords", [])
        if top_keywords:
            run_scraper_with_keywords(top_keywords)
        else:
            print("추천 키워드가 없어 수집을 건너뜁니다.")


if __name__ == "__main__":
    main()
