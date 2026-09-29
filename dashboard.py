"""
dashboard.py  —  소비패턴 데이터 탐정 대시보드 🕵️

main.py의 분석 함수(STEP 1~4)를 그대로 불러와 웹 대시보드로 보여준다.
main.py와 팀원 파일은 수정하지 않고 import만 한다.

실행: streamlit run dashboard.py
"""
import contextlib
import io
import json

import altair as alt
import pandas as pd
import streamlit as st

from main import (
    BRIEF_JSON,
    HIGH_AMOUNT_THRESHOLD,
    SMALL_AMOUNT_THRESHOLD,
    check_n8n_handoff,
    cross_check,
    inspect_data,
    load_frames,
    load_n8n_workflow,
    n8n_flow,
    n8n_notes,
    run_sql_files,
    tag_transactions,
)

WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]  # pandas dayofweek 순서
TIME_BANDS = ["새벽", "오전", "오후", "저녁"]
AMOUNT_LEVELS = ["소액", "일반", "고액"]
FLAG_LABELS = {
    "is_dup_id": "R2 ID 중복",
    "is_unknown_category": "R3 카테고리 결측·미등록",
    "is_orphan": "R4 고객·가맹점 조인 실패",
    "is_outlier": "R5 이상값(카테고리별 IQR)",
    "is_invalid_amount": "R6 금액 0 이하",
}
ACCENT = "#2f6fdf"

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600;700&display=swap');
:root {
  --ink: #111827; --muted: #6b7280; --line: #e5e7eb; --card: #ffffff;
  --accent: #2f6fdf; --accent-soft: #e8eefb;
  --warn-ink: #9a5b00; --warn-bg: #fff4e0; --warn-line: #f3c98b;
  --mono: 'IBM Plex Mono', ui-monospace, Consolas, monospace;
}
.stApp { background: #f3f4f8; }
.block-container { max-width: 1100px; padding-top: 2.5rem; }
.eyebrow { font-family: var(--mono); font-size: .85rem; letter-spacing: .12em;
  color: var(--muted); text-transform: uppercase; margin-bottom: .25rem; }
.title { font-size: 2.1rem; font-weight: 800; color: var(--ink); margin: 0 0 .4rem; }
.lede { color: #374151; font-size: 1rem; line-height: 1.6; max-width: 46rem; margin-bottom: .9rem; }
.badge { display: inline-block; padding: .35rem .7rem; border-radius: 6px; font-size: .85rem;
  font-weight: 600; color: var(--warn-ink); background: var(--warn-bg); border: 1px solid var(--warn-line);
  margin-bottom: 1.2rem; }
div[data-testid="stVerticalBlockBorderWrapper"] { background: var(--card); border-radius: 12px; }
.ctl-label { font-weight: 700; color: var(--ink); font-size: .95rem; }
.ctl-value { font-family: var(--mono); font-weight: 700; font-size: 1.05rem; color: var(--ink); }
.ctl-note { color: var(--muted); font-size: .85rem; margin-left: .4rem; }
.kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 1rem; margin: 1rem 0 1.2rem; }
.kpi { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 1.2rem 1.4rem; }
.kpi-label { color: var(--muted); font-size: .92rem; margin-bottom: .5rem; }
.kpi-value { font-family: var(--mono); font-weight: 700; font-size: 2rem; color: var(--ink); line-height: 1.1; }
.kpi-value .unit { font-family: inherit; font-size: 1.5rem; font-weight: 600; }
.kpi-sub { color: #4b5563; font-size: .88rem; margin-top: .5rem; }
.verdict { background: var(--accent-soft); border-radius: 12px; padding: 1.3rem 1.5rem; margin-bottom: 1.5rem; }
.verdict h3 { font-size: 1.05rem; font-weight: 800; color: #1e3a6e; margin: 0 0 .8rem; }
.verdict ol { margin: 0; padding-left: 1.2rem; color: var(--ink); line-height: 1.8; }
.verdict .tag { font-family: var(--mono); font-weight: 700; color: var(--accent); margin-right: .3rem; }
.verdict .check { margin-top: .8rem; font-size: .9rem; color: #1e3a6e; }
.stTabs [data-baseweb="tab-list"] { gap: .25rem; }
</style>
"""


def won(x: float) -> str:
    return f"{int(round(x)):,}원"


def kpi(label: str, number: str, unit: str, sub: str) -> str:
    return (
        f'<div class="kpi"><div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{number}<span class="unit">{unit}</span></div>'
        f'<div class="kpi-sub">{sub}</div></div>'
    )


# ── 데이터 준비 (main.py 함수 재사용) ─────────────────────
@st.cache_data
def analyze():
    """main.py STEP 1~4를 실행하고, 콘솔 출력은 로그로 모아 둔다."""
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        frames = load_frames()
        tx = inspect_data(frames)
        tx = tag_transactions(tx)
        sql = run_sql_files()
        all_ok = cross_check(tx, sql)

    categories = frames["categories"][["category", "category_name"]]
    tx = tx.merge(categories, on="category", how="left")
    tx["category_name"] = tx["category_name"].fillna("UNKNOWN")
    dates = pd.to_datetime(tx["date"])
    tx["month"] = dates.dt.month
    tx["weekday"] = dates.dt.dayofweek.map(lambda i: WEEKDAY_KO[i])
    tx["hour"] = tx["time"].str[:2].astype(int)
    return tx, sql, all_ok, log.getvalue()


st.set_page_config(page_title="소비패턴 데이터 탐정", page_icon="🕵️", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)
tx_all, sql, all_ok, log_text = analyze()

# ── 헤더 ──────────────────────────────────────────────────
start = pd.to_datetime(tx_all["date"].min())
end = pd.to_datetime(tx_all["date"].max())
st.markdown(
    f'<div class="eyebrow">사건 파일 · {start:%Y.%m}–{end:%Y.%m} · main.py step 1–6</div>'
    '<div class="title">🕵️ 소비패턴 데이터 탐정</div>'
    '<div class="lede">main.py가 터미널에 찍던 결과를 한 화면에 모은 대시보드입니다. '
    "위쪽 조건을 바꾸면 모든 숫자와 차트가 다시 계산됩니다.</div>"
    f'<div class="badge">가상 거래 데이터 {len(tx_all):,}건 · 분석 방법 검증용</div>',
    unsafe_allow_html=True,
)

# ── 조건 카드 ─────────────────────────────────────────────
months = sorted(tx_all["month"].unique())
cat_names = sorted(tx_all["category_name"].unique())
with st.container(border=True):
    c_label, c_seg, c_more = st.columns([1.1, 3, 1.4], vertical_alignment="center")
    c_label.markdown('<span class="ctl-label">R5 이상값</span>', unsafe_allow_html=True)
    outlier_mode = c_seg.segmented_control(
        "R5 이상값", ["포함", "제외"], default="포함", label_visibility="collapsed"
    ) or "포함"
    with c_more.popover("세부 필터", width="stretch"):
        picked_months = st.multiselect(
            "월", months, default=months, format_func=lambda m: f"{m}월"
        )
        picked_cats = st.multiselect("카테고리", cat_names, default=cat_names)

    c_label, c_slider, c_value = st.columns([1.1, 3, 3.4], vertical_alignment="center")
    c_label.markdown('<span class="ctl-label">고액 기준</span>', unsafe_allow_html=True)
    threshold = c_slider.slider(
        "고액 기준", 50_000, 500_000, HIGH_AMOUNT_THRESHOLD, step=10_000,
        label_visibility="collapsed", format="%d원",
    )
    note = (
        "팀 합의값 (sql/q2와 같음)"
        if threshold == HIGH_AMOUNT_THRESHOLD
        else f"팀 합의값 {HIGH_AMOUNT_THRESHOLD:,}원과 다름 · SQL 대조 불가"
    )
    c_value.markdown(
        f'<span class="ctl-value">{threshold:,}원</span><span class="ctl-note">{note}</span>',
        unsafe_allow_html=True,
    )

scope = tx_all[tx_all["month"].isin(picked_months) & tx_all["category_name"].isin(picked_cats)]
tx = scope[~scope["is_outlier"]] if outlier_mode == "제외" else scope

if tx.empty:
    st.warning("선택한 조건에 해당하는 거래가 없습니다. 세부 필터를 넓혀 주세요.")
    st.stop()

# ── 핵심 지표 카드 ────────────────────────────────────────
total = tx["amount"].sum()
high = tx[tx["amount"] >= threshold]
high_share = high["amount"].sum() / total * 100
outliers = scope[scope["is_outlier"]]
outlier_share = outliers["amount"].sum() / scope["amount"].sum() * 100

st.markdown(
    '<div class="kpi-grid">'
    + kpi("총지출", f"{total:,}", "원", f"{len(tx):,}건의 합")
    + kpi("거래 건수", f"{len(tx):,}", "건", f"건당 평균 {won(total / len(tx))}")
    + kpi("고액 거래", f"{len(high):,}", "건", f"총지출의 {high_share:.1f}% · {threshold:,}원 이상")
    + kpi(
        "이상값 플래그", f"{len(outliers):,}", "건",
        f"원본 지출의 {outlier_share:.1f}%를 차지" + (" · 현재 제외됨" if outlier_mode == "제외" else ""),
    )
    + "</div>",
    unsafe_allow_html=True,
)

# ── 탐정의 결론 ───────────────────────────────────────────
by_cat = (
    tx.groupby("category_name")["amount"]
    .agg(금액="sum", 건수="count")
    .sort_values("금액", ascending=False)
)
by_cat["비중(%)"] = (by_cat["금액"] / total * 100).round(1)
by_month = tx.groupby("month")["amount"].sum()
peak_weekday = tx.groupby("weekday")["amount"].sum().idxmax()
peak_hour = tx.groupby("hour")["amount"].sum().idxmax()

q2_line = (
    f"{won(threshold)} 이상 고액 거래 {len(high)}건({len(high) / len(tx) * 100:.1f}%)이 "
    f"총지출의 {high_share:.1f}% 차지, 가장 잦은 카테고리는 '{high['category_name'].value_counts().idxmax()}'"
    if not high.empty
    else f"{won(threshold)} 이상 고액 거래가 없음"
)
month_line = (
    f"최고 지출 {by_month.idxmax()}월({won(by_month.max())}), 최저 {by_month.idxmin()}월({won(by_month.min())}) · "
    if len(by_month) > 1
    else f"{by_month.idxmax()}월 지출 {won(by_month.max())} · "
)
check_line = (
    "✅ SQL·Pandas 교차검증 모두 일치 (전체 데이터 기준)"
    if all_ok
    else "❌ SQL·Pandas 교차검증 불일치 — 검증 탭 확인 필요"
)
st.markdown(
    '<div class="verdict"><h3>탐정의 결론</h3><ol>'
    f'<li><span class="tag">Q1</span>돈이 가장 많이 새는 곳은 \'{by_cat.index[0]}\' — '
    f"{won(by_cat['금액'].iloc[0])} (전체의 {by_cat['비중(%)'].iloc[0]}%)</li>"
    f'<li><span class="tag">Q2</span>{q2_line}</li>'
    f'<li><span class="tag">Q3</span>{month_line}{peak_weekday}요일 · {peak_hour}시에 지출이 가장 몰림</li>'
    f'</ol><div class="check">{check_line}</div></div>',
    unsafe_allow_html=True,
)


def bar(data, x, y, title, height=260, **kw):
    return (
        alt.Chart(data)
        .mark_bar(color=ACCENT, cornerRadiusEnd=3)
        .encode(x=x, y=y, **kw)
        .properties(title=title, height=height)
    )


tab_q1, tab_q2, tab_q3, tab_quality, tab_check, tab_mail = st.tabs(
    ["Q1 카테고리", "Q2 큰 금액", "Q3 기간 패턴", "데이터 품질", "검증 · SQL 결과", "n8n 메일 브리핑"]
)

# ── Q1 ────────────────────────────────────────────────────
with tab_q1:
    cat_df = by_cat.reset_index()
    left, right = st.columns([3, 2])
    with left:
        st.altair_chart(
            bar(
                cat_df,
                x=alt.X("금액:Q", title="지출 금액(원)", axis=alt.Axis(format=",")),
                y=alt.Y("category_name:N", sort="-x", title=None),
                title="카테고리별 지출",
                height=320,
                tooltip=["category_name", alt.Tooltip("금액:Q", format=","), "건수", "비중(%)"],
            ),
            width="stretch",
        )
    with right:
        st.dataframe(
            cat_df.rename(columns={"category_name": "카테고리"}),
            hide_index=True,
            column_config={"금액": st.column_config.NumberColumn(format="%d원")},
            width="stretch",
        )

    st.caption(
        f"금액 등급 (main.py classify_amount): 소액 < {won(SMALL_AMOUNT_THRESHOLD)} ≤ 일반 < "
        f"{won(HIGH_AMOUNT_THRESHOLD)} ≤ 고액"
    )
    level = (
        tx.groupby("amount_level")["amount"]
        .agg(건수="count", 금액="sum")
        .reindex(AMOUNT_LEVELS, fill_value=0)
        .reset_index()
    )
    c1, c2 = st.columns(2)
    for col, measure in ((c1, "건수"), (c2, "금액")):
        with col:
            st.altair_chart(
                bar(
                    level,
                    x=alt.X("amount_level:N", sort=AMOUNT_LEVELS, title=None),
                    y=alt.Y(f"{measure}:Q", axis=alt.Axis(format=",")),
                    title=f"등급별 {measure}",
                    height=220,
                    tooltip=["amount_level", alt.Tooltip(f"{measure}:Q", format=",")],
                ),
                width="stretch",
            )

# ── Q2 ────────────────────────────────────────────────────
with tab_q2:
    if high.empty:
        st.info("선택한 조건에 고액 거래가 없습니다.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            st.altair_chart(
                bar(
                    high,
                    x=alt.X("count():Q", title="건수"),
                    y=alt.Y("category_name:N", sort="-x", title=None),
                    title="카테고리별 고액 거래 건수",
                    height=280,
                    tooltip=["category_name", "count()"],
                ),
                width="stretch",
            )
        with c2:
            st.altair_chart(
                bar(
                    high,
                    x=alt.X("month:O", title="월"),
                    y=alt.Y("count():Q", title="건수"),
                    title="월별 고액 거래 건수",
                    height=280,
                    tooltip=["month", "count()"],
                ),
                width="stretch",
            )
        st.markdown(f"**고액 거래 목록** ({len(high)}건, 금액 큰 순)")
        st.dataframe(
            high.sort_values("amount", ascending=False)[
                ["transaction_id", "date", "time", "category_name", "amount", "channel", "is_outlier"]
            ],
            hide_index=True,
            column_config={"amount": st.column_config.NumberColumn("금액", format="%d원")},
            width="stretch",
        )

# ── Q3 ────────────────────────────────────────────────────
with tab_q3:
    st.altair_chart(
        alt.Chart(by_month.reset_index())
        .mark_line(point=True, color=ACCENT)
        .encode(
            x=alt.X("month:O", title="월"),
            y=alt.Y("amount:Q", title="지출 금액(원)", axis=alt.Axis(format=",")),
            tooltip=["month", alt.Tooltip("amount:Q", format=",")],
        )
        .properties(title="월별 지출 추이", height=280),
        width="stretch",
    )

    c1, c2 = st.columns(2)
    with c1:
        st.altair_chart(
            bar(
                tx,
                x=alt.X("weekday:N", sort=WEEKDAY_KO, title=None),
                y=alt.Y("sum(amount):Q", title="지출 금액(원)", axis=alt.Axis(format=",")),
                title="요일별 지출",
                tooltip=["weekday", alt.Tooltip("sum(amount):Q", format=",")],
            ),
            width="stretch",
        )
    with c2:
        st.altair_chart(
            bar(
                tx,
                x=alt.X("time_band:N", sort=TIME_BANDS, title=None),
                y=alt.Y("sum(amount):Q", title="지출 금액(원)", axis=alt.Axis(format=",")),
                title="시간대별 지출 (classify_time)",
                tooltip=["time_band", alt.Tooltip("sum(amount):Q", format=",")],
            ),
            width="stretch",
        )

    st.altair_chart(
        alt.Chart(tx)
        .mark_rect()
        .encode(
            x=alt.X("hour:O", title="시"),
            y=alt.Y("weekday:N", sort=WEEKDAY_KO, title=None),
            color=alt.Color("sum(amount):Q", title="지출", scale=alt.Scale(scheme="blues")),
            tooltip=["weekday", "hour", alt.Tooltip("sum(amount):Q", format=","), "count()"],
        )
        .properties(title="요일 × 시간 지출 히트맵", height=240),
        width="stretch",
    )

# ── 데이터 품질 ───────────────────────────────────────────
with tab_quality:
    st.caption("STEP 1 현장 조사 — docs/data_rules.md R1~R6. 문제 행은 삭제하지 않고 is_* 플래그만 붙였습니다. (전체 데이터 기준)")
    flags = pd.DataFrame(
        {
            "규칙": list(FLAG_LABELS.values()),
            "플래그 컬럼": list(FLAG_LABELS.keys()),
            "건수": [int(tx_all[col].sum()) for col in FLAG_LABELS],
        }
    )
    st.dataframe(flags, hide_index=True, width="stretch")

    all_total = tx_all["amount"].sum()
    clean_total = tx_all.loc[~tx_all["is_outlier"], "amount"].sum()
    st.markdown(
        '<div class="kpi-grid">'
        + kpi("이상값 포함 총지출", f"{all_total:,}", "원", "원본 그대로")
        + kpi("이상값 제외 총지출", f"{clean_total:,}", "원", "R5 플래그 행 제외")
        + kpi(
            "이상값 비중", f"{(all_total - clean_total) / all_total * 100:.1f}", "%",
            f"{int(tx_all['is_outlier'].sum())}건이 차지",
        )
        + "</div>",
        unsafe_allow_html=True,
    )

    all_outliers = tx_all[tx_all["is_outlier"]]
    if not all_outliers.empty:
        st.markdown(f"**R5 이상값 목록** ({len(all_outliers)}건)")
        st.dataframe(
            all_outliers.sort_values("amount", ascending=False)[
                ["transaction_id", "date", "category_name", "amount"]
            ],
            hide_index=True,
            column_config={"amount": st.column_config.NumberColumn("금액", format="%d원")},
            width="stretch",
        )

# ── 검증 · SQL 결과 ───────────────────────────────────────
with tab_check:
    st.caption("STEP 4 알리바이 확인 — 조건 카드와 상관없이 항상 전체 데이터 · 팀 합의 기준으로 대조합니다.")
    if all_ok:
        st.success("SQL과 Pandas로 각각 계산한 수치가 모두 일치합니다.")
    else:
        st.error("일치하지 않는 항목이 있습니다. 아래 분석 로그를 확인하세요.")

    for question, title in (
        ("q1", "Q1 카테고리별 지출 금액·건수·비중"),
        ("q2", "Q2 고액 거래"),
        ("q3", "Q3 월·요일·시간대별 지출"),
    ):
        if question in sql:
            with st.expander(f"{title} — SQL 결과 ({len(sql[question])}행)"):
                st.dataframe(sql[question], hide_index=True, width="stretch")

    with st.expander("main.py 분석 로그 (콘솔 출력)"):
        st.code(log_text, language=None)

# ── n8n 메일 브리핑 ───────────────────────────────────────
with tab_mail:
    st.caption(
        "STEP 6 메일 자동화 — n8n_auto.py 워크플로가 GitHub의 output/brief.json을 가져가 Gmail로 보냅니다. "
        "brief.json은 python main.py 실행 때 전체 데이터 기준으로 만들어지며, 조건 카드와 상관없습니다."
    )
    workflow = load_n8n_workflow()
    st.markdown(f"**{workflow['name']}**  \n" + " → ".join(f"`{name}`" for name in n8n_flow(workflow)))

    if not BRIEF_JSON.exists():
        st.warning("output/brief.json이 없습니다. python main.py를 먼저 실행해 주세요.")
    else:
        brief = json.loads(BRIEF_JSON.read_text(encoding="utf-8"))
        checks = check_n8n_handoff(workflow, brief)
        if all(ok for _, ok in checks):
            st.success("brief.json이 n8n 워크플로가 쓰는 파일·필드와 모두 맞습니다.")
        for name, ok in checks:
            st.markdown(f"{'✅' if ok else '❌'} {name}")
        for note in n8n_notes(workflow):
            st.warning(note)

        st.markdown("**메일 미리보기**")
        with st.container(border=True):
            st.markdown(f"**제목** {brief['subject']}")
            st.text(brief["body"])
        st.dataframe(pd.DataFrame(brief["kpis"]), hide_index=True, width="stretch")
