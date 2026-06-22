#!/bin/bash
# ══════════════════════════════════════════════════════════════
#  setup_postgres.sh — установка PostgreSQL и создание БД
#  Ubuntu 22/24 LTS
#  Запуск: chmod +x setup_postgres.sh && sudo ./setup_postgres.sh
# ══════════════════════════════════════════════════════════════

set -e   # остановить при ошибке

# ─── Настройки — измените под себя ───────────────────────────
DB_NAME="attendance"
DB_USER="attendance_user"
DB_PASS="peshkakot1336"   # ЗАМЕНИТЕ на свой пароль
# ─────────────────────────────────────────────────────────────

echo "=== 1. Установка PostgreSQL ==="
apt update
apt install -y postgresql postgresql-contrib

echo "=== 2. Запуск службы ==="
systemctl enable postgresql
systemctl start  postgresql

echo "=== 3. Создание пользователя и базы данных ==="
sudo -u postgres psql << SQL
-- Создаём пользователя
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$DB_USER') THEN
        CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';
    END IF;
END
\$\$;

-- Создаём базу данных
SELECT 'CREATE DATABASE $DB_NAME OWNER $DB_USER ENCODING ''UTF8'''
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$DB_NAME')\gexec

-- Выдаём права
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;
SQL

echo "=== 4. Создание таблиц из init_db.sql ==="
sudo -u postgres psql -d "$DB_NAME" -f "$(dirname "$0")/init_db.sql"

echo "=== 5. Выдача прав на таблицы и последовательности ==="
sudo -u postgres psql -d "$DB_NAME" << SQL
GRANT ALL ON ALL TABLES    IN SCHEMA public TO $DB_USER;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO $DB_USER;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT ALL ON TABLES    TO $DB_USER;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT ALL ON SEQUENCES TO $DB_USER;
SQL

echo ""
echo "══════════════════════════════════════════════════════"
echo "  PostgreSQL настроен успешно!"
echo "  База:     $DB_NAME"
echo "  Пользов.: $DB_USER"
echo ""
echo "  Добавьте в .env файл:"
echo "  DB_HOST=localhost"
echo "  DB_PORT=5432"
echo "  DB_NAME=$DB_NAME"
echo "  DB_USER=$DB_USER"
echo "  DB_PASSWORD=$DB_PASS"
echo "══════════════════════════════════════════════════════"
