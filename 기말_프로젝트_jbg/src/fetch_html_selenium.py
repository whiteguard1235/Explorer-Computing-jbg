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
LOG_CSV = "data/interim/fetch_log_selenium.csv"
FAILED_CSV = "data/interim/failed_urls_selenium.csv"


def safe_name(title):
    # 문제 제목을 파일명으로 바꿀 때 위험한 문자를 언더스코어로 치환한다.
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


def load_existing_failed():
    # 이전 Selenium 실행에서 실패했던 URL을 읽어와 중복 시도를 줄인다.
    if os.path.exists(FAILED_CSV):
        df = pd.read_csv(FAILED_CSV)
        if "url" in df.columns:
            return set(df["url"].dropna().astype(str))
    return set()


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


def main():
    # 메인 루프는 problem_index를 읽고, Selenium으로 페이지를 열어 HTML을 저장한다.
    os.makedirs(HTML_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(LOG_CSV), exist_ok=True)

    df = pd.read_csv(INDEX_CSV)
    total = len(df)
    logs = []
    failed_rows = []
    blocked_count = 0
    existing_failed = load_existing_failed()

    print(f"loaded index rows: {total}")
    print(f"cwd: {os.getcwd()}")
    print(f"html dir: {os.path.abspath(HTML_DIR)}")
    print(f"log file: {os.path.abspath(LOG_CSV)}")
    print(f"failed file: {os.path.abspath(FAILED_CSV)}")

    driver = make_driver()

    try:
        # 진행 상황을 콘솔과 파일에 동시에 남겨서, 장시간 실행 중에도 상태를 확인할 수 있게 한다.
        for i, row in df.iterrows():
            url = str(row["problem_url"])
            title = str(row["problem_title"])
            path = os.path.join(HTML_DIR, safe_name(title))
            status = None

            # 이미 저장된 HTML이 있어도 Cloudflare 차단본이면 다시 받아야 한다.
            if os.path.exists(path) and os.path.getsize(path) > 0:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    old_html = f.read()
                if not is_cloudflare_html(old_html):
                    status = "exists"
                    logs.append({
                        "i": i,
                        "problem_title": title,
                        "status": status,
                        "file": path,
                        "url": url,
                    })
                    print(f"[{i+1}/{total}] {status}: {title}")
                    if (i + 1) % 5 == 0:
                        append_csv(LOG_CSV, pd.DataFrame(logs))
                        logs = []
                    continue
                else:
                    print(f"[{i+1}/{total}] refetch_cloudflare_html: {title}")

            # 이전 Selenium 실행에서 실패한 URL은 우선 건너뛰어 중복 차단을 줄인다.
            if url in existing_failed:
                status = "skip_failed"
                logs.append({
                    "i": i,
                    "problem_title": title,
                    "status": status,
                    "file": "",
                    "url": url,
                })
                print(f"[{i+1}/{total}] {status}: {title}")
                if (i + 1) % 5 == 0:
                    append_csv(LOG_CSV, pd.DataFrame(logs))
                    logs = []
                continue

            # 너무 빠르게 접근하지 않도록 요청 전 랜덤 대기를 둔다.
            time.sleep(random.uniform(8, 20))

            try:
                # 브라우저로 실제 페이지를 열고 body가 뜰 때까지 기다린다.
                driver.get(url)
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )

                html = driver.page_source

                # Cloudflare 차단본이면 저장하지 않고 실패로 기록해서 다시 시도할 수 있게 한다.
                if is_cloudflare_html(html):
                    status = "cloudflare_block_selenium"
                    failed_rows.append({
                        "problem_title": title,
                        "url": url,
                        "status": status,
                    })
                    blocked_count += 1
                # 일정 길이 이상의 HTML이 확인되면 정상 저장으로 본다.
                elif html and len(html) > 1000:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(html)
                    status = "ok_selenium"
                    blocked_count = 0
                else:
                    status = "empty_html_selenium"
                    failed_rows.append({
                        "problem_title": title,
                        "url": url,
                        "status": status,
                    })

            except TimeoutException as e:
                status = f"timeout_selenium: {e}"
                failed_rows.append({
                    "problem_title": title,
                    "url": url,
                    "status": status,
                })
                blocked_count += 1
                time.sleep(random.uniform(30, 90))

            except WebDriverException as e:
                status = f"webdriver_error: {e}"
                failed_rows.append({
                    "problem_title": title,
                    "url": url,
                    "status": status,
                })
                blocked_count += 1
                time.sleep(random.uniform(30, 90))

            except Exception as e:
                status = f"error_selenium: {e}"
                failed_rows.append({
                    "problem_title": title,
                    "url": url,
                    "status": status,
                })
                blocked_count += 1
                time.sleep(random.uniform(30, 90))

            logs.append({
                "i": i,
                "problem_title": title,
                "status": status,
                "file": path if status == "ok_selenium" else "",
                "url": url,
            })
            print(f"[{i+1}/{total}] {status}: {title}")

            # 5개 단위로 로그를 저장하고, 실패 목록도 같은 주기로 즉시 저장한다.
            if (i + 1) % 5 == 0 and logs:
                append_csv(LOG_CSV, pd.DataFrame(logs))
                logs = []
            if failed_rows and ((i + 1) % 5 == 0 or len(failed_rows) >= 5):
                append_csv(FAILED_CSV, pd.DataFrame(failed_rows), key="url")
                print(f"saved failed rows: {len(failed_rows)}")
                failed_rows = []

            # 실패가 연속될 때는 브라우저 차단 가능성을 낮추기 위해 더 길게 쉰다.
            if blocked_count >= 3:
                cool_down = random.uniform(300, 900)
                print(f"cool down: sleeping {cool_down:.0f} seconds after repeated failures")
                time.sleep(cool_down)
                blocked_count = 0

            # 오래 돌릴 때는 주기적으로 긴 휴식을 넣어 과도한 접근을 피한다.
            if (i + 1) % 10 == 0:
                pause = random.uniform(60, 180)
                print(f"batch pause: sleeping {pause:.0f} seconds")
                time.sleep(pause)

        # 루프가 끝났을 때 남아 있는 로그와 실패분을 한 번 더 저장한다.
        if logs:
            append_csv(LOG_CSV, pd.DataFrame(logs))
        if failed_rows:
            append_csv(FAILED_CSV, pd.DataFrame(failed_rows), key="url")
            print(f"saved failed rows: {len(failed_rows)}")

    finally:
        driver.quit()

    print("saved:", LOG_CSV)
    print("saved:", FAILED_CSV)


if __name__ == "__main__":
    main()