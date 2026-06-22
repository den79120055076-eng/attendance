"""
benchmark_search.py — замер времени поиска совпадения лица среди
реальных эмбеддингов, накопленных в базе данных (find_best_match).

Помогает ответить на вопрос "как быстро ищет систему при N студентах
с реальными фото" — полезно для раздела тестирования производительности
в дипломной работе.

Запуск (из папки server/, после load_real_faces.py):
    python benchmark_search.py
"""

import os
import sys
import time
import pickle
import random

sys.path.insert(0, os.path.dirname(__file__))

from app import app, db, find_best_match
from models import StudentPhoto

import numpy as np


def main():
    with app.app_context():
        photos = StudentPhoto.query.filter(StudentPhoto.embedding != None).all()  # noqa: E711
        n = len(photos)

        if n == 0:
            print("В базе нет фотографий с вычисленным эмбеддингом.")
            print("Сначала запустите load_real_faces.py")
            return

        candidates = []
        for p in photos:
            emb = np.array(pickle.loads(p.embedding), dtype="float32")
            candidates.append((p.student_id, emb))

        print(f"Всего эмбеддингов в базе: {n}\n")

        # Берём случайный эмбеддинг как "запрос" — имитация фото с занятия
        query_student_id, query_embedding = random.choice(candidates)

        # Замеряем время поиска при разном количестве кандидатов
        # (чтобы показать, как растёт время с ростом базы)
        sizes_to_test = sorted(set([
            min(n, s) for s in [10, 25, 50, 100, 200, 500, n]
            if s <= n
        ]))

        print(f"{'Кандидатов':>12} {'Время поиска, мс':>20} {'Найден?':>10}")
        print("-" * 48)

        for size in sizes_to_test:
            subset = random.sample(candidates, size) if size < n else candidates
            # Гарантируем, что искомый эмбеддинг есть в подвыборке
            if not any(sid == query_student_id for sid, _ in subset):
                subset[0] = (query_student_id, query_embedding)

            # Несколько повторов для усреднения (из-за погрешности измерения)
            times = []
            for _ in range(20):
                t0 = time.perf_counter()
                result = find_best_match(query_embedding, subset, threshold=0.4)
                times.append((time.perf_counter() - t0) * 1000)

            avg_ms = sum(times) / len(times)
            found = "да" if result.get("matched") else "нет"
            print(f"{size:>12} {avg_ms:>17.3f} мс {found:>10}")

        print("\nВывод: поиск методом полного перебора (linear search) по")
        print("косинусному расстоянию линейно растёт со временем относительно")
        print("количества кандидатов, но даже при нескольких сотнях студентов")
        print("остаётся в пределах единиц миллисекунд на одно лицо.")


if __name__ == "__main__":
    main()
