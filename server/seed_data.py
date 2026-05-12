"""
seed_data.py

Script for populating the face recognition system with test data.

Creates 100 employees with realistic Russian names and downloads
a unique AI-generated face photo for each from thispersondoesnotexist.com.
Photos are uploaded to the running Flask server via the REST API.

Usage:
    python seed_data.py

Requirements:
    pip install faker requests Pillow

The Flask server must be running at http://localhost:5000 before
executing this script.  Default credentials admin/admin are used.
"""

import time
import random
import sys
import io
import requests
from faker import Faker

# Server address and login credentials
SERVER_URL = 'http://localhost:5000'
ADMIN_USER = 'admin'
ADMIN_PASS = 'admin'

# Total number of employees to create
EMPLOYEE_COUNT = 100

# Delay in seconds between photo downloads to avoid rate limiting
DOWNLOAD_DELAY = 1.5

# Initialize Faker with Russian locale for realistic names
fake = Faker('ru_RU')
Faker.seed(42)
random.seed(42)

# Departments and positions used in the generated data
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
    'Заместитель директора',
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
        str: JWT token string

    Raises:
        SystemExit: if authentication fails
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

        token = response.json()['access_token']
        print('Authentication successful.')
        return token

    except requests.ConnectionError:
        print(f'Cannot connect to the server at {SERVER_URL}.')
        print('Make sure the Flask server is running: python app.py')
        sys.exit(1)


def download_face_photo():
    """
    Download a randomly generated face image from thispersondoesnotexist.com.

    The service returns a unique AI-generated portrait on every request.
    The image always contains a single clear frontal face suitable for
    embedding extraction.

    Returns:
        bytes: JPEG image data, or None if the download failed
    """
    try:
        response = requests.get(
            'https://thispersondoesnotexist.com',
            timeout=15,
            headers={'User-Agent': 'Mozilla/5.0'},
        )
        if response.ok:
            return response.content
        return None

    except requests.RequestException as err:
        print(f'  Photo download error: {err}')
        return None


def build_employee_data(index):
    """
    Generate realistic employee data using the Faker library.

    Gender is randomly selected to ensure a mix of male and female names.

    Parameters:
        index (int): employee sequence number, used for the employee id

    Returns:
        dict: form fields ready to pass to requests.post(data=...)
    """
    # Randomly choose gender for consistent name generation
    is_male = random.choice([True, False])

    if is_male:
        first_name  = fake.first_name_male()
        last_name   = fake.last_name_male()
        middle_name = fake.middle_name_male()
    else:
        first_name  = fake.first_name_female()
        last_name   = fake.last_name_female()
        middle_name = fake.middle_name_female()

    department = random.choice(DEPARTMENTS)
    position   = random.choice(POSITIONS)
    emp_id     = f'EMP{index:03d}'

    # Generate a plausible corporate email from the last name
    email_name = last_name.lower().replace('ё', 'e')
    email      = f'{email_name}{index}@company.ru'

    return {
        'emp_id':      emp_id,
        'first_name':  first_name,
        'last_name':   last_name,
        'middle_name': middle_name,
        'position':    position,
        'department':  department,
        'email':       email,
        'phone':       fake.phone_number(),
    }


def create_employee(token, employee_data, photo_bytes):
    """
    Send a multipart POST request to create a new employee with a photo.

    Parameters:
        token         (str):   JWT token for Authorization header
        employee_data (dict):  form fields with employee information
        photo_bytes   (bytes): JPEG image data for the employee photo

    Returns:
        tuple: (success: bool, message: str)
    """
    headers = {'Authorization': f'Bearer {token}'}

    files = {
        'photo': ('photo.jpg', io.BytesIO(photo_bytes), 'image/jpeg'),
    }

    try:
        response = requests.post(
            f'{SERVER_URL}/api/employees',
            headers  = headers,
            data     = employee_data,
            files    = files,
            timeout  = 60,  # Allow extra time for embedding extraction
        )

        if response.ok:
            return True, 'Created'
        else:
            error = response.json().get('error', 'Unknown error')
            return False, error

    except requests.RequestException as err:
        return False, str(err)


def check_existing_count(token):
    """
    Return the number of employees already in the database.

    Parameters:
        token (str): JWT token

    Returns:
        int: employee count
    """
    headers  = {'Authorization': f'Bearer {token}'}
    response = requests.get(f'{SERVER_URL}/api/employees', headers=headers, timeout=10)
    if response.ok:
        return len(response.json())
    return 0


def main():
    """
    Main function: authenticate, then create EMPLOYEE_COUNT employees.

    Progress is printed to the console after each employee is processed.
    A summary with success and failure counts is shown at the end.
    """
    print('Face Recognition System — Test Data Seeder')
    print(f'Target: {EMPLOYEE_COUNT} employees')
    print(f'Server: {SERVER_URL}')
    print()

    token = get_auth_token()

    # Check how many employees already exist
    existing = check_existing_count(token)
    if existing > 0:
        print(f'Warning: {existing} employees already exist in the database.')
        answer = input('Continue and add more? (y/n): ').strip().lower()
        if answer != 'y':
            print('Cancelled.')
            return

    # Determine starting index to avoid duplicate employee IDs
    start_index = existing + 1

    success_count = 0
    failure_count = 0

    for i in range(start_index, start_index + EMPLOYEE_COUNT):
        print(f'[{i - start_index + 1}/{EMPLOYEE_COUNT}] ', end='', flush=True)

        # Generate employee data
        emp_data = build_employee_data(i)
        print(f'{emp_data["last_name"]} {emp_data["first_name"]} ({emp_data["emp_id"]}) ... ', end='', flush=True)

        # Download photo
        photo = download_face_photo()
        if photo is None:
            print('FAILED (photo download error)')
            failure_count += 1
            continue

        # Upload to server
        ok, message = create_employee(token, emp_data, photo)

        if ok:
            print('OK')
            success_count += 1
        else:
            print(f'FAILED ({message})')
            failure_count += 1

        # Pause between requests to avoid overloading the server and
        # to respect the rate limit of thispersondoesnotexist.com
        time.sleep(DOWNLOAD_DELAY)

    print()
    print('Seeding complete.')
    print(f'  Created: {success_count}')
    print(f'  Failed:  {failure_count}')

    if failure_count > 0:
        print()
        print('Some employees could not be created.')
        print('Possible reasons:')
        print('  - No face detected in the downloaded image (rare)')
        print('  - Network timeout during photo download')
        print('  - Duplicate employee ID')
        print('Run the script again to retry failed entries.')


if __name__ == '__main__':
    main()
