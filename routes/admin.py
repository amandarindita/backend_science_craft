import csv
import io
import json
import os
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import func
from werkzeug.utils import secure_filename

from extensions import db
from models import (
    CHECKPOINT_TYPES,
    Checkpoint,
    FunFact,
    Material,
    Question,
    SubMaterial,
    User,
)

admin_bp = Blueprint("admin", __name__)

IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
AUDIO_EXTENSIONS = {"mp3", "wav", "m4a", "aac", "ogg"}
MAX_MODULE_INTRO_LENGTH = 150

MASTER_CONTENT_RECORD_TYPES = {
    "MODULE",
    "SUBMATERIAL",
    "CHECKPOINT",
}

VALID_QUESTION_TYPES = {
    "pemahaman",
    "konsep",
    "studi_kasus",
}

VALID_QUESTION_ANSWERS = {
    "A",
    "B",
    "C",
    "D",
}


# =========================================================
# HELPERS
# =========================================================

def current_user_id():
    return int(get_jwt_identity())


def is_admin(user_id):
    user = db.session.get(User, user_id)
    return bool(user and user.role in ("admin", "superadmin"))


def require_admin():
    user_id = current_user_id()

    if not is_admin(user_id):
        return None, (jsonify({
            "error": "Akses ditolak. Khusus admin/guru."
        }), 403)

    return user_id, None


def get_request_data():
    """
    Mendukung JSON biasa dan multipart/form-data.
    Gunakan form-data saat mengunggah gambar atau audio.
    """
    if request.content_type and request.content_type.startswith(
        "multipart/form-data"
    ):
        return request.form

    return request.get_json(silent=True) or {}


def parse_bool(value, default=False):
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    return str(value).strip().lower() in {
        "1", "true", "yes", "ya", "on"
    }


def parse_int(value, default=0):
    if value in (None, ""):
        return default

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_json(value, default_value):
    """
    Menyimpan dict/list atau string JSON sebagai string JSON yang valid.
    """
    if value in (None, ""):
        return json.dumps(default_value, ensure_ascii=False)

    if isinstance(value, (dict, list, bool, int, float)):
        return json.dumps(value, ensure_ascii=False)

    if isinstance(value, str):
        parsed = json.loads(value)
        return json.dumps(parsed, ensure_ascii=False)

    raise ValueError("Format JSON tidak didukung")


def read_json(value, default_value):
    if value in (None, ""):
        return default_value

    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default_value


def get_extension(filename):
    if not filename or "." not in filename:
        return ""

    return filename.rsplit(".", 1)[1].lower()


def save_uploaded_file(file, subfolder, allowed_extensions):
    if not file or not file.filename:
        return None

    extension = get_extension(file.filename)

    if extension not in allowed_extensions:
        allowed = ", ".join(sorted(allowed_extensions))
        raise ValueError(
            f"Format file tidak didukung. Gunakan: {allowed}"
        )

    upload_root = current_app.config.get(
        "UPLOAD_FOLDER",
        "uploads",
    )

    target_folder = os.path.join(
        upload_root,
        subfolder,
    )

    os.makedirs(target_folder, exist_ok=True)

    safe_filename = secure_filename(file.filename)
    name, ext = os.path.splitext(safe_filename)

    unique_filename = (
        f"{name}_"
        f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
        f"{ext.lower()}"
    )

    file_path = os.path.join(
        target_folder,
        unique_filename,
    )

    file.save(file_path)

    return f"/uploads/{subfolder}/{unique_filename}"


def validate_level(level):
    if level not in {1, 2, 3}:
        raise ValueError("Level harus 1, 2, atau 3")


def validate_checkpoint_type(checkpoint_type):
    if checkpoint_type not in CHECKPOINT_TYPES:
        raise ValueError("Jenis checkpoint tidak valid")

def validate_module_intro(value):
    """
    Intro modul ditampilkan sebagai pemantik singkat pada kartu belajar.
    Batas 150 karakter termasuk spasi agar tetap proporsional di mobile.
    """
    if value is None:
        return None

    intro = str(value).strip()

    if len(intro) > MAX_MODULE_INTRO_LENGTH:
        raise ValueError(
            "Intro modul maksimal "
            f"{MAX_MODULE_INTRO_LENGTH} karakter termasuk spasi"
        )

    return intro or None



def clean_csv_row(row):
    """Rapikan nama kolom dan nilai dari csv.DictReader."""
    cleaned = {}

    for key, value in row.items():
        if key is None:
            continue

        clean_key = str(key).strip()

        if not clean_key:
            continue

        cleaned[clean_key] = (
            str(value).strip()
            if value is not None
            else ""
        )

    return cleaned


def csv_json(value, default_value):
    """Baca sel JSON. Sel kosong dikembalikan sebagai default."""
    if value in (None, ""):
        return default_value

    parsed = json.loads(value)

    if isinstance(default_value, dict) and not isinstance(parsed, dict):
        raise ValueError("JSON harus berupa object")

    if isinstance(default_value, list) and not isinstance(parsed, list):
        raise ValueError("JSON harus berupa list")

    return parsed


def csv_bool(row, key, default):
    value = row.get(key)

    if value in (None, ""):
        return default

    return parse_bool(value, default)


def import_counter():
    return {
        "imported": 0,
        "updated": 0,
        "skipped": 0,
    }


def find_material_by_title(title):
    return db.session.execute(
        db.select(Material).where(
            func.lower(Material.title)
            == title.strip().lower()
        )
    ).scalar_one_or_none()


def find_submaterial_by_title(material_id, title):
    return db.session.execute(
        db.select(SubMaterial).where(
            SubMaterial.material_id == material_id,
            func.lower(SubMaterial.title)
            == title.strip().lower(),
        )
    ).scalar_one_or_none()


def find_checkpoint_by_title(submaterial_id, title):
    return db.session.execute(
        db.select(Checkpoint).where(
            Checkpoint.submaterial_id == submaterial_id,
            func.lower(Checkpoint.title)
            == title.strip().lower(),
        )
    ).scalar_one_or_none()


def find_question_by_text(material_id, question_text):
    return db.session.execute(
        db.select(Question).where(
            Question.material_id == material_id,
            func.lower(Question.question_text)
            == question_text.strip().lower(),
        )
    ).scalar_one_or_none()


def clear_material_learning_content(material):
    """
    Hapus submateri dan checkpoint pada modul yang diimpor ulang.

    Soal kuis tidak dihapus karena dikelola melalui questions.csv
    dan endpoint import soal yang terpisah.
    """
    submaterials = db.session.execute(
        db.select(SubMaterial).where(
            SubMaterial.material_id == material.id
        )
    ).scalars().all()

    for submaterial in submaterials:
        db.session.delete(submaterial)

    db.session.flush()


# =========================================================
# SERIALIZER
# =========================================================

def checkpoint_to_dict(checkpoint):
    return {
        "id": checkpoint.id,
        "submaterial_id": checkpoint.submaterial_id,
        "checkpoint_type": checkpoint.checkpoint_type,
        "checkpoint_label": CHECKPOINT_TYPES.get(
            checkpoint.checkpoint_type,
            checkpoint.checkpoint_type,
        ),
        "title": checkpoint.title,
        "instruction": checkpoint.instruction,
        "question_text": checkpoint.question_text,
        "content": read_json(
            checkpoint.content_json,
            {},
        ),
        "answer": read_json(
            checkpoint.answer_json,
            {},
        ),
        "image_url": checkpoint.image_url,
        "correct_feedback": checkpoint.correct_feedback,
        "wrong_feedback": checkpoint.wrong_feedback,
        "order_index": checkpoint.order_index,
        "is_required": checkpoint.is_required,
        "created_at": (
            checkpoint.created_at.strftime("%Y-%m-%d %H:%M:%S")
            if checkpoint.created_at
            else None
        ),
        "updated_at": (
            checkpoint.updated_at.strftime("%Y-%m-%d %H:%M:%S")
            if checkpoint.updated_at
            else None
        ),
    }


def submaterial_to_dict(
    submaterial,
    include_checkpoints=False,
):
    result = {
        "id": submaterial.id,
        "material_id": submaterial.material_id,
        "title": submaterial.title,
        "order_index": submaterial.order_index,
        "read_content": submaterial.read_content,
        "tts_text": submaterial.tts_text,
        "audio_url": submaterial.audio_url,
        "visual_type": submaterial.visual_type,
        "visual_data": read_json(
            submaterial.visual_data,
            {},
        ),
        "summary": submaterial.summary,
        "image_url": submaterial.image_url,
        "is_required": submaterial.is_required,
        "is_published": submaterial.is_published,
        "created_at": (
            submaterial.created_at.strftime("%Y-%m-%d %H:%M:%S")
            if submaterial.created_at
            else None
        ),
        "updated_at": (
            submaterial.updated_at.strftime("%Y-%m-%d %H:%M:%S")
            if submaterial.updated_at
            else None
        ),
    }

    if include_checkpoints:
        checkpoints = sorted(
            submaterial.checkpoints,
            key=lambda item: (
                item.order_index,
                item.id,
            ),
        )

        result["checkpoints"] = [
            checkpoint_to_dict(item)
            for item in checkpoints
        ]

    return result


def material_to_dict(
    material,
    include_submaterials=False,
):
    result = {
        "id": material.id,
        "title": material.title,
        "content": material.content,
        "category": material.category,
        "level": material.level,
        "module_order": material.module_order,
        "short_description": material.short_description,
        "is_required": material.is_required,
        "is_published": material.is_published,
        "unity_scene_id": material.unity_scene_id,
        "instructions": material.instructions,
        "image_url": material.image_url,
        "submaterial_count": len(material.submaterials),
        "created_at": (
            material.created_at.strftime("%Y-%m-%d %H:%M:%S")
            if material.created_at
            else None
        ),
    }

    if include_submaterials:
        submaterials = sorted(
            material.submaterials,
            key=lambda item: (
                item.order_index,
                item.id,
            ),
        )

        result["submaterials"] = [
            submaterial_to_dict(
                item,
                include_checkpoints=True,
            )
            for item in submaterials
        ]

    return result


def question_to_dict(question):
    return {
        "id": question.id,
        "material_id": question.material_id,
        "question_text": question.question_text,
        "question_type": question.question_type,
        "option_a": question.option_a,
        "option_b": question.option_b,
        "option_c": question.option_c,
        "option_d": question.option_d,
        "correct_answer": question.correct_answer,
        "explanation": question.explanation,
    }


def funfact_to_dict(fact):
    return {
        "id": fact.id,
        "fact_text": fact.fact_text,
        "created_at": (
            fact.created_at.strftime("%Y-%m-%d %H:%M:%S")
            if fact.created_at
            else None
        ),
    }


# =========================================================
# PILIHAN FORM ADMIN
# =========================================================

@admin_bp.route("/checkpoint-types", methods=["GET"])
@jwt_required()
def get_checkpoint_types():
    _, error = require_admin()

    if error:
        return error

    result = [
        {
            "value": key,
            "label": label,
        }
        for key, label in CHECKPOINT_TYPES.items()
    ]

    return jsonify(result), 200


@admin_bp.route("/visual-types", methods=["GET"])
@jwt_required()
def get_visual_types():
    _, error = require_admin()

    if error:
        return error

    return jsonify([
        {
            "value": "infographic",
            "label": "Infografik",
        },
        {
            "value": "comparison",
            "label": "Perbandingan",
        },
        {
            "value": "flow",
            "label": "Alur",
        },
        {
            "value": "chart",
            "label": "Grafik/Data",
        },
        {
            "value": "formula",
            "label": "Rumus",
        },
        {
            "value": "hotspot",
            "label": "Titik Gambar",
        },
        {
            "value": "sequence",
            "label": "Urutan Proses",
        },
    ]), 200


# =========================================================
# CRUD MODUL
# Material lama sekarang dipakai sebagai Modul.
# =========================================================

@admin_bp.route("/material", methods=["POST"])
@jwt_required()
def add_material():
    _, error = require_admin()

    if error:
        return error

    data = get_request_data()

    title = (data.get("title") or "").strip()
    category = (data.get("category") or "").strip()
    level = parse_int(
        data.get("level"),
        1,
    )

    if not title:
        return jsonify({
            "error": "Judul modul wajib diisi"
        }), 400

    if not category:
        return jsonify({
            "error": "Kategori wajib diisi"
        }), 400

    try:
        validate_level(level)

        image_url = data.get("image_url")

        if "image" in request.files:
            image_url = save_uploaded_file(
                request.files["image"],
                "images",
                IMAGE_EXTENSIONS,
            )

        short_description = validate_module_intro(
            data.get("short_description")
        )

        material = Material(
            title=title,
            content=data.get("content") or "",
            category=category,
            level=level,
            module_order=parse_int(
                data.get("module_order"),
                0,
            ),
            short_description=short_description,
            is_required=parse_bool(
                data.get("is_required"),
                True,
            ),
            is_published=parse_bool(
                data.get("is_published"),
                True,
            ),
            unity_scene_id=(
                data.get("unity_scene_id")
                or None
            ),
            instructions=data.get("instructions"),
            image_url=image_url,
        )

        db.session.add(material)
        db.session.commit()

        return jsonify({
            "message": "Modul berhasil ditambahkan",
            "material": material_to_dict(material),
        }), 201

    except ValueError as exc:
        db.session.rollback()

        return jsonify({
            "error": str(exc)
        }), 400

    except Exception as exc:
        db.session.rollback()

        return jsonify({
            "error": f"Gagal menambahkan modul: {str(exc)}"
        }), 500


@admin_bp.route("/materials", methods=["GET"])
@admin_bp.route("/material", methods=["GET"])
@jwt_required()
def get_all_materials():
    _, error = require_admin()

    if error:
        return error

    category = request.args.get("category")
    level = request.args.get("level")

    statement = db.select(Material)

    if category:
        statement = statement.where(
            Material.category == category
        )

    if level:
        statement = statement.where(
            Material.level == parse_int(level, 1)
        )

    materials = db.session.execute(
        statement.order_by(
            Material.category.asc(),
            Material.level.asc(),
            Material.module_order.asc(),
            Material.id.asc(),
        )
    ).scalars().all()

    return jsonify([
        material_to_dict(item)
        for item in materials
    ]), 200


@admin_bp.route(
    "/material/<int:material_id>",
    methods=["GET"],
)
@jwt_required()
def get_single_material(material_id):
    _, error = require_admin()

    if error:
        return error

    material = db.session.get(
        Material,
        material_id,
    )

    if not material:
        return jsonify({
            "error": "Modul tidak ditemukan"
        }), 404

    return jsonify(
        material_to_dict(
            material,
            include_submaterials=True,
        )
    ), 200


@admin_bp.route(
    "/material/<int:material_id>",
    methods=["PUT"],
)
@jwt_required()
def update_material(material_id):
    _, error = require_admin()

    if error:
        return error

    material = db.session.get(
        Material,
        material_id,
    )

    if not material:
        return jsonify({
            "error": "Modul tidak ditemukan"
        }), 404

    data = get_request_data()

    try:
        if data.get("level") is not None:
            level = parse_int(
                data.get("level"),
                material.level,
            )
            validate_level(level)
            material.level = level

        if data.get("title") is not None:
            title = data.get("title").strip()

            if not title:
                return jsonify({
                    "error": "Judul modul tidak boleh kosong"
                }), 400

            material.title = title

        if data.get("category") is not None:
            material.category = (
                data.get("category").strip()
            )

        if data.get("content") is not None:
            material.content = data.get("content")

        if data.get("module_order") is not None:
            material.module_order = parse_int(
                data.get("module_order"),
                material.module_order,
            )

        if data.get("short_description") is not None:
            material.short_description = validate_module_intro(
                data.get("short_description")
            )

        if data.get("is_required") is not None:
            material.is_required = parse_bool(
                data.get("is_required"),
                material.is_required,
            )

        if data.get("is_published") is not None:
            material.is_published = parse_bool(
                data.get("is_published"),
                material.is_published,
            )

        if data.get("unity_scene_id") is not None:
            material.unity_scene_id = (
                data.get("unity_scene_id")
                or None
            )

        if data.get("instructions") is not None:
            material.instructions = data.get(
                "instructions"
            )

        if parse_bool(
            data.get("remove_image"),
            False,
        ):
            material.image_url = None
        elif data.get("image_url"):
            material.image_url = data.get(
                "image_url"
            )

        if "image" in request.files:
            material.image_url = save_uploaded_file(
                request.files["image"],
                "images",
                IMAGE_EXTENSIONS,
            )

        db.session.commit()

        return jsonify({
            "message": "Modul berhasil diperbarui",
            "material": material_to_dict(material),
        }), 200

    except ValueError as exc:
        db.session.rollback()

        return jsonify({
            "error": str(exc)
        }), 400

    except Exception as exc:
        db.session.rollback()

        return jsonify({
            "error": f"Gagal memperbarui modul: {str(exc)}"
        }), 500


@admin_bp.route(
    "/material/<int:material_id>",
    methods=["DELETE"],
)
@jwt_required()
def delete_material(material_id):
    _, error = require_admin()

    if error:
        return error

    material = db.session.get(
        Material,
        material_id,
    )

    if not material:
        return jsonify({
            "error": "Modul tidak ditemukan"
        }), 404

    try:
        db.session.delete(material)
        db.session.commit()

        return jsonify({
            "message": (
                "Modul, submateri, checkpoint, "
                "dan soal terkait berhasil dihapus"
            )
        }), 200

    except Exception as exc:
        db.session.rollback()

        return jsonify({
            "error": f"Gagal menghapus modul: {str(exc)}"
        }), 500


# =========================================================
# CRUD SUBMATERI
# =========================================================

@admin_bp.route("/submaterial", methods=["POST"])
@jwt_required()
def add_submaterial():
    _, error = require_admin()

    if error:
        return error

    data = get_request_data()

    material_id = parse_int(
        data.get("material_id"),
        0,
    )

    material = db.session.get(
        Material,
        material_id,
    )

    if not material:
        return jsonify({
            "error": "Modul tidak ditemukan"
        }), 404

    title = (data.get("title") or "").strip()

    if not title:
        return jsonify({
            "error": "Judul submateri wajib diisi"
        }), 400

    try:
        visual_data = normalize_json(
            data.get("visual_data"),
            {},
        )

        audio_url = data.get("audio_url")

        if "audio" in request.files:
            audio_url = save_uploaded_file(
                request.files["audio"],
                "audio",
                AUDIO_EXTENSIONS,
            )

        image_url = data.get("image_url")

        if "image" in request.files:
            image_url = save_uploaded_file(
                request.files["image"],
                "images",
                IMAGE_EXTENSIONS,
            )

        submaterial = SubMaterial(
            material_id=material_id,
            title=title,
            order_index=parse_int(
                data.get("order_index"),
                1,
            ),
            read_content=(
                data.get("read_content")
                or ""
            ),
            tts_text=(
                data.get("tts_text")
                or None
            ),
            audio_url=audio_url,
            visual_type=(
                data.get("visual_type")
                or None
            ),
            visual_data=visual_data,
            summary=(
                data.get("summary")
                or None
            ),
            image_url=image_url,
            is_required=parse_bool(
                data.get("is_required"),
                True,
            ),
            is_published=parse_bool(
                data.get("is_published"),
                True,
            ),
        )

        db.session.add(submaterial)
        db.session.commit()

        return jsonify({
            "message": "Submateri berhasil ditambahkan",
            "submaterial": submaterial_to_dict(
                submaterial
            ),
        }), 201

    except (
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        db.session.rollback()

        return jsonify({
            "error": f"Data tidak valid: {str(exc)}"
        }), 400

    except Exception as exc:
        db.session.rollback()

        return jsonify({
            "error": (
                "Gagal menambahkan submateri: "
                f"{str(exc)}"
            )
        }), 500


@admin_bp.route(
    "/submaterials/<int:material_id>",
    methods=["GET"],
)
@jwt_required()
def get_submaterials(material_id):
    _, error = require_admin()

    if error:
        return error

    material = db.session.get(
        Material,
        material_id,
    )

    if not material:
        return jsonify({
            "error": "Modul tidak ditemukan"
        }), 404

    submaterials = db.session.execute(
        db.select(SubMaterial)
        .where(
            SubMaterial.material_id == material_id
        )
        .order_by(
            SubMaterial.order_index.asc(),
            SubMaterial.id.asc(),
        )
    ).scalars().all()

    return jsonify([
        submaterial_to_dict(
            item,
            include_checkpoints=True,
        )
        for item in submaterials
    ]), 200


@admin_bp.route(
    "/submaterial/<int:submaterial_id>",
    methods=["GET"],
)
@jwt_required()
def get_submaterial(submaterial_id):
    _, error = require_admin()

    if error:
        return error

    submaterial = db.session.get(
        SubMaterial,
        submaterial_id,
    )

    if not submaterial:
        return jsonify({
            "error": "Submateri tidak ditemukan"
        }), 404

    return jsonify(
        submaterial_to_dict(
            submaterial,
            include_checkpoints=True,
        )
    ), 200


@admin_bp.route(
    "/submaterial/<int:submaterial_id>",
    methods=["PUT"],
)
@jwt_required()
def update_submaterial(submaterial_id):
    _, error = require_admin()

    if error:
        return error

    submaterial = db.session.get(
        SubMaterial,
        submaterial_id,
    )

    if not submaterial:
        return jsonify({
            "error": "Submateri tidak ditemukan"
        }), 404

    data = get_request_data()

    try:
        if data.get("title") is not None:
            title = data.get("title").strip()

            if not title:
                return jsonify({
                    "error": (
                        "Judul submateri "
                        "tidak boleh kosong"
                    )
                }), 400

            submaterial.title = title

        if data.get("order_index") is not None:
            submaterial.order_index = parse_int(
                data.get("order_index"),
                submaterial.order_index,
            )

        if data.get("read_content") is not None:
            submaterial.read_content = data.get(
                "read_content"
            )

        if data.get("tts_text") is not None:
            submaterial.tts_text = (
                data.get("tts_text")
                or None
            )

        if data.get("audio_url") is not None:
            submaterial.audio_url = (
                data.get("audio_url")
                or None
            )

        if data.get("visual_type") is not None:
            submaterial.visual_type = (
                data.get("visual_type")
                or None
            )

        if data.get("visual_data") is not None:
            submaterial.visual_data = normalize_json(
                data.get("visual_data"),
                {},
            )

        if data.get("summary") is not None:
            submaterial.summary = (
                data.get("summary")
                or None
            )

        if data.get("image_url") is not None:
            submaterial.image_url = (
                data.get("image_url")
                or None
            )

        if data.get("is_required") is not None:
            submaterial.is_required = parse_bool(
                data.get("is_required"),
                submaterial.is_required,
            )

        if data.get("is_published") is not None:
            submaterial.is_published = parse_bool(
                data.get("is_published"),
                submaterial.is_published,
            )

        if "audio" in request.files:
            submaterial.audio_url = save_uploaded_file(
                request.files["audio"],
                "audio",
                AUDIO_EXTENSIONS,
            )

        if "image" in request.files:
            submaterial.image_url = save_uploaded_file(
                request.files["image"],
                "images",
                IMAGE_EXTENSIONS,
            )

        db.session.commit()

        return jsonify({
            "message": "Submateri berhasil diperbarui",
            "submaterial": submaterial_to_dict(
                submaterial,
                include_checkpoints=True,
            ),
        }), 200

    except (
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        db.session.rollback()

        return jsonify({
            "error": f"Data tidak valid: {str(exc)}"
        }), 400

    except Exception as exc:
        db.session.rollback()

        return jsonify({
            "error": (
                "Gagal memperbarui submateri: "
                f"{str(exc)}"
            )
        }), 500


@admin_bp.route(
    "/submaterial/<int:submaterial_id>",
    methods=["DELETE"],
)
@jwt_required()
def delete_submaterial(submaterial_id):
    _, error = require_admin()

    if error:
        return error

    submaterial = db.session.get(
        SubMaterial,
        submaterial_id,
    )

    if not submaterial:
        return jsonify({
            "error": "Submateri tidak ditemukan"
        }), 404

    try:
        db.session.delete(submaterial)
        db.session.commit()

        return jsonify({
            "message": (
                "Submateri dan checkpoint "
                "terkait berhasil dihapus"
            )
        }), 200

    except Exception as exc:
        db.session.rollback()

        return jsonify({
            "error": (
                "Gagal menghapus submateri: "
                f"{str(exc)}"
            )
        }), 500


# =========================================================
# CRUD CHECKPOINT
# =========================================================

@admin_bp.route("/checkpoint", methods=["POST"])
@jwt_required()
def add_checkpoint():
    _, error = require_admin()

    if error:
        return error

    data = get_request_data()

    submaterial_id = parse_int(
        data.get("submaterial_id"),
        0,
    )

    submaterial = db.session.get(
        SubMaterial,
        submaterial_id,
    )

    if not submaterial:
        return jsonify({
            "error": "Submateri tidak ditemukan"
        }), 404

    checkpoint_type = (
        data.get("checkpoint_type")
        or ""
    ).strip()

    question_text = (
        data.get("question_text")
        or ""
    ).strip()

    if not question_text:
        return jsonify({
            "error": (
                "Pertanyaan checkpoint "
                "wajib diisi"
            )
        }), 400

    try:
        validate_checkpoint_type(
            checkpoint_type
        )

        content_json = normalize_json(
            data.get("content"),
            {},
        )

        answer_json = normalize_json(
            data.get("answer"),
            {},
        )

        image_url = data.get("image_url")

        if "image" in request.files:
            image_url = save_uploaded_file(
                request.files["image"],
                "checkpoint-images",
                IMAGE_EXTENSIONS,
            )

        checkpoint = Checkpoint(
            submaterial_id=submaterial_id,
            checkpoint_type=checkpoint_type,
            title=(
                data.get("title")
                or "Cek Pemahaman"
            ),
            instruction=data.get("instruction"),
            question_text=question_text,
            content_json=content_json,
            answer_json=answer_json,
            image_url=image_url,
            correct_feedback=data.get(
                "correct_feedback"
            ),
            wrong_feedback=data.get(
                "wrong_feedback"
            ),
            order_index=parse_int(
                data.get("order_index"),
                1,
            ),
            is_required=parse_bool(
                data.get("is_required"),
                True,
            ),
        )

        db.session.add(checkpoint)
        db.session.commit()

        return jsonify({
            "message": "Checkpoint berhasil ditambahkan",
            "checkpoint": checkpoint_to_dict(
                checkpoint
            ),
        }), 201

    except (
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        db.session.rollback()

        return jsonify({
            "error": (
                "Data checkpoint tidak valid: "
                f"{str(exc)}"
            )
        }), 400

    except Exception as exc:
        db.session.rollback()

        return jsonify({
            "error": (
                "Gagal menambahkan checkpoint: "
                f"{str(exc)}"
            )
        }), 500


@admin_bp.route(
    "/checkpoints/<int:submaterial_id>",
    methods=["GET"],
)
@jwt_required()
def get_checkpoints(submaterial_id):
    _, error = require_admin()

    if error:
        return error

    submaterial = db.session.get(
        SubMaterial,
        submaterial_id,
    )

    if not submaterial:
        return jsonify({
            "error": "Submateri tidak ditemukan"
        }), 404

    checkpoints = db.session.execute(
        db.select(Checkpoint)
        .where(
            Checkpoint.submaterial_id
            == submaterial_id
        )
        .order_by(
            Checkpoint.order_index.asc(),
            Checkpoint.id.asc(),
        )
    ).scalars().all()

    return jsonify([
        checkpoint_to_dict(item)
        for item in checkpoints
    ]), 200


@admin_bp.route(
    "/checkpoint/<int:checkpoint_id>",
    methods=["GET"],
)
@jwt_required()
def get_checkpoint(checkpoint_id):
    _, error = require_admin()

    if error:
        return error

    checkpoint = db.session.get(
        Checkpoint,
        checkpoint_id,
    )

    if not checkpoint:
        return jsonify({
            "error": "Checkpoint tidak ditemukan"
        }), 404

    return jsonify(
        checkpoint_to_dict(checkpoint)
    ), 200


@admin_bp.route(
    "/checkpoint/<int:checkpoint_id>",
    methods=["PUT"],
)
@jwt_required()
def update_checkpoint(checkpoint_id):
    _, error = require_admin()

    if error:
        return error

    checkpoint = db.session.get(
        Checkpoint,
        checkpoint_id,
    )

    if not checkpoint:
        return jsonify({
            "error": "Checkpoint tidak ditemukan"
        }), 404

    data = get_request_data()

    try:
        if data.get("checkpoint_type") is not None:
            checkpoint_type = (
                data.get("checkpoint_type").strip()
            )

            validate_checkpoint_type(
                checkpoint_type
            )

            checkpoint.checkpoint_type = (
                checkpoint_type
            )

        if data.get("title") is not None:
            checkpoint.title = data.get("title")

        if data.get("instruction") is not None:
            checkpoint.instruction = data.get(
                "instruction"
            )

        if data.get("question_text") is not None:
            question_text = (
                data.get("question_text").strip()
            )

            if not question_text:
                return jsonify({
                    "error": (
                        "Pertanyaan tidak boleh kosong"
                    )
                }), 400

            checkpoint.question_text = (
                question_text
            )

        if data.get("content") is not None:
            checkpoint.content_json = normalize_json(
                data.get("content"),
                {},
            )

        if data.get("answer") is not None:
            checkpoint.answer_json = normalize_json(
                data.get("answer"),
                {},
            )

        if data.get("image_url") is not None:
            checkpoint.image_url = (
                data.get("image_url")
                or None
            )

        if data.get("correct_feedback") is not None:
            checkpoint.correct_feedback = data.get(
                "correct_feedback"
            )

        if data.get("wrong_feedback") is not None:
            checkpoint.wrong_feedback = data.get(
                "wrong_feedback"
            )

        if data.get("order_index") is not None:
            checkpoint.order_index = parse_int(
                data.get("order_index"),
                checkpoint.order_index,
            )

        if data.get("is_required") is not None:
            checkpoint.is_required = parse_bool(
                data.get("is_required"),
                checkpoint.is_required,
            )

        if "image" in request.files:
            checkpoint.image_url = save_uploaded_file(
                request.files["image"],
                "checkpoint-images",
                IMAGE_EXTENSIONS,
            )

        db.session.commit()

        return jsonify({
            "message": "Checkpoint berhasil diperbarui",
            "checkpoint": checkpoint_to_dict(
                checkpoint
            ),
        }), 200

    except (
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        db.session.rollback()

        return jsonify({
            "error": (
                "Data checkpoint tidak valid: "
                f"{str(exc)}"
            )
        }), 400

    except Exception as exc:
        db.session.rollback()

        return jsonify({
            "error": (
                "Gagal memperbarui checkpoint: "
                f"{str(exc)}"
            )
        }), 500


@admin_bp.route(
    "/checkpoint/<int:checkpoint_id>",
    methods=["DELETE"],
)
@jwt_required()
def delete_checkpoint(checkpoint_id):
    _, error = require_admin()

    if error:
        return error

    checkpoint = db.session.get(
        Checkpoint,
        checkpoint_id,
    )

    if not checkpoint:
        return jsonify({
            "error": "Checkpoint tidak ditemukan"
        }), 404

    try:
        db.session.delete(checkpoint)
        db.session.commit()

        return jsonify({
            "message": "Checkpoint berhasil dihapus"
        }), 200

    except Exception as exc:
        db.session.rollback()

        return jsonify({
            "error": (
                "Gagal menghapus checkpoint: "
                f"{str(exc)}"
            )
        }), 500



# =========================================================
# IMPORT MASTER CONTENT CSV
# =========================================================

@admin_bp.route(
    "/import/learning-content",
    methods=["POST"],
)
@admin_bp.route(
    "/import/content-package",
    methods=["POST"],
)
@jwt_required()
def import_content_package_csv():
    """
    Import learning_content.csv berisi MODULE, SUBMATERIAL, dan CHECKPOINT.

    Relasi dalam file memakai module_code dan submaterial_code.
    Soal kuis sengaja diimpor terpisah melalui /admin/import/questions.
    """
    _, error = require_admin()

    if error:
        return error

    if "file" not in request.files:
        return jsonify({
            "error": "File learning_content.csv tidak ditemukan"
        }), 400

    file = request.files["file"]

    if not file.filename:
        return jsonify({
            "error": "Nama file kosong"
        }), 400

    if get_extension(file.filename) != "csv":
        return jsonify({
            "error": "File harus menggunakan format .csv"
        }), 400

    replace_existing = parse_bool(
        request.form.get("replace_existing"),
        False,
    )

    try:
        raw_content = file.stream.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        return jsonify({
            "error": (
                "CSV harus menggunakan encoding UTF-8. "
                "Simpan ulang sebagai CSV UTF-8."
            )
        }), 400

    try:
        reader = csv.DictReader(
            io.StringIO(raw_content, newline=None)
        )

        if not reader.fieldnames:
            return jsonify({
                "error": "CSV tidak memiliki header"
            }), 400

        normalized_headers = {
            str(header).strip()
            for header in reader.fieldnames
            if header is not None
        }

        required_headers = {
            "record_type",
            "module_code",
            "title",
        }

        missing_headers = sorted(
            required_headers - normalized_headers
        )

        if missing_headers:
            return jsonify({
                "error": (
                    "Header wajib belum tersedia: "
                    + ", ".join(missing_headers)
                )
            }), 400

        rows = []

        for row_number, raw_row in enumerate(
            reader,
            start=2,
        ):
            row = clean_csv_row(raw_row)

            if not any(row.values()):
                continue

            row["__row_number"] = row_number
            row["record_type"] = (
                row.get("record_type") or ""
            ).upper()
            rows.append(row)

        if not rows:
            return jsonify({
                "error": "CSV tidak memiliki baris data"
            }), 400

        counters = {
            "MODULE": import_counter(),
            "SUBMATERIAL": import_counter(),
            "CHECKPOINT": import_counter(),
        }

        skipped = []
        module_map = {}
        submaterial_map = {}
        reset_material_ids = set()

        def skip_row(row, reason):
            record_type = row.get("record_type") or "UNKNOWN"

            if record_type in counters:
                counters[record_type]["skipped"] += 1

            skipped.append({
                "row": row.get("__row_number"),
                "record_type": record_type,
                "reason": reason,
            })

        # -------------------------------------------------
        # PASS 1: MODULE
        # -------------------------------------------------
        for row in rows:
            if row.get("record_type") != "MODULE":
                continue

            module_code = (row.get("module_code") or "").strip()
            title = (row.get("title") or "").strip()
            category = (row.get("category") or "").strip()

            if not module_code:
                skip_row(row, "module_code wajib diisi")
                continue

            if module_code in module_map:
                skip_row(row, f"module_code '{module_code}' duplikat")
                continue

            if not title or not category:
                skip_row(row, "title dan category wajib diisi")
                continue

            try:
                level = parse_int(row.get("level"), 1)
                validate_level(level)

                intro = validate_module_intro(
                    row.get("short_description")
                    or row.get("intro")
                )

                material = find_material_by_title(title)
                is_new = material is None

                if material is None:
                    material = Material(
                        title=title,
                        category=category,
                        content="",
                        level=level,
                        module_order=parse_int(
                            row.get("order_index")
                            or row.get("module_order"),
                            1,
                        ),
                        short_description=intro,
                        is_required=csv_bool(
                            row,
                            "is_required",
                            True,
                        ),
                        is_published=csv_bool(
                            row,
                            "is_published",
                            True,
                        ),
                        unity_scene_id=(
                            row.get("unity_scene_id")
                            or None
                        ),
                        instructions=(
                            row.get("instructions")
                            or ""
                        ),
                        image_url=(
                            row.get("image_url")
                            or None
                        ),
                    )
                    db.session.add(material)
                    db.session.flush()
                else:
                    if (
                        replace_existing
                        and material.id not in reset_material_ids
                    ):
                        clear_material_learning_content(material)
                        reset_material_ids.add(material.id)

                    material.title = title
                    material.category = category
                    material.level = level
                    material.module_order = parse_int(
                        row.get("order_index")
                        or row.get("module_order"),
                        material.module_order or 1,
                    )
                    material.short_description = intro
                    material.is_required = csv_bool(
                        row,
                        "is_required",
                        material.is_required,
                    )
                    material.is_published = csv_bool(
                        row,
                        "is_published",
                        material.is_published,
                    )
                    material.unity_scene_id = (
                        row.get("unity_scene_id")
                        or None
                    )
                    material.instructions = (
                        row.get("instructions")
                        or ""
                    )

                    if row.get("image_url") != "":
                        material.image_url = (
                            row.get("image_url")
                            or None
                        )

                module_map[module_code] = material
                counters["MODULE"][
                    "imported" if is_new else "updated"
                ] += 1

            except (ValueError, json.JSONDecodeError) as exc:
                skip_row(row, str(exc))

        db.session.flush()

        # -------------------------------------------------
        # PASS 2: SUBMATERIAL
        # -------------------------------------------------
        for row in rows:
            if row.get("record_type") != "SUBMATERIAL":
                continue

            module_code = (row.get("module_code") or "").strip()
            submaterial_code = (
                row.get("submaterial_code") or ""
            ).strip()
            title = (row.get("title") or "").strip()
            material = module_map.get(module_code)

            if not material:
                skip_row(
                    row,
                    f"module_code '{module_code}' tidak ditemukan",
                )
                continue

            if not submaterial_code:
                skip_row(row, "submaterial_code wajib diisi")
                continue

            if submaterial_code in submaterial_map:
                skip_row(
                    row,
                    f"submaterial_code '{submaterial_code}' duplikat",
                )
                continue

            if not title:
                skip_row(row, "title submateri wajib diisi")
                continue

            try:
                visual_data = normalize_json(
                    csv_json(
                        row.get("visual_data"),
                        {},
                    ),
                    {},
                )

                submaterial = find_submaterial_by_title(
                    material.id,
                    title,
                )
                is_new = submaterial is None

                if submaterial is None:
                    submaterial = SubMaterial(
                        material_id=material.id,
                        title=title,
                        order_index=parse_int(
                            row.get("order_index"),
                            1,
                        ),
                        read_content=(
                            row.get("read_content")
                            or ""
                        ),
                        tts_text=(
                            row.get("tts_text")
                            or None
                        ),
                        audio_url=(
                            row.get("audio_url")
                            or None
                        ),
                        visual_type=(
                            row.get("visual_type")
                            or None
                        ),
                        visual_data=visual_data,
                        summary=(
                            row.get("summary")
                            or None
                        ),
                        image_url=(
                            row.get("image_url")
                            or None
                        ),
                        is_required=csv_bool(
                            row,
                            "is_required",
                            True,
                        ),
                        is_published=csv_bool(
                            row,
                            "is_published",
                            True,
                        ),
                    )
                    db.session.add(submaterial)
                    db.session.flush()
                else:
                    submaterial.title = title
                    submaterial.order_index = parse_int(
                        row.get("order_index"),
                        submaterial.order_index or 1,
                    )
                    submaterial.read_content = (
                        row.get("read_content")
                        or ""
                    )
                    submaterial.tts_text = (
                        row.get("tts_text")
                        or None
                    )
                    submaterial.audio_url = (
                        row.get("audio_url")
                        or None
                    )
                    submaterial.visual_type = (
                        row.get("visual_type")
                        or None
                    )
                    submaterial.visual_data = visual_data
                    submaterial.summary = (
                        row.get("summary")
                        or None
                    )
                    submaterial.image_url = (
                        row.get("image_url")
                        or None
                    )
                    submaterial.is_required = csv_bool(
                        row,
                        "is_required",
                        submaterial.is_required,
                    )
                    submaterial.is_published = csv_bool(
                        row,
                        "is_published",
                        submaterial.is_published,
                    )

                submaterial_map[submaterial_code] = submaterial
                counters["SUBMATERIAL"][
                    "imported" if is_new else "updated"
                ] += 1

            except (ValueError, json.JSONDecodeError) as exc:
                skip_row(row, str(exc))

        db.session.flush()

        # -------------------------------------------------
        # PASS 3: CHECKPOINT
        # -------------------------------------------------
        for row in rows:
            if row.get("record_type") != "CHECKPOINT":
                continue

            submaterial_code = (
                row.get("submaterial_code") or ""
            ).strip()
            submaterial = submaterial_map.get(submaterial_code)
            title = (row.get("title") or "").strip()
            checkpoint_type = (
                row.get("checkpoint_type") or ""
            ).strip().lower()
            question_text = (
                row.get("question_text") or ""
            ).strip()

            if not submaterial:
                skip_row(
                    row,
                    (
                        "submaterial_code "
                        f"'{submaterial_code}' tidak ditemukan"
                    ),
                )
                continue

            if not title or not question_text:
                skip_row(
                    row,
                    "title dan question_text wajib diisi",
                )
                continue

            try:
                validate_checkpoint_type(checkpoint_type)

                content_data = csv_json(
                    row.get("content"),
                    {},
                )
                answer_data = csv_json(
                    row.get("answer"),
                    {},
                )

                if not answer_data:
                    raise ValueError(
                        "answer checkpoint wajib diisi"
                    )

                checkpoint = find_checkpoint_by_title(
                    submaterial.id,
                    title,
                )
                is_new = checkpoint is None

                if checkpoint is None:
                    checkpoint = Checkpoint(
                        submaterial_id=submaterial.id,
                        checkpoint_type=checkpoint_type,
                        title=title,
                        instruction=(
                            row.get("instruction")
                            or ""
                        ),
                        question_text=question_text,
                        content_json=normalize_json(
                            content_data,
                            {},
                        ),
                        answer_json=normalize_json(
                            answer_data,
                            {},
                        ),
                        image_url=(
                            row.get("image_url")
                            or None
                        ),
                        correct_feedback=(
                            row.get("correct_feedback")
                            or "Mantap, jawabanmu benar!"
                        ),
                        wrong_feedback=(
                            row.get("wrong_feedback")
                            or (
                                "Belum tepat. Coba pelajari "
                                "kembali bagian ini."
                            )
                        ),
                        order_index=parse_int(
                            row.get("order_index"),
                            1,
                        ),
                        is_required=csv_bool(
                            row,
                            "is_required",
                            True,
                        ),
                    )
                    db.session.add(checkpoint)
                else:
                    checkpoint.checkpoint_type = checkpoint_type
                    checkpoint.title = title
                    checkpoint.instruction = (
                        row.get("instruction") or ""
                    )
                    checkpoint.question_text = question_text
                    checkpoint.content_json = normalize_json(
                        content_data,
                        {},
                    )
                    checkpoint.answer_json = normalize_json(
                        answer_data,
                        {},
                    )
                    checkpoint.image_url = (
                        row.get("image_url")
                        or None
                    )
                    checkpoint.correct_feedback = (
                        row.get("correct_feedback")
                        or "Mantap, jawabanmu benar!"
                    )
                    checkpoint.wrong_feedback = (
                        row.get("wrong_feedback")
                        or (
                            "Belum tepat. Coba pelajari "
                            "kembali bagian ini."
                        )
                    )
                    checkpoint.order_index = parse_int(
                        row.get("order_index"),
                        checkpoint.order_index or 1,
                    )
                    checkpoint.is_required = csv_bool(
                        row,
                        "is_required",
                        checkpoint.is_required,
                    )

                counters["CHECKPOINT"][
                    "imported" if is_new else "updated"
                ] += 1

            except (ValueError, json.JSONDecodeError) as exc:
                skip_row(row, str(exc))

        db.session.flush()

        # Unknown record_type rows are reported last.
        for row in rows:
            record_type = row.get("record_type")

            if record_type not in MASTER_CONTENT_RECORD_TYPES:
                skipped.append({
                    "row": row.get("__row_number"),
                    "record_type": record_type or "KOSONG",
                    "reason": (
                        "record_type harus MODULE, SUBMATERIAL, "
                        "atau CHECKPOINT"
                    ),
                })

        db.session.commit()

        total_imported = sum(
            item["imported"]
            for item in counters.values()
        )
        total_updated = sum(
            item["updated"]
            for item in counters.values()
        )

        return jsonify({
            "message": "Import konten pembelajaran selesai",
            "replace_existing": replace_existing,
            "totals": {
                "rows": len(rows),
                "imported": total_imported,
                "updated": total_updated,
                "skipped": len(skipped),
            },
            "by_type": {
                key.lower(): value
                for key, value in counters.items()
            },
            "skipped": skipped,
        }), 200

    except csv.Error as exc:
        db.session.rollback()

        return jsonify({
            "error": f"Format CSV tidak valid: {str(exc)}"
        }), 400

    except Exception as exc:
        db.session.rollback()

        return jsonify({
            "error": (
                "Gagal import konten pembelajaran: "
                f"{str(exc)}"
            )
        }), 500


# =========================================================
# IMPORT MODUL DARI CSV
# Tetap kompatibel dengan format lama.
# =========================================================

@admin_bp.route(
    "/import/materials",
    methods=["POST"],
)
@jwt_required()
def import_materials_csv():
    _, error = require_admin()

    if error:
        return error

    if "file" not in request.files:
        return jsonify({
            "error": "File CSV tidak ditemukan"
        }), 400

    file = request.files["file"]

    if not file.filename:
        return jsonify({
            "error": "Nama file kosong"
        }), 400

    try:
        stream = io.StringIO(
            file.stream.read().decode("utf-8-sig"),
            newline=None,
        )

        reader = csv.DictReader(stream)

        imported = 0
        updated = 0
        skipped = []

        for row_number, row in enumerate(
            reader,
            start=2,
        ):
            title = (
                row.get("title")
                or ""
            ).strip()

            category = (
                row.get("category")
                or ""
            ).strip()

            intro = (
                row.get("intro")
                or ""
            ).strip()

            if len(intro) > MAX_MODULE_INTRO_LENGTH:
                skipped.append({
                    "row": row_number,
                    "reason": (
                        "intro melebihi 150 karakter"
                    ),
                })
                continue

            if not title or not category:
                skipped.append({
                    "row": row_number,
                    "reason": (
                        "title/category kosong"
                    ),
                })
                continue

            sections = []

            for index in range(1, 5):
                section_title = (
                    row.get(
                        f"section_{index}_title"
                    )
                    or ""
                ).strip()

                section_content = (
                    row.get(
                        f"section_{index}_content"
                    )
                    or ""
                ).strip()

                section_examples = (
                    row.get(
                        f"section_{index}_examples"
                    )
                    or ""
                ).strip()

                if (
                    section_title
                    or section_content
                    or section_examples
                ):
                    sections.append({
                        "title": section_title,
                        "content": section_content,
                        "examples": section_examples,
                        "image_path": "",
                    })

            if not sections:
                skipped.append({
                    "row": row_number,
                    "reason": (
                        "Minimal satu section wajib diisi"
                    ),
                })
                continue

            combined_content = json.dumps(
                {
                    "intro": intro,
                    "sections": sections,
                },
                ensure_ascii=False,
            )

            existing = db.session.execute(
                db.select(Material).where(
                    func.lower(Material.title)
                    == title.lower()
                )
            ).scalar_one_or_none()

            level = parse_int(
                row.get("level"),
                1,
            )

            if level not in {1, 2, 3}:
                level = 1

            csv_short_description = validate_module_intro(
                row.get("short_description")
                or intro
            )

            if existing:
                existing.category = category
                existing.content = combined_content
                existing.level = level
                existing.module_order = parse_int(
                    row.get("module_order"),
                    existing.module_order,
                )
                existing.short_description = (
                    csv_short_description
                    or existing.short_description
                )
                updated += 1
            else:
                db.session.add(Material(
                    title=title,
                    category=category,
                    content=combined_content,
                    level=level,
                    module_order=parse_int(
                        row.get("module_order"),
                        0,
                    ),
                    short_description=csv_short_description,
                    unity_scene_id="",
                    instructions="",
                    image_url=None,
                ))
                imported += 1

        db.session.commit()

        return jsonify({
            "message": "Import CSV modul selesai",
            "imported": imported,
            "updated": updated,
            "skipped": skipped,
        }), 200

    except Exception as exc:
        db.session.rollback()

        return jsonify({
            "error": f"Gagal import modul: {str(exc)}"
        }), 500


# =========================================================
# CRUD SOAL KUIS
# =========================================================

@admin_bp.route("/question", methods=["POST"])
@jwt_required()
def add_question():
    _, error = require_admin()

    if error:
        return error

    data = request.get_json(silent=True) or {}

    material_id = parse_int(
        data.get("material_id"),
        0,
    )

    material = db.session.get(
        Material,
        material_id,
    )

    if not material:
        return jsonify({
            "error": "Modul tidak ditemukan"
        }), 404

    correct_answer = (
        data.get("correct_answer")
        or ""
    ).upper()

    if correct_answer not in {
        "A", "B", "C", "D"
    }:
        return jsonify({
            "error": (
                "Jawaban benar harus "
                "A, B, C, atau D"
            )
        }), 400

    question = Question(
        material_id=material_id,
        question_text=data.get("question_text"),
        question_type=data.get(
            "question_type",
            "pemahaman",
        ),
        option_a=data.get("option_a"),
        option_b=data.get("option_b"),
        option_c=data.get("option_c"),
        option_d=data.get("option_d"),
        correct_answer=correct_answer,
        explanation=data.get("explanation"),
    )

    db.session.add(question)
    db.session.commit()

    return jsonify({
        "message": "Soal berhasil ditambahkan",
        "question": question_to_dict(question),
    }), 201


@admin_bp.route(
    "/questions/<int:material_id>",
    methods=["GET"],
)
@admin_bp.route(
    "/question/<int:material_id>",
    methods=["GET"],
)
@jwt_required()
def get_questions_by_material(material_id):
    _, error = require_admin()

    if error:
        return error

    questions = db.session.execute(
        db.select(Question)
        .where(
            Question.material_id == material_id
        )
        .order_by(Question.id.asc())
    ).scalars().all()

    return jsonify([
        question_to_dict(item)
        for item in questions
    ]), 200


@admin_bp.route(
    "/question/<int:question_id>",
    methods=["PUT"],
)
@jwt_required()
def update_question(question_id):
    _, error = require_admin()

    if error:
        return error

    question = db.session.get(
        Question,
        question_id,
    )

    if not question:
        return jsonify({
            "error": "Soal tidak ditemukan"
        }), 404

    data = request.get_json(silent=True) or {}

    question.question_text = data.get(
        "question_text",
        question.question_text,
    )

    question.question_type = data.get(
        "question_type",
        question.question_type,
    )

    question.option_a = data.get(
        "option_a",
        question.option_a,
    )

    question.option_b = data.get(
        "option_b",
        question.option_b,
    )

    question.option_c = data.get(
        "option_c",
        question.option_c,
    )

    question.option_d = data.get(
        "option_d",
        question.option_d,
    )

    question.explanation = data.get(
        "explanation",
        question.explanation,
    )

    if data.get("correct_answer") is not None:
        correct_answer = (
            data.get("correct_answer").upper()
        )

        if correct_answer not in {
            "A", "B", "C", "D"
        }:
            return jsonify({
                "error": (
                    "Jawaban benar harus "
                    "A, B, C, atau D"
                )
            }), 400

        question.correct_answer = (
            correct_answer
        )

    db.session.commit()

    return jsonify({
        "message": "Soal berhasil diperbarui",
        "question": question_to_dict(question),
    }), 200


@admin_bp.route(
    "/question/<int:question_id>",
    methods=["DELETE"],
)
@jwt_required()
def delete_question(question_id):
    _, error = require_admin()

    if error:
        return error

    question = db.session.get(
        Question,
        question_id,
    )

    if not question:
        return jsonify({
            "error": "Soal tidak ditemukan"
        }), 404

    db.session.delete(question)
    db.session.commit()

    return jsonify({
        "message": "Soal berhasil dihapus"
    }), 200


# =========================================================
# IMPORT SOAL KUIS DARI CSV
# =========================================================

@admin_bp.route(
    "/import/questions",
    methods=["POST"],
)
@jwt_required()
def import_questions_csv():
    _, error = require_admin()

    if error:
        return error

    if "file" not in request.files:
        return jsonify({
            "error": "File CSV tidak ditemukan"
        }), 400

    file = request.files["file"]

    if not file.filename:
        return jsonify({
            "error": "Nama file kosong"
        }), 400

    valid_types = {
        "konsep",
        "pemahaman",
        "studi_kasus",
    }

    valid_answers = {
        "A", "B", "C", "D"
    }

    try:
        stream = io.StringIO(
            file.stream.read().decode("utf-8-sig"),
            newline=None,
        )

        reader = csv.DictReader(stream)

        if not reader.fieldnames:
            return jsonify({
                "error": "CSV soal tidak memiliki header"
            }), 400

        normalized_headers = {
            str(header).strip()
            for header in reader.fieldnames
            if header is not None
        }

        required_headers = {
            "material_title",
            "question_type",
            "question_text",
            "option_a",
            "option_b",
            "option_c",
            "option_d",
            "correct_answer",
            "explanation",
        }

        missing_headers = sorted(
            required_headers - normalized_headers
        )

        if missing_headers:
            return jsonify({
                "error": (
                    "Header soal wajib belum tersedia: "
                    + ", ".join(missing_headers)
                )
            }), 400

        materials = db.session.execute(
            db.select(Material)
        ).scalars().all()

        material_map = {
            material.title.strip().lower(): material
            for material in materials
        }

        imported = 0
        updated = 0
        skipped = []

        for row_number, row in enumerate(
            reader,
            start=2,
        ):
            material_title = (
                row.get("material_title")
                or ""
            ).strip()

            question_text = (
                row.get("question_text")
                or ""
            ).strip()

            question_type = (
                row.get("question_type")
                or "pemahaman"
            ).strip().lower()

            option_a = (
                row.get("option_a")
                or ""
            ).strip()

            option_b = (
                row.get("option_b")
                or ""
            ).strip()

            option_c = (
                row.get("option_c")
                or ""
            ).strip()

            option_d = (
                row.get("option_d")
                or ""
            ).strip()

            correct_answer = (
                row.get("correct_answer")
                or ""
            ).strip().upper()

            explanation = (
                row.get("explanation")
                or ""
            ).strip()

            material = material_map.get(
                material_title.lower()
            )

            if not material:
                skipped.append({
                    "row": row_number,
                    "reason": (
                        f"Modul '{material_title}' "
                        "tidak ditemukan"
                    ),
                })
                continue

            if not all([
                material_title,
                question_text,
                option_a,
                option_b,
                option_c,
                option_d,
                explanation,
            ]):
                skipped.append({
                    "row": row_number,
                    "reason": (
                        "Judul modul, pertanyaan, opsi A-D, "
                        "atau pembahasan ada yang kosong"
                    ),
                })
                continue

            if question_type not in valid_types:
                skipped.append({
                    "row": row_number,
                    "reason": (
                        "question_type harus pemahaman, "
                        "konsep, atau studi_kasus"
                    ),
                })
                continue

            if correct_answer not in valid_answers:
                skipped.append({
                    "row": row_number,
                    "reason": (
                        "correct_answer harus "
                        "A/B/C/D"
                    ),
                })
                continue

            existing = db.session.execute(
                db.select(Question).where(
                    Question.material_id
                    == material.id,
                    func.lower(
                        Question.question_text
                    )
                    == question_text.lower(),
                )
            ).scalar_one_or_none()

            if existing:
                existing.question_type = question_type
                existing.option_a = option_a
                existing.option_b = option_b
                existing.option_c = option_c
                existing.option_d = option_d
                existing.correct_answer = correct_answer
                existing.explanation = (
                    explanation or None
                )
                updated += 1
            else:
                db.session.add(Question(
                    material_id=material.id,
                    question_text=question_text,
                    question_type=question_type,
                    option_a=option_a,
                    option_b=option_b,
                    option_c=option_c,
                    option_d=option_d,
                    correct_answer=correct_answer,
                    explanation=(
                        explanation or None
                    ),
                ))
                imported += 1

        db.session.commit()

        return jsonify({
            "message": "Import CSV soal selesai",
            "imported": imported,
            "updated": updated,
            "skipped": skipped,
        }), 200

    except Exception as exc:
        db.session.rollback()

        return jsonify({
            "error": f"Gagal import soal: {str(exc)}"
        }), 500


# =========================================================
# CRUD FUN FACT
# =========================================================

@admin_bp.route("/funfact", methods=["POST"])
@jwt_required()
def add_funfact():
    _, error = require_admin()

    if error:
        return error

    data = request.get_json(silent=True) or {}

    fact_text = (
        data.get("fact_text")
        or ""
    ).strip()

    if not fact_text:
        return jsonify({
            "error": "Isi Fun Fact wajib diisi"
        }), 400

    fact = FunFact(
        fact_text=fact_text
    )

    db.session.add(fact)
    db.session.commit()

    return jsonify({
        "message": "Fun Fact berhasil ditambahkan",
        "funfact": funfact_to_dict(fact),
    }), 201


@admin_bp.route("/funfacts", methods=["GET"])
@admin_bp.route("/funfact", methods=["GET"])
@jwt_required()
def get_funfacts():
    """
    Endpoint baca Fun Fact untuk seluruh pengguna yang sudah login.

    Siswa perlu membaca data ini pada dashboard. Operasi tambah, edit,
    dan hapus tetap dilindungi require_admin().
    """
    facts = db.session.execute(
        db.select(FunFact)
        .order_by(FunFact.id.desc())
    ).scalars().all()

    return jsonify([
        funfact_to_dict(item)
        for item in facts
    ]), 200


@admin_bp.route(
    "/funfact/<int:fact_id>",
    methods=["PUT"],
)
@jwt_required()
def update_funfact(fact_id):
    _, error = require_admin()

    if error:
        return error

    fact = db.session.get(
        FunFact,
        fact_id,
    )

    if not fact:
        return jsonify({
            "error": "Fun Fact tidak ditemukan"
        }), 404

    data = request.get_json(silent=True) or {}

    fact_text = (
        data.get("fact_text")
        or ""
    ).strip()

    if not fact_text:
        return jsonify({
            "error": (
                "Isi Fun Fact tidak boleh kosong"
            )
        }), 400

    fact.fact_text = fact_text
    db.session.commit()

    return jsonify({
        "message": "Fun Fact berhasil diperbarui",
        "funfact": funfact_to_dict(fact),
    }), 200


@admin_bp.route(
    "/funfact/<int:fact_id>",
    methods=["DELETE"],
)
@jwt_required()
def delete_funfact(fact_id):
    _, error = require_admin()

    if error:
        return error

    fact = db.session.get(
        FunFact,
        fact_id,
    )

    if not fact:
        return jsonify({
            "error": "Fun Fact tidak ditemukan"
        }), 404

    db.session.delete(fact)
    db.session.commit()

    return jsonify({
        "message": "Fun Fact berhasil dihapus"
    }), 200
