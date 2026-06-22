"""
seed_data.py — наполнение базы данных тестовыми данными.

Создаёт:
  - 8 учебных групп
  - предметы (для группы ОБ-Вт-09.03.03.02-41 — заданные, для остальных — случайные)
  - студентов со случайными ФИО, 4-значным номером зачётки и фотографией-аватаром
  - расписание занятий (4-5 пар в день) с сегодняшнего дня до 19.07.2026

ВАЖНО про фотографии:
  Для каждого студента генерируется простой аватар (круг с инициалами на
  случайном фоне) средствами Pillow — он НЕ является фотографией реального
  лица. DeepFace/RetinaFace не сможет обнаружить на нём лицо, поэтому
  эмбеддинг (embedding) для таких фото останется пустым (None), а функция
  распознавания не будет находить совпадений по этим тестовым студентам.
  Это ожидаемо и нужно для проверки работы интерфейсов (списки, фото,
  карточки) без реальных фотографий людей.

  Если нужно протестировать именно распознавание лиц — замените функцию
  generate_avatar() на загрузку реальных фотографий (например, открытого
  датасета лиц) либо сделайте студентам фото через камеру в admin.html.

Запуск (из папки server/, с активированным venv):
    python seed_data.py
"""

import os
import random
import sys
from datetime import date, timedelta, datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from app import app, db, UPLOAD_DIR
from models import Group, Subject, Student, StudentPhoto, Lesson, User

from PIL import Image, ImageDraw, ImageFont

random.seed(42)  # для воспроизводимости (можно убрать)

# ═══════════════════════════════════════════════════════════════
#  1. ГРУППЫ
# ═══════════════════════════════════════════════════════════════
GROUPS = [
    {"name": "ОБ-Вт-09.03.03.02-41 Вт", "course": 4, "faculty": "Филиал УдГУ в г. Воткинске", "specialty": "09.03.03 Прикладная информатика"},
    {"name": "ОБ-Вт-09.03.03.02-11 Вт", "course": 1, "faculty": "Филиал УдГУ в г. Воткинске", "specialty": "09.03.03 Прикладная информатика"},
    {"name": "ОБ-21.03.01.01-11 Вт",    "course": 1, "faculty": "Филиал УдГУ в г. Воткинске", "specialty": "21.03.01 Нефтегазовое дело"},
    {"name": "ОБ-44.03.02.03-11 Вт",    "course": 1, "faculty": "Филиал УдГУ в г. Воткинске", "specialty": "44.03.02 Психолого-педагогическое образование"},
    {"name": "ОБ-44.03.02.03-21",       "course": 2, "faculty": "Филиал УдГУ в г. Воткинске", "specialty": "44.03.02 Психолого-педагогическое образование"},
    {"name": "ОБ-44.03.02.03-31",       "course": 3, "faculty": "Филиал УдГУ в г. Воткинске", "specialty": "44.03.02 Психолого-педагогическое образование"},
    {"name": "ОБ-44.03.02.03-41",       "course": 4, "faculty": "Филиал УдГУ в г. Воткинске", "specialty": "44.03.02 Психолого-педагогическое образование"},
    {"name": "ОБ-38.03.04.01-41",       "course": 4, "faculty": "Филиал УдГУ в г. Воткинске", "specialty": "38.03.04 Государственное и муниципальное управление"},
]

# ═══════════════════════════════════════════════════════════════
#  2. ПРЕДМЕТЫ
# ═══════════════════════════════════════════════════════════════
# Заданные предметы для ОБ-Вт-09.03.03.02-41 Вт
PI_SUBJECTS = [
    "Программная инженерия",
    "Корпоративные информационные технологии",
    "Оптимизация веб-приложений",
    "Программирование для мобильных устройств",
]

# Общий пул предметов для случайного распределения по остальным группам
RANDOM_SUBJECT_POOL = [
    "Высшая математика", "Физическая культура и спорт", "История России",
    "Иностранный язык", "Философия", "Экономическая теория",
    "Основы права", "Безопасность жизнедеятельности", "Психология",
    "Педагогика", "Социология", "Введение в специальность",
    "Информатика", "Геология нефти и газа", "Бурение скважин",
    "Возрастная психология", "Методика преподавания", "Конфликтология",
    "Государственное управление", "Муниципальное право",
    "Деловые коммуникации", "Статистика", "Менеджмент",
    "Документоведение", "Этика и эстетика",
]

# ═══════════════════════════════════════════════════════════════
#  3. ФИО — пулы для генерации случайных студентов
# ═══════════════════════════════════════════════════════════════
LAST_NAMES_M = ["Иванов","Петров","Сидоров","Кузнецов","Смирнов","Попов","Васильев",
    "Соколов","Михайлов","Новиков","Фёдоров","Морозов","Волков","Алексеев","Лебедев",
    "Семёнов","Егоров","Павлов","Козлов","Степанов","Николаев","Орлов","Андреев",
    "Макаров","Никитин","Захаров","Зайцев","Соловьёв","Борисов","Яковлев"]
LAST_NAMES_F = [n[:-1] + "а" if n.endswith("в") else n + "а" for n in LAST_NAMES_M]

FIRST_NAMES_M = ["Александр","Дмитрий","Максим","Сергей","Андрей","Алексей","Артём",
    "Илья","Кирилл","Михаил","Никита","Матвей","Роман","Егор","Арсений","Иван",
    "Денис","Евгений","Владислав","Тимур","Глеб","Данил","Владимир","Игорь"]
FIRST_NAMES_F = ["Анна","Мария","Елена","Ольга","Наталья","Татьяна","Светлана",
    "Екатерина","Юлия","Анастасия","Виктория","Дарья","Ксения","Полина","Алина",
    "Софья","Вероника","Алёна","Кристина","Маргарита","Валерия","Ева","Арина"]

MIDDLE_NAMES_M = ["Александрович","Дмитриевич","Сергеевич","Андреевич","Алексеевич",
    "Игоревич","Михайлович","Викторович","Владимирович","Николаевич","Евгеньевич",
    "Олегович","Юрьевич","Анатольевич","Павлович"]
MIDDLE_NAMES_F = ["Александровна","Дмитриевна","Сергеевна","Андреевна","Алексеевна",
    "Игоревна","Михайловна","Викторовна","Владимировна","Николаевна","Евгеньевна",
    "Олеговна","Юрьевна","Анатольевна","Павловна"]

STUDENTS_PER_GROUP = 14   # количество студентов в каждой группе

AVATAR_COLORS = ["#4A86C8", "#D99A3D", "#4CAF50", "#D9534F", "#9C6ADE",
                  "#3DB8C9", "#C97A3D", "#7A9C3D", "#C93D7A", "#6A8CDE"]


# ═══════════════════════════════════════════════════════════════
#  Генерация аватара (заглушка вместо реальной фотографии)
# ═══════════════════════════════════════════════════════════════
def generate_avatar(initials: str, save_path: Path):
    """Создаёт квадратное изображение 400x400 с кругом и инициалами."""
    size = 400
    bg_color = random.choice(AVATAR_COLORS)
    img = Image.new("RGB", (size, size), "#FFFFFF")
    draw = ImageDraw.Draw(img)
    draw.ellipse([20, 20, size - 20, size - 20], fill=bg_color)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 140)
    except Exception:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), initials, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1]),
               initials, fill="#FFFFFF", font=font)

    img.save(str(save_path), "JPEG", quality=90)


def random_fio(gender: str):
    if gender == "M":
        return (random.choice(FIRST_NAMES_M), random.choice(LAST_NAMES_M), random.choice(MIDDLE_NAMES_M))
    else:
        return (random.choice(FIRST_NAMES_F), random.choice(LAST_NAMES_F), random.choice(MIDDLE_NAMES_F))


# ═══════════════════════════════════════════════════════════════
#  Расписание: временные слоты пар
# ═══════════════════════════════════════════════════════════════
TIME_SLOTS = [
    ("08:20", "09:50"),
    ("10:00", "11:30"),
    ("11:50", "13:20"),
    ("13:50", "15:20"),
    ("15:30", "17:00"),
]
CLASSROOMS = ["101", "102", "203", "204", "305", "Лаб. 1", "Лаб. 2", "Акт. зал"]

END_DATE = date(2026, 7, 19)


def main():
    with app.app_context():
        teacher = User.query.filter_by(role="teacher").first()
        teacher_id = teacher.id if teacher else None

        # ── 1. Группы ────────────────────────────────────────────
        print("Создание групп...")
        group_objs = {}
        for g in GROUPS:
            existing = Group.query.filter_by(name=g["name"]).first()
            if existing:
                group_objs[g["name"]] = existing
                continue
            grp = Group(**g)
            db.session.add(grp)
            db.session.flush()
            group_objs[g["name"]] = grp
        db.session.commit()
        print(f"  Готово: {len(group_objs)} групп")

        # ── 2. Предметы ──────────────────────────────────────────
        print("Создание предметов...")
        subject_objs = {}

        def get_or_create_subject(name):
            if name in subject_objs:
                return subject_objs[name]
            existing = Subject.query.filter_by(name=name).first()
            if existing:
                subject_objs[name] = existing
                return existing
            s = Subject(name=name, code=None, description=None)
            db.session.add(s)
            db.session.flush()
            subject_objs[name] = s
            return s

        for name in PI_SUBJECTS:
            get_or_create_subject(name)

        group_subjects = {}  # group_name -> [Subject, ...]
        group_subjects["ОБ-Вт-09.03.03.02-41 Вт"] = [subject_objs[n] for n in PI_SUBJECTS]

        for g in GROUPS:
            if g["name"] == "ОБ-Вт-09.03.03.02-41 Вт":
                continue
            chosen_names = random.sample(RANDOM_SUBJECT_POOL, 5)
            group_subjects[g["name"]] = [get_or_create_subject(n) for n in chosen_names]

        db.session.commit()
        print(f"  Готово: {len(subject_objs)} предметов")

        # ── 3. Студенты + фото ──────────────────────────────────
        print("Создание студентов и фотографий...")
        used_zachetka = set(
            row[0] for row in db.session.query(Student.student_id).all()
        )

        def next_zachetka():
            while True:
                z = f"{random.randint(0, 9999):04d}"
                if z not in used_zachetka:
                    used_zachetka.add(z)
                    return z

        total_students = 0
        group_students = {}  # group_name -> [Student, ...]

        for g in GROUPS:
            grp = group_objs[g["name"]]
            students_list = []
            for i in range(STUDENTS_PER_GROUP):
                gender = random.choice(["M", "F"])
                first, last, middle = random_fio(gender)
                zachetka = next_zachetka()

                student = Student(
                    student_id=zachetka,
                    first_name=first,
                    last_name=last,
                    middle_name=middle,
                    group_id=grp.id,
                    status="active",
                )
                db.session.add(student)
                db.session.flush()

                # Генерация фото-аватара
                student_dir = UPLOAD_DIR / str(student.id)
                student_dir.mkdir(exist_ok=True, parents=True)
                photo_path = student_dir / "avatar.jpg"
                initials = (first[0] + last[0]).upper()
                generate_avatar(initials, photo_path)

                photo = StudentPhoto(
                    student_id=student.id,
                    filename="avatar.jpg",
                    file_path=str(photo_path),
                    embedding=None,   # реального лица нет — эмбеддинг не считаем
                    model_name="ArcFace",
                    detector_backend="retinaface",
                    is_primary=True,
                )
                db.session.add(photo)

                students_list.append(student)
                total_students += 1

            group_students[g["name"]] = students_list
            db.session.commit()
            print(f"  {g['name']}: {STUDENTS_PER_GROUP} студентов")

        print(f"  Итого студентов: {total_students}")

        # ── 4. Расписание занятий ───────────────────────────────
        print("Создание расписания...")
        today = date.today()
        # начинаем с ближайшего понедельника (или сегодня, если сегодня будний день)
        start_date = today
        total_lessons = 0

        current = start_date
        while current <= END_DATE:
            if current.weekday() < 6:   # Пн-Сб (0-5), воскресенье (6) — выходной
                lessons_today = random.randint(4, 5)
                for g in GROUPS:
                    grp = group_objs[g["name"]]
                    subjects_for_group = group_subjects[g["name"]]
                    for lesson_num in range(1, lessons_today + 1):
                        if lesson_num > len(TIME_SLOTS):
                            break
                        t_start, t_end = TIME_SLOTS[lesson_num - 1]
                        subject = random.choice(subjects_for_group)
                        lesson = Lesson(
                            subject_id=subject.id,
                            group_id=grp.id,
                            teacher_id=teacher_id,
                            lesson_number=lesson_num,
                            topic=None,
                            lesson_date=current,
                            time_start=t_start,
                            time_end=t_end,
                            classroom=random.choice(CLASSROOMS),
                            is_locked=False,
                            unrecognized_count=0,
                        )
                        db.session.add(lesson)
                        total_lessons += 1
            current += timedelta(days=1)

        db.session.commit()
        print(f"  Итого занятий: {total_lessons}")

        print("\n══════════════════════════════════════")
        print("Наполнение базы данных завершено!")
        print(f"  Групп:    {len(group_objs)}")
        print(f"  Предметов: {len(subject_objs)}")
        print(f"  Студентов: {total_students}")
        print(f"  Занятий:   {total_lessons}")
        print("══════════════════════════════════════")
        print("\nВАЖНО: фотографии студентов — это сгенерированные")
        print("аватары с инициалами, а не реальные лица. Распознавание")
        print("по этим фото работать не будет (эмбеддинги не вычислены).")
        print("Для теста распознавания загрузите реальные фото через")
        print("интерфейс администратора.")


if __name__ == "__main__":
    main()
