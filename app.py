import os
import fitz
from flask import Flask, jsonify, request
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
import google.generativeai as genai
from datetime import datetime, timedelta

# <-- Import untuk LangChain RAG -->
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

# Muat variabel dari file .env
load_dotenv()

# --- INISIALISASI ---
app = Flask(__name__)
bcrypt = Bcrypt(app) 

# --- KONFIGURASI GEMINI ---
genai.configure(api_key=os.environ.get('GEMINI_API_KEY')) 
model = genai.GenerativeModel('gemini-2.5-flash')

# --- INISIALISASI RAG (PDF & Vector DB) ---
try:
    folder_path = "dataset"
    all_text = ""
    if os.path.isdir(folder_path):
        for filename in os.listdir(folder_path):
            if filename.endswith(".pdf"):
                file_path = os.path.join(folder_path, filename)
                print(f"Membaca file: {file_path}")
                doc = fitz.open(file_path)
                for page in doc:
                    all_text += page.get_text("text") + "\n"
    else:
        print(f"Error: Folder '{folder_path}' tidak ditemukan.")
        all_text = "" 

    if all_text:
        print("Memulai split text...")
        splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
        chunks = splitter.split_text(all_text)
        print("Memulai embedding...")
        embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
        vector_db = Chroma.from_texts(chunks, embedding=embeddings) 
        print("Vector DB siap!")
    else:
        print("Tidak ada teks PDF. Chatbot jalan tanpa konteks.")
        vector_db = None

except Exception as e:
    print(f"Terjadi error saat inisialisasi RAG: {e}")
    vector_db = None

# --- KONFIGURASI DATABASE ---
db_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'science_craft_be.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- KONFIGURASI JWT ---
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY')
app.config['GOOGLE_CLIENT_ID'] = os.environ.get('GOOGLE_CLIENT_ID')
jwt = JWTManager(app)
db = SQLAlchemy(app) 

# --- MODEL DATABASE ---

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=True)
    
    avatar = db.Column(db.String(100), default='assets/aira.png')
    # Data Gamifikasi
    total_xp = db.Column(db.Integer, default=0) 
    
    # --- DATA STREAK ---
    streak_count = db.Column(db.Integer, default=0)
    last_login_date = db.Column(db.Date, nullable=True) # Format: YYYY-MM-DD
    
    def __repr__(self):
        return f'<User {self.username}>'

class UserProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    material_id = db.Column(db.Integer, nullable=False)
    progress = db.Column(db.Float, nullable=False, default=0.0)
    __table_args__ = (db.UniqueConstraint('user_id', 'material_id', name='_user_material_uc'),)

class UserBadge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    badge_code = db.Column(db.String(50), nullable=False)
    earned_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('user_id', 'badge_code', name='_user_badge_uc'),)


# --- FUNGSI BUAT TABEL ---
with app.app_context():
    db.create_all()

# --- HELPER FUNCTION: HITUNG STREAK (PUSAT LOGIKA) ---
# Fungsi ini dipanggil oleh Login Manual DAN Login Google
def update_streak(user):
    today = datetime.utcnow().date()
    
    # Jika User belum login hari ini
    if user.last_login_date != today:
        
        # Cek apakah login terakhir adalah KEMARIN
        if user.last_login_date is not None and user.last_login_date == today - timedelta(days=1):
            user.streak_count += 1 # Streak Nambah!
        else:
            user.streak_count = 1 # Streak Reset/Awal
        
        # Simpan tanggal hari ini
        user.last_login_date = today
        db.session.commit()

# --- ENDPOINT AUTH ---

@app.route('/')
def hello_world():
    return jsonify({"message": "Server Science Craft Siap! (Mode Hybrid + Streak)"})

# 1. LOGIN MANUAL
@app.route('/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    user = db.session.scalar(db.select(User).filter_by(email=email))

    if not user or not user.password_hash or not bcrypt.check_password_hash(user.password_hash, password):
        return jsonify({"error": "Email atau password salah"}), 401

    # --- PANGGIL HELPER STREAK ---
    update_streak(user) 
    # -----------------------------

    access_token = create_access_token(identity=user.id)
    return jsonify(access_token=access_token, message="Login berhasil!"), 200

# 2. REGISTER MANUAL
@app.route('/auth/register', methods=['POST'])
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
        total_xp=0,
        streak_count=1,       
        last_login_date=today 
    )
    db.session.add(new_user)
    db.session.commit()
    
    access_token = create_access_token(identity=new_user.id)
    return jsonify(access_token=access_token, message=f"User {username} berhasil dibuat!"), 201

# 3. LOGIN GOOGLE 
@app.route('/auth/google', methods=['POST'])
def google_login():
    data = request.get_json()
    token = data.get('token')
    if not token: return jsonify({"error": "Token Google tidak ada"}), 400

    try:
        idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), app.config['GOOGLE_CLIENT_ID'])
        email = idinfo['email']
        username = idinfo.get('name', email.split('@')[0])
        
        today = datetime.utcnow().date()

        user = db.session.scalar(db.select(User).filter_by(email=email))
        
        if not user:
            # --- KASUS A: User Google BARU ---
            user = User(
                username=username, 
                email=email, 
                password_hash=None, 
                total_xp=0,
                streak_count=1,       # Langsung set 1
                last_login_date=today # Langsung set hari ini
            )
            db.session.add(user)
            db.session.commit()
        else:
            # --- KASUS B: User Google LAMA (YANG DULU ERROR) ---
            # Sekarang kita panggil update_streak() di sini juga!
            update_streak(user) 
            
        access_token = create_access_token(identity=str(user.id))
        return jsonify(access_token=access_token, message=f"Login Google berhasil!"), 200
        
    except ValueError as e:
        return jsonify({"error": f"Token Google tidak valid: {e}"}), 401


# --- ENDPOINT LAINNYA ---

@app.route('/auth/update-profile', methods=['PUT'])
@jwt_required()
def update_profile():
    current_user_id = get_jwt_identity()
    data = request.get_json()
    new_username = data.get('username')
    new_avatar = data.get('avatar')

    if not new_username:
        return jsonify({"error": "Username tidak boleh kosong"}), 400

    user = db.session.get(User, current_user_id)
    if user:
        user.username = new_username
        db.session.commit()
        return jsonify({"message": "Profil diperbarui!", "username": user.username}), 200
    
    if new_avatar:
            user.avatar = new_avatar
    
    return jsonify({"error": "User tidak ditemukan"}), 404

    

@app.route('/sync/progress', methods=['POST'])
@jwt_required()
def sync_progress():
    current_user_id = get_jwt_identity()
    data = request.get_json()
    material_id = data.get('material_id')
    progress = data.get('progress')

    if material_id is None or progress is None:
        return jsonify({"error": "Data tidak lengkap"}), 400

    user_progress = db.session.scalar(db.select(UserProgress).filter_by(
        user_id=current_user_id, material_id=material_id
    ))
    
    if user_progress:
        user_progress.progress = progress
    else:
        user_progress = UserProgress(user_id=current_user_id, material_id=material_id, progress=progress)
        db.session.add(user_progress)

    db.session.commit()
    return jsonify({"message": "Progress tersimpan di server"}), 200

@app.route('/sync/all-progress', methods=['GET'])
@jwt_required()
def get_all_progress():
    current_user_id = get_jwt_identity()
    all_progress = db.session.execute(
        db.select(UserProgress).filter_by(user_id=current_user_id)
    ).scalars().all()

    result = [{"material_id": p.material_id, "progress": p.progress} for p in all_progress]
    return jsonify(result), 200

@app.route('/gamification/xp', methods=['POST'])
@jwt_required()
def add_xp():
    current_user_id = get_jwt_identity()
    data = request.get_json()
    amount = data.get('amount')

    if not amount: return jsonify({"error": "Jumlah XP diperlukan"}), 400

    user = db.session.get(User, current_user_id)
    if user:
        user.total_xp += int(amount)
        db.session.commit()
        return jsonify({"message": "XP bertambah", "current_xp": user.total_xp}), 200
    return jsonify({"error": "User tidak ditemukan"}), 404

@app.route('/gamification/user-data', methods=['GET'])
@jwt_required()
def get_user_data():
    current_user_id = get_jwt_identity()
    user = db.session.get(User, current_user_id)
    
    badges = db.session.execute(
        db.select(UserBadge).filter_by(user_id=current_user_id)
    ).scalars().all()
    badge_codes = [b.badge_code for b in badges]

    if user:
        return jsonify({
            "username": user.username,
            "total_xp": user.total_xp,
            "streak": user.streak_count, 
            "badges": badge_codes,
            "has_password": user.password_hash is not None, 
            "avatar": user.avatar if user.avatar else 'assets/aira.png'
        }), 200
    return jsonify({"error": "User tidak ditemukan"}), 404

@app.route('/gamification/badge', methods=['POST'])
@jwt_required()
def unlock_badge():
    current_user_id = get_jwt_identity()
    data = request.get_json()
    badge_code = data.get('badge_code')

    if not badge_code: return jsonify({"error": "Kode badge diperlukan"}), 400

    existing = db.session.scalar(db.select(UserBadge).filter_by(
        user_id=current_user_id, badge_code=badge_code
    ))

    if existing: return jsonify({"message": "User sudah punya badge ini"}), 200

    new_badge = UserBadge(user_id=current_user_id, badge_code=badge_code)
    db.session.add(new_badge)
    db.session.commit()
    return jsonify({"message": f"Badge {badge_code} berhasil dibuka!"}), 200

@app.route('/auth/delete', methods=['DELETE'])
@jwt_required()
def delete_account():
    current_user_id = get_jwt_identity()
    user = db.session.get(User, current_user_id)
    
    if not user:
        return jsonify({"error": "User tidak ditemukan"}), 404

    try:
        # 1. Hapus Data Pendukung Dulu (Bersih-bersih)
        # Kita hapus progress belajar & badge user ini
        db.session.execute(db.delete(UserProgress).filter_by(user_id=current_user_id))
        db.session.execute(db.delete(UserBadge).filter_by(user_id=current_user_id))
        
        # 2. Hapus User Utama
        db.session.delete(user)
        db.session.commit()
        
        return jsonify({"message": "Akun berhasil dihapus permanen."}), 200

    except Exception as e:
        db.session.rollback() # Batalkan kalau ada error
        print(f"Error delete user: {e}")
        return jsonify({"error": "Gagal menghapus akun"}), 500
    
# --- CHATBOT ---
def ask_cheerful_scibot(question):
    context = ""
    if vector_db:
        retriever = vector_db.as_retriever(search_kwargs={"k": 3}) 
        docs = retriever.invoke(question)
        context = "\n".join([d.page_content for d in docs])
    
    prompt = f"""
    Kamu adalah SENA (Science Education Navigator Assistant),
    asisten sains ceria dan edukatif untuk anak SMA.
    Jawablah dengan gaya ringan, bersemat, dan mudah dipahami.

    Gunakan konteks berikut JIKA ADA untuk membantu menjawab:
    {context}

    Pertanyaan: {question}
    """
    response = model.generate_content(prompt) 
    return response.text

@app.route('/chat-gemini', methods=['POST'])
def chat_gemini():
    data = request.get_json()
    user_message = data.get('message', '')
    if not user_message: return jsonify({"error": "Pesan tidak boleh kosong"}), 400
    try:
        reply = ask_cheerful_scibot(user_message)
        return jsonify({"reply": reply})
    except Exception as e:
        print(f"Error di /chat-gemini: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)