from app import app
from extensions import db
from sqlalchemy import text

with app.app_context():
    try:
        db.session.execute(
            text("ALTER TABLE material ADD COLUMN image_url VARCHAR(255)")
        )
        db.session.commit()
        print("Kolom image_url berhasil ditambahkan.")
    except Exception as e:
        db.session.rollback()
        print("Kolom image_url mungkin sudah ada atau gagal ditambahkan:")
        print(e)