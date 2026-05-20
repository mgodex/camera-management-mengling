from flask_login import LoginManager

login_manager = LoginManager()
login_manager.login_view = 'pages.login_page'
login_manager.login_message = '请先登录'
