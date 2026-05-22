import uuid
import time
import socket
import subprocess
import re
import struct
import concurrent.futures
import xml.etree.ElementTree as ET
from backend.utils.storage import camera_storage

BRAND_PRESETS = {
    'hikvision': {'port': 554, 'label': '海康威视', 'streams': {'main': '/stream2', 'sub': '/stream1'}},
    'dahua': {'port': 554, 'label': '大华', 'streams': {'main': '/cam/realmonitor?channel=1&subtype=0', 'sub': '/cam/realmonitor?channel=1&subtype=1'}},
    'uniview': {'port': 554, 'label': '宇视', 'streams': {'main': '/live/main', 'sub': '/live/sub'}},
    'other': {'port': 554, 'label': '其他', 'streams': {'main': '/stream1', 'sub': '/stream1'}},
}


def _stream_path(brand, stream_type):
    preset = BRAND_PRESETS.get(brand or 'other', BRAND_PRESETS['other'])
    return preset['streams'].get(stream_type, preset['streams']['sub'])


def get_all_cameras():
    return camera_storage().find_all()


def get_camera(camera_id):
    return camera_storage().find_by_id(camera_id)


def add_camera(name, host='', rtsp_url='', username='', password='',
               port=None, path='', brand='', stream_type='sub',
               location='', remark='', record_enabled=False):
    preset = BRAND_PRESETS.get(brand or 'other', BRAND_PRESETS['other'])
    if port is None:
        port = preset['port']
    if not path:
        path = _stream_path(brand, stream_type)
    port = port or 554
    camera = {
        'id': str(uuid.uuid4()),
        'name': name,
        'host': host,
        'port': port,
        'path': path,
        'brand': brand,
        'stream_type': stream_type,
        'username': username,
        'password': password,
        'rtsp_url': rtsp_url or _build_rtsp_url(host, port, path, username, password),
        'location': location,
        'remark': remark,
        'record_enabled': record_enabled,
        'status': 'offline',
        'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'updated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    camera_storage().insert(camera)
    if record_enabled and camera.get('rtsp_url'):
        try:
            from backend.services.recording_service import recording_manager
            ok, msg = recording_manager.start_recording(camera['id'], camera['rtsp_url'])
            if not ok:
                print(f'[camera_service] add_camera start_recording failed for {camera["id"]}: {msg}')
        except Exception as e:
            print(f'[camera_service] add_camera recording error: {e}')
            pass
    return camera


def update_camera(camera_id, data):
    data['updated_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
    cam = get_camera(camera_id)
    if not cam:
        return None

    old_enabled = cam.get('record_enabled', False)
    new_enabled = data.get('record_enabled', old_enabled)

    brand = data.get('brand', cam.get('brand', ''))
    stream_type = data.get('stream_type', cam.get('stream_type', 'sub'))
    if data.get('brand') or data.get('stream_type'):
        data['path'] = _stream_path(brand, stream_type)

    if data.get('host') or data.get('username') or data.get('password') or data.get('brand') or data.get('stream_type'):
        host = data.get('host', cam.get('host', ''))
        port = data.get('port', cam.get('port', 554))
        path = data.get('path', cam.get('path', ''))
        username = data.get('username', cam.get('username', ''))
        password = data.get('password', cam.get('password', ''))
        if 'rtsp_url' not in data:
            data['rtsp_url'] = _build_rtsp_url(host, port, path, username, password)

    data.setdefault('stream_type', stream_type)

    result = camera_storage().update(camera_id, data)

    # Start/stop recording based on record_enabled change
    try:
        from backend.services.recording_service import recording_manager
        rtsp_url = data.get('rtsp_url', cam.get('rtsp_url', ''))
        if new_enabled and not old_enabled and rtsp_url:
            ok, msg = recording_manager.start_recording(camera_id, rtsp_url)
            if not ok:
                print(f'[camera_service] start_recording failed for {camera_id}: {msg}')
        elif old_enabled and not new_enabled:
            recording_manager.stop_recording(camera_id)
    except Exception:
        pass

    return result


def delete_camera(camera_id):
    try:
        from backend.services.recording_service import recording_manager
        recording_manager.stop_recording(camera_id)
    except Exception:
        pass
    return camera_storage().delete(camera_id)


def _build_rtsp_url(host, port, path, username, password):
    if not host:
        return ''
    auth = ''
    if username:
        pw = f':{password}' if password else ''
        auth = f'{username}{pw}@'
    path_clean = path if path.startswith('/') else f'/{path}' if path else '/stream1'
    return f'rtsp://{auth}{host}:{port}{path_clean}'


# ─── Network helpers ───────────────────────────────────────────────


def _get_local_network():
    try:
        result = subprocess.run(['ifconfig'], capture_output=True, text=True, timeout=5)
        for m in re.finditer(r'inet\s+(\d+\.\d+\.\d+\.\d+)\s+netmask\s+(0x[0-9a-fA-F]+)',
                             result.stdout):
            ip = m.group(1)
            if ip.startswith('127.'):
                continue
            mask_int = int(m.group(2), 16)
            mask = '.'.join([
                str((mask_int >> 24) & 0xff),
                str((mask_int >> 16) & 0xff),
                str((mask_int >> 8) & 0xff),
                str(mask_int & 0xff),
            ])
            return ip, mask
    except Exception:
        pass
    return None, None


def _network_from_ip(ip, mask):
    ip_parts = [int(x) for x in ip.split('.')]
    mask_parts = [int(x) for x in mask.split('.')]
    return [ip_parts[i] & mask_parts[i] for i in range(4)]


def _prefix_len(mask):
    return sum(f'{int(x):08b}'.count('1') for x in mask.split('.'))


def _generate_ip_range(local_ip, netmask):
    plen = _prefix_len(netmask)
    if plen < 16:
        plen = 24
    raw = _network_from_ip(local_ip, netmask)
    last_octet = int(local_ip.split('.')[3])

    if plen >= 24:
        return [f'{raw[0]}.{raw[1]}.{raw[2]}.{i}' for i in range(1, 255) if i != last_octet]
    elif plen >= 16:
        return [
            f'{raw[0]}.{raw[1]}.{i}.{j}'
            for i in range(256)
            for j in range(1, 256)
            if not (i == raw[2] and j == last_octet)
        ]
    return []


# ─── TCP port scan (fallback) ─────────────────────────────────────


def _port_open(ip, port, timeout):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        result = s.connect_ex((ip, port))
        s.close()
        return result == 0
    except Exception:
        return False


def _check_device(ip, timeout):
    return [p for p in (554, 80, 8080, 8554) if _port_open(ip, p, timeout)]


def _tcp_scan_subnet(ips, timeout):
    return list(_tcp_scan_subnet_iter(ips, timeout))


def _tcp_scan_subnet_iter(ips, timeout):
    with concurrent.futures.ThreadPoolExecutor(max_workers=80) as pool:
        fut_map = {pool.submit(_check_device, ip, timeout): ip for ip in ips}
        for fut in concurrent.futures.as_completed(fut_map, timeout=120):
            ip = fut_map[fut]
            try:
                ports = fut.result()
                if ports:
                    yield ip
            except Exception:
                pass


# ─── ONVIF WS-Discovery ────────────────────────────────────────────


ONVIF_MCAST_ADDR = '239.255.255.250'
ONVIF_MCAST_PORT = 3702

_WS_PROBE = '''<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope
  xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
  xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing"
  xmlns:wsd="http://schemas.xmlsoap.org/ws/2005/04/discovery"
  xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
  <soap:Header>
    <wsa:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</wsa:Action>
    <wsa:MessageID>uuid:{message_id}</wsa:MessageID>
    <wsa:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</wsa:To>
  </soap:Header>
  <soap:Body>
    <wsd:Probe>
      <wsd:Types>dn:NetworkVideoTransmitter</wsd:Types>
    </wsd:Probe>
  </soap:Body>
</soap:Envelope>'''


def _onvif_discover(timeout=3):
    return list(_onvif_discover_iter(timeout))


def _onvif_discover_iter(timeout=3):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(timeout)
    sock.bind(('0.0.0.0', 0))

    ttl = struct.pack('b', 4)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)

    msg = _WS_PROBE.format(message_id=str(uuid.uuid4()))
    sock.sendto(msg.encode('utf-8'), (ONVIF_MCAST_ADDR, ONVIF_MCAST_PORT))

    found_ips = set()
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            data, addr = sock.recvfrom(65535)
            udp_ip = addr[0]
            if udp_ip not in found_ips:
                found_ips.add(udp_ip)
                info = _parse_probe_match(data, udp_ip)
                if info:
                    yield info
        except socket.timeout:
            break
        except Exception:
            continue

    sock.close()


NS = {
    'soap': 'http://www.w3.org/2003/05/soap-envelope',
    'wsd': 'http://schemas.xmlsoap.org/ws/2005/04/discovery',
    'wsa': 'http://schemas.xmlsoap.org/ws/2004/08/addressing',
}


def _parse_probe_match(raw, udp_ip):
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return None

    body = root.find('.//soap:Body', NS)
    if body is None:
        return None
    match = body.find('.//wsd:ProbeMatches/wsd:ProbeMatch', NS)
    if match is None:
        return None

    xaddrs_el = match.find('wsa:XAddrs', NS)
    types_el = match.find('wsd:Types', NS)
    scopes_el = match.find('wsd:Scopes', NS)

    xaddrs = xaddrs_el.text if xaddrs_el is not None and xaddrs_el.text else ''
    types = types_el.text if types_el is not None and types_el.text else ''
    scopes = scopes_el.text if scopes_el is not None and scopes_el.text else ''

    # Extract IP from XAddrs, fallback to UDP sender IP
    host = ''
    ip_match = re.search(r'https?://(\d+\.\d+\.\d+\.\d+)', xaddrs)
    if ip_match:
        host = ip_match.group(1)
    else:
        host_match = re.search(r'https?://([^:/]+)', xaddrs)
        if host_match:
            host = host_match.group(1)
    if not host:
        host = udp_ip

    # Parse scopes for device info
    model = ''
    location = ''
    hardware = ''
    name = ''
    for scope in scopes.split():
        if 'onvif://www.onvif.org/type/' in scope:
            model = scope.rsplit('/')[-1].replace('_', ' ')
        elif 'onvif://www.onvif.org/location/' in scope:
            location = scope.rsplit('/')[-1]
        elif 'onvif://www.onvif.org/name/' in scope:
            name = scope.rsplit('/')[-1]
        elif 'onvif://www.onvif.org/hardware/' in scope:
            hardware = scope.rsplit('/')[-1]

    scope_type = ''
    for url_part in types.split():
        if url_part.startswith('dn:'):
            scope_type = url_part[3:]

    display_name = name or hardware or model or f'ONVIF 设备 ({host})'

    return {
        'ip': host,
        'host': host,
        'name': display_name,
        'model': model,
        'hardware': hardware,
        'location': location,
        'xaddrs': xaddrs,
        'types': scope_type,
        'source': 'onvif',
    }


# ─── Brand detection ──────────────────────────────────────────


def _detect_brand(name='', model='', hardware=''):
    text = f'{hardware} {model} {name}'.upper()
    if 'DH-' in text or 'IPC-HFW' in text or 'IPC-T' in text or 'SD-' in text or 'NVR-' in text:
        return 'dahua'
    if 'DS-2' in text or 'iDS-' in text:
        return 'hikvision'
    return ''


# ─── Scan entry point ──────────────────────────────────────────────


def _format_onvif(d):
    xaddrs = d.get('xaddrs', '')
    http_url = xaddrs.split()[0] if xaddrs else ''
    brand = _detect_brand(d.get('name', ''), d.get('model', ''), d.get('hardware', ''))
    return {
        'ip': d['ip'],
        'host': d['host'],
        'name': d['name'],
        'model': d.get('model', ''),
        'hardware': d.get('hardware', ''),
        'brand': brand,
        'location': d.get('location', ''),
        'rtsp_url': f'rtsp://{d["host"]}:554/stream1',
        'http_url': http_url,
        'source': 'onvif',
    }


def _format_tcp(ip, has_rtsp):
    return {
        'ip': ip,
        'host': ip,
        'name': ip,
        'model': '',
        'hardware': '',
        'brand': '',
        'location': '',
        'rtsp_url': f'rtsp://{ip}:554/stream1' if has_rtsp else '',
        'http_url': f'http://{ip}',
        'source': 'tcp',
    }


def scan_network(timeout=2):
    return list(scan_network_stream(timeout))


def scan_network_stream(timeout=2):
    import time as _time
    _time.sleep(0.3)

    onvif_ips = set()

    for d in _onvif_discover_iter(timeout=timeout):
        if d.get('ip'):
            onvif_ips.add(d['ip'])
        yield _format_onvif(d)

    local_ip, netmask = _get_local_network()
    if not local_ip or not netmask:
        return

    ips = _generate_ip_range(local_ip, netmask)
    ips = [ip for ip in ips if ip not in onvif_ips]
    if not ips:
        return

    for ip in _tcp_scan_subnet_iter(ips, timeout):
        has_rtsp = _port_open(ip, 554, timeout) or _port_open(ip, 8554, timeout)
        yield _format_tcp(ip, has_rtsp)


def check_camera_status(host, port, timeout=3):
    """TCP connection check to determine if camera is reachable."""
    if not host:
        return False
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        result = s.connect_ex((host, int(port)))
        s.close()
        return result == 0
    except Exception:
        return False


def batch_check_status(camera_ids=None, timeout=3):
    """Check status for all cameras or specified IDs, update and return."""
    store = camera_storage()
    cameras = store.find_all()
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
        fut_map = {}
        for cam in cameras:
            if camera_ids and cam['id'] not in camera_ids:
                continue
            host = cam.get('host', '')
            port = cam.get('port', 554)
            if host:
                fut = pool.submit(check_camera_status, host, port, timeout)
                fut_map[fut] = cam['id']
        for fut in concurrent.futures.as_completed(fut_map, timeout=60):
            cid = fut_map[fut]
            try:
                online = fut.result()
            except Exception:
                online = False
            store.update(cid, {'status': 'online' if online else 'offline'})
            results[cid] = 'online' if online else 'offline'
    return results
