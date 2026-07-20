import os
import sys

ROOT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)

sys.path.insert(0, ROOT_DIR)

from app import app
from extensions import db
from models import Material


with app.app_context():
    materials = Material.query.all()

    print("\n=== DAFTAR MATERIAL ===")
    for m in materials:
        print(
            f"ID: {m.id} | "
            f"Title: {m.title} | "
            f"Category: {m.category} | "
            f"unity_scene_id: {m.unity_scene_id}"
        )

    print("\n=== MATERIAL YANG PUNYA LAB ===")
    lab_materials = Material.query.filter(Material.unity_scene_id.isnot(None)).all()

    for m in lab_materials:
        print(
            f"ID: {m.id} | "
            f"Title: {m.title} | "
            f"unity_scene_id: {m.unity_scene_id}"
        )