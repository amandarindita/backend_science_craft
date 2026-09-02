from app import app, db

def create_database():
    print("Mencoba membuat/memperbarui tabel database...")
    try:
        with app.app_context():
            db.create_all()
        print("Database dan tabel berhasil dibuat/diperbarui.")
    except Exception as e:
        print(f"Terjadi error saat membuat database: {e}")

if __name__ == '__main__':
    create_database()
