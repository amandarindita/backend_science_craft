# routes/auth.py
import os
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Blueprint, request, jsonify, current_app
# KUNCI 1: Tambahkan create_refresh_token dan parametrik refresh untuk jwt_required
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, get_jwt_identity
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from datetime import datetime, timedelta

# Import dari folder luar
from extensions import db, bcrypt
from models import User, OTPVerification
from services import update_streak

# Bikin Blueprint khusus Auth
auth_bp = Blueprint('auth', __name__)

# ==========================================
# HELPER: FUNGSI KIRIM EMAIL OTP VIA SMTP
# ==========================================
def send_email_otp(target_email, otp_code):
    smtp_server = current_app.config.get('SMTP_SERVER', 'smtp.gmail.com')
    smtp_port = current_app.config.get('SMTP_PORT', 587)
    sender_email = current_app.config.get('EMAIL_USER')
    sender_password = current_app.config.get('EMAIL_PASS')

    if not sender_email or not sender_password:
        print("Error: Konfigurasi email di .env / app.py belum lengkap!")
        return False

    message = MIMEMultipart("alternative")
    message["Subject"] = "Kode OTP Verifikasi Akun Science Craft"
    message["From"] = sender_email
    message["To"] = target_email

    text = f"""
Halo,

Terima kasih sudah mendaftar di Science Craft.

Kode OTP Anda adalah: {otp_code}

Kode ini berlaku selama 5 menit. Jangan bagikan kode ini kepada siapa pun.

Salam,
Science Craft Team
"""

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="UTF-8">
    </head>
    <body style="margin:0; padding:0; background-color:#F3F7FB; font-family:Arial, Helvetica, sans-serif;">
      <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#F3F7FB; padding:30px 0;">
        <tr>
          <td align="center">

            <table width="100%" cellpadding="0" cellspacing="0" style="max-width:520px; background-color:#ffffff; border-radius:18px; overflow:hidden; box-shadow:0 8px 24px rgba(0,0,0,0.08);">
              
              <!-- Header -->
              <tr>
                <td style="background:linear-gradient(135deg, #2B6CB0, #38B2AC); padding:28px 24px; text-align:center;">
                  <h1 style="margin:0; color:#ffffff; font-size:26px; letter-spacing:0.5px;">
                    Science Craft
                  </h1>
                  <p style="margin:8px 0 0; color:#E6FFFA; font-size:14px;">
                    Verifikasi Akun Pembelajaran Sains Interaktif
                  </p>
                </td>
              </tr>

              <!-- Content -->
              <tr>
                <td style="padding:32px 28px; text-align:center;">
                  <h2 style="margin:0 0 12px; color:#1A202C; font-size:22px;">
                    Kode Verifikasi OTP
                  </h2>

                  <p style="margin:0 0 22px; color:#4A5568; font-size:15px; line-height:1.6;">
                    Gunakan kode di bawah ini untuk menyelesaikan proses registrasi akun Science Craft Anda.
                  </p>

                  <div style="display:inline-block; background-color:#EDF2F7; border:2px dashed #2B6CB0; border-radius:14px; padding:16px 28px; margin:8px 0 22px;">
                    <span style="font-size:34px; font-weight:bold; color:#E53E3E; letter-spacing:8px;">
                      {otp_code}
                    </span>
                  </div>

                  <p style="margin:0; color:#718096; font-size:14px; line-height:1.6;">
                    Kode ini berlaku selama <b style="color:#2D3748;">5 menit</b>.<br>
                    Jangan bagikan kode ini kepada siapa pun.
                  </p>
                </td>
              </tr>

              <!-- Warning Box -->
              <tr>
                <td style="padding:0 28px 28px;">
                  <div style="background-color:#FFF5F5; border-left:5px solid #E53E3E; padding:14px 16px; border-radius:10px;">
                    <p style="margin:0; color:#742A2A; font-size:13px; line-height:1.5;">
                      Jika Anda tidak merasa melakukan registrasi, abaikan email ini.
                    </p>
                  </div>
                </td>
              </tr>

              <!-- Footer -->
              <tr>
                <td style="background-color:#F7FAFC; padding:18px 24px; text-align:center;">
                  <p style="margin:0; color:#A0AEC0; font-size:12px;">
                    © Science Craft — Virtual Science Learning App
                  </p>
                </td>
              </tr>

            </table>

          </td>
        </tr>
      </table>
    </body>
    </html>
    """

    message.attach(MIMEText(text, "plain"))
    message.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, target_email, message.as_string())
        return True

    except Exception as e:
        print(f"SMTP Error: {e}")
        return False


# ==========================================
# 1. REGISTER AWAL (INPUT USERNAME, EMAIL, PASSWORD)
# ==========================================
@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')

    if not all([username, email, password]):
        return jsonify({"error": "Username, email, dan password wajib diisi"}), 400

    existing_user = db.session.scalar(db.select(User).filter(
        (User.username == username) | (User.email == email)
    ))
    if existing_user:
        return jsonify({"error": "Username atau email sudah terdaftar"}), 409

    otp_code = f"{random.randint(100000, 999999)}"

    if not send_email_otp(email, otp_code):
        return jsonify({"error": "Gagal mengirim email OTP, silakan coba lagi nanti."}), 500

    db.session.execute(db.delete(OTPVerification).filter_by(email=email))

    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

    new_otp = OTPVerification(
        email=email,
        otp_code=otp_code,
        username=username,
        password_hash=hashed_password
    )
    db.session.add(new_otp)
    db.session.commit()

    return jsonify({"message": "Registrasi awal berhasil! Silakan cek kode OTP di email Anda."}), 200


# ==========================================
# 2. VERIFIKASI OTP (LANGSUNG DONE DAN JADI USER)
# ==========================================
@auth_bp.route('/register/verify-otp', methods=['POST'])
def verify_otp():
    data = request.get_json() or {}
    email = data.get('email')
    otp_input = data.get('otp')

    if not email or not otp_input:
        return jsonify({"error": "Email dan kode OTP wajib diisi"}), 400

    otp_record = db.session.scalar(
        db.select(OTPVerification).filter_by(email=email).order_by(OTPVerification.created_at.desc())
    )

    if not otp_record or otp_record.otp_code != str(otp_input):
        return jsonify({"error": "Kode OTP salah atau tidak cocok"}), 400

    if datetime.utcnow() - otp_record.created_at > timedelta(minutes=5):
        db.session.delete(otp_record)
        db.session.commit()
        return jsonify({"error": "Kode OTP sudah kedaluwarsa, silakan register ulang."}), 400

    existing_user = db.session.scalar(db.select(User).filter(
        (User.username == otp_record.username) | (User.email == email)
    ))
    if existing_user:
        db.session.delete(otp_record)
        db.session.commit()
        return jsonify({"error": "Username atau email sudah terdaftar"}), 409

    today = datetime.utcnow().date()
    new_user = User(
        username=otp_record.username, 
        email=otp_record.email, 
        password_hash=otp_record.password_hash, 
        role='user',
        total_xp=0,
        streak_count=1,       
        last_login_date=today,
        daily_status='login'
    )
    db.session.add(new_user)
    
    db.session.delete(otp_record)
    db.session.commit()
    
    # KUNCI 2: Bikin Access Token + Refresh Token
    access_token = create_access_token(identity=str(new_user.id))
    refresh_token = create_refresh_token(identity=str(new_user.id))
    
    return jsonify({
        "access_token": access_token, 
        "refresh_token": refresh_token, 
        "message": f"Verifikasi berhasil! Akun {new_user.username} telah aktif.",
        "user": {
            "email": new_user.email,
            "role": new_user.role,
            "has_password": True
        }
    }), 201


# ==========================================
# 3. LOGIN MANUAL
# ==========================================
@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    email = data.get('email')
    password = data.get('password')
    user = db.session.scalar(db.select(User).filter_by(email=email))

    if not user or not user.password_hash or not bcrypt.check_password_hash(user.password_hash, password):
        return jsonify({"error": "Email atau password salah"}), 401
    
    today = datetime.utcnow().date()
    old_last_login_date = user.last_login_date

    update_streak(user)

    if old_last_login_date != today:
        user.daily_status = 'login'

    db.session.commit()

    # KUNCI 3: Bikin Access Token + Refresh Token untuk Login Manual
    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))
 
    return jsonify({
        "access_token": access_token, 
        "refresh_token": refresh_token,
        "message": "Login berhasil!",
        "user": {
            "email": user.email,
            "role": user.role,
            "has_password": bool(user.password_hash)
        }
    }), 200


# ==========================================
# 4. LOGIN GOOGLE
# ==========================================
@auth_bp.route('/google', methods=['POST'])
def google_login():
    data = request.get_json() or {}
    token = data.get('token')
    if not token: 
        return jsonify({"error": "Token Google tidak ada"}), 400

    try:
        google_client_id = current_app.config.get('GOOGLE_CLIENT_ID')
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
            old_last_login_date = user.last_login_date
            update_streak(user)

            if old_last_login_date != today:
                user.daily_status = 'login'

        db.session.commit()
            
        # KUNCI 4: Bikin Access Token + Refresh Token untuk Google Login
        access_token = create_access_token(identity=str(user.id))
        refresh_token = create_refresh_token(identity=str(user.id))
        
        return jsonify({
            "access_token": access_token, 
            "refresh_token": refresh_token, 
            "message": "Login Google berhasil!",
            "user": {
                "email": user.email,
                "role": user.role,
                "has_password": bool(user.password_hash)
            }
        }), 200
        
    except ValueError as e:
        return jsonify({"error": f"Token Google tidak valid: {e}"}), 401


# ==========================================
# NEW KUNCI 5: ENDPOINT REFRESH TOKEN
# ==========================================
@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """
    Endpoint ini digunakan jika access_token sudah expired.
    Flutter harus mengirimkan 'refresh_token' di Header Authorization Bearer.
    """
    current_user_id = get_jwt_identity()
    new_access_token = create_access_token(identity=current_user_id)
    return jsonify({
        "access_token": new_access_token,
        "message": "Access token berhasil diperbarui!"
    }), 200


# ==========================================
# 5. UPDATE PROFIL
# ==========================================
@auth_bp.route('/update-profile', methods=['PUT'])
@jwt_required()
def update_profile():
    current_user_id = get_jwt_identity()
    data = request.get_json() or {}
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


# ==========================================
# 6. GANTI PASSWORD
# ==========================================
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

# ==========================================
# 7. LUPA PASSWORD - KIRIM OTP
# ==========================================
@auth_bp.route('/forgot-password/request-otp', methods=['POST'])
def forgot_password_request_otp():
    data = request.get_json() or {}
    email = data.get('email')

    if not email:
        return jsonify({"error": "Email wajib diisi"}), 400

    user = db.session.scalar(db.select(User).filter_by(email=email))

    if not user:
        return jsonify({"error": "Email tidak ditemukan"}), 404

    if not user.password_hash:
        return jsonify({
            "error": "Akun Google tidak dapat reset password melalui OTP."
        }), 400

    otp_code = f"{random.randint(100000, 999999)}"

    if not send_email_otp(email, otp_code):
        return jsonify({
            "error": "Gagal mengirim OTP ke email."
        }), 500

    db.session.execute(db.delete(OTPVerification).filter_by(email=email))

    otp_record = OTPVerification(
        email=email,
        otp_code=otp_code,
        username=user.username,
        password_hash=user.password_hash
    )

    db.session.add(otp_record)
    db.session.commit()

    return jsonify({
        "message": "Kode OTP reset password berhasil dikirim ke email."
    }), 200


# ==========================================
# 8. LUPA PASSWORD - RESET PASSWORD
# ==========================================
@auth_bp.route('/forgot-password/reset', methods=['POST'])
def forgot_password_reset():
    data = request.get_json() or {}

    email = data.get('email')
    otp_input = data.get('otp')
    new_password = data.get('new_password')
    confirm_password = data.get('confirm_password')

    if not email or not otp_input or not new_password or not confirm_password:
        return jsonify({
            "error": "Email, OTP, password baru, dan konfirmasi password wajib diisi."
        }), 400

    if new_password != confirm_password:
        return jsonify({
            "error": "Konfirmasi password baru tidak sesuai."
        }), 400

    if len(new_password) < 6:
        return jsonify({
            "error": "Password baru minimal 6 karakter."
        }), 400

    user = db.session.scalar(db.select(User).filter_by(email=email))

    if not user:
        return jsonify({"error": "Email tidak ditemukan"}), 404

    otp_record = db.session.scalar(
        db.select(OTPVerification)
        .filter_by(email=email)
        .order_by(OTPVerification.created_at.desc())
    )

    if not otp_record or otp_record.otp_code != str(otp_input):
        return jsonify({"error": "Kode OTP salah atau tidak cocok"}), 400

    if datetime.utcnow() - otp_record.created_at > timedelta(minutes=5):
        db.session.delete(otp_record)
        db.session.commit()
        return jsonify({
            "error": "Kode OTP sudah kedaluwarsa. Silakan minta OTP baru."
        }), 400

    user.password_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')

    db.session.delete(otp_record)
    db.session.commit()

    return jsonify({
        "message": "Password berhasil direset. Silakan login dengan password baru."
    }), 200