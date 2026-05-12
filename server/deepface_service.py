"""
deepface_service.py

Сервис распознавания лиц на основе библиотеки DeepFace.

Основные возможности:
    - Извлечение эмбеддинга (векторного представления лица) из фотографии
    - Обнаружение нескольких лиц на одном снимке (для фото аудитории)
    - Сравнение эмбеддингов и поиск ближайшего совпадения в базе

Выбор компонентов:
    Модель:   ArcFace     — точность 99.81% на наборе данных LFW
    Детектор: RetinaFace  — находит несколько лиц при повороте до 90 градусов
    Метрика:  cosine      — рекомендуется для модели ArcFace

Единственный экземпляр сервиса создаётся при запуске приложения
и переиспользуется для всех запросов (модель загружается один раз).
"""

import os
import pickle
import numpy as np

# Подавление информационных сообщений TensorFlow в консоли
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

try:
    from deepface import DeepFace
    DEEPFACE_AVAILABLE = True
except ImportError:
    DEEPFACE_AVAILABLE = False
    print('Предупреждение: библиотека DeepFace не установлена.')
    print('Установите: pip install deepface')


class FaceRecognitionService:
    """
    Сервис распознавания лиц.

    Инкапсулирует все операции с DeepFace:
    получение эмбеддингов, поиск совпадений, вычисление расстояний.

    Создаётся один раз при старте Flask-приложения (паттерн singleton),
    чтобы не загружать веса нейросети при каждом запросе.
    """

    def __init__(self, model, detector, metric, threshold, face_min_confidence, temp_dir):
        """
        Инициализирует сервис с заданными параметрами.

        Параметры:
            model               (str):   название модели распознавания (например 'ArcFace')
            detector            (str):   название детектора лиц (например 'retinaface')
            metric              (str):   метрика расстояния: 'cosine', 'euclidean', 'euclidean_l2'
            threshold           (float): порог совпадения (расстояние <= порога => одно лицо)
            face_min_confidence (float): минимальная уверенность детектора (0.0 — 1.0)
            temp_dir            (str):   путь к папке для временных файлов
        """
        self.model               = model
        self.detector            = detector
        self.metric              = metric
        self.threshold           = threshold
        self.face_min_confidence = face_min_confidence
        self.temp_dir            = temp_dir

    def update_threshold(self, new_threshold):
        """
        Изменяет порог совпадения без перезапуска сервера.

        Используется из панели администратора (вкладка «Настройки»).

        Параметры:
            new_threshold (float): новое значение порога
        """
        self.threshold = float(new_threshold)

    def get_settings(self):
        """
        Возвращает текущие настройки сервиса.

        Используется для отображения конфигурации в панели администратора
        и для проверки при выборе эмбеддингов из базы данных.

        Возвращает:
            dict: текущие параметры распознавания
        """
        return {
            'model':     self.model,
            'detector':  self.detector,
            'metric':    self.metric,
            'threshold': self.threshold,
        }

    def extract_embedding(self, image_path):
        """
        Извлекает векторное представление лица (эмбеддинг) из фотографии.

        Применяется при регистрации студента: фотография сохраняется
        и сразу вычисляется её эмбеддинг для хранения в базе данных.

        Алгоритм:
            1. DeepFace обнаруживает лицо на снимке заданным детектором
            2. Лицо выравнивается и приводится к стандартному размеру
            3. Нейросеть ArcFace возвращает вектор из 512 чисел

        Параметры:
            image_path (str): абсолютный путь к файлу изображения

        Возвращает:
            numpy.ndarray | None: вектор из 512 чисел, или None если лицо не найдено
        """
        if not DEEPFACE_AVAILABLE:
            return None

        try:
            result = DeepFace.represent(
                img_path          = image_path,
                model_name        = self.model,
                detector_backend  = self.detector,
                enforce_detection = True,
            )
            if result:
                return np.array(result[0]['embedding'])
            return None

        except Exception as error:
            # DeepFace выбрасывает исключение если лицо не обнаружено
            print(f'extract_embedding: лицо не найдено в {image_path}: {error}')
            return None

    def extract_all_faces_embeddings(self, image_path):
        """
        Обнаруживает все лица на снимке и возвращает эмбеддинг каждого.

        Применяется при распознавании: преподаватель фотографирует аудиторию,
        на одном снимке может быть несколько студентов.

        Алгоритм (раздел 3.2 пояснительной записки):
            1. RetinaFace сканирует изображение и находит все лица
            2. Лица с уверенностью ниже face_min_confidence отбрасываются
               (размытые, частично перекрытые, слишком мелкие)
            3. Для каждого принятого лица вызывается ArcFace с параметром
               detector_backend='skip' — повторное обнаружение не нужно,
               так как лицо уже вырезано и выровнено на шаге 1

        Параметры:
            image_path (str): абсолютный путь к файлу снимка аудитории

        Возвращает:
            list[numpy.ndarray]: список эмбеддингов (по одному на каждое лицо)
        """
        if not DEEPFACE_AVAILABLE:
            return []

        embeddings = []

        try:
            # Шаг 1: обнаружение всех лиц на снимке
            face_list = DeepFace.extract_faces(
                img_path          = image_path,
                detector_backend  = self.detector,
                enforce_detection = False,
                align             = True,
            )
        except Exception as error:
            print(f'extract_all_faces_embeddings: ошибка детектора: {error}')
            return []

        # Шаг 2: фильтрация и получение эмбеддинга для каждого лица
        for face_data in face_list:
            confidence = face_data.get('confidence', 0.0)
            if confidence < self.face_min_confidence:
                # Лицо обнаружено с низкой уверенностью — пропускаем
                continue

            face_array = face_data.get('face')
            if face_array is None:
                continue

            # Шаг 3: конвертация float [0,1] в uint8 [0,255] для DeepFace.represent()
            face_uint8 = (face_array * 255).astype(np.uint8)

            try:
                # detector_backend='skip': уже вырезанное лицо передаётся напрямую
                result = DeepFace.represent(
                    img_path          = face_uint8,
                    model_name        = self.model,
                    detector_backend  = 'skip',
                    enforce_detection = False,
                )
                if result:
                    embeddings.append(np.array(result[0]['embedding']))
            except Exception as error:
                print(f'extract_all_faces_embeddings: ошибка эмбеддинга: {error}')

        return embeddings

    def compute_distance(self, vector_a, vector_b):
        """
        Вычисляет расстояние между двумя векторными представлениями лиц.

        Косинусное расстояние вычисляется по формуле:
            distance = 1 - cos(angle) = 1 - (a · b) / (|a| * |b|)

        Значение 0 означает идентичные векторы (одно и то же лицо).
        Значение 2 означает максимально непохожие векторы.

        Параметры:
            vector_a (numpy.ndarray): первый вектор эмбеддинга
            vector_b (numpy.ndarray): второй вектор эмбеддинга

        Возвращает:
            float: расстояние, значение от 0 до 2
        """
        a = np.array(vector_a, dtype=np.float64)
        b = np.array(vector_b, dtype=np.float64)

        if self.metric == 'cosine':
            # Косинусное расстояние: 1 минус косинус угла между векторами
            norm_a = np.linalg.norm(a)
            norm_b = np.linalg.norm(b)
            # Добавляем 1e-10 чтобы избежать деления на ноль
            cosine_similarity = np.dot(a, b) / (norm_a * norm_b + 1e-10)
            return float(1.0 - cosine_similarity)

        elif self.metric == 'euclidean':
            # Евклидово расстояние: корень из суммы квадратов разностей
            return float(np.linalg.norm(a - b))

        else:
            # euclidean_l2: евклидово расстояние на нормализованных векторах
            a_norm = a / (np.linalg.norm(a) + 1e-10)
            b_norm = b / (np.linalg.norm(b) + 1e-10)
            return float(np.linalg.norm(a_norm - b_norm))

    def find_best_match(self, query_embedding, candidates):
        """
        Ищет ближайшее совпадение в списке кандидатов.

        Перебирает все эмбеддинги студентов группы и находит тот,
        расстояние до которого минимально. Если расстояние не превышает
        порог threshold, возвращает идентификатор студента.

        Параметры:
            query_embedding (numpy.ndarray): эмбеддинг лица с фото аудитории
            candidates (list): список кортежей (student_id, embedding)

        Возвращает:
            dict: словарь с ключами:
                matched     (bool):  True если совпадение найдено в пределах порога
                student_id  (int):   id студента или None
                distance    (float): расстояние до ближайшего кандидата
                confidence  (float): уверенность = 1 - distance
        """
        # Возвращаем пустой результат если нет эмбеддинга или кандидатов
        if query_embedding is None or not candidates:
            return {
                'matched':    False,
                'student_id': None,
                'distance':   None,
                'confidence': 0.0,
            }

        best_student_id = None
        best_distance   = float('inf')

        for student_id, db_embedding in candidates:
            try:
                distance = self.compute_distance(query_embedding, db_embedding)
                if distance < best_distance:
                    best_distance   = distance
                    best_student_id = student_id
            except Exception as error:
                print(f'find_best_match: ошибка при сравнении с id={student_id}: {error}')
                continue

        matched = best_distance <= self.threshold

        return {
            'matched':    matched,
            'student_id': best_student_id if matched else None,
            'distance':   round(best_distance, 4),
            'confidence': round(max(0.0, 1.0 - best_distance), 4),
        }

    def serialize_embedding(self, embedding):
        """
        Сериализует numpy-массив в байты для сохранения в базе данных.

        Использует стандартный модуль pickle. Сохранённые байты
        десериализуются методом deserialize_embedding.

        Параметры:
            embedding (numpy.ndarray): вектор эмбеддинга

        Возвращает:
            bytes: сериализованный массив
        """
        return pickle.dumps(embedding)

    def deserialize_embedding(self, data):
        """
        Восстанавливает numpy-массив из байт, сохранённых в базе данных.

        Параметры:
            data (bytes): сериализованный массив из поля StudentPhoto.embedding

        Возвращает:
            numpy.ndarray: вектор эмбеддинга
        """
        return pickle.loads(data)



# Глобальный экземпляр сервиса (создаётся один раз при запуске)


_service_instance = None


def init_service(config):
    """
    Создаёт и сохраняет глобальный экземпляр FaceRecognitionService.

    Вызывается один раз в функции create_app() при старте приложения.
    Последующие вызовы get_service() возвращают уже созданный экземпляр.

    Параметры:
        config: модуль config.py с атрибутами DEEPFACE_*

    Возвращает:
        FaceRecognitionService: созданный экземпляр сервиса
    """
    global _service_instance
    _service_instance = FaceRecognitionService(
        model               = config.DEEPFACE_MODEL,
        detector            = config.DEEPFACE_DETECTOR,
        metric              = config.DEEPFACE_METRIC,
        threshold           = config.DEEPFACE_THRESHOLD,
        face_min_confidence = config.FACE_MIN_CONFIDENCE,
        temp_dir            = config.TEMP_DIR,
    )
    print(
        f'FaceRecognitionService запущен. '
        f'Модель: {_service_instance.model}, '
        f'Детектор: {_service_instance.detector}, '
        f'Порог: {_service_instance.threshold}'
    )
    return _service_instance


def get_service():
    """
    Возвращает глобальный экземпляр FaceRecognitionService.

    Если init_service() ещё не вызывался — создаёт экземпляр
    с параметрами по умолчанию (для случаев использования вне Flask).

    Возвращает:
        FaceRecognitionService: активный экземпляр сервиса
    """
    global _service_instance
    if _service_instance is None:
        print('Предупреждение: сервис не инициализирован, используются параметры по умолчанию.')
        import config as cfg
        _service_instance = init_service(cfg)
    return _service_instance
