from datetime import timedelta
import os
import sys

# Ensure UTF-8 output on Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from flask import Flask, jsonify, send_from_directory, redirect, url_for
from flask_migrate import Migrate
from dotenv import load_dotenv

# Extensions
from extensions import db, bcrypt, jwt

# Blueprints
from routes.auth import auth_bp
from routes.gamification import gamification_bp
from routes.admin import admin_bp
from routes.admin_web import admin_web_bp
from routes.chatbot import chatbot_bp
from routes.daily_quest_routes import daily_quest_bp
from routes.learning import learning_bp

# Pastikan semua model terbaca oleh migration
import models


# =====================================================
# LOAD ENV & INITIALIZE APP
# =====================================================

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "science-craft-superadmin-secret-2026")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=4)


# =====================================================
# DATABASE
# =====================================================

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(BASE_DIR, "science_craft_be.db")

app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


# =====================================================
# JWT
# =====================================================

app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(minutes=15)
app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=30)

app.config["JWT_SECRET_KEY"] = os.environ.get(
    "JWT_SECRET_KEY",
    "rahasia-skripsi-123",
)

app.config["GOOGLE_CLIENT_ID"] = os.environ.get("GOOGLE_CLIENT_ID")


# =====================================================
# EMAIL
# =====================================================

app.config["EMAIL_USER"] = os.environ.get("EMAIL_USER")
app.config["EMAIL_PASS"] = os.environ.get("EMAIL_PASS")
app.config["SMTP_SERVER"] = os.environ.get(
    "SMTP_SERVER",
    "smtp.gmail.com",
)
app.config["SMTP_PORT"] = int(
    os.environ.get("SMTP_PORT", 587)
)


# =====================================================
# UPLOAD
# =====================================================

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# =====================================================
# INITIALIZE EXTENSIONS
# =====================================================

db.init_app(app)
bcrypt.init_app(app)
jwt.init_app(app)

# Ini yang membuat perintah `flask db` tersedia
migrate = Migrate(app, db)


# =====================================================
# REGISTER BLUEPRINTS
# =====================================================

app.register_blueprint(auth_bp, url_prefix="/auth")
app.register_blueprint(gamification_bp)
app.register_blueprint(admin_bp, url_prefix="/admin")
app.register_blueprint(admin_web_bp, url_prefix="/admin/web")
app.register_blueprint(chatbot_bp, url_prefix="/chat")
app.register_blueprint(daily_quest_bp)
app.register_blueprint(learning_bp, url_prefix="/learning")


# =====================================================
# ROUTES
# =====================================================

@app.route("/")
def hello_world():
    return jsonify({
        "message": "Server Science Craft Siap! (Modular Version with KeyRotator & Superadmin Dashboard)"
    })


@app.route("/admin/panel")
def redirect_to_admin():
    return redirect(url_for("admin_web.login_page"))


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        filename,
    )


# =====================================================
# RUN SERVER
# =====================================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True,
        exclude_patterns=[
            "*chroma_db*",
            "*uploads*",
            "*.db*",
            "*.sqlite3*",
            "*.sqlite3-journal",
            "*.sqlite3-wal",
            "*.sqlite3-shm",
        ],
    )
