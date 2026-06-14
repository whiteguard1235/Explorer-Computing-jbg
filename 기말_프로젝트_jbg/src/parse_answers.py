import os
import re
import pandas as pd
from pandas.errors import EmptyDataError
from bs4 import BeautifulSoup

INDEX_CSV = "data/raw/problem_index.csv"
HTML_DIR = "data/raw/html"
OUT_CSV = "data/interim/answers_parsed.csv"
LOG_CSV = "data/interim/answers_log.csv"


def safe_name(title):
    # 파일명으로 쓰기 어려운 문자는 언더스코어로 바꾼다.
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(title)) + ".html"


def safe_read_csv(path):
    # 파일이 없거나 비어 있으면 None을 반환해서 병합 단계가 안전하게 돌아가게 한다.
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return None
    try:
        return pd.read_csv(path)
    except EmptyDataError:
        return None


def is_cloudflare_block(soup):
    # Cloudflare 차단 페이지는 실제 answer key HTML이 아니므로 따로 분리한다.
    title = soup.title.get_text(" ", strip=True).lower() if soup.title else ""
    whole_text = soup.get_text(" ", strip=True).lower()
    return (
        "attention required" in title
        or "cloudflare" in title
        or "sorry, you have been blocked" in whole_text
        or "cf-error-details" in str(soup)
    )


def extract_candidate_texts(soup):
    # answer key에 가까운 영역을 우선 찾고, 없으면 본문 전체를 후보로 사용한다.
    candidates = []

    root = soup.select_one("div.mw-parser-output")
    if not root:
        return []

    text_all = root.get_text(" ", strip=True)
    if text_all:
        candidates.append(("root_full", text_all))

    # 제목이나 문단에 answer key, answers 같은 표현이 있으면 그 주변 텍스트를 우선 사용한다.
    for tag in root.find_all(["h1", "h2", "h3", "h4", "p", "li", "div", "table"]):
        txt = tag.get_text(" ", strip=True)
        low = txt.lower()
        if any(k in low for k in ["answer key", "answers", "official answers"]):
            block_text = " ".join(
                x.get_text(" ", strip=True)
                for x in [tag] + list(tag.find_all_next(limit=8))
            )
            if block_text:
                candidates.append(("answer_section", block_text))

    return candidates


def score_answer_sequence(nums):
    # 15개 3자리 숫자 시퀀스가 answer key처럼 보이는지 간단히 점수화한다.
    if len(nums) < 15:
        return -1

    seq = nums[:15]
    score = 0

    # AIME 답은 보통 000~999 사이의 3자리 정수 문자열이다.
    if all(re.fullmatch(r"\d{3}", x) for x in seq):
        score += 5

    # 너무 같은 숫자만 반복되면 품질이 낮다고 본다.
    unique_count = len(set(seq))
    score += unique_count

    # 000만 과도하게 반복되면 오탐 가능성이 있어 약간 감점한다.
    score -= seq.count("000")

    return score


def parse_answers(html):
    # answer key 페이지에서 신뢰도 높은 3자리 숫자 답안을 최대 15개 추출한다.
    soup = BeautifulSoup(html, "html.parser")

    if is_cloudflare_block(soup):
        return [], "cloudflare_block"

    candidates = extract_candidate_texts(soup)
    if not candidates:
        return [], "no_root"

    best_answers = []
    best_score = -1
    best_source = ""

    for source_name, text in candidates:
        # AIME 정답은 3자리 정수이므로 정확히 3자리 숫자만 후보로 잡는다.
        nums = re.findall(r"\b\d{3}\b", text)
        score = score_answer_sequence(nums)

        if score > best_score:
            best_score = score
            best_answers = nums[:15]
            best_source = source_name

    if len(best_answers) < 15:
        return best_answers, f"suspect_{best_source}_{len(best_answers)}"

    return best_answers, f"ok_{best_source}_15"


def append_unique(old_df, new_df, key=("exam_name", "problem_no")):
    # 기존 답안 결과와 새 결과를 시험명과 문항 번호 기준으로 합친다.
    if old_df is None or len(old_df) == 0:
        return new_df.copy()
    return pd.concat([old_df, new_df], ignore_index=True).drop_duplicates(
        subset=list(key), keep="last"
    )


def main():
    idx = pd.read_csv(INDEX_CSV)
    rows = []
    logs = []

    print(f"loaded index rows: {len(idx)}")
    print(f"cwd: {os.getcwd()}")
    print(f"index file: {os.path.abspath(INDEX_CSV)}")
    print(f"html dir: {os.path.abspath(HTML_DIR)}")

    # 시험 단위로 answer key를 파싱한다.
    for exam_name in idx["exam_name"].dropna().unique():
        path = os.path.join(HTML_DIR, safe_name(f"{exam_name}_answer_key"))
        html = ""

        # 저장된 answer key HTML이 있으면 그것을 우선 사용한다.
        if os.path.exists(path) and os.path.getsize(path) > 0:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                html = f.read()

        # answer key HTML이 없으면 기록만 남기고 넘어간다.
        if not html:
            logs.append({"exam_name": exam_name, "status": "missing_answer_html"})
            print(f"missing_answer_html: {exam_name}")
            continue

        answers, status = parse_answers(html)

        for i, ans in enumerate(answers, start=1):
            rows.append({
                "exam_name": exam_name,
                "problem_no": i,
                "answer": ans
            })

        logs.append({"exam_name": exam_name, "status": status})
        print(f"{status}: {exam_name}")

    new_df = pd.DataFrame(rows)
    old_df = safe_read_csv(OUT_CSV)
    combined = append_unique(old_df, new_df)
    combined.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    log_df = pd.DataFrame(logs)
    old_log = safe_read_csv(LOG_CSV)
    if old_log is not None:
        log_df = pd.concat([old_log, log_df], ignore_index=True)
    log_df.to_csv(LOG_CSV, index=False, encoding="utf-8-sig")

    print("saved:", OUT_CSV, len(combined))
    print("saved:", LOG_CSV)

    if not log_df.empty:
        print("status counts:")
        print(log_df["status"].value_counts(dropna=False).to_dict())


if __name__ == "__main__":
    main()