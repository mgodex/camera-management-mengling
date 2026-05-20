import uuid
import secrets
import time
from backend.utils.storage import dashboard_storage


def get_all_dashboards():
    return dashboard_storage().find_all()


def get_dashboard(dashboard_id):
    return dashboard_storage().find_by_id(dashboard_id)


def get_dashboard_by_token(token):
    return dashboard_storage().find_by(token=token)


def create_dashboard(name, camera_ids=None):
    dashboard = {
        'id': str(uuid.uuid4()),
        'name': name,
        'token': secrets.token_urlsafe(16),
        'camera_ids': camera_ids or [],
        'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'updated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    dashboard_storage().insert(dashboard)
    return dashboard


def update_dashboard(dashboard_id, data):
    data['updated_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
    return dashboard_storage().update(dashboard_id, data)


def delete_dashboard(dashboard_id):
    return dashboard_storage().delete(dashboard_id)


def add_camera_to_dashboard(dashboard_id, camera_id):
    dashboard = dashboard_storage().find_by_id(dashboard_id)
    if not dashboard:
        return None
    if camera_id not in dashboard['camera_ids']:
        dashboard['camera_ids'].append(camera_id)
        dashboard['updated_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
        dashboard_storage().update(dashboard_id, dashboard)
    return dashboard


def remove_camera_from_dashboard(dashboard_id, camera_id):
    dashboard = dashboard_storage().find_by_id(dashboard_id)
    if not dashboard:
        return None
    if camera_id in dashboard['camera_ids']:
        dashboard['camera_ids'].remove(camera_id)
        dashboard['updated_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
        dashboard_storage().update(dashboard_id, dashboard)
    return dashboard


def regenerate_token(dashboard_id):
    dashboard = dashboard_storage().find_by_id(dashboard_id)
    if not dashboard:
        return None
    new_token = secrets.token_urlsafe(16)
    dashboard['token'] = new_token
    dashboard['updated_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
    dashboard_storage().update(dashboard_id, dashboard)
    return dashboard
