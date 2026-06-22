"""
copy_group_photos.py — копирует реальные файлы фотографий студентов
выбранной группы в отдельную папку вместе с HTML-страницей-сеткой.
Папку можно целиком перенести на Windows (общая папка VMware,
перетаскивание) и открыть там без проблем с путями к файлам.

Перед запуском узнайте id нужной группы скриптом list_groups.py
и подставьте его в переменную GROUP_ID ниже.

Запуск (на VM, из папки server/, с активированным venv):
    cd ~/attendance/server
    source venv/bin/activate
    python copy_group_photos.py
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app import app
from models import Student, StudentPhoto, Group

# ══════════════════════════════════════════════════════════
#  НАСТРОЙКА — поменяйте на id нужной группы
#  (узнать id можно скриптом list_groups.py)
# ══════════════════════════════════════════════════════════
GROUP_ID = 1

# Максимум фото (0 = без ограничения, все студенты группы)
MAX_PHOTOS = 0


def main():
    with app.app_context():
        group = Group.query.get(GROUP_ID)
        if not group:
            print(f"Группа с id={GROUP_ID} не найдена.")
            print("Запустите list_groups.py чтобы посмотреть доступные id.")
            return

        students = Student.query.filter_by(group_id=GROUP_ID, status="active").all()
        print(f"Группа: {group.name}")
        print(f"Активных студентов в группе: {len(students)}")

        items = []   # [(имя_файла, ФИО, исходный_путь), ...]
        for s in students:
            photo = StudentPhoto.query.filter_by(student_id=s.id).first()
            if photo and Path(photo.file_path).exists():
                items.append((s.student_id, s.full_name, photo.file_path))

        if MAX_PHOTOS > 0:
            items = items[:MAX_PHOTOS]

        print(f"Найдено фото с файлом на диске: {len(items)}")
        if not items:
            print("Нет ни одного фото для этой группы.")
            return

        # ── Папка результата ────────────────────────────────────
        out_dir = Path(__file__).parent / "group_photos"
        photos_dir = out_dir / "photos"
        if out_dir.exists():
            shutil.rmtree(out_dir)
        photos_dir.mkdir(parents=True)

        # ── Копируем сами файлы ──────────────────────────────────
        copied = []
        for student_id, full_name, src_path in items:
            ext = Path(src_path).suffix or ".jpg"
            dest_name = f"{student_id}{ext}"
            dest_path = photos_dir / dest_name
            shutil.copy(src_path, dest_path)
            copied.append((dest_name, full_name))
            print(f"  скопировано: {dest_name}  ({full_name})")

        # ── HTML-сетка на ОТНОСИТЕЛЬНЫХ путях ────────────────────
        html = (
            "<html><head><meta charset='utf-8'>"
            f"<title>{group.name}</title></head>"
            "<body style='margin:0;background:white;font-family:sans-serif;'>"
            f"<h3 style='margin:10px;'>{group.name} — {len(copied)} фото</h3>"
            "<div style='display:flex;flex-wrap:wrap;'>"
        )
        for fname, full_name in copied:
            html += (
                f"<div style='margin:5px;text-align:center;'>"
                f"<img src='photos/{fname}' "
                f"style='width:150px;height:150px;object-fit:cover;"
                f"border:1px solid #ccc;'>"
                f"<div style='font-size:11px;width:150px;'>{full_name}</div></div>"
            )
        html += "</div></body></html>"

        (out_dir / "grid.html").write_text(html, encoding="utf-8")

        print(f"\nГотово! Папка создана: {out_dir}")
        print(f"Содержит: grid.html + photos/ ({len(copied)} файлов)")
        print("\nПеренесите ВСЮ папку group_photos целиком на Windows")
        print("(перетаскиванием или через общую папку VMware),")
        print("затем откройте файл grid.html двойным щелчком.")


if __name__ == "__main__":
    main()
