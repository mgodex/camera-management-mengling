from flask import Flask
from backend.config import SECRET_KEY
from backend.extensions import login_manager
from backend.services.auth_service import init_default_user, get_user_by_id


def create_app():
    app = Flask(
        __name__,
        template_folder='../frontend/templates',
        static_folder='../frontend/static',
        static_url_path='/static',
    )
    app.secret_key = SECRET_KEY

    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return get_user_by_id(user_id)

    from backend.api.auth import auth_bp
    from backend.api.cameras import cameras_bp
    from backend.api.dashboard import dashboard_bp
    from backend.api.stream import stream_bp
    from backend.api.pages import pages_bp
    from backend.api.recording import recording_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(cameras_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(stream_bp)
    app.register_blueprint(pages_bp)
    app.register_blueprint(recording_bp)

    init_default_user()

    return app
