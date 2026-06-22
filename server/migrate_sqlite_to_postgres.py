"""
migrate_sqlite_to_postgres.py — перенос данных из SQLite в PostgreSQL.

Запуск (после того как PostgreSQL настроен и таблицы созданы):
    python migrate_sqlite_to_postgres.py

Требования:
    - attendance.db (SQLite) в текущей директории
    - Заполненный .env с настройками PostgreSQL
    - pip install psycopg2-binary python-dotenv
"""

import os
import sqlite3
import psycopg2
from dotenv import load_dotenv

load_dotenv()

SQLITE_PATH = os.path.join(os.path.dirname(__file__), "..", "attendance.db")

DB_HOST = os.getenv("DB_HOST",     "localhost")
DB_PORT = os.getenv("DB_PORT",     "5432")
DB_NAME = os.getenv("DB_NAME",     "attendance")
DB_USER = os.getenv("DB_USER",     "attendance_user")
DB_PASS = os.getenv("DB_PASSWORD", "")


def migrate():
    print("Подключение к SQLite...")
    sqlite = sqlite3.connect(SQLITE_PATH)
    sqlite.row_factory = sqlite3.Row

    print("Подключение к PostgreSQL...")
    pg = psycopg2.connect(
        host=DB_HOST, port=DB_PORT,
        dbname=DB_NAME, user=DB_USER, password=DB_PASS,
    )
    pg.autocommit = False
    cur = pg.cursor()

    tables = [
        "users", "groups", "subjects", "students",
        "student_photos", "lessons", "attendance",
    ]

    for table in tables:
        rows = sqlite.execute(f"SELECT * FROM {table}").fetchall()
        if not rows:
            print(f"  {table}: нет данных, пропускаем")
            continue

        cols     = rows[0].keys()
        col_str  = ", ".join(cols)
        val_str  = ", ".join(["%s"] * len(cols))

        print(f"  {table}: перенос {len(rows)} записей...")

        for row in rows:
            values = [row[c] for c in cols]
            # bytes в SQLite → bytes в PostgreSQL (BYTEA) — без изменений
            cur.execute(
                f"INSERT INTO {table} ({col_str}) VALUES ({val_str}) "
                f"ON CONFLICT DO NOTHING",
                values,
            )

        # Сбрасываем последовательность SERIAL чтобы следующий id был правильным
        if "id" in cols:
            cur.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE(MAX(id), 1)) FROM {table}"
            )

    pg.commit()
    print("\nМиграция завершена успешно!")
    sqlite.close()
    pg.close()


if __name__ == "__main__":
    migrate()
