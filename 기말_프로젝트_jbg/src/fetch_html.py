# 문제 목록 CSV를 읽어서 문제 페이지 HTML과 answer key HTML을 내려받는 스크립트.
# 이미 저장된 HTML은 건너뛰고, 실패한 URL은 따로 기록해 재시도할 수 있게 한다.

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
LOG_CSV = "data/interim/fetch_log.csv"
FAILED_CSV = "data/interim/failed_urls.csv"

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

def problem_fname(problem_title):
    return safe_name(problem_title) + ".html"

def answer_key_fname(examname):
    return safe_name(examname) + "_answer_key.html"

def normalize_url(url):
    url = str(url).strip()
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("httpsartofproblemsolving.com"):
        return url.replace("httpsartofproblemsolving.com", "https://artofproblemsolving.com/")
    if url.startswith("httpartofproblemsolving.com"):
        return url.replace("httpartofproblemsolving.com", "http://artofproblemsolving.com/")
    return url

def load_existing_failed():
    if os.path.exists(FAILED_CSV):
        df = pd.read_csv(FAILED_CSV)
        if "url" in df.columns:
            return set(df["url"].dropna().astype(str))
    return set()

def save_append_csv(path, df, key=None):
    if df is None or len(df) == 0:
        return
    if os.path.exists(path):
        old = pd.read_csv(path)
        df = pd.concat([old, df], ignore_index=True)
    if key and key in df.columns:
        df = df.drop_duplicates(subset=[key], keep="last")
    df.to_csv(path, index=False, encoding="utf-8-sig")

def fetch_and_save(session, url, path):
    resp = session.get(url, headers=headers(), timeout=25)
    code = resp.status_code

    if code == 200 and resp.text:
        soup = BeautifulSoup(resp.text, "html.parser")
        with open(path, "w", encoding="utf-8") as f:
            f.write(str(soup))
        return "ok", code

    if code in [403, 429]:
        return f"blocked_{code}", code

    return f"http_{code}", code

def main():
    os.makedirs(HTML_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(LOG_CSV), exist_ok=True)

    df = pd.read_csv(INDEX_CSV)
    df.columns = [c.strip().lower() for c in df.columns]

    session = make_session()
    logs = []
    failed = []
    blocked_count = 0
    existing_failed = load_existing_failed()

    print(f"loaded index rows: {len(df)}")
    print(f"html dir: {os.path.abspath(HTML_DIR)}")

    problem_tasks = []
    for _, row in df.iterrows():
        url = normalize_url(row["problemurl"])
        title = str(row["problemtitle"])
        path = os.path.join(HTML_DIR, problem_fname(title))
        problem_tasks.append({
            "kind": "problem",
            "title": title,
            "url": url,
            "path": path,
        })

    answer_df = (
        df[["examname", "answerkeyurl"]]
        .dropna()
        .drop_duplicates(subset=["examname", "answerkeyurl"])
        .copy()
    )

    answer_tasks = []
    for _, row in answer_df.iterrows():
        examname = str(row["examname"])
        url = normalize_url(row["answerkeyurl"])
        path = os.path.join(HTML_DIR, answer_key_fname(examname))
        answer_tasks.append({
            "kind": "answer_key",
            "title": examname,
            "url": url,
            "path": path,
        })

    tasks = problem_tasks + answer_tasks
    total = len(tasks)

    for i, task in enumerate(tasks, start=1):
        kind = task["kind"]
        title = task["title"]
        url = task["url"]
        path = task["path"]

        if not url:
            status = "empty_url"
            failed.append({"kind": kind, "title": title, "url": url, "status": status})
            logs.append({"i": i, "kind": kind, "title": title, "status": status, "file": "", "url": url})
            continue

        if os.path.exists(path) and os.path.getsize(path) > 0:
            status = "exists"
            logs.append({"i": i, "kind": kind, "title": title, "status": status, "file": path, "url": url})
            print(f"[{i}/{total}] {kind} {status}: {title}")
            continue

        if url in existing_failed:
            status = "skip_failed"
            logs.append({"i": i, "kind": kind, "title": title, "status": status, "file": "", "url": url})
            print(f"[{i}/{total}] {kind} {status}: {title}")
            continue

        time.sleep(random.uniform(8, 15))

        try:
            status, code = fetch_and_save(session, url, path)

            if status == "ok":
                blocked_count = 0
            else:
                failed.append({"kind": kind, "title": title, "url": url, "status": status})
                if code in [403, 429]:
                    blocked_count += 1
                    if blocked_count >= 3:
                        time.sleep(random.uniform(120, 300))
                        blocked_count = 0

        except Exception as e:
            status = f"error: {e}"
            failed.append({"kind": kind, "title": title, "url": url, "status": status})
            time.sleep(random.uniform(5, 10))

        logs.append({
            "i": i,
            "kind": kind,
            "title": title,
            "status": status,
            "file": path if status == "ok" else "",
            "url": url,
        })
        print(f"[{i}/{total}] {kind} {status}: {title}")

        if i % 5 == 0 and logs:
            save_append_csv(LOG_CSV, pd.DataFrame(logs))
            logs = []
        if i % 10 == 0:
            time.sleep(random.uniform(40, 90))

    if logs:
        save_append_csv(LOG_CSV, pd.DataFrame(logs))
    if failed:
        save_append_csv(FAILED_CSV, pd.DataFrame(failed), key="url")

    print("saved:", LOG_CSV)
    print("saved:", FAILED_CSV)

if __name__ == "__main__":
    main()