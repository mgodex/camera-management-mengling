from backend.app import create_app
from backend.services.auth_service import DEFAULT_PASSWORD

app = create_app()

if __name__ == '__main__':
    print('=' * 50)
    print('  萌灵摄像头管理启动成功')
    print('  访问地址: http://localhost:5500')
    print(f'  默认账号: admin / {DEFAULT_PASSWORD}')
    print('=' * 50)   
    app.run(host='0.0.0.0', port=5500, debug=True)
