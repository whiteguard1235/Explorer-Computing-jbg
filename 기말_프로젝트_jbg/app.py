# =========================
# Math Contest Learning App
# app.py (project root)
# =========================

from pathlib import Path
import random
import re
import time
import json  # NEW: topic_summary 직렬화를 위해 추가

import pandas as pd
import streamlit as st


# -------------------------
# 1. 기본 설정
# -------------------------
st.set_page_config(
    page_title="Math Contest Learning App",
    page_icon="📘",
    layout="wide"
)

BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "data" / "processed" / "problems_final.csv"
HISTORY_PATH = BASE_DIR / "data" / "history.csv"  # NEW: 히스토리 파일 경로


# -------------------------
# 2. 데이터 로드 함수
# -------------------------
@st.cache_data
def load_data(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"CSV 파일을 찾을 수 없습니다: {path}")

    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]

    rename_map = {
        "exam_type": "examtype",
        "exam_name": "examname",
        "problem_no": "problemno",
        "problem_title": "problemtitle",
        "problem_url": "problemurl",
        "answer_key_url": "answerkeyurl",
        "statement_en": "statementen",
        "summary_en": "summaryen",
    }
    df = df.rename(columns=rename_map)

    expected_cols = [
        "year", "examtype", "examname", "problemno", "problemtitle",
        "problemurl", "answerkeyurl", "source", "statementen", "answer",
        "topic", "difficulty", "summaryen", "status"
    ]
    for col in expected_cols:
        if col not in df.columns:
            df[col] = ""

    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["problemno"] = pd.to_numeric(df["problemno"], errors="coerce")
    df["difficulty"] = pd.to_numeric(df["difficulty"], errors="coerce")

    text_cols = [
        "examtype", "examname", "problemtitle", "problemurl", "answerkeyurl",
        "source", "statementen", "answer", "topic", "summaryen", "status"
    ]
    for col in text_cols:
        df[col] = df[col].fillna("").astype(str).str.strip()

    df = df.dropna(subset=["year", "problemno"]).copy()
    return df


# -------------------------
# 3. 세션 상태 초기화
# -------------------------
def init_session_state():
    defaults = {
        "player_name": "",
        "history": [],
        "current_test": None,
        "last_result": None,
        "time_attack_set": None,
        "time_attack_index": 0,
        "time_attack_results": [],
        "time_attack_started_at": None,
        "time_attack_finished": False,
        "last_time_attack_result": None,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# -------------------------
# 4. 유틸 함수
# -------------------------
def safe_int(value, default=None):
    try:
        if pd.isna(value):
            return default
        return int(value)
    except:
        return default


def normalize_answer(text: str) -> str:
    s = str(text).strip()
    s = s.replace("−", "-").replace("–", "-")
    s = re.sub(r"\s+", "", s)

    if s.isdigit():
        s = s.zfill(3)

    return s


def parse_answer_candidates(raw) -> list[str]:
    s = str(raw).strip()

    if not s or s.lower() == "nan":
        return []

    s = re.sub(r"\s+(or|OR|Or)\s+", "|", s)
    s = s.replace("/", "|").replace(",", "|").replace(";", "|")

    parts = [normalize_answer(x) for x in s.split("|")]
    parts = [x for x in parts if x]

    return list(dict.fromkeys(parts))


def calculate_score(result_df: pd.DataFrame) -> tuple[int, int]:
    """
    난이도 * 10 점수제를 적용한다.
    - 각 문항의 배점 = difficulty * 10 (difficulty 없으면 10점으로 가정)
    - earned_score = 맞은 문제들의 배점 합
    - total_score = 모든 문제 배점 합
    """
    if result_df is None or result_df.empty:
        return 0, 0

    # difficulty가 없는 경우를 위해 기본값 1로 처리
    difficulties = result_df.get("difficulty", 1)
    difficulties = difficulties.fillna(1)

    # 각 문제 배점 = difficulty * 10
    weights = difficulties.astype(int) * 10

    # total_score = 모든 문제 배점 합
    total_score = int(weights.sum())

    # earned_score = 맞은 문제(correct=True)의 배점 합
    if "correct" in result_df.columns:
        earned_score = int(weights[result_df["correct"]].sum())
    else:
        earned_score = 0

    return earned_score, total_score


def render_problem_card(row, number_label=None, show_answer=False):
    title_prefix = f"{number_label}. " if number_label is not None else ""
    st.markdown(f"### {title_prefix}{row['problemtitle']}")

    meta = []

    year = safe_int(row["year"], None)
    problemno = safe_int(row["problemno"], None)
    difficulty = safe_int(row["difficulty"], None)

    if year is not None:
        meta.append(f"Year {year}")
    if row["examtype"]:
        meta.append(row["examtype"])
    if problemno is not None:
        meta.append(f"Problem {problemno}")
    if row["topic"]:
        meta.append(f"Topic: {row['topic']}")
    if difficulty is not None:
        meta.append(f"Difficulty: {difficulty}")

    if meta:
        st.caption(" | ".join(meta))

    if row["statementen"]:
        st.write(row["statementen"])
    else:
        st.write("(문제 본문이 없습니다.)")

    if row["summaryen"]:
        with st.expander("요약 보기"):
            st.write(row["summaryen"])

    c1, c2 = st.columns(2)
    with c1:
        if row["problemurl"]:
            st.markdown(f"[문제 원문 링크]({row['problemurl']})")
    with c2:
        if row["answerkeyurl"]:
            st.markdown(f"[정답/해설 링크]({row['answerkeyurl']})")

    if show_answer and row["answer"]:
        st.info(f"정답: {row['answer']}")


def grade_test(test_df: pd.DataFrame, prefix: str = "custom"):
    rows = []
    correct_count = 0

    for idx, row in test_df.iterrows():
        key = f"{prefix}_answer_{idx}"
        user_answer = st.session_state.get(key, "")
        user_norm = normalize_answer(user_answer)
        answer_candidates = parse_answer_candidates(row["answer"])
        is_correct = user_norm in answer_candidates if answer_candidates else False

        if is_correct:
            correct_count += 1

        rows.append({
            "year": safe_int(row["year"], ""),
            "examtype": row["examtype"],
            "problemno": safe_int(row["problemno"], ""),
            "topic": row["topic"],
            "difficulty": safe_int(row["difficulty"], ""),
            "correct": is_correct,
            "user_answer": user_answer,
            "true_answer": ", ".join(answer_candidates) if answer_candidates else row["answer"]
        })

    result_df = pd.DataFrame(rows)
    return result_df, correct_count


def build_feedback(score_rate: float, topic_stats: pd.Series):
    if score_rate >= 0.8:
        level = "상위권"
        overall = "전반적으로 매우 안정적인 풀이력을 보였습니다."
    elif score_rate >= 0.5:
        level = "중상위권"
        overall = "기본 실력은 갖추고 있지만, 특정 분야 보완이 필요합니다."
    else:
        level = "보완 필요"
        overall = "기본 유형 복습과 쉬운 문제 반복 풀이가 우선 필요합니다."

    weak_topics = topic_stats[topic_stats < 0.5].index.tolist() if not topic_stats.empty else []
    strong_topics = topic_stats[topic_stats >= 0.8].index.tolist() if not topic_stats.empty else []

    strong_text = (
        f"강한 분야: {', '.join(strong_topics)}"
        if strong_topics else
        "강한 분야는 아직 뚜렷하게 드러나지 않았습니다."
    )

    weak_text = (
        f"보완이 필요한 분야: {', '.join(weak_topics)}"
        if weak_topics else
        "보완이 필요한 분야가 뚜렷하게 드러나지 않았습니다."
    )

    return level, overall, strong_text, weak_text


# NEW: history 파일 로드/세이브 함수
def load_history_from_file():
    """
    앱 시작 시 history.csv를 읽어 session_state.history에 적재한다.
    topic_summary는 JSON 문자열로 저장해 두고 다시 dict로 복원한다.
    """
    if not HISTORY_PATH.exists():
        st.session_state.history = []
        return

    try:
        df = pd.read_csv(HISTORY_PATH)
    except Exception:
        st.session_state.history = []
        return

    records = []
    for _, row in df.iterrows():
        raw_topic_summary = row.get("topic_summary", "{}")
        try:
            topic_summary = json.loads(raw_topic_summary) if isinstance(raw_topic_summary, str) else {}
        except Exception:
            topic_summary = {}

        record = {
            "player_name": row.get("player_name", "Anonymous"),
            "mode": row.get("mode", ""),
            "correct_count": int(row.get("correct_count", 0)),
            "total": int(row.get("total", 0)),
            "earned_score": int(row.get("earned_score", 0)),
            "total_score": int(row.get("total_score", 0)),
            "score_rate": float(row.get("score_rate", 0.0)),
            "topic_summary": topic_summary,
        }
        records.append(record)

    st.session_state.history = records


def save_history_to_file():
    """
    session_state.history를 history.csv로 저장한다.
    topic_summary는 JSON 문자열로 직렬화한다.
    """
    if not st.session_state.history:
        return

    rows = []
    for item in st.session_state.history:
        rows.append({
            "player_name": item.get("player_name", "Anonymous"),
            "mode": item.get("mode", ""),
            "correct_count": item.get("correct_count", 0),
            "total": item.get("total", 0),
            "earned_score": item.get("earned_score", 0),
            "total_score": item.get("total_score", 0),
            "score_rate": item.get("score_rate", 0.0),
            "topic_summary": json.dumps(item.get("topic_summary", {}), ensure_ascii=False),
        })

    history_df = pd.DataFrame(rows)
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    history_df.to_csv(HISTORY_PATH, index=False, encoding="utf-8-sig")


def save_history(mode: str, correct_count: int, total: int, result_df: pd.DataFrame):
    player_name = st.session_state.player_name.strip() if st.session_state.player_name else "Anonymous"
    score_rate = correct_count / total if total > 0 else 0.0
    earned_score, total_score = calculate_score(result_df)

    topic_summary = {}
    if "topic" in result_df.columns and not result_df.empty:
        topic_summary = (
            result_df.groupby("topic")["correct"]
            .mean()
            .round(2)
            .to_dict()
        )

    history_item = {
        "player_name": player_name,
        "mode": mode,
        "correct_count": correct_count,
        "total": total,
        "earned_score": earned_score,
        "total_score": total_score,
        "score_rate": round(score_rate, 4),
        "topic_summary": topic_summary,
    }

    st.session_state.history.append(history_item)
    save_history_to_file()  # NEW: 파일에도 저장


def get_time_limit_by_difficulty(difficulty: int) -> int:
    mapping = {
        1: 180,
        2: 300,
        3: 600,
    }
    return mapping.get(difficulty, 180)


def format_seconds(seconds: float) -> str:
    seconds = max(0, int(seconds))
    minutes = seconds // 60
    remain = seconds % 60
    return f"{minutes:02d}:{remain:02d}"


def get_time_grade(elapsed_sec: float, limit_sec: int) -> str:
    ratio = elapsed_sec / limit_sec if limit_sec > 0 else 999

    if ratio <= 0.8:
        return "Excellent"
    elif ratio <= 1.0:
        return "Nice"
    elif ratio <= 1.3:
        return "So-So"
    elif ratio <= 2.0:
        return "Little Slow"
    else:
        return "Too Slow"


def build_time_attack_result_row(row, user_answer: str, elapsed_sec: float, gave_up: bool):
    difficulty = safe_int(row["difficulty"], 1)
    time_limit = get_time_limit_by_difficulty(difficulty)
    answer_candidates = parse_answer_candidates(row["answer"])
    user_norm = normalize_answer(user_answer)

    is_correct = (user_norm in answer_candidates) if answer_candidates and not gave_up else False

    if gave_up:
        grade = "Give Up"
    elif not is_correct:
        # 오답이면 시간과 무관하게 항상 Wrong
        grade = "Wrong"
    else:
        # 정답일 때만 시간 기반 Grade 적용
        grade = get_time_grade(elapsed_sec, time_limit)

    return {
        "year": safe_int(row["year"], ""),
        "examtype": row["examtype"],
        "problemno": safe_int(row["problemno"], ""),
        "topic": row["topic"],
        "difficulty": difficulty,
        "correct": is_correct,
        "user_answer": user_answer,
        "true_answer": ", ".join(answer_candidates) if answer_candidates else row["answer"],
        "elapsed_sec": round(elapsed_sec, 1),
        "time_limit_sec": time_limit,
        "grade": grade,
        "gave_up": gave_up,
    }


def reset_time_attack_state():
    st.session_state.time_attack_set = None
    st.session_state.time_attack_index = 0
    st.session_state.time_attack_results = []
    st.session_state.time_attack_started_at = None
    st.session_state.time_attack_finished = False
    st.session_state.last_time_attack_result = None


# -------------------------
# 5. 데이터 로드
# -------------------------
df = load_data(CSV_PATH)
init_session_state()
load_history_from_file()  # NEW: 파일에서 히스토리 복원


# -------------------------
# 6. 사이드바 메뉴
# -------------------------
st.sidebar.title("Menu")
page = st.sidebar.radio(
    "이동할 페이지를 선택하세요",
    ["Home", "Past Problems", "Custom Test", "Feedback", "Time Attack"]
)

# -------------------------
# 7. Home 페이지
# -------------------------
if page == "Home":
    st.title("수학경시 학습 보조 웹앱")

    player_name_input = st.text_input(
        "플레이어 이름",
        value=st.session_state.player_name,
        placeholder="예: CBG"
    ).strip()

    if player_name_input != st.session_state.player_name:
        st.session_state.player_name = player_name_input

    if st.session_state.player_name:
        st.success(f"현재 플레이어: {st.session_state.player_name}")
    else:
        st.info("플레이어 이름을 입력하면 결과 히스토리가 이름과 함께 저장됩니다.")

    st.write(
        "이 웹앱은 경시 수학 기출문제를 열람하고, "
        "원하는 조건의 시험지를 생성해 풀어본 뒤, "
        "결과를 바탕으로 자신의 강점과 약점을 분석할 수 있도록 설계되었습니다."
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        st.subheader("기출문제 열람")
        st.write("연도별·시험별 문제를 찾아보며 학습할 수 있습니다.")
    with c2:
        st.subheader("맞춤 시험지 생성")
        st.write("문제 수, 테마, 난이도를 골라 원하는 시험지를 만듭니다.")
    with c3:
        st.subheader("실력 분석")
        st.write("제출 결과를 바탕으로 강점과 약점을 확인할 수 있습니다.")

    st.divider()

    st.subheader("데이터 현황")
    st.write(f"총 문제 수: {len(df)}")
    st.write(f"포함 연도 수: {df['year'].dropna().nunique()}")
    st.write(f"시험 종류 수: {df['examtype'].replace('', pd.NA).dropna().nunique()}")


# -------------------------
# 8. Past Problems 페이지
# -------------------------
elif page == "Past Problems":
    st.title("기출문제 열람")

    years = sorted([
        safe_int(y) for y in df["year"].dropna().unique()
        if safe_int(y) is not None
    ])

    if not years:
        st.error("사용 가능한 연도 데이터가 없습니다.")
        st.stop()

    selected_year = st.selectbox("Year", years)

    examtypes = sorted([
        x for x in df.loc[df["year"] == selected_year, "examtype"]
        .fillna("").astype(str).str.strip().unique().tolist()
        if x
    ])

    if not examtypes:
        st.warning("해당 연도에 선택 가능한 Exam Type이 없습니다.")
        st.stop()

    selected_examtype = st.selectbox("Exam Type", examtypes)

    problem_numbers = sorted([
        safe_int(x) for x in df.loc[
            (df["year"] == selected_year) &
            (df["examtype"] == selected_examtype),
            "problemno"
        ].dropna().unique().tolist()
        if safe_int(x) is not None
    ])

    if not problem_numbers:
        st.warning("해당 조건의 문제가 없습니다.")
        st.stop()

    selected_problemno = st.selectbox("Problem No", problem_numbers)

    view_df = df[
        (df["year"] == selected_year) &
        (df["examtype"] == selected_examtype) &
        (df["problemno"] == selected_problemno)
    ]

    if not view_df.empty:
        row = view_df.iloc[0]
        render_problem_card(row, show_answer=False)

        show_answer = st.checkbox("정답 보기")
        if show_answer and row["answer"]:
            st.success(f"정답: {row['answer']}")
    else:
        st.warning("선택한 조건의 문제가 없습니다.")


# -------------------------
# 9. Custom Test 페이지
# -------------------------
elif page == "Custom Test":
    st.title("맞춤 시험지 생성")

    topics = sorted([
        x for x in df["topic"].dropna().astype(str).str.strip().unique().tolist()
        if x
    ])

    difficulties = sorted([
        safe_int(x) for x in df["difficulty"].dropna().unique()
        if safe_int(x) is not None
    ])

    c1, c2, c3 = st.columns(3)

    with c1:
        num_questions = st.slider("문제 수", min_value=3, max_value=15, value=5)

    with c2:
        selected_topics = st.multiselect(
            "테마",
            topics,
            default=topics[:2] if len(topics) >= 2 else topics
        )

    with c3:
        selected_difficulties = st.multiselect(
            "난이도",
            difficulties,
            default=difficulties
        )

    candidate_df = df.copy()

    if selected_topics:
        candidate_df = candidate_df[candidate_df["topic"].isin(selected_topics)]

    if selected_difficulties:
        candidate_df = candidate_df[candidate_df["difficulty"].isin(selected_difficulties)]

    candidate_df = candidate_df.reset_index(drop=True)

    st.write(f"선택 조건에 맞는 문제 수: {len(candidate_df)}")

    if st.button("시험지 생성", type="primary"):
        if len(candidate_df) < num_questions:
            st.warning("조건에 맞는 문제가 부족합니다. 조건을 조금 더 넓혀보세요.")
        else:
            test_df = candidate_df.sample(
                n=num_questions,
                random_state=random.randint(0, 100000)
            ).reset_index(drop=True)

            st.session_state.current_test = test_df
            st.session_state.last_result = None
            st.success("시험지가 생성되었습니다.")

    if st.session_state.current_test is not None:
        test_df = st.session_state.current_test

        st.divider()
        st.subheader("생성된 시험지")
        st.caption("숫자 답안은 자동으로 세 자리 형식으로 처리됩니다. 예: 7 → 007")

        with st.form("custom_test_form"):
            for idx, row in test_df.iterrows():
                render_problem_card(row, number_label=idx + 1, show_answer=False)

                st.text_input(
                    f"답 입력 - 문제 {idx + 1}",
                    key=f"custom_answer_{idx}",
                    placeholder="예: 007"
                )
                st.divider()

            submitted = st.form_submit_button("시험 제출")

        if submitted:
            result_df, correct_count = grade_test(test_df, prefix="custom")
            earned_score, total_score = calculate_score(result_df)

            st.session_state.last_result = {
                "mode": "Custom Test",
                "result_df": result_df,
                "correct_count": correct_count,
                "total": len(test_df),
                "earned_score": earned_score,
                "total_score": total_score
            }

            save_history("Custom Test", correct_count, len(test_df), result_df)

            st.success(
                f"제출 완료: {correct_count} / {len(test_df)} 정답 | "
                f"{earned_score} / {total_score} 점"
            )


# -------------------------
# 10. Feedback 페이지
# -------------------------
elif page == "Feedback":
    st.title("실력 분석 및 피드백")

    tab1, tab2, tab3 = st.tabs(["랜덤 시험지 피드백", "타임어택 피드백", "플레이 기록 히스토리"])

    with tab1:
        if st.session_state.last_result is None or st.session_state.last_result.get("mode") != "Custom Test":
            st.info("먼저 Custom Test 페이지에서 시험지를 생성하고 제출하세요.")
        else:
            result_df = st.session_state.last_result["result_df"]
            correct_count = st.session_state.last_result["correct_count"]
            total = st.session_state.last_result["total"]
            earned_score = st.session_state.last_result.get("earned_score", int(result_df["correct"].sum()))
            total_score = st.session_state.last_result.get("total_score", len(result_df))
            score_rate = correct_count / total if total > 0 else 0.0

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("맞은 문제", correct_count)
            with c2:
                st.metric("총 문제 수", total)
            with c3:
                st.metric("획득 점수", earned_score)
            with c4:
                st.metric("총 점수", total_score)

            st.caption(f"정답률: {score_rate * 100:.1f}%")

            if "topic" in result_df.columns and len(result_df) > 0:
                topic_stats = result_df.groupby("topic")["correct"].mean().sort_values()
            else:
                topic_stats = pd.Series(dtype=float)

            level, overall, strong_text, weak_text = build_feedback(score_rate, topic_stats)

            st.subheader("종합 평가")
            st.write(f"예상 성취 수준: **{level}**")
            st.write(overall)

            st.subheader("분야 분석")
            st.write(strong_text)
            st.write(weak_text)

            if not topic_stats.empty:
                st.subheader("토픽별 정답률")
                topic_chart_df = topic_stats.reset_index()
                topic_chart_df.columns = ["topic", "accuracy"]
                topic_chart_df["accuracy"] = topic_chart_df["accuracy"] * 100
                st.bar_chart(topic_chart_df.set_index("topic"))

            if "difficulty" in result_df.columns and len(result_df) > 0:
                difficulty_stats = result_df.groupby("difficulty")["correct"].mean().sort_index()
                if not difficulty_stats.empty:
                    st.subheader("난이도별 정답률")
                    difficulty_chart_df = difficulty_stats.reset_index()
                    difficulty_chart_df.columns = ["difficulty", "accuracy"]
                    difficulty_chart_df["difficulty"] = difficulty_chart_df["difficulty"].astype(str)
                    difficulty_chart_df["accuracy"] = difficulty_chart_df["accuracy"] * 100
                    st.bar_chart(difficulty_chart_df.set_index("difficulty"))

            st.subheader("문항별 결과")

            display_df = result_df.copy()
            display_df["correct_label"] = display_df["correct"].map({True: "정답", False: "오답"})

            correct_df = display_df[display_df["correct"] == True].copy()
            wrong_df = display_df[display_df["correct"] == False].copy()

            result_cols = [
                "year", "examtype", "problemno", "topic",
                "difficulty", "user_answer", "true_answer", "correct_label"
            ]

            rename_result_cols = {
                "year": "Year",
                "examtype": "Exam Type",
                "problemno": "Problem No",
                "topic": "Topic",
                "difficulty": "Difficulty",
                "user_answer": "Your Answer",
                "true_answer": "True Answer",
                "correct_label": "Result"
            }

            if not correct_df.empty:
                st.success("🟢 맞은 문제")
                st.dataframe(
                    correct_df[result_cols].rename(columns=rename_result_cols),
                    use_container_width=True,
                    hide_index=True
                )

            if not wrong_df.empty:
                st.error("🔴 틀린 문제")
                st.dataframe(
                    wrong_df[result_cols].rename(columns=rename_result_cols),
                    use_container_width=True,
                    hide_index=True
                )

            st.subheader("학습 방향")
            if score_rate >= 0.8:
                st.write("실전 감각 유지와 함께 고난도 문제 비중을 조금 더 늘리는 것이 좋습니다.")
            elif score_rate >= 0.5:
                st.write("틀린 문항의 토픽을 중심으로 중간 난이도 문제를 반복 학습하는 것이 좋습니다.")
            else:
                st.write("기본 유형 정리와 쉬운 문제 반복 풀이를 먼저 진행한 뒤 난이도를 높이는 것이 좋습니다.")

    with tab2:
        ta_result = st.session_state.last_time_attack_result

        if ta_result is None:
            st.info("먼저 Time Attack 페이지에서 타임어택을 완료하세요.")
        else:
            result_df = ta_result["result_df"]
            total = ta_result["total"]
            correct_count = ta_result["correct_count"]
            wrong_count = total - correct_count

            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("맞은 문제", correct_count)
            with c2:
                st.metric("틀린 문제", wrong_count)
            with c3:
                st.metric("총 문제 수", total)

            if not result_df.empty:
                grade_counts = result_df["grade"].value_counts().to_dict()
                st.subheader("Grade 분포")
                st.write(grade_counts)

                if "topic" in result_df.columns and len(result_df) > 0:
                    topic_stats = result_df.groupby("topic")["correct"].mean().sort_values()
                    if not topic_stats.empty:
                        st.subheader("토픽별 정답률")
                        topic_chart_df = topic_stats.reset_index()
                        topic_chart_df.columns = ["topic", "accuracy"]
                        topic_chart_df["accuracy"] = topic_chart_df["accuracy"] * 100
                        st.bar_chart(topic_chart_df.set_index("topic"))

                st.subheader("문항별 결과")
                display_df = result_df.copy()
                display_df["correct_label"] = display_df["correct"].map({True: "정답", False: "오답"})
                display_df["elapsed"] = display_df["elapsed_sec"].apply(lambda x: format_seconds(x))
                display_df["time_limit"] = display_df["time_limit_sec"].apply(lambda x: format_seconds(x))
                display_df["gave_up_label"] = display_df["gave_up"].map({True: "포기", False: "-"})

                show_cols = [
                    "year", "examtype", "problemno", "topic", "difficulty",
                    "user_answer", "true_answer", "correct_label",
                    "elapsed", "time_limit", "grade", "gave_up_label"
                ]

                rename_cols = {
                    "year": "Year",
                    "examtype": "Exam Type",
                    "problemno": "Problem No",
                    "topic": "Topic",
                    "difficulty": "Difficulty",
                    "user_answer": "Your Answer",
                    "true_answer": "True Answer",
                    "correct_label": "Result",
                    "elapsed": "Elapsed",
                    "time_limit": "Time Limit",
                    "grade": "Grade",
                    "gave_up_label": "Give Up"
                }

                st.dataframe(
                    display_df[show_cols].rename(columns=rename_cols),
                    use_container_width=True,
                    hide_index=True
                )

    with tab3:
        st.subheader("플레이 기록 히스토리")

        if st.session_state.history:
            history_df = pd.DataFrame(st.session_state.history).copy()
            history_df["score_rate"] = (history_df["score_rate"] * 100).round(1).astype(str) + "%"

            history_show = history_df[[
                "player_name", "mode", "correct_count", "total",
                "earned_score", "total_score", "score_rate"
            ]].rename(columns={
                "player_name": "Player",
                "mode": "Mode",
                "correct_count": "맞은 문제",
                "total": "총 문제 수",
                "earned_score": "획득 점수",
                "total_score": "총 점수",
                "score_rate": "정답률"
            })

            st.dataframe(
                history_show,
                use_container_width=True,
                hide_index=True
            )

            with st.expander("토픽별 기록 자세히 보기"):
                for i, row in enumerate(st.session_state.history, start=1):
                    st.write(
                        f"{i}. {row['player_name']} | {row['mode']} | "
                        f"{row['correct_count']}/{row['total']} | "
                        f"{row['earned_score']}/{row['total_score']}점 | "
                        f"{round(row['score_rate'] * 100, 1)}%"
                    )
                    st.write(f"토픽별 정답률: {row['topic_summary']}")
        else:
            st.info("아직 저장된 플레이 기록이 없습니다.")

        if st.button("히스토리 초기화"):
            st.session_state.history = []
            if HISTORY_PATH.exists():
                HISTORY_PATH.unlink()
            st.success("플레이 기록이 초기화되었습니다.")

# -------------------------
# 11. Time Attack 페이지
# -------------------------
elif page == "Time Attack":
    st.title("타임어택")

    st.write("한 문제씩 빠르게 풀며 감각을 유지하는 연습용 페이지입니다.")
    st.caption("난이도 1=3분, 난이도 2=5분, 난이도 3=10분 기준으로 Grade가 계산됩니다.")

    easy_df = df[df["difficulty"].fillna(99) <= 3].copy().reset_index(drop=True)

    num_ta = st.slider("문제 수", min_value=3, max_value=10, value=5)

    c1, c2 = st.columns(2)
    with c1:
        if st.button("타임어택 세트 만들기", type="primary"):
            if len(easy_df) < num_ta:
                st.warning("타임어택용 문제가 충분하지 않습니다.")
            else:
                reset_time_attack_state()
                st.session_state.time_attack_set = easy_df.sample(
                    n=num_ta,
                    random_state=random.randint(0, 100000)
                ).reset_index(drop=True)
                st.session_state.time_attack_started_at = time.time()
                st.success("타임어택 세트가 생성되었습니다.")

    with c2:
        if st.button("타임어택 초기화"):
            reset_time_attack_state()
            st.success("타임어택 상태가 초기화되었습니다.")

    if st.session_state.time_attack_set is not None and not st.session_state.time_attack_finished:
        ta_df = st.session_state.time_attack_set
        idx = st.session_state.time_attack_index

        if idx < len(ta_df):
            row = ta_df.iloc[idx]
            difficulty = safe_int(row["difficulty"], 1)
            time_limit = get_time_limit_by_difficulty(difficulty)

            st.divider()
            st.subheader(f"문제 {idx + 1} / {len(ta_df)}")
            st.caption("숫자 답안은 자동으로 세 자리 형식으로 처리됩니다. 예: 7 → 007")

            elapsed = time.time() - st.session_state.time_attack_started_at if st.session_state.time_attack_started_at else 0
            st.info(
                f"현재 경과 시간: {format_seconds(elapsed)} | "
                f"적정 시간: {format_seconds(time_limit)}"
            )

            render_problem_card(row, number_label=idx + 1, show_answer=False)

            user_answer = st.text_input(
                "답 입력",
                key=f"time_attack_single_answer_{idx}",
                placeholder="예: 007"
            )

            if f"time_attack_feedback_{idx}" not in st.session_state:
                st.session_state[f"time_attack_feedback_{idx}"] = None

            c_submit, c_giveup = st.columns(2)

            with c_submit:
                if st.button("제출", type="primary"):
                    elapsed = time.time() - st.session_state.time_attack_started_at if st.session_state.time_attack_started_at else 0
                    result_row = build_time_attack_result_row(
                        row=row,
                        user_answer=user_answer,
                        elapsed_sec=elapsed,
                        gave_up=False
                    )
                    st.session_state[f"time_attack_feedback_{idx}"] = result_row

            with c_giveup:
                if st.button("포기"):
                    elapsed = time.time() - st.session_state.time_attack_started_at if st.session_state.time_attack_started_at else 0
                    result_row = build_time_attack_result_row(
                        row=row,
                        user_answer="",
                        elapsed_sec=elapsed,
                        gave_up=True
                    )
                    st.session_state[f"time_attack_feedback_{idx}"] = result_row

            feedback = st.session_state[f"time_attack_feedback_{idx}"]
            if feedback is not None:
                is_correct = feedback["correct"]
                grade = feedback["grade"]
                elapsed_show = format_seconds(feedback["elapsed_sec"])
                limit_show = format_seconds(feedback["time_limit_sec"])

                if feedback["gave_up"]:
                    st.warning(
                        f"포기 처리되었습니다. (경과 시간 {elapsed_show} / 적정 시간 {limit_show}, Grade: {grade})"
                    )
                else:
                    if is_correct:
                        st.success(
                            f"정답입니다! (경과 시간 {elapsed_show} / 적정 시간 {limit_show}, Grade: {grade})"
                        )
                    else:
                        st.error(
                            f"오답입니다. (경과 시간 {elapsed_show} / 적정 시간 {limit_show}, Grade: {grade})"
                        )
                        st.info(f"정답: {feedback['true_answer']}")

                if st.button("다음 문제로 넘어가기"):
                    st.session_state.time_attack_results.append(feedback)
                    st.session_state.time_attack_index += 1
                    st.session_state.time_attack_started_at = time.time()
                    st.session_state[f"time_attack_feedback_{idx}"] = None

                    if st.session_state.time_attack_index >= len(ta_df):
                        st.session_state.time_attack_finished = True
                        result_df = pd.DataFrame(st.session_state.time_attack_results)
                        correct_count = int(result_df["correct"].sum()) if not result_df.empty else 0
                        st.session_state.last_time_attack_result = {
                            "mode": "Time Attack",
                            "result_df": result_df,
                            "correct_count": correct_count,
                            "total": len(result_df)
                        }
                        save_history("Time Attack", correct_count, len(result_df), result_df)

                    st.rerun()

        else:
            st.session_state.time_attack_finished = True

    if st.session_state.time_attack_finished and st.session_state.last_time_attack_result is not None:
        ta_result = st.session_state.last_time_attack_result
        result_df = ta_result["result_df"]
        total = ta_result["total"]
        correct_count = ta_result["correct_count"]
        wrong_count = total - correct_count

        st.divider()
        st.subheader("타임어택 결과")

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("맞은 문제", correct_count)
        with c2:
            st.metric("틀린 문제", wrong_count)
        with c3:
            st.metric("총 문제 수", total)

        if not result_df.empty:
            grade_counts = result_df["grade"].value_counts().to_dict()
            st.write("Grade 요약")
            st.write(grade_counts)

            display_df = result_df.copy()
            display_df["correct_label"] = display_df["correct"].map({True: "정답", False: "오답"})
            display_df["elapsed"] = display_df["elapsed_sec"].apply(lambda x: format_seconds(x))
            display_df["time_limit"] = display_df["time_limit_sec"].apply(lambda x: format_seconds(x))
            display_df["gave_up_label"] = display_df["gave_up"].map({True: "포기", False: "-"})

            show_cols = [
                "year", "examtype", "problemno", "topic", "difficulty",
                "user_answer", "true_answer", "correct_label",
                "elapsed", "time_limit", "grade", "gave_up_label"
            ]

            rename_cols = {
                "year": "Year",
                "examtype": "Exam Type",
                "problemno": "Problem No",
                "topic": "Topic",
                "difficulty": "Difficulty",
                "user_answer": "Your Answer",
                "true_answer": "True Answer",
                "correct_label": "Result",
                "elapsed": "Elapsed",
                "time_limit": "Time Limit",
                "grade": "Grade",
                "gave_up_label": "Give Up"
            }

            st.dataframe(
                display_df[show_cols].rename(columns=rename_cols),
                use_container_width=True,
                hide_index=True
            )