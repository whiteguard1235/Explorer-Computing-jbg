import os
import re
import pandas as pd
from pandas.errors import EmptyDataError


PROBLEMS_CSV = "data/interim/problems_parsed.csv"
ANSWERS_CSV = "data/interim/answers_parsed.csv"
OUT_CSV = "data/processed/problems_final.csv"


def safe_read_csv(path):
    # 파일이 없거나 비어 있으면 None을 반환해서 병합 단계가 안전하게 돌아가게 한다.
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return None
    try:
        return pd.read_csv(path)
    except EmptyDataError:
        return None


def normalize_text(text):
    # 분류용 텍스트를 소문자/공백 기준으로 정리한다.
    t = str(text).lower()
    t = t.replace("\n", " ")
    t = re.sub(r"\s+", " ", t).strip()

    # "relatively prime"은 여러 분야의 정답 표현으로 자주 나오므로
    # number theory 신호에서 제외하기 위해 먼저 제거한다.
    t = re.sub(r"\brelatively\s+prime\b", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def classify_topic(text):
    # 문제 본문의 키워드를 바탕으로 주제를 추정한다.
    t = normalize_text(text)

    scores = {
        "기하학(Geometry)": 0,
        "정수론(Number Theory)": 0,
        "조합론(Combinatorics)": 0,
        "대수(Algebra)": 0,
    }

    geometry_patterns = [
        r"\btriangle\b", r"\bcircle\b", r"\bcircumcircle\b", r"\bincircle\b",
        r"\bangle\b", r"\bpolygon\b", r"\bquadrilateral\b", r"\bhexagon\b",
        r"\boctagon\b", r"\bdodecagon\b", r"\bparallelogram\b", r"\btrapezoid\b",
        r"\brhombus\b", r"\brectangle\b", r"\bsquare\b", r"\btetrahedron\b",
        r"\bcube\b", r"\bsphere\b", r"\bcone\b", r"\bplane\b", r"\bpoint\b",
        r"\bline\b", r"\bsegment\b", r"\bradius\b", r"\bdiameter\b",
        r"\bperpendicular\b", r"\bparallel\b", r"\btangent\b", r"\bchord\b",
        r"\barc\b", r"\bcircumcenter\b", r"\bincenter\b", r"\bcentroid\b",
        r"\barea\b", r"\bperimeter\b", r"\blength\b", r"\bdistance\b",
        r"\binscribed\b", r"\bcyclic\b",
        r"\bmidpoint\b", r"\bconvex\b", r"\binside the circle\b"
    ]

    number_theory_patterns = [
        r"\bprime factor\b", r"\bprime factors\b",
        r"\bprime factorization\b",
        r"\bdivisor\b", r"\bdivisors\b", r"\bdivisible\b", r"\bdivides\b",
        r"\bremainder\b", r"\bquotient\b", r"\bgreatest common divisor\b",
        r"\bleast common multiple\b", r"\bgcd\b", r"\blcm\b",
        r"\bmod\b", r"\bmodulo\b", r"\bcongruent\b",
        r"\bdigits?\b", r"\bbase[- ]?\w+\b", r"\bpalindrome\b",
        r"\bmultiple\b", r"\bmultiples\b", r"\brepeating decimal\b",
    ]

    combinatorics_patterns = [
        r"\bchoose\b", r"\bchooses\b", r"\bchosen\b", r"\bselection\b",
        r"\barrange\b", r"\barrangement\b", r"\barrangements\b",
        r"\bpermutation\b", r"\bpermutations\b", r"\bcombination\b",
        r"\bcombinations\b", r"\bsubset\b", r"\bsubsets\b", r"\bset of all\b",
        r"\bprobability\b", r"\brandom\b", r"\brandomly\b",
        r"\bindependently\b", r"\bwith replacement\b", r"\bwithout replacement\b",
        r"\bways\b", r"\bhow many\b", r"\bcommittee\b", r"\bsequence of moves\b",
        r"\bexpected\b", r"\bgame\b", r"\bcolorings\b",
        r"\btournament\b", r"\bassigned opponents\b", r"\bselected at random\b",
        r"\bordered pairs\b", r"\bunordered pairs\b",
        r"\bdice\b", r"\bdie\b", r"\bcoin\b",
        r"\bconditional probability\b"
    ]

    algebra_patterns = [
        r"\bpolynomial\b", r"\bquadratic\b", r"\bcubic\b", r"\broot\b", r"\broots\b",
        r"\bequation\b", r"\bequations\b", r"\bsolve\b", r"\bsolution\b",
        r"\breal number\b", r"\breal numbers\b", r"\bcomplex\b",
        r"\bfunction\b", r"\bfunctions\b", r"\bsequence\b", r"\brecursive\b",
        r"\barithmetic sequence\b", r"\bgeometric progression\b",
        r"\bmean\b", r"\baverage\b", r"\bsystem of equations\b"
    ]

    for p in geometry_patterns:
        if re.search(p, t):
            scores["기하학(Geometry)"] += 2

    for p in number_theory_patterns:
        if re.search(p, t):
            scores["정수론(Number Theory)"] += 2

    for p in combinatorics_patterns:
        if re.search(p, t):
            scores["조합론(Combinatorics)"] += 2

    for p in algebra_patterns:
        if re.search(p, t):
            scores["대수(Algebra)"] += 2

    # 강한 힌트 보정
    if re.search(
        r"\bfind the number of\b|\bnumber of ways\b|\bhow many\b|"
        r"\bdice\b|\bcoin\b|\bcoins\b|\bways\b|\bway\b|\bpath\b|\bpaths\b|"
        r"\bmarble\b|\bmarbles\b|\bprobability\b|\brandomly\b|\bindependently\b|"
        r"\bexpected number\b",
        t,
    ):
        scores["조합론(Combinatorics)"] += 2

    if re.search(r"\bdivisible\b|\bdivisor\b|\bremainder\b|\bprime\b|\bgcd\b|\blcm\b", t):
        scores["정수론(Number Theory)"] += 2

    if re.search(
        r"\bcircumcircle\b|\bplane\b|\blengths\b|\blength\b|\bcircumcenter\b|"
        r"\bsphere\b|\btriangle\b|\bcircle\b|\bangle\b|\barea\b|\bperimeter\b|"
        r"\btangent\b|\bparallel\b|\bperpendicular\b|\bmidpoint\b",
        t,
    ):
        scores["기하학(Geometry)"] += 2

    if re.search(r"\bpolynomial\b|\bquadratic\b|\bcubic\b|\bfunction\b|\binfinite\b", t):
        scores["대수(Algebra)"] += 2

    # 예외 보정:
    # "find the number of"가 있어도 divisibility/prime/remainder 류가 강하면 정수론 쪽으로 다시 밀어준다.
    if re.search(r"\bfind the number of\b", t) and re.search(
        r"\bdivisible\b|\bdivisor\b|\bremainder\b|\bprime\b|\binteger\b|\bdigits?\b",
        t,
    ):
        scores["정수론(Number Theory)"] += 2

    # "find the number of"가 있어도 triangle/circle/area/perimeter가 강하면 기하로 다시 밀어준다.
    if re.search(r"\bfind the number of\b", t) and re.search(
        r"\btriangle\b|\bcircle\b|\bangle\b|\barea\b|\bperimeter\b|\btangent\b",
        t,
    ):
        scores["기하학(Geometry)"] += 2

    # 확률/랜덤은 조합론 쪽에 더 강하게 반영
    if re.search(r"\bprobability\b|\brandom\b|\brandomly\b|\bindependently\b|\bexpected\b", t):
        scores["조합론(Combinatorics)"] += 3

    # 동점일 때는 AIME 스타일상 대체로
    # Geometry > Number Theory > Combinatorics > Algebra 순으로 우선한다.
    priority = [
        "기하학(Geometry)",
        "정수론(Number Theory)",
        "조합론(Combinatorics)",
        "대수(Algebra)",
    ]

    best_score = max(scores.values())
    candidates = [k for k, v in scores.items() if v == best_score]

    for topic in priority:
        if topic in candidates:
            return topic

    return "대수(Algebra)"


def estimate_difficulty(problem_no):
    # AIME는 보통 뒤 번호로 갈수록 난도가 높아지는 경향이 있어 이를 대략 반영한다.
    try:
        n = int(problem_no)
    except (TypeError, ValueError):
        return None

    if n <= 3:
        return 1
    if n <= 6:
        return 2
    if n <= 10:
        return 3
    if n <= 13:
        return 4
    return 5


def summarize(text, max_len=140):
    # 본문 앞부분을 짧은 요약으로 잘라 저장한다.
    text = str(text).replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:max_len] + ("..." if len(text) > max_len else "")


def merge_append(old_df, new_df, key="problem_url"):
    # 기존 최종 데이터와 새 데이터를 problem_url 기준으로 합친다.
    if old_df is None or len(old_df) == 0:
        return new_df.copy()

    if key in old_df.columns and key in new_df.columns:
        old_df = old_df[~old_df[key].isin(new_df[key])]
        return pd.concat([old_df, new_df], ignore_index=True).drop_duplicates(
            subset=[key], keep="last"
        )

    return pd.concat([old_df, new_df], ignore_index=True).drop_duplicates(keep="last")


def main():
    problems = safe_read_csv(PROBLEMS_CSV)
    if problems is None or len(problems) == 0:
        print(f"no valid problems csv: {PROBLEMS_CSV}")
        return

    print(f"loaded problems: {len(problems)}")

    # 파싱이 실제로 성공한 문제만 최종 데이터셋 대상으로 삼는다.
    if "status" in problems.columns:
        problems = problems[problems["status"] == "ok"].copy()

    # 문제 본문이 비어 있는 행은 제외한다.
    if "statement_en" not in problems.columns:
        print("missing required column: statement_en")
        return

    problems = problems[problems["statement_en"].fillna("").str.len() > 0].copy()

    answers = safe_read_csv(ANSWERS_CSV)
    if answers is not None and len(answers) > 0:
        print(f"loaded answers: {len(answers)}")
        if all(c in problems.columns for c in ["exam_name", "problem_no"]) and all(
            c in answers.columns for c in ["exam_name", "problem_no"]
        ):
            problems = problems.merge(
                answers,
                on=["exam_name", "problem_no"],
                how="left",
                suffixes=("", "_ans"),
            )

            # answer 컬럼 정리
            if "answer_ans" in problems.columns:
                if "answer" in problems.columns:
                    problems["answer"] = problems["answer"].fillna(problems["answer_ans"])
                else:
                    problems["answer"] = problems["answer_ans"]
                problems = problems.drop(columns=["answer_ans"])
    else:
        print(f"no valid answers csv: {ANSWERS_CSV}")

    # 답안 컬럼이 없더라도 후속 코드가 깨지지 않도록 기본값을 채운다.
    if "answer" not in problems.columns:
        problems["answer"] = ""

    # 주제, 난이도, 요약 컬럼을 추가해 후속 분석과 활용을 쉽게 만든다.
    problems["topic"] = problems["statement_en"].apply(classify_topic)
    problems["difficulty"] = problems["problem_no"].apply(estimate_difficulty)
    problems["summary_en"] = problems["statement_en"].apply(summarize)

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    old = safe_read_csv(OUT_CSV)
    combined = merge_append(old, problems, key="problem_url")
    combined.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    print("saved:", OUT_CSV, len(combined))
    print("topic counts:")
    print(combined["topic"].value_counts(dropna=False).to_dict())


if __name__ == "__main__":
    main()