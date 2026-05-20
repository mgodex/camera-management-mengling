import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
SECRET_KEY = os.environ.get('SECRET_KEY', 'camera-management-secret-key-change-in-production')
DEFAULT_USERNAME = 'admin'
DEFAULT_PASSWORD = 'admin123'
