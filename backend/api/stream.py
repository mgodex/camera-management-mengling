import os
from flask import Blueprint, Response, send_from_directory
from flask_login import login_required
from backend.services.stream_service import stream_manager, FFMPEG_AVAILABLE
from backend.services.camera_service import get_camera
from backend.utils.response import success, not_found, bad_request

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
@login_required
def hls_start(camera_id):
    if not FFMPEG_AVAILABLE:
        return bad_request('系统未安装 FFmpeg')
    camera = get_camera(camera_id)
    if not camera:
        return not_found('摄像头不存在')
    rtsp_url = camera.get('rtsp_url', '')
    if not rtsp_url:
        return bad_request('RTSP 地址未配置')
    hls = stream_manager.hls_get_or_create(camera_id, rtsp_url)
    if hls.is_ready(timeout=15):
        return success(data={'playlist': f'/api/stream/{camera_id}/hls/live.m3u8'})
    stream_manager.hls_stop(camera_id)
    return bad_request('无法连接到摄像头')


@stream_bp.route('/api/stream/<camera_id>/hls/stop', methods=['POST'])
@login_required
def hls_stop(camera_id):
    stream_manager.hls_stop(camera_id)
    return success(message='已停止')


@stream_bp.route('/api/stream/<camera_id>/hls/<path:filename>')
@login_required
def hls_files(camera_id, filename):
    stream_manager.hls_touch(camera_id)
    hls_dir = stream_manager.get_hls_dir(camera_id)
    if filename.endswith('.m3u8'):
        return send_from_directory(hls_dir, filename, mimetype='application/vnd.apple.mpegurl')
    return send_from_directory(hls_dir, filename, mimetype='video/mp2t')


# ── MJPEG (dashboard) ──

@stream_bp.route('/api/stream/<camera_id>/mjpeg')
@login_required
def mjpeg_stream(camera_id):
    if not FFMPEG_AVAILABLE:
        return bad_request('系统未安装 FFmpeg')
    camera = get_camera(camera_id)
    if not camera:
        return not_found('摄像头不存在')
    rtsp_url = camera.get('rtsp_url', '')
    if not rtsp_url:
        return bad_request('RTSP 地址未配置')
    stream = stream_manager.mjpeg_get_or_create(camera_id, rtsp_url)

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
