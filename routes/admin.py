import os
import csv
import io
import json
from datetime import datetime
from sqlalchemy import func
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename

from extensions import db
from models import User, Material, Question, FunFact

admin_bp = Blueprint('admin', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


# --- FUNGSI BANTUAN CEK ADMIN ---
def is_admin(user_id):
    user = db.session.get(User, user_id)
    return user and user.role == 'admin'


def allowed_file(filename):
    return (
        '.' in filename and
        filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def save_uploaded_image(file):
    if not file or file.filename == '':
        return None

    if not allowed_file(file.filename):
        return None

    upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
    os.makedirs(upload_folder, exist_ok=True)

    filename = secure_filename(file.filename)
    name, ext = os.path.splitext(filename)
    unique_filename = f"{name}_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}{ext}"

    file_path = os.path.join(upload_folder, unique_filename)
    file.save(file_path)

    return f"/uploads/{unique_filename}"


def material_to_dict(material):
    return {
        "id": material.id,
        "title": material.title,
        "content": material.content,
        "category": material.category,
        "unity_scene_id": material.unity_scene_id,
        "instructions": material.instructions,
        "image_url": getattr(material, "image_url", None),
        "created_at": material.created_at.strftime("%Y-%m-%d %H:%M:%S") if material.created_at else None,
    }

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
    }

def funfact_to_dict(fact):
    return {
        "id": fact.id,
        "fact_text": fact.fact_text,
        "created_at": fact.created_at.strftime("%Y-%m-%d %H:%M:%S") if fact.created_at else None,
    }


def get_request_data():
    """
    Biar endpoint bisa nerima JSON biasa atau form-data.
    Kalau ada gambar, pakai form-data.
    Kalau tanpa gambar, JSON tetap bisa.
    """
    if request.content_type and request.content_type.startswith('multipart/form-data'):
        return request.form
    return request.get_json() or {}


# ==========================================
# CRUD MATERI
# ==========================================

@admin_bp.route('/material', methods=['POST'])
@jwt_required()
def add_material():
    current_user_id = get_jwt_identity()
    if not is_admin(current_user_id):
        return jsonify({"error": "Akses ditolak! Khusus Admin."}), 403

    data = get_request_data()

    image_url = data.get('image_url')

    if 'image' in request.files:
        uploaded_url = save_uploaded_image(request.files['image'])
        if uploaded_url:
            image_url = uploaded_url

    new_material = Material(
        title=data.get('title'),
        content=data.get('content'),
        category=data.get('category'),
        unity_scene_id=data.get('unity_scene_id'),
        instructions=data.get('instructions'),
        image_url=image_url,
    )

    db.session.add(new_material)
    db.session.commit()

    return jsonify({
        "message": "Materi berhasil ditambahkan!",
        "material": material_to_dict(new_material)
    }), 201


@admin_bp.route('/materials', methods=['GET'])
@admin_bp.route('/material', methods=['GET'])
@jwt_required()
def get_all_materials():
    materials = db.session.execute(
        db.select(Material).order_by(Material.id.desc())
    ).scalars().all()

    result = [material_to_dict(m) for m in materials]
    return jsonify(result), 200


@admin_bp.route('/material/<int:id>', methods=['GET'])
@jwt_required()
def get_single_material(id):
    material = db.session.get(Material, id)

    if not material:
        return jsonify({"error": "Materi tidak ada"}), 404

    return jsonify(material_to_dict(material)), 200


@admin_bp.route('/material/<int:id>', methods=['PUT'])
@jwt_required()
def update_material(id):
    current_user_id = get_jwt_identity()
    if not is_admin(current_user_id):
        return jsonify({"error": "Akses ditolak! Khusus Admin."}), 403

    material = db.session.get(Material, id)
    if not material:
        return jsonify({"error": "Materi tidak ditemukan!"}), 404

    data = get_request_data()

    material.title = data.get('title', material.title)
    material.content = data.get('content', material.content)
    material.category = data.get('category', material.category)
    material.unity_scene_id = data.get('unity_scene_id', material.unity_scene_id)
    material.instructions = data.get('instructions', material.instructions)

    image_url = data.get('image_url')
    if image_url:
        material.image_url = image_url

    if 'image' in request.files:
        uploaded_url = save_uploaded_image(request.files['image'])
        if uploaded_url:
            material.image_url = uploaded_url

    db.session.commit()

    return jsonify({
        "message": "Materi berhasil diperbarui!",
        "material": material_to_dict(material)
    }), 200


@admin_bp.route('/material/<int:id>', methods=['DELETE'])
@jwt_required()
def delete_material(id):
    current_user_id = get_jwt_identity()
    if not is_admin(current_user_id):
        return jsonify({"error": "Akses ditolak! Khusus Admin."}), 403

    material = db.session.get(Material, id)
    if not material:
        return jsonify({"error": "Materi tidak ditemukan!"}), 404

    db.session.execute(db.delete(Question).filter_by(material_id=id))
    db.session.delete(material)
    db.session.commit()

    return jsonify({"message": "Materi dan soal terkait berhasil dihapus!"}), 200

@admin_bp.route('/import/materials', methods=['POST'])
@jwt_required()
def import_materials_csv():
    current_user_id = get_jwt_identity()
    if not is_admin(current_user_id):
        return jsonify({"error": "Akses ditolak! Khusus Admin."}), 403

    if 'file' not in request.files:
        return jsonify({"error": "File CSV tidak ditemukan. Gunakan field name 'file'."}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({"error": "Nama file kosong."}), 400

    try:
        stream = io.StringIO(file.stream.read().decode("utf-8-sig"), newline=None)
        reader = csv.DictReader(stream)

        imported = 0
        updated = 0
        skipped = []

        for index, row in enumerate(reader, start=2):
            title = (row.get('title') or '').strip()
            category = (row.get('category') or '').strip()
            intro = (row.get('intro') or '').strip()

            if not title or not category:
                skipped.append({
                    "row": index,
                    "reason": "title/category kosong"
                })
                continue

            sections = []

            for i in range(1, 5):
                section_title = (row.get(f'section_{i}_title') or '').strip()
                section_content = (row.get(f'section_{i}_content') or '').strip()
                section_examples = (row.get(f'section_{i}_examples') or '').strip()

                if section_title or section_content or section_examples:
                    sections.append({
                        "title": section_title,
                        "content": section_content,
                        "examples": section_examples,
                        "image_path": ""
                    })

            if not sections:
                skipped.append({
                    "row": index,
                    "reason": "minimal 1 section wajib diisi"
                })
                continue

            combined_content = json.dumps({
                "intro": intro,
                "sections": sections
            }, ensure_ascii=False)

            existing_material = db.session.execute(
                db.select(Material).where(func.lower(Material.title) == title.lower())
            ).scalar_one_or_none()

            if existing_material:
                existing_material.category = category
                existing_material.content = combined_content
                updated += 1
            else:
                new_material = Material(
                    title=title,
                    category=category,
                    content=combined_content,
                    unity_scene_id="",
                    instructions="",
                    image_url=None,
                )
                db.session.add(new_material)
                imported += 1

        db.session.commit()

        return jsonify({
            "message": "Import CSV materi selesai.",
            "imported": imported,
            "updated": updated,
            "skipped": skipped
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Gagal import materi: {str(e)}"}), 500

@admin_bp.route('/import/questions', methods=['POST'])
@jwt_required()
def import_questions_csv():
    current_user_id = get_jwt_identity()
    if not is_admin(current_user_id):
        return jsonify({"error": "Akses ditolak! Khusus Admin."}), 403

    if 'file' not in request.files:
        return jsonify({"error": "File CSV tidak ditemukan. Gunakan field name 'file'."}), 400
    file = request.files['file']

    if file.filename == '':
       return jsonify({"error": "Nama file kosong."}), 400
    valid_types = {'konsep', 'pemahaman', 'studi_kasus'}
    valid_answers = {'A', 'B', 'C', 'D'}

    try:
            stream = io.StringIO(file.stream.read().decode("utf-8-sig"), newline=None)
            reader = csv.DictReader(stream)

            materials = db.session.execute(db.select(Material)).scalars().all()
            material_map = {
                m.title.strip().lower(): m for m in materials
            }

            imported = 0
            updated = 0
            skipped = []

            for index, row in enumerate(reader, start=2):
                material_title = (row.get('material_title') or '').strip()
                question_text = (row.get('question_text') or '').strip()
                question_type = (row.get('question_type') or 'pemahaman').strip().lower()
                option_a = (row.get('option_a') or '').strip()
                option_b = (row.get('option_b') or '').strip()
                option_c = (row.get('option_c') or '').strip()
                option_d = (row.get('option_d') or '').strip()
                correct_answer = (row.get('correct_answer') or '').strip().upper()

                if not material_title:
                    skipped.append({"row": index, "reason": "material_title kosong"})
                    continue

                material = material_map.get(material_title.lower())
                if not material:
                    skipped.append({
                        "row": index,
                        "reason": f"Materi '{material_title}' tidak ditemukan"
                    })
                    continue

                if not question_text or not option_a or not option_b or not option_c or not option_d:
                    skipped.append({
                        "row": index,
                        "reason": "pertanyaan/opsi jawaban ada yang kosong"
                    })
                    continue

                if question_type not in valid_types:
                    question_type = 'pemahaman'

                if correct_answer not in valid_answers:
                    skipped.append({
                        "row": index,
                        "reason": "correct_answer harus A/B/C/D"
                    })
                    continue

                existing_question = db.session.execute(
                    db.select(Question).where(
                        Question.material_id == material.id,
                        func.lower(Question.question_text) == question_text.lower()
                    )
                ).scalar_one_or_none()

                if existing_question:
                    existing_question.question_type = question_type
                    existing_question.option_a = option_a
                    existing_question.option_b = option_b
                    existing_question.option_c = option_c
                    existing_question.option_d = option_d
                    existing_question.correct_answer = correct_answer
                    updated += 1
                else:
                    new_question = Question(
                        material_id=material.id,
                        question_text=question_text,
                        question_type=question_type,
                        option_a=option_a,
                        option_b=option_b,
                        option_c=option_c,
                        option_d=option_d,
                        correct_answer=correct_answer
                    )
                    db.session.add(new_question)
                    imported += 1

            db.session.commit()

            return jsonify({
                "message": "Import CSV soal selesai.",
                "imported": imported,
                "updated": updated,
                "skipped": skipped
            }), 200

    except Exception as e:
        db.session.rollback()
    return jsonify({"error": f"Gagal import soal: {str(e)}"}), 500

# ==========================================
# CRUD SOAL KUIS
# ==========================================

@admin_bp.route('/question', methods=['POST'])
@jwt_required()
def add_question():
    current_user_id = get_jwt_identity()
    if not is_admin(current_user_id):
        return jsonify({"error": "Akses ditolak! Khusus Admin."}), 403

    data = request.get_json() or {}
    material_id = data.get('material_id')

    material = db.session.get(Material, material_id)
    if not material:
        return jsonify({"error": "Materi tidak ditemukan!"}), 404

    new_question = Question(
        material_id=material_id,
        question_text=data.get('question_text'),
        question_type=data.get('question_type', 'pemahaman'),
        option_a=data.get('option_a'),
        option_b=data.get('option_b'),
        option_c=data.get('option_c'),
        option_d=data.get('option_d'),
        correct_answer=data.get('correct_answer')
    )

    db.session.add(new_question)
    db.session.commit()

    return jsonify({
        "message": "Soal berhasil ditambahkan ke materi tersebut!",
        "question": question_to_dict(new_question)
    }), 201


@admin_bp.route('/questions/<int:material_id>', methods=['GET'])
@admin_bp.route('/question/<int:material_id>', methods=['GET'])
@jwt_required()
def get_questions_by_material(material_id):
    questions = db.session.execute(
        db.select(Question)
        .filter_by(material_id=material_id)
        .order_by(Question.id.desc())
    ).scalars().all()

    result = [question_to_dict(q) for q in questions]
    return jsonify(result), 200


@admin_bp.route('/question/<int:id>', methods=['PUT'])
@jwt_required()
def update_question(id):
    current_user_id = get_jwt_identity()
    if not is_admin(current_user_id):
        return jsonify({"error": "Akses ditolak! Khusus Admin."}), 403

    question = db.session.get(Question, id)
    if not question:
        return jsonify({"error": "Soal tidak ditemukan!"}), 404

    data = request.get_json() or {}

    question.question_text = data.get('question_text', question.question_text)
    question.question_type = data.get('question_type', question.question_type)
    question.option_a = data.get('option_a', question.option_a)
    question.option_b = data.get('option_b', question.option_b)
    question.option_c = data.get('option_c', question.option_c)
    question.option_d = data.get('option_d', question.option_d)
    question.correct_answer = data.get('correct_answer', question.correct_answer)

    db.session.commit()

    return jsonify({
        "message": "Soal berhasil diperbarui!",
        "question": question_to_dict(question)
    }), 200


@admin_bp.route('/question/<int:id>', methods=['DELETE'])
@jwt_required()
def delete_question(id):
    current_user_id = get_jwt_identity()
    if not is_admin(current_user_id):
        return jsonify({"error": "Akses ditolak! Khusus Admin."}), 403

    question = db.session.get(Question, id)
    if not question:
        return jsonify({"error": "Soal tidak ditemukan!"}), 404

    db.session.delete(question)
    db.session.commit()

    return jsonify({"message": "Soal berhasil dihapus!"}), 200


# ==========================================
# CRUD FUN FACT
# ==========================================

@admin_bp.route('/funfact', methods=['POST'])
@jwt_required()
def add_funfact():
    current_user_id = get_jwt_identity()
    if not is_admin(current_user_id):
        return jsonify({"error": "Akses ditolak! Khusus Admin."}), 403

    data = request.get_json() or {}
    fact_text = data.get('fact_text')

    if not fact_text:
        return jsonify({"error": "Isi Fun Fact tidak boleh kosong"}), 400

    new_fact = FunFact(fact_text=fact_text)

    db.session.add(new_fact)
    db.session.commit()

    return jsonify({
        "message": "Fun Fact berhasil ditambahkan!",
        "funfact": funfact_to_dict(new_fact)
    }), 201


@admin_bp.route('/funfacts', methods=['GET'])
@admin_bp.route('/funfact', methods=['GET'])
@jwt_required()
def get_funfacts():
    facts = db.session.execute(
        db.select(FunFact).order_by(FunFact.id.desc())
    ).scalars().all()

    result = [funfact_to_dict(f) for f in facts]
    return jsonify(result), 200


@admin_bp.route('/funfact/<int:id>', methods=['PUT'])
@jwt_required()
def update_funfact(id):
    current_user_id = get_jwt_identity()
    if not is_admin(current_user_id):
        return jsonify({"error": "Akses ditolak! Khusus Admin."}), 403

    fact = db.session.get(FunFact, id)
    if not fact:
        return jsonify({"error": "Fun Fact tidak ditemukan!"}), 404

    data = request.get_json() or {}
    fact.fact_text = data.get('fact_text', fact.fact_text)

    db.session.commit()

    return jsonify({
        "message": "Fun Fact berhasil diperbarui!",
        "funfact": funfact_to_dict(fact)
    }), 200


@admin_bp.route('/funfact/<int:id>', methods=['DELETE'])
@jwt_required()
def delete_funfact(id):
    current_user_id = get_jwt_identity()
    if not is_admin(current_user_id):
        return jsonify({"error": "Akses ditolak! Khusus Admin."}), 403

    fact = db.session.get(FunFact, id)
    if not fact:
        return jsonify({"error": "Fun Fact tidak ditemukan!"}), 404

    db.session.delete(fact)
    db.session.commit()

    return jsonify({"message": "Fun Fact berhasil dihapus!"}), 200