import pandas as pd

rows = []
for year in [2015]:
    for exam_type in ["AIME I", "AIME II"]:
        exam_slug = exam_type.replace(" ", "_")
        for problem_no in range(1, 16):
            problem_url = f"https://artofproblemsolving.com/wiki/index.php/{year}_{exam_slug}_Problems/Problem_{problem_no}"
            answer_key_url = f"https://artofproblemsolving.com/wiki/index.php/{year}_{exam_slug}_Answer_Key"
            rows.append({
                "year": year,
                "exam_type": exam_type,
                "exam_name": f"{year} {exam_type}",
                "problem_no": problem_no,
                "problem_title": f"{year} {exam_type} Problem {problem_no}",
                "problem_url": problem_url,
                "answer_key_url": answer_key_url,
                "source": "AoPS Wiki"
            })

df = pd.DataFrame(rows)
df.to_csv("data/raw/problem_index.csv", index=False, encoding="utf-8-sig")
print("saved:", len(df))