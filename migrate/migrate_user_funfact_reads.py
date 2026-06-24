from app import app, db

with app.app_context():
    db.create_all()
    print("Tabel user_funfact_reads berhasil dicek/dibuat.")