from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from datetime import datetime 
from models import (
    User,
    UserProgress,
    UserBadge,
    Material,
    Badge,
    Notification,
    FunFact,
    UserFunFactRead,
    UserLabResult
)
import json
gamification_bp = Blueprint('gamification', __name__)

def beri_badge_ke_user(user_id, badge_name):
    """
    Fungsi internal untuk memeriksa dan memberikan badge ke siswa.
    Mencegah duplikasi agar user tidak mendapat badge yang sama berkali-kali.
    """
    badge = db.session.scalar(db.select(Badge).filter_by(name=badge_name))
    if not badge:
        return False

    existing = db.session.scalar(db.select(UserBadge).filter_by(user_id=user_id, badge_id=badge.id))
    
    # 3. Kalau belum punya, masukkan ke database user_badges + notifications
    if not existing:
        # A. Masukkan piala ke lemari user
        new_ub = UserBadge(user_id=user_id, badge_id=badge.id, unlocked_at=datetime.utcnow())
        db.session.add(new_ub)
        
        # B. OTOMATIS CATAT DI NOTIFICATION CENTER 🌟
        new_notif = Notification(
            user_id=user_id,
            title="Badge Baru Terbuka! 🎉",
            message=f"Selamat! Kamu berhasil mendapatkan pencapaian '{badge.name}'. Cek profilmu buat lihat pialanya!"
        )
        db.session.add(new_notif)
        
        db.session.commit()
        return True
    return False


# ==========================================
# 📱 ROUTES SYSTEMS
# ==========================================
# 1. SINKRONISASI PROGRESS + OTOMATIS TRIGGER BADGE (VERSI PINTAR)
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
    
    # 🌟 FIX ERROR DISINI: Kasih nilai awal 0.0 dulu biar pasti ke-define
    progress_lama = 0.0 
    
    if user_progress:
        progress_lama = float(user_progress.progress)
        user_progress.progress = float(progress)
    else:
        user_progress = UserProgress(user_id=current_user_id, material_id=material_id, progress=float(progress))
        db.session.add(user_progress)

    # 🌟 UPGRADE API HIJAU & NAMBAH 60 XP
    # 🌟 UPDATE STATUS + XP MATERI
    MATERIAL_XP = 50
    xp_added = 0
    old_level = 1
    new_level = 1
    level_up = False

    user_sekarang = db.session.get(User, current_user_id)

    if user_sekarang:
        user_sekarang.daily_status = 'active'

        old_level = (user_sekarang.total_xp // 200) + 1

    if float(progress) >= 1.0 and progress_lama < 1.0:
        user_sekarang.total_xp += MATERIAL_XP
        xp_added = MATERIAL_XP

    new_level = (user_sekarang.total_xp // 200) + 1
    level_up = new_level > old_level

    if level_up:
        db.session.add(Notification(
            user_id=current_user_id,
            title="Hore! Level Naik! 🚀",
            message=f"Keren banget! Sekarang kamu naik ke Level {new_level}!"
        ))

    db.session.commit()

    badge_baru_didapat = []

    # 🎯 [LOGIKA TRIGGER BADGE OTOMATIS] 🎯
    if float(progress) >= 1.0:
        
        # A. First Spark (1 Materi Pertama)
        completed_count = db.session.scalar(
            db.select(db.func.count(UserProgress.id)).filter_by(user_id=current_user_id, progress=1.0)
        )
        if completed_count == 1:
            if beri_badge_ke_user(current_user_id, "First Spark"):
                badge_baru_didapat.append("First Spark")

        # B. Night Owl (Jam 10 Malam - 3 Pagi)
        now_hour = datetime.now().hour
        if now_hour >= 22 or now_hour <= 3:
            if beri_badge_ke_user(current_user_id, "Night Owl"):
                badge_baru_didapat.append("Night Owl")

        # C. Ambil Data Materi buat cek Kategori & Lab
        material = db.session.get(Material, material_id)
        if material:
            # --- CEK BADGE KATEGORI (Mastery) ---
            cat = material.category 
            total_in_cat = db.session.scalar(
                db.select(db.func.count(Material.id)).filter_by(category=cat)
            )
            user_done_in_cat = db.session.scalar(
                db.select(db.func.count(UserProgress.id))
                .join(Material, UserProgress.material_id == Material.id)
                .filter(UserProgress.user_id == current_user_id, UserProgress.progress >= 1.0, Material.category == cat)
            )
            
            if total_in_cat > 0 and user_done_in_cat == total_in_cat:
                target_badge = ""
                if cat == 'Biologi': target_badge = "Darwin’s Successor"
                elif cat == 'Fisika': target_badge = "Quantum Overlord"
                elif cat == 'Kimia': target_badge = "The Modern Alchemist"
                
                if target_badge and beri_badge_ke_user(current_user_id, target_badge):
                    badge_baru_didapat.append(target_badge)
            
            return jsonify({
                "message": "Progress tersimpan di server",
                "xp_added": xp_added,
                "current_xp": user_sekarang.total_xp if user_sekarang else 0,
                "level": new_level,
                "level_up": level_up,
                "new_badges_unlocked": badge_baru_didapat
            }), 200
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


# 3. TAMBAH XP + OTOMATIS DETEKSI NAIK LEVEL 🌟
@gamification_bp.route('/gamification/xp', methods=['POST'])
@jwt_required()
def add_xp():
    current_user_id = get_jwt_identity()
    data = request.get_json()
    amount = data.get('amount')

    if not amount: return jsonify({"error": "Jumlah XP diperlukan"}), 400

    user = db.session.get(User, current_user_id)
    if user:
        # Hitung level sebelum ditambah XP (Kelipatan 200)
        old_level = (user.total_xp // 200) + 1
        
        user.total_xp += int(amount)
        
        # Hitung level setelah ditambah XP
        new_level = (user.total_xp // 200) + 1
        
        # Jika level baru lebih gede, berarti Amanda NAIK LEVEL! Tembak notifikasi! 🎉
        if new_level > old_level:
            new_notif = Notification(
                user_id=current_user_id,
                title="Hore! Level Naik! 🚀",
                message=f"Keren banget! Sekarang kamu naik ke Level {new_level}. Tingkatkan terus belajarmu, ya!"
            )
            db.session.add(new_notif)
            
        db.session.commit()
        return jsonify({
            "message": "XP bertambah", 
            "current_xp": user.total_xp,
            "level": new_level
        }), 200
    return jsonify({"error": "User tidak ditemukan"}), 404


# 4. AMBIL DATA GAMIFIKASI USER (Dipakai di Profil Flutter)
@gamification_bp.route('/gamification/user-data', methods=['GET'])
@jwt_required()
def get_user_data():
    current_user_id = get_jwt_identity()
    user = db.session.get(User, current_user_id)
    
    user_badges = db.session.execute(
        db.select(UserBadge).filter_by(user_id=current_user_id)
    ).scalars().all()
    
    badge_list = [{
        "name": ub.badge.name,
        "description": ub.badge.description,
        "icon_name": ub.badge.icon_name
    } for ub in user_badges]

    if user:
        # Hitung level saat ini secara linear berdasarkan total_xp mentah di DB
        current_level = (user.total_xp // 200) + 1
        
        return jsonify({
            "username": user.username,
            "total_xp": user.total_xp,
            "level": current_level, # 🌟 Mengirim info level terkini ke Flutter
            "streak": user.streak_count, 
            "badges": badge_list, 
            "has_password": user.password_hash is not None, 
            "email": user.email,
            "daily_status": user.daily_status,
            "avatar": user.avatar if user.avatar else 'assets/aira.png'
        }), 200
    return jsonify({"error": "User tidak ditemukan"}), 404


# 5. UNLOCK MANUAl BADGE
@gamification_bp.route('/gamification/badge', methods=['POST'])
@jwt_required()
def unlock_badge():
    current_user_id = get_jwt_identity()
    data = request.get_json()
    badge_name = data.get('badge_name')

    if not badge_name: return jsonify({"error": "Nama badge diperlukan"}), 400

    sukses = beri_badge_ke_user(current_user_id, badge_name)

    if sukses:
        return jsonify({"message": f"Badge '{badge_name}' berhasil dibuka!"}), 200
    return jsonify({"message": "User sudah punya badge ini atau nama badge salah"}), 200


# ==========================================
# 📬 6. IN-APP NOTIFICATION CENTER ROUTE 🌟
# ==========================================
@gamification_bp.route('/notifications', methods=['GET'])
@jwt_required()
def get_notifications():
    """
    Mengambil seluruh riwayat notifikasi in-app milik user (Urut dari yang paling baru).
    Dipakai Flutter pas user nge-klik tombol ikon lonceng.
    """
    current_user_id = get_jwt_identity()
    
    notifs = db.session.execute(
        db.select(Notification)
        .filter_by(user_id=current_user_id)
        .order_by(Notification.created_at.desc())
    ).scalars().all()
    
    list_notif = [{
        "id": n.id,
        "title": n.title,
        "message": n.message,
        "is_read": n.is_read,
        "created_at": n.created_at.strftime("%Y-%m-%d %H:%M:%S")
    } for n in notifs]
    
    return jsonify(list_notif), 200

# ==========================================
# 🎯 7. JALUR SUBMIT KUIS & BONUS XP + BADGE (VERSI SOLID!)
# ==========================================
@gamification_bp.route('/quiz/submit', methods=['POST'])
@jwt_required()
def submit_quiz():
    current_user_id = get_jwt_identity()
    data = request.get_json() or {}

    try:
        material_id = int(data.get('material_id'))
        total_correct = int(data.get('total_correct'))
        total_soal = int(data.get('total_soal'))
    except (TypeError, ValueError):
        return jsonify({"error": "Data kuis tidak valid"}), 400

    if total_soal <= 0:
        return jsonify({"error": "Jumlah soal tidak valid"}), 400

    score = int((total_correct / total_soal) * 100)

    user = db.session.get(User, current_user_id)
    if not user:
        return jsonify({"error": "User tidak ditemukan"}), 404

    user_progress = db.session.scalar(
        db.select(UserProgress).filter_by(
            user_id=current_user_id,
            material_id=material_id
        )
    )

    if not user_progress:
        user_progress = UserProgress(
            user_id=current_user_id,
            material_id=material_id,
            progress=1.0,
            quiz_score=score,
            quiz_completed=False
        )
        db.session.add(user_progress)

    was_quiz_completed = bool(user_progress.quiz_completed)

    # Simpan nilai terbaik
    if user_progress.quiz_score is None or score > user_progress.quiz_score:
        user_progress.quiz_score = score

    if user_progress.progress is None or user_progress.progress < 1.0:
        user_progress.progress = 1.0

    QUIZ_XP = 40
    xp_added = 0

    old_level = (user.total_xp // 200) + 1

    # XP cuma sekali per materi kuis
    if not was_quiz_completed:
        user.total_xp += QUIZ_XP
        xp_added = QUIZ_XP
        user_progress.quiz_completed = True

    user.daily_status = 'active'

    new_level = (user.total_xp // 200) + 1
    level_up = new_level > old_level

    if level_up:
        db.session.add(Notification(
            user_id=current_user_id,
            title="Hore! Level Naik! 🚀",
            message=f"Keren banget! Sekarang kamu naik ke Level {new_level}!"
        ))

    badge_baru_didapat = []

    # Badge kuis
    if score == 100:
        # Grand Analyst hanya kalau nilai 100 saat percobaan pertama
        if not was_quiz_completed:
            if beri_badge_ke_user(current_user_id, "Grand Analyst"):
                badge_baru_didapat.append("Grand Analyst")

        perfect_quizzes = db.session.scalar(
            db.select(db.func.count(UserProgress.id))
            .filter_by(user_id=current_user_id, quiz_score=100)
        )

        if perfect_quizzes >= 3:
            if beri_badge_ke_user(current_user_id, "Flawless Victory"):
                badge_baru_didapat.append("Flawless Victory")

    db.session.commit()

    return jsonify({
        "message": "Jawaban kuis berhasil diproses!",
        "score": score,
        "xp_added": xp_added,
        "current_xp": user.total_xp,
        "level": new_level,
        "level_up": level_up,
        "is_first_quiz_completion": not was_quiz_completed,
        "new_badges_unlocked": badge_baru_didapat
    }), 200

# ==========================================
# 🌟 8. JALUR BACA FUN FACT & BADGE TRIVIA ROVER
# ==========================================
@gamification_bp.route('/funfacts/read', methods=['POST'])
@jwt_required()
def read_funfact():
    current_user_id = get_jwt_identity()
    data = request.get_json() or {}

    funfact_id = data.get('funfact_id')

    if funfact_id is None:
        return jsonify({"error": "FunFact ID wajib diisi"}), 400

    try:
        funfact_id = int(funfact_id)
    except (TypeError, ValueError):
        return jsonify({"error": "FunFact ID tidak valid"}), 400

    funfact = db.session.get(FunFact, funfact_id)
    if not funfact:
        return jsonify({"error": "FunFact tidak ditemukan"}), 404

    existing = db.session.scalar(
        db.select(UserFunFactRead).filter_by(
            user_id=current_user_id,
            funfact_id=funfact_id
        )
    )

    is_new_read = False

    if not existing:
        read_log = UserFunFactRead(
            user_id=current_user_id,
            funfact_id=funfact_id
        )
        db.session.add(read_log)
        is_new_read = True

    read_count = db.session.scalar(
        db.select(db.func.count(UserFunFactRead.id))
        .filter_by(user_id=current_user_id)
    )

    badge_baru_didapat = []

    if read_count >= 5:
        if beri_badge_ke_user(current_user_id, "Trivia Rover"):
            badge_baru_didapat.append("Trivia Rover")

    db.session.commit()

    return jsonify({
        "message": "FunFact berhasil dibaca",
        "is_new_read": is_new_read,
        "read_count": read_count,
        "new_badges_unlocked": badge_baru_didapat
    }), 200

@gamification_bp.route('/lab/complete', methods=['POST'])
@jwt_required()
def complete_lab():
    current_user_id = get_jwt_identity()
    data = request.get_json() or {}

    material_id = data.get('material_id')

    if material_id is None:
        return jsonify({"error": "Material ID wajib diisi"}), 400

    material = db.session.get(Material, material_id)
    if not material:
        return jsonify({"error": "Materi tidak ditemukan"}), 404

    if not material.unity_scene_id:
        return jsonify({"error": "Materi ini tidak memiliki simulasi lab"}), 400

    user = db.session.get(User, current_user_id)
    if not user:
        return jsonify({"error": "User tidak ditemukan"}), 404

    user_progress = db.session.scalar(
        db.select(UserProgress).filter_by(
            user_id=current_user_id,
            material_id=material_id
        )
    )

    if not user_progress:
        user_progress = UserProgress(
            user_id=current_user_id,
            material_id=material_id,
            progress=0.0,
            lab_completed=False
        )
        db.session.add(user_progress)

    was_lab_completed = bool(user_progress.lab_completed)

    LAB_XP = 100
    xp_added = 0

    old_level = (user.total_xp // 200) + 1

    user.daily_status = 'active'
    
    new_level = old_level
    level_up = False
    if not was_lab_completed:
        user_progress.lab_completed = True
        user.total_xp += LAB_XP
        xp_added = LAB_XP

        new_level = (user.total_xp // 200) + 1
        level_up = new_level > old_level

        if level_up:
            db.session.add(Notification(
                user_id=current_user_id,
                title="Hore! Level Naik! 🚀",
                message=f"Keren banget! Sekarang kamu naik ke Level {new_level}!"
            ))

    db.session.flush()

    badge_baru_didapat = []

    total_lab_selesai = db.session.scalar(
        db.select(db.func.count(UserProgress.id))
        .join(Material, UserProgress.material_id == Material.id)
        .filter(
            UserProgress.user_id == current_user_id,
            UserProgress.lab_completed == True,
            Material.unity_scene_id != None
        )
    )

    if total_lab_selesai >= 1:
        if beri_badge_ke_user(current_user_id, "Virtual Researcher"):
            badge_baru_didapat.append("Virtual Researcher")

    if total_lab_selesai >= 3:
        if beri_badge_ke_user(current_user_id, "Mad Scientist"):
            badge_baru_didapat.append("Mad Scientist")

    db.session.commit()

    return jsonify({
        "message": "Simulasi lab berhasil diselesaikan",
        "xp_added": xp_added,
        "current_xp": user.total_xp,
        "level": new_level,
        "level_up": level_up,
        "lab_completed": True,
        "new_badges_unlocked": badge_baru_didapat
    }), 200

@gamification_bp.route('/lab/result/save', methods=['POST'])
@jwt_required()
def save_lab_result():
    current_user_id = get_jwt_identity()
    data = request.get_json() or {}

    material_id = data.get('material_id')
    experiment_id = data.get('experiment_id') or data.get('experimentId')
    display_name = data.get('display_name') or data.get('displayName')

    if material_id is None:
        return jsonify({"error": "Material ID wajib diisi"}), 400

    try:
        material_id = int(material_id)
    except (TypeError, ValueError):
        return jsonify({"error": "Material ID tidak valid"}), 400

    material = db.session.get(Material, material_id)
    if not material:
        return jsonify({"error": "Materi tidak ditemukan"}), 404

    if not material.unity_scene_id:
        return jsonify({"error": "Materi ini tidak memiliki simulasi lab"}), 400

    if not experiment_id:
        experiment_id = material.unity_scene_id

    summary_json = data.get('summary_json') or data.get('summaryJson')
    activities = data.get('activities', [])

    # Kalau summary_json dikirim sebagai dict/list, ubah jadi string JSON
    if isinstance(summary_json, (dict, list)):
        summary_json = json.dumps(summary_json, ensure_ascii=False)

    # Kalau summary_json None, simpan string kosong
    if summary_json is None:
        summary_json = ""

    activities_json = json.dumps(activities, ensure_ascii=False)
    raw_payload_json = json.dumps(data, ensure_ascii=False)

    duration_seconds = data.get('duration_seconds') or data.get('durationSeconds') or 0
    remaining_seconds = data.get('remaining_seconds') or data.get('remainingSeconds') or 0
    elapsed_seconds = data.get('elapsed_seconds') or data.get('elapsedSeconds') or 0
    timestamp_utc = data.get('timestamp_utc') or data.get('timestampUtc')

    try:
        duration_seconds = int(float(duration_seconds))
        remaining_seconds = int(float(remaining_seconds))
        elapsed_seconds = int(float(elapsed_seconds))
    except (TypeError, ValueError):
        duration_seconds = 0
        remaining_seconds = 0
        elapsed_seconds = 0

    lab_result = UserLabResult(
        user_id=current_user_id,
        material_id=material_id,
        experiment_id=experiment_id,
        display_name=display_name,
        duration_seconds=duration_seconds,
        remaining_seconds=remaining_seconds,
        elapsed_seconds=elapsed_seconds,
        timestamp_utc=timestamp_utc,
        summary_json=summary_json,
        activities_json=activities_json,
        raw_payload_json=raw_payload_json
    )

    db.session.add(lab_result)
    db.session.commit()

    return jsonify({
        "message": "Hasil simulasi lab berhasil disimpan",
        "result_id": lab_result.id,
        "experiment_id": lab_result.experiment_id,
        "material_id": lab_result.material_id
    }), 201

@gamification_bp.route('/lab/results', methods=['GET'])
@jwt_required()
def get_lab_results():
    current_user_id = get_jwt_identity()

    results = db.session.execute(
        db.select(UserLabResult)
        .filter_by(user_id=current_user_id)
        .order_by(UserLabResult.created_at.desc())
    ).scalars().all()

    response = []

    for item in results:
        response.append({
            "id": item.id,
            "material_id": item.material_id,
            "experiment_id": item.experiment_id,
            "display_name": item.display_name,
            "elapsed_seconds": item.elapsed_seconds,
            "duration_seconds": item.duration_seconds,
            "remaining_seconds": item.remaining_seconds,
            "timestamp_utc": item.timestamp_utc,
            "created_at": item.created_at.strftime("%Y-%m-%d %H:%M:%S")
        })

    return jsonify(response), 200

@gamification_bp.route('/lab/results/<int:result_id>', methods=['GET'])
@jwt_required()
def get_lab_result_detail(result_id):
    current_user_id = get_jwt_identity()

    result = db.session.scalar(
        db.select(UserLabResult).filter_by(
            id=result_id,
            user_id=current_user_id
        )
    )

    if not result:
        return jsonify({"error": "Hasil lab tidak ditemukan"}), 404

    try:
        activities = json.loads(result.activities_json or "[]")
    except json.JSONDecodeError:
        activities = []

    try:
        summary = json.loads(result.summary_json or "{}")
    except json.JSONDecodeError:
        summary = result.summary_json

    return jsonify({
        "id": result.id,
        "material_id": result.material_id,
        "experiment_id": result.experiment_id,
        "display_name": result.display_name,
        "duration_seconds": result.duration_seconds,
        "remaining_seconds": result.remaining_seconds,
        "elapsed_seconds": result.elapsed_seconds,
        "timestamp_utc": result.timestamp_utc,
        "summary": summary,
        "activities": activities,
        "created_at": result.created_at.strftime("%Y-%m-%d %H:%M:%S")
    }), 200