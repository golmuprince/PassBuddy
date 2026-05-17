import streamlit as st
import os
import sqlite3
import uuid
import json
from datetime import date, datetime, timedelta
from dotenv import load_dotenv
load_dotenv()

st.set_page_config(page_title="PassBuddy", page_icon="🎯", layout="centered")

DEFAULT_CERT = "리눅스마스터 2급"
CERT_LIST_PATH = "data/cert_list.json"


def load_cert_list() -> list:
    os.makedirs("data", exist_ok=True)
    if os.path.exists(CERT_LIST_PATH):
        with open(CERT_LIST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return [DEFAULT_CERT]


def save_cert_list(certs: list):
    with open(CERT_LIST_PATH, "w", encoding="utf-8") as f:
        json.dump(certs, f, ensure_ascii=False)


if "logs" not in st.session_state:
    st.session_state.logs = []
if "cert_sessions" not in st.session_state:
    st.session_state.cert_sessions = {}
if "show_wrong" not in st.session_state:
    st.session_state.show_wrong = False


def add_log(level: str, msg: str):
    icon = {"INFO": "ℹ️", "OK": "✅", "ERROR": "❌", "WARN": "⚠️"}.get(level, "•")
    st.session_state.logs.append(f"{datetime.now().strftime('%H:%M:%S')} {icon} {msg}")
    if len(st.session_state.logs) > 50:
        st.session_state.logs = st.session_state.logs[-50:]


from langchain_core.callbacks.base import BaseCallbackHandler
from streamlit.delta_generator import DeltaGenerator

class StreamHandler(BaseCallbackHandler):
    def __init__(self, container: DeltaGenerator, initial_text=""):
        self.container = container
        self.text = initial_text
        self.tool_called = False

    def on_llm_new_token(self, token: str, **kwargs):
        self.text += token
        self.container.write(self.text)

    def on_tool_start(self, serialized, input_str, **kwargs):
        self.tool_called = True

    def on_llm_start(self, serialized, prompts, **kwargs):
        if self.tool_called:
            self.text += '\n\n'
            self.tool_called = False

# api_key, cert_name 미리 정의 (탭 밖에서 사용)
try:
    secrets_key = st.secrets.get("OPENAI_API_KEY", "")
except Exception:
    secrets_key = ""
api_key = secrets_key or os.getenv("OPENAI_API_KEY", "")
if api_key:
    os.environ["OPENAI_API_KEY"] = api_key

cert_list = load_cert_list()
cert_name = cert_list[0] if cert_list else "리눅스마스터 2급"

import tools.db_tools as db_tools

with st.sidebar:
    st.title("🎯 PassBuddy")
    st.divider()

    main_tab, cert_tab, wrong_tab, debug_tab = st.tabs(["📋 학습", "➕ 자격증", "📝 오답", "🪵 디버그"])

    with cert_tab:
        st.caption("➕ 새 자격증 추가 / PDF 업로드")
        new_cert = st.text_input("자격증 이름", placeholder="예: 정보처리기사")
        uploaded_pdf = st.file_uploader("기출문제 PDF (선택)", type=["pdf"])

        if st.button("추가 / 문제지 업로드", use_container_width=True):
            if not new_cert:
                st.warning("자격증 이름을 입력해주세요")
            else:
                if uploaded_pdf:
                    os.makedirs("data", exist_ok=True)
                    pdf_path = f"data/{new_cert}_{uploaded_pdf.name}"
                    with open(pdf_path, "wb") as f:
                        f.write(uploaded_pdf.read())
                    with st.spinner("PDF 분석 중..."):
                        try:
                            from tools.pdf_vision_to_quiz import extract_from_pdf
                            add_log("INFO", f"PDF 분석 시작: {uploaded_pdf.name}")
                            count = extract_from_pdf(pdf_path, new_cert)
                            add_log("OK", f"PDF 분석 완료: {count}개 문제 추출")
                            st.success(f"{count}개 문제 추출 완료! ✅")
                        except Exception as e:
                            add_log("ERROR", f"PDF 추출 실패: {e}")
                            st.error(f"추출 실패: {str(e)}")

                if new_cert not in cert_list:
                    cert_list.append(new_cert)
                    save_cert_list(cert_list)
                    st.success(f"{new_cert} 추가됐어요!")
                else:
                    st.info(f"{new_cert}에 문제가 추가됐어요!")
                st.rerun()

        st.divider()
        st.caption("📋 답안지 업로드 (정답 매칭)")
        answer_cert = st.selectbox("자격증 선택", cert_list, key="answer_cert")
        uploaded_answer = st.file_uploader("답안지 PDF", type=["pdf"], key="answer_pdf")

        if st.button("답안지 업로드", use_container_width=True):
            if uploaded_answer and answer_cert:
                os.makedirs("data", exist_ok=True)
                pdf_path = f"data/{answer_cert}_answer_{uploaded_answer.name}"
                with open(pdf_path, "wb") as f:
                    f.write(uploaded_answer.read())
                with st.spinner("답안지 분석 중..."):
                    try:
                        from tools.pdf_vision_to_quiz import extract_answers_from_pdf
                        add_log("INFO", f"답안지 분석 시작: {uploaded_answer.name}")
                        count = extract_answers_from_pdf(pdf_path, answer_cert)
                        add_log("OK", f"답안지 매칭 완료: {count}개 업데이트")
                        st.success(f"{count}개 문제에 정답 업데이트 완료! ✅")
                    except Exception as e:
                        add_log("ERROR", f"답안지 추출 실패: {e}")
                        st.error(f"추출 실패: {str(e)}")
            else:
                st.warning("자격증과 답안지 PDF를 선택해주세요")

    with main_tab:
        cert_name = st.radio("📋 자격증 선택", cert_list, index=0)

        if cert_name != DEFAULT_CERT:
            if st.button("🗑️ 이 자격증 삭제", use_container_width=True):
                cert_list.remove(cert_name)
                save_cert_list(cert_list)
                # DB 파일 삭제
                db_file = f"data/{cert_name}.db"
                if os.path.exists(db_file):
                    os.remove(db_file)
                # 퀴즈 JSON 및 PDF 삭제
                import glob
                for f in glob.glob(f"data/{cert_name}*"):
                    if "cert_list" not in f:
                        os.remove(f)
                st.rerun()

# ── DB 초기화 ─────────────────────────────────────────────────
db_tools.set_db_path(cert_name)
db_tools.init_db()

from tools.db_tools import load_plan, get_attendance_data

# ── 세션 초기화 ────────────────────────────────────────────────
if cert_name not in st.session_state.cert_sessions:
    st.session_state.cert_sessions[cert_name] = {
        "messages": [],
        "current_agent": "router",
        "thread_id": str(uuid.uuid4()),
    }

sess = st.session_state.cert_sessions[cert_name]
st.session_state.messages = sess["messages"]
st.session_state.current_agent = sess["current_agent"]
st.session_state.thread_id = sess["thread_id"]

# ── 그래프 빌드 ────────────────────────────────────────────────
from langgraph.graph import START, END, StateGraph, MessagesState
from langgraph.checkpoint.sqlite import SqliteSaver

DB_PATH = f"data/{cert_name}.db"


@st.cache_resource
def build_graph(cert_name: str):
    from agents.router import build_router
    from agents.planner_agent import build_planner
    from agents.class_agent import build_class
    from agents.quiz_agent import build_quiz

    class AgentState(MessagesState):
        current_agent: str

    def router_check(state: AgentState):
        return state.get("current_agent", "router")

    graph_builder = StateGraph(AgentState)
    graph_builder.add_node("router", build_router(cert_name), destinations=("planner_agent", "class_agent", "quiz_agent"))
    graph_builder.add_node("planner_agent", build_planner(cert_name))
    graph_builder.add_node("class_agent", build_class(cert_name))
    graph_builder.add_node("quiz_agent", build_quiz(cert_name))

    graph_builder.add_conditional_edges(START, router_check, ["router", "planner_agent", "class_agent", "quiz_agent"])
    graph_builder.add_edge("router", END)
    graph_builder.add_edge("planner_agent", END)
    graph_builder.add_edge("class_agent", END)
    graph_builder.add_edge("quiz_agent", END)

    conn = sqlite3.connect(f"data/{cert_name}.db", check_same_thread=False)
    memory = SqliteSaver(conn)
    return graph_builder.compile(checkpointer=memory)


graph = build_graph(cert_name)
config = {"configurable": {"thread_id": st.session_state.thread_id}}


def plan_to_daily(weekly_plan: dict, start_date: str) -> list:
    daily = []
    try:
        base = datetime.strptime(start_date, "%Y-%m-%d").date()
    except Exception:
        base = date.today()

    day_num = 0
    for key, value in weekly_plan.items():
        if key in ("총_학습일",):
            continue
        if isinstance(value, list):
            topic_str = ", ".join(str(t) for t in value)
        elif isinstance(value, dict):
            topic_str = ", ".join(
                ", ".join(str(t) for t in v) if isinstance(v, list) else str(v)
                for v in value.values()
            )
        else:
            topic_str = str(value)

        if "주차" in str(key):
            for topic in (value if isinstance(value, list) else [topic_str]):
                daily.append({"day": day_num + 1, "week": f"{day_num + 1}일차", "topic": str(topic), "date": str(base + timedelta(days=day_num))})
                day_num += 1
        else:
            daily.append({"day": day_num + 1, "week": f"{day_num + 1}일차", "topic": topic_str, "date": str(base + timedelta(days=day_num))})
            day_num += 1
    return daily


def clear_checkpoints():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    for table in ["checkpoints", "checkpoint_writes", "checkpoint_blobs"]:
        try:
            cursor.execute(f"DELETE FROM {table}")
        except Exception:
            pass
    conn.commit()
    conn.close()


# ── 사이드바 학습 현황 ─────────────────────────────────────────
with st.sidebar:
    with main_tab:
        st.divider()
        st.subheader(f"📊 {cert_name}")

        try:
            plan = load_plan.invoke({})
        except Exception:
            plan = None

        if isinstance(plan, dict):
            target_date = plan.get("exam_date", plan.get("target_date", ""))
            if target_date:
                try:
                    d_day = (datetime.strptime(target_date, "%Y-%m-%d").date() - date.today()).days
                    d_label = f"D-{d_day}" if d_day > 0 else ("D-Day!" if d_day == 0 else f"D+{abs(d_day)}")
                    st.metric("🎯 목표까지", d_label, delta=target_date, delta_color="off")
                except Exception:
                    st.metric("🎯 목표 날짜", target_date)

            attendance = get_attendance_data()
            att_map = {a["date"]: a for a in attendance}

            weekly_plan = plan.get("weekly_plan", {})
            created_at = plan.get("created_at", str(date.today()))
            daily_list = plan_to_daily(weekly_plan, created_at)

            if daily_list:
                total_all = len(daily_list)
                done_all = sum(1 for d in daily_list if att_map.get(d["date"], {}).get("studied", 0))
                pct_all = int(done_all / total_all * 100) if total_all > 0 else 0

                with st.expander(f"📋 전체 일정 ({done_all}/{total_all} · {pct_all}%)"):
                    for d in daily_list:
                        att = att_map.get(d["date"], {})
                        s_icon = "✅" if att.get("studied") else "⬜"
                        q_icon = "🧩" if att.get("quizzed") else "  "
                        score = f" `{att['quiz_score']}`" if att.get("quiz_score") else ""
                        is_today = d["date"] == str(date.today())
                        today_mark = " 👈" if is_today else ""
                        topic_short = d["topic"][:22] + ("..." if len(d["topic"]) > 22 else "")
                        st.write(f"{s_icon}{q_icon} **{d['week']}** {topic_short}{score}{today_mark}")
        else:
            st.info("학습 계획이 없어요.\n플래너에게 계획을 요청해보세요!")

        st.divider()

        agent_labels = {
            "router":        "🔀 라우터",
            "planner_agent": "📅 플래너",
            "class_agent":   "📚 클래스",
            "quiz_agent":    "🧩 퀴즈",
        }
        st.caption("현재 에이전트")
        st.write(agent_labels.get(st.session_state.current_agent, "🔀 라우터"))

        st.divider()

        if st.button("🗑️ 대화 초기화", use_container_width=True):
            st.session_state.cert_sessions[cert_name] = {
                "messages": [],
                "current_agent": "router",
                "thread_id": str(uuid.uuid4()),
            }
            clear_checkpoints()
            st.rerun()

        if st.button("📋 계획 초기화", use_container_width=True):
            st.session_state.cert_sessions[cert_name] = {
                "messages": [],
                "current_agent": "router",
                "thread_id": str(uuid.uuid4()),
            }
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            for table in ["study_plan", "study_log", "quiz_log", "attendance", "daily_questions"]:
                try:
                    cursor.execute(f"DELETE FROM {table}")
                except Exception:
                    pass
            conn.commit()
            conn.close()
            clear_checkpoints()
            st.rerun()

    with wrong_tab:
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT topic, question, question_number, user_answer, correct_answer
                FROM quiz_log WHERE is_correct = 0
                ORDER BY date DESC
            """)
            rows = cursor.fetchall()
            conn.close()

            import glob
            all_q = []
            for p in glob.glob("data/*_quiz.json"):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        all_q.extend(json.load(f))
                except Exception:
                    pass
            q_by_num = {q.get("number"): q for q in all_q}

            if not rows:
                st.info("틀린 문제가 없어요! 🎉")
            else:
                st.caption(f"총 {len(rows)}개 오답")
                for i, (topic, question, q_num, user_ans, correct_ans) in enumerate(rows, 1):
                    # 1. question_number로 매칭
                    q = q_by_num.get(q_num, {}) if q_num else {}
                    # 2. 매칭 실패 시 question 텍스트로 매칭
                    if not q:
                        matched = [m for m in all_q if m.get("question", "")[:40] == question[:40]]
                        q = matched[0] if matched else {}

                    real_correct = q.get("correct_answer") or correct_ans or "?"
                    with st.expander(f"{i}. {question[:35]}..."):
                        st.write(f"**{q.get('question', question)}**")
                        options = q.get("options", [])
                        if options:
                            for opt in options:
                                st.write(opt)
                        if user_ans:
                            st.error(f"❌ 내 답: {user_ans}")
                        st.success(f"✅ 정답: {real_correct}")
                        if q.get("explanation"):
                            st.info(f"💡 {q['explanation']}")
                        else:
                            st.warning("해설이 없어요. PDF에서 정답만 추출되어 해설이 비어있을 수 있어요.")
                        st.caption(f"주제: {topic}")
        except Exception as e:
            st.warning(f"오답 불러오기 실패: {e}")

    with debug_tab:
        st.caption("📦 LangGraph State")
        try:
            state = graph.get_state(config)
            vals = state.values
            st.caption("🤖 현재 에이전트")
            st.info(vals.get("current_agent", "없음"))
            st.caption("💬 메시지 히스토리")
            messages = vals.get("messages", [])
            if not messages:
                st.info("메시지 없어요")
            for msg in reversed(messages[-15:]):
                role = getattr(msg, "type", type(msg).__name__)
                if isinstance(msg.content, str):
                    text = msg.content
                elif isinstance(msg.content, list):
                    text = " ".join(c.get("text", str(c)) if isinstance(c, dict) else str(c) for c in msg.content)
                else:
                    text = str(msg.content)
                icon = {"human": "🧑", "ai": "🤖", "tool": "🔧"}.get(role, "•")
                with st.expander(f"{icon} {role} — {text[:50]}"):
                    st.text(text)
        except Exception as e:
            st.warning(f"State 없음: {e}")

        st.divider()
        st.caption("🪵 앱 로그")
        if st.button("로그 지우기", key="clear_log", use_container_width=True):
            st.session_state.logs = []
            st.rerun()
        for log in reversed(st.session_state.get("logs", [])):
            st.caption(log)

# ── 메인 화면 ──────────────────────────────────────────────────
st.title("🎯 PassBuddy")
st.caption(f"{cert_name} 취득을 도와드려요!")
st.markdown("""
> 기출문제 기반으로 공부하고 퀴즈까지 한번에.  
> 왼쪽 사이드바에서 자격증을 선택하거나 새로 추가해보세요.
""")
st.divider()

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

if not st.session_state.messages:
    with st.chat_message("ai"):
        st.markdown(f"""
안녕하세요! **PassBuddy** 예요 🎯

**{cert_name}** 취득을 도와드릴게요!

| 기능 | 말하는 방법 |
|------|------------|
| 📅 학습 계획 짜기 | "계획 짜줘", "한달 뒤가 목표야" |
| 📚 오늘 공부하기 | "오늘 공부할래", "학습 시작" |
| 🧩 퀴즈 풀기 | "퀴즈 풀고 싶어", "문제 내줘" |

> 💡 처음이라면 **학습 계획 짜기**부터 시작해보세요!
""")

user_input = st.chat_input("무엇이든 말씀해주세요")

if user_input:
    with st.chat_message("human"):
        st.write(user_input)
    st.session_state.messages.append({"role": "human", "content": user_input})
    st.session_state.cert_sessions[cert_name]["messages"] = st.session_state.messages

    with st.chat_message("ai"):
        agent_spinners = {
            "router":        "🔀 요청 분석 중...",
            "planner_agent": "📅 학습 계획 세우는 중...",
            "class_agent":   "📚 학습 내용 준비 중...",
            "quiz_agent":    "🧩 퀴즈 준비 중...",
        }
        spinner_msg = agent_spinners.get(st.session_state.current_agent, "생각 중...")
        placeholder = st.empty()

        try:
            add_log("INFO", f"입력: {user_input[:30]}...")
            add_log("INFO", f"에이전트: {st.session_state.current_agent}")

            handler = StreamHandler(placeholder)
            with st.spinner(spinner_msg):
                result = graph.invoke(
                    {
                        "messages": [{"role": "user", "content": user_input}],
                        "current_agent": st.session_state.current_agent,
                    },
                    config={**config, "callbacks": [handler]},
                )
            ai_messages = [m for m in result["messages"] if getattr(m, "type", "") == "ai" and isinstance(m.content, str) and m.content]
            response = ai_messages[-1].content if ai_messages else result["messages"][-1].content
            new_agent = result.get("current_agent", "router")
            st.session_state.current_agent = new_agent
            placeholder.write(response)

            if response:
                add_log("OK", f"응답 완료 → {st.session_state.current_agent}")
                st.session_state.messages.append({"role": "ai", "content": response})
                st.session_state.cert_sessions[cert_name]["messages"] = st.session_state.messages
                st.session_state.cert_sessions[cert_name]["current_agent"] = st.session_state.current_agent

        except Exception as e:
            add_log("ERROR", f"전체 오류: {type(e).__name__}: {e}")
            st.error(f"오류가 발생했어요: {str(e)}")

    st.rerun()