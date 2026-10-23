import hashlib
import sqlite3
import time

from fastapi.testclient import TestClient

from app import main
from test_api import client, sign_in

CURRENT = 'Test-Admin-Password-2026!'
NEW = 'Different-Admin-Password-2026!'


def test_create_admin_requires_reauthentication_and_hides_hashes(client):
    assert client.get('/api/admins').status_code == 401
    sign_in(client)
    body = {'username': 'Office.Admin', 'display_name': 'Office admin', 'password': NEW,
            'current_password': 'incorrect'}
    assert client.post('/api/admins', json=body).status_code == 403
    body['current_password'] = CURRENT
    invalid = client.post('/api/admins', json={**body, 'password': '1234567'})
    assert invalid.status_code == 422
    assert '1234567' not in invalid.text and CURRENT not in invalid.text
    assert client.post('/api/admins', json=body).status_code == 200
    assert client.post('/api/admins', json=body).status_code == 409
    result = client.get('/api/admins').json()
    assert result['current']['username'] == 'admin'
    assert [a['username'] for a in result['admins']] == ['admin', 'office.admin']
    assert all('password_hash' not in a and 'salt' not in a for a in result['admins'])
    with main.db() as c:
        assert c.execute('SELECT password_hash FROM admins WHERE username=?', ('office.admin',)).fetchone()[0] != NEW


def test_password_change_revokes_all_own_sessions_and_survives_restart(client):
    sign_in(client)
    with TestClient(main.app) as second:
        second.post('/api/login', json={'username': 'admin', 'password': CURRENT})
        assert client.post('/api/admins/password', json={'current_password': 'wrong', 'new_password': NEW}).status_code == 403
        assert second.get('/api/state').status_code == 200
        assert client.post('/api/admins/password', json={'current_password': CURRENT, 'new_password': NEW}).status_code == 200
        assert client.get('/api/state').status_code == 401
        assert second.get('/api/state').status_code == 401
    main.initialize()
    assert client.post('/api/login', json={'password': CURRENT}).status_code == 401
    assert client.post('/api/login', json={'username': 'ADMIN', 'password': NEW}).status_code == 200


def test_disable_reset_and_self_lockout_protection(client):
    sign_in(client)
    client.post('/api/admins', json={'username': 'office', 'display_name': 'Office admin',
                                   'password': NEW, 'current_password': CURRENT})
    accounts = client.get('/api/admins').json()
    own_id = accounts['current']['id']
    other_id = next(a['id'] for a in accounts['admins'] if a['username'] == 'office')
    assert client.put(f'/api/admins/{own_id}', json={'display_name': 'Administrator', 'enabled': False,
                       'current_password': CURRENT}).status_code == 409
    with TestClient(main.app) as other:
        other.post('/api/login', json={'username': 'office', 'password': NEW})
        assert other.get('/api/state').status_code == 200
        update = {'display_name': 'Office admin', 'enabled': True, 'current_password': CURRENT,
                  'password': 'Reset-Office-Password-2026!'}
        assert client.put(f'/api/admins/{other_id}', json=update).status_code == 200
        assert other.get('/api/state').status_code == 401
        assert other.post('/api/login', json={'username': 'office', 'password': NEW}).status_code == 401
        assert other.post('/api/login', json={'username': 'office', 'password': update['password']}).status_code == 200
        update.update(enabled=False, password='')
        assert client.put(f'/api/admins/{other_id}', json=update).status_code == 200
        assert other.get('/api/state').status_code == 401
        assert other.post('/api/login', json={'username': 'office', 'password': 'Reset-Office-Password-2026!'}).status_code == 401


def test_legacy_migration_preserves_password_and_session(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DATA', tmp_path)
    monkeypatch.setattr(main, 'RADIUS', '')
    monkeypatch.setenv('ADMIN_PASSWORD', 'New-env-must-not-reset-existing!')
    salt = 'ab' * 16
    token = 'legacy-cookie-token'
    c = sqlite3.connect(tmp_path / 'unifi.db')
    c.executescript('CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT NOT NULL); '
                    'CREATE TABLE sessions(token TEXT PRIMARY KEY,expires INTEGER NOT NULL);')
    c.executemany('INSERT INTO settings VALUES (?,?)', [('admin_salt', salt), ('admin_hash', main.password_hash(CURRENT, salt))])
    c.execute('INSERT INTO sessions VALUES (?,?)', (hashlib.sha256(token.encode()).hexdigest(), int(time.time()) + 3600))
    c.commit()
    c.close()
    with TestClient(main.app) as migrated:
        migrated.cookies.set('net2net_unifi', token)
        assert migrated.get('/api/admins').json()['current']['username'] == 'admin'
        assert migrated.post('/api/login', json={'password': CURRENT}).status_code == 200
        with main.db() as c:
            assert c.execute('SELECT COUNT(*) FROM admins').fetchone()[0] == 1
            assert not c.execute("SELECT 1 FROM settings WHERE key='admin_hash'").fetchone()
        main.initialize()
        assert migrated.post('/api/login', json={'password': CURRENT}).status_code == 200
