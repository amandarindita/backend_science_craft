import os
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from datetime import datetime

# Import dari folder luar
from extensions import db, bcrypt
from models import User
from services import update_streak

# Bikin Blueprint khusus Auth
auth_bp = Blueprint('auth', __name__)

# 1. LOGIN MANUAL
@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    user = db.session.scalar(db.select(User).filter_by(email=email))

    if not user or not user.password_hash or not bcrypt.check_password_hash(user.password_hash, password):
        return jsonify({"error": "Email atau password salah"}), 401

    update_streak(user) 
    if user.daily_status != 'active':
        user.daily_status = 'login'
        db.session.commit()
    access_token = create_access_token(identity=str(user.id))
    
    # --- UPDATE: Kirim role ke Flutter ---
    return jsonify({
        "access_token": access_token, 
        "message": "Login berhasil!",
        "user": {
            "email": user.email,
            "role": user.role,
             "has_password": bool(user.password_hash)
        }
    }), 200

# 2. REGISTER MANUAL
@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')

    existing_user = db.session.scalar(db.select(User).filter(
        (User.username == username) | (User.email == email)
    ))
    if existing_user:
        return jsonify({"error": "Username atau email sudah terdaftar"}), 409

    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
    today = datetime.utcnow().date()
    
    new_user = User(
        username=username, 
        email=email, 
        password_hash=hashed_password, 
        role='user',
        total_xp=0,
        streak_count=1,       
        last_login_date=today 
    )
    db.session.add(new_user)
    db.session.commit()
    
    access_token = create_access_token(identity=str(new_user.id))
    
    # --- UPDATE: Kirim role ke Flutter ---
    return jsonify({
        "access_token": access_token, 
        "message": f"User {username} berhasil dibuat!",
        "user": {
            "email": new_user.email,
            "role": new_user.role,
            "has_password": True
        }
    }), 201

# 3. LOGIN GOOGLE 
@auth_bp.route('/google', methods=['POST'])
def google_login():
    data = request.get_json()
    token = data.get('token')
    if not token: return jsonify({"error": "Token Google tidak ada"}), 400

    try:
        # PENTING: Nanti pastikan app.config['GOOGLE_CLIENT_ID'] dipanggil di app.py
        google_client_id = os.environ.get('GOOGLE_CLIENT_ID')
        idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), google_client_id)
        
        email = idinfo['email']
        username = idinfo.get('name', email.split('@')[0])
        today = datetime.utcnow().date()

        user = db.session.scalar(db.select(User).filter_by(email=email))
        
        if not user:
            user = User(
                username=username, 
                email=email, 
                password_hash=None, 
                total_xp=0,
                streak_count=1,       
                last_login_date=today 
            )
            db.session.add(user)
            db.session.commit()
        else:
            update_streak(user) 
        if user.daily_status != 'active':
            user.daily_status = 'login'
            db.session.commit()
            
        access_token = create_access_token(identity=str(user.id))
        
        # --- UPDATE: Kirim role ke Flutter ---
        return jsonify({
            "access_token": access_token, 
            "message": "Login Google berhasil!",
            "user": {
                "email": user.email,
                "role": user.role,
                 "has_password": bool(user.password_hash)
            }
        }), 200
        
    except ValueError as e:
        return jsonify({"error": f"Token Google tidak valid: {e}"}), 401

# 4. UPDATE PROFIL
@auth_bp.route('/update-profile', methods=['PUT'])
@jwt_required()
def update_profile():
    current_user_id = get_jwt_identity()
    data = request.get_json()
    new_username = data.get('username')
    new_avatar = data.get('avatar')

    user = db.session.get(User, current_user_id)
    if not user:
        return jsonify({"error": "User tidak ditemukan"}), 404

    if new_username:
        user.username = new_username
    if new_avatar:
        user.avatar = new_avatar
        
    db.session.commit()
    return jsonify({"message": "Profil diperbarui!", "username": user.username}), 200

# 5. GANTI PASSWORD
@auth_bp.route('/change-password', methods=['PUT'])
@jwt_required()
def change_password():
    current_user_id = get_jwt_identity()
    data = request.get_json() or {}

    old_password = data.get('old_password')
    new_password = data.get('new_password')
    confirm_password = data.get('confirm_password')

    user = db.session.get(User, current_user_id)
    if not user:
        return jsonify({"error": "User tidak ditemukan"}), 404

    # Kalau password_hash kosong, berarti akun Google
    if not user.password_hash:
        return jsonify({
            "error": "Akun Google tidak dapat mengubah password melalui aplikasi."
        }), 400

    if not old_password or not new_password or not confirm_password:
        return jsonify({
            "error": "Password lama, password baru, dan konfirmasi password wajib diisi."
        }), 400

    if not bcrypt.check_password_hash(user.password_hash, old_password):
        return jsonify({"error": "Password lama salah."}), 401

    if new_password != confirm_password:
        return jsonify({"error": "Konfirmasi password baru tidak sesuai."}), 400

    if len(new_password) < 6:
        return jsonify({"error": "Password baru minimal 6 karakter."}), 400

    user.password_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')
    db.session.commit()

    return jsonify({"message": "Password berhasil diperbarui."}), 200