import json
from flask import Blueprint, request, Response, stream_with_context
from flask_login import login_required
from backend.services import camera_service
from backend.utils.response import success, bad_request, not_found, created

cameras_bp = Blueprint('cameras', __name__)


def _sanitize(cam):
    return cam


@cameras_bp.route('/api/cameras', methods=['GET'])
@login_required
def list_cameras():
    cameras = camera_service.get_all_cameras()
    return success(data=[_sanitize(c) for c in cameras])


@cameras_bp.route('/api/cameras', methods=['POST'])
@login_required
def add_camera():
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    host = data.get('host', '').strip()
    rtsp_url = data.get('rtsp_url', '').strip()

    if not name:
        return bad_request('摄像头名称不能为空')
    if not host and not rtsp_url:
        return bad_request('请输入IP地址或RTSP地址')

    port_raw = data.get('port')
    try:
        port = int(port_raw) if port_raw else None
    except (ValueError, TypeError):
        port = None

    camera = camera_service.add_camera(
        name=name,
        host=host,
        rtsp_url=rtsp_url,
        username=data.get('username', ''),
        password=data.get('password', ''),
        port=port,
        path=data.get('path', ''),
        brand=data.get('brand', ''),
        stream_type=data.get('stream_type', 'sub'),
        location=data.get('location', ''),
        remark=data.get('remark', ''),
    )
    return created(data=_sanitize(camera))


@cameras_bp.route('/api/cameras/<camera_id>', methods=['GET'])
@login_required
def get_camera(camera_id):
    camera = camera_service.get_camera(camera_id)
    if not camera:
        return not_found('摄像头不存在')
    return success(data=_sanitize(camera))


@cameras_bp.route('/api/cameras/<camera_id>', methods=['PUT'])
@login_required
def update_camera(camera_id):
    camera = camera_service.get_camera(camera_id)
    if not camera:
        return not_found('摄像头不存在')

    data = request.get_json() or {}
    camera_service.update_camera(camera_id, data)
    updated = camera_service.get_camera(camera_id)
    return success(data=_sanitize(updated), message='更新成功')


@cameras_bp.route('/api/cameras/<camera_id>', methods=['DELETE'])
@login_required
def delete_camera(camera_id):
    if camera_service.delete_camera(camera_id):
        return success(message='删除成功')
    return not_found('摄像头不存在')


@cameras_bp.route('/api/cameras/scan', methods=['POST'])
@login_required
def scan_cameras():
    devices = camera_service.scan_network()
    return success(data=devices, message='扫描完成')


@cameras_bp.route('/api/cameras/scan-stream', methods=['GET'])
@login_required
def scan_stream():
    def generate():
        for device in camera_service.scan_network_stream():
            yield f'data: {json.dumps(device, ensure_ascii=False)}\n\n'
        yield 'data: {"type": "done"}\n\n'

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        },
    )


@cameras_bp.route('/api/cameras/brand-presets', methods=['GET'])
@login_required
def brand_presets():
    presets = []
    for key, val in camera_service.BRAND_PRESETS.items():
        presets.append({
            'id': key, 'label': val['label'], 'port': val['port'],
            'streams': val['streams'],
        })
    return success(data=presets)


@cameras_bp.route('/api/cameras/check-status', methods=['POST'])
@login_required
def check_status():
    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        data = {}
    camera_ids = data.get('camera_ids')
    results = camera_service.batch_check_status(camera_ids=camera_ids, timeout=3)
    return success(data=results)
