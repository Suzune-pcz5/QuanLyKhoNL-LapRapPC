"""Durable HTTP metadata outside the seventeen business tables."""
import hashlib
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager

from flask.sessions import SessionInterface, SessionMixin
from itsdangerous import BadSignature, URLSafeSerializer
from werkzeug.datastructures import CallbackDict

from db import RUNTIME


class WebState:
    def __init__(self, database):
        RUNTIME.mkdir(parents=True, exist_ok=True)
        self.path = RUNTIME / ('web-state-' + hashlib.sha256(database.encode()).hexdigest()[:24] + '.sqlite3')
        with self.connection() as c:
            c.execute('CREATE TABLE IF NOT EXISTS sessions (sid TEXT PRIMARY KEY, data TEXT NOT NULL, expires REAL NOT NULL, version INTEGER NOT NULL)')
            c.execute('CREATE TABLE IF NOT EXISTS operations (account INTEGER, kind TEXT, token TEXT, fingerprint TEXT NOT NULL, ident INTEGER NOT NULL, completed INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(account,kind,token))')

    @contextmanager
    def connection(self):
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        try:
            with c:
                yield c
        finally:
            c.close()

    def operation(self, account, kind, token):
        with self.connection() as c:
            row = c.execute('SELECT * FROM operations WHERE account=? AND kind=? AND token=?', (account, kind, token)).fetchone()
            return dict(row) if row else None

    def reserve(self, account, kind, token, fingerprint, ident):
        # Written before MySQL COMMIT. A retry checks the document under the
        # same MySQL connection lock, recovering both committed and rolled-back saves.
        with self.connection() as c:
            c.execute('INSERT INTO operations VALUES (?,?,?,?,?,0) ON CONFLICT(account,kind,token) DO UPDATE SET ident=excluded.ident,completed=0', (account, kind, token, fingerprint, ident))

    def complete(self, account, kind, token):
        with self.connection() as c:
            c.execute('UPDATE operations SET completed=1 WHERE account=? AND kind=? AND token=?', (account, kind, token))


class ServerSession(CallbackDict, SessionMixin):
    def __init__(self, data=None, sid=None, version=None):
        super().__init__(data, lambda value: setattr(value, 'modified', True))
        self.sid = sid or secrets.token_urlsafe(32)
        self.version = version
        self.modified = False
        self.rotate = False


class ServerSessions(SessionInterface):
    def __init__(self, store, database):
        self.store = store
        self.salt = 'mrp-server-session-v2:' + database

    def signer(self, app):
        return URLSafeSerializer(app.secret_key, salt=self.salt)

    def open_session(self, app, request):
        token = request.cookies.get(self.get_cookie_name(app))
        if token:
            try:
                sid = self.signer(app).loads(token)
                if isinstance(sid, str):
                    with self.store.connection() as c:
                        row = c.execute('SELECT * FROM sessions WHERE sid=? AND expires>?', (sid, time.time())).fetchone()
                    if row:
                        return ServerSession(json.loads(row['data']), sid, row['version'])
            except BadSignature:
                pass
        return ServerSession()

    def save_session(self, app, session, response):
        if not session.modified:
            return
        name = self.get_cookie_name(app)
        with self.store.connection() as c:
            c.execute('DELETE FROM sessions WHERE expires<=?', (time.time(),))
            if not session:
                c.execute('DELETE FROM sessions WHERE sid=?', (session.sid,))
                response.delete_cookie(name, path=self.get_cookie_path(app), domain=self.get_cookie_domain(app),
                                       secure=self.get_cookie_secure(app), httponly=True, samesite=self.get_cookie_samesite(app))
                return
            old_sid = session.sid
            expires = time.time() + (app.permanent_session_lifetime.total_seconds() if session.permanent else 3600)
            data = json.dumps(dict(session), ensure_ascii=False)
            if session.version is not None:
                # A response loaded before logout/login cannot revive the old session.
                changed = c.execute('DELETE FROM sessions WHERE sid=? AND version=?', (old_sid, session.version)).rowcount if session.rotate else c.execute(
                    'UPDATE sessions SET data=?,expires=?,version=version+1 WHERE sid=? AND version=?',
                    (data, expires, old_sid, session.version)).rowcount
                if not changed:
                    return
            if session.rotate:
                session.sid = secrets.token_urlsafe(32)
            if session.version is None or session.rotate:
                c.execute('INSERT INTO sessions VALUES (?,?,?,0)', (session.sid, data, expires))
        response.set_cookie(name, self.signer(app).dumps(session.sid), expires=self.get_expiration_time(app, session),
                            httponly=True, secure=self.get_cookie_secure(app), samesite=self.get_cookie_samesite(app),
                            domain=self.get_cookie_domain(app), path=self.get_cookie_path(app))
