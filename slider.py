import streamlit as st
import requests
import traceback
from datetime import date, timedelta

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup

API_URL = "http://localhost:8001/predict"  # customLLM.py에서 FastAPI 띄운 주소 예시
AI_API_URL = "http://localhost:8001/ai-predict"  # customLLM.py에서 FastAPI 띄운 주소 예시

today = date.today()
if today.weekday() == 0:  # 월요일
    tomorrow = today + timedelta(days=1)
    today_str = tomorrow.strftime("%Y-%m-%d")
else:
    today_str = today.strftime("%Y-%m-%d")


@st.cache_data(ttl=36000)
def fetch_kbo_matches():
    options = Options()
    options.add_argument("--headless")
    driver = webdriver.Chrome(options=options)
    driver.get("https://m.sports.naver.com/kbaseball/schedule/index?date=" + today_str)

    html = driver.page_source
    soup = BeautifulSoup(html, 'html.parser')

    # 팀 이름만 추출
    team_names = [m.text.strip() for m in soup.select('strong.MatchBoxHeadToHeadArea_team__40JQL')]

    # 두 개씩 묶어서 dict 만들기
    match_list = []
    for i in range(0, len(team_names), 2):
        match = {
            'team1': team_names[i],
            'team2': team_names[i + 1]
        }
        match_list.append(match)

    driver.quit()
    return match_list

# 🏁 앱 시작
st.title("📅 " + today_str + " 의 KBO 경기")

match_list = fetch_kbo_matches()

# 클릭된 팀 정보 저장 변수
# Debug: 리스트 확인
if not match_list:
    st.error("오늘 경기 정보가 없습니다. (match_list가 비어 있음)")
else:
    st.success(f"{len(match_list)}개의 경기를 불러왔습니다.")

    for i, match in enumerate(match_list):
        label = f"{match['team1']} VS {match['team2']}"
        if st.button(label, key=f"match_{i}"):
            st.session_state['team1'] = match['team1']
            st.session_state['team2'] = match['team2']

# 세션 상태에서 team1, team2 꺼내기
team1 = st.session_state.get('team1')
team2 = st.session_state.get('team2')


# 세션 상태에 저장
if "default_report" not in st.session_state:
    st.session_state["default_report"] = None
if "custom_report" not in st.session_state:
    st.session_state["custom_report"] = None
if "ai_stat_report" not in st.session_state:
    st.session_state["ai_stat_report"] = None
if "ai_site_report" not in st.session_state:
    st.session_state["ai_site_report"] = None
if "ai_trend_report" not in st.session_state:
    st.session_state["ai_trend_report"] = None

st.title("기본 가중치 기반 야구 승률 예측")


if st.button("기본 가중치로 승률 예측하기", key="btn_default"):
    if team1 == team2:
        st.warning("예측할 경기를 선택해주세요.")
    else:
        payload = {"team": f"{team1},{team2}", "mode": "default"}
        try:
            response = requests.post(API_URL, json=payload, verify=False)
            response.raise_for_status()
            data = response.json()
            st.session_state["default_report"] = data.get("report", "보고서를 받지 못했습니다.")
        except Exception as e:
            st.session_state["default_report"] = f"API 요청 오류: {e}"



st.title("커스텀 가중치 기반 야구 승률 예측")

st.markdown("12개 예측 요소 가중치를 조정하세요 (합 100%)")

# 키와 기본값 정의
all_keys = ["pitcher", "recent_form", "home_advantage", "ops", "defense", "pythagorean", "weather", "bullpen", "odds",
            "rest_travel", "log5", "insight"]
defaults = [20, 15, 10, 12, 8, 10, 7, 6, 4, 5, 5, 10]

labels = [
    "1. 선발투수 ERA/FIP/WHIP",
    "2. 최근 10경기 폼 (득실점, 승–패 흐름)",
    "3. 홈구장 + Park Factors",
    "4. 타격력 (wOBA/OPS)",
    "5. 수비력 (DRS/수비율)",
    "6. Pythagorean 기대승률",
    "7. 날씨/환경 (온도·습도·바람)",
    "8. 불펜력 (중간 + 마무리 ERA/FIP/WHIP)",
    "9. 배당/오즈",
    "10. 이동거리 및 휴식",
    "11. 투수‑타자 매치업 (Log5)",
    "12. 야구 유튜버 예측 인사이트"
]

# 1. session_state 초기화
for k, v in zip(all_keys, defaults):
    if k not in st.session_state:
        st.session_state[k] = v

# 정규화된 값들을 저장할 별도 키 초기화
if 'normalized_weights' not in st.session_state:
    st.session_state.normalized_weights = {}


# 2. 정규화 함수
def normalize_weights():
    total = sum(st.session_state[k] for k in all_keys)
    if total == 0:
        return {k: 0 for k in all_keys}

    result = {}
    remain = 100
    # 마지막 키에 나머지 할당하기 위해 나머지 모두 계산
    for k in all_keys[:-1]:
        val = round(st.session_state[k] / total * 100 / 5) * 5
        result[k] = val
        remain -= val
    # 마지막 요소에 나머지값 할당
    result[all_keys[-1]] = max(remain, 0)
    return result

# 3. number_input 위젯 생성
for k, label in zip(all_keys, labels):
    st.number_input(
        label,
        min_value=0,
        max_value=100,
        value=st.session_state[k],
        step=5,
        key=k
    )

# 4. 가중치 합 출력
weights = {k: st.session_state[k] for k in all_keys}
total_weight = sum(weights.values())
#st.markdown(f"**가중치 합계: {total_weight}**")

# 정규화 상태 표시
#if total_weight == 100:
#    st.success("✅ 가중치 합이 100입니다!")
#elif total_weight > 100:
#    st.warning(f"⚠️ 가중치 합이 100을 초과합니다 (+{total_weight - 100})")
#else:
#    st.info(f"ℹ️ 가중치 합이 100보다 작습니다 (-{100 - total_weight})")

# 5. 버튼이 클릭되었는지 확인
normalize_clicked = st.button("합을 100으로 자동 정규화")

if normalize_clicked:
    # 정규화된 값들을 계산하고 저장
    normalized = normalize_weights()
    st.session_state.normalized_weights = normalized

    # 각 session_state 값을 업데이트
    for k in all_keys:
        st.session_state[k] = normalized[k]

    # 앱 재실행
    st.rerun()


# 총합 계산
total = sum(st.session_state[k] for k in all_keys)

#st.markdown(f"**✅ weights: {weights}")
#st.markdown(f"**✅ 합계: {total:.0f}% (항상 100% 유지됨)**")

# 요약 출력
if total > 0:
    st.markdown("### 📊 현재 설정된 가중치")
    #for k in all_keys:
        #st.write(f"- {k}: {st.session_state[k]:.1f}%")
    st.markdown(
        f": 사용자는 '선발투수력'에 {st.session_state['pitcher']:.0f}%,"
        f" '최근 폼'에 {st.session_state['recent_form']:.0f}%,"
        f" '홈어드밴티지'에 {st.session_state['home_advantage']:.0f}%,"
        f" '타격력'에 {st.session_state['ops']:.0f}%,"
        f" '수비력'에 {st.session_state['defense']:.0f}%,"
        f" '기대승률'에 {st.session_state['pythagorean']:.0f}%,"
        f" '날씨/환경'에 {st.session_state['weather']:.0f}%,"
        f" '불펜력'에 {st.session_state['bullpen']:.0f}%,"
        f" '배당/오즈'에 {st.session_state['odds']:.0f}%,"
        f" '이동거리 및 휴식'에 {st.session_state['rest_travel']:.0f}%,"
        f" '투수‑타자 매치업'에 {st.session_state['log5']:.0f}%,"
        f" '야구 유튜버 예측 인사이트'에 {st.session_state['insight']:.0f}%를 설정하셨습니다."
    )
else:
    st.warning("최소 하나의 요소에 가중치를 입력해주세요.")


if st.button("커스텀 가중치로 승률 예측하기", key="btn_custom"):
    #if total != 100:
        #st.error("가중치 합은 정확히 100% 여야 합니다.")
    #elif team1 == team2:
        #st.warning("홈팀과 원정팀은 서로 달라야 합니다.")
    if team1 == team2:
        st.warning("예측할 경기를 선택해주세요.")
    else:
        payload = {"team": f"{team1},{team2}", "mode": "custom", "weights": weights}
        try:
            response = requests.post(API_URL, json=payload)
            response.raise_for_status()
            data = response.json()
            st.session_state["custom_report"] = data.get("report", "보고서를 받지 못했습니다.")
        except Exception as e:
            error_msg = f"API 요청 오류: {e}"
            trace = traceback.format_exc()  # 전체 traceback 문자열
            full_error = f"{error_msg}\n\n[Traceback]\n{trace}"
            print(full_error)  # PyCharm 콘솔에도 찍기
            st.session_state["custom_report"] = f"❌ 서버 오류 발생\n\n```{full_error}```"


def request_ai_report(api_url, team1, team2, mode, session_key):
    if team1 == team2:
        st.warning("예측할 경기를 선택해주세요.")
        return
    payload = {"team": f"{team1},{team2}", "mode": mode}
    try:
        response = requests.post(api_url, json=payload)
        response.raise_for_status()
        data = response.json()
        st.session_state[session_key] = data.get("report", "보고서를 받지 못했습니다.")
    except Exception as e:
        import traceback
        error_msg = f"API 요청 오류: {e}"
        trace = traceback.format_exc()
        full_error = f"{error_msg}\n\n[Traceback]\n{trace}"
        print(full_error)
        st.session_state[session_key] = f"❌ 서버 오류 발생\n\n``````"

st.title("🧠 " + "AI 모델별 경기 예측")

if st.button("AI#1 통계", key="btn_stat"):
    request_ai_report(AI_API_URL, team1, team2, mode="stat", session_key="ai_stat_report")

if st.button("AI#2 현장", key="btn_site"):
    request_ai_report(AI_API_URL, team1, team2, mode="site", session_key="ai_site_report")

if st.button("AI#3 트렌드", key="btn_trend"):
    request_ai_report(AI_API_URL, team1, team2, mode="trend", session_key="ai_trend_report")




# 현재 팀 표시
st.write("team1", team1)
st.write("team2", team2)

if st.session_state["default_report"]:
    st.markdown("---")
    st.subheader("기본 가중치 예측 결과")
    st.markdown(st.session_state["default_report"])

if st.session_state["custom_report"]:
    st.markdown("---")
    st.subheader("커스텀 가중치 예측 결과")
    st.markdown(st.session_state["custom_report"])

if st.session_state["ai_stat_report"]:
    st.markdown("---")
    st.markdown('<h3 style="color: #1565c0;">AI#1 통계 예측 결과</h3>', unsafe_allow_html=True)
    st.markdown(st.session_state["ai_stat_report"])

if st.session_state["ai_site_report"]:
    st.markdown("---")
    st.markdown('<h3 style="color: #1565c0;">AI#2 현장 예측 결과</h3>', unsafe_allow_html=True)
    st.markdown(st.session_state["ai_site_report"])

if st.session_state["ai_trend_report"]:
    st.markdown("---")
    st.markdown('<h3 style="color: #1565c0;">AI#3 트렌드 예측 결과</h3>', unsafe_allow_html=True)
    st.markdown(st.session_state["ai_trend_report"])