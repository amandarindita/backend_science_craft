from app import app
from extensions import db
from models import Badge

with app.app_context():
    # 1. Perintah buat maksa SQLAlchemy bikin tabel baru yang belum ada di .db
    db.create_all()
    
    # 2. Cek dulu biar kalau script ini di-run ulang, datanya nggak double
    if Badge.query.count() == 0:
        ten_badges = [
            Badge(name="Darwin’s Successor", description="Berhasil menyelesaikan seluruh modul teori dan eksperimen Biologi.", icon_name="1.png"),
            Badge(name="Quantum Overlord", description="Sukses menaklukkan seluruh tantangan hukum alam  dan mekanika Fisika.", icon_name="2.png"),
            Badge(name="The Modern Alchemist", description="Berhasil memahami seluruh reaksi zat dan struktur senyawa Kimia.", icon_name="3.png"),
            Badge(name="Virtual Researcher", description="Pertama kali berhasil melakukan simulasi laboratorium eksperimen 2D.", icon_name="4.png"),
            Badge(name="Mad Scientist", description="Berhasil menyelesaikan 3 atau lebih simulasi eksperimen di laboratorium virtual.", icon_name="5.png"),
            Badge(name="Grand Analyst", description="Berhasil menjawab soal studi kasus kuis dengan nilai sempurna (100) pada percobaan pertama.", icon_name="6.png"),
            Badge(name="Lab Regular", description="Mempertahankan streak belajar selama 7 hari berturut-turut.", icon_name="7.png"),
            Badge(name="First Spark", description="Memulai perjalanan sains dengan menyelesaikan 1 materi pertamamu.", icon_name="8.png"),
            Badge(name="Trivia Rover", description="Menemukan dan membaca 5 fakta unik sains (FunFact) di halaman utama.", icon_name="9.png"),
            Badge(name="Night Owl", description="Membaca materi atau menyelesaikan kuis di atas jam 10 malam.", icon_name="10.png"),
            Badge(name="Flawless Victory", description="Mendapatkan nilai sempurna (100) di 3 kuis yang berbeda.", icon_name="11.png")
        ]
        
        db.session.bulk_save_objects(ten_badges)
        db.session.commit()
        print("MANTAAP! 10 Master Badge berhasil disuntikkan ke database! 🔥🚀")
    else:
        print("Aman, data badge sudah ada sebelumnya")