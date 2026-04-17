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
import streamlit.components.v1 as components

from util import (
    DB연결,
    미분석차트조회,
    나이계산,
    환자검색,
    환자등록,
    환자목록가져오기,
    환자전체기록조회,
    환자정보수정,
    방문기록삭제,
    환자삭제,
    방문기록추가,
    방문기록_일괄수정,
)
from practice_analyzer import AI_패턴분석, 데일리_SQL체크
from backup import DB백업
from briefing_generator import 브리핑생성, 브리핑생성_최근차트
from chart_analyzer import (
    차트_데이터만_수정, 차트_재분석_저장, _변경사항_추출,
    차트분석, 제안_free_text_추가, 재추출, 분석결과_저장,
)

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
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+KR:wght@300;400;500;600;700&display=swap');

    /* 전체 글자체 — Inter(영문) + Noto Sans KR(한글) */
    html, body, [class*="css"], .stApp,
    .stMarkdown, .stMarkdown p, .stMarkdown span,
    .stTextInput input, .stTextArea textarea,
    button, label, .stTabs [data-baseweb="tab"],
    .stDataFrame, .stMetric, .stCaption,
    [data-testid="stSidebar"] * {
        font-family: 'Inter', 'Noto Sans KR', -apple-system, BlinkMacSystemFont,
                     'Segoe UI', sans-serif !important;
    }

    /* ── 라이트 테마 기본 ── */
    .stApp {
        background-color: #ffffff !important;
        color: #1a1a1a !important;
    }
    section[data-testid="stMain"] {
        background-color: #ffffff !important;
    }

    /* 입력 필드 */
    .stTextInput input,
    .stTextArea textarea,
    .stSelectbox select,
    [data-baseweb="input"] input,
    [data-baseweb="textarea"] textarea {
        background-color: #ffffff !important;
        border: 1px solid #ddd8ce !important;
        color: #1a1a1a !important;
        border-radius: 6px !important;
    }
    .stTextInput input:focus,
    .stTextArea textarea:focus,
    [data-baseweb="input"] input:focus {
        border-color: #c9a84c !important;
        box-shadow: 0 0 0 1px #c9a84c !important;
    }
    /* 라벨 */
    .stTextInput label, .stTextArea label,
    .stSelectbox label, .stNumberInput label,
    .stDateInput label, .stRadio label {
        color: #6b6560 !important;
    }
    /* expander */
    .stExpander details {
        background-color: #faf9f6 !important;
        border: 1px solid #e8e4dc !important;
        border-radius: 8px !important;
    }
    .stExpander summary {
        color: #1a1a1a !important;
    }
    .stExpander summary svg {
        fill: #c9a84c !important;
    }
    /* 데이터프레임/테이블 */
    .stDataFrame, [data-testid="stDataFrame"] {
        background-color: #ffffff !important;
    }
    .stDataFrame th {
        background-color: #f5f2ec !important;
        color: #6b6560 !important;
        border-bottom: 1px solid #e8e4dc !important;
    }
    .stDataFrame td {
        background-color: #ffffff !important;
        color: #1a1a1a !important;
        border-bottom: 1px solid #e8e4dc !important;
    }
    /* 탭 */
    .stTabs [data-baseweb="tab-list"] {
        background-color: transparent !important;
        border-bottom: 1px solid #e8e4dc !important;
    }
    .stTabs [data-baseweb="tab"] {
        color: #9a9590 !important;
        background-color: transparent !important;
    }
    .stTabs [aria-selected="true"] {
        color: #a08530 !important;
        border-bottom: 2px solid #c9a84c !important;
    }
    /* 일반 버튼 — primary */
    button[kind="primary"] {
        background-color: #c9a84c !important;
        border-color: #c9a84c !important;
        color: #ffffff !important;
    }
    button[kind="primary"]:hover {
        background-color: #a08530 !important;
        border-color: #a08530 !important;
    }
    /* 일반 버튼 — secondary */
    section[data-testid="stMain"] button[kind="secondary"] {
        background-color: #ffffff !important;
        border: 1px solid #ddd8ce !important;
        color: #1a1a1a !important;
    }
    section[data-testid="stMain"] button[kind="secondary"]:hover {
        background-color: #faf9f6 !important;
        border-color: #c9a84c !important;
    }
    /* selectbox / dropdown */
    [data-baseweb="select"] > div {
        background-color: #ffffff !important;
        border-color: #ddd8ce !important;
        color: #1a1a1a !important;
    }
    [data-baseweb="popover"] {
        background-color: #ffffff !important;
    }
    [data-baseweb="menu"] {
        background-color: #ffffff !important;
    }
    [data-baseweb="menu"] li {
        color: #1a1a1a !important;
    }
    [data-baseweb="menu"] li:hover {
        background-color: #faf9f6 !important;
    }
    /* radio */
    .stRadio [data-testid="stMarkdownContainer"] p {
        color: #1a1a1a !important;
    }
    /* caption */
    .stCaption, .stMarkdown small {
        color: #9a9590 !important;
    }
    /* alert / info box */
    .stAlert {
        background-color: #faf9f6 !important;
        border-color: #e8e4dc !important;
        color: #1a1a1a !important;
    }
    /* 구분선 */
    hr {
        border-color: #e8e4dc !important;
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

    /* ── 사이드바 ── */
    section[data-testid="stSidebar"] > div:first-child {
        background-color: #f8f7f3 !important;
        border-right: 1px solid #e8e4dc !important;
        padding-top: 1rem !important;
    }
    section[data-testid="stSidebar"] .stMarkdown p,
    section[data-testid="stSidebar"] .stMarkdown span,
    section[data-testid="stSidebar"] label {
        color: #6b6560 !important;
    }
    section[data-testid="stSidebar"] hr {
        border-color: #e8e4dc !important;
        margin: 8px 0;
    }
    /* 사이드바 버튼 — secondary (기본 환자 목록) */
    section[data-testid="stSidebar"] button[kind="secondary"] {
        background: transparent !important;
        border: 1px solid transparent !important;
        color: #3a3530 !important;
        transition: background 0.15s;
    }
    section[data-testid="stSidebar"] button[kind="secondary"]:hover {
        background: #edeae3 !important;
        border-color: #ddd8ce !important;
    }
    /* 사이드바 버튼 — primary (선택된 환자) */
    section[data-testid="stSidebar"] button[kind="primary"] {
        background: #c9a84c !important;
        border-color: #c9a84c !important;
        color: #ffffff !important;
    }
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
    /* 헤더/하단 아이콘 행 버튼 중앙 정렬 */
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
    section[data-testid="stSidebar"] > div[data-testid="stSidebarResizeHandle"] {
        display: none !important;
    }
    button[data-testid="stSidebarCollapseButton"],
    [data-testid="stSidebarCollapsedControl"] {
        display: none !important;
    }

    /* ── 요약 카드 ── */
    .stat-card {
        background: #ffffff;
        border-radius: 10px;
        padding: 20px 24px;
        border-left: 4px solid #c9a84c;
        border: 1px solid #e8e4dc;
        border-left: 4px solid #c9a84c;
    }
    .stat-card.warn  { border-left-color: #c9a84c; }
    .stat-card.danger { border-left-color: #c0392b; }
    .stat-card .label { font-size: 13px; color: #9a9590; margin-bottom: 4px; }
    .stat-card .value { font-size: 30px; font-weight: 700; color: #1a1a1a; }
    .stat-card .sub   { font-size: 12px; color: #b0ac9a; margin-top: 4px; }

    /* ── 환자 헤더 ── */
    .patient-header {
        display: flex;
        align-items: center;
        gap: 16px;
        padding: 16px;
        background: #faf9f6;
        border-radius: 10px;
        margin-bottom: 16px;
        border-left: 3px solid #c9a84c;
        border: 1px solid #e8e4dc;
        border-left: 3px solid #c9a84c;
    }

    /* ── 데일리 체크 항목 ── */
    .daily-item {
        padding: 10px 14px;
        border-radius: 8px;
        margin-bottom: 6px;
        font-size: 14px;
        line-height: 1.5;
    }
    .daily-item.danger {
        background: #fdf0ee;
        border-left: 3px solid #c0392b;
        color: #8b2020;
    }
    .daily-item.warn {
        background: #fdf8ec;
        border-left: 3px solid #c9a84c;
        color: #7a5c10;
    }
    .daily-item.info {
        background: #f0f5fb;
        border-left: 3px solid #5b8db8;
        color: #2a5070;
    }

    /* ── 신환 등록 버튼 중앙 정렬 ── */
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
        "page_history":       [],
        "last_no_match_search": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ============================================================
# 페이지 이동 헬퍼
# ============================================================
def _navigate_to(page: str, **kwargs):
    """페이지 이동 시 현재 페이지를 히스토리에 저장한다."""
    current = {
        "page": st.session_state.page,
        "selected_patient_id": st.session_state.selected_patient_id,
    }
    st.session_state.page_history.append(current)
    if len(st.session_state.page_history) > 10:
        st.session_state.page_history = st.session_state.page_history[-10:]
    st.session_state.page = page
    for k, v in kwargs.items():
        st.session_state[k] = v
    st.rerun()


def _go_back():
    """이전 페이지로 돌아간다."""
    if st.session_state.page_history:
        prev = st.session_state.page_history.pop()
        st.session_state.page = prev["page"]
        st.session_state.selected_patient_id = prev["selected_patient_id"]
        st.rerun()


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
                _navigate_to("홈")
        with col_research:
            if st.button(
                "📊", key="nav_연구", use_container_width=True,
                help="연구",
                type="primary" if st.session_state.page == "연구" else "secondary",
            ):
                _navigate_to("연구")

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
            _navigate_to("신환등록", selected_patient_id=None)
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
                _navigate_to("설정")
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
    """사이드바 환자 목록을 표시한다. 검색 시 전체 목록 유지 + 매칭 환자 최상단."""
    전체목록 = _환자목록_진단포함()

    if not 전체목록:
        st.caption("등록된 환자가 없습니다.")
        return

    if 검색어.strip():
        검색어_clean = 검색어.strip()
        매칭, 비매칭 = [], []
        for p in 전체목록:
            이름 = p.get("이름", "")
            병록번호 = str(p.get("병록번호", ""))
            if 검색어_clean in 이름 or 검색어_clean in 병록번호:
                매칭.append(p)
            else:
                비매칭.append(p)

        if 매칭:
            환자목록 = 매칭 + 비매칭
            # 현재 선택 환자가 매칭 목록에 없으면 첫 번째 매칭 환자 자동 선택
            if st.session_state.selected_patient_id not in [p["환자id"] for p in 매칭]:
                st.session_state.selected_patient_id = 매칭[0]["환자id"]
                st.session_state.page = "환자상세"
        else:
            환자목록 = 전체목록
            # 검색어가 바뀐 경우에만 팝업 표시 (무한 팝업 방지)
            if st.session_state.last_no_match_search != 검색어_clean:
                st.session_state.last_no_match_search = 검색어_clean
                _검색실패_팝업(검색어_clean)
    else:
        환자목록 = 전체목록

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
            _navigate_to("환자상세", selected_patient_id=환자["환자id"])


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
            <div class="value">{환자수}<span style="font-size:16px;color:#5a5550;font-weight:400;">명</span></div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        warn_class = " warn" if 미분석수 > 0 else ""
        st.markdown(f"""
        <div class="stat-card{warn_class}">
            <div class="label">📋 미분석 차트</div>
            <div class="value">{미분석수}<span style="font-size:16px;color:#5a5550;font-weight:400;">건</span></div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        danger_class = " danger" if 지연수 > 0 else ""
        st.markdown(f"""
        <div class="stat-card{danger_class}">
            <div class="label">⚠️ 추적 지연</div>
            <div class="value">{지연수}<span style="font-size:16px;color:#5a5550;font-weight:400;">건</span></div>
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
    # 환자 이름 → 환자id 매핑
    이름_id맵 = {p["이름"]: p["환자id"] for p in 환자목록가져오기()}

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
        이름매치 = re.search(r"[:\s]+(\S+)\s*—", msg)
        환자id = 이름_id맵.get(이름매치.group(1)) if 이름매치 else None
        if 환자id:
            if st.button(msg, key=f"daily_{abs(hash(msg)) % 100000}", use_container_width=True):
                _navigate_to("환자상세", selected_patient_id=환자id)
        else:
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
    hdr_left, hdr_right = st.columns([8, 1])
    with hdr_left:
        st.markdown("### ➕ 신환 등록")
    with hdr_right:
        if st.session_state.page_history:
            if st.button("← 뒤로", key="btn_back_new", type="secondary"):
                _go_back()

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

        _navigate_to("환자상세", selected_patient_id=환자id)


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

    # ── 환자 헤더 (1블록: 신상 + 가족력/약부작용 + 뒤로)
    hdr_left, hdr_mid, hdr_right = st.columns([4, 5, 1])

    with hdr_left:
        st.markdown(f"""
        <div style="background:#faf9f6;border:1px solid #e8e4dc;border-left:3px solid #c9a84c;border-radius:10px;padding:12px 16px;">
            <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;">
                <span style="font-size:18px;font-weight:700;color:#1a1a1a;">{이름}</span>
                <span style="font-size:14px;color:#6b6560;">{병록번호_숫자만}</span>
                <span style="font-size:14px;color:#6b6560;">{나이표시}/{성별}</span>
                <span style="font-size:14px;color:#6b6560;">{환자.get('생년월일', '')}</span>
            </div>
            <div style="font-size:13px;color:#a08530;margin-top:4px;">{주진단표시}</div>
        </div>
        """, unsafe_allow_html=True)

    with hdr_mid:
        가족력_현재  = 환자.get("가족력", "")      or ""
        약부작용_현재 = 환자.get("약부작용이력", "") or ""

        fi_col, fb_col = st.columns([5, 1], vertical_alignment="bottom")
        with fi_col:
            가족력_입력 = st.text_input("가족력", value=가족력_현재, key=f"fh_{환자id}")
        with fb_col:
            if st.button("저장", key=f"fh_save_{환자id}", use_container_width=True):
                환자정보수정(환자id, "가족력", 가족력_입력)
                st.toast("가족력 저장 완료")
                st.rerun()

        ai_col, ab_col = st.columns([5, 1], vertical_alignment="bottom")
        with ai_col:
            약부작용_입력 = st.text_input("약부작용이력", value=약부작용_현재, key=f"ae_{환자id}")
        with ab_col:
            if st.button("저장", key=f"ae_save_{환자id}", use_container_width=True):
                환자정보수정(환자id, "약부작용이력", 약부작용_입력)
                st.toast("약부작용이력 저장 완료")
                st.rerun()

    with hdr_right:
        if st.session_state.page_history:
            if st.button("← 뒤로", key="btn_back_detail", type="secondary"):
                _go_back()

    col_left, col_right = st.columns([6, 4], gap="medium")

    with col_left:
        with st.container(height=650, border=False):
            tabs = st.tabs(["📋 브리핑", "📝 진료기록", "✏️ 기록 수정"])
            with tabs[0]:
                _tab_briefing(환자id)
            with tabs[1]:
                _tab_chart_entry(환자id)
            with tabs[2]:
                _tab_edit(환자id)

    with col_right:
        with st.container(height=650, border=False):
            _tab_history(기록)


def _tab_briefing(환자id: int):
    cache_key = f"briefing_{환자id}"

    if st.session_state.get(cache_key):
        st.markdown(st.session_state[cache_key])
        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button("🔄 다시 생성", key=f"briefing_reload_{환자id}"):
                st.session_state[cache_key] = None
                st.rerun()
    else:
        브리핑모드 = st.radio(
            "브리핑 방식",
            ["전체 기록 분석 — 모든 방문/검사 데이터를 종합 분석",
             "최근 차트 분석 — 가장 최근 진료 기록만 분석"],
            key=f"briefing_mode_{환자id}",
            help="차트에 이전 기록을 요약해서 적는 스타일이면 '최근 차트'가 효율적입니다.",
        )

        st.info("AI 브리핑을 생성합니다. API 비용이 발생합니다.")

        if st.button("📋 AI 브리핑 생성", type="primary", key=f"briefing_gen_{환자id}"):
            with st.spinner("AI가 브리핑을 생성 중입니다..."):
                if "전체" in 브리핑모드:
                    결과 = 브리핑생성(환자id)
                else:
                    결과 = 브리핑생성_최근차트(환자id)
            if 결과:
                st.session_state[cache_key] = 결과
                st.rerun()
            else:
                st.error("브리핑 생성에 실패했습니다. API 키와 네트워크를 확인하세요.")


def _tab_chart_entry(환자id: int):
    mode = st.session_state.mode
    총단계 = 3 if mode == "진료보조용" else 5

    현재단계 = st.session_state.get(f"chart_step_{환자id}", 1)

    단계명 = ["① 차트 입력", "② AI 제안", "③ 보완 확인", "④ 추출 데이터", "⑤ 저장"]
    표시단계 = 단계명[:총단계]

    cols = st.columns(len(표시단계))
    for i, (col, label) in enumerate(zip(cols, 표시단계)):
        with col:
            단계번호 = i + 1
            if 단계번호 < 현재단계:
                st.markdown(f"<span style='color:#5a8a5a;'>✅ {label}</span>", unsafe_allow_html=True)
            elif 단계번호 == 현재단계:
                st.markdown(f"**{label}**")
            else:
                st.markdown(f"<span style='color:#9a9590;'>{label}</span>", unsafe_allow_html=True)

    st.markdown("---")

    if 현재단계 == 1:
        _chart_step1(환자id)
    elif 현재단계 == 2:
        _chart_step2(환자id)
    elif 현재단계 == 3:
        _chart_step3(환자id, mode)
    elif 현재단계 == 4 and 총단계 >= 4:
        _chart_step4(환자id)
    elif 현재단계 == 5 and 총단계 >= 5:
        _chart_step5(환자id)


# ── 진료기록 단계별 상태 초기화 헬퍼 ──
def _chart_state_초기화(환자id):
    for k in [f"chart_step_{환자id}", f"chart_분석결과_{환자id}",
              f"chart_승인texts_{환자id}", f"chart_보완본_{환자id}",
              f"chart_free_text_{환자id}", f"chart_방문일_{환자id}",
              f"chart_방문id_{환자id}", f"chart_저장건수_{환자id}"]:
        st.session_state.pop(k, None)


def _chart_step1(환자id):
    """Step 1: 방문일 + free-text 입력 → AI 분석 요청"""
    오늘 = datetime.today().strftime("%y%m%d")
    방문일 = st.text_input(
        "방문일 (YYMMDD, 빈칸=오늘)", value="",
        key=f"s1_date_{환자id}",
        placeholder=f"빈칸이면 오늘({오늘})",
    )
    free_text = st.text_area(
        "진료 기록 (free-text)", height=200,
        key=f"s1_ft_{환자id}",
        placeholder="예) HTN f/u. BP 140/90. amlodipine 5mg qd 복용 중.\nLDL 이전 130으로 높아 rosuvastatin 추가 고려.\n다음 3개월 후 Lab f/u 예정.",
    )

    if st.button("AI 분석 요청 →", type="primary", key=f"s1_submit_{환자id}"):
        if not free_text.strip():
            st.error("진료 기록을 입력하세요.")
            return

        실제방문일 = 방문일.strip() or 오늘
        st.session_state[f"chart_방문일_{환자id}"] = 실제방문일
        st.session_state[f"chart_free_text_{환자id}"] = free_text.strip()

        # 방문 기록 먼저 생성 (분석완료=0, 나중에 저장 후 1로 갱신)
        방문id = 방문기록추가(환자id, 실제방문일,
                            수축기=None, 이완기=None, 심박수=None,
                            키=None, 몸무게=None, BMI=None,
                            free_text=free_text.strip(), 분석완료=0)
        if not 방문id:
            st.error("방문 기록 생성에 실패했습니다.")
            return
        st.session_state[f"chart_방문id_{환자id}"] = 방문id

        with st.spinner("AI가 차트를 분석 중입니다..."):
            결과 = 차트분석(환자id, free_text.strip(), 실제방문일)

        if 결과:
            st.session_state[f"chart_분석결과_{환자id}"] = 결과
            st.session_state[f"chart_step_{환자id}"] = 2
            st.rerun()
        else:
            st.error("AI 분석에 실패했습니다. API 키와 네트워크를 확인하세요.")


def _chart_step2(환자id):
    """Step 2: AI 제안 확인 — 승인한 항목을 free-text에 추가할 텍스트로 구성"""
    분석결과 = st.session_state.get(f"chart_분석결과_{환자id}", {})
    if not 분석결과:
        st.error("분석 결과가 없습니다.")
        st.session_state[f"chart_step_{환자id}"] = 1
        st.rerun()
        return

    suggestions  = 분석결과.get("suggestions", [])
    legal        = 분석결과.get("legal", [])
    ic           = 분석결과.get("informed_consent", {})
    has_any      = bool(suggestions or legal or ic.get("chart_text"))

    if not has_any:
        st.info("AI 검토 의견이 없습니다. 다음 단계로 진행합니다.")
        st.session_state[f"chart_승인texts_{환자id}"] = []
        st.session_state[f"chart_step_{환자id}"] = 3
        st.rerun()
        return

    st.markdown("AI가 제안하는 보완/확인 사항입니다. 차트에 반영할 항목을 선택하세요.")

    approved_flags = {}

    if suggestions:
        st.markdown("**💡 AI 검토 의견**")
        for i, s in enumerate(suggestions):
            내용 = s.get("content", "")
            사유 = s.get("reason", "")
            chart_text = s.get("chart_text", "")
            라벨 = f"{내용}" + (f"  ({사유})" if 사유 else "")
            approved_flags[f"sug_{i}"] = st.checkbox(라벨, value=bool(chart_text), key=f"s2_sug_{환자id}_{i}")
            if chart_text:
                st.caption(f'  → 추가될 문구: "{chart_text}"')

    if legal:
        st.markdown("**⚖️ 법적 확인사항**")
        for i, l in enumerate(legal):
            내용 = l.get("content", "")
            사유 = l.get("reason", "")
            chart_text = l.get("chart_text", "")
            라벨 = f"{내용}" + (f"  ({사유})" if 사유 else "")
            approved_flags[f"legal_{i}"] = st.checkbox(라벨, value=bool(chart_text), key=f"s2_legal_{환자id}_{i}")
            if chart_text:
                st.caption(f'  → 추가될 문구: "{chart_text}"')

    ic_text = ic.get("chart_text", "")
    if ic_text:
        st.markdown("**📢 설명의무 기록**")
        drugs = ", ".join(ic.get("drugs", []))
        se    = ", ".join(ic.get("side_effects", []))
        if drugs:
            st.caption(f"약물: {drugs}  |  부작용: {se}")
        approved_flags["ic"] = st.checkbox(f'"{ic_text}"', value=True, key=f"s2_ic_{환자id}")

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("← 이전 단계", key=f"s2_back_{환자id}"):
            st.session_state[f"chart_step_{환자id}"] = 1
            st.rerun()
    with col2:
        if st.button("승인 항목 확정 →", type="primary", key=f"s2_next_{환자id}"):
            # 승인된 항목의 chart_text 수집
            approved_texts = []
            for i, s in enumerate(suggestions):
                if approved_flags.get(f"sug_{i}") and s.get("chart_text"):
                    approved_texts.append(s["chart_text"])
            for i, l in enumerate(legal):
                if approved_flags.get(f"legal_{i}") and l.get("chart_text"):
                    approved_texts.append(l["chart_text"])
            if approved_flags.get("ic") and ic_text:
                approved_texts.append(ic_text)

            st.session_state[f"chart_승인texts_{환자id}"] = approved_texts
            st.session_state[f"chart_step_{환자id}"] = 3
            st.rerun()


def _chart_step3(환자id, mode):
    """Step 3: 보완 차트 확인 — 원본 vs AI 보완본 비교, 편집 가능"""
    원본       = st.session_state.get(f"chart_free_text_{환자id}", "")
    approved_texts = st.session_state.get(f"chart_승인texts_{환자id}", [])
    보완본     = 제안_free_text_추가(원본, approved_texts)

    st.markdown("원본 / AI 보완본을 확인하고 최종본을 편집하세요.")

    col_orig, col_enhanced = st.columns(2)
    with col_orig:
        st.markdown("**원본 free-text**")
        st.text_area("원본", value=원본, height=220, disabled=True, key=f"s3_orig_{환자id}")
    with col_enhanced:
        st.markdown("**AI 보완본 (편집 가능)**")
        최종본 = st.text_area("보완본", value=보완본, height=220, key=f"s3_enhanced_{환자id}")

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("← 이전 단계", key=f"s3_back_{환자id}"):
            st.session_state[f"chart_step_{환자id}"] = 2
            st.rerun()
    with col2:
        다음라벨 = "최종 확정 (저장 없음) ✓" if mode == "진료보조용" else "최종 확정 →"
        if st.button(다음라벨, type="primary", key=f"s3_next_{환자id}"):
            st.session_state[f"chart_보완본_{환자id}"] = 최종본

            # 방문 free_text 업데이트 (보완본으로)
            방문id = st.session_state.get(f"chart_방문id_{환자id}")
            if 방문id and 최종본 != 원본:
                방문기록_일괄수정(방문id, {"free_text": 최종본})

            if mode == "진료보조용":
                st.success("차트 보완 완료! (진료보조용 모드 — 데이터 저장 없음)")
                _chart_state_초기화(환자id)
                st.rerun()
            else:
                st.session_state[f"chart_step_{환자id}"] = 4
                st.rerun()


def _chart_step4(환자id):
    """Step 4: 추출 데이터 확인 — 체크박스로 저장 항목 선택"""
    분석결과  = st.session_state.get(f"chart_분석결과_{환자id}", {})
    extraction = 분석결과.get("extraction", {})
    방문id    = st.session_state.get(f"chart_방문id_{환자id}")
    보완본    = st.session_state.get(f"chart_보완본_{환자id}", "")
    방문일    = st.session_state.get(f"chart_방문일_{환자id}", "")

    st.markdown("AI가 추출한 데이터입니다. 저장할 항목을 확인하세요.")

    # 각 항목 체크박스 렌더링 + 체크 결과 수집
    vitals    = extraction.get("vitals", {})
    lifestyle = extraction.get("lifestyle", {})
    diagnoses   = [d for d in extraction.get("diagnoses", [])   if d.get("구분") != "기존참조"]
    lab_results = [l for l in extraction.get("lab_results", []) if l.get("구분") != "기존참조"]
    imaging     = [i for i in extraction.get("imaging", [])     if i.get("구분") != "기존참조"]
    prescriptions = [p for p in extraction.get("prescriptions", []) if p.get("구분") not in ("기존참조",)]
    tracking    = [t for t in extraction.get("tracking", [])    if t.get("구분") != "기존참조"]
    test_orders = [o for o in extraction.get("test_orders", []) if o.get("구분") != "기존참조"]
    ps          = extraction.get("prescription_summary", "")
    patient_info = extraction.get("patient_info", {})

    chk = {}  # 체크 결과 저장

    if any(vitals.get(k) for k in ["수축기", "이완기", "심박수", "키", "몸무게"]):
        bp  = f"BP {vitals.get('수축기', '?')}/{vitals.get('이완기', '?')}"
        hr  = f"  HR {vitals['심박수']}" if vitals.get("심박수") else ""
        ht  = f"  키 {vitals['키']}cm"   if vitals.get("키") else ""
        wt  = f"  체중 {vitals['몸무게']}kg" if vitals.get("몸무게") else ""
        bmi = f"  BMI {vitals['BMI']}"   if vitals.get("BMI") else ""
        chk["vitals"] = st.checkbox(f"💓 활력징후: {bp}{hr}{ht}{wt}{bmi}", value=True, key=f"s4_vitals_{환자id}")

    if any(lifestyle.get(k) for k in ["흡연", "음주", "운동"]):
        항목들 = [f"{k}: {lifestyle[k]}" for k in ["흡연", "음주", "운동"] if lifestyle.get(k)]
        chk["lifestyle"] = st.checkbox(f"🚶 생활습관: {', '.join(항목들)}", value=True, key=f"s4_life_{환자id}")

    if diagnoses:
        st.markdown("**🩺 진단**")
        chk["diagnoses"] = []
        for i, d in enumerate(diagnoses):
            표시 = f"{d.get('진단명', '')} ({d.get('상태', '')})"
            checked = st.checkbox(f"  {표시}", value=True, key=f"s4_dx_{환자id}_{i}")
            if checked:
                chk["diagnoses"].append(d)

    if lab_results:
        st.markdown("**🧪 검사결과**")
        chk["lab_results"] = []
        for i, l in enumerate(lab_results):
            표시 = f"{l.get('검사항목', '')} {l.get('결과값', '')}{l.get('단위', '')}"
            checked = st.checkbox(f"  {표시}", value=True, key=f"s4_lab_{환자id}_{i}")
            if checked:
                chk["lab_results"].append(l)

    if imaging:
        st.markdown("**📷 영상검사**")
        chk["imaging"] = []
        for i, e in enumerate(imaging):
            표시 = f"{e.get('검사종류', '')} ({e.get('검사시행일', '')})"
            checked = st.checkbox(f"  {표시}", value=True, key=f"s4_img_{환자id}_{i}")
            if checked:
                chk["imaging"].append(e)

    if prescriptions:
        st.markdown("**💊 처방**")
        chk["prescriptions"] = []
        for i, p in enumerate(prescriptions):
            표시 = f"{p.get('약품명', '')} {p.get('용량', '')} {p.get('용법', '')} {p.get('일수', 0)}일"
            checked = st.checkbox(f"  {표시}", value=True, key=f"s4_rx_{환자id}_{i}")
            if checked:
                chk["prescriptions"].append(p)

    if tracking:
        st.markdown("**📅 추적계획**")
        chk["tracking"] = []
        for i, t in enumerate(tracking):
            표시 = f"{t.get('내용', '')} ({t.get('예정일', '')})"
            checked = st.checkbox(f"  {표시}", value=True, key=f"s4_trk_{환자id}_{i}")
            if checked:
                chk["tracking"].append(t)

    if test_orders:
        st.markdown("**🔬 검사처방**")
        chk["test_orders"] = []
        for i, o in enumerate(test_orders):
            표시 = f"{o.get('검사명', '')} (예정: {o.get('처방일', '')})"
            checked = st.checkbox(f"  {표시}", value=True, key=f"s4_ord_{환자id}_{i}")
            if checked:
                chk["test_orders"].append(o)

    if ps:
        chk["prescription_summary_flag"] = st.checkbox(f"📝 처방요약: {ps[:60]}{'...' if len(ps) > 60 else ''}", value=True, key=f"s4_ps_{환자id}")

    for 항목명, 변경 in patient_info.items():
        if 변경 and 변경.get("변경유형"):
            유형표시 = {"add": "추가", "modify": "수정", "remove": "삭제"}.get(변경.get("변경유형", ""), "변경")
            표시 = f"환자정보 {항목명} ({유형표시}): {변경.get('기존값', '')} → {변경.get('새값', '')}"
            if "patient_info" not in chk:
                chk["patient_info"] = {}
            checked = st.checkbox(f"👤 {표시}", value=True, key=f"s4_pi_{환자id}_{항목명}")
            if checked:
                chk["patient_info"][항목명] = 변경

    if not any([vitals, lifestyle, diagnoses, lab_results, imaging, prescriptions, tracking, test_orders, ps]):
        st.info("추출된 데이터가 없습니다.")

    st.markdown("---")
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        if st.button("← 이전 단계", key=f"s4_back_{환자id}"):
            st.session_state[f"chart_step_{환자id}"] = 3
            st.rerun()
    with col2:
        if st.button("🔄 저장 데이터 재추출", key=f"s4_reanalyze_{환자id}"):
            with st.spinner("AI가 재분석 중..."):
                재결과 = 재추출(환자id, 보완본, 방문일)
            if 재결과:
                분석결과["extraction"] = 재결과
                st.session_state[f"chart_분석결과_{환자id}"] = 분석결과
                st.rerun()
            else:
                st.error("재분석 실패. 기존 추출 데이터를 사용합니다.")
    with col3:
        if st.button("이대로 저장 →", type="primary", key=f"s4_save_{환자id}"):
            # approved_data 구성
            approved_data = {}
            if chk.get("vitals"):
                approved_data["vitals"] = vitals
            if chk.get("lifestyle"):
                approved_data["lifestyle"] = lifestyle
            if chk.get("diagnoses"):
                approved_data["diagnoses"] = chk["diagnoses"]
            if chk.get("lab_results"):
                approved_data["lab_results"] = chk["lab_results"]
            if chk.get("imaging"):
                approved_data["imaging"] = chk["imaging"]
            if chk.get("prescriptions"):
                approved_data["prescriptions"] = chk["prescriptions"]
            if chk.get("tracking"):
                approved_data["tracking"] = chk["tracking"]
            if chk.get("test_orders"):
                approved_data["test_orders"] = chk["test_orders"]
            if chk.get("prescription_summary_flag") and ps:
                approved_data["prescription_summary"] = ps
            if chk.get("patient_info"):
                approved_data["patient_info"] = chk["patient_info"]

            with st.spinner("저장 중..."):
                건수 = 분석결과_저장(환자id, 방문id, 보완본, approved_data)
                # 분석완료 플래그 업데이트
                방문기록_일괄수정(방문id, {"분석완료": 1})

            st.session_state[f"chart_저장건수_{환자id}"] = 건수
            st.session_state[f"chart_step_{환자id}"] = 5
            st.rerun()


def _chart_step5(환자id):
    """Step 5: 저장 완료 + 결과 요약"""
    건수      = st.session_state.get(f"chart_저장건수_{환자id}", 0)
    분석결과  = st.session_state.get(f"chart_분석결과_{환자id}", {})
    extraction = 분석결과.get("extraction", {})

    st.success(f"저장 완료! 총 {건수}건")

    요약 = [
        ("방문 기록", 1),
        ("진단",    len([d for d in extraction.get("diagnoses", [])   if d.get("구분") != "기존참조"])),
        ("검사결과", len([l for l in extraction.get("lab_results", []) if l.get("구분") != "기존참조"])),
        ("영상검사", len([i for i in extraction.get("imaging", [])     if i.get("구분") != "기존참조"])),
        ("처방",     len([p for p in extraction.get("prescriptions", []) if p.get("구분") not in ("기존참조",)])),
        ("검사처방", len([o for o in extraction.get("test_orders", []) if o.get("구분") != "기존참조"])),
        ("추적계획", len([t for t in extraction.get("tracking", [])    if t.get("구분") != "기존참조"])),
    ]
    for 항목명, n in 요약:
        if n > 0:
            st.markdown(f"  {항목명}: **{n}건**")

    st.markdown("---")
    if st.button("📝 새 진료기록 작성", key=f"s5_new_{환자id}"):
        for k in [f"chart_step_{환자id}", f"chart_분석결과_{환자id}",
                  f"chart_승인texts_{환자id}", f"chart_보완본_{환자id}",
                  f"chart_free_text_{환자id}", f"chart_방문일_{환자id}",
                  f"chart_방문id_{환자id}", f"chart_저장건수_{환자id}"]:
            st.session_state.pop(k, None)
        st.rerun()


def _tab_edit(환자id: int):
    기록 = 환자전체기록조회(환자id)
    방문목록 = 기록.get("방문", [])

    if not 방문목록:
        st.caption("방문 기록이 없습니다.")
        return

    # 방문 선택
    st.markdown("#### 수정할 방문 선택")

    정렬된_방문 = sorted(방문목록, key=lambda v: str(v.get("방문일", "")), reverse=True)

    for v in 정렬된_방문:
        방문일 = v.get("방문일", "")
        ft = (v.get("free_text") or "")[:60]
        미리보기 = f"{ft}..." if len(v.get("free_text", "") or "") > 60 else ft
        bp = ""
        if v.get("수축기") and v.get("이완기"):
            bp = f" | BP {v['수축기']}/{v['이완기']}"

        if st.button(
            f"📝 {방문일}{bp}\n{미리보기}",
            key=f"edit_visit_{v['방문id']}",
            use_container_width=True,
        ):
            st.session_state[f"editing_visit_{환자id}"] = v["방문id"]
            st.rerun()

    # 선택된 방문 편집
    편집중_방문id = st.session_state.get(f"editing_visit_{환자id}")
    if 편집중_방문id:
        편집_방문 = next((v for v in 방문목록 if v["방문id"] == 편집중_방문id), None)
        if 편집_방문:
            st.markdown("---")
            title_col, back_col = st.columns([4, 1])
            with title_col:
                st.markdown(f"#### {편집_방문.get('방문일', '')} 기록 수정")
            with back_col:
                if st.button("← 목록으로", key=f"edit_back_list_{환자id}", type="secondary"):
                    st.session_state[f"editing_visit_{환자id}"] = None
                    st.session_state.pop(f"edit_preview_{편집중_방문id}", None)
                    st.rerun()

            기존_free_text = 편집_방문.get("free_text", "") or ""

            새_free_text = st.text_area(
                "진료 기록 (free-text)",
                value=기존_free_text,
                height=200,
                key=f"edit_ft_{편집중_방문id}",
            )

            변경됨 = 새_free_text != 기존_free_text

            if 변경됨:
                st.caption("⚠ 변경사항이 있습니다.")

            # AI 재분석 여부 (당일 차트만 표시)
            오늘 = datetime.today().strftime("%y%m%d")
            방문일_원본 = 편집_방문.get("방문일", "")
            방문일_비교 = 방문일_원본.replace("-", "")
            if len(방문일_비교) == 8:
                방문일_비교 = 방문일_비교[2:]
            당일여부 = 방문일_비교 == 오늘

            if 당일여부:
                재분석 = st.radio(
                    "AI 재분석 여부",
                    ["아니오 — 데이터 수정만 (과거 기록 정정용)",
                     "예 — 전체 재분석 (당일 진료 중 수정용)"],
                    key=f"reanalyze_{편집중_방문id}",
                )
            else:
                재분석 = "아니오"
                st.caption("⚠ 과거 기록은 데이터 수정만 가능합니다 (의무기록 위변조 방지).")

            # 변경사항 확인 버튼 (항상 표시, 변경 없으면 비활성화)
            preview_key = f"edit_preview_{편집중_방문id}"

            if st.button(
                "🔍 변경사항 확인",
                type="primary",
                key=f"preview_edit_{편집중_방문id}",
                disabled=not 변경됨,
            ):
                with st.spinner("AI가 변경사항을 분석 중..."):
                    변경사항 = _변경사항_추출(
                        환자id, 편집중_방문id, 기존_free_text, 새_free_text,
                        편집_방문.get("방문일", ""))
                    st.session_state[preview_key] = 변경사항
                st.rerun()

            # 변경사항 미리보기 + 확정 저장
            if st.session_state.get(preview_key):
                변경사항 = st.session_state[preview_key]

                st.markdown("---")
                st.markdown("#### 변경사항 확인")

                변경있음 = False

                for 항목 in 변경사항.get("변경", []):
                    변경있음 = True
                    기존 = 항목.get("기존", {})
                    수정후 = 항목.get("수정후", {})
                    기존값 = 기존.get("결과값", "") or 기존.get("상태", "") or 기존.get("용량", "")
                    수정값 = 수정후.get("결과값", "") or 수정후.get("상태", "") or 수정후.get("용량", "")
                    항목명 = 기존.get("검사항목", "") or 기존.get("진단명", "") or 기존.get("약품명", "")
                    st.markdown(f"✏️ **{항목.get('테이블', '')}** — {항목명}: `{기존값}` → `{수정값}`")

                for 항목 in 변경사항.get("추가", []):
                    변경있음 = True
                    데이터 = 항목.get("데이터", {})
                    대표값 = (데이터.get("검사항목", "") or 데이터.get("진단명", "") or
                              데이터.get("약품명", "") or 데이터.get("내용", ""))
                    st.markdown(f"➕ **{항목.get('테이블', '')}** — {대표값} 추가")

                for 항목 in 변경사항.get("삭제", []):
                    변경있음 = True
                    데이터 = 항목.get("데이터", {})
                    대표값 = (데이터.get("검사항목", "") or 데이터.get("진단명", "") or
                              데이터.get("약품명", "") or 데이터.get("내용", ""))
                    st.markdown(f"🗑️ **{항목.get('테이블', '')}** — {대표값} 삭제")

                if 변경사항.get("활력징후_변경"):
                    변경있음 = True
                    st.markdown(f"✏️ **활력징후** — {변경사항['활력징후_변경']}")

                if 변경사항.get("처방요약_변경"):
                    변경있음 = True
                    st.markdown(f"✏️ **처방요약** — {변경사항['처방요약_변경']}")

                if not 변경있음:
                    st.info("AI가 감지한 데이터 변경사항이 없습니다. free-text만 수정됩니다.")

                st.markdown("---")
                정정사유 = st.text_input(
                    "정정사유 *",
                    placeholder="예: 검사수치 오기재, 처방 추가 등",
                    key=f"edit_reason_{편집중_방문id}",
                )

                col_save, col_cancel = st.columns([1, 1])
                with col_save:
                    if st.button("✅ 확정 저장", type="primary", key=f"confirm_save_{편집중_방문id}",
                                 disabled=not 정정사유.strip()):
                        with st.spinner("저장 중..."):
                            if "예" in 재분석:
                                try:
                                    결과 = 차트_재분석_저장(
                                        환자id, 편집중_방문id, 새_free_text, 편집_방문.get("방문일", ""))
                                    if 결과:
                                        st.success("재분석 + 저장 완료!")
                                    else:
                                        st.warning("재분석 완료 (변경사항 없음)")
                                except Exception as e:
                                    st.error(f"재분석 실패: {e}")
                            else:
                                요약, 건수 = 차트_데이터만_수정(
                                    환자id, 편집중_방문id, 기존_free_text,
                                    새_free_text, 편집_방문.get("방문일", ""),
                                    변경사항=변경사항, 정정사유=정정사유)
                                if 건수 > 0:
                                    st.success(f"저장 완료! {건수}건 변경")
                                else:
                                    st.success("free-text 수정 저장 완료")
                        st.session_state[preview_key] = None
                        st.session_state[f"editing_visit_{환자id}"] = None
                        st.rerun()
                with col_cancel:
                    if st.button("❌ 취소", key=f"cancel_save_{편집중_방문id}"):
                        st.session_state[preview_key] = None
                        st.rerun()

            st.markdown("---")

            # 이 방문 전체 삭제
            with st.expander("⚠️ 이 방문 삭제", expanded=False):
                st.warning("이 방문과 연결된 모든 데이터가 무효화됩니다.")
                삭제사유 = st.text_input("삭제 사유", key=f"del_reason_{편집중_방문id}")
                if st.button("🗑️ 방문 삭제", key=f"del_visit_{편집중_방문id}"):
                    if 삭제사유.strip():
                        방문기록삭제(편집중_방문id, 삭제사유)
                        st.success("삭제 완료")
                        st.session_state[f"editing_visit_{환자id}"] = None
                        st.rerun()
                    else:
                        st.error("삭제 사유를 입력하세요.")

    # 환자 전체 삭제
    st.markdown("---")
    with st.expander("⚠️ 환자 전체 삭제", expanded=False):
        st.error("이 환자의 모든 기록이 영구 삭제됩니다.")
        확인입력 = st.text_input("확인하려면 'yes' 입력", key=f"del_patient_{환자id}")
        if st.button("🗑️ 환자 삭제", key=f"del_patient_btn_{환자id}"):
            if 확인입력.strip() == "yes":
                환자삭제(환자id)
                st.success("환자 삭제 완료")
                st.session_state.selected_patient_id = None
                _navigate_to("홈")
            else:
                st.error("'yes'를 정확히 입력하세요.")


@st.dialog("검색 결과")
def _검색실패_팝업(검색어: str):
    """검색 결과 없음 팝업."""
    st.warning(f"'{검색어}' 에 해당하는 환자를 찾을 수 없습니다.")
    if st.button("확인", use_container_width=True):
        st.rerun()


def _날짜_정규화(날짜str) -> str:
    """YYMMDD → YYYY-MM-DD 변환. 이미 YYYY-MM-DD면 그대로."""
    if not 날짜str:
        return ""
    날짜str = str(날짜str).strip()
    # YYYY-MM-DD (10자리)
    if len(날짜str) == 10 and "-" in 날짜str:
        return 날짜str
    # YYYY-MM (7자리)
    if len(날짜str) == 7 and "-" in 날짜str:
        return 날짜str
    # YYMMDD (6자리)
    if len(날짜str) == 6 and 날짜str.isdigit():
        yy, mm, dd = 날짜str[:2], 날짜str[2:4], 날짜str[4:6]
        yyyy = f"20{yy}"
        if dd == "00":
            return f"{yyyy}-{mm}"
        return f"{yyyy}-{mm}-{dd}"
    # YYMM (4자리)
    if len(날짜str) == 4 and 날짜str.isdigit():
        yy, mm = 날짜str[:2], 날짜str[2:4]
        return f"20{yy}-{mm}"
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
    st.text(free_text)

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


def _copy_button(text, key):
    """클립보드 복사 버튼을 렌더링한다."""
    escaped = (text
               .replace("\\", "\\\\")
               .replace("`", "\\`")
               .replace("$", "\\$")
               .replace("'", "\\'")
               .replace("\n", "\\n")
               .replace("\r", ""))
    components.html(f"""
    <button onclick="
        navigator.clipboard.writeText('{escaped}').then(() => {{
            this.innerText = '✅ 복사됨';
            setTimeout(() => this.innerText = '📋 복사', 1500);
        }})
    " style="
        background: #faf9f6;
        border: 1px solid #e8e4dc;
        border-radius: 6px;
        padding: 4px 12px;
        cursor: pointer;
        font-size: 13px;
        color: #6b6560;
        font-family: 'Inter', 'Noto Sans KR', sans-serif;
    ">📋 복사</button>
    """, height=36)


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
        날짜 = _날짜_정규화(방문일_매핑.get(lr.get("방문id"), lr.get("검사시행일", "")))
        날짜별.setdefault(날짜, _빈항목())["검사결과"].append(lr)

    for img in 기록.get("영상검사", []):
        날짜 = _날짜_정규화(방문일_매핑.get(img.get("방문id"), img.get("검사시행일", "")))
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
            if 항목들["방문"]:
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
                        ft_col, cp_col = st.columns([6, 1])
                        with ft_col:
                            st.markdown("**진료 기록:**")
                        with cp_col:
                            _copy_button(ft, f"ft_{날짜}_{i}")
                        st.text(ft)
                    else:
                        st.markdown("**진료 기록:** 없음")

                    rx_summary = v.get("처방요약", "")
                    if rx_summary and rx_summary.strip():
                        st.caption(f"처방요약: {rx_summary}")
            else:
                st.caption("활력징후: 없음")
                st.markdown("**진료 기록:** 없음")

            # 진단
            st.markdown("**진단:**")
            if 항목들["진단"]:
                for d in 항목들["진단"]:
                    상태표시 = f"({d.get('상태', '')})" if d.get('상태') else ""
                    st.caption(f"  {d.get('진단명', '')} {상태표시}")
            else:
                # 이 날짜에 새 진단 없음 → 전체 활성/의심 진단 표시
                전체진단 = [d for d in 기록.get("진단", [])
                            if d.get("상태") in ("활성", "의심") and d.get("유효여부", 1) == 1]
                if 전체진단:
                    for d in 전체진단:
                        상태표시 = f"({d.get('상태', '')})" if d.get('상태') else ""
                        st.caption(f"  {d.get('진단명', '')} {상태표시}")
                else:
                    st.caption("  없음")

            # 검사결과 (당일/이전 구분)
            st.markdown("**검사결과:**")
            if 항목들["검사결과"]:
                현재날짜 = 날짜
                당일검사 = []
                이전검사 = {}
                for lr in 항목들["검사결과"]:
                    시행일 = _날짜_정규화(lr.get("검사시행일", ""))
                    if 시행일 == 현재날짜:
                        당일검사.append(lr)
                    else:
                        이전검사.setdefault(시행일, []).append(lr)
                if 당일검사:
                    st.markdown("*당일:*")
                    available = [c for c in ["검사항목", "결과값", "단위", "참고범위"] if c in 당일검사[0]]
                    df = pd.DataFrame(당일검사)[available]
                    st.dataframe(df, use_container_width=True, hide_index=True,
                                 height=min(len(df) * 40 + 38, 200))
                for 시행일 in sorted(이전검사.keys(), reverse=True):
                    검사들 = 이전검사[시행일]
                    st.markdown(f"*이전 (시행일: {시행일}):*")
                    available = [c for c in ["검사항목", "결과값", "단위", "참고범위"] if c in 검사들[0]]
                    df = pd.DataFrame(검사들)[available]
                    st.dataframe(df, use_container_width=True, hide_index=True,
                                 height=min(len(df) * 40 + 38, 200))
            else:
                st.caption("  없음")

            # 영상검사 (당일/이전 구분)
            st.markdown("**영상검사:**")
            if 항목들["영상검사"]:
                현재날짜 = 날짜
                당일영상 = []
                이전영상 = {}
                for img in 항목들["영상검사"]:
                    시행일 = _날짜_정규화(img.get("검사시행일", ""))
                    if 시행일 == 현재날짜:
                        당일영상.append(img)
                    else:
                        이전영상.setdefault(시행일, []).append(img)
                if 당일영상:
                    st.markdown("*당일:*")
                    for img in 당일영상:
                        st.caption(f"  {img.get('검사종류', '')} — {img.get('결과요약', '')}")
                for 시행일 in sorted(이전영상.keys(), reverse=True):
                    st.markdown(f"*이전 (시행일: {시행일}):*")
                    for img in 이전영상[시행일]:
                        st.caption(f"  {img.get('검사종류', '')} — {img.get('결과요약', '')}")
            else:
                st.caption("  없음")

            # 처방
            st.markdown("**처방:**")
            if 항목들["처방"]:
                available = [c for c in ["약품명", "성분명", "용량", "용법", "일수"] if c in 항목들["처방"][0]]
                df = pd.DataFrame(항목들["처방"])[available]
                st.dataframe(df, use_container_width=True, hide_index=True,
                             height=min(len(df) * 40 + 38, 200))
            else:
                st.caption("  없음")

            # 검사처방
            st.markdown("**검사처방:**")
            if 항목들["검사처방"]:
                for o in 항목들["검사처방"]:
                    시행 = "✅" if o.get("시행여부") else "⬜"
                    처방일 = _날짜_정규화(o.get("처방일", ""))
                    st.caption(f"  {시행} {o.get('검사명', '')} (처방일: {처방일})")
            else:
                st.caption("  없음")

            # 추적계획 (기존 추적계획 + 미래 검사처방 혼합)
            st.markdown("**추적계획:**")
            if 항목들["추적계획"]:
                for t in 항목들["추적계획"]:
                    if t.get("_미래검사"):
                        시행 = "✅" if t.get("시행여부") else "⬜"
                        예정일 = _날짜_정규화(t.get("처방일", ""))
                        st.caption(f"  {시행} 🔬 {t.get('검사명', '')} (예정: {예정일})")
                    else:
                        완료 = "✅" if t.get("완료여부") else "⬜"
                        예정일 = _날짜_정규화(t.get("예정일", ""))
                        st.caption(f"  {완료} {t.get('내용', '')} (예정: {예정일})")
            else:
                st.caption("  없음")


# ============================================================
# 연구 화면
# ============================================================
def _render_research_page():
    hdr_left, hdr_right = st.columns([8, 1])
    with hdr_left:
        st.markdown("## 📊 연구")
    with hdr_right:
        if st.session_state.page_history:
            if st.button("← 뒤로", key="btn_back_research", type="secondary"):
                _go_back()

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
    hdr_left, hdr_right = st.columns([8, 1])
    with hdr_left:
        st.markdown("## ⚙️ 설정")
    with hdr_right:
        if st.session_state.page_history:
            if st.button("← 뒤로", key="btn_back_settings", type="secondary"):
                _go_back()

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
    # DB 마이그레이션 (칼럼 추가 등) 자동 실행
    DB연결().close()
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
