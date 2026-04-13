"""
의료 차트 AI 어시스턴트 — Streamlit 웹앱
실행: streamlit run app.py
"""
import os
import re
import sqlite3
from datetime import datetime

import pandas as pd
import streamlit as st

from util import (
    미분석차트조회,
    나이계산,
    환자검색,
    환자등록,
    환자목록가져오기,
    환자전체기록조회,
    환자정보수정,
)
from practice_analyzer import AI_패턴분석, 데일리_SQL체크
from backup import DB백업

DB_경로 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "환자DB.db")


# ============================================================
# 앱 설정
# ============================================================
st.set_page_config(
    page_title="의료 차트 시스템",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# CSS
# ============================================================
def _inject_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;600;700&family=Inter:wght@400;500;600;700&display=swap');

    /* 전체 글자체 — Inter(영문) + Noto Sans KR(한글) */
    html, body, [class*="css"], .stApp,
    .stMarkdown, .stMarkdown p, .stMarkdown span,
    .stTextInput input, .stTextArea textarea,
    button, label, .stTabs [data-baseweb="tab"],
    .stDataFrame, .stMetric, .stCaption,
    [data-testid="stSidebar"] * {
        font-family: 'Inter', 'Noto Sans KR', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
    }

    /* Streamlit 기본 헤더/푸터/Deploy 버튼 숨기기 */
    header[data-testid="stHeader"] { display: none !important; }
    footer { display: none !important; }
    .stDeployButton { display: none !important; }

    /* 전체 레이아웃 */
    .main .block-container {
        padding-top: 1rem !important;
        padding-left: 2rem;
        padding-right: 2rem;
        max-width: 100% !important;
    }

    /* 사이드바 배경 */
    section[data-testid="stSidebar"] > div:first-child {
        background-color: #1e2432;
        border-right: 1px solid #2d3550;
        padding-top: 1rem !important;
    }
    /* 사이드바 텍스트 색상 */
    section[data-testid="stSidebar"] .stMarkdown p,
    section[data-testid="stSidebar"] .stMarkdown span,
    section[data-testid="stSidebar"] label {
        color: #c5cce8 !important;
    }
    section[data-testid="stSidebar"] hr {
        border-color: #2d3550 !important;
        margin: 8px 0;
    }
    /* 사이드바 버튼 — secondary (기본) */
    section[data-testid="stSidebar"] button[kind="secondary"] {
        background: transparent !important;
        border: 1px solid transparent !important;
        color: #c5cce8 !important;
        transition: background 0.15s;
    }
    section[data-testid="stSidebar"] button[kind="secondary"]:hover {
        background: #2d3550 !important;
        border-color: #3d4a70 !important;
    }
    /* 사이드바 버튼 — primary (활성/선택) */
    section[data-testid="stSidebar"] button[kind="primary"] {
        background: #4f6ef7 !important;
        border-color: #4f6ef7 !important;
        color: white !important;
    }
    /* 사이드바 신환등록(primary) 버튼 텍스트 중앙 정렬 */
    section[data-testid="stSidebar"] button[kind="primary"] p {
        text-align: center !important;
    }

    /* 사이드바 환자 목록 버튼 좌측 정렬 */
    section[data-testid="stSidebar"] button {
        text-align: left !important;
        justify-content: flex-start !important;
    }
    section[data-testid="stSidebar"] button p {
        text-align: left !important;
    }
    section[data-testid="stSidebar"] button div {
        text-align: left !important;
        justify-content: flex-start !important;
    }
    /* 헤더 행 / 하단 아이콘 행(HorizontalBlock) 버튼은 중앙 정렬 */
    section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] button {
        justify-content: center !important;
    }
    section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] button p {
        text-align: center !important;
    }

    /* 사이드바 크기 고정 */
    section[data-testid="stSidebar"] {
        width: 280px !important;
        min-width: 280px !important;
        max-width: 280px !important;
    }
    /* 사이드바 리사이즈 핸들 숨기기 */
    section[data-testid="stSidebar"] > div[data-testid="stSidebarResizeHandle"] {
        display: none !important;
    }
    /* 사이드바 접기 버튼 숨기기 */
    button[data-testid="stSidebarCollapseButton"],
    [data-testid="stSidebarCollapsedControl"] {
        display: none !important;
    }

    /* 요약 카드 */
    .stat-card {
        background: white;
        border-radius: 12px;
        padding: 20px 24px;
        box-shadow: 0 2px 8px rgba(0,0,0,.07);
        border-left: 4px solid #4f6ef7;
    }
    .stat-card.warn  { border-left-color: #f59e0b; }
    .stat-card.danger { border-left-color: #ef4444; }
    .stat-card .label { font-size: 13px; color: #6b7280; margin-bottom: 4px; }
    .stat-card .value { font-size: 30px; font-weight: 700; color: #1f2937; }
    .stat-card .sub   { font-size: 12px; color: #9ca3af; margin-top: 4px; }

    /* 환자 헤더 배지 */
    .patient-header {
        display: flex;
        align-items: center;
        gap: 16px;
        padding: 16px;
        background: #eff2ff;
        border-radius: 12px;
        margin-bottom: 16px;
    }
    .initial-badge {
        width: 52px; height: 52px;
        border-radius: 50%;
        background: #4f6ef7;
        color: white;
        display: flex; align-items: center; justify-content: center;
        font-weight: 700; font-size: 22px;
        flex-shrink: 0;
    }
    .initial-badge.sm {
        width: 36px; height: 36px;
        font-size: 15px;
    }

    /* 데일리 체크 항목 */
    .daily-item {
        padding: 10px 14px;
        border-radius: 8px;
        margin-bottom: 6px;
        font-size: 14px;
        line-height: 1.5;
    }
    .daily-item.danger {
        background: #fef2f2;
        border-left: 3px solid #ef4444;
        color: #991b1b;
    }
    .daily-item.warn {
        background: #fffbeb;
        border-left: 3px solid #f59e0b;
        color: #92400e;
    }
    .daily-item.info {
        background: #eff6ff;
        border-left: 3px solid #3b82f6;
        color: #1e40af;
    }

    /* 신환 등록 버튼 중앙 정렬 */
    .sidebar-center-btn button {
        justify-content: center !important;
    }
    .sidebar-center-btn button p,
    .sidebar-center-btn button div {
        text-align: center !important;
        justify-content: center !important;
    }

    /* 환자 상세 좌우 패널 상단 정렬 */
    [data-testid="stHorizontalBlock"]:has([data-testid="stVerticalBlockBorderWrapper"]) {
        align-items: flex-start !important;
    }

    /* 메인 영역 버튼 좌측 정렬 */
    section[data-testid="stMain"] button {
        justify-content: flex-start !important;
        text-align: left !important;
    }
    section[data-testid="stMain"] button p,
    section[data-testid="stMain"] button div {
        text-align: left !important;
        justify-content: flex-start !important;
    }
    </style>
    """, unsafe_allow_html=True)


# ============================================================
# 세션 상태 초기화
# ============================================================
def _init_state():
    defaults = {
        "page":               "홈",       # "홈" | "연구" | "신환등록" | "환자상세" | "설정"
        "mode":               "연구용",
        "lang":               "한국어",
        "show_lang_selector": False,
        "selected_patient_id": None,
        "daily_filter":       "전체",
        "daily_show_all":     False,
        "ai_pattern_result":  None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ============================================================
# DB 헬퍼
# ============================================================
def _환자목록_진단포함():
    """환자 목록에 활성/의심 진단을 포함해 반환한다."""
    conn = sqlite3.connect(DB_경로)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT p.*,
                   GROUP_CONCAT(d.진단명, ', ') AS 주진단목록
            FROM 환자 p
            LEFT JOIN 진단 d ON p.환자id = d.환자id
                             AND d.유효여부 = 1
                             AND d.상태 IN ('활성', '의심')
            GROUP BY p.환자id
            ORDER BY p.이름
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _주진단_조회(환자id_list):
    """환자id 리스트에 대한 주진단 dict를 반환한다."""
    if not 환자id_list:
        return {}
    conn = sqlite3.connect(DB_경로)
    conn.row_factory = sqlite3.Row
    placeholders = ",".join("?" * len(환자id_list))
    try:
        rows = conn.execute(
            f"SELECT 환자id, GROUP_CONCAT(진단명, ', ') AS 주진단목록 "
            f"FROM 진단 WHERE 환자id IN ({placeholders}) "
            f"AND 유효여부 = 1 AND 상태 IN ('활성', '의심') "
            f"GROUP BY 환자id",
            환자id_list,
        ).fetchall()
        return {r["환자id"]: r["주진단목록"] for r in rows}
    finally:
        conn.close()


def _추적지연_수():
    """오늘 기준 완료되지 않고 예정일이 지난 추적계획 수를 반환한다."""
    오늘 = datetime.today().strftime("%y%m%d")
    conn = sqlite3.connect(DB_경로)
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM 추적계획 "
            "WHERE 완료여부=0 AND 유효여부=1 "
            "AND 예정일 IS NOT NULL AND 예정일 != '' AND 예정일 < ?",
            (오늘,),
        ).fetchone()
        return row[0]
    except Exception:
        return 0
    finally:
        conn.close()


def _elapsed_days(msg: str) -> int:
    """메시지에서 경과 일수를 추출한다 (정렬용)."""
    m = re.search(r"(\d+)(일|개월) 경과", msg)
    if not m:
        return 0
    n = int(m.group(1))
    return n * 30 if m.group(2) == "개월" else n


# ============================================================
# 사이드바 — 환자 목록 전용
# ============================================================
def _render_sidebar():
    with st.sidebar:
        # ── 헤더 행: 제목 + [홈] [연구] 버튼
        col_title, col_home, col_research = st.columns([5, 2, 2])
        with col_title:
            st.markdown("**🏥 의료 차트**")
        with col_home:
            if st.button(
                "🏠", key="nav_홈", use_container_width=True,
                help="홈",
                type="primary" if st.session_state.page == "홈" else "secondary",
            ):
                st.session_state.page = "홈"
                st.rerun()
        with col_research:
            if st.button(
                "📊", key="nav_연구", use_container_width=True,
                help="연구",
                type="primary" if st.session_state.page == "연구" else "secondary",
            ):
                st.session_state.page = "연구"
                st.rerun()

        st.markdown("---")

        # ── 환자 검색창
        검색어 = st.text_input(
            "search",
            placeholder="🔍  이름 또는 병록번호 검색...",
            label_visibility="collapsed",
            key="patient_search",
        )

        # ── 신환 등록 버튼 (텍스트 중앙 정렬용 래퍼)
        st.markdown('<div class="sidebar-center-btn">', unsafe_allow_html=True)
        if st.button("➕  신환 등록", use_container_width=True, type="primary", key="btn_new_patient"):
            st.session_state.page = "신환등록"
            st.session_state.selected_patient_id = None
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("---")

        # ── 환자 목록 (스크롤 영역만 고정 높이)
        with st.container(height=400, border=False):
            _render_patient_list(검색어)

        # ── 하단 아이콘 행: ✏️ ⚙️ 🌐 🚪 (항상 고정)
        st.markdown("---")
        langs = ["한국어", "English", "Deutsch", "日本語"]
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            if st.button("✏️", key="btn_manual", help="수동입력 (추후 구현)"):
                st.toast("수동입력 (추후 구현)")
        with c2:
            if st.button(
                "⚙️", key="btn_settings", help="설정",
                type="primary" if st.session_state.page == "설정" else "secondary",
            ):
                st.session_state.page = "설정"
                st.rerun()
        with c3:
            if st.button("🌐", key="btn_lang", help=f"언어: {st.session_state.lang}"):
                st.session_state.show_lang_selector = not st.session_state.show_lang_selector
                st.rerun()
        with c4:
            if st.button("🚪", key="btn_logout", help="로그아웃 (추후 구현)"):
                st.toast("로그아웃 (추후 구현)")

        # 언어 선택 패널 (🌐 클릭 시 표시)
        if st.session_state.show_lang_selector:
            선택 = st.radio(
                "언어 선택",
                langs,
                index=langs.index(st.session_state.lang),
                label_visibility="collapsed",
                key="lang_radio",
            )
            if 선택 != st.session_state.lang:
                st.session_state.lang = 선택
                st.session_state.show_lang_selector = False
                st.rerun()


def _render_patient_list(검색어: str):
    """사이드바 환자 목록을 표시한다."""
    if 검색어.strip():
        이름결과 = 환자검색(검색어.strip())
        conn = sqlite3.connect(DB_경로)
        conn.row_factory = sqlite3.Row
        번호결과 = [dict(r) for r in conn.execute(
            "SELECT * FROM 환자 WHERE 병록번호 LIKE ?",
            (f"%{검색어.strip()}%",),
        ).fetchall()]
        conn.close()
        seen: set = set()
        환자목록 = []
        for p in 이름결과 + 번호결과:
            if p["환자id"] not in seen:
                seen.add(p["환자id"])
                환자목록.append(p)
        진단맵 = _주진단_조회([p["환자id"] for p in 환자목록])
        for p in 환자목록:
            p["주진단목록"] = 진단맵.get(p["환자id"], "")
    else:
        환자목록 = _환자목록_진단포함()

    if not 환자목록:
        msg = "검색 결과가 없습니다." if 검색어.strip() else "등록된 환자가 없습니다."
        st.caption(msg)
        return

    st.caption(f"{len(환자목록)}명")

    for 환자 in 환자목록:
        is_selected = 환자["환자id"] == st.session_state.selected_patient_id
        이름     = 환자.get("이름", "")
        병록번호  = 환자.get("병록번호", "")
        나이     = 나이계산(환자.get("생년월일"))
        성별     = 환자.get("성별", "")
        mrn_숫자 = 병록번호[4:] if 병록번호 and 병록번호.startswith("MRN-") else (병록번호 or "")
        나이_숫자 = str(나이) if 나이 is not None else "?"
        label = f"{이름}  {mrn_숫자}\n{나이_숫자}/{성별}"

        if st.button(
            label,
            key=f"pat_{환자['환자id']}",
            use_container_width=True,
            type="primary" if is_selected else "secondary",
        ):
            st.session_state.selected_patient_id = 환자["환자id"]
            st.session_state.page = "환자상세"
            st.rerun()


# ============================================================
# 홈 화면
# ============================================================
def _render_home():
    st.markdown("## 🏥 의료 차트 시스템")

    환자수  = len(환자목록가져오기())
    미분석수 = len(미분석차트조회())
    지연수  = _추적지연_수()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"""
        <div class="stat-card">
            <div class="label">👥 전체 환자</div>
            <div class="value">{환자수}<span style="font-size:16px;color:#6b7280;font-weight:400;">명</span></div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        warn_class = " warn" if 미분석수 > 0 else ""
        st.markdown(f"""
        <div class="stat-card{warn_class}">
            <div class="label">📋 미분석 차트</div>
            <div class="value">{미분석수}<span style="font-size:16px;color:#6b7280;font-weight:400;">건</span></div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        danger_class = " danger" if 지연수 > 0 else ""
        st.markdown(f"""
        <div class="stat-card{danger_class}">
            <div class="label">⚠️ 추적 지연</div>
            <div class="value">{지연수}<span style="font-size:16px;color:#6b7280;font-weight:400;">건</span></div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["📅 데일리 체크", "🤖 AI 패턴 분석 (유료)"])
    with tab1:
        _render_daily_check()
    with tab2:
        _render_ai_pattern()


def _render_daily_check():
    """SQL 기반 데일리 체크를 필터/정렬하여 표시한다."""
    msgs = 데일리_SQL체크()

    if not msgs:
        st.success("✅ 현재 주의사항이 없습니다.")
        return

    counts = {
        "전체":        len(msgs),
        "추적 지연":   sum(1 for m in msgs if "추적 지연"   in m),
        "미시행 검사": sum(1 for m in msgs if "미시행 검사" in m),
        "이번 주 예정": sum(1 for m in msgs if "이번 주 예정" in m),
    }

    col1, col2, col3, col4 = st.columns(4)
    for col, (fname, cnt) in zip([col1, col2, col3, col4], counts.items()):
        with col:
            active = st.session_state.daily_filter == fname
            if st.button(
                f"{fname} ({cnt})",
                key=f"df_{fname}",
                type="primary" if active else "secondary",
                use_container_width=True,
            ):
                st.session_state.daily_filter = fname
                st.session_state.daily_show_all = False
                st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    필터 = st.session_state.daily_filter
    if 필터 == "추적 지연":
        filtered = [m for m in msgs if "추적 지연"   in m]
    elif 필터 == "미시행 검사":
        filtered = [m for m in msgs if "미시행 검사" in m]
    elif 필터 == "이번 주 예정":
        filtered = [m for m in msgs if "이번 주 예정" in m]
    else:
        filtered = msgs

    지연   = sorted([m for m in filtered if "추적 지연" in m], key=_elapsed_days, reverse=True)
    나머지  = [m for m in filtered if "추적 지연" not in m]
    sorted_msgs = 지연 + 나머지

    show_count = len(sorted_msgs) if st.session_state.daily_show_all else min(10, len(sorted_msgs))

    for msg in sorted_msgs[:show_count]:
        if "추적 지연" in msg:
            css = "danger"
        elif "미시행 검사" in msg:
            css = "warn"
        else:
            css = "info"
        st.markdown(f'<div class="daily-item {css}">{msg}</div>', unsafe_allow_html=True)

    remaining = len(sorted_msgs) - show_count
    if remaining > 0:
        if st.button(f"더 보기 ({remaining}건)", key="daily_more"):
            st.session_state.daily_show_all = True
            st.rerun()


def _render_ai_pattern():
    """AI 패턴 분석 탭."""
    st.info("🤖 Claude API를 호출합니다. 비용이 발생합니다.", icon="⚠️")

    if st.session_state.ai_pattern_result:
        st.markdown(st.session_state.ai_pattern_result)
        col_a, _ = st.columns([1, 4])
        with col_a:
            if st.button("🔄 다시 분석", key="ai_rerun"):
                st.session_state.ai_pattern_result = None
                st.rerun()
    else:
        if st.button("🚀 AI 패턴 분석 시작", type="primary", key="ai_start"):
            with st.spinner("AI가 진료 패턴을 분석 중입니다..."):
                result = AI_패턴분석()
            if result:
                st.session_state.ai_pattern_result = result
                st.rerun()
            else:
                st.error("분석에 실패했습니다. API 키와 네트워크를 확인하세요.")


# ============================================================
# 신환 등록
# ============================================================
def _render_new_patient_form():
    st.markdown("### ➕ 신환 등록")

    with st.form("new_patient_form", clear_on_submit=False):
        이름 = st.text_input("환자 이름 *")
        생년월일 = st.text_input("생년월일 * (YYYYMMDD)", placeholder="예: 19900115")
        col_성별, _ = st.columns([1, 2])
        with col_성별:
            성별 = st.radio("성별 *", ["M", "F"], horizontal=True)
        병록번호 = st.text_input(
            "병록번호 (없으면 자동 부여)",
            placeholder="MRN-XXXXX 형식으로 자동 부여됩니다",
        )
        submitted = st.form_submit_button("등록", type="primary", use_container_width=True)

    if submitted:
        if not 이름.strip():
            st.error("이름을 입력하세요.")
            return
        if len(생년월일.strip()) != 8 or not 생년월일.strip().isdigit():
            st.error("생년월일은 8자리 숫자(YYYYMMDD)로 입력하세요.")
            return

        환자id = 환자등록(
            이름.strip(), 생년월일.strip(), 성별,
            병록번호=병록번호.strip() or None,
        )
        if 환자id is None:
            st.error("등록에 실패했습니다. 병록번호가 중복되었을 수 있습니다.")
            return

        mrn = 병록번호.strip() or f"MRN-{환자id:05d}"
        나이 = 나이계산(생년월일.strip())
        나이표시 = f", {나이}세" if 나이 is not None else ""
        st.success(f"✅ {이름} 환자가 등록되었습니다. (병록번호: {mrn}{나이표시})")

        st.session_state.selected_patient_id = 환자id
        st.session_state.page = "환자상세"
        st.rerun()


# ============================================================
# 환자 상세
# ============================================================
def _render_patient_detail(환자id: int):
    기록 = 환자전체기록조회(환자id)
    if not 기록:
        st.error("환자 정보를 찾을 수 없습니다.")
        return

    환자    = 기록["환자"]
    이름    = 환자.get("이름", "")
    나이    = 나이계산(환자.get("생년월일"))
    성별    = 환자.get("성별", "")
    병록번호 = 환자.get("병록번호", "")
    병록번호_숫자만 = 병록번호.replace("MRN-", "") if 병록번호 else ""
    활성진단 = [d["진단명"] for d in 기록.get("진단", []) if d.get("상태") in ("활성", "의심")]
    주진단표시 = ", ".join(활성진단[:3]) + ("…" if len(활성진단) > 3 else "") if 활성진단 else "진단 없음"
    나이표시 = str(나이) if 나이 is not None else "?"

    가족력_현재  = 환자.get("가족력", "")      or ""
    약부작용_현재 = 환자.get("약부작용이력", "") or ""

    # ── 환자 헤더 (컴팩트 2줄: 이름/번호/나이/성별/생년월일 + 주진단)
    st.markdown(f"""
    <div class="patient-header" style="padding:12px 16px;margin-bottom:8px;">
        <div style="flex:1;">
            <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;">
                <span style="font-size:18px;font-weight:700;color:#1f2937;">{이름}</span>
                <span style="font-size:14px;color:#6b7280;">{병록번호_숫자만}</span>
                <span style="font-size:14px;color:#6b7280;">{나이표시}/{성별}</span>
                <span style="font-size:14px;color:#6b7280;">{환자.get('생년월일', '')}</span>
            </div>
            <div style="font-size:13px;color:#4f6ef7;margin-top:4px;">{주진단표시}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── 가족력/약부작용
    fc1, fc2 = st.columns(2)
    with fc1:
        fi_col, fb_col = st.columns([5, 1], vertical_alignment="bottom")
        with fi_col:
            가족력_입력 = st.text_input("가족력", value=가족력_현재, key=f"fh_{환자id}")
        with fb_col:
            if st.button("저장", key=f"fh_save_{환자id}", use_container_width=True):
                환자정보수정(환자id, "가족력", 가족력_입력)
                st.toast("가족력 저장 완료")
                st.rerun()
    with fc2:
        ai_col, ab_col = st.columns([5, 1], vertical_alignment="bottom")
        with ai_col:
            약부작용_입력 = st.text_input("약부작용이력", value=약부작용_현재, key=f"ae_{환자id}")
        with ab_col:
            if st.button("저장", key=f"ae_save_{환자id}", use_container_width=True):
                환자정보수정(환자id, "약부작용이력", 약부작용_입력)
                st.toast("약부작용이력 저장 완료")
                st.rerun()

    col_left, col_right = st.columns([6, 4], gap="medium")

    with col_left:
        with st.container(height=650, border=False):
            tabs = st.tabs(["📋 브리핑", "📝 진료기록", "✏️ 수정", "🗑️ 삭제"])
            with tabs[0]:
                _tab_briefing(환자id)
            with tabs[1]:
                _tab_chart_entry(환자id)
            with tabs[2]:
                _tab_edit(환자id)
            with tabs[3]:
                _tab_delete(환자id)

    with col_right:
        with st.container(height=650, border=False):
            _tab_history(기록)


def _tab_briefing(환자id: int):
    st.info("🔧 추후 구현 — AI 브리핑 생성\n\n`briefing_generator.브리핑생성(환자id)` 연동 예정")


def _tab_chart_entry(환자id: int):
    mode = st.session_state.mode
    if mode == "진료보조용":
        st.caption("진료보조용 모드 — Step 1~3 (제안 확인까지, 저장 없음)")
    else:
        st.caption("연구용 모드 — Step 1~5 전체 (데이터 추출 및 저장 포함)")

    steps = ["① 차트 입력", "② AI 제안 확인", "③ 보완 차트", "④ 추출 데이터", "⑤ 저장 완료"]
    if mode == "진료보조용":
        steps = steps[:3]

    cols = st.columns(len(steps))
    for i, (col, label) in enumerate(zip(cols, steps)):
        with col:
            if i == 0:
                st.markdown(f"**{label}**")
            else:
                st.markdown(f"<span style='color:#9ca3af'>{label}</span>", unsafe_allow_html=True)

    st.markdown("---")
    st.info("🔧 추후 구현 — 진료기록 5단계 흐름\n\n`chart_analyzer.차트분석_저장_전체흐름()` 연동 예정")


def _tab_edit(환자id: int):
    st.info("🔧 추후 구현 — 기록 수정\n\n`util.py` 수정 함수들 연동 예정")


def _tab_delete(환자id: int):
    st.info("🔧 추후 구현 — 기록 삭제\n\n`util.py` 삭제 함수들 연동 예정")


def _날짜_정규화(날짜str) -> str:
    """YYMMDD → YYYY-MM-DD 변환. 이미 YYYY-MM-DD면 그대로."""
    if not 날짜str:
        return ""
    날짜str = str(날짜str).strip()
    if len(날짜str) == 10 and "-" in 날짜str:
        return 날짜str
    if len(날짜str) == 6 and 날짜str.isdigit():
        yy, mm, dd = 날짜str[:2], 날짜str[2:4], 날짜str[4:6]
        yyyy = f"20{yy}"
        if dd == "00":
            return f"{yyyy}-{mm}"
        return f"{yyyy}-{mm}-{dd}"
    return 날짜str


@st.dialog("진료 기록")
def _show_visit_record(방문: dict):
    """방문 기록 상세를 모달 팝업으로 표시한다."""
    st.markdown(f"**{방문.get('방문일', '')}**")

    bp = ""
    if 방문.get("수축기") and 방문.get("이완기"):
        bp = f"BP {방문['수축기']}/{방문['이완기']}"
    if 방문.get("심박수"):
        bp += f"  HR {방문['심박수']}"
    if bp:
        st.caption(bp)

    st.markdown("---")

    free_text = 방문.get("free_text", "") or "(기록 없음)"
    st.markdown(free_text)

    처방요약 = 방문.get("처방요약", "")
    if 처방요약:
        st.markdown("---")
        st.markdown(f"**처방요약:** {처방요약}")


def _render_grouped_section(
    data: list,
    date_col: str,
    display_cols: list,
    show_visit_btn: bool = False,
    section_key: str = "",
):
    """데이터를 날짜별로 묶어 최신 순으로 테이블 표시한다."""
    if not data:
        st.caption("기록 없음")
        return

    other_cols = [c for c in display_cols if c != date_col]

    grouped: dict = {}
    for row in data:
        날짜 = _날짜_정규화(row.get(date_col, "")) or "날짜 없음"
        grouped.setdefault(날짜, []).append(row)

    for 날짜 in sorted(grouped.keys(), reverse=True):
        rows = grouped[날짜]
        if show_visit_btn:
            날짜_col, 버튼_col = st.columns([5, 1])
            with 날짜_col:
                st.markdown(f"**{날짜}**")
            with 버튼_col:
                if st.button("보기", key=f"visit_{section_key}_{날짜}", help="진료 기록 보기", type="secondary"):
                    _show_visit_record(rows[0])
        else:
            st.markdown(f"**{날짜}**")

        available = [c for c in other_cols if c in rows[0]]
        if available:
            df = pd.DataFrame(rows)[available]
            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
                height=min(len(rows) * 40 + 38, 200),
            )
        else:
            st.caption("표시할 데이터 없음")


def _tab_history(기록: dict):
    """환자 전체이력 — 날짜별/항목별 탭으로 표시한다."""
    tab_날짜, tab_항목 = st.tabs(["📅 날짜별 정렬", "📑 항목별 정렬"])
    with tab_날짜:
        _history_by_date(기록)
    with tab_항목:
        _history_by_category(기록)


def _history_by_category(기록: dict):
    """항목(테이블)별로 접기/펼치기 표시한다."""
    # 방문id → 방문일 매핑 (진단·추적계획·처방의 날짜 보완용)
    방문일_매핑 = {v["방문id"]: v["방문일"] for v in 기록.get("방문", []) if v.get("방문id")}

    for 테이블 in ("진단", "추적계획", "처방"):
        for 행 in 기록.get(테이블, []):
            if not 행.get("방문일") and 행.get("방문id"):
                행["방문일"] = 방문일_매핑.get(행["방문id"], "")

    # 검사처방 분류: 당일/시행완료 → 검사처방, 미래 → 추적계획으로 이동
    당일검사처방 = []
    미래검사처방 = []
    for o in 기록.get("검사처방", []):
        방문일_원본 = 방문일_매핑.get(o.get("방문id"), "")
        처방일_원본 = str(o.get("처방일", ""))
        방문일_비교 = 방문일_원본.replace("-", "")[2:] if len(방문일_원본) == 10 else 방문일_원본
        if 처방일_원본 == 방문일_비교 or o.get("시행여부") == 1:
            당일검사처방.append(o)
        else:
            o["_미래검사"] = True
            미래검사처방.append(o)

    기록_표시용 = dict(기록)
    기록_표시용["검사처방"] = 당일검사처방
    기록_표시용["추적계획"] = list(기록.get("추적계획", [])) + 미래검사처방

    sections = [
        ("🏥 방문 기록",  "방문",     "방문일",    ["수축기","이완기","심박수","키","몸무게","BMI","흡연","음주","운동","처방요약"]),
        ("🔬 진단",       "진단",     "방문일",    ["진단명","상태","비고","표준코드"]),
        ("🧪 검사결과",   "검사결과", "검사시행일", ["검사항목","결과값","단위","참고범위"]),
        ("📷 영상검사",   "영상검사", "검사시행일", ["검사종류","결과요약","주요수치"]),
        ("📅 추적계획",   "추적계획", "예정일",    ["내용","완료여부"]),
        ("💊 처방",       "처방",     "방문일",    ["약품명","성분명","용량","용법","일수"]),
        ("🔬 검사처방",   "검사처방", "처방일",    ["검사명","시행여부"]),
    ]

    for title, key, date_col, display_cols in sections:
        data = 기록_표시용.get(key, [])
        is_first = key in ("방문", "진단")
        is_방문 = key == "방문"
        with st.expander(f"{title} ({len(data)}건)", expanded=is_first):
            _render_grouped_section(
                data, date_col, display_cols,
                show_visit_btn=is_방문,
                section_key=key,
            )


def _history_by_date(기록: dict):
    """모든 기록을 날짜별로 묶어 최신 순으로 표시한다."""
    # 방문id → 방문일 매핑
    방문일_매핑 = {v["방문id"]: v["방문일"] for v in 기록.get("방문", []) if v.get("방문id")}

    # 날짜별 수집 헬퍼
    def _빈항목():
        return {"방문": [], "진단": [], "검사결과": [], "영상검사": [], "처방": [], "검사처방": [], "추적계획": []}

    날짜별: dict = {}

    for v in 기록.get("방문", []):
        날짜 = _날짜_정규화(v.get("방문일", ""))
        날짜별.setdefault(날짜, _빈항목())["방문"].append(v)

    for d in 기록.get("진단", []):
        날짜 = _날짜_정규화(d.get("방문일") or 방문일_매핑.get(d.get("방문id"), ""))
        날짜별.setdefault(날짜, _빈항목())["진단"].append(d)

    for lr in 기록.get("검사결과", []):
        날짜 = _날짜_정규화(lr.get("검사시행일", ""))
        날짜별.setdefault(날짜, _빈항목())["검사결과"].append(lr)

    for img in 기록.get("영상검사", []):
        날짜 = _날짜_정규화(img.get("검사시행일", ""))
        날짜별.setdefault(날짜, _빈항목())["영상검사"].append(img)

    for rx in 기록.get("처방", []):
        날짜 = _날짜_정규화(rx.get("방문일") or 방문일_매핑.get(rx.get("방문id"), ""))
        날짜별.setdefault(날짜, _빈항목())["처방"].append(rx)

    # 검사처방 분류: 당일 처방 → 검사처방, 미래 처방 → 추적계획
    for o in 기록.get("검사처방", []):
        방문일_원본 = 방문일_매핑.get(o.get("방문id"), "")
        처방일_원본 = str(o.get("처방일", ""))
        방문일_비교 = 방문일_원본.replace("-", "")[2:] if len(방문일_원본) == 10 else 방문일_원본
        날짜 = _날짜_정규화(방문일_원본)
        if 처방일_원본 == 방문일_비교 or o.get("시행여부") == 1:
            날짜별.setdefault(날짜, _빈항목())["검사처방"].append(o)
        else:
            o["_미래검사"] = True
            날짜별.setdefault(날짜, _빈항목())["추적계획"].append(o)

    # 추적계획 — 방문일 기준 그룹핑
    for t in 기록.get("추적계획", []):
        날짜 = _날짜_정규화(t.get("방문일") or 방문일_매핑.get(t.get("방문id"), ""))
        날짜별.setdefault(날짜, _빈항목())["추적계획"].append(t)

    if not 날짜별:
        st.caption("기록 없음")
        return

    sorted_dates = sorted(날짜별.keys(), key=lambda x: str(x or ""), reverse=True)

    for i, 날짜 in enumerate(sorted_dates):
        항목들 = 날짜별[날짜]
        총건수 = sum(len(v) for v in 항목들.values())

        with st.expander(f"📅 {날짜 or '날짜 없음'} ({총건수}건)", expanded=(i == 0)):

            # 활력징후 + 진료기록
            for v in 항목들["방문"]:
                bp_parts = []
                if v.get("수축기") and v.get("이완기"):
                    bp_parts.append(f"BP {v['수축기']}/{v['이완기']}")
                if v.get("심박수"):
                    bp_parts.append(f"HR {v['심박수']}")
                if v.get("몸무게") and v.get("키"):
                    bp_parts.append(f"BMI {v.get('BMI', '')}")
                if bp_parts:
                    st.caption("활력징후: " + "  |  ".join(bp_parts))
                ft = v.get("free_text", "")
                if ft and ft.strip():
                    st.markdown("**진료 기록:**")
                    st.markdown(ft)
                rx_summary = v.get("처방요약", "")
                if rx_summary and rx_summary.strip():
                    st.caption(f"처방요약: {rx_summary}")

            # 진단
            if 항목들["진단"]:
                st.markdown("**진단:**")
                for d in 항목들["진단"]:
                    상태표시 = f"({d.get('상태', '')})" if d.get('상태') else ""
                    st.caption(f"  {d.get('진단명', '')} {상태표시}")

            # 검사결과
            if 항목들["검사결과"]:
                st.markdown("**검사결과:**")
                cols_사용 = [c for c in ["검사항목", "결과값", "단위", "참고범위"] if c in 항목들["검사결과"][0]]
                if cols_사용:
                    df = pd.DataFrame(항목들["검사결과"])[cols_사용]
                    st.dataframe(df, use_container_width=True, hide_index=True,
                                 height=min(len(df) * 40 + 38, 200))

            # 영상검사
            if 항목들["영상검사"]:
                st.markdown("**영상검사:**")
                for img in 항목들["영상검사"]:
                    st.caption(f"  {img.get('검사종류', '')} — {img.get('결과요약', '')}")

            # 처방
            if 항목들["처방"]:
                st.markdown("**처방:**")
                cols_사용 = [c for c in ["약품명", "성분명", "용량", "용법", "일수"] if c in 항목들["처방"][0]]
                if cols_사용:
                    df = pd.DataFrame(항목들["처방"])[cols_사용]
                    st.dataframe(df, use_container_width=True, hide_index=True,
                                 height=min(len(df) * 40 + 38, 200))

            # 검사처방
            if 항목들["검사처방"]:
                st.markdown("**검사처방:**")
                for o in 항목들["검사처방"]:
                    시행 = "✅" if o.get("시행여부") else "⬜"
                    처방일 = _날짜_정규화(o.get("처방일", ""))
                    st.caption(f"  {시행} {o.get('검사명', '')} (처방일: {처방일})")

            # 추적계획 (기존 추적계획 + 미래 검사처방 혼합)
            if 항목들["추적계획"]:
                st.markdown("**추적계획:**")
                for t in 항목들["추적계획"]:
                    if t.get("_미래검사"):
                        시행 = "✅" if t.get("시행여부") else "⬜"
                        예정일 = _날짜_정규화(t.get("처방일", ""))
                        st.caption(f"  {시행} 🔬 {t.get('검사명', '')} (예정: {예정일})")
                    else:
                        완료 = "✅" if t.get("완료여부") else "⬜"
                        예정일 = _날짜_정규화(t.get("예정일", ""))
                        st.caption(f"  {완료} {t.get('내용', '')} (예정: {예정일})")


# ============================================================
# 연구 화면
# ============================================================
def _render_research_page():
    st.markdown("## 📊 연구")

    tab1, tab2, tab3, tab4 = st.tabs([
        "📈 전체 통계",
        "🔍 자연어 검색",
        "🤖 AI 자동 분석",
        "📐 단계별 분석",
    ])
    with tab1:
        st.info("🔧 추후 구현 — 전체 통계\n\n`util.통계보기()` 연동 예정")
    with tab2:
        st.info("🔧 추후 구현 — 자연어 검색 (NL2SQL)\n\n`research_module.연구검색()` 연동 예정")
    with tab3:
        st.info("🔧 추후 구현 — AI 자동 분석\n\n`research_module.통계분석_자동()` 연동 예정")
    with tab4:
        st.info("🔧 추후 구현 — 단계별 분석\n\n`research_module.통계분석_단계별()` 연동 예정")


# ============================================================
# 설정 화면
# ============================================================
def _render_settings_page():
    st.markdown("## ⚙️ 설정")

    st.markdown("### 모드 선택")
    새_모드 = st.radio(
        "mode_radio",
        ["연구용", "진료보조용"],
        index=0 if st.session_state.mode == "연구용" else 1,
        help="연구용: 저장 포함 5단계 | 진료보조용: 제안까지 3단계",
    )
    if 새_모드 != st.session_state.mode:
        st.session_state.mode = 새_모드

    st.markdown("---")

    st.markdown("### DB 백업")
    if st.button("💾  백업 실행", type="primary", key="settings_backup"):
        try:
            경로 = DB백업()
            st.success(f"백업 완료: `{os.path.basename(경로)}`")
        except Exception as e:
            st.error(str(e))


# ============================================================
# 메인 진입점
# ============================================================
def main():
    _init_state()
    _inject_css()
    _render_sidebar()

    page = st.session_state.page

    if page == "홈":
        _render_home()
    elif page == "연구":
        _render_research_page()
    elif page == "신환등록":
        _render_new_patient_form()
    elif page == "환자상세":
        if st.session_state.selected_patient_id:
            _render_patient_detail(st.session_state.selected_patient_id)
        else:
            st.session_state.page = "홈"
            st.rerun()
    elif page == "설정":
        _render_settings_page()
    else:
        _render_home()


if __name__ == "__main__":
    main()
