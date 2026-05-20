import os
import subprocess
import threading
import time
import queue
import shutil

FFMPEG_AVAILABLE = shutil.which('ffmpeg') is not None
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
HLS_DIR = os.path.join(DATA_DIR, 'hls')


class CameraStream:
    """MJPEG stream (used by dashboard)."""
    def __init__(self, camera_id, rtsp_url, fps=15):
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.fps = fps
        self.process = None
        self.thread = None
        self.running = False
        self.frame_queue = queue.Queue(maxsize=2)
        self.last_access = time.time()
        self._buffer = b''

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._reader, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=3)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None

    def get_frame(self, timeout=5):
        self.last_access = time.time()
        try:
            return self.frame_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def _reader(self):
        if not FFMPEG_AVAILABLE:
            self.running = False
            return
        cmd = [
            'ffmpeg', '-rtsp_transport', 'tcp',
            '-fflags', 'nobuffer', '-flags', 'low_delay',
            '-analyzeduration', '2000000',
            '-i', self.rtsp_url,
            '-f', 'image2pipe', '-vcodec', 'mjpeg',
            '-q:v', '1', '-pix_fmt', 'yuvj420p',
            '-r', str(self.fps), '-an',
            '-loglevel', 'error', 'pipe:1',
        ]
        try:
            self.process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0,
            )
            while self.running:
                chunk = self.process.stdout.read(8192)
                if not chunk:
                    break
                self._buffer += chunk
                while True:
                    start = self._buffer.find(b'\xff\xd8')
                    if start == -1:
                        self._buffer = b''
                        break
                    end = self._buffer.find(b'\xff\xd9', start + 2)
                    if end == -1:
                        if start > 0:
                            self._buffer = self._buffer[start:]
                        break
                    jpeg = self._buffer[start:end + 2]
                    self._buffer = self._buffer[end + 2:]
                    if self.frame_queue.full():
                        try:
                            self.frame_queue.get_nowait()
                        except queue.Empty:
                            pass
                    self.frame_queue.put(jpeg)
        except Exception:
            pass
        finally:
            self.running = False
            if self.process:
                try:
                    self.process.terminate()
                except Exception:
                    pass


class HLSStream:
    def __init__(self, camera_id, rtsp_url):
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.process = None
        self.running = False
        self.last_access = time.time()
        self.output_dir = os.path.join(HLS_DIR, camera_id)

    def start(self):
        if self.running:
            return
        self.running = True
        os.makedirs(self.output_dir, exist_ok=True)
        playlist = os.path.join(self.output_dir, 'live.m3u8')
        seg = os.path.join(self.output_dir, 'seg_%03d.ts')
        cmd = [
            'ffmpeg', '-rtsp_transport', 'tcp',
            '-fflags', 'nobuffer', '-flags', 'low_delay',
            '-analyzeduration', '2000000',
            '-i', self.rtsp_url,
            '-c:v', 'libx264', '-preset', 'veryfast',
            '-tune', 'zerolatency', '-crf', '18',
            '-an',
            '-f', 'hls', '-hls_time', '1', '-hls_list_size', '3',
            '-hls_flags', 'delete_segments',
            '-hls_segment_filename', seg,
            '-loglevel', 'error', playlist,
        ]
        try:
            self.process = subprocess.Popen(cmd, stderr=subprocess.DEVNULL)
        except Exception:
            self.running = False

    def is_ready(self, timeout=15):
        playlist = os.path.join(self.output_dir, 'live.m3u8')
        deadline = time.time() + timeout
        while time.time() < deadline:
            if os.path.exists(playlist) and os.path.getsize(playlist) > 50:
                return True
            time.sleep(0.3)
        return False

    def stop(self):
        self.running = False
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=3)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None
        shutil.rmtree(self.output_dir, ignore_errors=True)


class StreamManager:
    def __init__(self):
        self._mjpeg = {}
        self._hls = {}
        self._lock = threading.Lock()
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

    # ── MJPEG (dashboard) ──

    def mjpeg_get_or_create(self, camera_id, rtsp_url):
        with self._lock:
            existing = self._mjpeg.get(camera_id)
            if existing and existing.running:
                existing.last_access = time.time()
                return existing
            st = CameraStream(camera_id, rtsp_url)
            st.start()
            self._mjpeg[camera_id] = st
            return st

    def mjpeg_stop(self, camera_id):
        with self._lock:
            st = self._mjpeg.pop(camera_id, None)
            if st:
                st.stop()

    def mjpeg_get_frame(self, camera_id, timeout=5):
        st = self._mjpeg.get(camera_id)
        if st:
            return st.get_frame(timeout=timeout)
        return None

    # ── HLS (main page) ──

    def hls_get_or_create(self, camera_id, rtsp_url):
        with self._lock:
            existing = self._hls.get(camera_id)
            if existing and existing.running:
                existing.last_access = time.time()
                return existing
            st = HLSStream(camera_id, rtsp_url)
            st.start()
            self._hls[camera_id] = st
            return st

    def hls_stop(self, camera_id):
        with self._lock:
            st = self._hls.pop(camera_id, None)
            if st:
                st.stop()

    def hls_touch(self, camera_id):
        with self._lock:
            st = self._hls.get(camera_id)
            if st:
                st.last_access = time.time()

    def get_hls_dir(self, camera_id):
        return os.path.join(HLS_DIR, camera_id)

    # ── common ──

    def stop_all(self):
        with self._lock:
            for st in list(self._mjpeg.values()):
                st.stop()
            self._mjpeg.clear()
            for st in list(self._hls.values()):
                st.stop()
            self._hls.clear()

    def get_status(self):
        with self._lock:
            now = time.time()
            status = {}
            for sid, s in self._mjpeg.items():
                status[sid] = {'type': 'mjpeg', 'running': s.running,
                               'idle_seconds': int(now - s.last_access)}
            for sid, s in self._hls.items():
                status[sid] = {'type': 'hls', 'running': s.running,
                               'idle_seconds': int(now - s.last_access)}
            return status

    def _cleanup_loop(self):
        while True:
            time.sleep(15)
            now = time.time()
            with self._lock:
                for sid in list(self._mjpeg.keys()):
                    if now - self._mjpeg[sid].last_access > 30:
                        self._mjpeg[sid].stop()
                        del self._mjpeg[sid]
                for sid in list(self._hls.keys()):
                    if now - self._hls[sid].last_access > 120:
                        self._hls[sid].stop()
                        del self._hls[sid]


stream_manager = StreamManager()
