"""Persistent browser credentials must remain HttpOnly and reject cross-origin writes."""
import time

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import Settings
from backend.runtime import Runtime


def client_for(tmp_path, base_url='http://testserver'):
    settings = Settings(data_dir=tmp_path, api_token='test-admin', camera_enabled=False)
    runtime = Runtime(settings)
    return TestClient(create_app(settings, runtime), base_url=base_url), runtime


def login(client, origin='http://testserver'):
    return client.post('/api/auth/session', headers={
        'Authorization': 'Bearer test-admin', 'Origin': origin,
    })


def test_persistent_cookie_survives_a_new_browser_session_and_logout(tmp_path):
    client, runtime = client_for(tmp_path)
    response = login(client)
    assert response.status_code == 200
    cookie_header = response.headers['set-cookie'].lower()
    assert 'httponly' in cookie_header and 'samesite=strict' in cookie_header
    assert 'max-age=31536000' in cookie_header and 'path=/api' in cookie_header
    assert 'test-admin' not in cookie_header and 'test-admin' not in response.text
    reopened = TestClient(client.app, cookies=client.cookies)
    assert reopened.get('/api/auth/status').json()['write_access'] is True
    assert reopened.get('/api/auth/status').json()['persistent_admin'] is True
    assert reopened.delete('/api/auth/session', headers={'Origin': 'http://testserver'}).status_code == 200
    assert reopened.get('/api/auth/status').json()['write_access'] is False


@pytest.mark.parametrize('origin', ['https://evil.example', 'http://testserver:8081', 'null', ''])
def test_cookie_never_authorizes_a_cross_origin_or_originless_write(tmp_path, origin):
    client, runtime = client_for(tmp_path)
    assert login(client).status_code == 200
    runtime.update_options = lambda body: pytest.fail('CSRF reached a write')
    assert client.put('/api/settings', json={'bulb_linkage': False},
                      headers={'Origin': origin} if origin else {}).status_code == 401
    assert client.delete('/api/auth/session', headers={'Origin': origin} if origin else {}).status_code == 403


def test_same_origin_cookie_write_and_existing_bearer_still_work(tmp_path):
    client, runtime = client_for(tmp_path)
    assert login(client).status_code == 200
    runtime.update_options = lambda body: body
    assert client.put('/api/settings', json={'bulb_linkage': False},
                      headers={'Origin': 'http://testserver'}).status_code == 200
    assert client.get('/api/auth/status', headers={'Authorization': 'Bearer wrong'}).json()['write_access'] is False
    assert client.get('/api/auth/status', headers={'Authorization': 'Bearer test-admin'}).json()['write_access'] is True


def test_cookie_expires_and_token_rotation_revokes_old_cookie(tmp_path, monkeypatch):
    client, runtime = client_for(tmp_path)
    assert login(client).status_code == 200
    current = time.time()
    monkeypatch.setattr('backend.admin_sessions.time.time', lambda: current + 31536001)
    assert client.get('/api/auth/status').json()['write_access'] is False
    monkeypatch.setattr('backend.admin_sessions.time.time', lambda: current)
    runtime.settings.api_token = 'rotated-test-token'
    assert client.get('/api/auth/status').json()['write_access'] is False


def test_tampered_cookie_and_missing_credentials_are_rejected(tmp_path):
    client, runtime = client_for(tmp_path)
    assert client.post('/api/auth/session', headers={'Origin': 'http://testserver'}).status_code == 401
    assert login(client, 'null').status_code == 400
    assert login(client).status_code == 200
    name, value = next(iter(client.cookies.items()))
    client.cookies.clear()
    client.cookies.set(name, value + 'tampered')
    assert client.get('/api/auth/status').json()['write_access'] is False


def test_https_cookie_is_secure(tmp_path):
    client, runtime = client_for(tmp_path, 'https://testserver')
    assert 'Secure' in login(client, 'https://testserver').headers['set-cookie']
