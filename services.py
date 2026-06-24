from datetime import datetime, timedelta
from extensions import db
from models import Badge, UserBadge, Notification # 🌟 WAJIB IMPORT INI

# Fungsi penghitung streak buatanmu
def update_streak(user):
    today = datetime.utcnow().date()
    
    # Jika User belum login hari ini
    if user.last_login_date != today:
        
        # Cek apakah login terakhir adalah KEMARIN
        if user.last_login_date is not None and user.last_login_date == today - timedelta(days=1):
            user.streak_count += 1 # Streak Nambah!
            
            # 🌟 LOGIKA BADGE STREAK 7 HARI (LAB REGULAR) 🌟
            if user.streak_count >= 7:
                badge = db.session.scalar(db.select(Badge).filter_by(name="Lab Regular"))
                if badge:
                    existing = db.session.scalar(db.select(UserBadge).filter_by(user_id=user.id, badge_id=badge.id))
                    if not existing:
                        db.session.add(UserBadge(user_id=user.id, badge_id=badge.id, unlocked_at=datetime.utcnow()))
                        db.session.add(Notification(
                            user_id=user.id,
                            title="Badge Baru Terbuka! 🎉",
                            message=f"Luar biasa! Kamu belajar 7 hari berturut-turut dan dapat badge '{badge.name}'!"
                        ))
            # 🌟 ==========================================
                        
        else:
            user.streak_count = 1 # Streak Reset/Awal
        
        # Simpan tanggal hari ini
        user.last_login_date = today
        db.session.commit()