#!/usr/bin/env python3

from pathlib import Path
import sys


OLD_SENSOR_BLOCK = """            if (cfg.unit) lines.push(`    unit_of_measurement: "${cfg.unit}"`);
            if (cfg.attrs.length > 0) {
                if (cfg.attributes_path) lines.push(`    json_attributes_path: "${cfg.attributes_path}"`);
                lines.push(`    json_attributes:`);
                cfg.attrs.forEach(a => lines.push(`      - ${a}`));
            }
            lines.push(`    scan_interval: 300`);
"""

NEW_SENSOR_BLOCK = """            if (cfg.unit) lines.push(`    unit_of_measurement: "${cfg.unit}"`);
            if (cfg.attrs.length > 0) {
                if (cfg.attributes_path) lines.push(`    json_attributes_path: "${cfg.attributes_path}"`);
                lines.push(`    json_attributes:`);
                cfg.attrs.forEach(a => lines.push(`      - ${a}`));
            }
            lines.push(`    headers:`);
            lines.push(`      Authorization: "Bearer ${apiKey}"`);
            lines.push(`    scan_interval: 300`);
"""


# Keep generated Home Assistant sensors on root API paths. The fnOS gateway
# rewrites quoted "/api/" strings in JavaScript, which previously made sensors
# use /app/baby-tracker while switches stayed on the root path.
HA_SENSOR_ROOT_PATH_REPLACEMENTS = (
    (
        "resource: '/api/ha/status',",
        "resource: 'api/ha/status',",
        "HA status root path",
    ),
    (
        "resource: '/api/ha/feed-today',",
        "resource: 'api/ha/feed-today',",
        "HA feed-today root path",
    ),
    (
        "resource: '/api/ha/last-feed',",
        "resource: 'api/ha/last-feed',",
        "HA last-feed root path",
    ),
    (
        "resource: '/api/ha/excrete-today',",
        "resource: 'api/ha/excrete-today',",
        "HA excrete-today root path",
    ),
    (
        'resource: "${base}${cfg.resource}"',
        'resource: "${base}/${cfg.resource}"',
        "HA sensor base URL",
    ),
)


OLD_ADMIN_USER_ACTIONS_BLOCK = """        actions += ` <button class="text-xs px-2 py-1 rounded border border-border text-text-muted hover:text-amber-400 hover:border-amber-500/30 transition-colors" data-reset-pw="${u.id}" data-reset-name="${esc(u.nickname || u.username)}">改密</button>`;
        actions += ` <button class="text-xs px-2 py-1 rounded border border-border text-text-muted hover:text-blue-400 hover:border-blue-500/30 transition-colors" data-rename-user="${u.id}" data-rename-name="${esc(u.username)}">改名</button>`;
        if (u.role !== 'admin') {
            actions += ` <button class="text-xs px-2 py-1 rounded border border-border text-text-muted hover:text-red-400 hover:border-red-500/30 transition-colors" onclick="deleteUser(${u.id})">删除</button>`;
        }
"""

NEW_ADMIN_USER_ACTIONS_BLOCK = """        if (u.role !== 'admin') {
            actions += ` <button class="text-xs px-2 py-1 rounded border border-border text-text-muted hover:text-amber-400 hover:border-amber-500/30 transition-colors" data-reset-pw="${u.id}" data-reset-name="${esc(u.nickname || u.username)}">改密</button>`;
            actions += ` <button class="text-xs px-2 py-1 rounded border border-border text-text-muted hover:text-blue-400 hover:border-blue-500/30 transition-colors" data-rename-user="${u.id}" data-rename-name="${esc(u.username)}">改名</button>`;
            actions += ` <button class="text-xs px-2 py-1 rounded border border-border text-text-muted hover:text-red-400 hover:border-red-500/30 transition-colors" onclick="deleteUser(${u.id})">删除</button>`;
        }
"""

OLD_ADMIN_HEADER_BLOCK = """    <div class="flex items-center justify-between">
        <h1 class="text-xl font-semibold">管理</h1>
        <a href="/" class="text-text-muted hover:text-text-secondary transition-colors text-sm flex items-center gap-1">
            <i data-lucide="arrow-left" class="w-4 h-4"></i>
            返回
        </a>
    </div>
"""

NEW_ADMIN_HEADER_BLOCK = """    <div class="flex items-center justify-between">
        <h1 class="text-xl font-semibold">管理</h1>
        <a href="/" class="text-text-muted hover:text-text-secondary transition-colors text-sm flex items-center gap-1">
            <i data-lucide="arrow-left" class="w-4 h-4"></i>
            返回
        </a>
    </div>

    {% if current_user and current_user.role == 'admin' %}
    <div class="card space-y-4" id="service-config-card">
        <div class="flex items-center gap-2">
            <i data-lucide="shield-check" class="w-4 h-4 text-accent"></i>
            <h2 class="text-sm font-medium text-text-secondary">管理配置</h2>
        </div>
        <p class="text-xs text-text-muted">管理员账号：<span class="font-mono text-text-secondary">{{ current_user.username }}</span></p>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
                <label class="text-text-muted text-xs mb-1 block">服务绑定地址</label>
                <input type="text" id="admin-bind-address" class="input-field font-mono text-sm" placeholder="192.168.1.10" autocomplete="off">
            </div>
            <div>
                <label class="text-text-muted text-xs mb-1 block">监听端口</label>
                <input type="number" id="admin-service-port" class="input-field font-mono text-sm" min="1024" max="65535" placeholder="8964">
            </div>
        </div>
        <div class="flex flex-wrap gap-2">
            <button class="btn-primary text-sm w-fit" data-save-service-config>保存服务配置</button>
            <button class="btn-secondary text-sm w-fit" data-change-admin-pw data-admin-id="{{ current_user.id }}" data-admin-name="{{ current_user.username }}">
                修改管理密码
            </button>
        </div>
        <p class="text-[10px] text-text-muted">保存服务配置会校验绑定地址并自动重启应用，飞牛网关和局域网端口会短暂中断；新地址会同步到下方 Home Assistant 配置第二步。</p>
        <p class="text-[10px] text-text-muted">忘记密码时，从飞牛桌面重新进入应用并完成一键登录后，可在此修改。</p>
    </div>
    {% endif %}
"""


OLD_LOGIN_BUTTON_BLOCK = """        <div id="login-error" class="text-red-400 text-xs hidden"></div>
        <button class="btn-primary w-full py-3 text-base" onclick="doLogin()">登录</button>
    </div>
"""

NEW_LOGIN_BUTTON_BLOCK = """        <div id="login-error" class="text-red-400 text-xs hidden"></div>
        <button class="btn-primary w-full py-3 text-base" onclick="doLogin()">登录</button>
        {% if gateway_login_available %}
        <div class="relative py-1">
            <div class="absolute inset-0 flex items-center"><div class="w-full border-t border-border"></div></div>
            <div class="relative flex justify-center text-xs"><span class="px-2 bg-surface text-text-muted">或</span></div>
        </div>
        <button id="gateway-login-button" class="btn-secondary w-full py-3 text-sm flex items-center justify-center gap-2" onclick="doGatewayLogin()">
            <i data-lucide="server" class="w-4 h-4"></i>
            使用飞牛账号登录
        </button>
        <div id="gateway-login-error" class="text-red-400 text-xs hidden"></div>
        {% endif %}
    </div>
"""


OLD_LOGIN_SCRIPT_BLOCK = """// 回车登录
document.getElementById('login-password').addEventListener('keydown', e => {
    if (e.key === 'Enter') doLogin();
});
"""

NEW_LOGIN_SCRIPT_BLOCK = """async function doGatewayLogin() {
    const errEl = document.getElementById('gateway-login-error');
    errEl.classList.add('hidden');

    try {
        await api('/api/auth/gateway-login', { method: 'POST' });
        showToast('登录成功');
        setTimeout(() => window.location.href = '/', 500);
    } catch (e) {
        errEl.textContent = e.message;
        errEl.classList.remove('hidden');
    }
}

// 回车登录
document.getElementById('login-password').addEventListener('keydown', e => {
    if (e.key === 'Enter') doLogin();
});
"""


OLD_LOGOUT_BLOCK = """        async function doLogout() {
            await api('/api/auth/logout', { method: 'POST' });
            window.location.href = '/';
        }
"""

NEW_LOGOUT_BLOCK = """        async function doLogout() {
            try {
                await api('/api/auth/logout', { method: 'POST' });
            } catch (e) {}
            window.location.href = '/login?logged_out=1';
        }
"""


OLD_ADMIN_EVENTS_BLOCK = """        document.addEventListener('click', e => {
            const resetBtn = e.target.closest('[data-reset-pw]');
            if (resetBtn) showResetPasswordModal(parseInt(resetBtn.dataset.resetPw), resetBtn.dataset.resetName);
            const renameBtn = e.target.closest('[data-rename-user]');
            if (renameBtn) showRenameUserModal(parseInt(renameBtn.dataset.renameUser), renameBtn.dataset.renameName);
        });
"""

NEW_ADMIN_EVENTS_BLOCK = """        document.addEventListener('click', e => {
            const resetBtn = e.target.closest('[data-reset-pw]');
            if (resetBtn) showResetPasswordModal(parseInt(resetBtn.dataset.resetPw), resetBtn.dataset.resetName);
            const saveServiceBtn = e.target.closest('[data-save-service-config]');
            if (saveServiceBtn) saveServiceConfig();
            const ownerPwBtn = e.target.closest('[data-change-admin-pw]');
            if (ownerPwBtn) showResetPasswordModal(parseInt(ownerPwBtn.dataset.adminId), ownerPwBtn.dataset.adminName);
            const renameBtn = e.target.closest('[data-rename-user]');
            if (renameBtn) showRenameUserModal(parseInt(renameBtn.dataset.renameUser), renameBtn.dataset.renameName);
        });
"""


OLD_RESET_MODAL_BLOCK = """    modal.innerHTML = `
    <div class="bg-surface border border-border rounded-xl p-6 w-80 max-w-[90vw]">
        <h3 class="text-sm font-medium text-text-secondary mb-3">重置密码 - ${esc(userName)}</h3>
        <input type="password" id="reset-pw-input" class="input-field font-mono" placeholder="输入新密码（至少6位）" autocomplete="new-password">
        <div class="flex gap-2 mt-4">
            <button class="btn-secondary flex-1 text-sm" onclick="closeResetPasswordModal()">取消</button>
            <button class="btn-primary flex-1 text-sm" onclick="resetPassword()">确认</button>
        </div>
    </div>`;
"""

NEW_RESET_MODAL_BLOCK = """    modal.innerHTML = `
    <div class="bg-surface border border-border rounded-xl p-6 w-80 max-w-[90vw]">
        <h3 class="text-sm font-medium text-text-secondary mb-3">修改管理密码 - ${esc(userName)}</h3>
        <input type="password" id="reset-pw-input" class="input-field font-mono" placeholder="输入新密码（8-128位）" autocomplete="new-password">
        <input type="password" id="reset-pw-confirm" class="input-field font-mono mt-2" placeholder="再次输入新密码" autocomplete="new-password">
        <div class="flex gap-2 mt-4">
            <button class="btn-secondary flex-1 text-sm" onclick="closeResetPasswordModal()">取消</button>
            <button class="btn-primary flex-1 text-sm" onclick="resetPassword()">确认</button>
        </div>
    </div>`;
"""


OLD_RESET_SCRIPT_BLOCK = """async function resetPassword() {
    const pw = document.getElementById('reset-pw-input').value;
    if (pw.length < 6) {
        showToast('密码至少6个字符');
        return;
    }
"""

NEW_RESET_SCRIPT_BLOCK = """async function resetPassword() {
    const pw = document.getElementById('reset-pw-input').value;
    const confirmation = document.getElementById('reset-pw-confirm').value;
    if (pw.length < 8 || pw.length > 128) {
        showToast('密码长度应为 8-128 位');
        return;
    }
    if (pw !== confirmation) {
        showToast('两次输入的密码不一致');
        return;
    }
"""


OLD_HA_API_KEY_FUNCTION_BLOCK = "async function generateHaApiKey() {"

NEW_SERVICE_CONFIG_FUNCTIONS_BLOCK = '''async function loadServiceConfig() {
    try {
        const config = await api('/api/admin/service-config');
        const bindInput = document.getElementById('admin-bind-address');
        const portInput = document.getElementById('admin-service-port');
        if (bindInput && config.bind_address) bindInput.value = config.bind_address;
        if (portInput && config.port) portInput.value = config.port;
        syncHaServiceAddress(config);
    } catch (e) {
        console.warn('加载服务配置失败', e);
    }
}

function syncHaServiceAddress(config) {
    const host = String(config?.bind_address || '').trim();
    const port = String(config?.port || '').trim();
    const hostInput = document.getElementById('ha-host');
    const portInput = document.getElementById('ha-port');
    if (hostInput && host) hostInput.value = host;
    if (portInput && port) portInput.value = port;
}

async function saveServiceConfig() {
    const bindInput = document.getElementById('admin-bind-address');
    const portInput = document.getElementById('admin-service-port');
    const bindAddress = bindInput?.value?.trim() || '';
    const port = portInput?.value?.trim() || '';
    const portNumber = Number(port);
    if (!bindAddress) {
        showToast('请输入服务绑定地址');
        return;
    }
    if (!port || !Number.isInteger(portNumber) || portNumber < 1024 || portNumber > 65535) {
        showToast('监听端口范围应为 1024-65535');
        return;
    }
    if (!await showConfirm('保存服务配置后应用会自动重启，飞牛网关和局域网端口会短暂中断。确定继续？', { confirmText: '保存并重启' })) return;

    const button = document.querySelector('[data-save-service-config]');
    if (button) {
        button.disabled = true;
        button.classList.add('opacity-60', 'cursor-not-allowed');
    }
    try {
        const result = await api('/api/admin/service-config', {
            method: 'PUT',
            body: JSON.stringify({ bind_address: bindAddress, port }),
        });
        const applied = {
            bind_address: result.bind_address || bindAddress,
            port: String(result.port || port),
        };
        if (bindInput) bindInput.value = applied.bind_address;
        if (portInput) portInput.value = applied.port;
        syncHaServiceAddress(applied);
        const yamlOutput = document.getElementById('ha-yaml-output');
        if (yamlOutput && !yamlOutput.textContent.includes('点击上方按钮生成配置')) {
            generateHaYaml();
        }
        showToast(result.message || '服务配置已保存');
    } catch (e) {
        showToast(e.message);
    } finally {
        if (button) {
            button.disabled = false;
            button.classList.remove('opacity-60', 'cursor-not-allowed');
        }
    }
}

async function generateHaApiKey() {
'''


OLD_ADMIN_INIT_BLOCK = """function initAdmin() {
    Promise.all([loadBaby(), loadSettings(), loadStats(), loadUsers(), loadButtons(), loadLogs(), loadHaApiKey()]);
"""

NEW_ADMIN_INIT_BLOCK = """function initAdmin() {
    Promise.all([loadBaby(), loadSettings(), loadStats(), loadUsers(), loadButtons(), loadLogs(), loadHaApiKey(), loadServiceConfig()]);
"""


def patch_frontend(server_dir: Path) -> int:
    replacements = (
        (
            server_dir / "static" / "js" / "admin.js",
            OLD_SENSOR_BLOCK,
            NEW_SENSOR_BLOCK,
            "HA sensor YAML block",
        ),
        *(
            (
                server_dir / "static" / "js" / "admin.js",
                old,
                new,
                label,
            )
            for old, new, label in HA_SENSOR_ROOT_PATH_REPLACEMENTS
        ),
        (
            server_dir / "static" / "js" / "admin.js",
            OLD_ADMIN_USER_ACTIONS_BLOCK,
            NEW_ADMIN_USER_ACTIONS_BLOCK,
            "administrator user-row actions",
        ),
        (
            server_dir / "templates" / "admin.html",
            OLD_ADMIN_HEADER_BLOCK,
            NEW_ADMIN_HEADER_BLOCK,
            "admin password card",
        ),
        (
            server_dir / "static" / "js" / "admin.js",
            OLD_ADMIN_INIT_BLOCK,
            NEW_ADMIN_INIT_BLOCK,
            "admin initialization",
        ),
        (
            server_dir / "static" / "js" / "admin.js",
            OLD_HA_API_KEY_FUNCTION_BLOCK,
            NEW_SERVICE_CONFIG_FUNCTIONS_BLOCK,
            "admin service configuration functions",
        ),
        (
            server_dir / "static" / "js" / "admin.js",
            OLD_ADMIN_EVENTS_BLOCK,
            NEW_ADMIN_EVENTS_BLOCK,
            "admin password event handler",
        ),
        (
            server_dir / "static" / "js" / "admin.js",
            OLD_RESET_MODAL_BLOCK,
            NEW_RESET_MODAL_BLOCK,
            "admin password modal",
        ),
        (
            server_dir / "static" / "js" / "admin.js",
            OLD_RESET_SCRIPT_BLOCK,
            NEW_RESET_SCRIPT_BLOCK,
            "admin password validation",
        ),
        (
            server_dir / "templates" / "login.html",
            OLD_LOGIN_BUTTON_BLOCK,
            NEW_LOGIN_BUTTON_BLOCK,
            "login button block",
        ),
        (
            server_dir / "templates" / "login.html",
            OLD_LOGIN_SCRIPT_BLOCK,
            NEW_LOGIN_SCRIPT_BLOCK,
            "login script block",
        ),
        (
            server_dir / "templates" / "base.html",
            OLD_LOGOUT_BLOCK,
            NEW_LOGOUT_BLOCK,
            "logout block",
        ),
    )

    for path, old, new, label in replacements:
        source = path.read_text(encoding="utf-8")
        if new in source:
            continue
        if source.count(old) != 1:
            print(f"expected one {label} in {path}", file=sys.stderr)
            return 1
        path.write_text(source.replace(old, new, 1), encoding="utf-8")
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: patch_frontend.py SERVER_DIR", file=sys.stderr)
        return 2
    return patch_frontend(Path(sys.argv[1]))


if __name__ == "__main__":
    raise SystemExit(main())
