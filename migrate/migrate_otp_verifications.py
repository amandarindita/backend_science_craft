import os
import sys

# Memastikan root folder terdaftar di Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from sqlalchemy import text

with app.app_context():
    print("Memulai proses rekonstruksi tabel 'otp_verifications'...")
    
    with db.engine.connect() as conn:
        # 1. Hapus tabel lama kalau memang terlanjur ada
        conn.execute(text("DROP TABLE IF EXISTS otp_verifications;"))
        conn.commit()
        print("Tabel lama (jika ada) berhasil dihapus.")
        
        # 2. Buat tabel baru dari nol dengan skema yang benar dan lengkap
        conn.execute(text("""
            CREATE TABLE otp_verifications (
                id INTEGER NOT NULL, 
                email VARCHAR(120) NOT NULL, 
                otp_code VARCHAR(6) NOT NULL, 
                username VARCHAR(80) NOT NULL, 
                password_hash VARCHAR(128) NOT NULL, 
                created_at DATETIME, 
                PRIMARY KEY (id)
            );
        """))
        conn.commit()
        
    print("Tabel 'otp_verifications' yang baru berhasil dibuat dengan kolom username!")