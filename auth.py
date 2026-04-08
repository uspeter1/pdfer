"""
pdfer — auth blueprint
Handles user registration, login, logout, and token validation.
Workflow CRUD routes are also here.
"""
import json
import sqlite3
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

import bcrypt
from flask import Blueprint, g, jsonify, request

# ── Config ─────────────────────────────────────────────────────────────────────
WORK_ROOT = Path('/tmp/pdfer')
DB_PATH   = WORK_ROOT.parent / 'pdfer.db'   # /tmp/pdfer.db
TOKEN_TTL = 7 * 24 * 3600                    # 7 days in seconds

auth_bp = Blueprint('auth', __name__)

# ── In-memory token store  {token: {user_id, username, expires}} ───────────────
_tokens: dict = {}
_tok_lock = threading.Lock()


# ── Database helpers ───────────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    """Return a per-request cached connection stored on Flask's g object."""
    if 'db' not in g:
        g.db = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    """Create tables if they don't exist yet."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id          TEXT PRIMARY KEY,
            username    TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS workflows (
            id          TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name        TEXT NOT NULL,
            steps_json  TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


# ── Token helpers ──────────────────────────────────────────────────────────────

def _make_token(user_id: str, username: str) -> str:
    token = str(uuid.uuid4())
    with _tok_lock:
        _tokens[token] = {
            'user_id':  user_id,
            'username': username,
            'expires':  time.time() + TOKEN_TTL,
        }
    return token


def _validate_token(token: str) -> dict | None:
    """Return token payload or None if missing/expired."""
    with _tok_lock:
        payload = _tokens.get(token)
    if not payload:
        return None
    if time.time() > payload['expires']:
        with _tok_lock:
            _tokens.pop(token, None)
        return None
    return payload


def _get_current_user() -> dict | None:
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None
    token = auth_header[7:].strip()
    return _validate_token(token)


def _require_auth():
    """Return (user_payload, None) or (None, error_response)."""
    user = _get_current_user()
    if user is None:
        return None, (jsonify({'error': 'Authentication required'}), 401)
    return user, None


# ── Auth routes ────────────────────────────────────────────────────────────────

@auth_bp.route('/api/auth/register', methods=['POST'])
def register():
    data     = request.get_json(force=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not username or not password:
        return jsonify({'error': 'username and password are required'}), 400
    if len(username) < 2 or len(username) > 64:
        return jsonify({'error': 'Username must be 2–64 characters'}), 400
    if len(password) < 4:
        return jsonify({'error': 'Password must be at least 4 characters'}), 400

    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user_id       = str(uuid.uuid4())
    created_at    = datetime.utcnow().isoformat()

    db = get_db()
    try:
        db.execute(
            'INSERT INTO users (id, username, password_hash, created_at) VALUES (?,?,?,?)',
            (user_id, username, password_hash, created_at),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Username already taken'}), 409

    token = _make_token(user_id, username)
    return jsonify({'user_id': user_id, 'username': username, 'token': token}), 201


@auth_bp.route('/api/auth/login', methods=['POST'])
def login():
    data     = request.get_json(force=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not username or not password:
        return jsonify({'error': 'username and password are required'}), 400

    db  = get_db()
    row = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    if row is None:
        return jsonify({'error': 'Invalid username or password'}), 401

    if not bcrypt.checkpw(password.encode(), row['password_hash'].encode()):
        return jsonify({'error': 'Invalid username or password'}), 401

    token = _make_token(row['id'], row['username'])
    return jsonify({'user_id': row['id'], 'username': row['username'], 'token': token})


@auth_bp.route('/api/auth/logout', methods=['POST'])
def logout():
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:].strip()
        with _tok_lock:
            _tokens.pop(token, None)
    return jsonify({'success': True})


@auth_bp.route('/api/auth/me')
def me():
    user = _get_current_user()
    if user is None:
        return jsonify({'error': 'Not authenticated'}), 401
    return jsonify({'user_id': user['user_id'], 'username': user['username']})


# ── Workflow routes ────────────────────────────────────────────────────────────

@auth_bp.route('/api/workflows')
def list_workflows():
    user, err = _require_auth()
    if err:
        return err

    db   = get_db()
    rows = db.execute(
        'SELECT id, name, steps_json, created_at, updated_at FROM workflows WHERE user_id = ? ORDER BY updated_at DESC',
        (user['user_id'],),
    ).fetchall()

    result = []
    for row in rows:
        steps = json.loads(row['steps_json'])
        result.append({
            'id':         row['id'],
            'name':       row['name'],
            'steps':      steps,
            'step_count': len(steps),
            'created_at': row['created_at'],
            'updated_at': row['updated_at'],
        })
    return jsonify(result)


@auth_bp.route('/api/workflows', methods=['POST'])
def create_workflow():
    user, err = _require_auth()
    if err:
        return err

    data  = request.get_json(force=True) or {}
    name  = (data.get('name') or '').strip()
    steps = data.get('steps')

    if not name:
        return jsonify({'error': 'name is required'}), 400
    if not isinstance(steps, list):
        return jsonify({'error': 'steps must be an array'}), 400

    wf_id      = str(uuid.uuid4())
    now        = datetime.utcnow().isoformat()
    steps_json = json.dumps(steps)

    db = get_db()
    db.execute(
        'INSERT INTO workflows (id, user_id, name, steps_json, created_at, updated_at) VALUES (?,?,?,?,?,?)',
        (wf_id, user['user_id'], name, steps_json, now, now),
    )
    db.commit()

    return jsonify({
        'id':         wf_id,
        'name':       name,
        'steps':      steps,
        'step_count': len(steps),
        'created_at': now,
        'updated_at': now,
    }), 201


@auth_bp.route('/api/workflows/<wf_id>', methods=['PUT'])
def update_workflow(wf_id):
    user, err = _require_auth()
    if err:
        return err

    db  = get_db()
    row = db.execute(
        'SELECT * FROM workflows WHERE id = ? AND user_id = ?',
        (wf_id, user['user_id']),
    ).fetchone()
    if row is None:
        return jsonify({'error': 'Workflow not found'}), 404

    data       = request.get_json(force=True) or {}
    name       = (data.get('name') or row['name']).strip()
    steps      = data.get('steps', json.loads(row['steps_json']))
    now        = datetime.utcnow().isoformat()
    steps_json = json.dumps(steps)

    db.execute(
        'UPDATE workflows SET name=?, steps_json=?, updated_at=? WHERE id=?',
        (name, steps_json, now, wf_id),
    )
    db.commit()

    return jsonify({
        'id':         wf_id,
        'name':       name,
        'steps':      steps,
        'step_count': len(steps),
        'created_at': row['created_at'],
        'updated_at': now,
    })


@auth_bp.route('/api/workflows/<wf_id>', methods=['DELETE'])
def delete_workflow(wf_id):
    user, err = _require_auth()
    if err:
        return err

    db  = get_db()
    row = db.execute(
        'SELECT id FROM workflows WHERE id = ? AND user_id = ?',
        (wf_id, user['user_id']),
    ).fetchone()
    if row is None:
        return jsonify({'error': 'Workflow not found'}), 404

    db.execute('DELETE FROM workflows WHERE id = ?', (wf_id,))
    db.commit()
    return jsonify({'success': True})
