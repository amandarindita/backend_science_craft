from datetime import datetime

from extensions import db
from models import MilestoneReward, Notification, UserMilestoneReward


# Katalog bawaan aplikasi. Bukan CRUD admin.
MILESTONE_CATALOG = [
    {
        "reward_key": "discovery_robert_hooke",
        "required_xp": 50,
        "reward_type": "discovery_card",
        "category": "scientist",
        "title": "Robert Hooke",
        "subtitle": "Tokoh Sains",
        "description": (
            "Kenali Robert Hooke dan bagaimana pengamatannya membantu "
            "perkembangan sains, dari elastisitas hingga pengamatan mikroskopis."
        ),
        "visual_asset": None,
        "sort_order": 1,
    },
    {
        "reward_key": "frame_atom",
        "required_xp": 100,
        "reward_type": "avatar_frame",
        "category": None,
        "title": "Bingkai Atom",
        "subtitle": "Bingkai Avatar",
        "description": (
            "Bingkai avatar bertema atom yang dapat digunakan setelah milestone terbuka."
        ),
        "visual_asset": None,
        "sort_order": 2,
    },
    {
        "reward_key": "discovery_bent_straw",
        "required_xp": 150,
        "reward_type": "discovery_card",
        "category": "phenomenon",
        "title": "Sedotan Tampak Bengkok",
        "subtitle": "Fenomena Sains",
        "description": (
            "Mengapa sedotan terlihat bengkok saat berada di dalam air? "
            "Kartu ini membahas fenomena pembiasan melalui contoh sehari-hari."
        ),
        "visual_asset": None,
        "sort_order": 3,
    },
    {
        "reward_key": "discovery_vehicle_suspension",
        "required_xp": 250,
        "reward_type": "discovery_card",
        "category": "application",
        "title": "Suspensi Kendaraan",
        "subtitle": "Penerapan Sains",
        "description": (
            "Lihat bagaimana konsep gaya, pegas, dan redaman diterapkan pada "
            "sistem suspensi kendaraan."
        ),
        "visual_asset": None,
        "sort_order": 4,
    },
    {
        "reward_key": "discovery_fiber_optic",
        "required_xp": 350,
        "reward_type": "discovery_card",
        "category": "technology",
        "title": "Serat Optik",
        "subtitle": "Teknologi Sains",
        "description": (
            "Pelajari bagaimana cahaya dapat dipandu di dalam serat untuk "
            "mengirimkan informasi dalam teknologi komunikasi."
        ),
        "visual_asset": None,
        "sort_order": 5,
    },
    {
        "reward_key": "frame_molecule",
        "required_xp": 500,
        "reward_type": "avatar_frame",
        "category": None,
        "title": "Bingkai Molekul",
        "subtitle": "Bingkai Avatar",
        "description": (
            "Bingkai avatar bertema molekul yang dapat digunakan setelah milestone terbuka."
        ),
        "visual_asset": None,
        "sort_order": 6,
    },
    {
        "reward_key": "discovery_michael_faraday",
        "required_xp": 650,
        "reward_type": "discovery_card",
        "category": "scientist",
        "title": "Michael Faraday",
        "subtitle": "Tokoh Sains",
        "description": (
            "Kenali Michael Faraday dan kontribusinya pada elektromagnetisme "
            "serta perkembangan teknologi listrik."
        ),
        "visual_asset": None,
        "sort_order": 7,
    },
    {
        "reward_key": "discovery_rainbow",
        "required_xp": 800,
        "reward_type": "discovery_card",
        "category": "phenomenon",
        "title": "Pelangi",
        "subtitle": "Fenomena Sains",
        "description": (
            "Pelangi terbentuk saat cahaya mengalami pembiasan, pemantulan, "
            "dan dispersi di dalam tetes air."
        ),
        "visual_asset": None,
        "sort_order": 8,
    },
]


def ensure_milestone_catalog():
    """Pastikan katalog bawaan tersedia dalam transaction aktif."""
    changed = False

    for item in MILESTONE_CATALOG:
        reward = db.session.scalar(
            db.select(MilestoneReward).filter_by(reward_key=item["reward_key"])
        )

        if reward is None:
            db.session.add(MilestoneReward(**item))
            changed = True
            continue

        # Sinkronkan konfigurasi bawaan tanpa menjadikan reward sebagai CRUD admin.
        for field, value in item.items():
            if getattr(reward, field) != value:
                setattr(reward, field, value)
                changed = True

    if changed:
        db.session.flush()


def _ordered_rewards():
    ensure_milestone_catalog()
    return db.session.execute(
        db.select(MilestoneReward).order_by(
            MilestoneReward.required_xp.asc(),
            MilestoneReward.sort_order.asc(),
            MilestoneReward.id.asc(),
        )
    ).scalars().all()


def sync_user_milestones(user, previous_xp=None, notify_new=False):
    """
    Backfill semua milestone yang seharusnya sudah dimiliki user.

    Jika previous_xp diberikan, hanya milestone yang benar-benar dilewati pada
    perubahan XP ini yang dimasukkan ke daftar newly_crossed dan dapat memicu
    notifikasi. Milestone historis dibackfill diam-diam.
    """
    rewards = _ordered_rewards()
    current_xp = max(int(user.total_xp or 0), 0)

    owned_rows = db.session.execute(
        db.select(UserMilestoneReward).filter_by(user_id=user.id)
    ).scalars().all()
    owned_reward_ids = {row.reward_id for row in owned_rows}

    newly_crossed = []

    for reward in rewards:
        if reward.required_xp > current_xp:
            break

        if reward.id in owned_reward_ids:
            continue

        row = UserMilestoneReward(
            user_id=user.id,
            reward_id=reward.id,
            unlocked_at=datetime.utcnow(),
            is_equipped=False,
        )
        db.session.add(row)
        owned_reward_ids.add(reward.id)

        crossed_now = (
            previous_xp is not None
            and int(previous_xp) < reward.required_xp <= current_xp
        )

        if crossed_now:
            newly_crossed.append(reward)
            if notify_new:
                db.session.add(
                    Notification(
                        user_id=user.id,
                        title="Milestone Tercapai! 🎉",
                        message=(
                            f"Kamu mencapai {reward.required_xp} XP dan membuka "
                            f"'{reward.title}'."
                        ),
                    )
                )

    return newly_crossed


def serialize_reward(reward, owned_row=None):
    return {
        "id": reward.reward_key,
        "reward_key": reward.reward_key,
        "required_xp": reward.required_xp,
        "reward_type": reward.reward_type,
        "category": reward.category,
        "title": reward.title,
        "subtitle": reward.subtitle,
        "description": reward.description,
        "visual_asset": reward.visual_asset,
        "unlocked": owned_row is not None,
        "unlocked_at": (
            owned_row.unlocked_at.isoformat() if owned_row and owned_row.unlocked_at else None
        ),
        "is_equipped": bool(owned_row.is_equipped) if owned_row else False,
    }


def serialize_milestone_state(user):
    rewards = _ordered_rewards()
    owned_rows = db.session.execute(
        db.select(UserMilestoneReward).filter_by(user_id=user.id)
    ).scalars().all()
    owned_map = {row.reward_id: row for row in owned_rows}

    current_xp = max(int(user.total_xp or 0), 0)

    next_reward = None
    previous_threshold = 0
    equipped_reward = None

    serialized = []
    for reward in rewards:
        row = owned_map.get(reward.id)
        item = serialize_reward(reward, row)
        serialized.append(item)

        if reward.required_xp <= current_xp:
            previous_threshold = reward.required_xp
        elif next_reward is None:
            next_reward = reward

        if row and row.is_equipped and reward.reward_type == "avatar_frame":
            equipped_reward = item

    if next_reward is None:
        target_xp = current_xp
        remaining_xp = 0
        progress_value = 1.0
    else:
        target_xp = next_reward.required_xp
        span = max(target_xp - previous_threshold, 1)
        gained = max(current_xp - previous_threshold, 0)
        progress_value = min(max(gained / span, 0.0), 1.0)
        remaining_xp = max(target_xp - current_xp, 0)

    next_item = None
    if next_reward is not None:
        next_item = serialize_reward(next_reward, owned_map.get(next_reward.id))

    return {
        "total_xp": current_xp,
        "unlocked_count": len(owned_rows),
        "total_count": len(rewards),
        "equipped_frame": equipped_reward,
        "next_milestone": next_item,
        "progress": {
            "start_xp": previous_threshold,
            "target_xp": target_xp,
            "current_xp": current_xp,
            "remaining_xp": remaining_xp,
            "value": progress_value,
        },
        "rewards": serialized,
    }


def equip_user_frame(user, reward_key):
    """Gunakan satu frame yang sudah dimiliki user. Empty key = lepas frame."""
    # Pastikan kepemilikan historis sinkron sebelum validasi frame.
    sync_user_milestones(user, previous_xp=None, notify_new=False)
    db.session.flush()

    owned_rows = db.session.execute(
        db.select(UserMilestoneReward).filter_by(user_id=user.id)
    ).scalars().all()

    # Selalu hanya boleh ada satu frame aktif.
    for row in owned_rows:
        row.is_equipped = False

    cleaned_key = (reward_key or "").strip()
    if not cleaned_key:
        return True, None

    reward = db.session.scalar(
        db.select(MilestoneReward).filter_by(reward_key=cleaned_key)
    )
    if reward is None:
        return False, "Reward tidak ditemukan"

    if reward.reward_type != "avatar_frame":
        return False, "Reward ini bukan bingkai avatar"

    owned_row = next((row for row in owned_rows if row.reward_id == reward.id), None)
    if owned_row is None:
        return False, "Bingkai belum terbuka"

    owned_row.is_equipped = True
    return True, None


def seed_milestone_catalog():
    """Alias opsional untuk seeding manual dari shell/app context."""
    ensure_milestone_catalog()
    db.session.commit()
