import os
import time
import requests
import json
import sqlite3
from dotenv import load_dotenv

load_dotenv()

DATA_GO_KR_KEY = os.getenv("DATA_GO_KR_API_KEY")
PUBMED_API_KEY = os.getenv("PUBMED_API_KEY", "")
DB경로 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "환자DB.db")


# ─────────────────────────────────────────────
# 공통 재시도 래퍼
# ─────────────────────────────────────────────

def api_재시도(호출함수, 최대시도=3, 대기초=5):
    """외부 API 호출을 재시도하는 래퍼.
    호출함수: 인자 없는 lambda 또는 함수.
    실패 시 None 반환."""
    for 시도 in range(최대시도):
        try:
            return 호출함수()
        except Exception as e:
            에러명 = type(e).__name__
            if 시도 < 최대시도 - 1:
                대기 = 대기초 * (시도 + 1)
                print(f"  [재시도] {에러명} — {대기}초 후 재시도 ({시도+1}/{최대시도})...")
                time.sleep(대기)
            else:
                print(f"  [오류] {에러명} — 최대 재시도 횟수 초과")
                return None


# ─────────────────────────────────────────────
# 2. DUR API (병용금기, 임부금기, 연령금기, 용량주의)
# ─────────────────────────────────────────────

def dur_조회(약품명):
    """약품명으로 DUR 정보를 조회한다.
    Returns: dict with keys: 병용금기[], 임부금기[], 연령금기[], 용량주의[]
    각 항목은 {'금기약품': '', '사유': ''} 형태.
    조회 실패 시 빈 dict 반환."""

    기본URL = "https://apis.data.go.kr/1471000/DURPrdlstInfoService03"

    결과 = {"병용금기": [], "임부금기": [], "연령금기": [], "용량주의": []}

    # 병용금기 조회 (네트워크 오류 시 재시도, 4xx는 재시도 안 함)
    응답 = api_재시도(lambda: requests.get(
        f"{기본URL}/getUsjntTabooInfoList03",
        params={"serviceKey": DATA_GO_KR_KEY, "itemName": 약품명, "type": "json", "numOfRows": "10"},
        timeout=10
    ))
    if 응답 and 응답.status_code == 200:
        items = 응답.json().get("body", {}).get("items", [])
        if isinstance(items, list):
            for item in items:
                결과["병용금기"].append({
                    "금기약품": item.get("MIXTURE_ITEM_NAME", ""),
                    "사유": item.get("PROHBT_CONTENT", "")
                })

    # 임부금기 조회
    응답 = api_재시도(lambda: requests.get(
        f"{기본URL}/getPwnmTabooInfoList03",
        params={"serviceKey": DATA_GO_KR_KEY, "itemName": 약품명, "type": "json", "numOfRows": "10"},
        timeout=10
    ))
    if 응답 and 응답.status_code == 200:
        items = 응답.json().get("body", {}).get("items", [])
        if isinstance(items, list):
            for item in items:
                결과["임부금기"].append({
                    "등급": item.get("GRADE_NM", ""),
                    "사유": item.get("PROHBT_CONTENT", "")
                })

    return 결과


# ─────────────────────────────────────────────
# 3. e약은요 API (효능, 부작용, 상호작용)
# ─────────────────────────────────────────────

def 약품정보_조회(약품명):
    """약품명으로 e약은요 정보를 조회한다.
    Returns: dict with keys: 효능, 사용법, 주의사항, 부작용, 상호작용
    조회 실패 시 빈 dict 반환."""

    응답 = api_재시도(lambda: requests.get(
        "http://apis.data.go.kr/1471000/DrbEasyDrugInfoService/getDrbEasyDrugList",
        params={"serviceKey": DATA_GO_KR_KEY, "itemName": 약품명, "type": "json", "numOfRows": "1"},
        timeout=10
    ))
    if 응답 and 응답.status_code == 200:
        items = 응답.json().get("body", {}).get("items", [])
        if items and isinstance(items, list):
            item = items[0]
            return {
                "효능": item.get("efcyQesitm", ""),
                "사용법": item.get("useMethodQesitm", ""),
                "주의사항": item.get("atpnQesitm", ""),
                "부작용": item.get("seQesitm", ""),
                "상호작용": item.get("intrcQesitm", "")
            }
    return {}


# ─────────────────────────────────────────────
# 4. 약가마스터 (CSV → DB 로드 + 조회)
# ─────────────────────────────────────────────

def 약가DB_초기화():
    """약가마스터 CSV를 SQLite 테이블로 로드한다. 이미 있으면 건너뜀."""
    conn = sqlite3.connect(DB경로)
    # 약가 테이블 존재 확인
    테이블존재 = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='약가마스터'"
    ).fetchone()
    if 테이블존재:
        conn.close()
        return True

    # CSV 파일 자동 탐색 (약가, 약품, 마스터 키워드)
    # macOS HFS+는 한글 파일명을 NFD로 저장하므로 NFC 정규화 후 비교
    import unicodedata
    프로젝트폴더 = os.path.dirname(os.path.abspath(__file__))
    csv파일 = None
    for f in os.listdir(프로젝트폴더):
        f_nfc = unicodedata.normalize("NFC", f)
        if f_nfc.endswith(".csv") and any(k in f_nfc for k in ["약가", "약품", "마스터"]):
            csv파일 = os.path.join(프로젝트폴더, f)
            break

    if not csv파일:
        print("  [경고] 약가마스터 CSV 파일을 찾을 수 없습니다.")
        conn.close()
        return False

    # CSV 읽기 → 테이블 생성
    import pandas as pd
    try:
        df = pd.read_csv(csv파일, encoding="cp949", low_memory=False)
    except UnicodeDecodeError:
        df = pd.read_csv(csv파일, encoding="utf-8", low_memory=False)

    df.to_sql("약가마스터", conn, if_exists="replace", index=False)
    conn.commit()
    conn.close()
    print(f"  [약가마스터] {len(df)}건 로드 완료")
    return True


def 급여정보_조회(약품명):
    """약품명으로 급여 여부와 상한금액을 조회한다.
    Returns: list of dict with keys: 제품명, 급여구분, 상한금액 (CSV 칼럼에 따라 다를 수 있음)
    조회 실패 시 빈 list 반환."""
    약가DB_초기화()
    conn = sqlite3.connect(DB경로)
    conn.row_factory = sqlite3.Row
    try:
        # 실제 칼럼명 동적 탐색 (CSV마다 다를 수 있음)
        칼럼들 = conn.execute("PRAGMA table_info(약가마스터)").fetchall()
        칼럼명목록 = [c[1] for c in 칼럼들]

        제품명칼럼 = None
        for 칼럼 in 칼럼명목록:
            if any(k in 칼럼 for k in ["한글상품명", "제품명", "품목명", "약품명", "상품명"]):
                제품명칼럼 = 칼럼
                break

        if not 제품명칼럼:
            print(f"  [약가마스터] 제품명 칼럼을 찾을 수 없음. 칼럼 목록: {칼럼명목록[:10]}...")
            return []

        rows = conn.execute(
            f'SELECT * FROM 약가마스터 WHERE [{제품명칼럼}] LIKE ? LIMIT 5',
            (f"%{약품명}%",)
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"  [급여정보 조회 오류] {e}")
        return []
    finally:
        conn.close()


# ─────────────────────────────────────────────
# 5. PubMed API (논문 검색)
# ─────────────────────────────────────────────

def pubmed_검색(검색어, 최대건수=3):
    """PubMed에서 관련 논문을 검색한다.
    Returns: list of dict with keys: 제목, 저널, 연도, PMID, 링크"""

    결과 = []
    # API 키가 있을 때만 파라미터에 포함
    api_key_param = {"api_key": PUBMED_API_KEY} if PUBMED_API_KEY else {}

    # Step 1: 검색 (esearch)
    검색응답 = api_재시도(lambda: requests.get(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        params={"db": "pubmed", "term": 검색어, "retmax": 최대건수,
                "sort": "relevance", "retmode": "json", **api_key_param},
        timeout=10
    ))
    if not 검색응답 or 검색응답.status_code != 200:
        return 결과

    ids = 검색응답.json().get("esearchresult", {}).get("idlist", [])
    if not ids:
        return 결과

    # Step 2: 상세 정보 (esummary)
    상세응답 = api_재시도(lambda: requests.get(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
        params={"db": "pubmed", "id": ",".join(ids), "retmode": "json", **api_key_param},
        timeout=10
    ))
    if not 상세응답 or 상세응답.status_code != 200:
        return 결과

    결과데이터 = 상세응답.json().get("result", {})
    for pmid in ids:
        논문 = 결과데이터.get(pmid, {})
        if not 논문:
            continue
        결과.append({
            "제목": 논문.get("title", ""),
            "저널": 논문.get("source", ""),
            "연도": 논문.get("pubdate", "")[:4],
            "PMID": pmid,
            "링크": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        })
    return 결과


# 영문 성분명 → 한글 변환 테이블 (급여정보 조회용)
# 약가마스터 DB는 한글상품명에 성분명이 괄호로 포함되어 있어 한글로 검색해야 매칭됨
_영문_한글_성분명 = {
    "amlodipine": "암로디핀",
    "losartan": "로사르탄",
    "valsartan": "발사르탄",
    "telmisartan": "텔미사르탄",
    "olmesartan": "올메사르탄",
    "rosuvastatin": "로수바스타틴",
    "atorvastatin": "아토르바스타틴",
    "pitavastatin": "피타바스타틴",
    "metformin": "메트포르민",
    "glimepiride": "글리메피리드",
    "sitagliptin": "시타글립틴",
    "dapagliflozin": "다파글리플로진",
    "empagliflozin": "엠파글리플로진",
    "levothyroxine": "레보티록신",
    "allopurinol": "알로푸리놀",
    "febuxostat": "페북소스타트",
    "warfarin": "와파린",
    "aspirin": "아스피린",
    "clopidogrel": "클로피도그렐",
    "bisoprolol": "비소프롤롤",
    "carvedilol": "카르베딜롤",
    "furosemide": "푸로세미드",
    "spironolactone": "스피로노락톤",
    "omeprazole": "오메프라졸",
    "lansoprazole": "란소프라졸",
    "esomeprazole": "에소메프라졸",
}


# ─────────────────────────────────────────────
# 6. 통합 조회 함수
# ─────────────────────────────────────────────

def 처방_안전성_조회(약품명목록):
    """처방된 약품 목록에 대해 DUR + e약은요 + 급여 정보를 한꺼번에 조회.
    chart_analyzer.py에서 호출.
    Returns: dict keyed by 약품명, each containing dur, 약품정보, 급여정보"""

    결과 = {}
    for 약품명 in 약품명목록:
        약품명 = 약품명.strip()
        if not 약품명:
            continue
        # DUR, e약은요, 급여정보 모두 한글 검색이 필요 — 영문 성분명이면 한글로 변환
        검색어 = _영문_한글_성분명.get(약품명.lower(), 약품명)
        결과[약품명] = {
            "dur": dur_조회(검색어),
            "약품정보": 약품정보_조회(검색어),
            "급여정보": 급여정보_조회(검색어)
        }
    return 결과
