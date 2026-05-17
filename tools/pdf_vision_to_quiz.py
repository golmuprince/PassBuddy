import os
import sys
import json
import base64
import argparse
from pdf2image import convert_from_path
from openai import OpenAI


def get_client():
    return OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


def image_to_base64(image) -> str:
    import io
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def extract_questions_from_image(image, cert_name: str, page_num: int) -> list:
    image_b64 = image_to_base64(image)

    prompt = f"""이 이미지는 {cert_name} 기출문제입니다.
이미지에서 시험 문제를 찾아 아래 JSON 형식으로 추출해주세요.
문제가 없으면 빈 배열 []을 반환하세요.

반환 형식 (순수 JSON 배열만, 코드블록 없이):
[
  {{
    "topic": "문제 주제 또는 단원명",
    "question": "문제 전체 내용",
    "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
    "correct_answer": "A",
    "explanation": "해설 (있으면 포함, 없으면 빈 문자열)"
  }}
]

주의사항:
- 보기가 4개 또는 5개인 객관식 문제만 추출
- ① ② ③ ④ ⑤ 형식은 A) B) C) D) E) 로 변환
- 이미지 속 표, 명령어, 특수문자도 정확히 포함
- 정답이 보이면 correct_answer에, 없으면 빈 문자열
- JSON 배열만 반환
"""

    try:
        response = get_client().chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}", "detail": "high"}},
                    {"type": "text", "text": prompt}
                ]
            }],
            max_tokens=2000,
            temperature=0,
        )
        content = response.choices[0].message.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        questions = json.loads(content)
        if isinstance(questions, list):
            return [q for q in questions if isinstance(q, dict) and len(q.get("options", [])) >= 4]
        return []
    except json.JSONDecodeError:
        print(f"  ⚠ 페이지 {page_num}: JSON 파싱 실패")
        return []
    except Exception as e:
        print(f"  ⚠ 페이지 {page_num}: 오류 - {e}")
        return []


def extract_answers_from_image(image, page_num: int) -> dict:
    image_b64 = image_to_base64(image)
    prompt = """이 이미지는 시험 답안지입니다.
문제 번호와 정답을 추출해서 아래 JSON 형식으로 반환하세요.
반환 형식 (순수 JSON만, 코드블록 없이):
{"1": "A", "2": "C", "3": "B", ...}
- ①②③④⑤ → A/B/C/D/E 변환
- 1/2/3/4/5 숫자도 A/B/C/D/E로 변환
"""
    try:
        response = get_client().chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}", "detail": "high"}},
                    {"type": "text", "text": prompt}
                ]
            }],
            max_tokens=1000,
            temperature=0,
        )
        content = response.choices[0].message.content.strip()
        if "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
            if content.startswith("json"):
                content = content[4:].strip()
        return json.loads(content)
    except Exception as e:
        print(f"  ⚠ 페이지 {page_num}: {e}")
        return {}


def pdf_to_images(pdf_path: str, pages: str = None):
    if pages:
        if "-" in pages:
            start, end = pages.split("-")
            return convert_from_path(pdf_path, first_page=int(start), last_page=int(end), dpi=150)
        else:
            page_list = [int(p) for p in pages.split(",")]
            return convert_from_path(pdf_path, first_page=min(page_list), last_page=max(page_list), dpi=150)
    return convert_from_path(pdf_path, dpi=150)


def deduplicate(existing: list, new_questions: list) -> list:
    existing_set = {q["question"].strip()[:50] for q in existing}
    result = []
    for q in new_questions:
        key = q.get("question", "").strip()[:50]
        if key and key not in existing_set:
            result.append(q)
            existing_set.add(key)
    return result


def extract_from_pdf(pdf_path: str, cert_name: str, pages: str = None) -> int:
    output_path = f"data/{cert_name}_quiz.json"
    os.makedirs("data", exist_ok=True)

    print(f"PDF 변환 중: {pdf_path}")
    images = pdf_to_images(pdf_path, pages)
    print(f"총 {len(images)}페이지 처리 중...")

    all_new = []
    for i, image in enumerate(images, 1):
        print(f"  페이지 {i}/{len(images)}...", end=" ")
        questions = extract_questions_from_image(image, cert_name, i)
        print(f"{len(questions)}문제 추출")
        all_new.extend(questions)

    existing = []
    if os.path.exists(output_path):
        with open(output_path, "r", encoding="utf-8") as f:
            existing = json.load(f)

    unique_new = deduplicate(existing, all_new)
    all_questions = existing + unique_new
    for i, q in enumerate(all_questions, 1):
        q["number"] = i

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_questions, f, ensure_ascii=False, indent=2)

    print(f"✅ {len(unique_new)}개 추가 (총 {len(all_questions)}개)")
    return len(unique_new)


def merge_answers_to_quiz(cert_name: str, answers: dict) -> int:
    quiz_path = f"data/{cert_name}_quiz.json"
    if not os.path.exists(quiz_path):
        return 0
    with open(quiz_path, "r", encoding="utf-8") as f:
        questions = json.load(f)
    updated = 0
    for q in questions:
        q_num = str(q.get("number", ""))
        if q_num in answers:
            q["correct_answer"] = answers[q_num]
            updated += 1
    with open(quiz_path, "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)
    return updated


def extract_answers_from_pdf(pdf_path: str, cert_name: str, pages: str = None) -> int:
    images = pdf_to_images(pdf_path, pages)
    print(f"답안지 {len(images)}페이지 처리 중...")
    all_answers = {}
    for i, image in enumerate(images, 1):
        print(f"  페이지 {i}/{len(images)}...", end=" ")
        answers = extract_answers_from_image(image, i)
        print(f"{len(answers)}개 정답 추출")
        all_answers.update(answers)
    updated = merge_answers_to_quiz(cert_name, all_answers)
    print(f"✅ {updated}개 문제에 정답 업데이트")
    return updated


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--cert", required=True)
    parser.add_argument("--pages", default=None)
    args = parser.parse_args()
    extract_from_pdf(args.pdf, args.cert, args.pages)