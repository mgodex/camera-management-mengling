import socket
from flask import Blueprint, render_template
from flask_login import login_required
from backend.utils.response import success

pages_bp = Blueprint('pages', __name__)


@pages_bp.route('/')
@login_required
def index():
    return render_template('cameras.html')


@pages_bp.route('/login')
def login_page():
    return render_template('login.html')


@pages_bp.route('/dashboard-view/<token>')
def dashboard_view(token):
    return render_template('dashboard.html', token=token)


@pages_bp.route('/api/system/lan-ip')
def get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        s.connect(('10.254.254.254', 1))
        ip = s.getsockname()[0]
        s.close()
        return success(data={'ip': ip, 'port': 5500})
    except Exception:
        return success(data={'ip': '127.0.0.1', 'port': 5500})
