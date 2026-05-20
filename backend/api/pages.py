from flask import Blueprint, render_template
from flask_login import login_required

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
    return render_template('dashboard.html', token=token, public=True)
