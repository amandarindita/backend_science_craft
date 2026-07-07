import os
from flask import Flask, jsonify
from dotenv import load_dotenv

# 1. Import Extensions
from extensions import db, bcrypt, jwt

# 2. Import Blueprints (Rute yang sudah kita pisah-pisah)
from routes.auth import auth_bp
from routes.gamification import gamification_bp
from routes.admin import admin_bp
from routes.chatbot import chatbot_bp
from routes.daily_quest_routes import daily_quest_bp
from flask import Flask, jsonify, send_from_directory
# 3. Import Models (Sangat penting agar db.create_all() mendeteksi semua tabel)
import models

# Muat variabel dari file .env
load_dotenv()

app = Flask(__name__)

# --- KONFIGURASI DATABASE & JWT ---
db_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'science_craft_be.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'rahasia-skripsi-123')
app.config['GOOGLE_CLIENT_ID'] = os.environ.get('GOOGLE_CLIENT_ID')
UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# --- INISIALISASI EXTENSIONS ---
db.init_app(app)
bcrypt.init_app(app)
jwt.init_app(app)

# --- REGISTER BLUEPRINTS (Menyambungkan rute ke aplikasi utama) ---
app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(gamification_bp) # Tanpa prefix karena di filenya sudah ditulis /gamification/... dan /sync/...
app.register_blueprint(admin_bp, url_prefix='/admin')
print(app.url_map)
app.register_blueprint(chatbot_bp, url_prefix='/chat')
app.register_blueprint(daily_quest_bp)

# --- BUAT TABEL OTOMATIS ---
with app.app_context():
    db.create_all()

# --- RUTE TES SERVER ---
@app.route('/')
def hello_world():
    return jsonify({"message": "Server Science Craft Siap! (Modular Version 🚀)"})
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)