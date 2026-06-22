"""
app.py — Flask-приложение системы учёта посещаемости.
СУБД: PostgreSQL (через psycopg2 + Flask-SQLAlchemy).
"""
import time

import os
import uuid
import pickle
import threading
import tempfile
from datetime import datetime
from pathlib import Path

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required,
    get_jwt_identity, get_jwt,
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from PIL import Image
import numpy as np

from models import db, User, Group, Subject, Student, StudentPhoto, Lesson, Attendance

# ─────────────────────────────────────────────────────────────
#  Загрузка переменных окружения из .env
# ─────────────────────────────────────────────────────────────
load_dotenv()

# ─────────────────────────────────────────────────────────────
#  Конфигурация приложения
# ─────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
UPLOAD_DIR  = BASE_DIR / "uploads"
TEMP_DIR    = BASE_DIR / "temp"
UPLOAD_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)

MAX_PHOTOS = 5   # максимум фото на студента

# ─── Строка подключения к PostgreSQL ─────────────────────────
DB_HOST = os.getenv("DB_HOST",     "localhost")
DB_PORT = os.getenv("DB_PORT",     "5432")
DB_NAME = os.getenv("DB_NAME",     "attendance")
DB_USER = os.getenv("DB_USER",     "attendance_user")
DB_PASS = os.getenv("DB_PASSWORD", "")

DATABASE_URL = (
    os.getenv("DATABASE_URL")          # если задана явно — берём её
    or f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

# ─────────────────────────────────────────────────────────────
#  Создание Flask-приложения
# ─────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder=str(BASE_DIR.parent / "web"))
CORS(app)

app.config["SQLALCHEMY_DATABASE_URI"]        = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
# PostgreSQL: можно использовать connection pool
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_size":    5,
    "max_overflow": 10,
    "pool_timeout": 30,
    "pool_recycle": 1800,   # переподключение каждые 30 минут
}
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "dev-secret-change-me")
# Токен без срока действия — удобно для демонстрации/защиты диплома.
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = False
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024   # 50 МБ

db.init_app(app)
jwt = JWTManager(app)
flask_app = app   # ссылка для фоновых потоков


# ─────────────────────────────────────────────────────────────
#  Хранилище фоновых задач распознавания
# ─────────────────────────────────────────────────────────────
_jobs: dict = {}
_jobs_lock  = threading.Lock()


# ─────────────────────────────────────────────────────────────
#  Вспомогательные функции
# ─────────────────────────────────────────────────────────────
def admin_only():
    """Возвращает ошибку 403, если текущий пользователь не администратор."""
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"error": "Доступ запрещён"}), 403
    return None


def _save_photo(student_id: int, file) -> StudentPhoto:
    """Сохраняет файл фото, вычисляет эмбеддинг ArcFace и создаёт запись в БД."""
    from deepface import DeepFace

    student_dir = UPLOAD_DIR / str(student_id)
    student_dir.mkdir(exist_ok=True)

    filename = secure_filename(f"{uuid.uuid4().hex}.jpg")
    filepath = student_dir / filename

    # Конвертируем в JPEG и сохраняем
    img = Image.open(file.stream).convert("RGB")
    img.save(str(filepath), "JPEG", quality=92)

    # Вычисляем эмбеддинг
    embedding_blob = None
    try:
        results = DeepFace.represent(
            img_path=str(filepath),
            model_name="ArcFace",
            detector_backend="retinaface",
            enforce_detection=False,
        )
        if results:
            emb_array   = np.array(results[0]["embedding"], dtype=np.float32)
            embedding_blob = pickle.dumps(emb_array)
    except Exception as e:
        app.logger.warning(f"Не удалось вычислить эмбеддинг: {e}")

    photo = StudentPhoto(
        student_id=student_id,
        filename=filename,
        file_path=str(filepath),
        embedding=embedding_blob,
        model_name="ArcFace",
        detector_backend="retinaface",
    )
    db.session.add(photo)
    db.session.flush()   # получаем id до commit
    return photo


def find_best_match(embedding: np.ndarray, candidates: list, threshold: float = 0.4):
    """
    Поиск ближайшего студента по косинусному расстоянию.
    threshold: максимальное допустимое расстояние (чем меньше — тем строже).
    """
    best_dist = float("inf")
    best_sid  = None
    for student_id, ref_emb in candidates:
        dot  = np.dot(embedding, ref_emb)
        norm = np.linalg.norm(embedding) * np.linalg.norm(ref_emb) + 1e-10
        dist = 1.0 - dot / norm
        if dist < best_dist:
            best_dist = dist
            best_sid  = student_id
    if best_dist <= threshold:
        return {"matched": True, "student_id": best_sid,
                "distance": float(best_dist), "confidence": float(1 - best_dist)}
    return {"matched": False}


# ─────────────────────────────────────────────────────────────
#  Фоновая задача распознавания лиц
# ─────────────────────────────────────────────────────────────
def _run_recognition(flask_app, job_id: str, lesson_id: int, temp_paths: list):
    """Выполняется в отдельном потоке. Результат пишет в _jobs[job_id]."""
    _t_start = time.perf_counter()
    from deepface import DeepFace

    with flask_app.app_context():
        try:
            lesson = Lesson.query.get(lesson_id)
            if not lesson:
                raise ValueError(f"Занятие {lesson_id} не найдено")

            # 1. Загружаем эталонные эмбеддинги студентов группы
            photos = (StudentPhoto.query
                      .join(Student)
                      .filter(
                          Student.group_id == lesson.group_id,
                          Student.status   == "active",
                          StudentPhoto.embedding  != None,
                          StudentPhoto.model_name == "ArcFace",
                      ).all())

            candidates = []
            for ph in photos:
                try:
                    emb = np.array(pickle.loads(ph.embedding), dtype=np.float32)
                    candidates.append((ph.student_id, emb))
                except Exception:
                    pass

            # 2. Обрабатываем каждое фото занятия
            recognized_map: dict = {}   # student_id → best match
            unrecognized_count = 0

            for tmp_path in temp_paths:
                try:
                    results = DeepFace.represent(
                        img_path=tmp_path,
                        model_name="ArcFace",
                        detector_backend="retinaface",
                        enforce_detection=False,
                    )
                    for r in results:
                        emb   = np.array(r["embedding"], dtype=np.float32)
                        match = find_best_match(emb, candidates)
                        if match["matched"]:
                            sid = match["student_id"]
                            # Сохраняем лучший результат (наименьшее расстояние)
                            if sid not in recognized_map or \
                               match["distance"] < recognized_map[sid]["distance"]:
                                recognized_map[sid] = match
                        else:
                            unrecognized_count += 1
                except Exception as e:
                    app.logger.warning(f"Ошибка обработки фото {tmp_path}: {e}")

            # 3. Формируем итоговые списки
            all_students = (Student.query
                            .filter_by(group_id=lesson.group_id, status="active")
                            .order_by(Student.last_name)
                            .all())

            recognized = []
            absent     = []
            for s in all_students:
                if s.id in recognized_map:
                    recognized.append({
                        "id":         s.id,
                        "full_name":  s.full_name,
                        "confidence": recognized_map[s.id]["confidence"],
                        "distance":   recognized_map[s.id]["distance"],
                    })
                else:
                    absent.append({"id": s.id, "full_name": s.full_name})

            # 4. Сохраняем счётчик нераспознанных
            lesson.unrecognized_count = unrecognized_count
            db.session.commit()

            _elapsed = time.perf_counter() - _t_start
            total_faces = len(recognized) + unrecognized_count
            print(f"[RECOGNITION] фото={len(temp_paths)} "
                  f"лиц_найдено={total_faces} "
                  f"время={_elapsed:.2f} сек "
                  f"({_elapsed/max(total_faces,1):.2f} сек/лицо)", flush=True)

            with _jobs_lock:
                _jobs[job_id] = {
                    "status": "done",
                    "result": {
                        "recognized":         recognized,
                        "absent":             absent,
                        "unrecognized_count": unrecognized_count,
                        "photos_processed":   len(temp_paths),
                        "processing_time_sec": round(_elapsed, 2),
                    },
                }
        except Exception as e:
            import traceback
            print("=" * 60)
            print("ОШИБКА В _run_recognition:")
            traceback.print_exc()
            print("=" * 60)
            with _jobs_lock:
                _jobs[job_id] = {"status": "error", "error": str(e)}
        finally:
            for p in temp_paths:
                try:
                    os.remove(p)
                except Exception:
                    pass


# ═════════════════════════════════════════════════════════════
#  МАРШРУТЫ REST API
# ═════════════════════════════════════════════════════════════

# ─── Статические файлы ────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(app.static_folder, filename)


# ─── Авторизация ──────────────────────────────────────────────
@app.route("/api/auth/login", methods=["POST"])
def login():
    data     = request.get_json()
    username = data.get("username", "").strip()
    password = data.get("password", "")
    user = User.query.filter_by(username=username).first()
    if not user or not check_password_hash(user.pwd_hash, password):
        return jsonify({"error": "Неверный логин или пароль"}), 401
    user.last_login = datetime.utcnow()
    db.session.commit()
    token = create_access_token(
        identity=str(user.id),
        additional_claims={"role": user.role, "full_name": user.full_name}
    )
    return jsonify({"access_token": token, "role": user.role, "full_name": user.full_name})


# ─── Пользователи ─────────────────────────────────────────────
@app.route("/api/users", methods=["GET"])
@jwt_required()
def get_users():
    err = admin_only()
    if err: return err
    return jsonify([u.to_dict() for u in User.query.order_by(User.username).all()])

@app.route("/api/users", methods=["POST"])
@jwt_required()
def create_user():
    err = admin_only()
    if err: return err
    d = request.get_json()
    if User.query.filter_by(username=d["username"]).first():
        return jsonify({"error": "Логин уже занят"}), 409
    user = User(
        username=d["username"],
        pwd_hash=generate_password_hash(d["password"]),
        role=d.get("role", "teacher"),
        full_name=d.get("full_name", ""),
    )
    db.session.add(user)
    db.session.commit()
    return jsonify(user.to_dict()), 201

@app.route("/api/users/<int:uid>", methods=["PUT"])
@jwt_required()
def update_user(uid):
    err = admin_only()
    if err: return err
    user = User.query.get_or_404(uid)
    d    = request.get_json()
    if "full_name" in d: user.full_name = d["full_name"]
    if "role"      in d: user.role      = d["role"]
    if "password"  in d and d["password"]:
        user.pwd_hash = generate_password_hash(d["password"])
    db.session.commit()
    return jsonify(user.to_dict())

@app.route("/api/users/<int:uid>", methods=["DELETE"])
@jwt_required()
def delete_user(uid):
    err = admin_only()
    if err: return err
    db.session.delete(User.query.get_or_404(uid))
    db.session.commit()
    return jsonify({"ok": True})


# ─── Группы ───────────────────────────────────────────────────
@app.route("/api/groups", methods=["GET"])
@jwt_required()
def get_groups():
    return jsonify([g.to_dict() for g in Group.query.order_by(Group.name).all()])

@app.route("/api/groups", methods=["POST"])
@jwt_required()
def create_group():
    d = request.get_json()
    g = Group(**{k: d.get(k) for k in ("name","course","faculty","specialty")})
    db.session.add(g)
    db.session.commit()
    return jsonify(g.to_dict()), 201

@app.route("/api/groups/<int:gid>", methods=["PUT"])
@jwt_required()
def update_group(gid):
    g = Group.query.get_or_404(gid)
    d = request.get_json()
    for k in ("name","course","faculty","specialty"):
        if k in d: setattr(g, k, d[k])
    db.session.commit()
    return jsonify(g.to_dict())

@app.route("/api/groups/<int:gid>", methods=["DELETE"])
@jwt_required()
def delete_group(gid):
    db.session.delete(Group.query.get_or_404(gid))
    db.session.commit()
    return jsonify({"ok": True})


# ─── Дисциплины ───────────────────────────────────────────────
@app.route("/api/subjects", methods=["GET"])
@jwt_required()
def get_subjects():
    return jsonify([s.to_dict() for s in Subject.query.order_by(Subject.name).all()])

@app.route("/api/subjects", methods=["POST"])
@jwt_required()
def create_subject():
    d = request.get_json()
    s = Subject(**{k: d.get(k) for k in ("name","code","description")})
    db.session.add(s)
    db.session.commit()
    return jsonify(s.to_dict()), 201

@app.route("/api/subjects/<int:sid>", methods=["PUT"])
@jwt_required()
def update_subject(sid):
    s = Subject.query.get_or_404(sid)
    d = request.get_json()
    for k in ("name","code","description"):
        if k in d: setattr(s, k, d[k])
    db.session.commit()
    return jsonify(s.to_dict())

@app.route("/api/subjects/<int:sid>", methods=["DELETE"])
@jwt_required()
def delete_subject(sid):
    db.session.delete(Subject.query.get_or_404(sid))
    db.session.commit()
    return jsonify({"ok": True})


# ─── Студенты ─────────────────────────────────────────────────
@app.route("/api/students", methods=["GET"])
@jwt_required()
def get_students():
    q = Student.query
    if gid := request.args.get("group_id"):
        q = q.filter_by(group_id=int(gid))
    if search := request.args.get("search"):
        like = f"%{search}%"
        q = q.filter(
            (Student.last_name.ilike(like)) |
            (Student.first_name.ilike(like)) |
            (Student.student_id.ilike(like))
        )
    students = q.order_by(Student.last_name, Student.first_name).all()
    return jsonify([s.to_dict() for s in students])

@app.route("/api/students/<int:sid>", methods=["GET"])
@jwt_required()
def get_student(sid):
    s = Student.query.get_or_404(sid)
    d = s.to_dict()
    d["photos"] = [p.to_dict() for p in s.photos]
    return jsonify(d)

@app.route("/api/students", methods=["POST"])
@jwt_required()
def create_student():
    # Поддержка как JSON, так и multipart/form-data (с фото)
    if request.content_type and "multipart" in request.content_type:
        data = request.form
    else:
        data = request.get_json()

    s = Student(
        student_id=data.get("student_id"),
        first_name=data.get("first_name"),
        last_name=data.get("last_name"),
        middle_name=data.get("middle_name"),
        group_id=int(data["group_id"]) if data.get("group_id") else None,
        email=data.get("email"),
        status=data.get("status", "active"),
    )
    db.session.add(s)
    db.session.flush()

    # Загрузка фото (если переданы)
    for file in request.files.getlist("photos"):
        if file and file.filename:
            _save_photo(s.id, file)

    db.session.commit()
    return jsonify(s.to_dict()), 201

@app.route("/api/students/<int:sid>", methods=["PUT"])
@jwt_required()
def update_student(sid):
    s    = Student.query.get_or_404(sid)
    data = request.get_json() or request.form
    for k in ("first_name","last_name","middle_name","email","status"):
        if k in data: setattr(s, k, data[k])
    if "group_id" in data:
        s.group_id = int(data["group_id"]) if data["group_id"] else None
    db.session.commit()
    return jsonify(s.to_dict())

@app.route("/api/students/<int:sid>", methods=["DELETE"])
@jwt_required()
def delete_student(sid):
    db.session.delete(Student.query.get_or_404(sid))
    db.session.commit()
    return jsonify({"ok": True})

@app.route("/api/students/<int:sid>/photos", methods=["POST"])
@jwt_required()
def add_photo(sid):
    Student.query.get_or_404(sid)
    count = StudentPhoto.query.filter_by(student_id=sid).count()
    if count >= MAX_PHOTOS:
        return jsonify({"error": f"Максимум {MAX_PHOTOS} фото на студента"}), 400
    file = request.files.get("photo")
    if not file:
        return jsonify({"error": "Файл не передан"}), 400
    photo = _save_photo(sid, file)
    db.session.commit()
    return jsonify(photo.to_dict()), 201

@app.route("/api/photos/<int:pid>/file", methods=["GET"])
def get_photo_file(pid):
    """Отдаёт файл фотографии студента по ID записи StudentPhoto."""
    from flask import send_file
    photo = StudentPhoto.query.get_or_404(pid)
    if not os.path.exists(photo.file_path):
        return jsonify({"error": "Файл не найден"}), 404
    return send_file(photo.file_path, mimetype="image/jpeg")


@app.route("/api/photos/<int:pid>", methods=["DELETE"])
@jwt_required()
def delete_photo(pid):
    photo = StudentPhoto.query.get_or_404(pid)
    try:
        os.remove(photo.file_path)
    except Exception:
        pass
    db.session.delete(photo)
    db.session.commit()
    return jsonify({"ok": True})


# ─── Занятия ──────────────────────────────────────────────────
@app.route("/api/lessons", methods=["GET"])
@jwt_required()
def get_lessons():
    q = Lesson.query
    if gid := request.args.get("group_id"):
        q = q.filter_by(group_id=int(gid))
    claims = get_jwt()
    if claims.get("role") == "teacher":
        uid = int(get_jwt_identity())
        q = q.filter_by(teacher_id=uid)
    lessons = q.order_by(Lesson.lesson_date.desc()).all()
    return jsonify([l.to_dict() for l in lessons])

@app.route("/api/lessons/current", methods=["GET"])
@jwt_required()
def get_current_lesson():
    group_id = request.args.get("group_id", type=int)
    if not group_id:
        return jsonify({"error": "group_id обязателен"}), 400

    today = datetime.utcnow().date()
    now_str = datetime.now().strftime("%H:%M")

    # Сначала ищем занятие, которое идёт прямо сейчас
    lesson = (Lesson.query
              .filter_by(group_id=group_id, lesson_date=today)
              .filter(Lesson.time_start <= now_str, Lesson.time_end >= now_str)
              .first())

    # Если сейчас перерыв — берём ближайшее следующее занятие сегодня
    if not lesson:
        lesson = (Lesson.query
                  .filter_by(group_id=group_id, lesson_date=today)
                  .filter(Lesson.time_start >= now_str)
                  .order_by(Lesson.time_start)
                  .first())

    # Если на сегодня больше ничего не предстоит — берём последнее
    # уже прошедшее занятие (например, чтобы отметить сразу после пары)
    if not lesson:
        lesson = (Lesson.query
                  .filter_by(group_id=group_id, lesson_date=today)
                  .filter(Lesson.time_end <= now_str)
                  .order_by(Lesson.time_start.desc())
                  .first())

    if not lesson:
        return jsonify({"error": "Нет ближайшего занятия"}), 404

    return jsonify({"lesson": lesson.to_dict()})


@app.route("/api/lessons", methods=["POST"])
@jwt_required()
def create_lesson():
    d = request.get_json()
    l = Lesson(
        subject_id=int(d["subject_id"]),
        group_id=int(d["group_id"]),
        teacher_id=int(d["teacher_id"]) if d.get("teacher_id") else None,
        lesson_number=int(d.get("lesson_number", 1)),
        topic=d.get("topic"),
        lesson_date=datetime.strptime(d["lesson_date"], "%Y-%m-%d").date(),
        time_start=d.get("time_start"),
        time_end=d.get("time_end"),
        classroom=d.get("classroom"),
    )
    db.session.add(l)
    db.session.commit()
    return jsonify(l.to_dict()), 201

@app.route("/api/lessons/<int:lid>", methods=["PUT"])
@jwt_required()
def update_lesson(lid):
    l = Lesson.query.get_or_404(lid)
    d = request.get_json()
    for k in ("topic","time_start","time_end","classroom","lesson_number"):
        if k in d: setattr(l, k, d[k])
    if "lesson_date" in d:
        l.lesson_date = datetime.strptime(d["lesson_date"], "%Y-%m-%d").date()
    db.session.commit()
    return jsonify(l.to_dict())

@app.route("/api/lessons/<int:lid>", methods=["DELETE"])
@jwt_required()
def delete_lesson(lid):
    db.session.delete(Lesson.query.get_or_404(lid))
    db.session.commit()
    return jsonify({"ok": True})

@app.route("/api/lessons/<int:lid>/lock", methods=["POST"])
@jwt_required()
def lock_lesson(lid):
    lesson = Lesson.query.get_or_404(lid)
    lesson.is_locked = True
    db.session.commit()
    return jsonify({"ok": True, "lesson_id": lid})


# ─── Распознавание лиц ────────────────────────────────────────
@app.route("/api/attendance/recognize", methods=["POST"])
@jwt_required()
def attendance_recognize():
    lesson_id = request.form.get("lesson_id", type=int)
    photos    = request.files.getlist("photos")
    if not lesson_id or not photos:
        return jsonify({"error": "lesson_id и photos обязательны"}), 400

    # Сохраняем фото во временные файлы
    temp_paths = []
    for f in photos:
        if not f or not f.filename:
            continue
        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", dir=str(TEMP_DIR), delete=False)
        tmp.close()
        f.save(tmp.name)
        temp_paths.append(tmp.name)

    if not temp_paths:
        return jsonify({"error": "Нет корректных фотографий"}), 400

    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {"status": "processing"}

    threading.Thread(
        target=_run_recognition,
        args=(flask_app, job_id, lesson_id, temp_paths),
        daemon=True,
    ).start()

    return jsonify({"job_id": job_id, "status": "processing"}), 202

@app.route("/api/attendance/jobs/<job_id>", methods=["GET"])
@jwt_required()
def get_job_status(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id, {"status": "not_found"})
    return jsonify(job)

@app.route("/api/attendance/submit", methods=["POST"])
@jwt_required()
def attendance_submit():
    d          = request.get_json()
    lesson_id  = int(d["lesson_id"])
    present    = set(int(x) for x in d.get("present_ids", []))
    manual     = set(int(x) for x in d.get("manual_ids",  []))
    unrec      = int(d.get("unrecognized_count", 0))

    lesson = Lesson.query.get_or_404(lesson_id)

    # Удаляем старые записи и создаём новые
    Attendance.query.filter_by(lesson_id=lesson_id).delete()

    students = Student.query.filter_by(
        group_id=lesson.group_id, status="active"
    ).all()

    for s in students:
        if s.id in present:
            status = "present"
        elif s.id in manual:
            status = "manual"
        else:
            status = "absent"
        db.session.add(Attendance(
            lesson_id=lesson_id,
            student_id=s.id,
            status=status,
        ))

    lesson.unrecognized_count = unrec
    db.session.commit()

    present_count = sum(1 for s in students if s.id in present or s.id in manual)
    absent_count  = len(students) - present_count
    return jsonify({"ok": True, "lesson_id": lesson_id,
                    "present_count": present_count, "absent_count": absent_count})

@app.route("/api/attendance/lesson/<int:lid>", methods=["GET"])
@jwt_required()
def get_lesson_attendance(lid):
    lesson  = Lesson.query.get_or_404(lid)
    records = Attendance.query.filter_by(lesson_id=lid).all()
    return jsonify({
        "lesson":             lesson.to_dict(),
        "records":            [r.to_dict() for r in records],
        "unrecognized_count": lesson.unrecognized_count or 0,
    })

def _lesson_hours(l):
    """Длительность занятия в часах по time_start/time_end, 1.5 по умолчанию."""
    if not l.time_start or not l.time_end:
        return 1.5
    try:
        t1 = datetime.strptime(l.time_start, "%H:%M")
        t2 = datetime.strptime(l.time_end, "%H:%M")
        return round((t2 - t1).seconds / 3600, 2)
    except Exception:
        return 1.5


@app.route("/api/attendance/report", methods=["GET"])
@jwt_required()
def attendance_report():
    group_id   = request.args.get("group_id", type=int)
    subject_id = request.args.get("subject_id", type=int)
    date_from  = request.args.get("date_from")   # "YYYY-MM-DD", необязательно
    date_to    = request.args.get("date_to")     # "YYYY-MM-DD", необязательно
    if not group_id:
        return jsonify({"error": "group_id обязателен"}), 400

    group   = Group.query.get(group_id)
    subject = Subject.query.get(subject_id) if subject_id else None
    today   = datetime.utcnow().date()

    q = Lesson.query.filter_by(group_id=group_id)
    if subject_id:
        q = q.filter_by(subject_id=subject_id)
    if date_from:
        q = q.filter(Lesson.lesson_date >= datetime.strptime(date_from, "%Y-%m-%d").date())
    if date_to:
        # явно указанная дата "по" учитывается как есть, без ограничения
        # сегодняшним днём — администратор сам решает, какой диапазон считать
        to_date = datetime.strptime(date_to, "%Y-%m-%d").date()
        q = q.filter(Lesson.lesson_date <= to_date)
    else:
        # по умолчанию (если дата "по" не указана явно) учитываем только
        # прошедшие и сегодняшние занятия, чтобы ещё не наступившие пары
        # не занижали процент посещаемости
        q = q.filter(Lesson.lesson_date <= today)

    lessons = q.order_by(Lesson.lesson_date).all()
    total_hours_all = sum(_lesson_hours(l) for l in lessons)

    students = (Student.query
                .filter_by(group_id=group_id, status="active")
                .order_by(Student.last_name)
                .all())

    report = []
    for s in students:
        attended = 0
        attended_hours = 0.0
        for l in lessons:
            rec = Attendance.query.filter_by(lesson_id=l.id, student_id=s.id).first()
            if rec and rec.status in ("present", "manual"):
                attended += 1
                attended_hours += _lesson_hours(l)
        total   = len(lessons)
        percent = round(attended / total * 100, 1) if total else 0
        report.append({
            "student_id":     s.student_id,
            "full_name":      s.full_name,
            "attended":       attended,
            "total":          total,
            "percentage":     percent,
            "attended_hours": round(attended_hours, 1),
        })

    return jsonify({
        "group":       {"id": group.id, "name": group.name} if group else None,
        "subject":     {"id": subject.id, "name": subject.name} if subject else None,
        "date_from":   date_from,
        "date_to":     date_to,
        "lessons":     [l.to_dict() for l in lessons],
        "total_hours": round(total_hours_all, 1),
        "students":    report,
    })


@app.route("/api/attendance/summary", methods=["GET"])
@jwt_required()
def attendance_summary():
    claims = get_jwt()
    q = Lesson.query
    if claims.get("role") == "teacher":
        q = q.filter_by(teacher_id=int(get_jwt_identity()))
    lessons = q.order_by(Lesson.lesson_date.desc()).all()
    result  = []
    for l in lessons:
        present = sum(1 for a in l.attendance if a.status in ("present", "manual"))
        absent  = len(l.attendance) - present
        d       = l.to_dict()
        d.update({"present_count": present, "absent_count": absent})
        result.append(d)
    return jsonify(result)


# ─────────────────────────────────────────────────────────────
#  Запуск приложения
# ─────────────────────────────────────────────────────────────
def _warmup_model():
    """
    Прогрев модели распознавания: загружает веса ArcFace и RetinaFace
    в оперативную память сразу при старте сервера, на одном "пустом"
    изображении. Без этого первый реальный запрос пользователя ждал бы
    несколько секунд (инициализация TensorFlow и весов нейросети).
    """
    import numpy as np
    from PIL import Image
    from deepface import DeepFace
    print("Прогрев модели распознавания лиц...")
    t0 = time.perf_counter()

    # Создаём временное изображение 224x224 (любой размер подойдёт)
    dummy = Image.fromarray(
        (np.random.rand(224, 224, 3) * 255).astype("uint8")
    )
    dummy_path = str(TEMP_DIR / "_warmup.jpg")
    dummy.save(dummy_path, "JPEG")

    try:
        DeepFace.represent(
            img_path=dummy_path,
            model_name="ArcFace",
            detector_backend="retinaface",
            enforce_detection=False,
        )
    except Exception as e:
        print(f"Прогрев завершился с предупреждением (это нормально): {e}")
    finally:
        import os
        try:
            os.remove(dummy_path)
        except Exception:
            pass

    elapsed = time.perf_counter() - t0
    print(f"Модель загружена в память за {elapsed:.1f} сек. "
          f"Сервер готов к быстрой обработке запросов.")


if __name__ == "__main__":
    with app.app_context():
        db.create_all()   # создаёт таблицы если не существуют

    # Прогрев модели распознавания ДО старта сервера —
    # первый пользовательский запрос будет быстрым
    _warmup_model()

    with app.app_context():
        # Создаём администратора по умолчанию если пользователей нет
        if User.query.count() == 0:
            admin = User(
                username="admin",
                pwd_hash=generate_password_hash("admin123"),
                role="admin",
                full_name="Администратор",
            )
            db.session.add(admin)
            db.session.commit()
            print("Создан администратор по умолчанию: admin / admin123")

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        ssl_context=("cert.pem", "key.pem"),
    )
