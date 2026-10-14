from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from fastapi.testclient import TestClient

from webgal_backend.storage import JobStore, write_json
from webgal_backend.teacher_ecosystem import build_publication_payload
from webgal_backend.validators import ValidationFailure, semantic_quiz_plan, validate_schema


def _question(question_id: str, question_type: str) -> dict:
    if question_type == "judgement":
        options = [{"id": "A", "text": "正确"}, {"id": "B", "text": "错误"}]
    else:
        options = [
            {"id": "A", "text": "选项一"},
            {"id": "B", "text": "选项二"},
            {"id": "C", "text": "选项三"},
            {"id": "D", "text": "选项四"},
        ]
    return {
        "id": question_id,
        "type": question_type,
        "prompt": f"第 {question_id} 题",
        "options": options,
        "correct_option_ids": ["A"],
        "explanation": "答案来自教学材料。",
        "knowledge_point": "关键知识点",
        "difficulty": "基础",
        "teaching_tip": "请学生说明判断依据。",
    }


def _quiz_plan() -> dict:
    return {
        "title": "课堂讲评练",
        "introduction": "用于检查学生对关键知识点的理解。",
        "questions": [
            _question("q1", "single_choice"),
            _question("q2", "judgement"),
            _question("q3", "single_choice"),
            _question("q4", "judgement"),
        ],
    }


class TeacherEcosystemQuizTests(unittest.TestCase):
    def test_quiz_contract_accepts_both_supported_card_types(self) -> None:
        plan = _quiz_plan()

        validate_schema("quiz_plan.schema.json", plan)
        semantic_quiz_plan(plan)

    def test_quiz_contract_rejects_malformed_judgement_card(self) -> None:
        plan = _quiz_plan()
        plan["questions"][1]["options"][1]["text"] = "不正确"

        with self.assertRaisesRegex(ValidationFailure, "must be 正确 and 错误"):
            semantic_quiz_plan(plan)

    def test_publication_payload_uses_lesson_metadata_and_generated_cover(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp)
            state_dir = job_dir / "state"
            background_dir = job_dir / "public" / "game" / "background"
            state_dir.mkdir(parents=True)
            background_dir.mkdir(parents=True)
            (state_dir / "narrative_plan.json").write_text(
                '{"title":"叙事标题","theme":"理解选择的后果","emotion_tone":"克制"}',
                encoding="utf-8",
            )
            (background_dir / "title_cover.webp").write_bytes(b"cover")

            payload = build_publication_payload(
                job={
                    "id": "a" * 32,
                    "options": {
                        "classroom_topic": "孔乙己人物分析",
                        "grade": "九年级语文",
                        "narrative_mode": "角色扮演",
                    },
                },
                job_dir=job_dir,
                user={"id": "user-1", "nickname": "林老师", "email": "teacher@example.com"},
                frontend_url="https://example.com/narrativeos/",
            )

        self.assertEqual(payload["title"], "孔乙己人物分析")
        self.assertEqual(payload["subject"], "语文")
        self.assertEqual(payload["authorName"], "林老师")
        self.assertEqual(payload["playUrl"], f"https://example.com/narrativeos/play/{'a' * 32}/")
        self.assertIsNone(payload["quizUrl"])
        self.assertEqual(
            payload["coverUrl"],
            f"https://example.com/narrativeos/play/{'a' * 32}/game/background/title_cover.webp",
        )

    def test_publication_payload_exposes_practice_only_after_quiz_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp)
            state_dir = job_dir / "state"
            state_dir.mkdir(parents=True)
            (state_dir / "quiz_plan.json").write_text("{}", encoding="utf-8")

            payload = build_publication_payload(
                job={"id": "b" * 32, "options": {"classroom_topic": "课堂作品"}},
                job_dir=job_dir,
                user={"id": "user-1", "email": "teacher@example.com"},
                frontend_url="https://example.com/narrativeos/",
            )

        self.assertEqual(payload["quizUrl"], f"https://example.com/narrativeos/practice/{'b' * 32}/")

    def test_published_quiz_is_readable_without_the_owner_session(self) -> None:
        import webgal_backend.app as backend_app

        original_store = backend_app.store
        try:
            with tempfile.TemporaryDirectory() as tmp, patch.dict(
                "os.environ",
                {"WEBGAL_AUTH_MODE": "invite", "WEBGAL_INVITE_CODES": "owner-code"},
                clear=False,
            ):
                backend_app.store = JobStore(Path(tmp) / "jobs")
                job = backend_app.store.create(
                    "lesson",
                    {},
                    identity={"type": "invite", "invite_code": "owner-code"},
                )
                job_dir = backend_app.store.job_dir(job["id"])
                (job_dir / "public" / "game" / "config.txt").write_text("Game_name: test", encoding="utf-8")
                write_json(job_dir / "state" / "quiz_plan.json", _quiz_plan())

                response = TestClient(backend_app.app).get(f"/public/jobs/{job['id']}/quiz")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], "READY")
            self.assertFalse(response.json()["can_manage"])
            self.assertEqual(response.json()["quiz"]["title"], "课堂讲评练")
        finally:
            backend_app.store = original_store


if __name__ == "__main__":
    unittest.main()
