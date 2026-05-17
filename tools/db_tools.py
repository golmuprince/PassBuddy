import os
import sqlite3
import json
import random
from datetime import date
from langchain_core.tools import tool

DB_PATH = "data/리눅스마스터2급.db"


def set_db_path(cert_name: str):
    global DB_PATH
    os.makedirs("data", exist_ok=True)
    DB_PATH = f"data/{cert_name}.db"


def get_quiz_path(cert_name: str) -> str:
    return f"data/{cert_name}_quiz.json"


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS study_plan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_date TEXT,
            created_at TEXT,
            weekly_plan TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS study_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            topic TEXT,
            summary TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quiz_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            topic TEXT,
            question TEXT,
            is_correct INTEGER,
            question_number INTEGER,
            user_answer TEXT,
            correct_answer TEXT
        )
    """)
    try:
        cursor.execute("ALTER TABLE quiz_log ADD COLUMN user_answer TEXT")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE quiz_log ADD COLUMN correct_answer TEXT")
    except Exception:
        pass
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE,
            studied INTEGER DEFAULT 0,
            quizzed INTEGER DEFAULT 0,
            quiz_score TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE,
            questions TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE,
            questions TEXT
        )
    """)
    try:
        cursor.execute("ALTER TABLE quiz_log ADD COLUMN question_number INTEGER")
    except Exception:
        pass

    conn.commit()
    conn.close()


init_db()


def _assign_questions_to_plan(weekly_plan: dict, created_at: str):
    """계획 저장 시 일차별 문제를 자동 배정 (실제 DB 문제만 사용)"""
    import glob
    from datetime import datetime, timedelta

    all_questions = []
    for p in glob.glob("data/*_quiz.json"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                all_questions.extend(json.load(f))
        except Exception:
            pass

    if not all_questions:
        return

    try:
        base = datetime.strptime(created_at, "%Y-%m-%d").date()
    except Exception:
        base = date.today()

    days = [(k, v) for k, v in weekly_plan.items() if k != "총_학습일"]
    total_days = len(days)
    if total_days == 0:
        return

    per_day = min(len(all_questions) // total_days, 10)
    per_day = max(per_day, 1)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    used_numbers = set()
    for i, (day_key, topics) in enumerate(days):
        target_date = str(base + timedelta(days=i))
        topic_list = topics if isinstance(topics, list) else [str(topics)]
        topic_str = " ".join(topic_list)

        # 주제 매칭 문제 우선
        matched = [q for q in all_questions
                   if any(kw in q.get("topic", "") for kw in topic_str.split())
                   and q.get("number") not in used_numbers]

        if len(matched) < per_day:
            extra = [q for q in all_questions
                     if q.get("number") not in used_numbers and q not in matched]
            random.shuffle(extra)
            matched = matched + extra

        selected = matched[:per_day]
        for q in selected:
            used_numbers.add(q.get("number"))

        cursor.execute("""
            INSERT INTO daily_questions (date, questions)
            VALUES (?, ?)
            ON CONFLICT(date) DO UPDATE SET questions = ?
        """, (target_date,
              json.dumps(selected, ensure_ascii=False),
              json.dumps(selected, ensure_ascii=False)))

    conn.commit()
    conn.close()


@tool
def save_plan(exam_date: str, weekly_plan: dict):
    """
    학습 플랜을 DB에 저장합니다.
    저장과 동시에 일차별 문제를 자동 배정합니다.
    Args:
        exam_date: 목표 날짜 (예: '2025-11-08')
        weekly_plan: 일차별 학습 계획 딕셔너리
    """
    today = str(date.today())
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO study_plan (exam_date, created_at, weekly_plan)
        VALUES (?, ?, ?)
    """, (exam_date, today, json.dumps(weekly_plan, ensure_ascii=False)))
    conn.commit()
    conn.close()

    _assign_questions_to_plan(weekly_plan, today)
    return "플랜과 일차별 문제 배정이 완료됐어요!"


@tool
def load_plan():
    """가장 최근 학습 플랜을 불러옵니다."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT exam_date, weekly_plan, created_at FROM study_plan ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()

    if row is None:
        return "저장된 플랜이 없어요."

    return {
        "exam_date": row[0],
        "weekly_plan": json.loads(row[1]),
        "created_at": row[2],
    }


@tool
def save_study_log(topic: str, summary: str):
    """오늘 학습한 내용을 저장합니다."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO study_log (date, topic, summary) VALUES (?, ?, ?)",
                   (str(date.today()), topic, summary))
    conn.commit()
    conn.close()
    return "학습 일지가 저장됐어요!"


@tool
def load_quiz_bank(topic: str = None, limit: int = 50):
    """
    기출문제를 불러옵니다.
    Args:
        topic: 주제 필터 (없으면 전체 랜덤 반환)
        limit: 최대 문제 수 (기본 20개)
    """
    import glob
    all_questions = []
    for p in glob.glob("data/*_quiz.json"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                all_questions.extend(json.load(f))
        except Exception:
            pass

    if not all_questions:
        return []

    if topic:
        exact = [q for q in all_questions if topic in q.get("topic", "")]
        if exact:
            random.shuffle(exact)
            return exact[:limit]

        keywords = [w.strip() for w in topic.replace(",", " ").replace("/", " ").split() if len(w.strip()) > 1]
        matched = [q for q in all_questions if any(kw in q.get("topic", "") for kw in keywords)]
        if matched:
            random.shuffle(matched)
            return matched[:limit]

    random.shuffle(all_questions)
    return all_questions[:limit]


@tool
def save_quiz_log(topic: str, question: str, is_correct: bool, question_number: int = 0, user_answer: str = "", correct_answer: str = ""):
    """퀴즈 결과를 저장합니다."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO quiz_log (date, topic, question, is_correct, question_number, user_answer, correct_answer)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (str(date.today()), topic, question, 1 if is_correct else 0, question_number, user_answer, correct_answer))
    conn.commit()
    conn.close()
    return "퀴즈 결과가 저장됐어요!"


@tool
def load_wrong_questions(limit: int = 10):
    """이전에 틀린 문제를 불러옵니다."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT topic, question, question_number FROM quiz_log
        WHERE is_correct = 0 ORDER BY date DESC LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return "이전에 틀린 문제가 없어요."

    import glob
    all_questions = []
    for path in glob.glob("data/*_quiz.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                all_questions.extend(json.load(f))
        except Exception:
            pass

    q_by_number = {q.get("number"): q for q in all_questions}
    wrong = []
    seen = set()
    for topic, question, q_number in rows:
        if q_number and q_number in q_by_number:
            q = q_by_number[q_number]
        else:
            matched = [q for q in all_questions if q.get("question", "")[:40] == question[:40]]
            q = matched[0] if matched else {"topic": topic, "question": question}
        key = q.get("question", question)[:40]
        if key not in seen:
            wrong.append(q)
            seen.add(key)

    return wrong


@tool
def mark_attendance(studied: bool = False, quizzed: bool = False, quiz_score: str = ""):
    """오늘의 출석 및 학습/퀴즈 완료를 기록합니다."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    today = str(date.today())
    cursor.execute("""
        INSERT INTO attendance (date, studied, quizzed, quiz_score)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(date) DO UPDATE SET
            studied = MAX(studied, ?),
            quizzed = MAX(quizzed, ?),
            quiz_score = CASE WHEN ? != '' THEN ? ELSE quiz_score END
    """, (
        today, 1 if studied else 0, 1 if quizzed else 0, quiz_score,
        1 if studied else 0, 1 if quizzed else 0, quiz_score, quiz_score
    ))
    conn.commit()
    conn.close()
    return "출석 기록 완료!"


def get_attendance_data():
    """출석 데이터를 불러옵니다."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT date, studied, quizzed, quiz_score FROM attendance ORDER BY date")
        rows = cursor.fetchall()
        conn.close()
        return [{"date": r[0], "studied": r[1], "quizzed": r[2], "quiz_score": r[3]} for r in rows]
    except Exception:
        return []


@tool
def save_today_questions(questions: list):
    """
    오늘 수업에서 다룬 문제 목록을 State에 저장합니다.
    quiz_agent가 이 문제들을 우선 출제합니다.
    """
    from langgraph.types import Command
    return Command(update={"today_questions": questions})


@tool
def load_today_questions():
    """오늘 학습할 문제 목록을 DB에서 불러옵니다."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT questions FROM daily_questions WHERE date = ?", (str(date.today()),))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return []
    return json.loads(row[0])


@tool
def save_today_questions(questions: list):
    """오늘 학습할 문제 목록을 DB에 저장합니다."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO daily_questions (date, questions)
        VALUES (?, ?)
        ON CONFLICT(date) DO UPDATE SET questions = ?
    """, (str(date.today()), json.dumps(questions, ensure_ascii=False), json.dumps(questions, ensure_ascii=False)))
    conn.commit()
    conn.close()
    return f"{len(questions)}개 문제가 저장됐어요!"


@tool
def save_daily_plan_questions(daily_map: dict):
    """
    플래너가 일차별로 배정한 문제를 날짜별로 DB에 저장합니다.
    Args:
        daily_map: {"2025-11-01": [문제목록], "2025-11-02": [...]} 형식
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    for target_date, questions in daily_map.items():
        cursor.execute("""
            INSERT INTO daily_questions (date, questions)
            VALUES (?, ?)
            ON CONFLICT(date) DO UPDATE SET questions = ?
        """, (target_date, json.dumps(questions, ensure_ascii=False), json.dumps(questions, ensure_ascii=False)))
    conn.commit()
    conn.close()
    return f"{len(daily_map)}일치 문제가 배정됐어요!"