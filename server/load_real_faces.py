"""
load_real_faces.py — загрузка реальных фотографий лиц из открытого
датасета LFW (Labeled Faces in the Wild) и замена ими фото-аватаров
у части студентов в базе данных. Позволяет протестировать реальную
работу ArcFace/RetinaFace и замерить время поиска по эмбеддингам.

LFW — стандартный научный датасет для тестирования систем распознавания
лиц (13 233 фотографии 5 749 человек), распространяется свободно для
исследовательских и учебных целей: http://vis-www.cs.umass.edu/lfw/

Установка зависимости:
    pip install scikit-learn

Запуск (из папки server/, с активированным venv):
    python load_real_faces.py [--count 30]

Что делает:
  1. Скачивает датасет LFW (один раз, кешируется в ~/scikit_learn_data)
  2. Берёт N случайных реальных фотографий лиц
  3. Находит в базе N студентов без вычисленного эмбеддинга
     (или создаёт новых, если не хватает)
  4. Сохраняет реальное фото вместо аватара, вычисляет эмбеддинг ArcFace
  5. Выводит время вычисления каждого эмбеддинга
"""

import os
import sys
import time
import random
import argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from app import app, db, UPLOAD_DIR
from models import Student, StudentPhoto, Group

from PIL import Image

random.seed()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=30,
                         help="Количество реальных фото для загрузки")
    args = parser.parse_args()

    print("Загрузка датасета LFW (может занять 1-2 минуты при первом запуске)...")
    from sklearn.datasets import fetch_lfw_people

    # min_faces_per_person=1 — берём максимально разнообразный набор лиц
    lfw = fetch_lfw_people(color=True, resize=1.0, min_faces_per_person=1)
    images = lfw.images          # numpy array (N, H, W, 3), значения 0..1
    names  = lfw.target_names

    total_available = len(images)
    print(f"Датасет загружен: {total_available} фотографий доступно")

    count = min(args.count, total_available)
    indices = random.sample(range(total_available), count)

    with app.app_context():
        from deepface import DeepFace

        # Берём существующих студентов (без реального фото) или создаём новых
        students = Student.query.limit(count).all()
        if len(students) < count:
            print(f"В базе недостаточно студентов ({len(students)}), "
                  f"запустите сначала seed_data.py для создания группы и студентов.")
            group = Group.query.first()
            if not group:
                print("Нет ни одной группы — сначала запустите seed_data.py")
                return
            needed = count - len(students)
            for i in range(needed):
                s = Student(
                    student_id=f"R{i:03d}",
                    first_name="Тест", last_name=f"Студент{i}",
                    group_id=group.id, status="active",
                )
                db.session.add(s)
            db.session.commit()
            students = Student.query.limit(count).all()

        total_time = 0.0
        success_count = 0

        print(f"\nОбработка {count} реальных фотографий...")
        print(f"{'№':>3} {'Студент':<30} {'Время вычисления, мс':>22}")
        print("-" * 60)

        for i, (student, img_idx) in enumerate(zip(students, indices)):
            # Конвертируем numpy-массив LFW (0..1 float) в JPEG
            img_array = (images[img_idx] * 255).astype("uint8")
            pil_img = Image.fromarray(img_array)

            student_dir = UPLOAD_DIR / str(student.id)
            student_dir.mkdir(exist_ok=True, parents=True)
            photo_path = student_dir / "real_face.jpg"
            pil_img.save(str(photo_path), "JPEG", quality=95)

            # Удаляем старую фотографию-аватар (если есть) из базы
            StudentPhoto.query.filter_by(student_id=student.id).delete()

            # Вычисляем эмбеддинг и замеряем время
            t0 = time.perf_counter()
            embedding_blob = None
            try:
                results = DeepFace.represent(
                    img_path=str(photo_path),
                    model_name="ArcFace",
                    detector_backend="retinaface",
                    enforce_detection=False,
                )
                if results:
                    import pickle
                    import numpy as np
                    emb = np.array(results[0]["embedding"], dtype="float32")
                    embedding_blob = pickle.dumps(emb)
                    success_count += 1
            except Exception as e:
                print(f"    ошибка обработки: {e}")

            elapsed_ms = (time.perf_counter() - t0) * 1000
            total_time += elapsed_ms

            photo = StudentPhoto(
                student_id=student.id,
                filename="real_face.jpg",
                file_path=str(photo_path),
                embedding=embedding_blob,
                model_name="ArcFace",
                detector_backend="retinaface",
                is_primary=True,
            )
            db.session.add(photo)
            db.session.commit()

            status = "OK" if embedding_blob else "лицо не обнаружено"
            print(f"{i+1:>3} {student.full_name:<30} {elapsed_ms:>18.1f} мс  [{status}]")

        print("-" * 60)
        print(f"\nИтого обработано: {count}")
        print(f"Успешно вычислен эмбеддинг: {success_count}")
        print(f"Среднее время вычисления эмбеддинга: {total_time/count:.1f} мс")
        print(f"Общее время обработки: {total_time/1000:.2f} сек")
        print("\nТеперь можно протестировать распознавание: сфотографируйте")
        print("монитор с одним из загруженных реальных лиц через интерфейс")
        print("преподавателя (teacher.html) и оцените скорость поиска.")


if __name__ == "__main__":
    main()
