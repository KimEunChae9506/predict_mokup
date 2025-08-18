import streamlit as st
import requests
from datetime import date, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import traceback

# fastapi 로 생성한 LLM 답변 받아 오는 endpoint. (https://predict-mokup.onrender.com == http://localhost:8001)
# 가중치 예측 endpoint
API_URL = "https://predict-mokup.onrender.com/predict"
# AI 모델별 예측 endpoint
AI_API_URL = "https://predict-mokup.onrender.com/ai-predict"

# 📅 오늘 날짜 계산
today = date.today()
if today.weekday() == 0:
    today += timedelta(days=1)
today_str = today.strftime("%Y-%m-%d")

# ⚙️ 세션 초기화 함수
def init_session_state():
    keys = ["default_report", "custom_report", "ai_stat_report", "ai_site_report", "ai_trend_report",
            "default_json", "custom_json", "ai_stat_json", "ai_site_json", "ai_trend_json"
            ]
    for k in keys:
        st.session_state.setdefault(k, None)

    weight_keys = ["pitcher", "recent_form", "home_advantage", "ops", "defense", "pythagorean",
                   "weather", "bullpen", "odds", "rest_travel", "log5", "insight"]
    defaults = [20, 15, 10, 12, 8, 10, 7, 6, 4, 5, 5, 10]
    for k, v in zip(weight_keys, defaults):
        st.session_state.setdefault(k, v)

    st.session_state.setdefault('normalized_weights', {})

init_session_state()

# 경기 목록 크롤링 (10시간 캐시)
@st.cache_data(ttl=36000)
def fetch_kbo_matches():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-dev-shm-usage')  # 메모리 부족 방지
    options.add_argument('--no-sandbox')

    driver = webdriver.Chrome(options=options)
    driver.get("https://m.sports.naver.com/kbaseball/schedule/index?date=" + today_str)
    html = driver.page_source
    soup = BeautifulSoup(html, 'html.parser')
    team_names = [m.text.strip() for m in soup.select('strong.MatchBoxHeadToHeadArea_team__40JQL')]
    driver.quit()
    return [{"team1": team_names[i], "team2": team_names[i+1]} for i in range(0, len(team_names), 2)]

# API 요청 함수
def post_prediction(url, payload, session_key):
    try:
        res = requests.post(url, json=payload, verify=False)
        res.raise_for_status()
        st.session_state[session_key] = res.json().get("report", "❌ 결과 없음")
    except requests.exceptions.HTTPError as e:
        status = res.status_code if 'res' in locals() else "No response"
        headers = res.headers if 'res' in locals() else {}
        body = res.text if 'res' in locals() else ""

        print("🔥 Perplexity API 호출 실패")
        print("Status:", status)
        print("Headers:", headers)
        print("Body:", body)
        st.session_state[session_key] = f"❌ 서버 오류\n\n```\n{headers}\n```"


# 가중치 정규화
def normalize_weights(keys):
    total = sum(st.session_state[k] for k in keys)
    if total == 0: return {k: 0 for k in keys}
    remain = 100
    result = {}
    for k in keys[:-1]:
        val = round(st.session_state[k] / total * 100 / 5) * 5
        result[k] = val
        remain -= val
    result[keys[-1]] = max(remain, 0)
    return result

# UI: 경기 선택
st.title("📅 " + today_str + " 의 KBO 경기")
matches = fetch_kbo_matches()

if not matches:
    st.error("오늘 경기 정보가 없습니다.")
else:
    selected_match = None
    for i, m in enumerate(matches):
        if st.button(f"{m['team1']} VS {m['team2']}", key=f"btn_{i}"):
            st.session_state['team1'], st.session_state['team2'] = m['team1'], m['team2']

team1 = st.session_state.get("team1")
team2 = st.session_state.get("team2")

# UI: 기본 예측
st.title("기본 가중치 기반 예측")
if st.button("기본 가중치로 예측하기"):
    if not team1 or not team2 or team1 == team2:
        st.warning("예측할 경기를 선택해주세요.")
    else:
        post_prediction(API_URL, {"team": f"{team1},{team2}", "mode": "default", "returnType": "report"}, "default_report")

if st.button("기본 가중치로 예측하기 - 승률 JSON 리턴"):
    if not team1 or not team2 or team1 == team2:
        st.warning("예측할 경기를 선택해주세요.")
    else:
        post_prediction(API_URL, {"team": f"{team1},{team2}", "mode": "default", "returnType": "json"}, "default_json")

# UI: 커스텀 가중치 슬라이더
st.title("커스텀 가중치 기반 예측")
st.markdown("예측 요소 가중치를 조정하세요 (합 100%)")
weight_keys = ["pitcher", "recent_form", "home_advantage", "ops", "defense", "pythagorean",
               "weather", "bullpen", "odds", "rest_travel", "log5", "insight"]
labels = [
    "1. 선발투수", "2. 최근 폼", "3. 홈구장", "4. 타격력", "5. 수비력", "6. 기대승률",
    "7. 날씨", "8. 불펜력", "9. 배당", "10. 이동거리/휴식", "11. Log5 매치업", "12. 유튜버 인사이트"
]
for k, l in zip(weight_keys, labels):
    st.number_input(l, min_value=0, max_value=100, step=5, key=k)

if st.button("가중치 정규화"):
    norm = normalize_weights(weight_keys)
    st.session_state.normalized_weights = norm
    for k in weight_keys:
        st.session_state[k] = norm[k]
    st.rerun()

# 커스텀 예측 실행
if st.button("커스텀 가중치로 예측하기"):
    if not team1 or not team2 or team1 == team2:
        st.warning("예측할 경기를 선택해주세요.")
    else:
        weights = {k: st.session_state[k] for k in weight_keys}
        post_prediction(API_URL, {"team": f"{team1},{team2}", "mode": "custom", "weights": weights, "returnType": "report"}, "custom_report")

if st.button("커스텀 가중치로 예측하기 - 승률 JSON 리턴"):
    if not team1 or not team2 or team1 == team2:
        st.warning("예측할 경기를 선택해주세요.")
    else:
        weights = {k: st.session_state[k] for k in weight_keys}
        post_prediction(API_URL, {"team": f"{team1},{team2}", "mode": "custom", "weights": weights, "returnType": "json"}, "custom_json")

# UI: AI 모델들 예측
st.title("🧠 AI 모델 기반 예측")
ai_modes = [("AI#1 통계", "stat", "ai_stat_report"),
            ("AI#2 현장", "site", "ai_site_report"),
            ("AI#3 트렌드", "trend", "ai_trend_report")]

for label, mode, session_key in ai_modes:
    if st.button(label):
        if not team1 or not team2 or team1 == team2:
            st.warning("예측할 경기를 선택해주세요.")
        else:
            post_prediction(AI_API_URL, {"team": f"{team1},{team2}", "mode": mode, "returnType": "report"}, session_key)

ai_modes_json = [("AI#1 통계 - JSON", "stat", "ai_stat_json"),
            ("AI#2 현장 - JSON", "site", "ai_site_json"),
            ("AI#3 트렌드 - JSON", "trend", "ai_trend_json")]

for label, mode, session_key in ai_modes_json:
    if st.button(label):
        if not team1 or not team2 or team1 == team2:
            st.warning("예측할 경기를 선택해주세요.")
        else:
            post_prediction(AI_API_URL, {"team": f"{team1},{team2}", "mode": mode, "returnType": "json"}, session_key)

# 예측 결과 출력
def show_result(title, session_key):
    result = st.session_state.get(session_key)
    if result:
        st.markdown("---")
        st.subheader(title)
        st.markdown(result, unsafe_allow_html=True)

show_result("기본 예측 결과", "default_report")
show_result("기본 예측 결과 -JSON", "default_json")
show_result("커스텀 예측 결과", "custom_report")
show_result("커스텀 예측 결과 -JSON", "custom_json")
show_result("AI#1 통계 예측", "ai_stat_report")
show_result("AI#1 통계 예측 -JSON", "ai_stat_json")
show_result("AI#2 현장 예측", "ai_site_report")
show_result("AI#2 현장 예측 -JSON", "ai_site_json")
show_result("AI#3 트렌드 예측", "ai_trend_report")
show_result("AI#3 트렌드 예측 -JSON", "ai_trend_json")
