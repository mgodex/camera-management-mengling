import os
import re
from flask import Blueprint, request, send_from_directory
from flask_login import login_required
from backend.services.recording_service import recording_manager
from backend.services.camera_service import get_camera, get_all_cameras
from backend.utils.response import success, bad_request, not_found

recording_bp = Blueprint('recording', __name__)


@recording_bp.route('/api/recording/config', methods=['GET'])
@login_required
def get_config():
    cfg = recording_manager.get_config()
    return success(data={
        'retention_days': cfg.get('retention_days', 7),
        'storage_path': cfg.get('storage_path', ''),
    })


@recording_bp.route('/api/recording/config', methods=['PUT'])
@login_required
def update_config():
    data = request.get_json() or {}
    cfg = recording_manager.update_config(data)
    return success(data={
        'retention_days': cfg.get('retention_days', 7),
        'storage_path': cfg.get('storage_path', ''),
    })


@recording_bp.route('/api/recording/cameras', methods=['GET'])
@login_required
def list_recording_cameras():
    cameras = get_all_cameras()
    active = recording_manager.get_active_recordings()
    result = []
    for cam in cameras:
        cid = cam['id']
        rec_info = active.get(cid, {})
        is_rec = rec_info.get('running', False)
        exit_code = rec_info.get('exit_code')
        error = ''
        if not is_rec and cam.get('record_enabled') and exit_code is not None:
            error = recording_manager.get_recording_error(cid)
        result.append({
            'id': cid,
            'name': cam.get('name', ''),
            'host': cam.get('host', ''),
            'record_enabled': cam.get('record_enabled', False),
            'is_recording': is_rec,
            'status': cam.get('status', 'offline'),
            'recording_error': error,
            'has_recordings': recording_manager._has_recordings(cid),
        })
    return success(data=result)


@recording_bp.route('/api/recording/start-all', methods=['POST'])
@login_required
def start_all():
    cameras = get_all_cameras()
    started = 0
    failed = 0
    for cam in cameras:
        if cam.get('record_enabled') and cam.get('rtsp_url'):
            ok = recording_manager.start_recording(cam['id'], cam['rtsp_url'])
            if ok:
                started += 1
            else:
                failed += 1
    return success(data={'started': started, 'failed': failed})


@recording_bp.route('/api/recording/stop-all', methods=['POST'])
@login_required
def stop_all():
    recording_manager.stop_all()
    return success(message='已停止所有录制')


@recording_bp.route('/api/recording/<camera_id>/files', methods=['GET'])
@login_required
def get_files(camera_id):
    cam = get_camera(camera_id)
    if not cam:
        return not_found('摄像头不存在')
    date = request.args.get('date', '')
    files = recording_manager.get_recording_files(camera_id, date)
    dates = recording_manager.get_recording_dates(camera_id)
    # Optional time range filter
    start_time = request.args.get('start_time', '')
    end_time = request.args.get('end_time', '')
    if start_time:
        files = [f for f in files if f.get('time', '') >= start_time]
    if end_time:
        files = [f for f in files if f.get('time', '') <= end_time]
    return success(data={
        'camera': {
            'id': cam['id'],
            'name': cam.get('name', ''),
            'host': cam.get('host', ''),
        },
        'files': files,
        'dates': dates,
    })


@recording_bp.route('/api/recording/<camera_id>/timeline', methods=['GET'])
@login_required
def get_timeline(camera_id):
    cam = get_camera(camera_id)
    if not cam:
        return not_found('摄像头不存在')
    date = request.args.get('date', '')
    if not date:
        return bad_request('需要 date 参数 (YYYYMMDD)')
    files = recording_manager.get_recording_files(camera_id, date)
    timeline = [{'hour': f'{h:02d}', 'has_data': False, 'file_count': 0} for h in range(24)]
    for f in files:
        h = int(f['time'][:2])
        if h < 24:
            timeline[h]['has_data'] = True
            timeline[h]['file_count'] += 1
    return success(data=timeline)


@recording_bp.route('/api/recording/<camera_id>/file/<path:filename>')
@login_required
def serve_file(camera_id, filename):
    cam = get_camera(camera_id)
    if not cam:
        return not_found('摄像头不存在')
    safe = re.sub(r'[^a-zA-Z0-9_.\-]', '', filename)
    if not safe:
        return bad_request('非法文件名')
    cam_dir = recording_manager._camera_dir(camera_id)
    ext = os.path.splitext(safe)[1].lower()
    if ext == '.m4s':
        mime = 'video/iso.segment'
    elif ext == '.mp4':
        mime = 'video/mp4'
    else:
        mime = 'video/mp2t'
    return send_from_directory(cam_dir, safe, mimetype=mime)


@recording_bp.route('/api/recording/<camera_id>/playlist')
@login_required
def serve_playlist(camera_id):
    cam = get_camera(camera_id)
    if not cam:
        return not_found('摄像头不存在')
    date = request.args.get('date', '')
    if not date:
        return bad_request('需要 date 参数 (YYYYMMDD)')
    start_time = request.args.get('start_time', '')  # HHMM
    end_time = request.args.get('end_time', '')      # HHMM
    files = recording_manager.get_recording_files(camera_id, date)
    if not files:
        return not_found('该日期无录像文件')

    # Filter by time range
    if start_time:
        files = [f for f in files if f.get('time', '') >= start_time]
    if end_time:
        files = [f for f in files if f.get('time', '') <= end_time]

    if not files:
        return not_found('该时间段无录像文件')

    lines = ['#EXTM3U', '#EXT-X-PLAYLIST-TYPE:VOD', '#EXT-X-VERSION:7',
             '#EXT-X-TARGETDURATION:10', '#EXT-X-MEDIA-SEQUENCE:0']

    has_init = recording_manager.has_init_segment(camera_id)
    if has_init:
        lines.append('#EXT-X-MAP:URI="file/init.mp4"')

    seg_duration = 10
    for i, f in enumerate(files):
        dur = seg_duration
        if i == len(files) - 1:
            dur = recording_manager._estimate_duration(
                recording_manager._camera_dir(camera_id), f['filename']
            )
        lines.append(f'#EXTINF:{dur:.3f},')
        lines.append(f'file/{f["filename"]}')
    lines.append('#EXT-X-ENDLIST')
    from flask import Response
    return Response('\n'.join(lines), mimetype='application/vnd.apple.mpegurl')
