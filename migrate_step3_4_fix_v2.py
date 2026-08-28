"""ScienceCraft Step 3-4 FIX v2 migration.

Jalankan SEKALI dari root backend setelah file FIX v2 di-replace:
    python migrate_step3_4_fix_v2.py

Script ini:
1. membuat tabel yang belum ada (termasuk user_daily_activities dan milestone),
2. backfill satu riwayat streak lama bila tersedia,
3. seed katalog milestone bawaan,
4. backfill kepemilikan milestone akun lama berdasarkan total XP,
5. tidak menghapus data lama.
"""

from datetime import datetime


def resolve_app():
    import app as app_module

    flask_app = getattr(app_module, "app", None)
    if flask_app is not None:
        return flask_app

    create_app = getattr(app_module, "create_app", None)
    if callable(create_app):
        return create_app()

    raise RuntimeError("Tidak menemukan app atau create_app() di app.py")


flask_app = resolve_app()

with flask_app.app_context():
    from sqlalchemy import inspect

    from extensions import db
    from milestone_service import ensure_milestone_catalog, sync_user_milestones
    from models import User, UserDailyActivity, UserMilestoneReward

    # Aman untuk tabel baru. Tidak menghapus atau mengganti tabel lama.
    db.create_all()

    users = db.session.execute(db.select(User)).scalars().all()

    streak_backfilled = 0
    milestone_backfilled = 0

    # Backfill status streak lama dari field User yang memang sudah tersedia.
    for user in users:
        activity_date = user.last_login_date
        if activity_date is None:
            continue

        existing = db.session.scalar(
            db.select(UserDailyActivity).where(
                UserDailyActivity.user_id == user.id,
                UserDailyActivity.activity_date == activity_date,
            )
        )
        if existing is not None:
            continue

        status = (
            "active"
            if str(user.daily_status or "").lower() == "active"
            else "login"
        )
        now_utc = datetime.utcnow()

        db.session.add(
            UserDailyActivity(
                user_id=user.id,
                activity_date=activity_date,
                status=status,
                first_login_at=now_utc,
                first_active_at=now_utc if status == "active" else None,
                last_activity_at=now_utc,
            )
        )
        streak_backfilled += 1

    # Seed master katalog milestone.
    ensure_milestone_catalog()
    db.session.flush()

    # Akun lama yang sudah punya XP langsung memperoleh reward yang seharusnya,
    # tanpa notifikasi historis/popup palsu.
    for user in users:
        before_count = db.session.scalar(
            db.select(db.func.count(UserMilestoneReward.id)).where(
                UserMilestoneReward.user_id == user.id
            )
        ) or 0

        sync_user_milestones(
            user,
            previous_xp=None,
            notify_new=False,
        )
        db.session.flush()

        after_count = db.session.scalar(
            db.select(db.func.count(UserMilestoneReward.id)).where(
                UserMilestoneReward.user_id == user.id
            )
        ) or 0

        milestone_backfilled += max(after_count - before_count, 0)

    db.session.commit()

    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())
    required_tables = {
        "user_daily_activities",
        "milestone_rewards",
        "user_milestone_rewards",
    }
    missing = sorted(required_tables - tables)

    if missing:
        raise RuntimeError(f"Tabel belum terbentuk: {missing}")

    print("OK — ScienceCraft Step 3-4 FIX v2 berhasil dipasang.")
    print(f"Streak lama yang dibackfill: {streak_backfilled}")
    print(f"Milestone user yang dibackfill: {milestone_backfilled}")
    print("Data lama tidak dihapus.")
