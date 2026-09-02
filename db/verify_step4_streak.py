"""
Verifikasi ScienceCraft Step 4.

Jalankan:
    python verify_step4_streak.py
"""

from sqlalchemy import inspect


def resolve_app():
    import app as app_module

    flask_app = getattr(
        app_module,
        "app",
        None,
    )

    if flask_app is not None:
        return flask_app

    create_app = getattr(
        app_module,
        "create_app",
        None,
    )

    if callable(create_app):
        return create_app()

    raise RuntimeError(
        "Tidak menemukan app atau create_app() di app.py"
    )


flask_app = resolve_app()

with flask_app.app_context():
    from extensions import db
    from models import UserDailyActivity
    from services.streak_service import (
        calculate_streak_count,
        weekly_activity_payload,
    )

    inspector = inspect(db.engine)
    tables = inspector.get_table_names()

    assert (
        "user_daily_activities" in tables
    ), (
        "Tabel user_daily_activities belum ada. "
        "Jalankan migrate_step4_streak.py."
    )

    columns = {
        item["name"]
        for item in inspector.get_columns(
            "user_daily_activities"
        )
    }

    required = {
        "id",
        "user_id",
        "activity_date",
        "status",
        "first_login_at",
        "first_active_at",
        "last_activity_at",
    }

    missing = required - columns

    assert not missing, (
        f"Kolom belum lengkap: {sorted(missing)}"
    )

    print(
        "OK — struktur streak Step 4 terpasang."
    )
    print(
        "Warna: none=abu-abu, login=kuning, active=hijau."
    )
