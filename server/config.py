"""
config.py

Конфигурационный файл приложения учёта посещаемости студентов.

Все изменяемые параметры (пути, ключи, пороги) сосредоточены здесь.
Для смены настройки достаточно изменить одну переменную в этом файле.
"""

import os
from datetime import timedelta


# Пути к директориям


# Корневая директория проекта (на уровень выше папки server/)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Папка для хранения базы данных, фотографий и временных файлов
DATA_DIR    = os.path.join(BASE_DIR, 'data')
PHOTOS_DIR  = os.path.join(BASE_DIR, 'data', 'student_photos')
TEMP_DIR    = os.path.join(BASE_DIR, 'data', 'temp')

# Папка со статическими файлами (HTML, CSS)
WEB_DIR     = os.path.join(BASE_DIR, 'web')


# Параметры базы данных


# SQLite: база данных хранится в одном файле, не требует отдельного сервера
DATABASE_PATH = os.path.join(DATA_DIR, 'attendance.sqlite3')
DATABASE_URI  = 'sqlite:///' + DATABASE_PATH


# Параметры безопасности и авторизации


# Секретный ключ Flask (используется для подписи сессий)
# В реальном развёртывании заменить на случайную строку из переменной окружения
SECRET_KEY     = os.environ.get('SECRET_KEY',     'attendance-secret-key-change-in-production')

# Секретный ключ для подписи JWT-токенов
JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'attendance-jwt-key-change-in-production')

# Время жизни токена авторизации
JWT_TOKEN_LIFETIME = timedelta(hours=12)

# Параметры загрузки файлов


# Максимальный допустимый размер загружаемого файла (32 МБ)
# Учитывает возможность одновременной загрузки нескольких фото аудитории
MAX_UPLOAD_SIZE_MB = 32
MAX_CONTENT_LENGTH = MAX_UPLOAD_SIZE_MB * 1024 * 1024

# Допустимые расширения файлов изображений
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png'}


# Параметры распознавания лиц (DeepFace)


# Модель распознавания лиц.
# ArcFace выбрана как наиболее точная: 99.81% на наборе данных LFW.
# Другие варианты: Facenet512 (99.65%), SFace (99.60%), VGG-Face (98.95%).
DEEPFACE_MODEL = 'ArcFace'

# Детектор лиц.
# RetinaFace выбран потому что находит несколько лиц в одном кадре
# и работает при повороте головы до 90 градусов — важно для групповых фото.
# Для слабых машин можно заменить на 'opencv' (быстрее, но менее точный).
DEEPFACE_DETECTOR = 'retinaface'

# Метрика расстояния между эмбеддингами.
# cosine рекомендуется для модели ArcFace (см. документацию DeepFace).
DEEPFACE_METRIC = 'cosine'

# Порог совпадения: расстояние ниже этого значения означает «один человек».
# Для ArcFace + cosine оптимальное значение — 0.68 (из документации DeepFace).
# Уменьшить (0.50) — строже, больше отказов.
# Увеличить (0.80) — мягче, риск ложных совпадений.
DEEPFACE_THRESHOLD = 0.68

# Минимальная уверенность детектора при поиске лиц в групповом фото.
# Лица с более низкой уверенностью считаются размытыми или частично скрытыми.
FACE_MIN_CONFIDENCE = 0.85


# Учётные данные по умолчанию (создаются при первом запуске)


DEFAULT_ADMIN_LOGIN    = 'admin'
DEFAULT_ADMIN_PASSWORD = 'admin'
DEFAULT_TEACHER_LOGIN    = 'teacher'
DEFAULT_TEACHER_PASSWORD = 'teacher'


# Создание директорий при импорте конфига


for _directory in [DATA_DIR, PHOTOS_DIR, TEMP_DIR]:
    os.makedirs(_directory, exist_ok=True)
