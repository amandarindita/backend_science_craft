from app import app, db
from sqlalchemy import inspect, text

with app.app_context():
    inspector = inspect(db.engine)
    columns = [col["name"] for col in inspector.get_columns("question")]

    if "question_type" in columns:
        print("Kolom question_type sudah ada.")
    else:
        with db.engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE question "
                "ADD COLUMN question_type VARCHAR(30) NOT NULL DEFAULT 'pemahaman'"
            ))
            conn.commit()

        print("Kolom question_type berhasil ditambahkan.")