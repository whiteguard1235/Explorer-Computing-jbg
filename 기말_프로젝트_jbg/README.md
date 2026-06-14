# Math Contest Problem Learning App

경시 수학(AIME) 문제를 기반으로, 기출을 탐색하고 연습 시험/타임어택/피드백까지 한 번에 할 수 있는 학습 보조 웹앱입니다.

---

## 프로젝트 개요

AoPS Wiki의 경시수학 문제를 수집하고, HTML 원문을 저장한 뒤, 문제 본문을 파싱하여 학습용 데이터셋을 만드는 프로젝트입니다.  
최종적으로 생성된 데이터셋을 바탕으로 Streamlit 앱을 제공하여, 사용자가 브라우저에서 바로 문제를 풀고 분석할 수 있도록 합니다.

---

## 주요 기능 (Streamlit 앱)

- **Past Problems**  
  연도, 시험 종류, 문항 번호를 선택해 개별 기출 문제와 원문 링크를 확인합니다.

- **Custom Test**  
  토픽과 난이도, 문항 수를 골라 맞춤 시험지를 만들고, 제출 후 정답/오답, 토픽/난이도별 정답률, 점수를 확인합니다.  
  점수는 `difficulty × 10` 배점으로 계산됩니다.

- **Time Attack**  
  한 문제씩 시간 제한을 두고 푸는 모드입니다.  
  - 정답: 걸린 시간에 따라 `Excellent / Nice / So-So / Little Slow / Too Slow` 등급 부여  
  - 오답: 시간과 관계없이 `Wrong`  
  - 포기: `Give Up`  
  결과는 히스토리에 함께 저장됩니다.

- **Feedback & History**  
  최근 Custom Test / Time Attack 결과에 대해  
  - 토픽/난이도별 정답률과 점수  
  - 맞은 문제(초록), 틀린 문제(빨강) 표  
  를 보여주고, 모든 플레이 기록을 `data/history/history.csv`에 누적 저장합니다.

---

## 폴더 설명

- `data/raw/`: 원본 수집 데이터와 HTML 파일 - HTML 파일은 너무 많아, 최종폴더에는 생략.  
- `data/interim/`: 파싱 중간 결과  
- `data/processed/`: Streamlit 앱에서 사용할 최종 데이터셋 (`problems_final.csv`)  
- `data/history/`: 웹앱 실행 중 생성되는 플레이 히스토리(`history.csv`)  
- `src/`: 수집, 파싱, 정제 스크립트  
- `app.py`: Streamlit 앱 (배포/실행 진입점)

---

## 데이터 파이프라인 실행 순서

1. `python src/crawl_index.py`  
2. `python src/fetch_html.py`  
3. `python src/parse_problems.py`  
4. `python src/parse_answers.py`  
5. `python src/build_dataset.py`  
6. `streamlit run app.py`  (웹앱 실행)

---

## 설치 및 실행

```bash
# 의존성 설치
pip install -r requirements.txt

# 로컬에서 앱 실행
streamlit run app.py
```