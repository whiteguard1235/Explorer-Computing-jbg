# fetch_html_answer_keys.py
import os
import re
import time
import random
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

INDEX_CSV = "data/raw/problem_index.csv"
HTML_DIR = "data/raw/html"
LOG_CSV = "data/interim/fetch_answer_keys_log.csv"
FAILED_CSV = "data/interim/fetch_answer_keys_failed.csv"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
]

def make_session():
    session = requests.Session()
    retry = Retry(
        total=3,
        read=3,
        connect=3,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://artofproblemsolving.com/",
    }

def safe_name(text):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(text)).strip("_")

def answer_key_fname(exam_name):
    return safe_name(exam_name) + "_answer_key.html"

def save_append_csv(path, df, key=None):
    if df is None or len(df) == 0:
        return
    if os.path.exists(path):
        old = pd.read_csv(path)
        df = pd.concat([old, df], ignore_index=True)
    if key and key in df.columns:
        df = df.drop_duplicates(subset=[key], keep="last")
    df.to_csv(path, index=False, encoding="utf-8-sig")

def pick_col(df, candidates):
    for col in candidates:
        if col in df.columns:
            return col
    raise ValueError(f"missing required column. candidates={candidates}, actual={list(df.columns)}")

def main():
    os.makedirs(HTML_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(LOG_CSV), exist_ok=True)

    df = pd.read_csv(INDEX_CSV)
    df.columns = [c.strip().lower() for c in df.columns]

    exam_col = pick_col(df, ["exam_name", "examname"])
    answer_col = pick_col(df, ["answer_key_url", "answerkeyurl"])

    answer_df = (
        df[[exam_col, answer_col]]
        .dropna()
        .drop_duplicates(subset=[exam_col, answer_col])
        .copy()
    )

    session = make_session()
    logs = []
    failed = []
    total = len(answer_df)

    print(f"loaded answer key rows: {total}")
    print(f"using columns: exam={exam_col}, answer={answer_col}")

    for i, row in answer_df.iterrows():
        exam_name = str(row[exam_col]).strip()
        url = str(row[answer_col]).strip()
        path = os.path.join(HTML_DIR, answer_key_fname(exam_name))
        status = None

        if not url:
            status = "empty_url"
            failed.append({"exam_name": exam_name, "url": url, "status": status})
            continue

        if os.path.exists(path) and os.path.getsize(path) > 0:
            status = "exists"
            logs.append({"i": i, "exam_name": exam_name, "status": status, "file": path, "url": url})
            print(f"[{i+1}/{total}] {status}: {exam_name}")
            continue

        time.sleep(random.uniform(3, 7))

        try:
            resp = session.get(url, headers=headers(), timeout=25)
            code = resp.status_code

            if code == 200 and resp.text:
                soup = BeautifulSoup(resp.text, "html.parser")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(str(soup))
                status = "ok"
            else:
                status = f"http_{code}"
                failed.append({"exam_name": exam_name, "url": url, "status": status})

        except Exception as e:
            status = f"error: {e}"
            failed.append({"exam_name": exam_name, "url": url, "status": status})

        logs.append({
            "i": i,
            "exam_name": exam_name,
            "status": status,
            "file": path if status == "ok" else "",
            "url": url,
        })
        print(f"[{i+1}/{total}] {status}: {exam_name}")

    if logs:
        save_append_csv(LOG_CSV, pd.DataFrame(logs))
    if failed:
        save_append_csv(FAILED_CSV, pd.DataFrame(failed), key="url")

    print("saved:", LOG_CSV)
    print("saved:", FAILED_CSV)

if __name__ == "__main__":
    main()