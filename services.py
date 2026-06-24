from datetime import datetime, timedelta
from extensions import db

# Fungsi penghitung streak buatanmu
def update_streak(user):
    today = datetime.utcnow().date()
    
    # Jika User belum login hari ini
    if user.last_login_date != today:
        
        # Cek apakah login terakhir adalah KEMARIN
        if user.last_login_date is not None and user.last_login_date == today - timedelta(days=1):
            user.streak_count += 1 # Streak Nambah!
        else:
            user.streak_count = 1 # Streak Reset/Awal
        
        # Simpan tanggal hari ini
        user.last_login_date = today
        db.session.commit()