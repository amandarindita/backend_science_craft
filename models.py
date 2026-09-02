from datetime import datetime
from sqlalchemy import text

from extensions import db


# =========================================================
# PILIHAN CHECKPOINT DAN MODE BELAJAR
# =========================================================

CHECKPOINT_TYPES = {
    "multiple_choice": "Pilihan",
    "true_false": "Benar/Salah",
    "matching": "Pasangkan",
    "ordering": "Urutkan",
    "image_hotspot": "Tunjuk Bagian",
    "data_interpretation": "Analisis Data",
}

LEARNING_MODES = {
    "read": "Baca",
    "audio": "Dengarkan",
    "visual": "Visual",
}


# =========================================================
# USER
# =========================================================

class User(db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(
        db.String(80),
        unique=True,
        nullable=False,
    )
    email = db.Column(
        db.String(120),
        unique=True,
        nullable=False,
    )
    password_hash = db.Column(
        db.String(128),
        nullable=True,
    )

    role = db.Column(
        db.String(20),
        default="user",
    )

    avatar = db.Column(
        db.String(100),
        default="assets/aira.png",
    )

    total_xp = db.Column(
        db.Integer,
        default=0,
    )

    streak_count = db.Column(
        db.Integer,
        default=0,
    )

    last_login_date = db.Column(
        db.Date,
        nullable=True,
    )

    daily_status = db.Column(
        db.Text,
        nullable=False,
        default="login",
    )

    funfact_read_count = db.Column(
        db.Integer,
        default=0,
    )
    gacha_tickets = db.Column(
        db.Integer, default=0,
        server_default="0",
        nullable=False
    )
    shards = db.Column(
        db.Integer, default=0,
        server_default="0",
        nullable=False
    )


# =========================================================
# RIWAYAT AKTIVITAS HARIAN / STREAK
#
# status:
# - login  = siswa hanya masuk aplikasi (kuning)
# - active = siswa melakukan aktivitas belajar (hijau)
#
# Tidak ada baris pada tanggal tertentu berarti tidak login
# pada hari tersebut (abu-abu).
# =========================================================

class UserDailyActivity(db.Model):
    __tablename__ = "user_daily_activities"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
        index=True,
    )

    activity_date = db.Column(
        db.Date,
        nullable=False,
        index=True,
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="login",
        server_default=text("'login'"),
    )

    first_login_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    first_active_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    last_activity_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "activity_date",
            name="uq_user_daily_activity_date",
        ),
    )


# =========================================================
# MATERIAL / MODUL
#
# Tabel Material lama tetap digunakan.
# Setelah revisi, satu Material dianggap sebagai satu Modul.
# =========================================================

class Material(db.Model):
    __tablename__ = "material"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    title = db.Column(
        db.String(200),
        nullable=False,
    )

    # Dipertahankan agar materi lama tidak langsung rusak.
    content = db.Column(
        db.Text,
        nullable=False,
        default="",
    )

    # Kimia, Fisika, atau Biologi
    category = db.Column(
        db.String(50),
        nullable=True,
    )

    # 1 = Dasar
    # 2 = Penerapan
    # 3 = Analisis
    level = db.Column(
        db.Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )

    # Urutan modul di halaman Flutter
    module_order = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    short_description = db.Column(
        db.String(500),
        nullable=True,
    )

    # Modul wajib untuk membuka level berikutnya
    is_required = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
    )

    # Guru bisa menyimpan modul sebagai draft
    is_published = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
    )

    unity_scene_id = db.Column(
        db.String(100),
        nullable=True,
    )

    instructions = db.Column(
        db.Text,
        nullable=True,
    )

    image_url = db.Column(
        db.String(255),
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
    )

    submaterials = db.relationship(
        "SubMaterial",
        back_populates="material",
        cascade="all, delete-orphan",
        order_by="SubMaterial.order_index",
    )

    questions = db.relationship(
        "Question",
        back_populates="material",
        cascade="all, delete-orphan",
    )


# =========================================================
# SUBMATERI
#
# Contoh:
# Modul: Sifat dan Konsep Asam Basa
#
# Submateri:
# - Asam Basa Arrhenius
# - Asam Basa Brønsted–Lowry
# - Asam Basa Lewis
# =========================================================

class SubMaterial(db.Model):
    __tablename__ = "sub_materials"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    material_id = db.Column(
        db.Integer,
        db.ForeignKey("material.id"),
        nullable=False,
        index=True,
    )

    title = db.Column(
        db.String(200),
        nullable=False,
    )

    order_index = db.Column(
        db.Integer,
        nullable=False,
        default=1,
    )

    # Isi yang ditampilkan pada mode Baca
    read_content = db.Column(
        db.Text,
        nullable=False,
        default="",
    )

    # Teks khusus yang mudah dibaca TTS
    tts_text = db.Column(
        db.Text,
        nullable=True,
    )

    # Contoh:
    # /uploads/audio/arrhenius.mp3
    audio_url = db.Column(
        db.String(500),
        nullable=True,
    )

    # Contoh:
    # infographic, comparison, flow, chart,
    # formula, hotspot, sequence
    visual_type = db.Column(
        db.String(50),
        nullable=True,
    )

    # Isi visual disimpan sebagai JSON string
    visual_data = db.Column(
        db.Text,
        nullable=True,
    )

    summary = db.Column(
        db.Text,
        nullable=True,
    )

    image_url = db.Column(
        db.String(500),
        nullable=True,
    )

    is_required = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )

    is_published = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    material = db.relationship(
        "Material",
        back_populates="submaterials",
    )

    checkpoints = db.relationship(
        "Checkpoint",
        back_populates="submaterial",
        cascade="all, delete-orphan",
        order_by="Checkpoint.order_index",
    )


# =========================================================
# CHECKPOINT
#
# checkpoint_type:
# - multiple_choice
# - true_false
# - matching
# - ordering
# - image_hotspot
# - data_interpretation
# =========================================================

class Checkpoint(db.Model):
    __tablename__ = "checkpoints"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    submaterial_id = db.Column(
        db.Integer,
        db.ForeignKey("sub_materials.id"),
        nullable=False,
        index=True,
    )

    checkpoint_type = db.Column(
        db.String(30),
        nullable=False,
    )

    title = db.Column(
        db.String(150),
        nullable=True,
    )

    instruction = db.Column(
        db.Text,
        nullable=True,
    )

    question_text = db.Column(
        db.Text,
        nullable=False,
    )

    # Data pilihan, pasangan, urutan, gambar, atau tabel.
    # Disimpan sebagai JSON string.
    content_json = db.Column(
        db.Text,
        nullable=False,
        default="{}",
    )

    # Jawaban yang benar.
    # Disimpan sebagai JSON string.
    answer_json = db.Column(
        db.Text,
        nullable=False,
        default="{}",
    )

    # Digunakan terutama untuk checkpoint gambar
    image_url = db.Column(
        db.String(500),
        nullable=True,
    )

    correct_feedback = db.Column(
        db.Text,
        nullable=True,
    )

    wrong_feedback = db.Column(
        db.Text,
        nullable=True,
    )

    order_index = db.Column(
        db.Integer,
        nullable=False,
        default=1,
    )

    is_required = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    submaterial = db.relationship(
        "SubMaterial",
        back_populates="checkpoints",
    )


# =========================================================
# PROGRESS MODUL
# =========================================================

class UserProgress(db.Model):
    __tablename__ = "user_progress"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
    )

    material_id = db.Column(
        db.Integer,
        db.ForeignKey("material.id"),
        nullable=False,
    )

    # Nantinya dihitung berdasarkan jumlah submateri selesai
    progress = db.Column(
        db.Float,
        default=0.0,
    )

    # Menyimpan nilai kuis terbaik
    quiz_score = db.Column(
        db.Integer,
        default=0,
    )

    lab_completed = db.Column(
        db.Boolean,
        default=False,
    )

    # Setelah revisi:
    # True berarti kuis sudah lulus minimal 75
    quiz_completed = db.Column(
        db.Boolean,
        default=False,
    )


# =========================================================
# PROGRESS SUBMATERI
#
# Submateri selesai jika:
# 1. Siswa menyelesaikan salah satu mode belajar.
# 2. Semua checkpoint wajib selesai.
# =========================================================

class UserSubMaterialProgress(db.Model):
    __tablename__ = "user_submaterial_progress"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
        index=True,
    )

    submaterial_id = db.Column(
        db.Integer,
        db.ForeignKey("sub_materials.id"),
        nullable=False,
        index=True,
    )

    # read, audio, atau visual
    selected_mode = db.Column(
        db.String(20),
        nullable=True,
    )

    mode_completed = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )

    checkpoint_completed = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )

    is_completed = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )

    first_opened_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    last_accessed_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    completed_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "submaterial_id",
            name="uq_user_submaterial_progress",
        ),
    )


# =========================================================
# PROGRESS CHECKPOINT
# =========================================================

class UserCheckpointProgress(db.Model):
    __tablename__ = "user_checkpoint_progress"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
        index=True,
    )

    checkpoint_id = db.Column(
        db.Integer,
        db.ForeignKey("checkpoints.id"),
        nullable=False,
        index=True,
    )

    attempts = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    is_completed = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )

    # Jawaban terakhir siswa dalam bentuk JSON
    last_answer_json = db.Column(
        db.Text,
        nullable=True,
    )

    completed_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "checkpoint_id",
            name="uq_user_checkpoint_progress",
        ),
    )


# =========================================================
# KUIS
# =========================================================

class Question(db.Model):
    __tablename__ = "question"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    material_id = db.Column(
        db.Integer,
        db.ForeignKey("material.id"),
        nullable=False,
    )

    question_text = db.Column(
        db.Text,
        nullable=False,
    )

    # konsep, pemahaman, studi_kasus
    question_type = db.Column(
        db.String(30),
        nullable=False,
        default="pemahaman",
    )

    option_a = db.Column(
        db.String(255),
        nullable=False,
    )

    option_b = db.Column(
        db.String(255),
        nullable=False,
    )

    option_c = db.Column(
        db.String(255),
        nullable=False,
    )

    option_d = db.Column(
        db.String(255),
        nullable=False,
    )

    correct_answer = db.Column(
        db.String(1),
        nullable=False,
    )

    # Pembahasan setelah kuis selesai
    explanation = db.Column(
        db.Text,
        nullable=True,
    )

    material = db.relationship(
        "Material",
        back_populates="questions",
    )


# =========================================================
# FUN FACT
# =========================================================

class FunFact(db.Model):
    __tablename__ = "fun_fact"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    fact_text = db.Column(
        db.Text,
        nullable=False,
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
    )


class UserFunFactRead(db.Model):
    __tablename__ = "user_funfact_reads"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
    )

    funfact_id = db.Column(
        db.Integer,
        db.ForeignKey("fun_fact.id"),
        nullable=False,
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
    )

    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "funfact_id",
            name="unique_user_funfact_read",
        ),
    )

# =========================================================
# CARD
# =========================================================

class Card(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # Nama ilmuwan
    rarity = db.Column(db.String(20), nullable=False) # Tingkat kelangkaan (Common, Rare, dll)
    description = db.Column(db.Text)                 # Info singkat tentang ilmuwan
    image_url = db.Column(db.String(200))            # Path gambar kartunya

class UserCard(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    card_id = db.Column(db.Integer, db.ForeignKey('card.id'), nullable=False)
    obtained_at = db.Column(db.DateTime, default=datetime.utcnow)
# =========================================================
# BADGE
# =========================================================

class Badge(db.Model):
    __tablename__ = "badges"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    name = db.Column(
        db.String(100),
        nullable=False,
    )

    description = db.Column(
        db.Text,
        nullable=False,
    )

    icon_name = db.Column(
        db.String(100),
        nullable=False,
    )

    users = db.relationship(
        "UserBadge",
        back_populates="badge",
        cascade="all, delete-orphan",
    )


class UserBadge(db.Model):
    __tablename__ = "user_badges"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
    )

    badge_id = db.Column(
        db.Integer,
        db.ForeignKey("badges.id"),
        nullable=False,
    )

    unlocked_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
    )

    user = db.relationship(
        "User",
        backref=db.backref(
            "user_badges",
            lazy=True,
        ),
    )

    badge = db.relationship(
        "Badge",
        back_populates="users",
    )


# =========================================================
# NOTIFIKASI
# =========================================================


# =========================================================
# MILESTONE & KOLEKSI
# =========================================================
class MilestoneReward(db.Model):
    __tablename__ = "milestone_rewards"

    id = db.Column(db.Integer, primary_key=True)
    reward_key = db.Column(db.String(100), unique=True, nullable=False)
    required_xp = db.Column(db.Integer, nullable=False)
    reward_type = db.Column(db.String(30), nullable=False)
    category = db.Column(db.String(30), nullable=True)
    title = db.Column(db.String(150), nullable=False)
    subtitle = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    visual_asset = db.Column(db.String(255), nullable=True)
    sort_order = db.Column(db.Integer, default=0, nullable=False)

    users = db.relationship(
        "UserMilestoneReward",
        back_populates="reward",
        cascade="all, delete-orphan",
    )


class UserMilestoneReward(db.Model):
    __tablename__ = "user_milestone_rewards"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
    )
    reward_id = db.Column(
        db.Integer,
        db.ForeignKey("milestone_rewards.id"),
        nullable=False,
    )
    unlocked_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    is_equipped = db.Column(db.Boolean, default=False, nullable=False)

    user = db.relationship(
        "User",
        backref=db.backref("user_milestone_rewards", lazy=True),
    )
    reward = db.relationship("MilestoneReward", back_populates="users")

    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "reward_id",
            name="uq_user_milestone_reward",
        ),
    )

class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
    )

    title = db.Column(
        db.String(100),
        nullable=False,
    )

    message = db.Column(
        db.Text,
        nullable=False,
    )

    is_read = db.Column(
        db.Boolean,
        default=False,
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
    )


# =========================================================
# DAILY QUEST
# =========================================================

class DailyQuestDay(db.Model):
    __tablename__ = "daily_quest_days"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
    )

    quest_date = db.Column(
        db.Date,
        nullable=False,
    )

    reward_xp = db.Column(
        db.Integer,
        default=50,
    )

    is_claimed = db.Column(
        db.Boolean,
        default=False,
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    items = db.relationship(
        "DailyQuestItem",
        backref="quest_day",
        cascade="all, delete-orphan",
        lazy=True,
    )

    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "quest_date",
            name="uq_user_daily_quest_date",
        ),
    )


class DailyQuestItem(db.Model):
    __tablename__ = "daily_quest_items"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    daily_quest_day_id = db.Column(
        db.Integer,
        db.ForeignKey("daily_quest_days.id"),
        nullable=False,
    )

    quest_key = db.Column(
        db.String(50),
        nullable=False,
    )

    title = db.Column(
        db.String(150),
        nullable=False,
    )

    description = db.Column(
        db.Text,
        nullable=False,
    )

    target = db.Column(
        db.Integer,
        default=1,
    )

    progress = db.Column(
        db.Integer,
        default=0,
    )

    is_completed = db.Column(
        db.Boolean,
        default=False,
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        db.UniqueConstraint(
            "daily_quest_day_id",
            "quest_key",
            name="uq_daily_quest_item_key",
        ),
    )


# =========================================================
# OTP
# =========================================================

class OTPVerification(db.Model):
    __tablename__ = "otp_verifications"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    email = db.Column(
        db.String(120),
        nullable=False,
    )

    otp_code = db.Column(
        db.String(6),
        nullable=False,
    )

    username = db.Column(
        db.String(80),
        nullable=False,
    )

    password_hash = db.Column(
        db.String(128),
        nullable=False,
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
    )


# =========================================================
# HASIL LAB UNITY
# =========================================================

class UserLabResult(db.Model):
    __tablename__ = "user_lab_results"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
    )

    material_id = db.Column(
        db.Integer,
        db.ForeignKey("material.id"),
        nullable=False,
    )

    experiment_id = db.Column(
        db.String(100),
        nullable=False,
    )

    display_name = db.Column(
        db.String(150),
        nullable=True,
    )

    duration_seconds = db.Column(
        db.Integer,
        default=0,
    )

    remaining_seconds = db.Column(
        db.Integer,
        default=0,
    )

    elapsed_seconds = db.Column(
        db.Integer,
        default=0,
    )

    timestamp_utc = db.Column(
        db.String(100),
        nullable=True,
    )

    summary_json = db.Column(
        db.Text,
        nullable=True,
    )

    activities_json = db.Column(
        db.Text,
        nullable=True,
    )

    raw_payload_json = db.Column(
        db.Text,
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
    )