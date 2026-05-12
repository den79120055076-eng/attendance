"""
import_photos.py

Imports employees into the face recognition system from a ZIP archive
or a folder containing JPEG face photos.

Run this script on the VIRTUAL MACHINE after transferring face_photos.zip
from the main PC (created by download_photos.py).

Usage:
    # From a ZIP archive:
    python import_photos.py --archive face_photos.zip

    # From an extracted folder:
    python import_photos.py --folder /path/to/photos

Requirements:
    pip install faker requests
    Flask server must be running at http://localhost:5000
"""

import os
import sys
import io
import zipfile
import argparse
import random
import requests
from faker import Faker

SERVER_URL = 'http://localhost:5000'
ADMIN_USER = 'admin'
ADMIN_PASS = 'admin'

fake = Faker('ru_RU')
Faker.seed(20)
random.seed(20)

DEPARTMENTS = [
    'Бухгалтерия',
    'Отдел кадров',
    'Отдел продаж',
    'Отдел разработки',
    'Технический отдел',
    'Юридический отдел',
    'Маркетинг',
    'Служба безопасности',
    'Административный отдел',
    'Финансовый отдел',
]

POSITIONS = [
    'Менеджер',
    'Старший менеджер',
    'Специалист',
    'Ведущий специалист',
    'Аналитик',
    'Руководитель отдела',
    'Бухгалтер',
    'Юрист',
    'Инженер',
    'Программист',
    'Системный администратор',
    'Дизайнер',
    'Маркетолог',
    'Секретарь',
]


def get_auth_token():
    """
    Authenticate with the server and return a JWT access token.

    Returns:
        str: JWT token

    Raises:
        SystemExit: if the server is not reachable or credentials are wrong
    """
    try:
        response = requests.post(
            f'{SERVER_URL}/api/auth/login',
            json={'username': ADMIN_USER, 'password': ADMIN_PASS},
            timeout=10,
        )
        if not response.ok:
            print(f'Authentication failed: {response.json().get("error")}')
            sys.exit(1)
        print('Authentication successful.')
        return response.json()['access_token']

    except requests.ConnectionError:
        print(f'Cannot connect to server at {SERVER_URL}.')
        print('Make sure the Flask server is running: python app.py')
        sys.exit(1)


def get_existing_count(token):
    """
    Return the number of employees currently in the database.

    Parameters:
        token (str): JWT access token

    Returns:
        int: employee count
    """
    headers  = {'Authorization': f'Bearer {token}'}
    response = requests.get(f'{SERVER_URL}/api/employees', headers=headers, timeout=10)
    return len(response.json()) if response.ok else 0


def load_photos_from_zip(zip_path):
    """
    Read all JPEG images from a ZIP archive into memory.

    Parameters:
        zip_path (str): path to the ZIP file

    Returns:
        list of bytes: image data for each photo, sorted by filename
    """
    photos = []
    with zipfile.ZipFile(zip_path, 'r') as zf:
        names = sorted([
            n for n in zf.namelist()
            if n.lower().endswith(('.jpg', '.jpeg', '.png'))
        ])
        for name in names:
            photos.append(zf.read(name))
    return photos


def load_photos_from_folder(folder_path):
    """
    Read all JPEG images from a folder into memory.

    Parameters:
        folder_path (str): path to the folder containing image files

    Returns:
        list of bytes: image data for each photo, sorted by filename
    """
    photos = []
    filenames = sorted([
        f for f in os.listdir(folder_path)
        if f.lower().endswith(('.jpg', '.jpeg', '.png'))
    ])
    for filename in filenames:
        filepath = os.path.join(folder_path, filename)
        with open(filepath, 'rb') as f:
            photos.append(f.read())
    return photos


def generate_employee_data(index):
    """
    Generate realistic Russian employee data using Faker.

    Parameters:
        index (int): sequence number used to build the employee ID and email

    Returns:
        dict: form fields for the API request
    """
    is_male = random.choice([True, False])

    if is_male:
        first_name  = fake.first_name_male()
        last_name   = fake.last_name_male()
        middle_name = fake.middle_name_male()
    else:
        first_name  = fake.first_name_female()
        last_name   = fake.last_name_female()
        middle_name = fake.middle_name_female()

    translit = str.maketrans({
        'а': 'a',  'б': 'b',  'в': 'v',  'г': 'g',  'д': 'd',
        'е': 'e',  'ё': 'e',  'ж': 'zh', 'з': 'z',  'и': 'i',
        'й': 'y',  'к': 'k',  'л': 'l',  'м': 'm',  'н': 'n',
        'о': 'o',  'п': 'p',  'р': 'r',  'с': 's',  'т': 't',
        'у': 'u',  'ф': 'f',  'х': 'h',  'ц': 'ts', 'ч': 'ch',
        'ш': 'sh', 'щ': 'sch','ъ': '',   'ы': 'y',  'ь': '',
        'э': 'e',  'ю': 'yu', 'я': 'ya',
    })
    email = f'{last_name.lower().translate(translit)}{index}@company.ru'

    return {
        'emp_id':      f'EMP{index:03d}',
        'first_name':  first_name,
        'last_name':   last_name,
        'middle_name': middle_name,
        'position':    random.choice(POSITIONS),
        'department':  random.choice(DEPARTMENTS),
        'email':       email,
        'phone':       fake.phone_number(),
    }


def upload_employee(token, emp_data, photo_bytes):
    """
    Create a new employee and upload their photo in a single API request.

    Parameters:
        token       (str):   JWT access token
        emp_data    (dict):  employee form fields
        photo_bytes (bytes): JPEG image data

    Returns:
        tuple: (success: bool, message: str)
    """
    headers = {'Authorization': f'Bearer {token}'}
    files   = {'photo': ('photo.jpg', io.BytesIO(photo_bytes), 'image/jpeg')}

    try:
        response = requests.post(
            f'{SERVER_URL}/api/employees',
            headers = headers,
            data    = emp_data,
            files   = files,
            timeout = 60,
        )
        if response.ok:
            return True, 'OK'
        return False, response.json().get('error', 'Unknown error')

    except requests.RequestException as err:
        return False, str(err)


def main():
    """
    Load photos from the archive or folder and create one employee per photo.
    """
    parser = argparse.ArgumentParser(
        description='Import employees from a folder or ZIP of face photos.'
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '--archive',
        help='Path to a ZIP file containing face photos',
    )
    group.add_argument(
        '--folder',
        help='Path to a folder containing face photos',
    )
    parser.add_argument(
        '--count',
        type=int,
        default=0,
        help='Limit the number of photos to import (default: all)',
    )
    args = parser.parse_args()

    # Load photos
    if args.archive:
        if not os.path.isfile(args.archive):
            print(f'File not found: {args.archive}')
            sys.exit(1)
        print(f'Reading photos from {args.archive} ...')
        photos = load_photos_from_zip(args.archive)
    else:
        if not os.path.isdir(args.folder):
            print(f'Folder not found: {args.folder}')
            sys.exit(1)
        print(f'Reading photos from {args.folder} ...')
        photos = load_photos_from_folder(args.folder)

    if not photos:
        print('No JPEG photos found in the provided source.')
        sys.exit(1)

    if args.count > 0:
        photos = photos[:args.count]

    print(f'Photos to import: {len(photos)}')

    # Authenticate
    token    = get_auth_token()
    existing = get_existing_count(token)

    if existing > 0:
        print(f'Note: {existing} employees already in the database.')
        answer = input('Continue and add more? (y/n): ').strip().lower()
        if answer != 'y':
            print('Cancelled.')
            return

    start_index   = existing + 1
    success_count = 0
    failure_count = 0

    print()
    total = len(photos)

    for i, photo_bytes in enumerate(photos):
        emp_index = start_index + i
        emp_data  = generate_employee_data(emp_index)

        print(
            f'[{i + 1:3d}/{total}] '
            f'{emp_data["last_name"]} {emp_data["first_name"]} '
            f'({emp_data["emp_id"]}) ... ',
            end='', flush=True,
        )

        ok, message = upload_employee(token, emp_data, photo_bytes)

        if ok:
            print('OK')
            success_count += 1
        else:
            print(f'FAILED ({message})')
            failure_count += 1

    print()
    print('Import complete.')
    print(f'  Created : {success_count}')
    print(f'  Failed  : {failure_count}')


if __name__ == '__main__':
    main()
