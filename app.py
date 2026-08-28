from datetime import timedelta
import os

from flask import Flask, jsonify, send_from_directory
from flask_migrate import Migrate
from dotenv import load_dotenv

# Extensions
from extensions import db, bcrypt, jwt

# Blueprints
from routes.auth import auth_bp
from routes.gamification import gamification_bp
from routes.admin import admin_bp
from routes.chatbot import chatbot_bp
from routes.daily_quest_routes import daily_quest_bp
from routes.learning import learning_bp
# Pastikan semua model terbaca oleh migration
import models


# =====================================================
# LOAD ENV
# =====================================================

load_dotenv()

app = Flask(__name__)


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
app.register_blueprint(chatbot_bp, url_prefix="/chat")
app.register_blueprint(daily_quest_bp)
app.register_blueprint(learning_bp,url_prefix="/learning",)


# =====================================================
# ROUTES
# =====================================================

@app.route("/")
def hello_world():
    return jsonify({
        "message": "Server Science Craft Siap! (Modular Version 🚀)"
    })


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
    )