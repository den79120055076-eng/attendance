"""
models.py

Модели базы данных системы учёта посещаемости студентов.
Используется SQLAlchemy ORM с базой данных SQLite.
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


def _dt(value):
    """Преобразует datetime в ISO-строку или возвращает None."""
    return value.isoformat() if value else None


class User(db.Model):
    """
    Пользователь системы.
    role: 'admin' — полный доступ, 'teacher' — только проведение занятий.
    """
    __tablename__ = 'users'

    id         = db.Column(db.Integer,     primary_key=True)
    username   = db.Column(db.String(80),  unique=True, nullable=False)
    pwd_hash   = db.Column(db.String(255), nullable=False)
    role       = db.Column(db.String(20),  nullable=False)
    full_name  = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    def set_password(self, raw):
        """Хэширует пароль и сохраняет в pwd_hash. Пароль не хранится в открытом виде."""
        self.pwd_hash = generate_password_hash(raw)

    def check_password(self, raw):
        """Проверяет совпадение введённого пароля с сохранённым хэшем."""
        return check_password_hash(self.pwd_hash, raw)

    def to_dict(self):
        return {
            'id':         self.id,
            'username':   self.username,
            'role':       self.role,
            'full_name':  self.full_name,
            'created_at': _dt(self.created_at),
            'last_login': _dt(self.last_login),
        }


class Group(db.Model):
    """Учебная группа студентов."""
    __tablename__ = 'groups'

    id        = db.Column(db.Integer,    primary_key=True)
    name      = db.Column(db.String(50), unique=True, nullable=False)
    course    = db.Column(db.Integer)
    faculty   = db.Column(db.String(150))
    specialty = db.Column(db.String(200))

    students = db.relationship('Student', backref='group', lazy=True)
    lessons  = db.relationship('Lesson',  backref='group', lazy=True)

    def to_dict(self):
        return {
            'id':            self.id,
            'name':          self.name,
            'course':        self.course,
            'faculty':       self.faculty,
            'specialty':     self.specialty,
            'student_count': len(self.students),
        }


class Subject(db.Model):
    """Учебная дисциплина."""
    __tablename__ = 'subjects'

    id          = db.Column(db.Integer,     primary_key=True)
    name        = db.Column(db.String(200), nullable=False)
    code        = db.Column(db.String(30))
    description = db.Column(db.Text)

    lessons = db.relationship('Lesson', backref='subject', lazy=True)

    def to_dict(self):
        return {
            'id':          self.id,
            'name':        self.name,
            'code':        self.code,
            'description': self.description,
        }


class Lesson(db.Model):
    """
    Конкретное занятие: предмет + группа + дата + время.

    is_locked: если True — журнал окончательно сохранён преподавателем
    и дальнейшее добавление снимков заблокировано. Значение хранится
    в базе данных и не зависит от браузера или устройства.
    """
    __tablename__ = 'lessons'

    id            = db.Column(db.Integer, primary_key=True)
    subject_id    = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    group_id      = db.Column(db.Integer, db.ForeignKey('groups.id'),   nullable=False)
    teacher_id    = db.Column(db.Integer, db.ForeignKey('users.id'),    nullable=True)
    lesson_number = db.Column(db.Integer, nullable=False)
    topic         = db.Column(db.String(300))
    lesson_date   = db.Column(db.Date,    nullable=False)
    time_start    = db.Column(db.String(5))
    time_end      = db.Column(db.String(5))
    classroom     = db.Column(db.String(50))
    is_locked          = db.Column(db.Boolean, default=False, nullable=False)
    unrecognized_count = db.Column(db.Integer, default=0,     nullable=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    teacher    = db.relationship('User', backref='lessons')
    attendance = db.relationship(
        'Attendance', backref='lesson',
        lazy=True, cascade='all, delete-orphan'
    )

    def to_dict(self):
        return {
            'id':                   self.id,
            'subject_id':           self.subject_id,
            'subject_name':         self.subject.name if self.subject else None,
            'subject_code':         self.subject.code if self.subject else None,
            'group_id':             self.group_id,
            'group_name':           self.group.name   if self.group   else None,
            'teacher_id':           self.teacher_id,
            'teacher_name':         self.teacher.full_name if self.teacher else None,
            'lesson_number':        self.lesson_number,
            'topic':                self.topic,
            'lesson_date':          self.lesson_date.isoformat() if self.lesson_date else None,
            'time_start':           self.time_start,
            'time_end':             self.time_end,
            'classroom':            self.classroom,
            'is_locked':            bool(self.is_locked),
            'unrecognized_count':   self.unrecognized_count or 0,
            'attendance_submitted': len(self.attendance) > 0,
        }


class Student(db.Model):
    """Студент. Может иметь несколько фотографий для повышения точности распознавания."""
    __tablename__ = 'students'

    id          = db.Column(db.Integer,    primary_key=True)
    student_id  = db.Column(db.String(50), unique=True, nullable=False)
    first_name  = db.Column(db.String(100), nullable=False)
    last_name   = db.Column(db.String(100), nullable=False)
    middle_name = db.Column(db.String(100))
    group_id    = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=True)
    email       = db.Column(db.String(120))
    status      = db.Column(db.String(20), default='active')
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    photos             = db.relationship(
        'StudentPhoto', backref='student',
        lazy=True, cascade='all, delete-orphan'
    )
    attendance_records = db.relationship('Attendance', backref='student', lazy=True)

    @property
    def full_name(self):
        """ФИО в формате «Фамилия Имя Отчество»."""
        parts = [self.last_name, self.first_name]
        if self.middle_name:
            parts.append(self.middle_name)
        return ' '.join(parts).strip()

    def to_dict(self, with_photos=False):
        result = {
            'id':           self.id,
            'student_id':   self.student_id,
            'first_name':   self.first_name,
            'last_name':    self.last_name,
            'middle_name':  self.middle_name,
            'full_name':    self.full_name,
            'group_id':     self.group_id,
            'group_name':   self.group.name if self.group else None,
            'email':        self.email,
            'status':       self.status,
            'created_at':   _dt(self.created_at),
            'photos_count': len(self.photos),
        }
        if with_photos:
            result['photos'] = [p.to_dict() for p in self.photos]
        return result


class StudentPhoto(db.Model):
    """
    Фотография студента с сохранённым эмбеддингом.

    embedding — numpy-массив 512 float32, сериализованный через pickle.
    Хранится в BLOB SQLite. Размер ≈ 2 КБ на одно фото.
    Сам файл JPEG хранится на диске, в базе только путь к нему.
    """
    __tablename__ = 'student_photos'

    id               = db.Column(db.Integer,     primary_key=True)
    student_id       = db.Column(db.Integer,     db.ForeignKey('students.id'), nullable=False)
    filename         = db.Column(db.String(255), nullable=False)
    file_path        = db.Column(db.String(500), nullable=False)
    embedding        = db.Column(db.LargeBinary)
    model_name       = db.Column(db.String(50))
    detector_backend = db.Column(db.String(50))
    is_primary       = db.Column(db.Boolean, default=False)
    uploaded_at      = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':          self.id,
            'student_id':  self.student_id,
            'filename':    self.filename,
            'is_primary':  self.is_primary,
            'model_name':  self.model_name,
            'uploaded_at': _dt(self.uploaded_at),
            'url':         f'/api/photo/{self.student_id}/{self.filename}',
        }


class Attendance(db.Model):
    """
    Запись посещаемости одного студента на одном занятии.

    status:
        present — распознан системой автоматически
        manual  — преподаватель отметил вручную
        absent  — не присутствовал
    """
    __tablename__ = 'attendance'

    id          = db.Column(db.Integer,    primary_key=True)
    lesson_id   = db.Column(db.Integer,    db.ForeignKey('lessons.id'),  nullable=False)
    student_id  = db.Column(db.Integer,    db.ForeignKey('students.id'), nullable=False)
    status      = db.Column(db.String(20), nullable=False)
    confidence  = db.Column(db.Float)
    distance    = db.Column(db.Float)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':          self.id,
            'lesson_id':   self.lesson_id,
            'student_id':  self.student_id,
            'full_name':   self.student.full_name  if self.student else None,
            'student_num': self.student.student_id if self.student else None,
            'group_name':  (self.student.group.name
                            if self.student and self.student.group else None),
            'status':      self.status,
            'confidence':  self.confidence,
            'distance':    self.distance,
            'recorded_at': _dt(self.recorded_at),
        }
