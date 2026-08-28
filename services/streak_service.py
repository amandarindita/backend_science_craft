from datetime import datetime, timedelta, timezone

from extensions import db
from models import User, UserDailyActivity


JAKARTA_TZ = timezone(timedelta(hours=7))

VALID_STATUSES = {
    "login",
    "active",
}

DAY_LABELS = [
    "S",
    "S",
    "R",
    "K",
    "J",
    "S",
    "M",
]

DAY_NAMES = [
    "Senin",
    "Selasa",
    "Rabu",
    "Kamis",
    "Jumat",
    "Sabtu",
    "Minggu",
]


def jakarta_now():
    return datetime.now(JAKARTA_TZ)


def jakarta_today():
    return jakarta_now().date()


def _utcnow():
    return datetime.utcnow()


def _normalized_status(status):
    value = str(status or "login").strip().lower()

    if value not in VALID_STATUSES:
        return "login"

    return value


def mark_daily_activity(
    user_id,
    status="login",
):
    """
    Mencatat aktivitas hari ini tanpa commit.

    Aturan peningkatan status:
    none   -> login
    login  -> active
    active -> tetap active

    Pemanggilan status login tidak pernah menurunkan status active.
    """
    user_id = int(user_id)
    status = _normalized_status(status)
    today = jakarta_today()
    now_utc = _utcnow()

    activity = db.session.scalar(
        db.select(UserDailyActivity).where(
            UserDailyActivity.user_id
            == user_id,
            UserDailyActivity.activity_date
            == today,
        )
    )

    if activity is None:
        activity = UserDailyActivity(
            user_id=user_id,
            activity_date=today,
            status=status,
            first_login_at=now_utc,
            first_active_at=(
                now_utc
                if status == "active"
                else None
            ),
            last_activity_at=now_utc,
        )
        db.session.add(activity)
    else:
        activity.last_activity_at = now_utc

        if activity.first_login_at is None:
            activity.first_login_at = now_utc

        if (
            status == "active"
            and activity.status != "active"
        ):
            activity.status = "active"

            if activity.first_active_at is None:
                activity.first_active_at = now_utc

    user = db.session.get(User, user_id)

    if user is not None:
        user.last_login_date = today
        user.daily_status = activity.status

    db.session.flush()

    streak_count = calculate_streak_count(
        user_id,
        today=today,
    )

    if user is not None:
        user.streak_count = streak_count

    return activity


def calculate_streak_count(
    user_id,
    today=None,
):
    """
    Kuning (login) dan hijau (active) sama-sama mempertahankan streak.
    Hari tanpa catatan memutus streak.
    """
    user_id = int(user_id)
    today = today or jakarta_today()

    recorded_dates = set(
        db.session.execute(
            db.select(
                UserDailyActivity.activity_date
            ).where(
                UserDailyActivity.user_id
                == user_id,
                UserDailyActivity.activity_date
                <= today,
            )
        ).scalars().all()
    )

    streak = 0
    cursor = today

    while cursor in recorded_dates:
        streak += 1
        cursor -= timedelta(days=1)

    return streak


def weekly_activity_payload(
    user_id,
):
    """
    Mengembalikan status Senin-Minggu untuk Profile Flutter.
    """
    user_id = int(user_id)
    today = jakarta_today()
    monday = today - timedelta(
        days=today.weekday()
    )
    sunday = monday + timedelta(days=6)

    activities = db.session.execute(
        db.select(UserDailyActivity).where(
            UserDailyActivity.user_id
            == user_id,
            UserDailyActivity.activity_date
            >= monday,
            UserDailyActivity.activity_date
            <= sunday,
        )
    ).scalars().all()

    activity_by_date = {
        item.activity_date: item
        for item in activities
    }

    days = []

    for index in range(7):
        date_value = monday + timedelta(
            days=index
        )
        activity = activity_by_date.get(
            date_value
        )
        status = (
            activity.status
            if activity is not None
            else "none"
        )

        days.append({
            "date": date_value.isoformat(),
            "label": DAY_LABELS[index],
            "day_name": DAY_NAMES[index],
            "status": status,
            "is_today": date_value == today,
            "is_future": date_value > today,
        })

    today_activity = activity_by_date.get(
        today
    )
    today_status = (
        today_activity.status
        if today_activity is not None
        else "none"
    )

    return {
        "streak_count": calculate_streak_count(
            user_id,
            today=today,
        ),
        "today_status": today_status,
        "week_start": monday.isoformat(),
        "week_end": sunday.isoformat(),
        "days": days,
    }
