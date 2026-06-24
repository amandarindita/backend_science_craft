from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models import User, Material, Question, FunFact

admin_bp = Blueprint('admin', __name__)

# --- FUNGSI BANTUAN CEK ADMIN ---
def is_admin(user_id):
    user = db.session.get(User, user_id)
    return user and user.role == 'admin'

# ==========================================
# CRUD MATERI
# ==========================================

@admin_bp.route('/material', methods=['POST'])
@jwt_required()
def add_material():
    current_user_id = get_jwt_identity()
    if not is_admin(current_user_id):
        return jsonify({"error": "Akses ditolak! Khusus Admin."}), 403

    data = request.get_json()
    new_material = Material(
        title=data.get('title'),
        content=data.get('content'),
        category=data.get('category'),
        unity_scene_id=data.get('unity_scene_id')
    )
    db.session.add(new_material)
    db.session.commit()
    return jsonify({"message": "Materi berhasil ditambahkan!", "id": new_material.id}), 201

@admin_bp.route('/materials', methods=['GET'])
@jwt_required()
def get_all_materials():
    # User biasa juga boleh lihat daftar materi kan? Jadi nggak usah cek admin di sini
    materials = db.session.execute(db.select(Material)).scalars().all()
    result = []
    for m in materials:
        result.append({
            "id": m.id,
            "title": m.title,
            "category": m.category,
            "unity_scene_id": m.unity_scene_id
        })
    return jsonify(result), 200
    
@admin_bp.route('/material/<int:id>', methods=['GET'])
@jwt_required()
def get_single_material(id):
    material = db.session.get(Material, id)
    if not material: return jsonify({"error": "Materi tidak ada"}), 404
    return jsonify({
        "id": material.id,
        "title": material.title,
        "content": material.content,
        "category": material.category,
        "unity_scene_id": material.unity_scene_id
    }), 200

# ==========================================
# CRUD SOAL KUIS (Berdasarkan Materi)
# ==========================================

@admin_bp.route('/question', methods=['POST'])
@jwt_required()
def add_question():
    current_user_id = get_jwt_identity()
    if not is_admin(current_user_id):
        return jsonify({"error": "Akses ditolak! Khusus Admin."}), 403

    data = request.get_json()
    material_id = data.get('material_id')
    
    # Pastikan materinya ada dulu
    material = db.session.get(Material, material_id)
    if not material:
        return jsonify({"error": "Materi tidak ditemukan!"}), 404

    new_question = Question(
        material_id=material_id,
        question_text=data.get('question_text'),
        option_a=data.get('option_a'),
        option_b=data.get('option_b'),
        option_c=data.get('option_c'),
        option_d=data.get('option_d'),
        correct_answer=data.get('correct_answer')
    )
    db.session.add(new_question)
    db.session.commit()
    return jsonify({"message": "Soal berhasil ditambahkan ke materi tersebut!"}), 201

@admin_bp.route('/questions/<int:material_id>', methods=['GET'])
@jwt_required()
def get_questions_by_material(material_id):
    # Ambil semua soal yang nyambung sama materi ini
    questions = db.session.execute(db.select(Question).filter_by(material_id=material_id)).scalars().all()
    result = []
    for q in questions:
        result.append({
            "id": q.id,
            "question_text": q.question_text,
            "option_a": q.option_a,
            "option_b": q.option_b,
            "option_c": q.option_c,
            "option_d": q.option_d,
            "correct_answer": q.correct_answer
        })
    return jsonify(result), 200
# ==========================================
# CRUD FUN FACT
# ==========================================

@admin_bp.route('/funfact', methods=['POST'])
@jwt_required()
def add_funfact():
    current_user_id = get_jwt_identity()
    if not is_admin(current_user_id):
        return jsonify({"error": "Akses ditolak! Khusus Admin."}), 403

    data = request.get_json()
    new_fact = FunFact(fact_text=data.get('fact_text'))
    
    db.session.add(new_fact)
    db.session.commit()
    return jsonify({"message": "Fun Fact berhasil ditambahkan!"}), 201

@admin_bp.route('/funfacts', methods=['GET'])
@jwt_required()
def get_funfacts():
    # User biasa juga bisa lihat fun fact
    facts = db.session.execute(db.select(FunFact)).scalars().all()
    result = [{"id": f.id, "fact_text": f.fact_text} for f in facts]
    return jsonify(result), 200
# ==========================================
# LANJUTAN: UPDATE & DELETE MATERI
# ==========================================

@admin_bp.route('/material/<int:id>', methods=['PUT'])
@jwt_required()
def update_material(id):
    current_user_id = get_jwt_identity()
    if not is_admin(current_user_id):
        return jsonify({"error": "Akses ditolak! Khusus Admin."}), 403

    material = db.session.get(Material, id)
    if not material:
        return jsonify({"error": "Materi tidak ditemukan!"}), 404

    data = request.get_json()
    material.title = data.get('title', material.title)
    material.content = data.get('content', material.content)
    material.category = data.get('category', material.category)
    material.unity_scene_id = data.get('unity_scene_id', material.unity_scene_id)
    
    db.session.commit()
    return jsonify({"message": "Materi berhasil diperbarui!"}), 200

@admin_bp.route('/material/<int:id>', methods=['DELETE'])
@jwt_required()
def delete_material(id):
    current_user_id = get_jwt_identity()
    if not is_admin(current_user_id):
        return jsonify({"error": "Akses ditolak! Khusus Admin."}), 403

    material = db.session.get(Material, id)
    if not material:
        return jsonify({"error": "Materi tidak ditemukan!"}), 404

    # Hapus semua soal yang terkait dengan materi ini dulu
    db.session.execute(db.delete(Question).filter_by(material_id=id))
    
    db.session.delete(material)
    db.session.commit()
    return jsonify({"message": "Materi dan soal terkait berhasil dihapus!"}), 200


# ==========================================
# LANJUTAN: UPDATE & DELETE SOAL KUIS
# ==========================================

@admin_bp.route('/question/<int:id>', methods=['PUT'])
@jwt_required()
def update_question(id):
    current_user_id = get_jwt_identity()
    if not is_admin(current_user_id):
        return jsonify({"error": "Akses ditolak! Khusus Admin."}), 403

    question = db.session.get(Question, id)
    if not question:
        return jsonify({"error": "Soal tidak ditemukan!"}), 404

    data = request.get_json()
    question.question_text = data.get('question_text', question.question_text)
    question.option_a = data.get('option_a', question.option_a)
    question.option_b = data.get('option_b', question.option_b)
    question.option_c = data.get('option_c', question.option_c)
    question.option_d = data.get('option_d', question.option_d)
    question.correct_answer = data.get('correct_answer', question.correct_answer)
    
    db.session.commit()
    return jsonify({"message": "Soal berhasil diperbarui!"}), 200

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
# LANJUTAN: UPDATE & DELETE FUN FACT
# ==========================================

@admin_bp.route('/funfact/<int:id>', methods=['PUT'])
@jwt_required()
def update_funfact(id):
    current_user_id = get_jwt_identity()
    if not is_admin(current_user_id):
        return jsonify({"error": "Akses ditolak! Khusus Admin."}), 403

    fact = db.session.get(FunFact, id)
    if not fact:
        return jsonify({"error": "Fun Fact tidak ditemukan!"}), 404

    data = request.get_json()
    fact.fact_text = data.get('fact_text', fact.fact_text)
    
    db.session.commit()
    return jsonify({"message": "Fun Fact berhasil diperbarui!"}), 200

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
# (Nanti kamu bisa tambahin rute metode ['PUT'] untuk Edit dan ['DELETE'] untuk Hapus kalau Flutter-nya udah siap)