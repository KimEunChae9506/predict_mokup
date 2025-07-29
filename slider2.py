import streamlit as st
import requests
import traceback
from datetime import date

API_URL = "http://localhost:8001/predict"  # customLLM.py에서 FastAPI 띄운 주소 예시

# --- 두 팀 입력 텍스트박스 ---
st.title("오늘 경기 예측할 두 팀")
import requests
from bs4 import BeautifulSoup
import streamlit as st
from requests_html import HTMLSession

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import time
import asyncio

today_str = date.today().strftime("%Y-%m-%d")

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

st.write("https://m.sports.naver.com/kbaseball/schedule/index?date=" + today_str)
# 🏁 앱 시작
st.title("📅 오늘의 KBO 경기")

match_list = fetch_kbo_matches()



# 클릭된 팀 정보 저장 변수
# Debug: 리스트 확인
if not match_list:
    st.error("오늘 경기 정보가 없습니다. (match_list가 비어 있음)")
else:
    st.success(f"{len(match_list)}개의 경기를 불러왔습니다.")

if 'team1' not in st.session_state:
    st.session_state['team1'] = None
if 'team2' not in st.session_state:
    st.session_state['team2'] = None

    for i, match in enumerate(match_list):
        label = f"{match['team1']} VS {match['team2']}"
        is_selected = (
                st.session_state['team1'] == match['team1']
                and st.session_state['team2'] == match['team2']
        )

        # 커스텀 버튼 스타일 (선택 여부에 따라 강조)
        button_style = f"""
            <style>
            div[data-testid="stButton"][key="match_{i}"] > button {{
                border: 2px solid {'#ff4b4b' if is_selected else '#ccc'};
                background-color: {'#fff0f0' if is_selected else '#f9f9f9'};
                color: black;
                font-weight: {'bold' if is_selected else 'normal'};
            }}
            </style>
            """
        st.markdown(button_style, unsafe_allow_html=True)

        if st.button(label, key=f"match_{i}"):
            st.session_state['team1'] = match['team1']
            st.session_state['team2'] = match['team2']
            st.rerun()

# 세션 상태에서 team1, team2 꺼내기
team1 = st.session_state.get('team1')
team2 = st.session_state.get('team2')

# 세션 상태에 저장
if "default_report" not in st.session_state:
    st.session_state["default_report"] = None
if "custom_report" not in st.session_state:
    st.session_state["custom_report"] = None

st.title("기본 가중치 기반 야구 승률 예측")


if st.button("기본 가중치로 승률 예측하기", key="btn_default"):
    if team1 == team2:
        st.warning("홈팀과 원정팀은 서로 달라야 합니다.")
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

st.markdown("5개 예측 요소 가중치를 조정하세요 (합 100%)")

# 키와 기본값 정의
all_keys = ["pitcher", "recent", "ops", "home", "odds"]
defaults = [30, 20, 20, 15, 15]

# 초기화
for k, d in zip(all_keys, defaults):
    if k not in st.session_state:
        st.session_state[k] = d

# 정규화 함수 (10단위 슬라이더, 선택된 요소 제외 나머지를 균등 분배)
def normalize(changed_key):
    total = sum(st.session_state[k] for k in all_keys)
    if total == 0:
        return
    remain = 100 - st.session_state[changed_key]
    other_keys = [k for k in all_keys if k != changed_key]
    sum_others = sum(st.session_state[k] for k in other_keys)
    for k in other_keys:
        if sum_others == 0:
            st.session_state[k] = (remain // 10 // len(other_keys)) * 10
        else:
            # 비율로 나눠서 10단위 반올림
            val = round(st.session_state[k] / sum_others * remain / 10) * 10
            st.session_state[k] = int(val)
    # 중간에 10단위 오차로 100 안될 경우 보정
    fix = 100 - sum([st.session_state[k] for k in all_keys])
    if fix != 0:
        # 가장 값이 큰 key에 보정값 부여
        max_key = max(all_keys, key=lambda k: st.session_state[k])
        st.session_state[max_key] += fix

# 슬라이더 생성 (10단위) - 각각 콜백이 자신을 제외한 4개에만 적용
pitcher = st.slider("1. 선발투수 ERA/FIP/WHIP", 0, 100, step=10, key="pitcher", on_change=normalize, args=("pitcher",))
recent = st.slider("2. 최근 10경기 폼 (득실점, 승–패 흐름)", 0, 100, step=10, key="recent", on_change=normalize, args=("recent",))
ops = st.slider("3. 타격력 (wOBA/OPS)", 0, 100, step=10,  key="ops", on_change=normalize, args=("ops",))
home = st.slider("4. 홈 어드밴티지", 0, 100, step=10, key="home", on_change=normalize, args=("home",))
odds = st.slider("5. 배당률", 0, 100, step=10, key="odds", on_change=normalize, args=("odds",))

weights = {k: st.session_state[k] for k in all_keys}

# 총합 계산
total = sum(st.session_state[k] for k in all_keys)

#st.markdown(f"**✅ weights: {weights}")
#st.markdown(f"**✅ 합계: {total:.0f}% (항상 100% 유지됨)**")

# 요약 출력
if total > 0:
    st.markdown("### 📊 현재 설정된 가중치")
    for k in all_keys:
        st.write(f"- {k}: {st.session_state[k]:.1f}%")
    st.markdown(
        f"**결과 요약**: 사용자는 '선발투수력'에 {st.session_state['pitcher']:.0f}%,"
        f" '최근 폼'에 {st.session_state['recent']:.0f}%,"
        f" '타격력'에 {st.session_state['ops']:.0f}%,"
        f" '홈어드밴티지'에 {st.session_state['home']:.0f}%,"
        f" '배당률'에 {st.session_state['odds']:.0f}%를 설정하셨습니다."
    )
else:
    st.warning("최소 하나의 요소에 가중치를 입력해주세요.")


if st.button("커스텀 가중치로 승률 예측하기", key="btn_custom"):
    if total != 100:
        st.error("가중치 합은 정확히 100% 여야 합니다.")
    elif team1 == team2:
        st.warning("홈팀과 원정팀은 서로 달라야 합니다.")
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

if st.session_state["default_report"]:
    st.markdown("---")
    st.subheader("기본 가중치 예측 결과")
    st.markdown(st.session_state["default_report"])

if st.session_state["custom_report"]:
    st.markdown("---")
    st.subheader("커스텀 가중치 예측 결과")
    st.markdown(st.session_state["custom_report"])
