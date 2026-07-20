import os
import sys

ROOT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)

sys.path.insert(0, ROOT_DIR)

from app import app
from extensions import db
from sqlalchemy import inspect
from models import UserLabResult


with app.app_context():
    print("Mengecek / membuat tabel user_lab_results...")

    db.create_all()

    inspector = inspect(db.engine)
    tables = inspector.get_table_names()

    if "user_lab_results" in tables:
        print("✅ Tabel user_lab_results sudah ada / berhasil dibuat.")
    else:
        print("❌ Tabel user_lab_results belum ditemukan.")