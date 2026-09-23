#!/usr/bin/env python3

from pathlib import Path
import sys


OLD_BLOCK = """    # 默认管理员
    admin_count = db.execute("SELECT COUNT(*) as c FROM users WHERE role='admin'").fetchone()['c']
    if admin_count == 0:
        db.execute(
            "INSERT INTO users (username, password_hash, nickname, role, status) VALUES (?, ?, ?, 'admin', 'approved')",
            ('admin', generate_password_hash('admin123'), '管理员', )
        )
"""

NEW_BLOCK = """    # 管理员账号由飞牛统一网关首次登录时创建
"""


ENSURE_DB_BLOCK = """_db_initialized = False
_db_init_lock = threading.Lock()


@app.before_request
def ensure_db():
    global _db_initialized
    if not _db_initialized:
        with _db_init_lock:
            if not _db_initialized:
                init_db()
                _db_initialized = True
"""


OLD_LOGOUT_BLOCK = """    session.clear()
    return jsonify({'message': '已退出'})
"""


NEW_LOGOUT_BLOCK = """    session.clear()
    session['gateway_login_disabled'] = True
    return jsonify({'message': '已退出'})
"""


OLD_LOGIN_BLOCK = """    session.permanent = True
    session['user_id'] = user['id']
    session['role'] = user['role']
"""

NEW_LOGIN_BLOCK = """    session.pop('gateway_login_disabled', None)
    session.permanent = True
    session['user_id'] = user['id']
    session['role'] = user['role']
"""


OLD_LOGIN_PAGE_BLOCK = """@app.route('/login')
def login_page():
    return render_template('login.html')
"""

NEW_LOGIN_PAGE_BLOCK = """@app.route('/login')
def login_page():
    return render_template('login.html', gateway_login_available=_gateway_identity() is not None)
"""

OLD_RESET_CLI_BLOCK = """@app.cli.command('reset-password')
def reset_password_cmd():
    \"\"\"重置管理员密码，生成随机密码并输出\"\"\"
    with app.app_context():
        db = get_db()
        admin = db.execute("SELECT id, username FROM users WHERE role = 'admin' LIMIT 1").fetchone()
        if not admin:
            print('错误: 未找到管理员账户')
            return
        alphabet = string.ascii_letters + string.digits
        new_pw = ''.join(secrets.choice(alphabet) for _ in range(10))
        db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                   (generate_password_hash(new_pw), admin['id']))
        db.commit()
        print(f'管理员 [{admin["username"]}] 密码已重置')
        print(f'新密码: {new_pw}')
"""

AUTH_MARKER = "# fnOS gateway authentication"
AUTH_BLOCK = r'''


import ipaddress
import subprocess
from pathlib import Path


# fnOS gateway authentication
_PUBLIC_AUTH_PATHS = {
    '/login',
    '/register',
    '/api/auth/login',
    '/api/auth/gateway-login',
    '/api/auth/register',
    '/api/auth/me',
    '/api/auth/logout',
    '/favicon.ico',
}


def _is_public_auth_path(path):
    return path in _PUBLIC_AUTH_PATHS or path.startswith('/static/')


def _gateway_identity():
    # Gunicorn uses an empty REMOTE_ADDR for Unix Socket requests.
    if request.environ.get('REMOTE_ADDR', None) not in ('', None):
        return None
    user_id = (request.headers.get('X-Trim-Userid') or '').strip()
    username = (request.headers.get('X-Trim-Username') or '').strip()
    if not user_id.isdigit() or not (1 <= len(username) <= 128):
        return None
    return user_id, username, (request.headers.get('X-Trim-Isadmin') or '').lower() == 'true'


def _sign_in_gateway_user():
    if session.get('gateway_login_disabled'):
        return False
    identity = _gateway_identity()
    if identity is None:
        return False
    gateway_uid, username, gateway_is_admin = identity
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    if user is None:
        role = 'admin' if gateway_is_admin else 'user'
        cursor = db.execute(
            "INSERT INTO users (username, password_hash, nickname, role, status) VALUES (?, ?, ?, ?, 'approved')",
            (username, generate_password_hash(secrets.token_urlsafe(48)), username, role)
        )
        user_id = cursor.lastrowid
    else:
        user_id = user['id']
        role = 'admin' if gateway_is_admin else user['role']
        db.execute("UPDATE users SET role = ?, status = 'approved' WHERE id = ?", (role, user_id))
    if gateway_is_admin:
        db.execute("UPDATE users SET role = 'user' WHERE role = 'admin' AND id != ?", (user_id,))
    db.commit()
    session.permanent = True
    session['user_id'] = user_id
    session['role'] = role
    session['gateway_uid'] = gateway_uid
    return True


def _admin_password_setup_required():
    user = current_user()
    if not user or user['role'] != 'admin' or user['status'] != 'approved':
        return False
    row = get_db().execute(
        "SELECT value FROM settings WHERE key = 'admin_password_initialized'"
    ).fetchone()
    return row is None or row['value'] != '1'


def _mark_admin_password_initialized():
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO settings (key, value, updated_at) "
        "VALUES ('admin_password_initialized', '1', datetime('now','localtime'))"
    )
    db.commit()


@app.route('/api/auth/gateway-login', methods=['POST'])
def gateway_login():
    if _gateway_identity() is None:
        return jsonify({'error': '仅支持从飞牛统一网关登录'}), 403
    session.pop('gateway_login_disabled', None)
    if not _sign_in_gateway_user():
        return jsonify({'error': '无法获取飞牛登录身份'}), 403
    user = current_user()
    return jsonify({
        'message': '登录成功',
        'user': {
            'id': user['id'],
            'username': user['username'],
            'nickname': user['nickname'],
            'role': user['role'],
        }
    })


@app.route('/setup-password')
def setup_password_page():
    if not is_admin():
        return redirect('/')
    if not _admin_password_setup_required():
        return redirect('/')
    return render_template('setup-password.html')


@app.route('/api/auth/setup-password', methods=['POST'])
def setup_admin_password():
    user = current_user()
    if not user or user['role'] != 'admin' or user['status'] != 'approved':
        return jsonify({'error': '仅管理员可以设置管理密码'}), 403
    data = request.get_json(silent=True) or {}
    password = str(data.get('password') or '')
    confirmation = str(data.get('confirm_password') or '')
    if not (8 <= len(password) <= 128):
        return jsonify({'error': '管理密码长度应为 8-128 位'}), 400
    if password != confirmation:
        return jsonify({'error': '两次输入的密码不一致'}), 400
    db = get_db()
    db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (generate_password_hash(password), user['id'])
    )
    _mark_admin_password_initialized()
    add_log('设置管理密码', 'user', user['id'], f"为 {user['username']} 设置管理密码")
    return jsonify({'message': '管理密码已设置'})


def _read_service_config_value(filename, fallback=''):
    config_dir = os.environ.get('TRIM_PKGETC', '').strip()
    if not config_dir:
        return fallback
    try:
        value = Path(config_dir, filename).read_text(encoding='utf-8').strip()
    except OSError:
        return fallback
    return value or fallback


def _service_config_values():
    return (
        _read_service_config_value(
            'bind_address', os.environ.get('BABY_TRACKER_BIND_ADDRESS', '').strip()
        ),
        _read_service_config_value(
            'service_port', os.environ.get('BABY_TRACKER_SERVICE_PORT', '').strip()
        ),
    )


@app.route('/api/admin/service-config', methods=['GET'])
def get_service_config():
    if not is_admin():
        return jsonify({'error': '仅管理员可以查看服务配置'}), 403
    bind_address, port = _service_config_values()
    return jsonify({'bind_address': bind_address, 'port': port})


@app.route('/api/admin/service-config', methods=['PUT'])
def update_service_config():
    if not is_admin():
        return jsonify({'error': '仅管理员可以修改服务配置'}), 403
    data = request.get_json(silent=True) or {}
    bind_address = str(data.get('bind_address') or '').strip()
    port = str(data.get('port') or '').strip()
    try:
        address = ipaddress.ip_address(bind_address)
    except ValueError:
        return jsonify({'error': '绑定地址必须是有效的局域网 IPv4 地址'}), 400
    if (
        address.version != 4
        or address.is_unspecified
        or address.is_loopback
        or address.is_multicast
        or address.is_global
    ):
        return jsonify({'error': '绑定地址不能是 0.0.0.0、127.0.0.1 或公网 IPv4 地址'}), 400
    if not port.isdigit() or not (1024 <= int(port) <= 65535):
        return jsonify({'error': '监听端口范围应为 1024-65535'}), 400

    current_bind_address, current_port = _service_config_values()
    launcher_path = os.environ.get('BABY_TRACKER_CMD_MAIN', '').strip()
    if not launcher_path:
        app_dest = os.environ.get('TRIM_APPDEST', '').strip()
        if app_dest:
            launcher_path = str(Path(app_dest) / 'cmd' / 'main')
    if not launcher_path or not os.path.isfile(launcher_path) or not os.access(launcher_path, os.X_OK):
        return jsonify({'error': '无法定位应用启动器，请从飞牛应用中心停止并重新启动应用'}), 500

    environment = os.environ.copy()
    environment['wizard_bind_address'] = bind_address
    environment['wizard_port'] = port
    try:
        validation = subprocess.run(
            [launcher_path, 'configure'],
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return jsonify({'error': '服务配置校验失败，请确认应用运行正常'}), 500
    if validation.returncode != 0:
        detail = (validation.stderr or validation.stdout or '').strip()
        return jsonify({
            'error': detail or '服务配置校验失败：绑定地址必须是 NAS 本机局域网 IPv4 地址'
        }), 400

    if current_bind_address == bind_address and current_port == port:
        return jsonify({
            'message': '服务配置未变化',
            'bind_address': bind_address,
            'port': port,
            'restarted': False,
        })

    try:
        subprocess.Popen(
            [launcher_path, 'restart'],
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
    except OSError:
        return jsonify({'error': '服务配置已保存，但自动重启失败，请手动重启应用'}), 500

    add_log(
        '修改服务配置',
        'service',
        None,
        f'服务地址改为 {bind_address}:{port}，应用将自动重启',
    )
    return jsonify({
        'message': '服务配置已保存，应用正在重启',
        'bind_address': bind_address,
        'port': port,
        'restarted': True,
    })


@app.before_request
def require_authentication():
    path = request.path
    if request.method == 'OPTIONS' or _is_public_auth_path(path):
        return None

    if path.startswith('/api/ha/') and path != '/api/ha/api-key':
        if _check_ha_api_key() or _sign_in_gateway_user() or is_approved():
            return None
        return jsonify({'error': '未授权，请提供有效的 API 密钥'}), 401

    if _sign_in_gateway_user() or is_approved():
        if _admin_password_setup_required() and path not in (
            '/setup-password',
            '/api/auth/setup-password',
        ):
            if path.startswith('/api/'):
                return jsonify({
                    'error': '请先设置管理密码',
                    'password_setup_required': True,
                }), 403
            return redirect('/setup-password')
        return None

    if path.startswith('/api/'):
        return jsonify({'error': '未登录或账号未通过审批'}), 401
    return redirect(url_for('login_page'))
'''


OLD_DEV_SERVER_BLOCK = """    app.run(host='0.0.0.0', port=5000, debug=True)
"""

NEW_DEV_SERVER_BLOCK = """    app.run(host='127.0.0.1', port=5000, debug=True)
"""


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: patch_source.py PATH", file=sys.stderr)
        return 2

    path = Path(sys.argv[1])
    source = path.read_text(encoding="utf-8")
    changed = False
    if "import string\n" in source:
        source = source.replace("import string\n", "", 1)
        changed = True

    if OLD_RESET_CLI_BLOCK in source:
        source = source.replace(OLD_RESET_CLI_BLOCK, "", 1)
        changed = True

    if NEW_BLOCK not in source:
        if source.count(OLD_BLOCK) != 1:
            print(f"expected one initial-admin block in {path}", file=sys.stderr)
            return 1
        source = source.replace(OLD_BLOCK, NEW_BLOCK, 1)
        changed = True

    if NEW_LOGIN_BLOCK not in source:
        if source.count(OLD_LOGIN_BLOCK) != 1:
            print(f"expected one local login block in {path}", file=sys.stderr)
            return 1
        source = source.replace(OLD_LOGIN_BLOCK, NEW_LOGIN_BLOCK, 1)
        changed = True

    if NEW_LOGIN_PAGE_BLOCK not in source:
        if source.count(OLD_LOGIN_PAGE_BLOCK) != 1:
            print(f"expected one login page block in {path}", file=sys.stderr)
            return 1
        source = source.replace(OLD_LOGIN_PAGE_BLOCK, NEW_LOGIN_PAGE_BLOCK, 1)
        changed = True

    if AUTH_MARKER not in source:
        if source.count(ENSURE_DB_BLOCK) != 1:
            print(f"expected one database initialization block in {path}", file=sys.stderr)
            return 1
        source = source.replace(ENSURE_DB_BLOCK, ENSURE_DB_BLOCK + AUTH_BLOCK, 1)
        changed = True

    if NEW_LOGOUT_BLOCK not in source:
        if source.count(OLD_LOGOUT_BLOCK) != 1:
            print(f"expected one logout block in {path}", file=sys.stderr)
            return 1
        source = source.replace(OLD_LOGOUT_BLOCK, NEW_LOGOUT_BLOCK, 1)
        changed = True

    if NEW_DEV_SERVER_BLOCK not in source:
        if source.count(OLD_DEV_SERVER_BLOCK) != 1:
            print(f"expected one development server block in {path}", file=sys.stderr)
            return 1
        source = source.replace(OLD_DEV_SERVER_BLOCK, NEW_DEV_SERVER_BLOCK, 1)
        changed = True

    if changed:
        path.write_text(source, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
