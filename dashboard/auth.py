"""
MOTOSIRA — Authentication
Single shared operator login (kiosk/shop device), password stored hashed.
"""
import os
from functools import wraps
from flask import session, redirect, url_for, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

VALID_USER = os.getenv('MOTOSIRA_USER', 'admin')

# Prefer a pre-hashed password (MOTOSIRA_PASS_HASH) if set; otherwise hash
# the plaintext MOTOSIRA_PASS from .env at import time so nothing sensitive
# is compared or logged in plaintext at runtime.
_env_hash = os.getenv('MOTOSIRA_PASS_HASH')
if _env_hash:
    VALID_PASS_HASH = _env_hash
else:
    VALID_PASS_HASH = generate_password_hash(os.getenv('MOTOSIRA_PASS', 'motosira123'))


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def check_credentials(username, password):
    return username == VALID_USER and check_password_hash(VALID_PASS_HASH, password)
