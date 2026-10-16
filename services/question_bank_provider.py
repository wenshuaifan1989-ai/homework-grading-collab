"""Small, replaceable local QuestionAsset provider for 013."""

from __future__ import annotations

import hashlib
import json
from difflib import SequenceMatcher
from pathlib import Path
from typing import Protocol

from sqlalchemy import func,or_
from sqlalchemy.orm import Session

from models.paper import QuestionAsset


PROVIDER_NAME = "local_question_asset"
PROVIDER_VERSION = "013-local-jsonl-v1"
RIGHTS_BASES = {"PROJECT_AUTHORED", "OPEN_LICENSE", "TEACHER_AUTHORIZED"}
LOCAL_DATASET = (
    Path(__file__).resolve().parents[1]
    / "数据"
    / "题库"
    / "数学七年级_原创练习_v1.jsonl"
)


class QuestionBankProvider(Protocol):
    name: str
    version: str

    def search_questions(
        self, db: Session, *, subject: str, grade: str, query: str = "",
        difficulty: str | None = None, limit: int = 100, teacher_id: int | None = None,
    ) -> list[QuestionAsset]: ...

    def get_question(self, db: Session, asset_id: int, teacher_id: int | None = None) -> QuestionAsset | None: ...

    def find_similar(
        self, db: Session, *, subject: str, grade: str, question_text: str,
        limit: int = 10,
    ) -> list[QuestionAsset]: ...


def question_fingerprint(
    *, subject: str, grade: str, question_text: str,
    question_type: str | None, options: list | dict | None, correct_answer: str,
) -> str:
    payload = {
        "subject": subject.strip().casefold(),
        "grade": grade.strip().casefold(),
        "text": " ".join(question_text.split()).casefold(),
        "type": (question_type or "").strip().casefold(),
        "options": options,
        "answer": " ".join(correct_answer.split()).casefold(),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class LocalQuestionAssetProvider:
    """Queries only provenance-bearing QuestionAsset rows; never ingests student scans."""
    @staticmethod
    def readable(asset, teacher_id):
        return asset.source != 'teacher_v2' or (teacher_id is not None and
            (asset.rights_reference or '').startswith(f'teacher:{teacher_id}:'))

    name = PROVIDER_NAME
    version = PROVIDER_VERSION

    def search_questions(
        self, db: Session, *, subject: str, grade: str, query: str = "",
        difficulty: str | None = None, limit: int = 100, teacher_id: int | None = None,
    ) -> list[QuestionAsset]:
        rows = db.query(QuestionAsset).filter(
            or_(QuestionAsset.source!='teacher_v2',QuestionAsset.rights_reference.like(f'teacher:{teacher_id}:%'))
                if teacher_id is not None else QuestionAsset.source!='teacher_v2',
            QuestionAsset.subject == subject.strip().lower(),
            QuestionAsset.grade == grade.strip().lower(),
            QuestionAsset.rights_basis.in_(sorted(RIGHTS_BASES)),
            QuestionAsset.rights_reference.is_not(None),
            func.trim(QuestionAsset.rights_reference) != "",
            func.trim(QuestionAsset.question_text) != "",
            func.trim(QuestionAsset.correct_answer) != "",
            func.trim(QuestionAsset.analysis) != "",
            QuestionAsset.review_status.in_(["PENDING_REVIEW", "CONFIRMED"]),
        ).order_by(QuestionAsset.id).limit(max(1, min(limit, 200))).all()
        rows = [row for row in rows if self.readable(row,teacher_id)]
        needle = query.strip().casefold()
        if needle:
            rows = [row for row in rows if needle in (row.question_text or "").casefold()
                    or any(needle in str(point).casefold() for point in (row.knowledge_points_json or []))]
        if difficulty:
            rows = [row for row in rows if row.difficulty == difficulty]
        return rows[:max(1, min(limit, 200))]

    def get_question(self, db: Session, asset_id: int, teacher_id: int | None = None) -> QuestionAsset | None:
        asset = db.query(QuestionAsset).filter(
            QuestionAsset.id == asset_id,
            QuestionAsset.rights_basis.in_(sorted(RIGHTS_BASES)),
            QuestionAsset.rights_reference.is_not(None),
            func.trim(QuestionAsset.rights_reference) != "",
            func.trim(QuestionAsset.question_text) != "",
            func.trim(QuestionAsset.correct_answer) != "",
            func.trim(QuestionAsset.analysis) != "",
            QuestionAsset.review_status.in_(["PENDING_REVIEW", "CONFIRMED"]),
        ).first()
        return asset if asset and self.readable(asset,teacher_id) else None

    def find_similar(
        self, db: Session, *, subject: str, grade: str, question_text: str,
        limit: int = 10,
    ) -> list[QuestionAsset]:
        candidates = self.search_questions(db, subject=subject, grade=grade, limit=200)
        needle = " ".join(question_text.split()).casefold()
        ranked = sorted(
            candidates,
            key=lambda row: SequenceMatcher(
                None, needle, " ".join((row.question_text or "").split()).casefold()
            ).ratio(),
            reverse=True,
        )
        return ranked[:max(1, min(limit, 50))]


def import_local_original_questions(db: Session, *, subject: str, grade: str) -> dict[str, int]:
    """Idempotently import the versioned project-authored JSONL as pending assets."""
    if not LOCAL_DATASET.is_file():
        raise FileNotFoundError("local original question dataset is missing")
    wanted_subject = subject.strip().lower()
    wanted_grade = grade.strip().lower()
    created = reused = 0
    seen_ids: set[str] = set()
    lines = LOCAL_DATASET.read_text(encoding="utf-8").splitlines()
    for line_no, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item, dict):
            raise ValueError(f"question record must be a JSON object at line {line_no}")
        item_id = str(item.get("item_id", "")).strip()
        string_fields = ["subject", "grade", "question_text", "question_type", "correct_answer",
                         "analysis", "difficulty", "rights_basis", "rights_reference"]
        if (
            not item_id or len(item_id) > 100 or item_id in seen_ids
            or any(not isinstance(item.get(key), str) or not item[key].strip() for key in string_fields)
            or not isinstance(item.get("knowledge_points"), list)
            or not item["knowledge_points"]
            or any(not isinstance(point, str) or not point.strip() for point in item["knowledge_points"])
            or (item.get("options") is not None and not isinstance(item.get("options"), (list, dict)))
            or (isinstance(item.get("options"), list) and any(not isinstance(value, str) for value in item["options"]))
            or (isinstance(item.get("options"), dict) and any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in item["options"].items()
            ))
        ):
            raise ValueError(f"invalid local question record at line {line_no}")
        seen_ids.add(item_id)
        if item["rights_basis"] != "PROJECT_AUTHORED":
            raise ValueError(f"unapproved rights basis in local question record at line {line_no}")
        if (
            len(item["subject"]) > 40 or len(item["grade"]) > 40
            or len(item["question_type"]) > 40 or len(item["rights_reference"]) > 255
            or item["difficulty"] not in {"easy", "medium", "hard"}
        ):
            raise ValueError(f"question record has an invalid field or difficulty at line {line_no}")
        if item["subject"].strip().lower() != wanted_subject or item["grade"].strip().lower() != wanted_grade:
            continue
        if (
            len(item["question_text"]) > 12000 or len(item["correct_answer"]) > 6000
            or len(item["analysis"]) > 12000
            or any(len(point) > 200 for point in item["knowledge_points"])
        ):
            raise ValueError(f"question record exceeds field limits at line {line_no}")
        fingerprint = question_fingerprint(
            subject=item["subject"], grade=item["grade"], question_text=item["question_text"],
            question_type=item["question_type"], options=item.get("options"),
            correct_answer=item["correct_answer"],
        )
        existing = db.query(QuestionAsset).filter_by(content_fingerprint=fingerprint).first()
        if existing is not None:
            if existing.rights_basis not in RIGHTS_BASES or not existing.rights_reference:
                raise ValueError("a local question fingerprint collides with an asset lacking usage rights")
            reused += 1
            continue
        db.add(QuestionAsset(
            subject=wanted_subject,
            grade=wanted_grade,
            question_text=item["question_text"].strip(),
            question_type=item["question_type"].strip(),
            options_json=item.get("options"),
            correct_answer=item["correct_answer"].strip(),
            analysis=item["analysis"].strip(),
            difficulty=item["difficulty"],
            knowledge_points_json=item["knowledge_points"],
            confidence=1.0,
            source="local_jsonl",
            asset_version=PROVIDER_VERSION,
            rights_basis=item["rights_basis"],
            rights_reference=f"数据/题库/数学七年级_原创练习_v1.jsonl#{item_id}",
            review_status="PENDING_REVIEW",
            clean_image_status="NOT_REQUIRED",
            content_fingerprint=fingerprint,
        ))
        created += 1
    db.flush()
    return {"created": created, "reused": reused, "total_in_dataset": len(seen_ids)}


question_bank_provider: QuestionBankProvider = LocalQuestionAssetProvider()
