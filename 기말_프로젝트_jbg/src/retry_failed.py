# 실패한 URL을 Selenium으로 재시도해서 문제 HTML과 answer key HTML을 저장한다.

import os
import re
import time
import random
import pandas as pd

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

FAILED_CSV = "data/interim/failed_urls.csv"
HTML_DIR = "data/raw/html"
RETRY_LOG_CSV = "data/interim/retry_log.csv"
RETRY_FAILED_CSV = "data/interim/retry_failed_urls.csv"

def safe_name(text):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(text)).strip("_")

def make_fname(kind, title):
    if kind == "answer_key":
        return safe_name(title) + "_answer_key.html"
    return safe_name(title) + ".html"

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

def append_csv(path, df, key=None):
    if df is None or len(df) == 0:
        return
    if os.path.exists(path):
        old = pd.read_csv(path)
        df = pd.concat([old, df], ignore_index=True)
    if key and key in df.columns:
        df = df.drop_duplicates(subset=[key], keep="last")
    df.to_csv(path, index=False, encoding="utf-8-sig")

def make_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1400,2000")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--lang=en-US")
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(45)
    return driver

def load_failed_rows():
    if not os.path.exists(FAILED_CSV):
        return pd.DataFrame(columns=["kind", "title", "url", "status"])
    df = pd.read_csv(FAILED_CSV)
    need_cols = ["kind", "title", "url", "status"]
    for col in need_cols:
        if col not in df.columns:
            df[col] = ""
    return df[need_cols].dropna(subset=["url"])

def main():
    os.makedirs(HTML_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(RETRY_LOG_CSV), exist_ok=True)

    df = load_failed_rows()
    total = len(df)
    logs = []
    still_failed = []

    print(f"loaded failed rows: {total}")
    if total == 0:
        print("no failed rows to retry")
        return

    driver = make_driver()

    try:
        for i, row in df.iterrows():
            kind = str(row["kind"])
            title = str(row["title"])
            url = normalize_url(row["url"])
            prev_status = str(row["status"])
            path = os.path.join(HTML_DIR, make_fname(kind, title))

            if os.path.exists(path) and os.path.getsize(path) > 0:
                status = "exists_after_retry"
                logs.append({
                    "i": i,
                    "kind": kind,
                    "title": title,
                    "status": status,
                    "prev_status": prev_status,
                    "file": path,
                    "url": url,
                })
                print(f"[{i+1}/{total}] {kind} {status}: {title}")
                continue

            time.sleep(random.uniform(8, 20))

            try:
                driver.get(url)
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                html = driver.page_source

                if html and len(html) > 1000:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(html)
                    status = "ok_selenium"
                else:
                    status = "empty_html_selenium"
                    still_failed.append({
                        "kind": kind,
                        "title": title,
                        "url": url,
                        "status": status,
                        "prev_status": prev_status,
                    })

            except TimeoutException as e:
                status = f"timeout_selenium: {e}"
                still_failed.append({
                    "kind": kind,
                    "title": title,
                    "url": url,
                    "status": status,
                    "prev_status": prev_status,
                })
                time.sleep(random.uniform(30, 90))

            except WebDriverException as e:
                status = f"webdriver_error: {e}"
                still_failed.append({
                    "kind": kind,
                    "title": title,
                    "url": url,
                    "status": status,
                    "prev_status": prev_status,
                })
                time.sleep(random.uniform(30, 90))

            except Exception as e:
                status = f"error_selenium: {e}"
                still_failed.append({
                    "kind": kind,
                    "title": title,
                    "url": url,
                    "status": status,
                    "prev_status": prev_status,
                })
                time.sleep(random.uniform(30, 90))

            logs.append({
                "i": i,
                "kind": kind,
                "title": title,
                "status": status,
                "prev_status": prev_status,
                "file": path if status == "ok_selenium" else "",
                "url": url,
            })
            print(f"[{i+1}/{total}] {kind} {status}: {title}")

            if (i + 1) % 5 == 0 and logs:
                append_csv(RETRY_LOG_CSV, pd.DataFrame(logs))
                logs = []
            if still_failed and ((i + 1) % 5 == 0 or len(still_failed) >= 5):
                append_csv(RETRY_FAILED_CSV, pd.DataFrame(still_failed), key="url")
                still_failed = []

            if (i + 1) % 10 == 0:
                time.sleep(random.uniform(60, 180))

        if logs:
            append_csv(RETRY_LOG_CSV, pd.DataFrame(logs))
        if still_failed:
            append_csv(RETRY_FAILED_CSV, pd.DataFrame(still_failed), key="url")

    finally:
        driver.quit()

    print("saved:", RETRY_LOG_CSV)
    print("saved:", RETRY_FAILED_CSV)

if __name__ == "__main__":
    main()