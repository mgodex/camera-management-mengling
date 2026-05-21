import os
from flask import Blueprint, Response, send_from_directory, request
from flask_login import login_required, current_user
from backend.services.stream_service import stream_manager, FFMPEG_AVAILABLE
from backend.services.camera_service import get_camera
from backend.services import dashboard_service
from backend.utils.response import success, not_found, bad_request, unauthorized

stream_bp = Blueprint('stream', __name__)


@stream_bp.route('/api/stream/ffmpeg-check', methods=['GET'])
@login_required
def ffmpeg_check():
    return success(data={'available': FFMPEG_AVAILABLE})


@stream_bp.route('/api/stream/status', methods=['GET'])
@login_required
def stream_status():
    return success(data=stream_manager.get_status())


# ── HLS (main page) ──

@stream_bp.route('/api/stream/<camera_id>/hls/start', methods=['POST'])
def hls_start(camera_id):
    token = request.args.get('token', '')
    print(f'[DEBUG hls_start] camera={camera_id} token={token}')
    authed = _check_dashboard_token(camera_id, token)
    print(f'[DEBUG hls_start] token_check={authed} user_auth={current_user.is_authenticated}')
    if not authed:
        if not current_user.is_authenticated:
            return unauthorized('未授权')
    if not FFMPEG_AVAILABLE:
        return bad_request('系统未安装 FFmpeg')
    camera = get_camera(camera_id)
    if not camera:
        return not_found('摄像头不存在')
    rtsp_url = camera.get('rtsp_url', '')
    if not rtsp_url:
        return bad_request('RTSP 地址未配置')
    hls = stream_manager.hls_get_or_create(camera_id, rtsp_url)
    if hls is None:
        return bad_request('系统繁忙，请稍后再试')
    ready = hls.is_ready(timeout=15)
    print(f'[DEBUG hls_start] camera={camera_id} ready={ready}')
    if ready:
        return success(data={'playlist': f'/api/stream/{camera_id}/hls/live.m3u8'})
    stream_manager.hls_stop(camera_id)
    return bad_request('无法连接到摄像头')


@stream_bp.route('/api/stream/<camera_id>/hls/stop', methods=['POST'])
def hls_stop(camera_id):
    token = request.args.get('token', '')
    if not _check_dashboard_token(camera_id, token):
        if not current_user.is_authenticated:
            return unauthorized('未授权')
    stream_manager.hls_stop(camera_id)
    return success(message='已停止')


@stream_bp.route('/api/stream/<camera_id>/hls/<path:filename>')
def hls_files(camera_id, filename):
    if filename.endswith('.m3u8'):
        token = request.args.get('token', '')
        if not _check_dashboard_token(camera_id, token):
            if not current_user.is_authenticated:
                return unauthorized('未授权')
    # .ts segments: auth already validated at hls_start, camera_id is UUID, skip re-check for hls.js compatibility
    stream_manager.hls_touch(camera_id)
    hls_dir = stream_manager.get_hls_dir(camera_id)
    if filename.endswith('.m3u8'):
        return send_from_directory(hls_dir, filename, mimetype='application/vnd.apple.mpegurl')
    return send_from_directory(hls_dir, filename, mimetype='video/mp2t')


# ── MJPEG (dashboard) ──

def _check_dashboard_token(camera_id, token):
    if not token:
        return False
    dashboard = dashboard_service.get_dashboard_by_token(token)
    if not dashboard:
        return False
    return camera_id in dashboard.get('camera_ids', [])


@stream_bp.route('/api/stream/<camera_id>/mjpeg')
def mjpeg_stream(camera_id):
    token = request.args.get('token', '')
    if not _check_dashboard_token(camera_id, token):
        if not current_user.is_authenticated:
            return unauthorized('未授权')
    if not FFMPEG_AVAILABLE:
        return bad_request('系统未安装 FFmpeg')
    camera = get_camera(camera_id)
    if not camera:
        return not_found('摄像头不存在')
    rtsp_url = camera.get('rtsp_url', '')
    if not rtsp_url:
        return bad_request('RTSP 地址未配置')
    stream = stream_manager.mjpeg_get_or_create(camera_id, rtsp_url)
    if stream is None:
        return bad_request('系统繁忙，请稍后再试')

    def generate():
        retries = 0
        while retries < 60:
            frame = stream.get_frame(timeout=2)
            if frame is None:
                retries += 1
                continue
            retries = 0
            yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n'

    return Response(
        generate(),
        mimetype='multipart/x-mixed-replace; boundary=frame',
        headers={
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0',
        },
    )
