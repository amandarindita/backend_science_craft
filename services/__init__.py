"""
Compatibility exports for the ScienceCraft services package.

routes/auth.py lama masih menggunakan:
    from services import update_streak

Step 4 memindahkan logika streak ke services/streak_service.py.
Wrapper ini menjaga auth.py lama tetap berjalan tanpa mengubah route login.
"""

from .streak_service import (
    calculate_streak_count,
    jakarta_now,
    jakarta_today,
    mark_daily_activity,
    weekly_activity_payload,
)


def update_streak(user):
    """
    Kompatibilitas untuk auth.py lama.

    Login hanya mencatat status kuning. Jika status hari ini sebelumnya
    sudah hijau, mark_daily_activity tidak akan menurunkannya kembali.
    Commit tetap dilakukan oleh route auth yang memanggil fungsi ini.
    """
    if user is None or getattr(user, "id", None) is None:
        return None

    return mark_daily_activity(
        int(user.id),
        "login",
    )


__all__ = [
    "update_streak",
    "mark_daily_activity",
    "calculate_streak_count",
    "weekly_activity_payload",
    "jakarta_now",
    "jakarta_today",
]
