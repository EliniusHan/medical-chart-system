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
    sidebar_width = "260px" if st.session_state.get("sidebar_open", True) else "76px"
    st.markdown(f"""
    <style>
    /* 전체 레이아웃 */
    .main .block-container {{
        padding-top: 1.5rem;
        padding-left: 2rem;
        padding-right: 2rem;
        max-width: 1600px;
    }}

    /* 사이드바 너비 제어 */
    section[data-testid="stSidebar"] > div:first-child {{
        width: {sidebar_width} !important;
        background-color: #1e2432;
        border-right: 1px solid #2d3550;
    }}
    /* 사이드바 텍스트 색상 */
    section[data-testid="stSidebar"] .stMarkdown p,
    section[data-testid="stSidebar"] .stMarkdown span,
    section[data-testid="stSidebar"] label {{
        color: #c5cce8 !important;
    }}
    section[data-testid="stSidebar"] hr {{
        border-color: #2d3550 !important;
        margin: 8px 0;
    }}
    /* 사이드바 버튼 — secondary (기본) */
    section[data-testid="stSidebar"] button[kind="secondary"] {{
        background: transparent !important;
        border: 1px solid transparent !important;
        color: #c5cce8 !important;
        transition: background 0.15s;
    }}
    section[data-testid="stSidebar"] button[kind="secondary"]:hover {{
        background: #2d3550 !important;
        border-color: #3d4a70 !important;
    }}
    /* 사이드바 버튼 — primary (활성 메뉴) */
    section[data-testid="stSidebar"] button[kind="primary"] {{
        background: #4f6ef7 !important;
        border-color: #4f6ef7 !important;
        color: white !important;
    }}

    /* 요약 카드 */
    .stat-card {{
        background: white;
        border-radius: 12px;
        padding: 20px 24px;
        box-shadow: 0 2px 8px rgba(0,0,0,.07);
        border-left: 4px solid #4f6ef7;
    }}
    .stat-card.warn {{ border-left-color: #f59e0b; }}
    .stat-card.danger {{ border-left-color: #ef4444; }}
    .stat-card .label {{ font-size: 13px; color: #6b7280; margin-bottom: 4px; }}
    .stat-card .value {{ font-size: 30px; font-weight: 700; color: #1f2937; }}
    .stat-card .sub {{ font-size: 12px; color: #9ca3af; margin-top: 4px; }}

    /* 환자 헤더 배지 */
    .patient-header {{
        display: flex;
        align-items: center;
        gap: 16px;
        padding: 16px;
        background: #eff2ff;
        border-radius: 12px;
        margin-bottom: 16px;
    }}
    .initial-badge {{
        width: 52px; height: 52px;
        border-radius: 50%;
        background: #4f6ef7;
        color: white;
        display: flex; align-items: center; justify-content: center;
        font-weight: 700; font-size: 22px;
        flex-shrink: 0;
    }}
    .initial-badge.sm {{
        width: 36px; height: 36px;
        font-size: 15px;
    }}

    /* 데일리 체크 항목 */
    .daily-item {{
        padding: 10px 14px;
        border-radius: 8px;
        margin-bottom: 6px;
        font-size: 14px;
        line-height: 1.5;
    }}
    .daily-item.danger {{
        background: #fef2f2;
        border-left: 3px solid #ef4444;
        color: #991b1b;
    }}
    .daily-item.warn {{
        background: #fffbeb;
        border-left: 3px solid #f59e0b;
        color: #92400e;
    }}
    .daily-item.info {{
        background: #eff6ff;
        border-left: 3px solid #3b82f6;
        color: #1e40af;
    }}

    /* 환자 목록 패널 스크롤 */
    div[data-testid="patient-list-scroll"] {{
        max-height: calc(100vh - 280px);
        overflow-y: auto;
        padding-right: 4px;
    }}

    /* 반응형: 환자 목록 왼쪽 패널 구분선 */
    .patient-panel-divider {{
        border-right: 1px solid #e5e7eb;
        padding-right: 16px;
        min-height: calc(100vh - 120px);
    }}
    </style>
    """, unsafe_allow_html=True)


# ============================================================
# 세션 상태 초기화
# ============================================================
def _init_state():
    defaults = {
        "page": "홈",
        "mode": "연구용",
        "lang": "한국어",
        "sidebar_open": True,
        "selected_patient_id": None,
        "patient_view": None,       # None | "new" | "detail"
        "daily_filter": "전체",
        "daily_show_all": False,
        "ai_pattern_result": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ============================================================
# DB 헬퍼
# ============================================================
def _환자목록_진단포함():
    """환자 목록에 활성/의심 진단 목록을 포함하여 반환한다."""
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
    """메시지에서 경과 일수를 추출한다 (정렬용). 더 클수록 오래됨."""
    m = re.search(r"(\d+)(일|개월) 경과", msg)
    if not m:
        return 0
    n = int(m.group(1))
    return n * 30 if m.group(2) == "개월" else n


# ============================================================
# 사이드바
# ============================================================
def _render_sidebar():
    open_ = st.session_state.sidebar_open

    with st.sidebar:
        # ── 토글
        if st.button("◀" if open_ else "▶", key="sb_toggle", help="사이드바 접기/펴기"):
            st.session_state.sidebar_open = not open_
            st.rerun()

        st.markdown("---")

        # ── 메뉴
        if open_:
            st.markdown("**메뉴**")

        for icon, label, page_key in [
            ("🏠", "홈",  "홈"),
            ("👤", "환자", "환자"),
            ("📊", "연구", "연구"),
        ]:
            btn_label = f"{icon}  {label}" if open_ else icon
            is_active = st.session_state.page == page_key
            if st.button(
                btn_label,
                key=f"nav_{page_key}",
                use_container_width=open_,
                type="primary" if is_active else "secondary",
            ):
                st.session_state.page = page_key
                st.rerun()

        st.markdown("---")

        # ── 모드 선택
        if open_:
            st.markdown("**모드**")
            새_모드 = st.radio(
                "mode_radio",
                ["연구용", "진료보조용"],
                index=0 if st.session_state.mode == "연구용" else 1,
                label_visibility="collapsed",
                help="연구용: 저장 포함 5단계 | 진료보조용: 제안까지 3단계",
            )
            if 새_모드 != st.session_state.mode:
                st.session_state.mode = 새_모드
        else:
            # 접힌 상태: 현재 모드 아이콘만 표시
            mode_icon = "🔬" if st.session_state.mode == "연구용" else "🩺"
            st.button(mode_icon, key="mode_icon", disabled=True)

        st.markdown("---")

        # ── 관리
        if open_:
            st.markdown("**관리**")

        backup_label = "💾  백업" if open_ else "💾"
        if st.button(backup_label, key="btn_backup", use_container_width=open_):
            try:
                경로 = DB백업()
                if open_:
                    st.success(f"백업 완료\n`{os.path.basename(경로)}`")
                else:
                    st.toast("백업 완료")
            except Exception as e:
                st.error(str(e))

        manual_label = "✏️  수동입력" if open_ else "✏️"
        if st.button(manual_label, key="btn_manual", use_container_width=open_):
            st.session_state.page = "환자"
            st.session_state.patient_view = "new"
            st.session_state.selected_patient_id = None
            st.rerun()

        # ── 하단 아이콘 (설정 / 언어 / 로그아웃)
        st.markdown("---")
        lang_code_map = {"한국어": "KO", "English": "EN", "Deutsch": "DE", "日本語": "JA"}
        현재_코드 = lang_code_map.get(st.session_state.lang, "KO")

        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("⚙️", key="btn_settings", help="설정"):
                st.toast("설정 (추후 구현)")
        with c2:
            if st.button(현재_코드, key="btn_lang", help="언어 변경"):
                langs = list(lang_code_map.keys())
                idx = langs.index(st.session_state.lang)
                st.session_state.lang = langs[(idx + 1) % len(langs)]
                st.rerun()
        with c3:
            if st.button("→", key="btn_logout", help="로그아웃"):
                st.toast("로그아웃 (추후 구현)")


# ============================================================
# 홈 화면
# ============================================================
def _render_home():
    st.markdown("## 🏥 의료 차트 시스템")

    # ── 요약 카드 3개
    환자수 = len(환자목록가져오기())
    미분석수 = len(미분석차트조회())
    지연수 = _추적지연_수()

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

    # ── 탭
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

    # 필터 버튼 행
    counts = {
        "전체":      len(msgs),
        "추적 지연": sum(1 for m in msgs if "추적 지연"  in m),
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

    # 필터 적용
    필터 = st.session_state.daily_filter
    if 필터 == "추적 지연":
        filtered = [m for m in msgs if "추적 지연"  in m]
    elif 필터 == "미시행 검사":
        filtered = [m for m in msgs if "미시행 검사" in m]
    elif 필터 == "이번 주 예정":
        filtered = [m for m in msgs if "이번 주 예정" in m]
    else:
        filtered = msgs

    # 경과 기간 순 정렬 (추적 지연 항목)
    지연 = sorted(
        [m for m in filtered if "추적 지연" in m],
        key=_elapsed_days,
        reverse=True,
    )
    나머지 = [m for m in filtered if "추적 지연" not in m]
    sorted_msgs = 지연 + 나머지

    # 페이징
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
        col_a, col_b = st.columns([1, 4])
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
# 환자 화면
# ============================================================
def _render_patient_page():
    col_left, col_right = st.columns([3, 7], gap="medium")

    with col_left:
        st.markdown('<div class="patient-panel-divider">', unsafe_allow_html=True)
        _render_patient_list_panel()
        st.markdown("</div>", unsafe_allow_html=True)

    with col_right:
        view = st.session_state.patient_view
        if view == "new":
            _render_new_patient_form()
        elif view == "detail" and st.session_state.selected_patient_id:
            _render_patient_detail(st.session_state.selected_patient_id)
        else:
            st.markdown("<br><br>", unsafe_allow_html=True)
            st.info("👈 왼쪽 목록에서 환자를 선택하거나 신환을 등록하세요.")


def _render_patient_list_panel():
    st.markdown("### 환자 목록")

    검색어 = st.text_input(
        "search",
        placeholder="🔍  이름 또는 병록번호 검색...",
        label_visibility="collapsed",
        key="patient_search",
    )

    if st.button("➕  신환 등록", use_container_width=True, type="primary", key="btn_new_patient"):
        st.session_state.patient_view = "new"
        st.session_state.selected_patient_id = None
        st.rerun()

    st.markdown("---")

    # 환자 목록 로드
    if 검색어.strip():
        raw = 환자검색(검색어.strip())
        진단맵 = _주진단_조회([p["환자id"] for p in raw])
        for p in raw:
            p["주진단목록"] = 진단맵.get(p["환자id"], "")
        환자목록 = raw
    else:
        환자목록 = _환자목록_진단포함()

    if not 환자목록:
        msg = "검색 결과가 없습니다." if 검색어.strip() else "등록된 환자가 없습니다."
        st.caption(msg)
        return

    st.caption(f"{len(환자목록)}명")

    for 환자 in 환자목록:
        is_selected = 환자["환자id"] == st.session_state.selected_patient_id
        이름 = 환자.get("이름", "")
        병록번호 = 환자.get("병록번호", "")
        나이 = 나이계산(환자.get("생년월일"))
        성별 = 환자.get("성별", "")
        주진단 = (환자.get("주진단목록") or "진단 없음")
        # 길면 축약
        if len(주진단) > 22:
            주진단 = 주진단[:22] + "…"
        나이표시 = f"{나이}세" if 나이 is not None else "?"

        label = f"{이름}  {병록번호}\n{나이표시} {성별}  {주진단}"

        if st.button(
            label,
            key=f"pat_{환자['환자id']}",
            use_container_width=True,
            type="primary" if is_selected else "secondary",
        ):
            st.session_state.selected_patient_id = 환자["환자id"]
            st.session_state.patient_view = "detail"
            st.rerun()


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
        st.session_state.patient_view = "detail"
        st.rerun()


def _render_patient_detail(환자id: int):
    기록 = 환자전체기록조회(환자id)
    if not 기록:
        st.error("환자 정보를 찾을 수 없습니다.")
        return

    환자 = 기록["환자"]
    이름    = 환자.get("이름", "")
    나이    = 나이계산(환자.get("생년월일"))
    성별    = 환자.get("성별", "")
    병록번호 = 환자.get("병록번호", "")
    이니셜  = 이름[0] if 이름 else "?"
    활성진단 = [d["진단명"] for d in 기록.get("진단", []) if d.get("상태") in ("활성", "의심")]
    주진단표시 = ", ".join(활성진단[:3]) + ("…" if len(활성진단) > 3 else "") if 활성진단 else "진단 없음"
    나이표시 = f"{나이}세" if 나이 is not None else "?"

    # ── 환자 헤더
    st.markdown(f"""
    <div class="patient-header">
        <div class="initial-badge">{이니셜}</div>
        <div>
            <div style="font-size:18px;font-weight:700;">
                {이름}
                <span style="font-size:14px;font-weight:400;color:#6b7280;">
                    ({나이표시}&nbsp;{성별})
                </span>
            </div>
            <div style="font-size:13px;color:#6b7280;margin-top:2px;">{병록번호}</div>
            <div style="font-size:13px;color:#4f6ef7;margin-top:4px;">{주진단표시}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── 5개 탭
    tabs = st.tabs(["📋 브리핑", "📝 진료기록", "✏️ 수정", "🗑️ 삭제", "📂 전체이력"])

    with tabs[0]:
        _tab_briefing(환자id)

    with tabs[1]:
        _tab_chart_entry(환자id)

    with tabs[2]:
        _tab_edit(환자id)

    with tabs[3]:
        _tab_delete(환자id)

    with tabs[4]:
        _tab_history(기록)


def _tab_briefing(환자id: int):
    st.info("🔧 추후 구현 — AI 브리핑 생성\n\n`briefing_generator.브리핑생성(환자id)` 연동 예정")


def _tab_chart_entry(환자id: int):
    mode = st.session_state.mode
    if mode == "진료보조용":
        st.caption("진료보조용 모드 — Step 1~3 (제안 확인까지, 저장 없음)")
    else:
        st.caption("연구용 모드 — Step 1~5 전체 (데이터 추출 및 저장 포함)")

    # 단계 진행 표시
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


def _tab_history(기록: dict):
    """환자 전체이력을 테이블별 접기/펼치기로 표시한다."""
    환자 = 기록["환자"]

    # 환자 기본정보
    with st.expander("🧑 환자 기본정보", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("이름",     환자.get("이름", ""))
            st.metric("성별",     환자.get("성별", ""))
        with col2:
            st.metric("생년월일", 환자.get("생년월일", ""))
            st.metric("병록번호", 환자.get("병록번호", ""))
        with col3:
            가족력 = 환자.get("가족력") or "(없음)"
            약부작용 = 환자.get("약부작용이력") or "(없음)"
            st.text_area("가족력", 가족력, height=60, disabled=True, key=f"fh_{환자['환자id']}")
            st.text_area("약부작용이력", 약부작용, height=60, disabled=True, key=f"ae_{환자['환자id']}")

    # 테이블별 섹션 정의: (제목, 키, 표시할 컬럼 순서)
    sections = [
        ("🏥 방문 기록",  "방문",     ["방문id","방문일","수축기","이완기","심박수","키","몸무게","BMI","흡연","음주","운동","처방요약"]),
        ("🔬 진단",       "진단",     ["진단id","진단명","상태","비고","표준코드","방문일"]),
        ("🧪 검사결과",   "검사결과", ["검사id","검사시행일","검사항목","결과값","단위","참고범위"]),
        ("📷 영상검사",   "영상검사", ["영상id","검사시행일","검사종류","결과요약","주요수치"]),
        ("📅 추적계획",   "추적계획", ["추적id","예정일","내용","완료여부","방문일"]),
        ("💊 처방",       "처방",     ["처방id","약품명","성분명","용량","용법","일수"]),
        ("🔬 검사처방",   "검사처방", ["처방검사id","검사명","처방일","시행여부"]),
    ]

    for title, key, cols in sections:
        data = 기록.get(key, [])
        is_first = key in ("방문", "진단")
        with st.expander(f"{title} ({len(data)}건)", expanded=is_first):
            if data:
                available = [c for c in cols if c in data[0]]
                df = pd.DataFrame(data)[available]
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.caption("기록 없음")


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
# 메인 진입점
# ============================================================
def main():
    _init_state()
    _inject_css()
    _render_sidebar()

    page = st.session_state.page

    if page == "홈":
        _render_home()
    elif page == "환자":
        _render_patient_page()
    elif page == "연구":
        _render_research_page()
    else:
        _render_home()


if __name__ == "__main__":
    main()
