"""Cookie-session identity and company memberships; no password/token stored in cleartext.

SQLite is intended for one VPS host. For clustered deployment migrate to PostgreSQL
and add database RLS alongside these application checks.
"""
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
import uuid
from . import core

SESSION_SECONDS = 7 * 24 * 3600
INVITE_SECONDS = 7 * 24 * 3600
EMAIL = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]{2,}$')
ALLOWED_ROLES = {'owner', 'editor', 'viewer'}


def install():
    with core.connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
          id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE,
          password_hash TEXT NOT NULL, created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS company_memberships (
          company_id TEXT NOT NULL REFERENCES companies(id),
          user_id TEXT NOT NULL REFERENCES users(id),
          role TEXT NOT NULL CHECK(role IN ('owner','editor','viewer')),
          joined_at INTEGER NOT NULL,
          PRIMARY KEY(company_id,user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_memberships_user ON company_memberships(user_id);
        CREATE TABLE IF NOT EXISTS browser_sessions (
          token_hash TEXT PRIMARY KEY,
          user_id TEXT NOT NULL REFERENCES users(id),
          created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON browser_sessions(expires_at);
        CREATE TABLE IF NOT EXISTS company_invitations (
          id TEXT PRIMARY KEY,
          company_id TEXT NOT NULL REFERENCES companies(id),
          email TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('editor','viewer')),
          token_hash TEXT NOT NULL UNIQUE,
          expires_at INTEGER NOT NULL, consumed_at INTEGER,
          created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_invite_tenant ON company_invitations(company_id,expires_at);
        CREATE TABLE IF NOT EXISTS auth_failures (
          email TEXT NOT NULL, addr TEXT NOT NULL, happened_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_auth_failures ON auth_failures(email,happened_at);
        ''')


def normalized_email(value):
    result = (value or '').strip().lower()
    if len(result) > 254 or not EMAIL.fullmatch(result):
        raise ValueError('Invalid email address')
    return result


def password_hash(password):
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        raise ValueError('Password must have 12–128 characters')
    salt = secrets.token_bytes(16)
    value = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f'scrypt$16384$8$1${salt.hex()}${value.hex()}'


def valid_password(password, stored):
    try:
        algorithm,n,r,p,salt,digest = stored.split('$')
        if algorithm != 'scrypt': return False
        result = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(result, bytes.fromhex(digest))
    except (ValueError,TypeError,OverflowError):
        return False


def _create_session(db, user_id):
    token = secrets.token_urlsafe(40)
    db.execute('INSERT INTO browser_sessions VALUES(?,?,?,?)', (core.digest(token),user_id,core.now(),core.now()+SESSION_SECONDS))
    return token


def create_user_company(email, password, company_name):
    email = normalized_email(email)
    if not isinstance(company_name,str) or not 2 <= len(company_name.strip()) <= 120:
        raise ValueError('Company name must have 2–120 characters')
    pw = password_hash(password)
    user_id, company_id = core.uid(), core.uid()
    with core.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM users WHERE email=?',(email,)).fetchone():
            raise ValueError('Account already exists')
        db.execute('INSERT INTO users VALUES(?,?,?,?)',(user_id,email,pw,core.now()))
        db.execute('INSERT INTO companies VALUES(?,?,?)',(company_id,company_name.strip(),core.now()))
        db.execute('INSERT INTO company_memberships VALUES(?,?,?,?)',(company_id,user_id,'owner',core.now()))
        core.log(db,company_id,'company.created',{'name':company_name.strip(),'source':'registered_owner'})
        token = _create_session(db,user_id)
        db.commit()
    return token


def login(email,password,addr='unknown'):
    email=normalized_email(email)
    if not isinstance(password,str): return None
    with core.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM auth_failures WHERE happened_at<?',(core.now()-900,))
        attempts=db.execute('SELECT COUNT(*) AS n FROM auth_failures WHERE email=? AND happened_at>=?',(email,core.now()-900)).fetchone()['n']
        if attempts >= 6:
            db.commit()
            return None
        user=db.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
        if user is None or not valid_password(password,user['password_hash']):
            db.execute('INSERT INTO auth_failures VALUES(?,?,?)',(email,(addr or '')[:80],core.now()))
            db.commit()
            return None
        db.execute('DELETE FROM auth_failures WHERE email=?',(email,))
        token=_create_session(db,user['id'])
        db.commit()
        return token


def session_info(token):
    if not token: return None
    with core.connect() as db:
        user=db.execute('''SELECT u.id,u.email,s.expires_at FROM browser_sessions s
            JOIN users u ON s.user_id=u.id
            WHERE s.token_hash=? AND s.expires_at>?''',(core.digest(token),core.now())).fetchone()
        if user is None: return None
        memberships=[dict(r) for r in db.execute('''SELECT m.company_id,m.role,c.name FROM company_memberships m
         JOIN companies c ON c.id=m.company_id WHERE m.user_id=? ORDER BY m.joined_at''',(user['id'],))]
        return {'id':user['id'],'email':user['email'],'memberships':memberships,'expires_at':user['expires_at']}


def revoke_session(token):
    with core.connect() as db:
        db.execute('DELETE FROM browser_sessions WHERE token_hash=?',(core.digest(token),))


def create_company(user_id,name):
    if not isinstance(name,str) or not 2<=len(name.strip())<=120:raise ValueError('Invalid company name')
    with core.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        existing=db.execute('SELECT COUNT(*) AS n FROM company_memberships WHERE user_id=?',(user_id,)).fetchone()['n']
        if existing>=10:raise ValueError('Company limit reached')
        company_id=core.uid()
        db.execute('INSERT INTO companies VALUES(?,?,?)',(company_id,name.strip(),core.now()))
        db.execute('INSERT INTO company_memberships VALUES(?,?,?,?)',(company_id,user_id,'owner',core.now()))
        core.log(db,company_id,'company.created',{'name':name.strip(),'source':'member_created'})
        db.commit()
        return company_id


def invite(company_id,email,role):
    email=normalized_email(email)
    if role not in ('viewer','editor'):raise ValueError('Invalid invitation role')
    token=secrets.token_urlsafe(32)
    with core.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT INTO company_invitations VALUES(?,?,?,?,?,?,?,?)',
                   (core.uid(),company_id,email,role,core.digest(token),core.now()+INVITE_SECONDS,None,core.now()))
        core.log(db,company_id,'member.invited',{'role':role,'recipient_email_masked':'[redacted]'})
        db.commit()
    return token


def accept_invite(token,email,password):
    email=normalized_email(email)
    if not isinstance(password,str): raise ValueError('Invalid credentials')
    with core.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        invitation=db.execute('''SELECT * FROM company_invitations
            WHERE token_hash=? AND email=? AND consumed_at IS NULL AND expires_at>?''',
            (core.digest(token),email,core.now())).fetchone()
        if invitation is None: raise ValueError('Invitation unavailable')
        user=db.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
        if user:
            if not valid_password(password,user['password_hash']):raise ValueError('Invalid credentials')
            user_id=user['id']
        else:
            hash_value=password_hash(password)
            user_id=core.uid()
            db.execute('INSERT INTO users VALUES(?,?,?,?)',(user_id,email,hash_value,core.now()))
        existing=db.execute('SELECT 1 FROM company_memberships WHERE company_id=? AND user_id=?',(invitation['company_id'],user_id)).fetchone()
        if existing is None:
            db.execute('INSERT INTO company_memberships VALUES(?,?,?,?)',
                (invitation['company_id'],user_id,invitation['role'],core.now()))
        db.execute('UPDATE company_invitations SET consumed_at=? WHERE id=?',(core.now(),invitation['id']))
        core.log(db,invitation['company_id'],'member.joined',{'role':invitation['role']})
        session=_create_session(db,user_id)
        db.commit()
        return session


def list_members(company_id):
    with core.connect() as db:
        return [dict(r) for r in db.execute('''SELECT u.email,m.role,m.joined_at FROM company_memberships m
            JOIN users u ON u.id=m.user_id WHERE m.company_id=?
            ORDER BY m.joined_at,u.email''',(company_id,))]
