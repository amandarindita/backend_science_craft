import os
import sqlite3


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "science_craft_be.db")

TABLES = [
    "user_checkpoint_progress",
    "user_submaterial_progress",
    "checkpoints",
    "sub_materials",
]


connection = sqlite3.connect(DB_PATH)

try:
    cursor = connection.cursor()
    tables_with_data = []

    print("Memeriksa tabel baru...")

    for table in TABLES:
        cursor.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name=?",
            (table,),
        )

        exists = cursor.fetchone()

        if not exists:
            print(f"- {table}: belum ada")
            continue

        cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
        row_count = cursor.fetchone()[0]

        print(f"- {table}: {row_count} data")

        if row_count > 0:
            tables_with_data.append(table)

    if tables_with_data:
        print("\nDIBATALKAN.")
        print("Ada tabel yang sudah berisi data:")
        for table in tables_with_data:
            print(f"- {table}")
    else:
        cursor.execute("PRAGMA foreign_keys = OFF")

        for table in TABLES:
            cursor.execute(f'DROP TABLE IF EXISTS "{table}"')
            print(f"Tabel {table} dihapus.")

        connection.commit()
        print("\nTabel baru yang kosong berhasil dibersihkan.")

finally:
    connection.close()