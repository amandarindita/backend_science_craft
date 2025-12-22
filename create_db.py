# Impor app dan db dari app.py
from app import app, db

# --- PENTING ---
# Kita tidak perlu mengimpor model (User, UserProgress) di sini.
# app.py sudah mengimpornya. Saat kita 'from app import db',
# db sudah "kenal" dengan semua model tersebut.

def create_database():
    print("Mencoba membuat/memperbarui tabel database...")
    try:
        # 'with app.app_context()' sangat penting
        # agar db.create_all() tahu database mana yang harus diurus
        with app.app_context():
            # db.create_all() itu "pintar".
            # Dia hanya akan membuat tabel yang BELUM ADA.
            # Jadi, dia akan membuat 'user_progress' tanpa menghapus 'user'.
            db.create_all()
        print("Database dan tabel berhasil dibuat/diperbarui.")
    except Exception as e:
        print(f"Terjadi error saat membuat database: {e}")

if __name__ == '__main__':
    create_database()
