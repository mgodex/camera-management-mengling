import json
import os
import threading
from backend.config import DATA_DIR


class JsonStorage:
    _instances = {}
    _lock = threading.Lock()

    def __init__(self, filename):
        self.filepath = os.path.join(DATA_DIR, filename)
        self._lock = threading.Lock()
        self._ensure_file()

    def _ensure_file(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        if not os.path.exists(self.filepath):
            with open(self.filepath, 'w') as f:
                json.dump([], f)

    def _read(self):
        with open(self.filepath, 'r') as f:
            return json.load(f)

    def _write(self, data):
        with open(self.filepath, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def find_all(self):
        with self._lock:
            return self._read()

    def find_by_id(self, obj_id):
        with self._lock:
            items = self._read()
            for item in items:
                if item.get('id') == obj_id:
                    return item
            return None

    def find_by(self, **kwargs):
        with self._lock:
            items = self._read()
            for item in items:
                if all(item.get(k) == v for k, v in kwargs.items()):
                    return item
            return None

    def find_all_by(self, **kwargs):
        with self._lock:
            items = self._read()
            return [
                item for item in items
                if all(item.get(k) == v for k, v in kwargs.items())
            ]

    def insert(self, item):
        with self._lock:
            items = self._read()
            items.append(item)
            self._write(items)
            return item

    def update(self, obj_id, new_data):
        with self._lock:
            items = self._read()
            for i, item in enumerate(items):
                if item.get('id') == obj_id:
                    items[i].update(new_data)
                    items[i]['id'] = obj_id
                    self._write(items)
                    return items[i]
            return None

    def delete(self, obj_id):
        with self._lock:
            items = self._read()
            new_items = [item for item in items if item.get('id') != obj_id]
            if len(new_items) == len(items):
                return False
            self._write(new_items)
            return True

    def delete_all(self):
        with self._lock:
            self._write([])


def get_storage(filename):
    if filename not in JsonStorage._instances:
        with JsonStorage._lock:
            if filename not in JsonStorage._instances:
                JsonStorage._instances[filename] = JsonStorage(filename)
    return JsonStorage._instances[filename]


user_storage = lambda: get_storage('users.json')
camera_storage = lambda: get_storage('cameras.json')
dashboard_storage = lambda: get_storage('dashboards.json')
