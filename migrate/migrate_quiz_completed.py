from app import app, db
from sqlalchemy import inspect, text

with app.app_context():
    inspector = inspect(db.engine)
    columns = [col["name"] for col in inspector.get_columns("user_progress")]

    if "quiz_completed" in columns:
        print("Kolom quiz_completed sudah ada.")
    else:
        with db.engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE user_progress ADD COLUMN quiz_completed BOOLEAN DEFAULT 0"
            ))
            conn.commit()

        print("Kolom quiz_completed berhasil ditambahkan.")