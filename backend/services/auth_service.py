import uuid
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from backend.utils.storage import user_storage

DEFAULT_PASSWORD = 'no-password'


class User(UserMixin):
    def __init__(self, id, username, password_hash):
        self.id = id
        self.username = username
        self.password_hash = password_hash

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
        }


def init_default_user():
    store = user_storage()
    existing = store.find_by(username='admin')
    if not existing:
        user = {
            'id': str(uuid.uuid4()),
            'username': 'admin',
            'password_hash': generate_password_hash(DEFAULT_PASSWORD, method='pbkdf2:sha256'),
        }
        store.insert(user)


def get_user_by_id(user_id):
    store = user_storage()
    data = store.find_by_id(user_id)
    if data:
        return User(
            id=data['id'],
            username=data['username'],
            password_hash=data['password_hash'],
        )
    return None


def authenticate(username, password):
    store = user_storage()
    data = store.find_by(username=username)
    if data and check_password_hash(data['password_hash'], password):
        return User(
            id=data['id'],
            username=data['username'],
            password_hash=data['password_hash'],
        )
    return None


def is_default_password(username):
    store = user_storage()
    data = store.find_by(username=username)
    if data:
        return check_password_hash(data['password_hash'], DEFAULT_PASSWORD)
    return False


def change_password(username, old_password, new_password):
    store = user_storage()
    data = store.find_by(username=username)
    if not data:
        return False, '用户不存在'
    if not check_password_hash(data['password_hash'], old_password):
        return False, '原密码错误'
    if not new_password or len(new_password) < 6:
        return False, '新密码至少6位'
    store.update(data['id'], {
        'password_hash': generate_password_hash(new_password, method='pbkdf2:sha256'),
    })
    return True, '密码修改成功，请重新登录'
