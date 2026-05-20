from flask import Blueprint, request
from flask_login import login_user, logout_user, login_required, current_user
from backend.services.auth_service import authenticate, is_default_password, change_password as _change_password
from backend.utils.response import success, bad_request, unauthorized

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return bad_request('用户名和密码不能为空')

    user = authenticate(username, password)
    if user is None:
        return unauthorized('用户名或密码错误')

    if is_default_password(username):
        return success(data={'needs_password_change': True}, message='初次使用，请先设置新密码')

    login_user(user)
    return success(data=user.to_dict(), message='登录成功')


@auth_bp.route('/api/auth/change-password', methods=['POST'])
def change_password():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')

    ok, msg = _change_password(username, old_password, new_password)
    if ok:
        return success(message=msg)
    return bad_request(msg)


@auth_bp.route('/api/auth/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return success(message='退出成功')


@auth_bp.route('/api/auth/check', methods=['GET'])
def check():
    if current_user.is_authenticated:
        return success(data=current_user.to_dict())
    return unauthorized('未登录')


@auth_bp.route('/api/auth/default-check', methods=['GET'])
def default_check():
    return success(data={'is_default': is_default_password('admin')})
