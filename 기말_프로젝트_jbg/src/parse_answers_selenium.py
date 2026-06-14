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

INDEX_CSV = "data/raw/problem_index.csv"
HTML_DIR = "data/raw/html"
LOG_CSV = "data/interim/fetch_answers_log_selenium.csv"
FAILED_CSV = "data/interim/failed_answer_urls_selenium.csv"


def safe_name(title):
    # 파일명으로 쓰기 어려운 문자는 언더스코어로 바꾼다.
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(title)) + ".html"


def append_csv(path, df, key=None):
    # 기존 파일이 있으면 이어 붙이고, 필요하면 key 기준으로 마지막 상태만 남긴다.
    if df is None or len(df) == 0:
        return
    if os.path.exists(path):
        old = pd.read_csv(path)
        df = pd.concat([old, df], ignore_index=True)
    if key and key in df.columns:
        df = df.drop_duplicates(subset=[key], keep="last")
    df.to_csv(path, index=False, encoding="utf-8-sig")


def is_cloudflare_html(html):
    # Cloudflare 차단 페이지인지 문자열 기준으로 빠르게 확인한다.
    if not html:
        return False
    low = html.lower()
    return (
        "attention required! | cloudflare" in low
        or "sorry, you have been blocked" in low
        or "cf-error-details" in low
    )


def make_driver():
    # headless Chrome 브라우저를 구성한다.
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


def build_answer_index(df):
    # problem_index에서 시험별 answer_key_url을 하나씩만 뽑아 answer key 전용 인덱스를 만든다.
    need_cols = ["exam_name", "answer_key_url"]
    for col in need_cols:
        if col not in df.columns:
            df[col] = ""

    ans = df[["exam_name", "answer_key_url"]].dropna(subset=["exam_name"]).copy()
    ans["answer_key_url"] = ans["answer_key_url"].fillna("").astype(str)
    ans = ans[ans["answer_key_url"].str.len() > 0].copy()
    ans = ans.drop_duplicates(subset=["exam_name"], keep="first")
    return ans


def main():
    # 시험별 answer key 페이지를 Selenium으로 열어 HTML 파일로 저장한다.
    os.makedirs(HTML_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(LOG_CSV), exist_ok=True)

    idx = pd.read_csv(INDEX_CSV)
    ans_idx = build_answer_index(idx)
    total = len(ans_idx)
    logs = []
    failed_rows = []
    blocked_count = 0

    print(f"loaded exams with answer_key_url: {total}")
    print(f"cwd: {os.getcwd()}")
    print(f"html dir: {os.path.abspath(HTML_DIR)}")
    print(f"log file: {os.path.abspath(LOG_CSV)}")
    print(f"failed file: {os.path.abspath(FAILED_CSV)}")

    driver = make_driver()

    try:
        for i, row in ans_idx.iterrows():
            exam_name = str(row["exam_name"])
            url = str(row["answer_key_url"])
            path = os.path.join(HTML_DIR, safe_name(f"{exam_name}_answer_key"))
            status = None

            # 기존 answer key HTML이 정상 페이지면 다시 받지 않는다.
            if os.path.exists(path) and os.path.getsize(path) > 0:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    old_html = f.read()
                if not is_cloudflare_html(old_html):
                    status = "exists"
                    logs.append({"exam_name": exam_name, "status": status, "file": path, "url": url})
                    print(f"[{i+1}/{total}] {status}: {exam_name}")
                    if (i + 1) % 5 == 0:
                        append_csv(LOG_CSV, pd.DataFrame(logs), key="url")
                        logs = []
                    continue
                else:
                    print(f"[{i+1}/{total}] refetch_cloudflare_html: {exam_name}")

            # 너무 빠른 연속 접근을 피하기 위해 요청 전에 랜덤 대기를 둔다.
            time.sleep(random.uniform(8, 20))

            try:
                # 브라우저로 answer key 페이지를 열고 body가 뜰 때까지 기다린다.
                driver.get(url)
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )

                html = driver.page_source

                if is_cloudflare_html(html):
                    status = "cloudflare_block_selenium"
                    failed_rows.append({"exam_name": exam_name, "url": url, "status": status})
                    blocked_count += 1
                elif html and len(html) > 1000:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(html)
                    status = "ok_selenium"
                    blocked_count = 0
                else:
                    status = "empty_html_selenium"
                    failed_rows.append({"exam_name": exam_name, "url": url, "status": status})

            except TimeoutException as e:
                status = f"timeout_selenium: {e}"
                failed_rows.append({"exam_name": exam_name, "url": url, "status": status})
                blocked_count += 1
                time.sleep(random.uniform(30, 90))

            except WebDriverException as e:
                status = f"webdriver_error: {e}"
                failed_rows.append({"exam_name": exam_name, "url": url, "status": status})
                blocked_count += 1
                time.sleep(random.uniform(30, 90))

            except Exception as e:
                status = f"error_selenium: {e}"
                failed_rows.append({"exam_name": exam_name, "url": url, "status": status})
                blocked_count += 1
                time.sleep(random.uniform(30, 90))

            logs.append({"exam_name": exam_name, "status": status, "file": path if status == "ok_selenium" else "", "url": url})
            print(f"[{i+1}/{total}] {status}: {exam_name}")

            # 5개 단위로 로그와 실패 목록을 중간 저장한다.
            if (i + 1) % 5 == 0 and logs:
                append_csv(LOG_CSV, pd.DataFrame(logs), key="url")
                logs = []
            if failed_rows and ((i + 1) % 5 == 0 or len(failed_rows) >= 5):
                append_csv(FAILED_CSV, pd.DataFrame(failed_rows), key="url")
                print(f"saved failed answer rows: {len(failed_rows)}")
                failed_rows = []

            # 실패가 연속될 때는 더 길게 쉬어 차단 가능성을 낮춘다.
            if blocked_count >= 3:
                cool_down = random.uniform(300, 900)
                print(f"cool down: sleeping {cool_down:.0f} seconds after repeated failures")
                time.sleep(cool_down)
                blocked_count = 0

            # 오래 돌릴 때는 주기적으로 휴식을 넣는다.
            if (i + 1) % 10 == 0:
                pause = random.uniform(60, 180)
                print(f"batch pause: sleeping {pause:.0f} seconds")
                time.sleep(pause)

        # 루프 종료 후 남은 로그와 실패분을 마지막으로 저장한다.
        if logs:
            append_csv(LOG_CSV, pd.DataFrame(logs), key="url")
        if failed_rows:
            append_csv(FAILED_CSV, pd.DataFrame(failed_rows), key="url")
            print(f"saved failed answer rows: {len(failed_rows)}")

    finally:
        driver.quit()

    print("saved:", LOG_CSV)
    print("saved:", FAILED_CSV)


if __name__ == "__main__":
    main()