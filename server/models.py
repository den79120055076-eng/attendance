"""
models.py — ORM-модели SQLAlchemy.

Совместимы с PostgreSQL (и SQLite для разработки).
Ключевые отличия от SQLite-версии:
  - LargeBinary → хранится как BYTEA в PostgreSQL (автоматически через SQLAlchemy)
  - Integer autoincrement → SERIAL в PostgreSQL (автоматически)
  - Boolean → BOOLEAN в PostgreSQL (автоматически)
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


# ─────────────────────────────────────────────────────────────
#  users — пользователи системы (администраторы и преподаватели)
# ─────────────────────────────────────────────────────────────
class User(db.Model):
    __tablename__ = "users"

    id         = db.Column(db.Integer, primary_key=True)
    username   = db.Column(db.String(80),  nullable=False, unique=True)
    pwd_hash   = db.Column(db.String(255), nullable=False)
    role       = db.Column(db.String(20),  nullable=False, default="teacher")  # admin / teacher
    full_name  = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    # Связь: один пользователь → много занятий (как преподаватель)
    lessons = db.relationship("Lesson", backref="teacher", lazy=True,
                               foreign_keys="Lesson.teacher_id")

    def to_dict(self):
        return {
            "id":         self.id,
            "username":   self.username,
            "role":       self.role,
            "full_name":  self.full_name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
        }


# ─────────────────────────────────────────────────────────────
#  groups — учебные группы
# ─────────────────────────────────────────────────────────────
class Group(db.Model):
    __tablename__ = "groups"

    id        = db.Column(db.Integer, primary_key=True)
    name      = db.Column(db.String(100), nullable=False, unique=True)
    course    = db.Column(db.Integer)
    faculty   = db.Column(db.String(200))
    specialty = db.Column(db.String(200))

    # Связи
    students = db.relationship("Student", backref="group", lazy=True)
    lessons  = db.relationship("Lesson",  backref="group", lazy=True,
                                foreign_keys="Lesson.group_id")

    def to_dict(self):
        return {
            "id":        self.id,
            "name":      self.name,
            "course":    self.course,
            "faculty":   self.faculty,
            "specialty": self.specialty,
        }


# ─────────────────────────────────────────────────────────────
#  subjects — учебные дисциплины
# ─────────────────────────────────────────────────────────────
class Subject(db.Model):
    __tablename__ = "subjects"

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(200), nullable=False)
    code        = db.Column(db.String(50))
    description = db.Column(db.Text)

    # Связь
    lessons = db.relationship("Lesson", backref="subject", lazy=True)

    def to_dict(self):
        return {
            "id":          self.id,
            "name":        self.name,
            "code":        self.code,
            "description": self.description,
        }


# ─────────────────────────────────────────────────────────────
#  students — студенты
# ─────────────────────────────────────────────────────────────
class Student(db.Model):
    __tablename__ = "students"

    id          = db.Column(db.Integer, primary_key=True)
    student_id  = db.Column(db.String(50),  nullable=False, unique=True)  # номер зачётки
    first_name  = db.Column(db.String(100), nullable=False)
    last_name   = db.Column(db.String(100), nullable=False)
    middle_name = db.Column(db.String(100))
    group_id    = db.Column(db.Integer, db.ForeignKey("groups.id",   ondelete="SET NULL"), nullable=True)
    email       = db.Column(db.String(120))
    status      = db.Column(db.String(20), default="active")  # active / expelled
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    # Связи
    photos     = db.relationship("StudentPhoto", backref="student", lazy=True,
                                  cascade="all, delete-orphan")
    attendance = db.relationship("Attendance", backref="student", lazy=True)

    @property
    def full_name(self):
        parts = [self.last_name, self.first_name]
        if self.middle_name:
            parts.append(self.middle_name)
        return " ".join(p for p in parts if p)

    def to_dict(self):
        return {
            "id":           self.id,
            "student_id":   self.student_id,
            "first_name":   self.first_name,
            "last_name":    self.last_name,
            "middle_name":  self.middle_name,
            "full_name":    self.full_name,
            "group_id":     self.group_id,
            "group_name":   self.group.name if self.group else None,
            "email":        self.email,
            "status":       self.status,
            "photos_count": len(self.photos),
        }


# ─────────────────────────────────────────────────────────────
#  student_photos — фотографии и эмбеддинги студентов
# ─────────────────────────────────────────────────────────────
class StudentPhoto(db.Model):
    __tablename__ = "student_photos"

    id               = db.Column(db.Integer, primary_key=True)
    student_id       = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    filename         = db.Column(db.String(255), nullable=False)
    file_path        = db.Column(db.String(500), nullable=False)
    # LargeBinary → BYTEA в PostgreSQL (pickle.dumps(numpy float32[512]))
    embedding        = db.Column(db.LargeBinary)
    model_name       = db.Column(db.String(50))    # "ArcFace"
    detector_backend = db.Column(db.String(50))    # "retinaface"
    is_primary       = db.Column(db.Boolean, default=False)
    uploaded_at      = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id":               self.id,
            "student_id":       self.student_id,
            "filename":         self.filename,
            "file_path":        self.file_path,
            "has_embedding":    self.embedding is not None,
            "model_name":       self.model_name,
            "detector_backend": self.detector_backend,
            "is_primary":       self.is_primary,
            "uploaded_at":      self.uploaded_at.isoformat() if self.uploaded_at else None,
        }


# ─────────────────────────────────────────────────────────────
#  lessons — занятия
# ─────────────────────────────────────────────────────────────
class Lesson(db.Model):
    __tablename__ = "lessons"

    id                 = db.Column(db.Integer, primary_key=True)
    subject_id         = db.Column(db.Integer, db.ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    group_id           = db.Column(db.Integer, db.ForeignKey("groups.id",   ondelete="CASCADE"), nullable=False)
    teacher_id         = db.Column(db.Integer, db.ForeignKey("users.id",    ondelete="SET NULL"), nullable=True)
    lesson_number      = db.Column(db.Integer, nullable=False)
    topic              = db.Column(db.String(300))
    lesson_date        = db.Column(db.Date, nullable=False)
    time_start         = db.Column(db.String(5))   # "08:20"
    time_end           = db.Column(db.String(5))   # "09:50"
    classroom          = db.Column(db.String(50))
    is_locked          = db.Column(db.Boolean, default=False)
    unrecognized_count = db.Column(db.Integer, default=0)
    created_at         = db.Column(db.DateTime, default=datetime.utcnow)

    # Связи
    attendance = db.relationship("Attendance", backref="lesson", lazy=True,
                                  cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id":                  self.id,
            "subject_id":          self.subject_id,
            "subject_name":        self.subject.name  if self.subject  else None,
            "group_id":            self.group_id,
            "group_name":          self.group.name    if self.group    else None,
            "teacher_id":          self.teacher_id,
            "teacher_name":        self.teacher.full_name if self.teacher else None,
            "lesson_number":       self.lesson_number,
            "topic":               self.topic,
            "lesson_date":         self.lesson_date.isoformat() if self.lesson_date else None,
            "time_start":          self.time_start,
            "time_end":            self.time_end,
            "classroom":           self.classroom,
            "is_locked":           bool(self.is_locked),
            "unrecognized_count":  self.unrecognized_count or 0,
            "attendance_submitted": len(self.attendance) > 0,
        }


# ─────────────────────────────────────────────────────────────
#  attendance — журнал посещаемости
# ─────────────────────────────────────────────────────────────
class Attendance(db.Model):
    __tablename__ = "attendance"

    id          = db.Column(db.Integer, primary_key=True)
    lesson_id   = db.Column(db.Integer, db.ForeignKey("lessons.id",  ondelete="CASCADE"), nullable=False)
    student_id  = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    status      = db.Column(db.String(20), nullable=False)  # present / manual / absent
    confidence  = db.Column(db.Float)   # уверенность ArcFace, 0..1
    distance    = db.Column(db.Float)   # косинусное расстояние в пространстве эмбеддингов
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Уникальность: один студент на одном занятии — одна запись
    __table_args__ = (
        db.UniqueConstraint("lesson_id", "student_id", name="uq_attendance_lesson_student"),
    )

    def to_dict(self):
        return {
            "id":          self.id,
            "lesson_id":   self.lesson_id,
            "student_id":  self.student_id,
            "full_name":   self.student.full_name if self.student else None,
            "status":      self.status,
            "confidence":  round(self.confidence, 4) if self.confidence else None,
            "distance":    round(self.distance,   4) if self.distance   else None,
            "recorded_at": self.recorded_at.isoformat() if self.recorded_at else None,
        }
