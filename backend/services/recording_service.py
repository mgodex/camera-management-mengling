import os
import json
import time
import threading
import subprocess
import shutil

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
CONFIG_FILE = os.path.join(DATA_DIR, 'recording_config.json')

DEFAULT_CONFIG = {
    'retention_days': 7,
    'storage_path': os.path.join(DATA_DIR, 'recordings'),
}


def _load_config():
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(DEFAULT_CONFIG)


def _save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


class RecordingManager:
    def __init__(self):
        self._processes = {}       # camera_id -> subprocess.Popen
        self._lock = threading.Lock()
        # Background threads
        threading.Thread(target=self._init_loop, daemon=True).start()
        threading.Thread(target=self._health_loop, daemon=True).start()
        threading.Thread(target=self._cleanup_loop, daemon=True).start()

    def _init_loop(self):
        """Start recordings in background with staggered delay (no limit)."""
        time.sleep(3)
        try:
            from backend.services.camera_service import get_all_cameras
            cameras = get_all_cameras()
            for i, cam in enumerate(cameras):
                if cam.get('record_enabled') and cam.get('rtsp_url'):
                    time.sleep(i * 1.5)
                    ok, msg = self.start_recording(cam['id'], cam['rtsp_url'])
                    print(f'[RecordingManager] init {cam["id"]}: {"OK" if ok else "FAIL " + msg}')
        except Exception as e:
            print(f'[RecordingManager] init error: {e}')

    # ── Config ──

    def get_config(self):
        return _load_config()

    def update_config(self, cfg):
        merged = dict(self.get_config())
        if 'retention_days' in cfg:
            merged['retention_days'] = int(cfg['retention_days'])
        if 'storage_path' in cfg:
            merged['storage_path'] = cfg['storage_path']
        _save_config(merged)
        return merged

    def _get_storage_path(self):
        return self.get_config().get('storage_path', DEFAULT_CONFIG['storage_path'])

    def _camera_dir(self, camera_id):
        return os.path.join(self._get_storage_path(), camera_id)

    # ── Start / Stop ──

    def start_recording(self, camera_id, rtsp_url):
        with self._lock:
            existing = self._processes.get(camera_id)
            if existing and existing.poll() is None:
                return True, 'already_running'

            cam_dir = self._camera_dir(camera_id)
            os.makedirs(cam_dir, exist_ok=True)

            cmd = [
                'ffmpeg', '-rtsp_transport', 'tcp',
                '-fflags', 'nobuffer', '-flags', 'low_delay',
                '-analyzeduration', '2000000',
                '-i', rtsp_url,
                '-c:v', 'libx264', '-preset', 'veryfast',
                '-tune', 'zerolatency', '-crf', '18',
                '-an',
                '-f', 'hls', '-hls_time', '10', '-hls_list_size', '0',
                '-hls_segment_type', 'fmp4',
                '-hls_flags', 'independent_segments',
                '-hls_segment_filename', os.path.join(cam_dir, 'seg_%05d.m4s'),
                '-loglevel', 'error',
                os.path.join(cam_dir, 'index.m3u8'),
            ]

            try:
                logfile = os.path.join(cam_dir, 'recorder.log')
                proc = subprocess.Popen(
                    cmd, stderr=open(logfile, 'w'), stdout=subprocess.DEVNULL,
                )
                self._processes[camera_id] = proc
                return True, 'started'
            except Exception as e:
                return False, str(e)

    def stop_recording(self, camera_id):
        with self._lock:
            proc = self._processes.pop(camera_id, None)
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def stop_all(self):
        for cid in list(self._processes.keys()):
            self.stop_recording(cid)

    def get_active_recordings(self):
        result = {}
        with self._lock:
            for cid, proc in list(self._processes.items()):
                running = proc.poll() is None
                result[cid] = {
                    'running': running,
                    'exit_code': proc.poll() if not running else None,
                }
        return result

    def get_recording_error(self, camera_id):
        cam_dir = self._camera_dir(camera_id)
        logfile = os.path.join(cam_dir, 'recorder.log')
        try:
            with open(logfile) as f:
                content = f.read().strip()
                return content[-500:] if content else ''
        except (FileNotFoundError, IOError):
            return ''

    # ── Health check (30s loop, infinite retry) ──

    def _health_loop(self):
        while True:
            time.sleep(30)
            try:
                self._check_and_restart()
            except Exception as e:
                print(f'[RecordingManager] health error: {e}')

    def _check_and_restart(self):
        dead = []
        with self._lock:
            for cid, proc in list(self._processes.items()):
                if proc.poll() is not None:
                    dead.append((cid, proc.poll()))

        if not dead:
            return

        try:
            from backend.services.camera_service import get_camera
        except Exception:
            return

        for cid, exit_code in dead:
            with self._lock:
                if cid not in self._processes:
                    continue
                del self._processes[cid]

            cam = get_camera(cid)
            if cam and cam.get('record_enabled') and cam.get('rtsp_url'):
                print(f'[RecordingManager] restarting {cid} (exit={exit_code})')
                ok, msg = self.start_recording(cid, cam['rtsp_url'])
                if ok:
                    print(f'[RecordingManager] restarted {cid}')
                else:
                    print(f'[RecordingManager] restart failed {cid}: {msg}')
            else:
                self.stop_recording(cid)

    # ── Recording presence check ──

    def _has_recordings(self, camera_id):
        cam_dir = self._camera_dir(camera_id)
        if not os.path.isdir(cam_dir):
            return False
        for f in os.listdir(cam_dir):
            if f.endswith('.m4s') and not f.startswith('init'):
                return True
        return False

    # ── File listing (mtime-based date filtering) ──

    def get_recording_files(self, camera_id, date_str=None):
        cam_dir = self._camera_dir(camera_id)
        if not os.path.isdir(cam_dir):
            return []

        all_files = []
        for f in sorted(os.listdir(cam_dir)):
            if not f.endswith('.m4s'):
                continue
            filepath = os.path.join(cam_dir, f)
            mtime = os.path.getmtime(filepath)
            file_date = time.strftime('%Y%m%d', time.localtime(mtime))
            file_time = time.strftime('%H%M%S', time.localtime(mtime))

            if date_str and file_date != date_str:
                continue

            stat = os.stat(filepath)
            all_files.append({
                'filename': f,
                'size': stat.st_size,
                'mtime': int(mtime),
                'date': file_date,
                'time': file_time,
                'duration': self._estimate_duration(cam_dir, f),
            })
        return all_files

    def get_recording_dates(self, camera_id):
        cam_dir = self._camera_dir(camera_id)
        if not os.path.isdir(cam_dir):
            return []
        dates = set()
        for f in os.listdir(cam_dir):
            if not f.endswith('.m4s'):
                continue
            fp = os.path.join(cam_dir, f)
            dates.add(time.strftime('%Y%m%d', time.localtime(os.path.getmtime(fp))))
        return sorted(dates, reverse=True)

    def has_init_segment(self, camera_id):
        return os.path.isfile(os.path.join(self._camera_dir(camera_id), 'init.mp4'))

    def _estimate_duration(self, cam_dir, filename):
        try:
            size = os.path.getsize(os.path.join(cam_dir, filename))
            bitrate = 2_000_000
            return max(1, size * 8 // bitrate)
        except Exception:
            return 0

    # ── Cleanup old files (hourly) ──

    def _cleanup_loop(self):
        while True:
            time.sleep(3600)
            try:
                self._cleanup_old_files()
            except Exception:
                pass

    def _cleanup_old_files(self):
        cfg = self.get_config()
        retention = cfg.get('retention_days', DEFAULT_CONFIG['retention_days'])
        storage = cfg.get('storage_path', DEFAULT_CONFIG['storage_path'])
        if not os.path.isdir(storage):
            return
        cutoff = time.time() - retention * 86400
        for cid in os.listdir(storage):
            cam_dir = os.path.join(storage, cid)
            if not os.path.isdir(cam_dir):
                continue
            for f in os.listdir(cam_dir):
                if f == 'init.mp4':
                    continue
                if not f.endswith(('.ts', '.m4s', '.mp4', '.m3u8', '.log')):
                    continue
                fp = os.path.join(cam_dir, f)
                try:
                    if os.path.getmtime(fp) < cutoff:
                        os.remove(fp)
                except OSError:
                    pass


recording_manager = RecordingManager()
