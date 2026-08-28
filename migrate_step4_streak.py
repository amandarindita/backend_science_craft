"""
ScienceCraft Step 4 migration.

Jalankan dari folder backend:
    python migrate_step4_streak.py
"""

from datetime import datetime, timedelta, timezone


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
    from models import (
        User,
        UserDailyActivity,
    )

    db.create_all()

    jakarta_today = datetime.now(
        timezone(timedelta(hours=7))
    ).date()

    users = db.session.execute(
        db.select(User)
    ).scalars().all()

    backfilled = 0

    for user in users:
        # Hanya backfill bila tanggal login lama memang tersedia.
        activity_date = user.last_login_date

        if activity_date is None:
            continue

        existing = db.session.scalar(
            db.select(
                UserDailyActivity
            ).where(
                UserDailyActivity.user_id
                == user.id,
                UserDailyActivity.activity_date
                == activity_date,
            )
        )

        if existing is not None:
            continue

        status = (
            "active"
            if str(
                user.daily_status or ""
            ).lower() == "active"
            else "login"
        )

        now_utc = datetime.utcnow()

        db.session.add(
            UserDailyActivity(
                user_id=user.id,
                activity_date=activity_date,
                status=status,
                first_login_at=now_utc,
                first_active_at=(
                    now_utc
                    if status == "active"
                    else None
                ),
                last_activity_at=now_utc,
            )
        )
        backfilled += 1

    db.session.commit()

    print(
        "OK — tabel user_daily_activities siap."
    )
    print(
        f"Riwayat lama yang berhasil dipindahkan: {backfilled}"
    )
    print(
        f"Tanggal Jakarta saat migrasi: {jakarta_today}"
    )
