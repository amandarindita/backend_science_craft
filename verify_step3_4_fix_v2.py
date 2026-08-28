"""Verifikasi ScienceCraft Step 3-4 FIX v2.

Jalankan setelah migration:
    python verify_step3_4_fix_v2.py
"""


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
    from models import MilestoneReward, UserDailyActivity, UserMilestoneReward

    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())

    required_tables = {
        "user_daily_activities",
        "milestone_rewards",
        "user_milestone_rewards",
    }
    missing_tables = sorted(required_tables - tables)
    assert not missing_tables, f"Tabel belum lengkap: {missing_tables}"

    streak_columns = {
        item["name"]
        for item in inspector.get_columns("user_daily_activities")
    }
    required_streak_columns = {
        "id",
        "user_id",
        "activity_date",
        "status",
        "first_login_at",
        "first_active_at",
        "last_activity_at",
    }
    missing_columns = sorted(required_streak_columns - streak_columns)
    assert not missing_columns, f"Kolom streak belum lengkap: {missing_columns}"

    reward_count = db.session.scalar(
        db.select(db.func.count(MilestoneReward.id))
    ) or 0
    assert reward_count >= 8, (
        f"Katalog milestone belum lengkap. Ditemukan: {reward_count}"
    )

    print("OK — import UserDailyActivity berhasil.")
    print("OK — tabel streak tersedia.")
    print("OK — tabel milestone tersedia.")
    print(f"OK — katalog milestone: {reward_count} reward.")
    print("Backend siap dijalankan dengan: python app.py")
