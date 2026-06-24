from extensions import db
from datetime import datetime

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=True)
    
    # --- ROLE SYSTEM ---
    role = db.Column(db.String(20), default='user') # 'user' atau 'admin'
    
    avatar = db.Column(db.String(100), default='assets/aira.png')
    total_xp = db.Column(db.Integer, default=0)
    streak_count = db.Column(db.Integer, default=0)
    last_login_date = db.Column(db.Date, nullable=True)
    daily_status = db.Column(db.String(20), default='login')
    funfact_read_count = db.Column(db.Integer, default=0)
# --- MATERIAL TABLE ---
class Material(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50)) # 'Kimia' atau 'Fisika' atau 'Biologi'
    unity_scene_id = db.Column(db.String(100)) # ID Scene Unity 2D
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    instructions = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.String(255), nullable=True)

class UserProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey('material.id'), nullable=False)
    progress = db.Column(db.Float, default=0.0)
    quiz_score = db.Column(db.Integer, default=0)
    lab_completed = db.Column(db.Boolean, default=False)
    quiz_completed = db.Column(db.Boolean, default=False)

# --- QUIZ SYSTEM ---
# --- QUIZ SYSTEM ---
class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey('material.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)

    # Tipe soal: konsep / pemahaman / studi_kasus
    question_type = db.Column(db.String(30), nullable=False, default='pemahaman')
    
    # Pilihan Ganda
    option_a = db.Column(db.String(255), nullable=False)
    option_b = db.Column(db.String(255), nullable=False)
    option_c = db.Column(db.String(255), nullable=False)
    option_d = db.Column(db.String(255), nullable=False)
    
    correct_answer = db.Column(db.String(1), nullable=False)
    
# --- FUN FACT SYSTEM ---
class FunFact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fact_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class UserFunFactRead(db.Model):
    __tablename__ = 'user_funfact_reads'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    funfact_id = db.Column(db.Integer, db.ForeignKey('fun_fact.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'funfact_id', name='unique_user_funfact_read'),
    )
# --- GAMIFICATION BADGES SYSTEM ---
class Badge(db.Model):
    __tablename__ = 'badges'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    icon_name = db.Column(db.String(100), nullable=False) # Nama file asset di Flutter
    
    users = db.relationship('UserBadge', back_populates='badge', cascade="all, delete-orphan")

class UserBadge(db.Model):
    __tablename__ = 'user_badges'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) # Sudah difix ke 'user.id'
    badge_id = db.Column(db.Integer, db.ForeignKey('badges.id'), nullable=False)
    unlocked_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relasi balik
    user = db.relationship('User', backref=db.backref('user_badges', lazy=True))
    badge = db.relationship('Badge', back_populates='users')

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)      # Contoh: "Badge Baru Terbuka! 🎉"
    message = db.Column(db.Text, nullable=False)          # Contoh: "Selamat! Kamu mendapatkan badge First Spark."
    is_read = db.Column(db.Boolean, default=False)         # Biar Flutter tahu ini udah dibaca/belum
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# --- DAILY QUEST SYSTEM ---
class DailyQuestDay(db.Model):
    __tablename__ = 'daily_quest_days'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    quest_date = db.Column(db.Date, nullable=False)

    reward_xp = db.Column(db.Integer, default=50)
    is_claimed = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    items = db.relationship(
        'DailyQuestItem',
        backref='quest_day',
        cascade='all, delete-orphan',
        lazy=True
    )

    __table_args__ = (
        db.UniqueConstraint(
            'user_id',
            'quest_date',
            name='uq_user_daily_quest_date'
        ),
    )


class DailyQuestItem(db.Model):
    __tablename__ = 'daily_quest_items'

    id = db.Column(db.Integer, primary_key=True)
    daily_quest_day_id = db.Column(
        db.Integer,
        db.ForeignKey('daily_quest_days.id'),
        nullable=False
    )

    quest_key = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)

    target = db.Column(db.Integer, default=1)
    progress = db.Column(db.Integer, default=0)
    is_completed = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    __table_args__ = (
        db.UniqueConstraint(
            'daily_quest_day_id',
            'quest_key',
            name='uq_daily_quest_item_key'
        ),
    )