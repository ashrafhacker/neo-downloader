"""Shared request helpers for the neo app."""
import os
import datetime
import threading

try:
    import requests as http_requests
    HTTP_OK = True
except Exception:
    http_requests = None
    HTTP_OK = False

IS_SERVERLESS = bool(os.environ.get("VERCEL"))


def extract_ip():
    from flask import request
    fwd = request.headers.get('X-Forwarded-For', '')
    if fwd:
        return fwd.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def extract_session():
    from flask import request
    return request.headers.get('X-Session-Id', '')


def get_ua_info(ua):
    info = {"browser": "?", "os": "?", "device": "Desktop"}
    if not ua:
        return info
    u = ua.lower()
    if 'chrome' in u and 'edg/' not in u:
        info['browser'] = 'Chrome'
    elif 'firefox' in u:
        info['browser'] = 'Firefox'
    elif 'safari' in u and 'chrome' not in u:
        info['browser'] = 'Safari'
    elif 'edg/' in u:
        info['browser'] = 'Edge'
    elif 'opera' in u or 'opr/' in u:
        info['browser'] = 'Opera'
    if 'windows' in u:
        info['os'] = 'Windows'
    elif 'mac' in u:
        info['os'] = 'macOS'
    elif 'linux' in u and 'android' not in u:
        info['os'] = 'Linux'
    elif 'android' in u:
        info['os'] = 'Android'
        info['device'] = 'Mobile'
    elif 'iphone' in u or 'ipad' in u:
        info['os'] = 'iOS'
        info['device'] = 'Mobile'
    elif 'crkey' in u or 'cros' in u:
        info['os'] = 'ChromeOS'
    if 'mobile' in u:
        info['device'] = 'Mobile'
    elif 'tablet' in u or 'ipad' in u:
        info['device'] = 'Tablet'
    return info


_geo_cache = {}
_geo_lock = threading.Lock()


def get_geo(ip):
    if ip in ('127.0.0.1', '::1', 'localhost', 'unknown'):
        return {}
    if not HTTP_OK or IS_SERVERLESS:
        return {}
    with _geo_lock:
        if ip in _geo_cache:
            return _geo_cache[ip]
    try:
        r = http_requests.get(
            f"http://ip-api.com/json/{ip}?fields=country,city,isp,lat,lon", timeout=2
        )
        if r.status_code == 200:
            data = r.json()
            with _geo_lock:
                _geo_cache[ip] = data
            return data
    except Exception:
        pass
    return {}
