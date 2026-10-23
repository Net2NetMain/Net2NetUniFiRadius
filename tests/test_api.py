import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DATA', tmp_path)
    monkeypatch.setattr(main, 'RADIUS', '')
    monkeypatch.setenv('ADMIN_PASSWORD', 'Test-Admin-Password-2026!')
    with TestClient(main.app) as client:
        yield client


def sign_in(client):
    assert client.post('/api/login', json={'password': 'Test-Admin-Password-2026!'}).status_code == 200
    client.headers['X-Net2Net-Request'] = 'portal'


def test_access_control_and_logout(client):
    assert client.get('/api/state').status_code == 401
    assert client.post('/api/login', json={'password': 'wrong'}).status_code == 401
    sign_in(client)
    assert client.get('/api/state').status_code == 200
    del client.headers['X-Net2Net-Request']
    assert client.post('/api/profiles', json={'name': 'Staff', 'vlan': 20}).status_code == 403
    client.headers['X-Net2Net-Request'] = 'portal'
    assert client.post('/api/logout').status_code == 200
    assert client.get('/api/state').status_code == 401


def test_users_vlan_suspension_and_secrets(client):
    sign_in(client)
    assert client.post('/api/profiles', json={'name': 'Staff', 'vlan': 20}).status_code == 200
    profile = client.get('/api/state').json()['profiles'][0]
    user = {'username': 'test@example.com', 'display_name': 'Test user',
            'password': "A-%{literal}-'Password!", 'profile_id': profile['id']}
    assert client.post('/api/users', json=user).status_code == 200
    assert client.post('/api/nas', json={'name': 'Test AP', 'address': '192.0.2.10',
                                       'secret': 'A-Strong-NAS-Secret!'}).status_code == 200
    state = client.get('/api/state').json()
    assert 'password' not in state['users'][0]
    assert 'secret' not in state['nas'][0]
    with main.db() as c:
        users, clients = main.render_config(c)
        assert 'Tunnel-Private-Group-Id := "20"' in users
        assert "Cleartext-Password := 'A-%{literal}-\\'Password!'" in users
        assert 'Mikrotik' not in users
        assert 'require_message_authenticator = yes' in clients
        assert user['password'] not in c.execute('SELECT password FROM users').fetchone()[0]
    assert client.delete(f"/api/profiles/{profile['id']}").status_code == 409
    user.update(status='suspended', password='')
    assert client.put(f"/api/users/{state['users'][0]['id']}", json=user).status_code == 200
    with main.db() as c:
        users, _ = main.render_config(c)
        assert 'Auth-Type := Reject' in users
        assert 'Cleartext-Password' not in users
    backup = client.get('/api/backup')
    assert backup.status_code == 200
    with zipfile.ZipFile(io.BytesIO(backup.content)) as archive:
        assert {'unifi.db', 'secret.key'} <= set(archive.namelist())


def test_validation_and_config_rollback(client, monkeypatch):
    sign_in(client)
    assert client.post('/api/profiles', json={'name': 'Bad', 'vlan': 4095}).status_code == 422
    assert client.post('/api/nas', json={'name': 'Bad', 'address': '0.0.0.0/0', 'secret': 'secret'}).status_code == 422
    assert client.post('/api/nas', json={'name': 'Bad', 'address': '192.0.2.10',
                                       'secret': '${config-injection}'}).status_code == 422
    assert client.post('/api/users', json={'username': 'bad\nDEFAULT', 'display_name': 'Bad user',
                                          'profile_id': 1, 'password': 'long-enough-password'}).status_code == 422
    def fail(c):
        raise RuntimeError('invalid config')
    monkeypatch.setattr(main, 'apply_config', fail)
    assert client.post('/api/profiles', json={'name': 'Rollback', 'vlan': 30}).status_code == 503
    assert client.get('/api/state').json()['profiles'] == []


def test_login_rate_limit(client):
    for _ in range(5):
        assert client.post('/api/login', json={'password': 'wrong'}).status_code == 401
    assert client.post('/api/login', json={'password': 'wrong'}).status_code == 429


def test_accounting_nas_session_collision(client):
    sign_in(client)
    for host in ['192.0.2.10', '192.0.2.11']:
        folder = main.DATA / 'accounting' / host
        folder.mkdir(parents=True)
        (folder / 'detail-20261023').write_text(
            f'Fri Oct 23\n\tAcct-Session-Id = "same-id"\n\tNAS-IP-Address = {host}\n'
            '\tUser-Name = "test-user"\n\tAcct-Status-Type = Start\n\n')
    assert len(client.get('/api/accounting').json()) == 2
