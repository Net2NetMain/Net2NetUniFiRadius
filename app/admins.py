"""Named administrator accounts; changes require the acting admin's password."""
import hmac
import secrets
import sqlite3

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, field_validator


class Reauthenticate(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)


class PasswordChange(Reauthenticate):
    new_password: str = Field(min_length=12, max_length=256)


class AdminCreate(Reauthenticate):
    username: str = Field(pattern=r'^[a-z0-9_.@-]{3,64}$')
    display_name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=12, max_length=256)

    @field_validator('username', mode='before')
    @classmethod
    def normalize(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class AdminUpdate(Reauthenticate):
    display_name: str = Field(min_length=2, max_length=100)
    enabled: bool
    password: str = Field(default='', max_length=256)

    @field_validator('password')
    @classmethod
    def minimum(cls, value):
        if value and len(value) < 12:
            raise ValueError('Administrator passwords require at least 12 characters')
        return value


def confirm(c, identity, password):
    from . import main as m
    actor = c.execute('SELECT * FROM admins WHERE id=? AND enabled=1', (identity['id'],)).fetchone()
    if not actor or not hmac.compare_digest(m.password_hash(password, actor['salt']), actor['password_hash']):
        raise HTTPException(403, 'Your current administrator password is incorrect')


def register_admins(app, admin):
    from . import main as m

    @app.get('/api/admins')
    def list_admins(identity: dict = Depends(admin)):
        with m.db() as c:
            return {'current': identity,
                    'admins': [dict(r) for r in c.execute('SELECT id,username,display_name,enabled FROM admins ORDER BY username')]}

    @app.post('/api/admins/password')
    def change_password(body: PasswordChange, identity: dict = Depends(admin)):
        with m.LOCK, m.db() as c:
            confirm(c, identity, body.current_password)
            salt = secrets.token_hex(16)
            c.execute('UPDATE admins SET password_hash=?,salt=? WHERE id=?',
                      (m.password_hash(body.new_password, salt), salt, identity['id']))
            c.execute('DELETE FROM sessions WHERE admin_id=?', (identity['id'],))
        return {'ok': True, 'sign_in_again': True}

    @app.post('/api/admins')
    def create_admin(body: AdminCreate, identity: dict = Depends(admin)):
        with m.LOCK, m.db() as c:
            confirm(c, identity, body.current_password)
            salt = secrets.token_hex(16)
            try:
                c.execute('INSERT INTO admins(username,display_name,password_hash,salt) VALUES (?,?,?,?)',
                          (body.username, body.display_name, m.password_hash(body.password, salt), salt))
            except sqlite3.IntegrityError:
                raise HTTPException(409, 'Administrator username already exists')
        return {'ok': True}

    @app.put('/api/admins/{item_id}')
    def update_admin(item_id: int, body: AdminUpdate, identity: dict = Depends(admin)):
        with m.LOCK, m.db() as c:
            confirm(c, identity, body.current_password)
            target = c.execute('SELECT * FROM admins WHERE id=?', (item_id,)).fetchone()
            if not target:
                raise HTTPException(404, 'Administrator not found')
            if not body.enabled:
                if item_id == identity['id']:
                    raise HTTPException(409, 'You cannot disable your own account')
                if target['enabled'] and c.execute('SELECT COUNT(*) FROM admins WHERE enabled=1').fetchone()[0] <= 1:
                    raise HTTPException(409, 'At least one enabled administrator is required')
            if item_id == identity['id'] and body.password:
                raise HTTPException(409, 'Use Change my password to update your own password')
            c.execute('UPDATE admins SET display_name=?,enabled=? WHERE id=?',
                      (body.display_name, body.enabled, item_id))
            if body.password:
                salt = secrets.token_hex(16)
                c.execute('UPDATE admins SET password_hash=?,salt=? WHERE id=?',
                          (m.password_hash(body.password, salt), salt, item_id))
            if body.password or not body.enabled:
                c.execute('DELETE FROM sessions WHERE admin_id=?', (item_id,))
        return {'ok': True}
