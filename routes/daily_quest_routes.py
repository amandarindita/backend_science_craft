from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timezone, timedelta
import random

from extensions import db
from models import User, DailyQuestDay, DailyQuestItem, Notification
from milestone_service import sync_user_milestones


daily_quest_bp = Blueprint('daily_quest', __name__)

# Biar reset hariannya ikut WIB, bukan UTC
JAKARTA_TZ = timezone(timedelta(hours=7))

REWARD_XP = 50

# Daftar kemungkinan quest harian
QUEST_POOL = [
    {
        "quest_key": "read_material",
        "title": "Baca 1 Materi",
        "description": "Selesaikan satu materi pembelajaran hari ini.",
        "target": 1
    },
    {
        "quest_key": "do_quiz",
        "title": "Kerjakan 1 Kuis",
        "description": "Kerjakan satu kuis dari materi yang tersedia.",
        "target": 1
    },
    {
        "quest_key": "open_lab",
        "title": "Buka Simulasi Lab",
        "description": "Coba satu simulasi virtual lab hari ini.",
        "target": 1
    },
    {
        "quest_key": "continue_learning",
        "title": "Lanjutkan Belajar",
        "description": "Buka kembali materi yang belum selesai.",
        "target": 1
    },
    {
        "quest_key": "collect_xp",
        "title": "Kumpulkan 50 XP",
        "description": "Dapatkan minimal 50 XP dari aktivitas belajar.",
        "target": 50
    },
]


def get_current_user_id():
    return int(get_jwt_identity())


def get_today_date():
    return datetime.now(JAKARTA_TZ).date()


def serialize_daily_quest(day):
    items = sorted(day.items, key=lambda item: item.id)

    return {
        "id": day.id,
        "date": day.quest_date.isoformat(),
        "reward_xp": day.reward_xp,
        "is_claimed": day.is_claimed,
        "all_completed": all(item.is_completed for item in items),
        "quests": [
            {
                "id": item.quest_key,
                "quest_key": item.quest_key,
                "title": item.title,
                "desc": item.description,
                "description": item.description,
                "target": item.target,
                "progress": item.progress,
                "is_completed": item.is_completed
            }
            for item in items
        ]
    }


def get_or_create_today_quest(user_id):
    today = get_today_date()

    day = db.session.scalar(
        db.select(DailyQuestDay).filter_by(
            user_id=user_id,
            quest_date=today
        )
    )

    if day:
        return day

    # Kalau belum ada quest hari ini, backend bikin otomatis
    new_day = DailyQuestDay(
        user_id=user_id,
        quest_date=today,
        reward_xp=REWARD_XP,
        is_claimed=False
    )

    db.session.add(new_day)
    db.session.flush()

    selected_quests = random.sample(QUEST_POOL, 3)

    for quest in selected_quests:
        item = DailyQuestItem(
            daily_quest_day_id=new_day.id,
            quest_key=quest["quest_key"],
            title=quest["title"],
            description=quest["description"],
            target=quest["target"],
            progress=0,
            is_completed=False
        )
        db.session.add(item)

    db.session.commit()
    return new_day


# =====================================================
# 1. AMBIL DAILY QUEST HARI INI
# =====================================================
@daily_quest_bp.route('/daily-quests/today', methods=['GET'])
@jwt_required()
def get_today_daily_quest():
    user_id = get_current_user_id()

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User tidak ditemukan"}), 404

    day = get_or_create_today_quest(user_id)

    return jsonify({
        "message": "Daily Quest hari ini berhasil diambil",
        "daily_quest": serialize_daily_quest(day)
    }), 200


# =====================================================
# 2. UPDATE PROGRESS DAILY QUEST
# =====================================================
@daily_quest_bp.route('/daily-quests/progress', methods=['POST'])
@jwt_required()
def update_daily_quest_progress():
    user_id = get_current_user_id()
    data = request.get_json() or {}

    quest_key = data.get('quest_key') or data.get('id')
    amount = data.get('amount', 1)

    if not quest_key:
        return jsonify({"error": "quest_key wajib dikirim"}), 400

    try:
        amount = int(amount)
    except Exception:
        return jsonify({"error": "amount harus berupa angka"}), 400

    if amount <= 0:
        return jsonify({"error": "amount harus lebih dari 0"}), 400

    day = get_or_create_today_quest(user_id)

    item = db.session.scalar(
        db.select(DailyQuestItem).filter_by(
            daily_quest_day_id=day.id,
            quest_key=quest_key
        )
    )

    # Kalau quest ini tidak muncul hari ini, jangan error.
    # Misalnya hari ini tidak ada quest open_lab, tapi Flutter tetap kirim trigger.
    if not item:
        return jsonify({
            "message": f"Quest {quest_key} tidak aktif hari ini",
            "daily_quest": serialize_daily_quest(day)
        }), 200

    if item.is_completed:
        return jsonify({
            "message": "Quest ini sudah selesai",
            "daily_quest": serialize_daily_quest(day)
        }), 200

    item.progress = min(item.target, item.progress + amount)

    if item.progress >= item.target:
        item.progress = item.target
        item.is_completed = True

    db.session.commit()

    return jsonify({
        "message": "Progress Daily Quest diperbarui",
        "daily_quest": serialize_daily_quest(day)
    }), 200


# =====================================================
# 3. CLAIM REWARD DAILY QUEST
# =====================================================
@daily_quest_bp.route('/daily-quests/claim', methods=['POST'])
@jwt_required()
def claim_daily_quest_reward():
    user_id = get_current_user_id()

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User tidak ditemukan"}), 404

    day = get_or_create_today_quest(user_id)

    if day.is_claimed:
        return jsonify({
            "error": "Reward hari ini sudah diklaim",
            "daily_quest": serialize_daily_quest(day)
        }), 409

    all_completed = all(item.is_completed for item in day.items)

    if not all_completed:
        return jsonify({
            "error": "Selesaikan semua Daily Quest dulu",
            "daily_quest": serialize_daily_quest(day)
        }), 400

    old_xp = int(user.total_xp or 0)
    old_level = (user.total_xp // 200) + 1

    user.total_xp += day.reward_xp
    user.daily_status = 'active'
    day.is_claimed = True

    new_level = (user.total_xp // 200) + 1
    level_up = new_level > old_level

    if level_up:
        notif = Notification(
            user_id=user_id,
            title="Hore! Level Naik! 🚀",
            message=f"Keren banget! Sekarang kamu naik ke Level {new_level}!"
        )
        db.session.add(notif)

    milestone_baru = sync_user_milestones(
        user,
        previous_xp=old_xp,
        notify_new=True,
    )

    db.session.commit()

    return jsonify({
        "message": f"Reward Daily Quest berhasil diklaim +{day.reward_xp} XP",
        "reward_xp": day.reward_xp,
        "current_xp": user.total_xp,
        "level": new_level,
        "level_up": level_up,
        "new_milestones_unlocked": [r.reward_key for r in milestone_baru],
        "daily_quest": serialize_daily_quest(day)
    }), 200