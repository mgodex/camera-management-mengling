from flask import Blueprint, request
from flask_login import login_required
from backend.services import dashboard_service, camera_service
from backend.utils.response import success, bad_request, not_found, created

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/api/dashboards', methods=['GET'])
@login_required
def list_dashboards():
    dashboards = dashboard_service.get_all_dashboards()
    return success(data=dashboards)


@dashboard_bp.route('/api/dashboards', methods=['POST'])
@login_required
def create_dashboard():
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    if not name:
        return bad_request('大屏名称不能为空')
    dashboard = dashboard_service.create_dashboard(
        name=name,
        camera_ids=data.get('camera_ids'),
    )
    return created(data=dashboard)


@dashboard_bp.route('/api/dashboards/<dashboard_id>', methods=['GET'])
@login_required
def get_dashboard(dashboard_id):
    dashboard = dashboard_service.get_dashboard(dashboard_id)
    if not dashboard:
        return not_found('大屏不存在')

    cameras = []
    for cid in dashboard.get('camera_ids', []):
        cam = camera_service.get_camera(cid)
        if cam:
            cameras.append(cam)
    dashboard['cameras'] = cameras
    return success(data=dashboard)


@dashboard_bp.route('/api/dashboards/<dashboard_id>', methods=['PUT'])
@login_required
def update_dashboard(dashboard_id):
    dashboard = dashboard_service.get_dashboard(dashboard_id)
    if not dashboard:
        return not_found('大屏不存在')
    data = request.get_json() or {}
    dashboard_service.update_dashboard(dashboard_id, data)
    updated = dashboard_service.get_dashboard(dashboard_id)
    return success(data=updated, message='更新成功')


@dashboard_bp.route('/api/dashboards/<dashboard_id>', methods=['DELETE'])
@login_required
def delete_dashboard(dashboard_id):
    if dashboard_service.delete_dashboard(dashboard_id):
        return success(message='删除成功')
    return not_found('大屏不存在')


@dashboard_bp.route('/api/dashboards/<dashboard_id>/cameras', methods=['POST'])
@login_required
def add_camera(dashboard_id):
    data = request.get_json() or {}
    camera_id = data.get('camera_id')
    if not camera_id:
        return bad_request('请指定摄像头ID')

    camera = camera_service.get_camera(camera_id)
    if not camera:
        return not_found('摄像头不存在')

    result = dashboard_service.add_camera_to_dashboard(dashboard_id, camera_id)
    if not result:
        return not_found('大屏不存在')
    return success(data=result, message='添加成功')


@dashboard_bp.route('/api/dashboards/<dashboard_id>/cameras/<camera_id>', methods=['DELETE'])
@login_required
def remove_camera(dashboard_id, camera_id):
    result = dashboard_service.remove_camera_from_dashboard(dashboard_id, camera_id)
    if not result:
        return not_found('大屏不存在')
    return success(data=result, message='移除成功')


@dashboard_bp.route('/api/dashboards/<dashboard_id>/regenerate-token', methods=['POST'])
@login_required
def regenerate_token(dashboard_id):
    result = dashboard_service.regenerate_token(dashboard_id)
    if not result:
        return not_found('大屏不存在')
    return success(data=result, message='Token已重新生成')


@dashboard_bp.route('/api/dashboards/share/<token>', methods=['GET'])
def share_dashboard(token):
    dashboard = dashboard_service.get_dashboard_by_token(token)
    if not dashboard:
        return not_found('大屏不存在或链接已失效')

    cameras = []
    for cid in dashboard.get('camera_ids', []):
        cam = camera_service.get_camera(cid)
        if cam:
            cameras.append(cam)
    dashboard['cameras'] = cameras
    return success(data=dashboard)
