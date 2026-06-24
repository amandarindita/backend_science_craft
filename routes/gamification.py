from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models import User, UserProgress, UserBadge

# Blueprint ini nggak usah dipakein url_prefix nanti di app.py 
# biar rutenya persis sama kayak script aslimu.
gamification_bp = Blueprint('gamification', __name__)

# 1. SINKRONISASI PROGRESS SATU MATERI
@gamification_bp.route('/sync/progress', methods=['POST'])
@jwt_required()
def sync_progress():
    current_user_id = get_jwt_identity()
    data = request.get_json()
    material_id = data.get('material_id')
    progress = data.get('progress')

    if material_id is None or progress is None:
        return jsonify({"error": "Data tidak lengkap"}), 400

    user_progress = db.session.scalar(db.select(UserProgress).filter_by(
        user_id=current_user_id, material_id=material_id
    ))
    
    if user_progress:
        user_progress.progress = progress
    else:
        user_progress = UserProgress(user_id=current_user_id, material_id=material_id, progress=progress)
        db.session.add(user_progress)

    db.session.commit()
    return jsonify({"message": "Progress tersimpan di server"}), 200

# 2. AMBIL SEMUA PROGRESS USER
@gamification_bp.route('/sync/all-progress', methods=['GET'])
@jwt_required()
def get_all_progress():
    current_user_id = get_jwt_identity()
    all_progress = db.session.execute(
        db.select(UserProgress).filter_by(user_id=current_user_id)
    ).scalars().all()

    result = [{"material_id": p.material_id, "progress": p.progress} for p in all_progress]
    return jsonify(result), 200

# 3. TAMBAH XP
@gamification_bp.route('/gamification/xp', methods=['POST'])
@jwt_required()
def add_xp():
    current_user_id = get_jwt_identity()
    data = request.get_json()
    amount = data.get('amount')

    if not amount: return jsonify({"error": "Jumlah XP diperlukan"}), 400

    user = db.session.get(User, current_user_id)
    if user:
        user.total_xp += int(amount)
        db.session.commit()
        return jsonify({"message": "XP bertambah", "current_xp": user.total_xp}), 200
    return jsonify({"error": "User tidak ditemukan"}), 404

# 4. AMBIL DATA GAMIFIKASI USER (Dipakai di Profil)
@gamification_bp.route('/gamification/user-data', methods=['GET'])
@jwt_required()
def get_user_data():
    current_user_id = get_jwt_identity()
    user = db.session.get(User, current_user_id)
    
    badges = db.session.execute(
        db.select(UserBadge).filter_by(user_id=current_user_id)
    ).scalars().all()
    badge_codes = [b.badge_code for b in badges]

    if user:
        return jsonify({
            "username": user.username,
            "total_xp": user.total_xp,
            "streak": user.streak_count, 
            "badges": badge_codes,
            "has_password": user.password_hash is not None, 
            "avatar": user.avatar if user.avatar else 'assets/aira.png'
        }), 200
    return jsonify({"error": "User tidak ditemukan"}), 404

# 5. UNLOCK BADGE BARU
@gamification_bp.route('/gamification/badge', methods=['POST'])
@jwt_required()
def unlock_badge():
    current_user_id = get_jwt_identity()
    data = request.get_json()
    badge_code = data.get('badge_code')

    if not badge_code: return jsonify({"error": "Kode badge diperlukan"}), 400

    existing = db.session.scalar(db.select(UserBadge).filter_by(
        user_id=current_user_id, badge_code=badge_code
    ))

    if existing: return jsonify({"message": "User sudah punya badge ini"}), 200

    new_badge = UserBadge(user_id=current_user_id, badge_code=badge_code)
    db.session.add(new_badge)
    db.session.commit()
    return jsonify({"message": f"Badge {badge_code} berhasil dibuka!"}), 200