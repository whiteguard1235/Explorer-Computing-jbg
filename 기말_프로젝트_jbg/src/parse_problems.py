import os
import re
import pandas as pd
from pandas.errors import EmptyDataError
from bs4 import BeautifulSoup, NavigableString, Tag

INDEX_CSV = "data/raw/problem_index.csv"
HTML_DIR = "data/raw/html"
OUT_CSV = "data/interim/problems_parsed.csv"
LOG_CSV = "data/interim/parsing_log.csv"


def safe_name(title):
    # 문제 제목을 파일명으로 바꿀 때 위험한 문자를 언더스코어로 치환한다.
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(title)) + ".html"


def safe_read_csv(path):
    # 파일이 없거나 비어 있으면 None을 반환해서 병합 단계가 안전하게 돌아가게 한다.
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return None
    try:
        return pd.read_csv(path)
    except EmptyDataError:
        return None


def node_to_text(node):
    # HTML 태그를 문자열로 바꿀 때 이미지 alt도 최대한 살린다.
    if isinstance(node, NavigableString):
        return str(node)
    if isinstance(node, Tag):
        if node.name == "img":
            return node.get("alt", "")
        return "".join(node_to_text(child) for child in node.children)
    return ""


def extract_text(tag):
    return " ".join(node_to_text(tag).split()).strip()


def is_cloudflare_block(soup):
    # Cloudflare 차단 페이지는 실제 문제 HTML이 아니므로 따로 분리해서 기록한다.
    title = soup.title.get_text(" ", strip=True).lower() if soup.title else ""
    whole_text = soup.get_text(" ", strip=True).lower()
    return (
        "attention required" in title
        or "cloudflare" in title
        or "sorry, you have been blocked" in whole_text
        or "cf-error-details" in str(soup)
    )


def find_problem_heading(root):
    # 문제 본문 시작 위치를 찾기 위해 heading 태그를 찾는다.
    for h in root.find_all(["h1", "h2", "h3"]):
        txt = h.get_text(" ", strip=True).lower()
        if txt.startswith("problem"):
            return h
    return None


def parse_html(html):
    soup = BeautifulSoup(html, "html.parser")

    # 차단 페이지는 구조가 완전히 다르므로 먼저 걸러낸다.
    if is_cloudflare_block(soup):
        return "", "cloudflare_block"

    root = soup.select_one("div.mw-parser-output")
    if not root:
        return "", "no_root"

    problem_h = find_problem_heading(root)
    if not problem_h:
        return "", "no_problem_heading"

    parts = []
    for sib in problem_h.next_siblings:
        if isinstance(sib, NavigableString):
            continue
        if isinstance(sib, Tag) and sib.name in ["h1", "h2", "h3"]:
            break
        if isinstance(sib, Tag):
            txt = extract_text(sib)
            if txt:
                parts.append(txt)

    text = "\n\n".join(parts).strip()
    return text, "ok" if text else "empty"


def append_unique(old_df, new_df, key="problem_url"):
    # 기존 파싱 결과와 새 결과를 문제 URL 기준으로 합친다.
    if old_df is None or len(old_df) == 0:
        return new_df.copy()
    if key in old_df.columns and key in new_df.columns:
        old_df = old_df[~old_df[key].isin(new_df[key])]
        return pd.concat([old_df, new_df], ignore_index=True).drop_duplicates(subset=[key], keep="last")
    return pd.concat([old_df, new_df], ignore_index=True).drop_duplicates(keep="last")


def main():
    index_df = pd.read_csv(INDEX_CSV)
    rows = []
    logs = []

    print(f"loaded index rows: {len(index_df)}")
    print(f"cwd: {os.getcwd()}")
    print(f"index file: {os.path.abspath(INDEX_CSV)}")
    print(f"html dir: {os.path.abspath(HTML_DIR)}")

    for _, row in index_df.iterrows():
        path = os.path.join(HTML_DIR, safe_name(row["problem_title"]))

        # HTML이 없으면 파싱할 수 없으니 기록만 남긴다.
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            status = "missing_html"
            rows.append({**row.to_dict(), "statement_en": "", "status": status})
            logs.append({"problem_title": row["problem_title"], "status": status, "url": row["problem_url"]})
            print(f"{status}: {row['problem_title']}")
            continue

        with open(path, "r", encoding="utf-8") as f:
            text, status = parse_html(f.read())

        rows.append({**row.to_dict(), "statement_en": text, "status": status})
        logs.append({"problem_title": row["problem_title"], "status": status, "url": row["problem_url"]})
        print(f"{status}: {row['problem_title']}")

    new_df = pd.DataFrame(rows)
    old_df = safe_read_csv(OUT_CSV)
    combined = append_unique(old_df, new_df, key="problem_url")
    combined.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    log_df = pd.DataFrame(logs)
    old_log = safe_read_csv(LOG_CSV)
    if old_log is not None:
        log_df = pd.concat([old_log, log_df], ignore_index=True)
    log_df.to_csv(LOG_CSV, index=False, encoding="utf-8-sig")

    print("saved:", OUT_CSV, len(combined))
    print("saved:", LOG_CSV)

    if not new_df.empty:
        print("status counts:")
        print(new_df["status"].value_counts(dropna=False).to_dict())


if __name__ == "__main__":
    main()