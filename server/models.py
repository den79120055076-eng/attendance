"""
models.py

Модели базы данных для системы учёта посещаемости.

Используется SQLAlchemy ORM с базой данных SQLite.
Каждый класс соответствует одной таблице в базе данных.

Схема таблиц:
    User          — пользователи системы (преподаватели и администраторы)
    Group         — учебные группы
    Subject       — учебные дисциплины
    Lesson        — занятие (конкретная пара в конкретный день)
    Student       — студент
    StudentPhoto  — фото студента с векторным представлением лица
    Attendance    — запись посещаемости студента на занятии
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

# Глобальный объект базы данных, подключается к Flask-приложению в app.py
db = SQLAlchemy()


def format_datetime(value):
    """
    Преобразует объект datetime в строку формата ISO 8601.

    Используется во всех методах to_dict() для единообразной
    сериализации дат в JSON-ответах API.

    Параметры:
        value (datetime | None): дата и время

    Возвращает:
        str | None: строка вида '2025-09-01T08:20:00' или None
    """
    if value is None:
        return None
    return value.isoformat()


class User(db.Model):
    """
    Пользователь системы.

    Роли:
        admin   — полный доступ: управление студентами, группами, занятиями
        teacher — ограниченный доступ: только проведение занятий и отметка посещаемости
    """

    __tablename__ = 'users'

    id         = db.Column(db.Integer,     primary_key=True)
    username   = db.Column(db.String(80),  unique=True, nullable=False)
    pwd_hash   = db.Column(db.String(255), nullable=False)
    role       = db.Column(db.String(20),  nullable=False)   # 'admin' или 'teacher'
    full_name  = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    def set_password(self, raw_password):
        """
        Хэширует пароль и сохраняет в поле pwd_hash.

        Пароль никогда не хранится в открытом виде.

        Параметры:
            raw_password (str): пароль в открытом виде
        """
        self.pwd_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        """
        Проверяет, совпадает ли введённый пароль с сохранённым хэшем.

        Параметры:
            raw_password (str): пароль для проверки

        Возвращает:
            bool: True если пароль верный, False иначе
        """
        return check_password_hash(self.pwd_hash, raw_password)

    def to_dict(self):
        """
        Сериализует объект пользователя в словарь для JSON-ответа.

        Поле pwd_hash намеренно исключено из ответа по соображениям безопасности.

        Возвращает:
            dict: поля пользователя без пароля
        """
        return {
            'id':         self.id,
            'username':   self.username,
            'role':       self.role,
            'full_name':  self.full_name,
            'created_at': format_datetime(self.created_at),
            'last_login': format_datetime(self.last_login),
        }


class Group(db.Model):
    """
    Учебная группа студентов.

    Каждый студент принадлежит одной группе.
    Занятия планируются для конкретной группы.
    """

    __tablename__ = 'groups'

    id        = db.Column(db.Integer,    primary_key=True)
    name      = db.Column(db.String(50), unique=True, nullable=False)  # например: ИС-22-1
    course    = db.Column(db.Integer)       # курс обучения: 1, 2, 3, 4
    faculty   = db.Column(db.String(150))
    specialty = db.Column(db.String(200))

    # При обращении group.students возвращается список студентов этой группы
    students = db.relationship('Student', backref='group', lazy=True)
    # При обращении group.lessons возвращается список занятий этой группы
    lessons  = db.relationship('Lesson',  backref='group', lazy=True)

    def to_dict(self):
        """
        Сериализует группу в словарь.

        Поле student_count вычисляется динамически — показывает
        количество активных студентов в группе.

        Возвращает:
            dict: поля группы включая количество студентов
        """
        return {
            'id':            self.id,
            'name':          self.name,
            'course':        self.course,
            'faculty':       self.faculty,
            'specialty':     self.specialty,
            'student_count': len(self.students),
        }


class Subject(db.Model):
    """
    Учебная дисциплина (предмет).

    Предметы могут создаваться вручную или автоматически
    при импорте расписания из Excel-файла.
    """

    __tablename__ = 'subjects'

    id          = db.Column(db.Integer,    primary_key=True)
    name        = db.Column(db.String(200), nullable=False)
    code        = db.Column(db.String(30))   # код дисциплины, например CS401
    description = db.Column(db.Text)

    lessons = db.relationship('Lesson', backref='subject', lazy=True)

    def to_dict(self):
        """
        Сериализует предмет в словарь.

        Возвращает:
            dict: поля предмета
        """
        return {
            'id':          self.id,
            'name':        self.name,
            'code':        self.code,
            'description': self.description,
        }


class Lesson(db.Model):
    """
    Конкретное занятие: определённый предмет, группа, дата и время.

    Посещаемость фиксируется для каждого занятия отдельно.
    После того как преподаватель сохраняет журнал, запись в поле
    attendance становится непустой.
    """

    __tablename__ = 'lessons'

    id            = db.Column(db.Integer, primary_key=True)
    subject_id    = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    group_id      = db.Column(db.Integer, db.ForeignKey('groups.id'),   nullable=False)
    teacher_id    = db.Column(db.Integer, db.ForeignKey('users.id'),    nullable=True)
    lesson_number = db.Column(db.Integer, nullable=False)  # порядковый номер занятия
    topic         = db.Column(db.String(300))              # тема занятия
    lesson_date   = db.Column(db.Date,    nullable=False)
    time_start    = db.Column(db.String(5))   # формат HH:MM
    time_end      = db.Column(db.String(5))
    classroom     = db.Column(db.String(50))
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    teacher    = db.relationship('User',       backref='lessons')
    # cascade='all, delete-orphan' удаляет записи посещаемости при удалении занятия
    attendance = db.relationship(
        'Attendance', backref='lesson',
        lazy=True, cascade='all, delete-orphan'
    )

    def to_dict(self):
        """
        Сериализует занятие в словарь.

        Включает названия связанных объектов (предмет, группа, преподаватель)
        для удобства отображения на фронтенде без дополнительных запросов.

        Возвращает:
            dict: поля занятия с названиями связанных объектов
        """
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
            # True если журнал уже был сохранён для этого занятия
            'attendance_submitted': len(self.attendance) > 0,
        }


class Student(db.Model):
    """
    Студент, зарегистрированный в системе.

    Фотографии хранятся в отдельной таблице StudentPhoto.
    У одного студента может быть несколько фотографий —
    это повышает точность распознавания при разных условиях освещения.
    """

    __tablename__ = 'students'

    id          = db.Column(db.Integer,    primary_key=True)
    student_id  = db.Column(db.String(50), unique=True, nullable=False)  # номер зачётки
    first_name  = db.Column(db.String(100), nullable=False)
    last_name   = db.Column(db.String(100), nullable=False)
    middle_name = db.Column(db.String(100))
    group_id    = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=True)
    email       = db.Column(db.String(120))
    status      = db.Column(db.String(20), default='active')  # 'active' или 'expelled'
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    photos            = db.relationship(
        'StudentPhoto', backref='student',
        lazy=True, cascade='all, delete-orphan'
    )
    attendance_records = db.relationship('Attendance', backref='student', lazy=True)

    @property
    def full_name(self):
        """
        Возвращает полное имя студента в формате «Фамилия Имя Отчество».

        Отчество добавляется только если оно указано в базе.

        Возвращает:
            str: полное имя без лишних пробелов
        """
        parts = [self.last_name, self.first_name]
        if self.middle_name:
            parts.append(self.middle_name)
        return ' '.join(parts).strip()

    def to_dict(self, with_photos=False):
        """
        Сериализует студента в словарь.

        Параметры:
            with_photos (bool): если True — включить список фотографий.
                                Используется при запросе конкретного студента.

        Возвращает:
            dict: поля студента, опционально с фотографиями
        """
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
            'created_at':   format_datetime(self.created_at),
            'photos_count': len(self.photos),
        }
        if with_photos:
            result['photos'] = [photo.to_dict() for photo in self.photos]
        return result


class StudentPhoto(db.Model):
    """
    Фотография студента с сохранённым векторным представлением лица (эмбеддингом).

    Эмбеддинг — массив из 512 чисел, полученный от модели ArcFace.
    Он сохраняется в поле embedding в формате pickle (сериализованный numpy-массив).

    Поле model_name фиксирует, какой моделью был получен эмбеддинг.
    Эмбеддинги разных моделей несовместимы и не сравниваются между собой.
    """

    __tablename__ = 'student_photos'

    id               = db.Column(db.Integer,     primary_key=True)
    student_id       = db.Column(db.Integer,     db.ForeignKey('students.id'), nullable=False)
    filename         = db.Column(db.String(255), nullable=False)
    file_path        = db.Column(db.String(500), nullable=False)
    embedding        = db.Column(db.LargeBinary)  # pickle-сериализованный numpy-массив
    model_name       = db.Column(db.String(50))   # название модели, создавшей эмбеддинг
    detector_backend = db.Column(db.String(50))   # название детектора
    is_primary       = db.Column(db.Boolean, default=False)  # основная фотография
    uploaded_at      = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        """
        Сериализует запись фотографии в словарь.

        Бинарное поле embedding не включается в ответ — оно используется
        только внутри сервиса распознавания.

        Возвращает:
            dict: метаданные фотографии с URL для загрузки изображения
        """
        return {
            'id':          self.id,
            'student_id':  self.student_id,
            'filename':    self.filename,
            'is_primary':  self.is_primary,
            'model_name':  self.model_name,
            'uploaded_at': format_datetime(self.uploaded_at),
            # URL для запроса фотографии через API
            'url': f'/api/photo/{self.student_id}/{self.filename}',
        }


class Attendance(db.Model):
    """
    Запись посещаемости одного студента на одном занятии.

    Значения поля status:
        present  — студент распознан системой автоматически
        manual   — преподаватель отметил вручную
        absent   — студент не присутствовал
    """

    __tablename__ = 'attendance'

    id          = db.Column(db.Integer,    primary_key=True)
    lesson_id   = db.Column(db.Integer,    db.ForeignKey('lessons.id'),  nullable=False)
    student_id  = db.Column(db.Integer,    db.ForeignKey('students.id'), nullable=False)
    status      = db.Column(db.String(20), nullable=False)  # present / manual / absent
    confidence  = db.Column(db.Float)   # уверенность распознавания (1 - расстояние)
    distance    = db.Column(db.Float)   # косинусное расстояние между эмбеддингами
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        """
        Сериализует запись посещаемости в словарь.

        Включает ФИО и номер зачётки студента для отображения в журнале.

        Возвращает:
            dict: поля записи посещаемости с данными студента
        """
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
            'recorded_at': format_datetime(self.recorded_at),
        }
