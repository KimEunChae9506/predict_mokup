from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import Dict
import uvicorn
import requests
from datetime import date
import traceback
import sys
import logging
app = FastAPI()

@app.get("/")
async def root():
   return {"connect" : "ok"}

@app.get("/slider")
async def root():
    return RedirectResponse(url="https://predict-mokup-slide.onrender.com")

### 기본 12개 요소 고정 가중치 (%) ###
DEFAULT_WEIGHTS_12 = {
    "pitcher": 20,
    "recent_form": 15,
    "home_advantage": 10,
    "ops": 12,
    "defense": 8,
    "pythagorean": 10,
    "weather": 7,
    "bullpen": 6,
    "odds": 4,
    "rest_travel": 5,
    "log5": 5,
    "insight": 10
}

### 5개 커스텀 요소 → 12개 요소 매핑 비율표 ###
CUSTOM_KEYS = list(DEFAULT_WEIGHTS_12.keys())


### POST 요청 데이터 정의 ###
class PredictionRequest(BaseModel):
    team: str
    mode: str  # "default" 또는 "custom"
    weights: Dict[str, int] = None  # 버튼2 custom일 때는 5개 요소 딕셔너리 입력

KOR_LABELS = {
    "pitcher": "1. 선발투수 ERA/FIP/WHIP",
    "recent_form": "2. 최근 10경기 폼 (득실점, 승–패 흐름)",
    "home_advantage": "3. 홈구장 + Park Factors",
    "batting": "4. 타격력 (wOBA/OPS)",
    "defense": "5. 수비력 (DRS/수비율)",
    "pythagorean": "6. Pythagorean 기대승률",
    "weather": "7. 날씨/환경 (온도·습도·바람)",
    "bullpen": "8. 불펜력 (중간 + 마무리 ERA/FIP/WHIP)",
    "odds": "9. 배당/오즈",
    "rest_travel": "10. 이동거리 및 휴식",
    "log5": "11. 투수‑타자 매치업 (Log5)",
    "insight": "12. 야구 유튜버 예측 인사이트"
}

### user_prompt 생성 함수 ###
def build_user_prompt(final_weights_12: dict, teams: str) -> str:
    team_names = teams.split(",")
    today_str = date.today().strftime("%Y년 %m월 %d일")
    team_summary = f"{today_str} 분석 경기: {team_names[0].strip()} vs {team_names[1].strip()}"

    prompt_lines = [team_summary, "아래 예측 요소에 따라 경기를 분석해 주세요:\n"]

    prompt_lines.append("12가지 각 예측 요소에 대한 내용:")
    for key, value in final_weights_12.items():
        kor_label = KOR_LABELS.get(key, key)  # 매칭없으면 영어 key 그대로
        prompt_lines.append(f"- {kor_label}: {value:.1f}%")

    prompt_lines.append("\n예측 결과로 다음 5가지를 포함하세요:")
    prompt_lines.append("\n아래 사항을 반드시 포함해 주십시오:")
    prompt_lines.append("1. 두 팀 승리 확률 (%)")
    prompt_lines.append("2. 전력 비교 요약 (텍스트 및 표 활용).")
    prompt_lines.append("3. 12가지 각 예측 요소에 대한 설명.")
    prompt_lines.append("4. 예상 최종 스코어(예: 4:3, 6:4 등)와 양 팀의 예상 '합산 점수', 점수차, 합계 홀짝 여부(odd/even), 오버/언더 임계치(예: 기준점 8.5 기준 over/under)")
    prompt_lines.append("5. 예상 우세 팀 + 분석 근거 (4-6줄)")
    prompt_lines.append("6. 리스크 요인 2가지 제시")

    #for k, v in final_weights_12.items():
    #    prompt_lines.append(f"- {k.replace('_', ' ').title()}: {v:.1f}%")

    return "\n".join(prompt_lines)

### user_prompt AI 모델별 생성 함수 ###
def build_ai_mode_user_prompt(mode: str, teams: str) -> str:
    team_names = teams.split(",")
    today_str = date.today().strftime("%Y년 %m월 %d일")
    team_summary = f"{today_str} 분석 경기: {team_names[0].strip()} vs {team_names[1].strip()}"

    prompt_lines = [team_summary]

    # mode별 요구사항 추가
    if mode == "stat":  # 통계형
        prompt_lines.append("▼ [통계형 예측]")
        prompt_lines.append(
            "- 반드시 '선발투수 ERA', '팀 타율', '팀 수비지표' 항목(각각 가중치 0.37/0.28/0.17)을 중심으로 실데이터와 최근 추이, 평균 대비 장단점을 근거로 제시해주세요.")
        prompt_lines.append("- 오직 통계 데이터를 근거로 승/패 예측, 점수 예상, 주요 변수와 신뢰도도 설명해 주세요.")
        prompt_lines.append("- 추가 변수(부상, 날씨 등)는 별도 섹션으로 정리합니다.")

    elif mode == "site":  # 현장파
        prompt_lines.append("▼ [현장파 예측]")
        prompt_lines.append("- 반드시 '팀 피로도'(0.41), '중심타선 컨디션·전력'(0.22), '수비시프트 전략'(0.16) 항목을 중점적으로 분석하고,")
        prompt_lines.append("- 현장 기사·전문가 발언, 실전 변수와 분위기 등 현장감 넘치는 근거를 집중 반영해 예측 결과와 근거를 제시해 주세요.")
        prompt_lines.append("- 현장 변수와 주요 리스크·승부처도 논리적으로 기술해 주세요.")

    elif mode == "trend":  # 트렌드형
        prompt_lines.append("▼ [트렌드 기반 예측]")
        prompt_lines.append("- 반드시 '최근 7경기 팀 득점'(0.33), '상대전적'(0.26), '구장 특성'(0.15)을 포함해,")
        prompt_lines.append("- 최근 승패 흐름, 특정 상대팀과의 특징, 구장 경향 등 트렌드 데이터를 인용하여, 점수 예측·승부처·리스크를 설명해 주세요.")

    else:
        prompt_lines.append("- (기본 분석 방식으로 작성)")

    prompt_lines.append("\n예측 결과로 하단에 아래 사항을 반드시 포함해 주십시오:")
    prompt_lines.append("1. 두 팀 승리 확률 (%)")
    prompt_lines.append(
        "2. 예상 최종 스코어(예: 4:3, 6:4 등)와 양 팀의 예상 '합산 점수', 점수차, 합계 홀짝 여부(odd/even), 오버/언더 임계치(예: 기준점 8.5 기준 over/under)")
    prompt_lines.append("\n리포트 전체는 존댓말, 간결·명확하게 작성 바랍니다.")

    return "\n".join(prompt_lines)

### 5개 custom 가중치 → 12개 요소로 변환 함수 ###
def expand_custom_weights(custom_weights: Dict[str, float]) -> Dict[str, float]:
    """
    사용자로부터 12개 각 요소별 가중치가 넘어온 경우,
    적합한 값인지 검증 후, DEFAULT_WEIGHTS_12 키와 일치하는 값만 담아 반환.
    """
    result = {key: 0.0 for key in DEFAULT_WEIGHTS_12}

    for key, weight in custom_weights.items():
        try:
            w = float(weight)
        except Exception as e:
            raise ValueError(f"잘못된 가중치 입력: {key} = {weight} (type={type(weight)})")

        if key in result:
            result[key] = w
        else:
            print(f"[WARN] unknown custom weight key: {key}")

    return result


def get_perplexity_response(system_prompt: str, user_prompt: str) -> str:
    API_KEY = "Bearer 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"  # 💡 여기에 토큰 교체
    API_URL = "https://api.perplexity.ai/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": API_KEY
    }

    body = {
        "model": "sonar-pro",  # 또는 pplx-7b-chat 등 사용 중 모델 확인
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.7,
        "top_p": 1,
        "max_tokens": 1800
    }

    response = requests.post(API_URL, headers=headers, json=body, verify=False)
    response.raise_for_status()

    reply = response.json()
    return reply["choices"][0]["message"]["content"]

@app.post("/predict")
def predict(req: PredictionRequest):

    if req.mode == "default":
        weights_12 = DEFAULT_WEIGHTS_12.copy()
    elif req.mode == "custom" and req.weights:
        try:
            weights_12 = expand_custom_weights(req.weights)
        except Exception as e:
            print("🔥 커스텀 가중치 변환 오류:", e)
            return {"error": f"커스텀 가중치 오류: {str(e)}"}
    else:
        return {"error": "Invalid request. 'mode' must be 'default' or 'custom'."}

    # 프롬프트 생성
    #https://www.koreabaseball.com/schedule/scoreboard.aspx
    user_prompt = build_user_prompt(weights_12, req.team)
    system_prompt = """
        당신은 KBO 리그 전문 야구 데이터 분석가이며, AI 리포트 작성자입니다. 
        아래 출처의 최신 데이터를 반드시 참고해 예측 분석 리포트를 작성하십시오.
        - KBO 공식 홈페이지의 게임센터,기록실(선발·불펜, 누적 및 경기별 스탯):  https://www.koreabaseball.com/Schedule/GameCenter/Main.aspx, https://www.koreabaseball.com/record/player/hitterbasic/basic1.aspx
        - Naver Sports, statiz, Livesport, Flashscore 등 검증된 실시간 프로야구 데이터 사이트
        특히, 전문가 예측과 전력 해석에는 다음 유튜브 분석 정보도 반드시 포함해야 합니다.
        - 경기 당일 예측 정보: '매일 야구 분석 라운지' 유튜브 채널의 당일 경기 예측 요약 및 해설 인사이트
        - 주간 전망 정보: '크보오프너 주간오프너(주간야구분석)' 유튜브 채널의 최신 주간 예측 요약 및 전체 프레임 해설
        
        리포트 작성 시,
        - 당일 예측 정보(30분~1시간 전)와 주간 예측 정보 모두를 각각 별도 section으로 요약하여 주요 근거와 리스크에 반영하십시오.
        - 두 정보가 상충하거나 차이가 있을 경우, 그 이유와 각 정보의 시점·문맥을 모두 해설로 포함해 주세요.
        - 분석, 예측, 통계, 리포트 내용이 위 공식 데이터 출처 또는 위 유튜브 분석 결과와 정확히 일치하는지 답변 전 반드시 한 번 더 교차 검토하고, 실제 자료와 다르거나 오류가 있을 경우 반드시 정정·보완해서 답변해 주세요.
        - 모든 분석과 결과는 한국어로, 리포트는 실제 KBO 전문 데이터 분석가처럼 간결하고 명확하게 존댓말로 작성하십시오.
        """

    try:
        ai_report = get_perplexity_response(system_prompt, user_prompt)
    except Exception as e:
        print("[ERROR] AI 요청 중 에러 발생:", req.team, req.weights)
        traceback.print_exc()
        return {"error": f"AI 요청 실패: {str(e)}"}

    #mock_report = f"""🧠 AI 분석 리포트"""

    return {
        "report": ai_report
    }


@app.post("/ai-predict")
def predict(req: PredictionRequest):

    # 프롬프트 생성
    user_prompt = build_ai_mode_user_prompt(req.mode, req.team)
    system_prompt = """
        당신은 KBO 리그 전문 야구 데이터 분석가이며, AI 리포트 작성자입니다. 
        아래 출처의 최신 데이터를 반드시 참고해 예측 분석 리포트를 작성하십시오.
        - KBO 공식 홈페이지의 게임센터,기록실(선발·불펜, 누적 및 경기별 스탯):  https://www.koreabaseball.com/Schedule/GameCenter/Main.aspx, https://www.koreabaseball.com/record/player/hitterbasic/basic1.aspx
        - Naver Sports, statiz, Livesport, Flashscore 등 검증된 실시간 프로야구 데이터 사이트

        리포트 작성 시,
        - 분석, 예측, 통계, 리포트 내용이 위 공식 데이터 출처 또는 위 유튜브 분석 결과와 정확히 일치하는지 답변 전 반드시 한 번 더 교차 검토하고, 실제 자료와 다르거나 오류가 있을 경우 반드시 정정·보완해서 답변해 주세요.
        - 모든 분석과 결과는 한국어로, 리포트는 실제 KBO 전문 데이터 분석가처럼 간결하고 명확하게 존댓말로 작성하십시오.
        """

    try:
        ai_report = get_perplexity_response(system_prompt, user_prompt)
    except Exception as e:
        print("[ERROR] AI 요청 중 에러 발생:", req.team, req.weights)
        traceback.print_exc()
        return {"error": f"AI 요청 실패: {str(e)}"}

    # mock_report = f"""🧠 AI 분석 리포트"""

    return {
        "report": ai_report
    }