-- ══════════════════════════════════════════════════════════════
--  init_db.sql — создание таблиц базы данных системы
--  СУБД: PostgreSQL 14+
--  Запуск: psql -U attendance_user -d attendance -f init_db.sql
-- ══════════════════════════════════════════════════════════════

-- Расширение для генерации UUID (опционально, если понадобится)
-- CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ─────────────────────────────────────────────────────────────
--  1. users — пользователи системы
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id         SERIAL       PRIMARY KEY,
    username   VARCHAR(80)  NOT NULL UNIQUE,
    pwd_hash   VARCHAR(255) NOT NULL,
    role       VARCHAR(20)  NOT NULL DEFAULT 'teacher',  -- admin / teacher
    full_name  VARCHAR(200),
    created_at TIMESTAMP    DEFAULT NOW(),
    last_login TIMESTAMP
);

COMMENT ON TABLE  users          IS 'Пользователи системы (администраторы и преподаватели)';
COMMENT ON COLUMN users.role     IS 'Роль: admin или teacher';
COMMENT ON COLUMN users.pwd_hash IS 'Хэш пароля (Werkzeug generate_password_hash)';


-- ─────────────────────────────────────────────────────────────
--  2. groups — учебные группы
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS groups (
    id        SERIAL       PRIMARY KEY,
    name      VARCHAR(100) NOT NULL UNIQUE,
    course    SMALLINT,
    faculty   VARCHAR(200),
    specialty VARCHAR(200)
);

COMMENT ON TABLE groups IS 'Учебные группы';


-- ─────────────────────────────────────────────────────────────
--  3. subjects — учебные дисциплины
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS subjects (
    id          SERIAL       PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,
    code        VARCHAR(50),
    description TEXT
);

COMMENT ON TABLE subjects IS 'Учебные дисциплины';


-- ─────────────────────────────────────────────────────────────
--  4. students — студенты
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS students (
    id          SERIAL       PRIMARY KEY,
    student_id  VARCHAR(50)  NOT NULL UNIQUE,   -- номер зачётной книжки
    first_name  VARCHAR(100) NOT NULL,
    last_name   VARCHAR(100) NOT NULL,
    middle_name VARCHAR(100),
    group_id    INTEGER      REFERENCES groups(id) ON DELETE SET NULL,
    email       VARCHAR(120),
    status      VARCHAR(20)  NOT NULL DEFAULT 'active',  -- active / expelled
    created_at  TIMESTAMP    DEFAULT NOW()
);

COMMENT ON TABLE  students            IS 'Студенты';
COMMENT ON COLUMN students.student_id IS 'Номер зачётной книжки';
COMMENT ON COLUMN students.status     IS 'Статус: active или expelled';


-- ─────────────────────────────────────────────────────────────
--  5. student_photos — фотографии и эмбеддинги студентов
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS student_photos (
    id               SERIAL       PRIMARY KEY,
    student_id       INTEGER      NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    filename         VARCHAR(255) NOT NULL,
    file_path        VARCHAR(500) NOT NULL,
    embedding        BYTEA,           -- numpy float32[512], pickle.dumps()
    model_name       VARCHAR(50),     -- 'ArcFace'
    detector_backend VARCHAR(50),     -- 'retinaface'
    is_primary       BOOLEAN      NOT NULL DEFAULT FALSE,
    uploaded_at      TIMESTAMP    DEFAULT NOW()
);

COMMENT ON TABLE  student_photos           IS 'Фотографии студентов и эмбеддинги ArcFace';
COMMENT ON COLUMN student_photos.embedding IS 'Эмбеддинг лица: numpy float32[512], сериализован через pickle.dumps()';


-- ─────────────────────────────────────────────────────────────
--  6. lessons — занятия
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS lessons (
    id                 SERIAL    PRIMARY KEY,
    subject_id         INTEGER   NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    group_id           INTEGER   NOT NULL REFERENCES groups(id)   ON DELETE CASCADE,
    teacher_id         INTEGER   REFERENCES users(id) ON DELETE SET NULL,
    lesson_number      SMALLINT  NOT NULL,
    topic              VARCHAR(300),
    lesson_date        DATE      NOT NULL,
    time_start         VARCHAR(5),       -- 'HH:MM', например '08:20'
    time_end           VARCHAR(5),       -- 'HH:MM', например '09:50'
    classroom          VARCHAR(50),
    is_locked          BOOLEAN   NOT NULL DEFAULT FALSE,
    unrecognized_count INTEGER   NOT NULL DEFAULT 0,
    created_at         TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE  lessons                    IS 'Занятия';
COMMENT ON COLUMN lessons.is_locked          IS 'TRUE — журнал сохранён преподавателем, редактирование закрыто';
COMMENT ON COLUMN lessons.unrecognized_count IS 'Количество лиц, не идентифицированных ArcFace на фото занятия';


-- ─────────────────────────────────────────────────────────────
--  7. attendance — журнал посещаемости
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS attendance (
    id          SERIAL    PRIMARY KEY,
    lesson_id   INTEGER   NOT NULL REFERENCES lessons(id)  ON DELETE CASCADE,
    student_id  INTEGER   NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    status      VARCHAR(20) NOT NULL,  -- present / manual / absent
    confidence  REAL,                  -- уверенность ArcFace, 0..1
    distance    REAL,                  -- косинусное расстояние в пространстве эмбеддингов
    recorded_at TIMESTAMP DEFAULT NOW(),

    -- Один студент — одна запись на занятие
    CONSTRAINT uq_attendance_lesson_student UNIQUE (lesson_id, student_id)
);

COMMENT ON TABLE  attendance            IS 'Записи посещаемости студентов';
COMMENT ON COLUMN attendance.status     IS 'present — распознан, manual — отмечен вручную, absent — отсутствует';
COMMENT ON COLUMN attendance.confidence IS 'Уверенность идентификации: 1 - cosine_distance';


-- ─────────────────────────────────────────────────────────────
--  Индексы для ускорения частых запросов
-- ─────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_students_group_id
    ON students(group_id);

CREATE INDEX IF NOT EXISTS idx_lessons_group_id
    ON lessons(group_id);

CREATE INDEX IF NOT EXISTS idx_lessons_date
    ON lessons(lesson_date DESC);

CREATE INDEX IF NOT EXISTS idx_attendance_lesson_id
    ON attendance(lesson_id);

CREATE INDEX IF NOT EXISTS idx_attendance_student_id
    ON attendance(student_id);

CREATE INDEX IF NOT EXISTS idx_student_photos_student_id
    ON student_photos(student_id);


-- ─────────────────────────────────────────────────────────────
--  Создание первого администратора (пароль: admin123)
--  Хэш сгенерирован через werkzeug.security.generate_password_hash
--  ЗАМЕНИТЕ на собственный хэш перед использованием!
-- ─────────────────────────────────────────────────────────────
INSERT INTO users (username, pwd_hash, role, full_name)
VALUES (
    'admin',
    'pbkdf2:sha256:600000$placeholder$change_this_hash',
    'admin',
    'Администратор системы'
)
ON CONFLICT (username) DO NOTHING;
