# retry_answer_keys_selenium.py
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

FAILED_CSV = "data/interim/fetch_answer_keys_failed.csv"
HTML_DIR = "data/raw/html"
LOG_CSV = "data/interim/retry_answer_keys_log.csv"
STILL_FAILED_CSV = "data/interim/retry_answer_keys_failed.csv"

def safe_name(text):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(text)).strip("_")

def answer_key_fname(exam_name):
    return safe_name(exam_name) + "_answer_key.html"

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
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(45)
    return driver

def main():
    os.makedirs(HTML_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(LOG_CSV), exist_ok=True)

    df = pd.read_csv(FAILED_CSV)
    df.columns = [c.strip().lower() for c in df.columns]

    total = len(df)
    logs = []
    still_failed = []

    print(f"loaded failed rows: {total}")
    if total == 0:
        print("no failed rows")
        return

    driver = make_driver()

    try:
        for i, row in df.iterrows():
            exam_name = str(row["exam_name"]).strip()
            url = str(row["url"]).strip()
            path = os.path.join(HTML_DIR, answer_key_fname(exam_name))

            if os.path.exists(path) and os.path.getsize(path) > 0:
                status = "exists_after_retry"
                logs.append({"i": i, "exam_name": exam_name, "status": status, "file": path, "url": url})
                print(f"[{i+1}/{total}] {status}: {exam_name}")
                continue

            time.sleep(random.uniform(8, 18))

            try:
                driver.get(url)
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                time.sleep(6)

                html = driver.page_source

                if html and len(html) > 1000:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(html)
                    status = "ok_selenium"
                else:
                    status = "empty_html_selenium"
                    still_failed.append({"exam_name": exam_name, "url": url, "status": status})

            except TimeoutException as e:
                status = f"timeout_selenium: {e}"
                still_failed.append({"exam_name": exam_name, "url": url, "status": status})

            except WebDriverException as e:
                status = f"webdriver_error: {e}"
                still_failed.append({"exam_name": exam_name, "url": url, "status": status})

            except Exception as e:
                status = f"error_selenium: {e}"
                still_failed.append({"exam_name": exam_name, "url": url, "status": status})

            logs.append({
                "i": i,
                "exam_name": exam_name,
                "status": status,
                "file": path if status == "ok_selenium" else "",
                "url": url,
            })
            print(f"[{i+1}/{total}] {status}: {exam_name}")

            if (i + 1) % 5 == 0 and logs:
                append_csv(LOG_CSV, pd.DataFrame(logs))
                logs = []
            if still_failed and ((i + 1) % 5 == 0 or len(still_failed) >= 5):
                append_csv(STILL_FAILED_CSV, pd.DataFrame(still_failed), key="url")
                still_failed = []

        if logs:
            append_csv(LOG_CSV, pd.DataFrame(logs))
        if still_failed:
            append_csv(STILL_FAILED_CSV, pd.DataFrame(still_failed), key="url")

    finally:
        driver.quit()

    print("saved:", LOG_CSV)
    print("saved:", STILL_FAILED_CSV)

if __name__ == "__main__":
    main()