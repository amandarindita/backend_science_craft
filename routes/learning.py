import json
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from extensions import db
from models import (
    Badge,
    Checkpoint,
    Material,
    Notification,
    Question,
    SubMaterial,
    User,
    UserBadge,
    UserCheckpointProgress,
    UserLabResult,
    UserProgress,
    UserSubMaterialProgress,
)
from services.streak_service import mark_daily_activity
from milestone_service import sync_user_milestones


learning_bp = Blueprint("learning", __name__)

LEARNING_MODES = {
    "read": "Baca",
    "listen": "Dengarkan",
    "visual": "Visual",
}

QUIZ_PASSING_SCORE = 75
CHECKPOINT_XP = 10
QUIZ_XP = 40
LAB_XP = 50
XP_PER_GAMIFICATION_LEVEL = 200


JAKARTA_TZ = timezone(timedelta(hours=7))

CATEGORY_BADGES = {
    "Biologi": "Darwin’s Successor",
    "Fisika": "Quantum Overlord",
    "Kimia": "The Modern Alchemist",
}


def award_badge(user_id, badge_name):
    """
    Memberikan badge secara idempotent.

    Helper ini tidak melakukan commit sendiri agar seluruh perubahan
    progress, XP, badge, dan notifikasi tetap berada dalam satu transaksi.
    """
    badge = db.session.scalar(
        db.select(Badge).where(
            Badge.name == badge_name
        )
    )

    if not badge:
        return False

    existing = db.session.scalar(
        db.select(UserBadge).where(
            UserBadge.user_id == user_id,
            UserBadge.badge_id == badge.id,
        )
    )

    if existing:
        return False

    db.session.add(UserBadge(
        user_id=user_id,
        badge_id=badge.id,
        unlocked_at=utcnow(),
    ))

    db.session.add(Notification(
        user_id=user_id,
        title="Badge Baru Terbuka! 🎉",
        message=(
            "Selamat! Kamu berhasil mendapatkan "
            f"pencapaian '{badge.name}'."
        ),
    ))

    # Membuat insert pending terlihat oleh pengecekan badge berikutnya
    # pada transaksi yang sama.
    db.session.flush()
    return True


def add_badge_if_new(
    collected_badges,
    user_id,
    badge_name,
):
    if award_badge(user_id, badge_name):
        collected_badges.append(badge_name)


def award_streak_badge(
    collected_badges,
    user_id,
):
    user = db.session.get(User, user_id)

    if user and int(user.streak_count or 0) >= 7:
        add_badge_if_new(
            collected_badges,
            user_id,
            "Lab Regular",
        )


def award_night_owl_badge(
    collected_badges,
    user_id,
):
    current_hour = datetime.now(
        JAKARTA_TZ
    ).hour

    if current_hour >= 22 or current_hour <= 3:
        add_badge_if_new(
            collected_badges,
            user_id,
            "Night Owl",
        )


def award_module_badges(
    user_id,
    material_id,
    include_night_owl=False,
):
    new_badges = []

    db.session.flush()

    completed_module_count = (
        db.session.scalar(
            db.select(
                db.func.count(
                    UserProgress.id
                )
            ).where(
                UserProgress.user_id
                == user_id,
                UserProgress.progress >= 1.0,
            )
        )
        or 0
    )

    if completed_module_count >= 1:
        add_badge_if_new(
            new_badges,
            user_id,
            "First Spark",
        )

    if include_night_owl:
        award_night_owl_badge(
            new_badges,
            user_id,
        )

    award_streak_badge(
        new_badges,
        user_id,
    )

    material = db.session.get(
        Material,
        material_id,
    )

    if not material:
        return new_badges

    category_badge = CATEGORY_BADGES.get(
        material.category
    )

    if not category_badge:
        return new_badges

    total_category_modules = (
        db.session.scalar(
            db.select(
                db.func.count(Material.id)
            ).where(
                Material.category
                == material.category,
                Material.is_required.is_(True),
                Material.is_published.is_(True),
            )
        )
        or 0
    )

    completed_category_modules = (
        db.session.scalar(
            db.select(
                db.func.count(
                    UserProgress.id
                )
            )
            .join(
                Material,
                UserProgress.material_id
                == Material.id,
            )
            .where(
                UserProgress.user_id
                == user_id,
                UserProgress.progress >= 1.0,
                Material.category
                == material.category,
                Material.is_required.is_(True),
                Material.is_published.is_(True),
            )
        )
        or 0
    )

    if (
        total_category_modules > 0
        and completed_category_modules
        >= total_category_modules
    ):
        add_badge_if_new(
            new_badges,
            user_id,
            category_badge,
        )

    return new_badges


def award_quiz_badges(
    user_id,
    score,
    is_first_pass,
):
    new_badges = []

    db.session.flush()

    if int(score) == 100 and is_first_pass:
        add_badge_if_new(
            new_badges,
            user_id,
            "Grand Analyst",
        )

    perfect_quiz_count = (
        db.session.scalar(
            db.select(
                db.func.count(
                    UserProgress.id
                )
            ).where(
                UserProgress.user_id
                == user_id,
                UserProgress.quiz_completed
                .is_(True),
                UserProgress.quiz_score == 100,
            )
        )
        or 0
    )

    if perfect_quiz_count >= 3:
        add_badge_if_new(
            new_badges,
            user_id,
            "Flawless Victory",
        )

    award_night_owl_badge(
        new_badges,
        user_id,
    )
    award_streak_badge(
        new_badges,
        user_id,
    )

    return new_badges


def award_lab_badges(user_id):
    new_badges = []

    db.session.flush()

    completed_lab_count = (
        db.session.scalar(
            db.select(
                db.func.count(
                    UserProgress.id
                )
            )
            .join(
                Material,
                UserProgress.material_id
                == Material.id,
            )
            .where(
                UserProgress.user_id
                == user_id,
                UserProgress.lab_completed
                .is_(True),
                Material.unity_scene_id
                .is_not(None),
            )
        )
        or 0
    )

    if completed_lab_count >= 1:
        add_badge_if_new(
            new_badges,
            user_id,
            "Virtual Researcher",
        )

    if completed_lab_count >= 3:
        add_badge_if_new(
            new_badges,
            user_id,
            "Mad Scientist",
        )

    award_streak_badge(
        new_badges,
        user_id,
    )

    return new_badges


# =========================================================
# HELPERS
# =========================================================

def current_user_id():
    return int(get_jwt_identity())


def utcnow():
    return datetime.utcnow()


def read_json(value, default_value):
    if value in (None, ""):
        return default_value

    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default_value


def write_json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
    )


def normalize_scalar(value):
    """
    Menyamakan format jawaban sederhana:
    - A dan a dianggap sama
    - "true" dan True dianggap sama
    - angka dalam string dibandingkan sebagai angka
    """
    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return value

    if isinstance(value, str):
        cleaned = value.strip()

        if cleaned.lower() == "true":
            return True

        if cleaned.lower() == "false":
            return False

        try:
            if "." in cleaned:
                return float(cleaned)
            return int(cleaned)
        except ValueError:
            return cleaned.lower()

    return value


def normalize_structure(value, sort_lists=False):
    if isinstance(value, dict):
        return {
            str(key): normalize_structure(
                item,
                sort_lists=sort_lists,
            )
            for key, item in sorted(
                value.items(),
                key=lambda pair: str(pair[0]),
            )
        }

    if isinstance(value, list):
        normalized = [
            normalize_structure(
                item,
                sort_lists=sort_lists,
            )
            for item in value
        ]

        if sort_lists:
            return sorted(
                normalized,
                key=lambda item: json.dumps(
                    item,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )

        return normalized

    return normalize_scalar(value)


def extract_answer_value(value):
    """
    Mendukung beberapa bentuk answer_json:
    {"correct": true}
    {"answer": "A"}
    {"value": "A"}
    {"pairs": [...]}
    {"order": [...]}
    atau langsung berupa string/list/dict.
    """
    if not isinstance(value, dict):
        return value

    preferred_keys = (
        "correct",
        "answer",
        "value",
        "selected",
        "selected_id",
        "hotspot_id",
        "pairs",
        "order",
        "sequence",
    )

    for key in preferred_keys:
        if key in value:
            return value[key]

    return value


def is_answer_correct(checkpoint, submitted_answer):
    expected_raw = read_json(
        checkpoint.answer_json,
        {},
    )

    expected = extract_answer_value(
        expected_raw
    )

    submitted = extract_answer_value(
        submitted_answer
    )

    checkpoint_type = (
        checkpoint.checkpoint_type
        or ""
    ).strip().lower()

    if checkpoint_type == "matching":
        return normalize_structure(
            submitted,
            sort_lists=True,
        ) == normalize_structure(
            expected,
            sort_lists=True,
        )

    if checkpoint_type == "ordering":
        return normalize_structure(
            submitted,
            sort_lists=False,
        ) == normalize_structure(
            expected,
            sort_lists=False,
        )

    return normalize_structure(
        submitted,
        sort_lists=False,
    ) == normalize_structure(
        expected,
        sort_lists=False,
    )


def available_modes(submaterial):
    visual_data = read_json(
        submaterial.visual_data,
        {},
    )

    return {
        "read": bool(
            submaterial.read_content
        ),
        "listen": bool(
            submaterial.audio_url
            or submaterial.tts_text
            or submaterial.read_content
        ),
        "visual": bool(
            submaterial.visual_type
            or submaterial.image_url
            or visual_data
        ),
    }


def get_submaterial_progress(
    user_id,
    submaterial_id,
):
    return db.session.scalar(
        db.select(
            UserSubMaterialProgress
        ).where(
            UserSubMaterialProgress.user_id
            == user_id,
            UserSubMaterialProgress.submaterial_id
            == submaterial_id,
        )
    )


def get_or_create_submaterial_progress(
    user_id,
    submaterial_id,
):
    progress = get_submaterial_progress(
        user_id,
        submaterial_id,
    )

    now = utcnow()

    if progress:
        progress.last_accessed_at = now
        return progress

    progress = UserSubMaterialProgress(
        user_id=user_id,
        submaterial_id=submaterial_id,
        selected_mode=None,
        mode_completed=False,
        checkpoint_completed=False,
        is_completed=False,
        first_opened_at=now,
        last_accessed_at=now,
        completed_at=None,
    )

    db.session.add(progress)
    db.session.flush()

    return progress


def get_checkpoint_progress(
    user_id,
    checkpoint_id,
):
    return db.session.scalar(
        db.select(
            UserCheckpointProgress
        ).where(
            UserCheckpointProgress.user_id
            == user_id,
            UserCheckpointProgress.checkpoint_id
            == checkpoint_id,
        )
    )


def get_or_create_checkpoint_progress(
    user_id,
    checkpoint_id,
):
    progress = get_checkpoint_progress(
        user_id,
        checkpoint_id,
    )

    if progress:
        return progress

    progress = UserCheckpointProgress(
        user_id=user_id,
        checkpoint_id=checkpoint_id,
        attempts=0,
        is_completed=False,
        last_answer_json=None,
        completed_at=None,
        updated_at=utcnow(),
    )

    db.session.add(progress)
    db.session.flush()

    return progress


def get_or_create_material_progress(
    user_id,
    material_id,
):
    progress = db.session.scalar(
        db.select(UserProgress).where(
            UserProgress.user_id == user_id,
            UserProgress.material_id
            == material_id,
        )
    )

    if progress:
        return progress

    progress = UserProgress(
        user_id=user_id,
        material_id=material_id,
        progress=0.0,
        quiz_score=0,
        lab_completed=False,
        quiz_completed=False,
    )

    db.session.add(progress)
    db.session.flush()

    return progress


def required_checkpoints(submaterial_id):
    return db.session.execute(
        db.select(Checkpoint)
        .where(
            Checkpoint.submaterial_id
            == submaterial_id,
            Checkpoint.is_required.is_(True),
        )
        .order_by(
            Checkpoint.order_index.asc(),
            Checkpoint.id.asc(),
        )
    ).scalars().all()


def recalculate_submaterial_progress(
    user_id,
    submaterial_id,
):
    progress = get_or_create_submaterial_progress(
        user_id,
        submaterial_id,
    )

    checkpoints = required_checkpoints(
        submaterial_id
    )

    if not checkpoints:
        all_checkpoints_completed = True
    else:
        completed_checkpoint_ids = set(
            db.session.execute(
                db.select(
                    UserCheckpointProgress.checkpoint_id
                ).where(
                    UserCheckpointProgress.user_id
                    == user_id,
                    UserCheckpointProgress.checkpoint_id.in_(
                        [
                            item.id
                            for item in checkpoints
                        ]
                    ),
                    UserCheckpointProgress.is_completed
                    .is_(True),
                )
            ).scalars().all()
        )

        all_checkpoints_completed = all(
            item.id in completed_checkpoint_ids
            for item in checkpoints
        )

    progress.checkpoint_completed = (
        all_checkpoints_completed
    )

    was_completed = bool(
        progress.is_completed
    )

    progress.is_completed = bool(
        progress.mode_completed
        and progress.checkpoint_completed
    )

    if (
        progress.is_completed
        and not was_completed
    ):
        progress.completed_at = utcnow()

    if not progress.is_completed:
        progress.completed_at = None

    return progress


def required_published_submaterials(
    material_id,
):
    return db.session.execute(
        db.select(SubMaterial)
        .where(
            SubMaterial.material_id
            == material_id,
            SubMaterial.is_required.is_(True),
            SubMaterial.is_published.is_(True),
        )
        .order_by(
            SubMaterial.order_index.asc(),
            SubMaterial.id.asc(),
        )
    ).scalars().all()


def recalculate_material_progress(
    user_id,
    material_id,
):
    """
    Menghitung progres modul final.

    Komponen wajib:
    1. Seluruh submateri wajib selesai.
    2. Kuis lulus minimal 75, jika modul punya soal.
    3. Laboratorium selesai, jika modul punya Unity scene.

    UserProgress.progress menyimpan progres keseluruhan modul,
    bukan hanya progres membaca.
    """
    material = db.session.get(
        Material,
        material_id,
    )

    if not material:
        raise ValueError("Modul tidak ditemukan")

    material_progress = (
        get_or_create_material_progress(
            user_id,
            material_id,
        )
    )

    required_items = (
        required_published_submaterials(
            material_id
        )
    )

    question_count = db.session.scalar(
        db.select(
            db.func.count(Question.id)
        ).where(
            Question.material_id
            == material_id
        )
    ) or 0

    quiz_required = question_count > 0
    lab_required = bool(
        material.unity_scene_id
        and str(material.unity_scene_id).strip()
    )

    # Materi lama belum dipaksa mengikuti struktur baru.
    if not required_items:
        current_value = float(
            material_progress.progress or 0.0
        )

        quiz_passed = bool(
            material_progress.quiz_completed
            and int(
                material_progress.quiz_score or 0
            ) >= QUIZ_PASSING_SCORE
        )

        lab_completed = bool(
            material_progress.lab_completed
        )

        return {
            "progress": current_value,
            "learning_progress": current_value,
            "learning_completed": (
                current_value >= 1.0
            ),
            "completed_submaterials": 0,
            "total_submaterials": 0,
            "question_count": question_count,
            "quiz_required": quiz_required,
            "quiz_unlocked": True,
            "quiz_passed": quiz_passed,
            "quiz_score": int(
                material_progress.quiz_score or 0
            ),
            "quiz_passing_score": (
                QUIZ_PASSING_SCORE
            ),
            "lab_required": lab_required,
            # Step 8 — materi lama juga tidak boleh menjadi jalur bypass.
            # Progress lama >= 1 dianggap materi telah selesai.
            "lab_unlocked": bool(
                lab_required
                and current_value >= 1.0
                and (
                    quiz_passed
                    if quiz_required
                    else True
                )
            ),
            "lab_completed": lab_completed,
            "module_completed": (
                current_value >= 1.0
            ),
            "module_completion_xp_added": 0,
            "new_badges_unlocked": [],
            "legacy_mode": True,
        }

    completed_ids = set(
        db.session.execute(
            db.select(
                UserSubMaterialProgress
                .submaterial_id
            ).where(
                UserSubMaterialProgress.user_id
                == user_id,
                UserSubMaterialProgress.submaterial_id
                .in_(
                    [
                        item.id
                        for item in required_items
                    ]
                ),
                UserSubMaterialProgress.is_completed
                .is_(True),
            )
        ).scalars().all()
    )

    completed_count = sum(
        1
        for item in required_items
        if item.id in completed_ids
    )

    total_count = len(required_items)

    learning_progress = (
        completed_count / total_count
        if total_count > 0
        else 0.0
    )

    learning_completed = bool(
        total_count > 0
        and completed_count == total_count
    )

    quiz_passed = bool(
        material_progress.quiz_completed
        and int(
            material_progress.quiz_score or 0
        ) >= QUIZ_PASSING_SCORE
    )

    lab_completed = bool(
        material_progress.lab_completed
    )

    # ==========================================
    # LOGIKA BARU: PROGRESS NAIK TIAP ACTIVITY SELESAI
    # ==========================================
    total_components = total_count
    completed_components = completed_count

    if quiz_required:
        total_components += 1
        if quiz_passed:
            completed_components += 1

    if lab_required:
        total_components += 1
        if lab_completed:
            completed_components += 1

    overall_progress = (
        completed_components / total_components
        if total_components > 0
        else 0.0
    )

    previous_overall_progress = float(
        material_progress.progress or 0.0
    )

    # 2. Simpan progress baru ke database
    material_progress.progress = round(
        overall_progress,
        4,
    )
    
    module_completed = (
        total_components > 0 
        and completed_components == total_components
    )

    # Penyelesaian modul tidak lagi memberi XP tambahan.
    # XP hanya berasal dari checkpoint, kuis, lab, dan Daily Quest.
    module_completion_xp_added = 0
    new_badges_unlocked = []

    if module_completed:
        new_badges_unlocked.extend(
            award_module_badges(
                user_id,
                material_id,
                include_night_owl=(
                    previous_overall_progress
                    < 1.0
                ),
            )
        )




    return {
        "progress": round(
            overall_progress,
            4,
        ),
        "learning_progress": round(
            learning_progress,
            4,
        ),
        "learning_completed": (
            learning_completed
        ),
        "completed_submaterials": (
            completed_count
        ),
        "total_submaterials": total_count,
        "question_count": question_count,
        "quiz_required": quiz_required,
        "quiz_unlocked": bool(
            learning_completed
            and quiz_required
        ),
        "quiz_passed": quiz_passed,
        "quiz_score": int(
            material_progress.quiz_score or 0
        ),
        "quiz_passing_score": (
            QUIZ_PASSING_SCORE
        ),
        "lab_required": lab_required,
        # Step 8 — Lab hanya terbuka setelah materi wajib selesai
        # dan kuis (jika ada) sudah lulus minimal nilai kelulusan.
        "lab_unlocked": bool(
            learning_completed
            and lab_required
            and (
                quiz_passed
                if quiz_required
                else True
            )
        ),
        "lab_completed": lab_completed,
        "module_completed": (
            module_completed
        ),
        "module_completion_xp_added": (
            module_completion_xp_added
        ),
        "new_badges_unlocked": (
            new_badges_unlocked
        ),
        "legacy_mode": False,
    }

def calculate_level_target_xp(target_level):
    """
    Menghitung total XP minimum dari seluruh modul wajib 
    pada level-level sebelumnya secara kumulatif.
    """
    cumulative_xp = 0
    # Cek dari level 1 sampai level sebelum target
    for lvl in range(1, target_level):
        materials = db.session.execute(
            db.select(Material)
            .where(
                Material.level == lvl,
                Material.is_required.is_(True),
                Material.is_published.is_(True),
            )
        ).scalars().all()

        for mat in materials:
            # Hitung jumlah checkpoint wajib di modul ini (10 XP per checkpoint)
            checkpoints_count = db.session.scalar(
                db.select(db.func.count(Checkpoint.id))
                .join(SubMaterial, Checkpoint.submaterial_id == SubMaterial.id)
                .where(
                    SubMaterial.material_id == mat.id,
                    Checkpoint.is_required.is_(True)
                )
            ) or 0
            cumulative_xp += checkpoints_count * CHECKPOINT_XP

            # Cek apakah modul punya kuis (40 XP)
            question_count = db.session.scalar(
                db.select(db.func.count(Question.id))
                .where(Question.material_id == mat.id)
            ) or 0
            if question_count > 0:
                cumulative_xp += QUIZ_XP

            # Cek apakah modul punya lab (50 XP)
            if mat.unity_scene_id and str(mat.unity_scene_id).strip():
                cumulative_xp += LAB_XP

    return cumulative_xp

def is_level_unlocked(user_id, target_level):
    """
    Level terbuka jika total XP user sudah mencapai 
    target akumulasi XP dari level-level sebelumnya.
    """
    if target_level <= 1:
        return True

    user = db.session.get(User, user_id)
    if not user:
        return False

    user_xp = int(user.total_xp or 0)
    required_xp = calculate_level_target_xp(target_level)

    return user_xp >= required_xp

def checkpoint_for_student(
    checkpoint,
    progress=None,
):
    return {
        "id": checkpoint.id,
        "submaterial_id": (
            checkpoint.submaterial_id
        ),
        "checkpoint_type": (
            checkpoint.checkpoint_type
        ),
        "title": checkpoint.title,
        "instruction": checkpoint.instruction,
        "question_text": (
            checkpoint.question_text
        ),
        "content": read_json(
            checkpoint.content_json,
            {},
        ),
        "image_url": checkpoint.image_url,
        "order_index": checkpoint.order_index,
        "is_required": checkpoint.is_required,
        "attempts": (
            progress.attempts
            if progress
            else 0
        ),
        "is_completed": bool(
            progress
            and progress.is_completed
        ),
    }


def submaterial_for_student(
    submaterial,
    user_id,
):
    progress = get_submaterial_progress(
        user_id,
        submaterial.id,
    )

    checkpoints = db.session.execute(
        db.select(Checkpoint)
        .where(
            Checkpoint.submaterial_id
            == submaterial.id
        )
        .order_by(
            Checkpoint.order_index.asc(),
            Checkpoint.id.asc(),
        )
    ).scalars().all()

    checkpoint_items = []

    for checkpoint in checkpoints:
        checkpoint_progress = (
            get_checkpoint_progress(
                user_id,
                checkpoint.id,
            )
        )

        checkpoint_items.append(
            checkpoint_for_student(
                checkpoint,
                checkpoint_progress,
            )
        )

    return {
        "id": submaterial.id,
        "material_id": (
            submaterial.material_id
        ),
        "title": submaterial.title,
        "order_index": (
            submaterial.order_index
        ),
        "read_content": (
            submaterial.read_content
        ),
        "tts_text": submaterial.tts_text,
        "audio_url": submaterial.audio_url,
        "visual_type": (
            submaterial.visual_type
        ),
        "visual_data": read_json(
            submaterial.visual_data,
            {},
        ),
        "summary": submaterial.summary,
        "image_url": submaterial.image_url,
        "is_required": (
            submaterial.is_required
        ),
        "available_modes": (
            available_modes(submaterial)
        ),
        "progress": {
            "selected_mode": (
                progress.selected_mode
                if progress
                else None
            ),
            "mode_completed": bool(
                progress
                and progress.mode_completed
            ),
            "checkpoint_completed": bool(
                progress
                and progress.checkpoint_completed
            ),
            "is_completed": bool(
                progress
                and progress.is_completed
            ),
            "first_opened_at": (
                progress.first_opened_at
                .strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                if (
                    progress
                    and progress.first_opened_at
                )
                else None
            ),
            "completed_at": (
                progress.completed_at
                .strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                if (
                    progress
                    and progress.completed_at
                )
                else None
            ),
        },
        "checkpoints": checkpoint_items,
    }


def module_for_student(
    material,
    user_id,
    include_submaterials=False,
):
    summary = recalculate_material_progress(
        user_id,
        material.id,
    )

    result = {
        "id": material.id,
        "title": material.title,
        "category": material.category,
        "level": material.level,
        "module_order": (
            material.module_order
        ),
        "short_description": (
            material.short_description
        ),
        "image_url": material.image_url,
        "unity_scene_id": (
            material.unity_scene_id
        ),
        "instructions": material.instructions,
        "is_required": material.is_required,
        "is_unlocked": is_level_unlocked(
            user_id,
            material.level,
        ),
        "progress": summary["progress"],
        "learning_progress": (
            summary["learning_progress"]
        ),
        "learning_completed": (
            summary["learning_completed"]
        ),
        "completed_submaterials": (
            summary[
                "completed_submaterials"
            ]
        ),
        "total_submaterials": (
            summary["total_submaterials"]
        ),
        "question_count": (
            summary["question_count"]
        ),
        "quiz_required": (
            summary["quiz_required"]
        ),
        "quiz_unlocked": (
            summary["quiz_unlocked"]
        ),
        "quiz_passed": (
            summary["quiz_passed"]
        ),
        "quiz_score": (
            summary["quiz_score"]
        ),
        "quiz_passing_score": (
            summary["quiz_passing_score"]
        ),
        "lab_required": (
            summary["lab_required"]
        ),
        "lab_unlocked": (
            summary["lab_unlocked"]
        ),
        "lab_completed": (
            summary["lab_completed"]
        ),
        "module_completed": (
            summary["module_completed"]
        ),
        "module_completion_xp_added": (
            summary[
                "module_completion_xp_added"
            ]
        ),
        "new_badges_unlocked": (
            summary.get(
                "new_badges_unlocked",
                [],
            )
        ),
        "legacy_mode": (
            summary["legacy_mode"]
        ),
    }

    if include_submaterials:
        submaterials = db.session.execute(
            db.select(SubMaterial)
            .where(
                SubMaterial.material_id
                == material.id,
                SubMaterial.is_published
                .is_(True),
            )
            .order_by(
                SubMaterial.order_index.asc(),
                SubMaterial.id.asc(),
            )
        ).scalars().all()

        result["content"] = material.content

        result["submaterials"] = [
            submaterial_for_student(
                item,
                user_id,
            )
            for item in submaterials
        ]

    return result

def get_user_or_404(user_id):
    return db.session.get(
        User,
        user_id,
    )


def add_level_up_notification(
    user_id,
    old_xp,
    new_xp,
):
    old_level = (
        int(old_xp or 0)
        // XP_PER_GAMIFICATION_LEVEL
    ) + 1

    new_level = (
        int(new_xp or 0)
        // XP_PER_GAMIFICATION_LEVEL
    ) + 1

    if new_level > old_level:
        db.session.add(Notification(
            user_id=user_id,
            title="Hore! Level Naik! 🚀",
            message=(
                "Keren banget! Sekarang kamu "
                f"naik ke Level {new_level}!"
            ),
        ))

    return {
        "old_level": old_level,
        "new_level": new_level,
        "level_up": new_level > old_level,
    }


def question_for_student(question):
    return {
        "id": question.id,
        "material_id": question.material_id,
        "question_text": (
            question.question_text
        ),
        "question_type": (
            question.question_type
        ),
        "options": {
            "A": question.option_a,
            "B": question.option_b,
            "C": question.option_c,
            "D": question.option_d,
        },
    }


def normalize_quiz_answers(raw_answers):
    """
    Bentuk yang didukung:

    {"12": "A", "13": "C"}

    atau:

    [
        {"question_id": 12, "answer": "A"},
        {"question_id": 13, "answer": "C"}
    ]
    """
    normalized = {}

    if isinstance(raw_answers, dict):
        items = raw_answers.items()

        for question_id, answer in items:
            try:
                question_id = int(question_id)
            except (TypeError, ValueError):
                raise ValueError(
                    "Question ID tidak valid"
                )

            normalized[question_id] = (
                str(answer).strip().upper()
            )

        return normalized

    if isinstance(raw_answers, list):
        for item in raw_answers:
            if not isinstance(item, dict):
                raise ValueError(
                    "Format jawaban kuis tidak valid"
                )

            question_id = item.get(
                "question_id"
            )

            answer = item.get("answer")

            try:
                question_id = int(question_id)
            except (TypeError, ValueError):
                raise ValueError(
                    "Question ID tidak valid"
                )

            normalized[question_id] = (
                str(answer).strip().upper()
            )

        return normalized

    raise ValueError(
        "answers harus berupa object atau list"
    )


def get_submaterial_and_material(
    submaterial_id,
):
    submaterial = db.session.get(
        SubMaterial,
        submaterial_id,
    )

    if (
        not submaterial
        or not submaterial.is_published
    ):
        return None, None

    material = db.session.get(
        Material,
        submaterial.material_id,
    )

    if (
        not material
        or not material.is_published
    ):
        return None, None

    return submaterial, material


# =========================================================
# LEVEL DAN DAFTAR MODUL
# =========================================================

@learning_bp.route(
    "/levels",
    methods=["GET"],
)
@jwt_required()
def get_levels():
    user_id = current_user_id()

    result = []

    for level in (1, 2, 3):
        materials = db.session.execute(
            db.select(Material)
            .where(
                Material.level == level,
                Material.is_published.is_(True),
            )
            .order_by(
                Material.module_order.asc(),
                Material.id.asc(),
            )
        ).scalars().all()

        module_summaries = [
            recalculate_material_progress(
                user_id,
                item.id,
            )
            for item in materials
        ]

        structured_summaries = [
            item
            for item in module_summaries
            if not item["legacy_mode"]
        ]

        if structured_summaries:
            level_progress = sum(
                item["progress"]
                for item in structured_summaries
            ) / len(structured_summaries)
        else:
            level_progress = 0.0

        result.append({
            "level": level,
            "is_unlocked": (
                is_level_unlocked(
                    user_id,
                    level,
                )
            ),
            "module_count": len(materials),
            "progress": round(
                level_progress,
                4,
            ),
        })

    db.session.commit()

    return jsonify(result), 200


@learning_bp.route(
    "/modules",
    methods=["GET"],
)
@jwt_required()
def get_modules():
    user_id = current_user_id()

    statement = db.select(Material).where(
        Material.is_published.is_(True)
    )

    level = request.args.get("level")
    category = request.args.get("category")

    if level:
        try:
            level_number = int(level)
        except (TypeError, ValueError):
            return jsonify({
                "error": "Level harus berupa angka"
            }), 400

        if level_number not in {1, 2, 3}:
            return jsonify({
                "error": "Level harus 1, 2, atau 3"
            }), 400

        statement = statement.where(
            Material.level == level_number
        )

    if category:
        statement = statement.where(
            Material.category == category
        )

    materials = db.session.execute(
        statement.order_by(
            Material.level.asc(),
            Material.module_order.asc(),
            Material.id.asc(),
        )
    ).scalars().all()

    result = [
        module_for_student(
            material,
            user_id,
            include_submaterials=False,
        )
        for material in materials
    ]

    db.session.commit()

    return jsonify(result), 200


@learning_bp.route(
    "/module/<int:material_id>",
    methods=["GET"],
)
@jwt_required()
def get_module(material_id):
    user_id = current_user_id()

    material = db.session.get(
        Material,
        material_id,
    )

    if (
        not material
        or not material.is_published
    ):
        return jsonify({
            "error": "Modul tidak ditemukan"
        }), 404

    if not is_level_unlocked(
        user_id,
        material.level,
    ):
        return jsonify({
            "error": (
                "Level modul ini masih terkunci"
            ),
            "required_level": material.level,
        }), 403

    result = module_for_student(
        material,
        user_id,
        include_submaterials=True,
    )

    db.session.commit()

    return jsonify(result), 200


# =========================================================
# AKSES DAN PENYELESAIAN MODE BELAJAR
# =========================================================

@learning_bp.route(
    "/submaterial/<int:submaterial_id>/open",
    methods=["POST"],
)
@jwt_required()
def open_submaterial(submaterial_id):
    user_id = current_user_id()

    submaterial, material = (
        get_submaterial_and_material(
            submaterial_id
        )
    )

    if not submaterial:
        return jsonify({
            "error": "Submateri tidak ditemukan"
        }), 404

    if not is_level_unlocked(
        user_id,
        material.level,
    ):
        return jsonify({
            "error": "Level masih terkunci"
        }), 403

    data = request.get_json(silent=True) or {}
    selected_mode = data.get("mode")

    if (
        selected_mode is not None
        and selected_mode
        not in LEARNING_MODES
    ):
        return jsonify({
            "error": (
                "Mode harus read, listen, "
                "atau visual"
            )
        }), 400

    modes = available_modes(submaterial)

    if (
        selected_mode
        and not modes.get(
            selected_mode,
            False,
        )
    ):
        return jsonify({
            "error": (
                "Mode tersebut belum tersedia "
                "untuk submateri ini"
            )
        }), 400

    progress = (
        get_or_create_submaterial_progress(
            user_id,
            submaterial_id,
        )
    )

    if selected_mode:
        progress.selected_mode = (
            selected_mode
        )

    db.session.commit()

    return jsonify({
        "message": "Submateri berhasil dibuka",
        "submaterial_id": submaterial_id,
        "selected_mode": (
            progress.selected_mode
        ),
        "available_modes": modes,
        "first_opened_at": (
            progress.first_opened_at
            .strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            if progress.first_opened_at
            else None
        ),
    }), 200


@learning_bp.route(
    "/submaterial/<int:submaterial_id>/complete-mode",
    methods=["POST"],
)
@jwt_required()
def complete_learning_mode(submaterial_id):
    user_id = current_user_id()

    submaterial, material = (
        get_submaterial_and_material(
            submaterial_id
        )
    )

    if not submaterial:
        return jsonify({
            "error": "Submateri tidak ditemukan"
        }), 404

    if not is_level_unlocked(
        user_id,
        material.level,
    ):
        return jsonify({
            "error": "Level masih terkunci"
        }), 403

    data = request.get_json(silent=True) or {}
    selected_mode = data.get("mode")

    if selected_mode not in LEARNING_MODES:
        return jsonify({
            "error": (
                "Mode harus read, listen, "
                "atau visual"
            )
        }), 400

    modes = available_modes(submaterial)

    if not modes.get(
        selected_mode,
        False,
    ):
        return jsonify({
            "error": (
                "Mode tersebut belum tersedia "
                "untuk submateri ini"
            )
        }), 400

    progress = (
        get_or_create_submaterial_progress(
            user_id,
            submaterial_id,
        )
    )

    progress.selected_mode = selected_mode
    progress.mode_completed = True
    progress.last_accessed_at = utcnow()

    # Menyelesaikan Baca, Dengarkan, atau Visual
    # mengubah status hari ini menjadi hijau.
    mark_daily_activity(
        user_id,
        "active",
    )

    progress = (
        recalculate_submaterial_progress(
            user_id,
            submaterial_id,
        )
    )

    material_summary = (
        recalculate_material_progress(
            user_id,
            material.id,
        )
    )

    db.session.commit()

    return jsonify({
        "message": (
            "Mode belajar berhasil diselesaikan"
        ),
        "submaterial_id": submaterial_id,
        "selected_mode": selected_mode,
        "mode_label": (
            LEARNING_MODES[selected_mode]
        ),
        "mode_completed": True,
        "checkpoint_completed": (
            progress.checkpoint_completed
        ),
        "submaterial_completed": (
            progress.is_completed
        ),
        "module_progress": (
            material_summary["progress"]
        ),
        "module_completion_xp_added": (
            material_summary[
                "module_completion_xp_added"
            ]
        ),
        "new_badges_unlocked": (
            material_summary.get(
                "new_badges_unlocked",
                [],
            )
        ),
        "quiz_unlocked": (
            material_summary["quiz_unlocked"]
        ),
    }), 200


# =========================================================
# SUBMATERIAL TTS AUDIO (EDGE NEURAL TTS)
# =========================================================

@learning_bp.route(
    "/submaterial/<int:submaterial_id>/tts-audio",
    methods=["GET", "POST"],
)
@jwt_required(optional=True)
def get_submaterial_tts_audio(submaterial_id):
    submaterial, material = get_submaterial_and_material(submaterial_id)
    if not submaterial:
        return jsonify({
            "success": False,
            "error": "Submateri tidak ditemukan",
        }), 404

    if submaterial.audio_url and submaterial.audio_url.strip():
        return jsonify({
            "success": True,
            "audio_url": submaterial.audio_url,
            "source": "uploaded_audio",
            "voice": "custom",
            "title": submaterial.title,
        }), 200

    text_to_narrate = (
        submaterial.tts_text
        or submaterial.read_content
        or submaterial.title
        or ""
    ).strip()

    if not text_to_narrate:
        return jsonify({
            "success": False,
            "error": "Teks submateri kosong",
        }), 400

    try:
        from services.tts_service import generate_submaterial_tts, DEFAULT_VOICE
        from flask import current_app

        upload_folder = current_app.config.get("UPLOAD_FOLDER", "uploads")
        audio_rel_url = generate_submaterial_tts(
            submaterial_id=submaterial_id,
            text=text_to_narrate,
            upload_folder=upload_folder,
            voice=DEFAULT_VOICE,
        )

        return jsonify({
            "success": True,
            "audio_url": audio_rel_url,
            "source": "neural_tts",
            "voice": DEFAULT_VOICE,
            "title": submaterial.title,
        }), 200
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Gagal membuat audio TTS: {str(e)}",
        }), 500


# =========================================================
# SUBMIT CHECKPOINT
# =========================================================

@learning_bp.route(
    "/checkpoint/<int:checkpoint_id>/submit",
    methods=["POST"],
)
@jwt_required()
def submit_checkpoint(checkpoint_id):
    user_id = current_user_id()

    checkpoint = db.session.get(
        Checkpoint,
        checkpoint_id,
    )

    if not checkpoint:
        return jsonify({
            "error": "Checkpoint tidak ditemukan"
        }), 404

    submaterial, material = (
        get_submaterial_and_material(
            checkpoint.submaterial_id
        )
    )

    if not submaterial:
        return jsonify({
            "error": "Submateri tidak ditemukan"
        }), 404

    if not is_level_unlocked(
        user_id,
        material.level,
    ):
        return jsonify({
            "error": "Level masih terkunci"
        }), 403

    submaterial_progress = (
        get_or_create_submaterial_progress(
            user_id,
            submaterial.id,
        )
    )

    if not submaterial_progress.mode_completed:
        return jsonify({
            "error": (
                "Selesaikan salah satu mode "
                "belajar terlebih dahulu"
            )
        }), 403

    data = request.get_json(silent=True) or {}

    if "answer" not in data:
        return jsonify({
            "error": "Jawaban wajib dikirim"
        }), 400

    submitted_answer = data.get("answer")
    correct = is_answer_correct(
        checkpoint,
        submitted_answer,
    )

    checkpoint_progress = (
        get_or_create_checkpoint_progress(
            user_id,
            checkpoint_id,
        )
    )

    was_completed = bool(
        checkpoint_progress.is_completed
    )

    checkpoint_progress.attempts = (
        int(checkpoint_progress.attempts or 0)
        + 1
    )
    checkpoint_progress.last_answer_json = (
        write_json(submitted_answer)
    )
    checkpoint_progress.updated_at = utcnow()

    user = get_user_or_404(user_id)

    if not user:
        return jsonify({
            "error": "User tidak ditemukan"
        }), 404

    old_xp = int(user.total_xp or 0)
    xp_added = 0

    if correct:
        checkpoint_progress.is_completed = True

        if not checkpoint_progress.completed_at:
            checkpoint_progress.completed_at = (
                utcnow()
            )

        # XP hanya pada jawaban benar pertama.
        if not was_completed:
            user.total_xp = (
                old_xp + CHECKPOINT_XP
            )
            xp_added = CHECKPOINT_XP

    # Menjawab checkpoint termasuk aktivitas belajar.
    mark_daily_activity(
        user_id,
        "active",
    )

    submaterial_progress = (
        recalculate_submaterial_progress(
            user_id,
            submaterial.id,
        )
    )

    material_summary = (
        recalculate_material_progress(
            user_id,
            material.id,
        )
    )

    level_info = add_level_up_notification(
        user_id,
        old_xp,
        user.total_xp,
    )

    milestone_baru = sync_user_milestones(
        user,
        previous_xp=old_xp,
        notify_new=xp_added > 0,
    )

    db.session.commit()

    return jsonify({
        "message": (
            "Jawaban checkpoint diproses"
        ),
        "checkpoint_id": checkpoint.id,
        "is_correct": correct,
        "feedback": (
            checkpoint.correct_feedback
            if correct
            else checkpoint.wrong_feedback
        ),
        "attempts": (
            checkpoint_progress.attempts
        ),
        "checkpoint_completed": (
            checkpoint_progress.is_completed
        ),
        "is_first_completion": bool(
            correct and not was_completed
        ),
        "activity_xp_added": xp_added,
        "total_xp_added": xp_added,
        "xp_already_received": bool(
            correct and was_completed
        ),
        "current_xp": user.total_xp,
        "gamification_level": (
            level_info["new_level"]
        ),
        "level_up": (
            level_info["level_up"]
        ),
        "submaterial_completed": (
            submaterial_progress.is_completed
        ),
        "module_progress": (
            material_summary["progress"]
        ),
        "module_completion_xp_added": 0,
        "new_badges_unlocked": (
            material_summary.get(
                "new_badges_unlocked",
                [],
            )
        ),
        "new_milestones_unlocked": [
            reward.reward_key
            for reward in milestone_baru
        ],
        "quiz_unlocked": (
            material_summary["quiz_unlocked"]
        ),
    }), 200


# =========================================================
# STEP 5 — STATUS MODUL, KUIS, LAB, XP, DAN LEVEL
# =========================================================

@learning_bp.route(
    "/module/<int:material_id>/status",
    methods=["GET"],
)
@jwt_required()
def get_module_status(material_id):
    user_id = current_user_id()

    material = db.session.get(
        Material,
        material_id,
    )

    if (
        not material
        or not material.is_published
    ):
        return jsonify({
            "error": "Modul tidak ditemukan"
        }), 404

    summary = recalculate_material_progress(
        user_id,
        material_id,
    )

    level_unlocked = is_level_unlocked(
        user_id,
        material.level,
    )

    db.session.commit()

    return jsonify({
        "material_id": material_id,
        **summary,
        "level_unlocked": level_unlocked,
    }), 200


@learning_bp.route(
    "/module/<int:material_id>/quiz",
    methods=["GET"],
)
@jwt_required()
def get_module_quiz(material_id):
    user_id = current_user_id()

    material = db.session.get(
        Material,
        material_id,
    )

    if (
        not material
        or not material.is_published
    ):
        return jsonify({
            "error": "Modul tidak ditemukan"
        }), 404

    if not is_level_unlocked(
        user_id,
        material.level,
    ):
        return jsonify({
            "error": "Level modul masih terkunci"
        }), 403

    summary = recalculate_material_progress(
        user_id,
        material_id,
    )

    if not summary["quiz_required"]:
        return jsonify({
            "error": (
                "Modul ini belum memiliki soal kuis"
            )
        }), 404

    if not summary["quiz_unlocked"]:
        return jsonify({
            "error": (
                "Selesaikan seluruh submateri "
                "wajib sebelum membuka kuis"
            ),
            "learning_progress": (
                summary["learning_progress"]
            ),
        }), 403

    limit = min(
        int(summary["question_count"]),
        20,
    )

    questions = db.session.execute(
        db.select(Question)
        .where(
            Question.material_id
            == material_id
        )
        .order_by(
            db.func.random()
        )
        .limit(limit)
    ).scalars().all()

    db.session.commit()

    return jsonify({
        "material_id": material_id,
        "title": material.title,
        "passing_score": (
            QUIZ_PASSING_SCORE
        ),
        "question_count": len(questions),
        "questions": [
            question_for_student(item)
            for item in questions
        ],
    }), 200


@learning_bp.route(
    "/module/<int:material_id>/quiz/submit",
    methods=["POST"],
)
@jwt_required()
def submit_module_quiz(material_id):
    user_id = current_user_id()

    material = db.session.get(
        Material,
        material_id,
    )

    if (
        not material
        or not material.is_published
    ):
        return jsonify({
            "error": "Modul tidak ditemukan"
        }), 404

    if not is_level_unlocked(
        user_id,
        material.level,
    ):
        return jsonify({
            "error": "Level modul masih terkunci"
        }), 403

    summary = recalculate_material_progress(
        user_id,
        material_id,
    )

    if not summary["quiz_required"]:
        return jsonify({
            "error": (
                "Modul ini belum memiliki soal kuis"
            )
        }), 404

    if not summary["quiz_unlocked"]:
        return jsonify({
            "error": (
                "Selesaikan seluruh submateri "
                "wajib sebelum mengerjakan kuis"
            )
        }), 403

    data = request.get_json(silent=True) or {}

    try:
        submitted_answers = (
            normalize_quiz_answers(
                data.get("answers")
            )
        )
    except ValueError as exc:
        return jsonify({
            "error": str(exc)
        }), 400

    if not submitted_answers:
        return jsonify({
            "error": "Jawaban kuis masih kosong"
        }), 400

    expected_answer_count = min(
        int(summary["question_count"]),
        20,
    )

    if len(submitted_answers) != expected_answer_count:
        return jsonify({
            "error": (
                "Jumlah jawaban belum lengkap"
            ),
            "expected_answers": (
                expected_answer_count
            ),
            "received_answers": len(
                submitted_answers
            ),
        }), 400

    question_ids = list(
        submitted_answers.keys()
    )

    questions = db.session.execute(
        db.select(Question)
        .where(
            Question.id.in_(question_ids),
            Question.material_id
            == material_id,
        )
    ).scalars().all()

    if len(questions) != len(
        set(question_ids)
    ):
        return jsonify({
            "error": (
                "Ada soal yang tidak ditemukan "
                "atau bukan milik modul ini"
            )
        }), 400

    correct_count = 0
    answer_results = []

    for question in questions:
        submitted = submitted_answers.get(
            question.id,
            "",
        )

        correct_answer = (
            question.correct_answer
            or ""
        ).strip().upper()

        is_correct = (
            submitted == correct_answer
        )

        if is_correct:
            correct_count += 1

        answer_results.append({
            "question_id": question.id,
            "submitted_answer": submitted,
            "correct_answer": (
                correct_answer
            ),
            "is_correct": is_correct,
            "explanation": (
                question.explanation
            ),
        })

    total_questions = len(questions)

    score = round(
        (
            correct_count
            / total_questions
        ) * 100
    )

    passed = (
        score >= QUIZ_PASSING_SCORE
    )

    user = get_user_or_404(user_id)

    if not user:
        return jsonify({
            "error": "User tidak ditemukan"
        }), 404

    user_progress = (
        get_or_create_material_progress(
            user_id,
            material_id,
        )
    )

    was_passed = bool(
        user_progress.quiz_completed
    )

    best_score = max(
        int(
            user_progress.quiz_score or 0
        ),
        int(score),
    )

    user_progress.quiz_score = best_score

    xp_added = 0
    old_xp = int(user.total_xp or 0)

    if passed:
        user_progress.quiz_completed = True

        if not was_passed:
            user.total_xp = (
                old_xp + QUIZ_XP
            )
            xp_added = QUIZ_XP

    mark_daily_activity(
        user_id,
        "active",
    )

    quiz_badges = award_quiz_badges(
        user_id,
        score,
        bool(passed and not was_passed),
    )

    lab_badges = award_lab_badges(
        user_id
    )

    level_info = add_level_up_notification(
        user_id,
        old_xp,
        user.total_xp,
    )

    final_summary = (
        recalculate_material_progress(
            user_id,
            material_id,
        )
    )

    milestone_baru = sync_user_milestones(
        user,
        previous_xp=old_xp,
        notify_new=xp_added > 0,
    )

    db.session.commit()

    return jsonify({
        "message": (
            "Kuis berhasil diperiksa"
        ),
        "material_id": material_id,
        "score": score,
        "best_score": best_score,
        "passing_score": (
            QUIZ_PASSING_SCORE
        ),
        "passed": passed,
        "quiz_completed": bool(
            user_progress.quiz_completed
        ),
        "is_first_pass": bool(
            passed and not was_passed
        ),
        "xp_already_received": bool(
            passed and was_passed
        ),
        "correct_count": correct_count,
        "total_questions": (
            total_questions
        ),
        "activity_xp_added": xp_added,
        "module_completion_xp_added": (
            final_summary[
                "module_completion_xp_added"
            ]
        ),
        "total_xp_added": (
            xp_added
            + final_summary[
                "module_completion_xp_added"
            ]
        ),
        "current_xp": user.total_xp,
        "gamification_level": (
            level_info["new_level"]
        ),
        "level_up": (
            level_info["level_up"]
        ),
        "module_progress": (
            final_summary["progress"]
        ),
        "module_completed": (
            final_summary[
                "module_completed"
            ]
        ),
        "new_badges_unlocked": list(
            dict.fromkeys(
                quiz_badges
                + final_summary.get(
                    "new_badges_unlocked",
                    [],
                )
            )
        ),
        "new_milestones_unlocked": [
            reward.reward_key
            for reward in milestone_baru
        ],
        "answers": answer_results,
    }), 200


@learning_bp.route(
    "/module/<int:material_id>/lab/result",
    methods=["POST"],
)
@jwt_required()
def save_module_lab_result(material_id):
    user_id = current_user_id()

    material = db.session.get(
        Material,
        material_id,
    )

    if (
        not material
        or not material.is_published
    ):
        return jsonify({
            "error": "Modul tidak ditemukan"
        }), 404

    summary = recalculate_material_progress(
        user_id,
        material_id,
    )

    if not summary["lab_required"]:
        return jsonify({
            "error": (
                "Modul ini tidak memiliki "
                "simulasi laboratorium"
            )
        }), 400

    # Step 8 — jalur langsung ke endpoint Lab juga tidak boleh
    # melewati progression level.
    if not is_level_unlocked(user_id, material.level):
        return jsonify({
            "error": (
                "Laboratorium belum terbuka. "
                "Selesaikan modul pada level sebelumnya terlebih dahulu."
            )
        }), 403

    if not summary["lab_unlocked"]:
        return jsonify({
            "error": (
                "Laboratorium belum terbuka. "
                "Selesaikan materi dan raih nilai kuis minimal 75 "
                "pada modul ini terlebih dahulu."
            )
        }), 403

    data = request.get_json(silent=True) or {}

    experiment_id = (
        data.get("experiment_id")
        or data.get("experimentId")
        or material.unity_scene_id
    )

    display_name = (
        data.get("display_name")
        or data.get("displayName")
    )

    summary_json = (
        data.get("summary_json")
        or data.get("summaryJson")
        or {}
    )

    activities = data.get(
        "activities",
        [],
    )

    if isinstance(
        summary_json,
        (dict, list),
    ):
        summary_json = json.dumps(
            summary_json,
            ensure_ascii=False,
        )

    if summary_json is None:
        summary_json = ""

    def safe_int(value):
        try:
            return int(float(value or 0))
        except (TypeError, ValueError):
            return 0

    duration_seconds = safe_int(
        data.get("duration_seconds")
        or data.get("durationSeconds")
    )

    remaining_seconds = safe_int(
        data.get("remaining_seconds")
        or data.get("remainingSeconds")
    )

    elapsed_seconds = safe_int(
        data.get("elapsed_seconds")
        or data.get("elapsedSeconds")
    )

    timestamp_utc = (
        data.get("timestamp_utc")
        or data.get("timestampUtc")
    )

    lab_result = UserLabResult(
        user_id=user_id,
        material_id=material_id,
        experiment_id=experiment_id,
        display_name=display_name,
        duration_seconds=duration_seconds,
        remaining_seconds=remaining_seconds,
        elapsed_seconds=elapsed_seconds,
        timestamp_utc=timestamp_utc,
        summary_json=summary_json,
        activities_json=json.dumps(
            activities,
            ensure_ascii=False,
        ),
        raw_payload_json=json.dumps(
            data,
            ensure_ascii=False,
        ),
    )

    db.session.add(lab_result)
    db.session.commit()

    return jsonify({
        "message": (
            "Hasil laboratorium berhasil disimpan"
        ),
        "result_id": lab_result.id,
        "material_id": material_id,
        "experiment_id": experiment_id,
        "lab_completed": False,
        "next_action": (
            "Panggil endpoint lab/complete "
            "setelah simulasi benar-benar selesai"
        ),
    }), 201


@learning_bp.route(
    "/module/<int:material_id>/lab/complete",
    methods=["POST"],
)
@jwt_required()
def complete_module_lab(material_id):
    user_id = current_user_id()

    material = db.session.get(
        Material,
        material_id,
    )

    if (
        not material
        or not material.is_published
    ):
        return jsonify({
            "error": "Modul tidak ditemukan"
        }), 404

    summary = recalculate_material_progress(
        user_id,
        material_id,
    )

    if not summary["lab_required"]:
        return jsonify({
            "error": (
                "Modul ini tidak memiliki "
                "simulasi laboratorium"
            )
        }), 400

    # Step 8 — validasi ulang di server saat Unity menyelesaikan Lab.
    if not is_level_unlocked(user_id, material.level):
        return jsonify({
            "error": (
                "Laboratorium belum terbuka. "
                "Selesaikan modul pada level sebelumnya terlebih dahulu."
            )
        }), 403

    if not summary["lab_unlocked"]:
        return jsonify({
            "error": (
                "Laboratorium belum terbuka. "
                "Selesaikan materi dan raih nilai kuis minimal 75 "
                "pada modul ini terlebih dahulu."
            )
        }), 403

    data = request.get_json(silent=True) or {}
    result_id = data.get("result_id")

    result_statement = db.select(
        UserLabResult
    ).where(
        UserLabResult.user_id == user_id,
        UserLabResult.material_id
        == material_id,
    )

    if result_id is not None:
        try:
            result_id = int(result_id)
        except (TypeError, ValueError):
            return jsonify({
                "error": "Result ID tidak valid"
            }), 400

        result_statement = (
            result_statement.where(
                UserLabResult.id == result_id
            )
        )

    lab_result = db.session.scalar(
        result_statement.order_by(
            UserLabResult.created_at.desc()
        )
    )

    if not lab_result:
        return jsonify({
            "error": (
                "Simpan hasil simulasi lab "
                "terlebih dahulu"
            )
        }), 403

    user = get_user_or_404(user_id)

    if not user:
        return jsonify({
            "error": "User tidak ditemukan"
        }), 404

    user_progress = (
        get_or_create_material_progress(
            user_id,
            material_id,
        )
    )

    was_completed = bool(
        user_progress.lab_completed
    )

    old_xp = int(user.total_xp or 0)
    xp_added = 0

    if not was_completed:
        user_progress.lab_completed = True
        user.total_xp = old_xp + LAB_XP
        xp_added = LAB_XP

    mark_daily_activity(
        user_id,
        "active",
    )

    level_info = add_level_up_notification(
        user_id,
        old_xp,
        user.total_xp,
    )

    final_summary = (
        recalculate_material_progress(
            user_id,
            material_id,
        )
    )

    milestone_baru = sync_user_milestones(
        user,
        previous_xp=old_xp,
        notify_new=xp_added > 0,
    )

    db.session.commit()

    return jsonify({
        "message": (
            "Laboratorium berhasil diselesaikan"
        ),
        "material_id": material_id,
        "result_id": lab_result.id,
        "lab_completed": True,
        "is_first_completion": (
            not was_completed
        ),
        "xp_already_received": bool(
            was_completed
        ),
        "activity_xp_added": xp_added,
        "module_completion_xp_added": (
            final_summary[
                "module_completion_xp_added"
            ]
        ),
        "total_xp_added": (
            xp_added
            + final_summary[
                "module_completion_xp_added"
            ]
        ),
        "current_xp": user.total_xp,
        "gamification_level": (
            level_info["new_level"]
        ),
        "level_up": (
            level_info["level_up"]
        ),
        "module_progress": (
            final_summary["progress"]
        ),
        "module_completed": (
            final_summary[
                "module_completed"
            ]
        ),
        "new_badges_unlocked": list(
            dict.fromkeys(
                lab_badges
                + final_summary.get(
                    "new_badges_unlocked",
                    [],
                )
            )
        ),
        "new_milestones_unlocked": [
            reward.reward_key
            for reward in milestone_baru
        ],
    }), 200


# =========================================================
# RINGKASAN PROGRESS SISWA
# =========================================================

@learning_bp.route(
    "/progress",
    methods=["GET"],
)
@jwt_required()
def get_learning_progress():
    user_id = current_user_id()

    materials = db.session.execute(
        db.select(Material)
        .where(
            Material.is_published.is_(True)
        )
        .order_by(
            Material.level.asc(),
            Material.module_order.asc(),
            Material.id.asc(),
        )
    ).scalars().all()

    modules = [
        module_for_student(
            material,
            user_id,
            include_submaterials=False,
        )
        for material in materials
    ]

    structured_modules = [
        item
        for item in modules
        if not item["legacy_mode"]
    ]

    if structured_modules:
        overall_progress = sum(
            item["progress"]
            for item in structured_modules
        ) / len(structured_modules)
    else:
        overall_progress = 0.0

    db.session.commit()

    return jsonify({
        "overall_progress": round(
            overall_progress,
            4,
        ),
        "module_count": len(modules),
        "structured_module_count": len(
            structured_modules
        ),
        "modules": modules,
    }), 200
