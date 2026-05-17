🎯 PassBuddy

자격증 취득을 함께 준비하는 AI 학습 파트너

LangGraph 기반 멀티 에이전트로 만든 자격증 학습 도우미예요. 기출문제 PDF만 올리면 시험 날짜에 맞춰 일차별 계획을 세우고, 그날 풀 문제와 연동된 수업을 진행한 뒤, 바로 퀴즈로 확인할 수 있어요.
기본으로 리눅스마스터 2급이 탑재돼있고, 다른 자격증도 자유롭게 추가 가능해요.

✨ 주요 기능

📅 자동 학습 계획 — 목표 날짜 기반 일차별 커리큘럼
📚 퀴즈 연동 수업 — 오늘 풀 문제를 미리 분석해서 그 개념만 정확히 설명
🧩 자동 채점 퀴즈 — 기출문제 출제 + 해설
📝 오답 노트 — 틀린 문제 자동 누적 + 다음 퀴즈에서 우선 재출제
📄 PDF 자동 분석 — GPT-4o Vision으로 문제/답안지 추출
🎯 다중 자격증 지원 — 자격증별 독립 학습 환경


🚀 사용 방법

사이드바에서 자격증 선택 (또는 새로 추가)
"계획 짜줘" 입력 → 시험 날짜 입력
"오늘 공부할래" → 학습 시작
"퀴즈 풀고 싶어" → 문제 풀이


🛠️ 로컬 실행
bash# 의존성 설치
uv sync

# OpenAI API 키 설정
echo "OPENAI_API_KEY=sk-..." > .env

# 실행
streamlit run main.py

🧰 기술 스택

LangGraph — 멀티 에이전트 오케스트레이션
OpenAI GPT-4o / mini — 에이전트별 차등 적용
Streamlit — 웹 UI
SQLite — 영구 저장
GPT-4o Vision — PDF 문제 추출


📂 프로젝트 구조
passbuddy/
├── main.py                       # Streamlit 앱
├── agents/
│   ├── router.py                 # 사용자 의도 파악
│   ├── planner_agent.py          # 학습 계획 생성
│   ├── class_agent.py            # 학습 진행
│   └── quiz_agent.py             # 퀴즈 출제
├── tools/
│   ├── db_tools.py               # SQLite 저장소
│   ├── shared_tools.py           # 에이전트 전환
│   └── pdf_vision_to_quiz.py     # PDF 분석
└── data/
    ├── cert_list.json            # 자격증 목록
    └── {자격증}_quiz.json        # 자격증별 문제

made by @Golmu
