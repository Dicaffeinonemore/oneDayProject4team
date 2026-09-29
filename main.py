"""
main.py  —  소비패턴 데이터 탐정 🕵️

팀원 결과물을 한 번에 연결해 실행한다.

  STEP 1. 현장 조사   : 결측·중복·이상값 점검 (docs/data_rules.md 규칙, 삭제 없이 플래그만)
  STEP 2. 단서 분류   : Python 분류 함수로 금액 등급·시간대 태그 붙이기
  STEP 3. SQL 심문    : sql/q1~q3_*.sql 실행 (2번 SQL 담당, function/run_sql.py)
  STEP 4. 알리바이 확인: 같은 질문을 Pandas로 다시 계산해 SQL 결과와 대조
                       + function/validation_suyeon.py 실행 → output/validation_result.csv
  STEP 5. 사건 보고서  : function/brief_seongho.py 실행 → output/briefing.md, output/brief.json
  STEP 6. 메일 자동화  : n8n_auto.py(n8n 워크플로)가 brief.json을 메일로 보낼 수 있는지 점검

실행: python main.py   (프로젝트 폴더 어디서 실행해도 동작)
"""
import json
import os
import re
import runpy
import sqlite3
import subprocess
from pathlib import Path

import pandas as pd

from function import validation_suyeon
from function.run_sql import DATABASE_PATH, DATA_DIR, SQL_DIR, load_csv_files

PROJECT_DIR = Path(__file__).resolve().parent
BRIEF_SCRIPT = PROJECT_DIR / "function" / "brief_seongho.py"
BRIEF_JSON = PROJECT_DIR / "output" / "brief.json"
# 확장자는 .py지만 내용은 n8n에서 내보낸 워크플로 JSON이다.
N8N_WORKFLOW = PROJECT_DIR / "n8n_auto.py"

# Q2 '큰 금액' 기준: 팀 합의값 (sql/q2, brief_seongho.py와 동일해야 함)
HIGH_AMOUNT_THRESHOLD = 150_000
SMALL_AMOUNT_THRESHOLD = 10_000

WEEKDAY_KO = ["일", "월", "화", "수", "목", "금", "토"]  # SQLite strftime('%w') 순서


def section(title: str) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def won(x: float) -> str:
    return f"{int(round(x)):,}원"


# ── Python 분류 함수 ──────────────────────────────────────
def classify_amount(amount: int) -> str:
    """거래 금액을 소액 / 일반 / 고액으로 분류한다."""
    if amount >= HIGH_AMOUNT_THRESHOLD:
        return "고액"
    if amount < SMALL_AMOUNT_THRESHOLD:
        return "소액"
    return "일반"


def classify_time(time_text: str) -> str:
    """'HH:MM' 문자열을 시간대 이름으로 분류한다."""
    hour = int(time_text[:2])
    if hour < 6:
        return "새벽"
    if hour < 12:
        return "오전"
    if hour < 18:
        return "오후"
    return "저녁"


# ── STEP 1. 현장 조사 ─────────────────────────────────────
def load_frames() -> dict[str, pd.DataFrame]:
    return {
        path.stem: pd.read_csv(path, encoding="utf-8-sig")
        for path in sorted(DATA_DIR.glob("*.csv"))
    }


def inspect_data(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """data_rules.md R1~R6 규칙으로 문제 행을 찾아 is_* 플래그를 붙인다."""
    section("STEP 1. 현장 조사 — 결측·중복·이상값 점검")
    tx = frames["transactions"].copy()

    for name, df in frames.items():
        print(f"- {name}: {len(df):,}행, 결측 {int(df.isna().sum().sum())}개")

    full_dup = tx.duplicated()
    print(f"- R1 완전 중복: {int(full_dup.sum())}건 (첫 행만 남김)")
    tx = tx[~full_dup].copy()

    tx["is_dup_id"] = tx["transaction_id"].duplicated(keep=False)
    known = set(frames["categories"]["category"])
    tx["is_unknown_category"] = tx["category"].isna() | ~tx["category"].isin(known)
    tx["is_orphan"] = ~tx["customer_id"].isin(frames["customers"]["customer_id"]) | ~tx[
        "merchant_id"
    ].isin(frames["merchants"]["merchant_id"])
    tx["is_invalid_amount"] = tx["amount"] <= 0

    # R5: 카테고리별 IQR 상한 초과
    q1 = tx.groupby("category")["amount"].transform(lambda s: s.quantile(0.25))
    q3 = tx.groupby("category")["amount"].transform(lambda s: s.quantile(0.75))
    tx["is_outlier"] = tx["amount"] > q3 + 1.5 * (q3 - q1)

    labels = {
        "is_dup_id": "R2 ID 중복",
        "is_unknown_category": "R3 카테고리 결측·미등록",
        "is_orphan": "R4 고객·가맹점 조인 실패",
        "is_outlier": "R5 이상값(카테고리별 IQR)",
        "is_invalid_amount": "R6 금액 0 이하",
    }
    for column, label in labels.items():
        print(f"- {label}: {int(tx[column].sum())}건")

    outliers = tx[tx["is_outlier"]]
    print(
        f"  → 이상값은 삭제하지 않고 플래그만 붙임. "
        f"포함 시 총지출 {won(tx['amount'].sum())} / 제외 시 {won(tx.loc[~tx['is_outlier'], 'amount'].sum())} "
        f"(이상값 {len(outliers)}건이 {outliers['amount'].sum() / tx['amount'].sum() * 100:.1f}% 차지)"
    )
    return tx


# ── STEP 2. 단서 분류 ─────────────────────────────────────
def tag_transactions(tx: pd.DataFrame) -> pd.DataFrame:
    section("STEP 2. 단서 분류 — Python 분류 함수 적용")
    tx["amount_level"] = tx["amount"].map(classify_amount)
    tx["time_band"] = tx["time"].map(classify_time)

    summary = (
        tx.groupby("amount_level")["amount"]
        .agg(건수="count", 금액="sum")
        .reindex(["소액", "일반", "고액"], fill_value=0)
    )
    summary["금액비중(%)"] = (summary["금액"] / tx["amount"].sum() * 100).round(1)
    print(f"금액 등급 (소액 < {won(SMALL_AMOUNT_THRESHOLD)} ≤ 일반 < {won(HIGH_AMOUNT_THRESHOLD)} ≤ 고액)")
    print(summary.to_string())

    band = tx.groupby("time_band")["amount"].sum().reindex(["새벽", "오전", "오후", "저녁"], fill_value=0)
    print("\n시간대별 지출")
    print(band.map(won).to_string())
    return tx


# ── STEP 3. SQL 심문 ──────────────────────────────────────
def run_sql_files() -> dict[str, pd.DataFrame]:
    section("STEP 3. SQL 심문 — WHERE · GROUP BY · ORDER BY")
    results = {}
    with sqlite3.connect(DATABASE_PATH) as connection:
        load_csv_files(connection)
        for question in ("q1", "q2", "q3"):
            for sql_path in sorted(SQL_DIR.glob(f"{question}_*.sql")):
                query = sql_path.read_text(encoding="utf-8-sig").strip()
                title = query.splitlines()[0].lstrip("- ").strip()
                result = pd.read_sql_query(query, connection)
                results[question] = result
                print(f"\n[{question.upper()}] {title}  ({sql_path.name}, {len(result)}행)")
                print(result.head(5).to_string(index=False))
    return results


# ── STEP 4. 알리바이 확인 ─────────────────────────────────
def cross_check(tx: pd.DataFrame, sql: dict[str, pd.DataFrame]) -> bool:
    """같은 질문을 Pandas로 다시 풀어 SQL 결과와 숫자가 맞는지 대조한다."""
    section("STEP 4. 알리바이 확인 — SQL vs Pandas 교차검증")
    checks = []

    if "q1" in sql:
        pd_q1 = tx.groupby("category")["amount"].agg(["count", "sum"])
        sql_q1 = sql["q1"].set_index("category")[["transaction_count", "total_amount"]]
        sql_q1.columns = ["count", "sum"]
        checks.append(("Q1 카테고리별 건수·금액", pd_q1.sort_index().equals(sql_q1.sort_index())))
        checks.append(("Q1 비중 합계 100%", abs(sql["q1"]["amount_share_pct"].sum() - 100) < 0.1))

    if "q2" in sql:
        high = tx[tx["amount"] >= HIGH_AMOUNT_THRESHOLD]
        checks.append(("Q2 고액 거래 건수", len(high) == len(sql["q2"])))
        checks.append(("Q2 고액 거래 금액 합", high["amount"].sum() == sql["q2"]["amount"].sum()))

    if "q3" in sql:
        dates = pd.to_datetime(tx["date"])
        pandas_periods = {
            "month": tx.groupby(dates.dt.strftime("%m"))["amount"].sum(),
            "weekday": tx.groupby(((dates.dt.dayofweek + 1) % 7).astype(str))["amount"].sum(),
            "hour": tx.groupby(tx["time"].str[:2])["amount"].sum(),
        }
        for period, pd_sum in pandas_periods.items():
            sql_sum = sql["q3"].query("period_type == @period").set_index("period_value")["total_amount"]
            checks.append((f"Q3 {period}별 금액", pd_sum.sort_index().to_dict() == sql_sum.sort_index().to_dict()))
        months_total = sql["q3"].query("period_type == 'month'")["total_amount"].sum()
        checks.append(("전체 합계 = 월별 합계", months_total == tx["amount"].sum()))

    for name, ok in checks:
        print(f"{'✅' if ok else '❌'} {name}")
    all_ok = all(ok for _, ok in checks)
    print("\n→ 모든 수치 일치" if all_ok else "\n→ 불일치 항목 확인 필요")
    return all_ok


def run_validation() -> None:
    """5번 검증 담당 스크립트(function/validation_suyeon.py)를 실행한다."""
    # validation_suyeon.py는 자기 파일 위치 기준으로 data/sql/output 경로를 잡으므로
    # function/ 폴더로 옮긴 뒤에는 프로젝트 폴더 기준 경로로 바꿔서 실행한다.
    validation_suyeon.PROJECT_DIR = PROJECT_DIR
    validation_suyeon.DATA_DIR = PROJECT_DIR / "data"
    validation_suyeon.SQL_DIR = PROJECT_DIR / "sql"
    validation_suyeon.OUTPUT_DIR = PROJECT_DIR / "output"
    validation_suyeon.main()


# ── STEP 5. 사건 보고서 ───────────────────────────────────
def detective_findings(tx: pd.DataFrame, sql: dict[str, pd.DataFrame]) -> None:
    section("🕵️ 탐정의 결론")
    q1 = sql["q1"].iloc[0]
    print(f"1. [Q1] 돈이 가장 많이 새는 곳은 '{q1['category_name']}' — {won(q1['total_amount'])} (전체의 {q1['amount_share_pct']}%)")

    high = sql["q2"]
    high_share = high["amount"].sum() / tx["amount"].sum() * 100
    top_high_cat = high["category_name"].value_counts().idxmax()
    print(
        f"2. [Q2] {won(HIGH_AMOUNT_THRESHOLD)} 이상 고액 거래 {len(high)}건({len(high) / len(tx) * 100:.1f}%)이 "
        f"전체 지출의 {high_share:.1f}% 차지, 가장 잦은 카테고리는 '{top_high_cat}'"
    )

    q3 = sql["q3"]
    month = q3.query("period_type == 'month'").set_index("period_value")["total_amount"]
    weekday = q3.query("period_type == 'weekday'").set_index("period_value")["total_amount"]
    hour = q3.query("period_type == 'hour'").set_index("period_value")["total_amount"]
    print(
        f"3. [Q3] 최고 지출 월 {int(month.idxmax())}월({won(month.max())}), 최저 {int(month.idxmin())}월({won(month.min())}) · "
        f"{WEEKDAY_KO[int(weekday.idxmax())]}요일 · {int(hour.idxmax())}시에 지출이 가장 몰림"
    )


def write_briefing() -> None:
    section("STEP 5. 사건 보고서 — 브리핑 생성 (brief_seongho.py)")
    # brief_seongho.py는 'data', 'output' 상대 경로를 쓰므로 프로젝트 폴더에서 실행한다.
    current_dir = Path.cwd()
    os.chdir(PROJECT_DIR)
    try:
        runpy.run_path(str(BRIEF_SCRIPT), run_name="__main__")
    finally:
        os.chdir(current_dir)


# ── STEP 6. 메일 자동화 ───────────────────────────────────
def load_n8n_workflow() -> dict:
    return json.loads(N8N_WORKFLOW.read_text(encoding="utf-8"))


def n8n_node(workflow: dict, kind: str) -> dict:
    """노드 종류(httpRequest, gmail 등)로 워크플로 노드를 찾는다."""
    return next(node for node in workflow["nodes"] if node["type"].endswith(f".{kind}"))


def n8n_flow(workflow: dict) -> list[str]:
    """트리거부터 connections를 따라가며 실행 순서대로 노드 이름을 나열한다."""
    connections = workflow["connections"]
    targets = {link["node"] for outs in connections.values() for branch in outs["main"] for link in branch}
    current = next(name for name in connections if name not in targets)
    flow = []
    while current:
        flow.append(current)
        branches = connections.get(current, {}).get("main", [])
        current = branches[0][0]["node"] if branches and branches[0] else None
    return flow


def check_n8n_handoff(workflow: dict, brief: dict) -> list[tuple[str, bool]]:
    """n8n이 가져가는 파일·필드와 brief_seongho.py가 만든 brief.json이 맞물리는지 확인한다."""
    url = n8n_node(workflow, "httpRequest")["parameters"]["url"]
    mail = n8n_node(workflow, "gmail")["parameters"]
    used_fields = sorted(set(re.findall(r"\$json\.(\w+)", json.dumps(mail))))
    return [
        ("n8n이 가져가는 파일 = output/brief.json", url.endswith("/output/brief.json")),
        *[(f"brief.json '{field}' 필드 (메일 노드가 사용)", bool(brief.get(field))) for field in used_fields],
    ]


def n8n_notes(workflow: dict) -> list[str]:
    """n8n에서 실행하기 전에 사람이 챙겨야 할 것."""
    gmail = n8n_node(workflow, "gmail")
    notes = []
    if gmail["parameters"]["sendTo"].endswith("@example.com"):
        notes.append("'브리핑 메일 발송' 노드의 받는 사람(To)이 예시 주소 — n8n에서 실제 주소로 바꿔야 함")
    if "credentials" not in gmail:
        notes.append("Gmail 계정(OAuth2)이 워크플로에 연결되어 있지 않음 — n8n에서 연결 필요")
    try:
        changed = subprocess.run(
            ["git", "status", "--porcelain", "--", str(BRIEF_JSON)],
            cwd=PROJECT_DIR, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        changed = ""
    if changed:
        notes.append("output/brief.json이 마지막 커밋과 다름 — GitHub main에 push해야 n8n이 새 내용을 가져감")
    return notes


def prepare_n8n_mail() -> bool:
    section("STEP 6. 메일 자동화 — n8n 워크플로 점검 (n8n_auto.py)")
    workflow = load_n8n_workflow()
    brief = json.loads(BRIEF_JSON.read_text(encoding="utf-8"))
    print(f"워크플로: {workflow['name']}")
    print("흐름: " + " → ".join(n8n_flow(workflow)))

    checks = check_n8n_handoff(workflow, brief)
    for name, ok in checks:
        print(f"{'✅' if ok else '❌'} {name}")
    for note in n8n_notes(workflow):
        print(f"⚠️ {note}")
    print(f"\n메일 제목: {brief['subject']}")
    return all(ok for _, ok in checks)


def main() -> None:
    print("🕵️ 소비패턴 데이터 탐정 — 수사를 시작합니다")
    frames = load_frames()
    tx = inspect_data(frames)
    tx = tag_transactions(tx)
    sql = run_sql_files()
    cross_check(tx, sql)
    run_validation()
    write_briefing()
    prepare_n8n_mail()
    detective_findings(tx, sql)


if __name__ == "__main__":
    main()
