from extensions import db
from datetime import datetime

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=True)
    
    # --- KOLOM BARU UNTUK ROLE ADMIN ---
    role = db.Column(db.String(20), default='user') # 'user' atau 'admin'
    # -----------------------------------
    
    avatar = db.Column(db.String(100), default='assets/aira.png')
    total_xp = db.Column(db.Integer, default=0)
    streak_count = db.Column(db.Integer, default=0)
    last_login_date = db.Column(db.Date, nullable=True)

# --- TABEL BARU: MATERIAL (BIAR BISA NAMBAH MATERI) ---
class Material(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50)) # Misalnya: 'Kimia' atau 'Fisika'
    unity_scene_id = db.Column(db.String(100)) # Biar Flutter tau harus buka Scene Unity yg mana
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class UserProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey('material.id'), nullable=False)
    progress = db.Column(db.Float, default=0.0)

class UserBadge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    badge_code = db.Column(db.String(50), nullable=False)
    earned_at = db.Column(db.DateTime, default=datetime.utcnow)

# --- TABEL BARU: SOAL KUIS (Terkait dengan Materi) ---
class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey('material.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    
    # Pilihan ganda
    option_a = db.Column(db.String(255), nullable=False)
    option_b = db.Column(db.String(255), nullable=False)
    option_c = db.Column(db.String(255), nullable=False)
    option_d = db.Column(db.String(255), nullable=False)
    
    # Jawaban benar (misal isinya: 'A', 'B', 'C', atau 'D')
    correct_answer = db.Column(db.String(1), nullable=False)

# --- TABEL BARU: FUN FACT ---
class FunFact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fact_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)