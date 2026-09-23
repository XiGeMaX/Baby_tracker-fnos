#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="${ROOT_DIR}/source"
PACK_DIR="${ROOT_DIR}/packaging/baby-tracker"
ASSETS_DIR="${ROOT_DIR}/packaging/build-assets"
SERVER_DIR="${PACK_DIR}/app/server"
WHEELHOUSE_DIR="${ASSETS_DIR}/wheelhouse"
TOOLS_DIR="${ROOT_DIR}/tools"
DIST_DIR="${ROOT_DIR}/dist"
FNPACK_VERSION="1.2.3"
REPO_URL="https://github.com/XiGeMaX/Baby_tracker-fnos.git"

log() {
    printf '[build] %s\n' "$1"
}

die() {
    printf '[build] ERROR: %s\n' "$1" >&2
    exit 1
}

regex_matches() {
    local pattern="$1" value="$2"
    "${PYTHON_BIN:-python3}" - "${pattern}" "${value}" <<'PY'
import re
import sys

raise SystemExit(0 if re.fullmatch(sys.argv[1], sys.argv[2]) else 1)
PY
}

ensure_fnpack() {
    if [ -n "${FNPACK_BIN:-}" ]; then
        [ -x "${FNPACK_BIN}" ] || die "FNPACK_BIN is not executable: ${FNPACK_BIN}"
        printf '%s' "${FNPACK_BIN}"
        return 0
    fi

    local os arch name url target
    os="$(uname -s)"
    arch="$(uname -m)"

    case "${os}:${arch}" in
        Darwin:arm64) name="fnpack-${FNPACK_VERSION}-darwin-arm64" ;;
        Darwin:x86_64) name="fnpack-${FNPACK_VERSION}-darwin-amd64" ;;
        Linux:aarch64|Linux:arm64) name="fnpack-${FNPACK_VERSION}-linux-arm64" ;;
        Linux:x86_64|Linux:amd64) name="fnpack-${FNPACK_VERSION}-linux-amd64" ;;
        *) die "Unsupported build host: ${os} ${arch}" ;;
    esac

    target="${TOOLS_DIR}/${name}"
    if [ ! -x "${target}" ]; then
        url="https://static2.fnnas.com/fnpack/${name}"
        log "Downloading ${name}"
        mkdir -p "${TOOLS_DIR}"
        curl -fL --retry 3 "${url}" -o "${target}"
        chmod +x "${target}"
    fi
    printf '%s' "${target}"
}

stage_payload() {
    log "Staging fnOS source"
    rm -rf "${SERVER_DIR}"
    mkdir -p "${SERVER_DIR}/wheelhouse"

    cp "${SOURCE_DIR}/app.py" "${SERVER_DIR}/app.py"
    cp "${SOURCE_DIR}/requirements.txt" "${SERVER_DIR}/requirements-source.txt"
    cp "${SOURCE_DIR}/LICENSE" "${SERVER_DIR}/LICENSE"
    cp "${ASSETS_DIR}/THIRD_PARTY_NOTICES.md" "${SERVER_DIR}/THIRD_PARTY_NOTICES.md"
    cp -R "${SOURCE_DIR}/templates" "${SERVER_DIR}/templates"
    cp -R "${SOURCE_DIR}/static" "${SERVER_DIR}/static"
    cp "${ASSETS_DIR}/setup-password.html" "${SERVER_DIR}/templates/setup-password.html"
    cp "${ASSETS_DIR}/wsgi.py" "${SERVER_DIR}/wsgi.py"
    cp "${ASSETS_DIR}/bootstrap.py" "${SERVER_DIR}/bootstrap.py"
    cp "${ASSETS_DIR}/requirements-fnos.txt" "${SERVER_DIR}/requirements-fnos.txt"
    cp -R "${WHEELHOUSE_DIR}/." "${SERVER_DIR}/wheelhouse/"
    "${PYTHON_BIN:-python3}" "${ROOT_DIR}/scripts/patch_source.py" "${SERVER_DIR}/app.py"
    "${PYTHON_BIN:-python3}" "${ROOT_DIR}/scripts/patch_frontend.py" "${SERVER_DIR}"

    mkdir -p "${SERVER_DIR}/static/vendor"
    cp "${ASSETS_DIR}/vendor-tailwindcss.min.js" "${SERVER_DIR}/static/vendor/tailwindcss.min.js"
    cp "${ASSETS_DIR}/vendor-lucide.min.js" "${SERVER_DIR}/static/vendor/lucide.min.js"
    cp "${ASSETS_DIR}/vendor-chart.js-4.4.7.min.js" "${SERVER_DIR}/static/vendor/chart.js-4.4.7.min.js"

    perl -0pi -e 's#https://cdn\.tailwindcss\.com#/static/vendor/tailwindcss.min.js#g; s#https://unpkg\.com/lucide\@0\.460\.0#/static/vendor/lucide.min.js#g' "${SERVER_DIR}/templates/base.html"
    perl -0pi -e 's#https://cdn\.jsdelivr\.net/npm/chart\.js\@4\.4\.7#/static/vendor/chart.js-4.4.7.min.js#g' "${SERVER_DIR}/templates/trends.html"
    perl -ni -e 'print unless /fonts\.(?:googleapis|gstatic)\.com/' "${SERVER_DIR}/templates/base.html"
    perl -ni -e 'print unless /<link rel="dns-prefetch"/' "${SERVER_DIR}/templates/base.html"

    mkdir -p "${PACK_DIR}/app/ui/images"
    cp "${ASSETS_DIR}/icons/icon_256.png" "${PACK_DIR}/ICON_256.PNG"
    cp "${ASSETS_DIR}/icons/icon_64.png" "${PACK_DIR}/ICON.PNG"
    cp "${ASSETS_DIR}/icons/icon_256.png" "${PACK_DIR}/app/ui/images/icon_256.png"
    cp "${ASSETS_DIR}/icons/icon_64.png" "${PACK_DIR}/app/ui/images/icon_64.png"
}

build_wheelhouse() {
    local python_bin platform
    python_bin="${PYTHON_BIN:-python3}"
    command -v "${python_bin}" >/dev/null 2>&1 || die "Python 3 is required to download wheels."

    if [ "${FPK_OFFLINE_WHEELS:-0}" = "1" ]; then
        log "Keeping existing wheelhouse"
        [ -n "$(find "${WHEELHOUSE_DIR}" -maxdepth 1 -type f -name '*.whl' -print -quit)" ] || die "Offline wheelhouse is empty."
        return 0
    fi

    log "Downloading Linux x86_64 and arm64 wheels for Python 3.12"
    rm -rf "${WHEELHOUSE_DIR}"
    mkdir -p "${WHEELHOUSE_DIR}"
    for platform in manylinux2014_x86_64 manylinux2014_aarch64; do
        "${python_bin}" -m pip download \
            --disable-pip-version-check \
            --no-cache-dir \
            --only-binary=:all: \
            --implementation cp \
            --python-version 312 \
            --abi cp312 \
            --platform "${platform}" \
            --dest "${WHEELHOUSE_DIR}" \
            -r "${ASSETS_DIR}/requirements-fnos.txt"
    done
}

validate_package() {
    log "Validating package files"
    find "${PACK_DIR}/app" -name '.DS_Store' -type f -delete
    [ -s "${PACK_DIR}/manifest" ] || die "manifest is missing."
    grep -q 'Home Assistant 集成' "${PACK_DIR}/manifest" || die "Manifest description is missing the Home Assistant integration introduction."
    grep -q '重置管理密码' "${PACK_DIR}/manifest" || die "Manifest description is missing the admin password reset flow."
    if grep -q 'reset-password.txt' "${PACK_DIR}/manifest"; then
        die "Manifest description still contains the legacy reset-password flow."
    fi
    [ -s "${PACK_DIR}/ICON.PNG" ] || die "ICON.PNG is missing."
    [ -s "${PACK_DIR}/ICON_256.PNG" ] || die "ICON_256.PNG is missing."
    [ -s "${PACK_DIR}/app/server/wsgi.py" ] || die "WSGI entrypoint is missing."
    [ -s "${PACK_DIR}/app/server/bootstrap.py" ] || die "Database bootstrap script is missing."
    [ -s "${SERVER_DIR}/templates/setup-password.html" ] || die "First-login password setup page is missing."
    if [ -e "${SERVER_DIR}/reset_watcher.py" ]; then
        die "Legacy reset-password watcher is still packaged."
    fi
    [ -s "${PACK_DIR}/wizard/install" ] || die "Install wizard is missing."
    if grep -q 'BABY_TRACKER_ADMIN_USERNAME\|BABY_TRACKER_ADMIN_PASSWORD' "${SERVER_DIR}/app.py"; then
        die "Legacy installer administrator configuration is still packaged."
    fi
    grep -q 'fnOS gateway authentication' "${SERVER_DIR}/app.py" || die "Authentication gate is missing."
    grep -q "app.run(host='127.0.0.1', port=5000, debug=True)" "${SERVER_DIR}/app.py" || die "Development server fallback must bind to loopback only."
    if grep -q "host='0.0.0.0'" "${SERVER_DIR}/app.py"; then
        die "Application source still contains an all-interface listener."
    fi
    grep -q 'X-Trim-Userid' "${SERVER_DIR}/app.py" || die "Gateway identity handling is missing."
    grep -q 'gateway-login' "${SERVER_DIR}/app.py" || die "Gateway sign-in endpoint is missing."
    grep -q 'gateway_login_disabled' "${SERVER_DIR}/app.py" || die "Gateway logout state is missing."
    grep -q 'admin_password_initialized' "${SERVER_DIR}/app.py" || die "Admin password setup state is missing."
    grep -q '/api/auth/setup-password' "${SERVER_DIR}/app.py" || die "Admin password setup endpoint is missing."
    grep -q 'doGatewayLogin' "${SERVER_DIR}/templates/login.html" || die "Gateway sign-in entry is missing."
    grep -q '管理配置' "${SERVER_DIR}/templates/admin.html" || die "Admin configuration card is missing."
    grep -q 'id="admin-bind-address"' "${SERVER_DIR}/templates/admin.html" || die "Admin bind-address input is missing."
    grep -q 'id="admin-service-port"' "${SERVER_DIR}/templates/admin.html" || die "Admin service-port input is missing."
    grep -q '/api/admin/service-config' "${SERVER_DIR}/app.py" || die "Admin service-config API is missing."
    grep -q '仅管理员可以修改服务配置' "${SERVER_DIR}/app.py" || die "Admin service-config API authorization is missing."
    grep -q 'loadServiceConfig()' "${SERVER_DIR}/static/js/admin.js" || die "Admin service-config loader is missing."
    grep -q 'syncHaServiceAddress(applied)' "${SERVER_DIR}/static/js/admin.js" || die "HA service-address synchronization is missing."
    grep -q 'data-save-service-config' "${SERVER_DIR}/templates/admin.html" || die "Admin service-config save control is missing."
    grep -q 'BABY_TRACKER_CMD_MAIN' "${SERVER_DIR}/app.py" || die "Packaged app cannot locate the service launcher."
    grep -q 'BABY_TRACKER_CMD_MAIN' "${PACK_DIR}/cmd/main" || die "Launcher command path is not passed to the app runtime."
    grep -q '^    configure)' "${PACK_DIR}/cmd/main" || die "Launcher configure command is missing."
    grep -q '^    restart)' "${PACK_DIR}/cmd/main" || die "Launcher restart command is missing."
    grep -q 'gateway_login_available=_gateway_identity() is not None' "${SERVER_DIR}/app.py" || die "Gateway sign-in visibility flag is missing."
    grep -q '{% if gateway_login_available %}' "${SERVER_DIR}/templates/login.html" || die "Gateway sign-in button is not environment-gated."
    grep -q 'login?logged_out=1' "${SERVER_DIR}/templates/base.html" || die "Logout redirect is missing."
    grep -q 'Authorization: "Bearer ${apiKey}"' "${SERVER_DIR}/static/js/admin.js" || die "HA API key headers are missing."
    "${PYTHON_BIN:-python3}" - "${SERVER_DIR}/static/js/admin.js" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1]).read_text(encoding="utf-8")
expected = """        if (u.role !== 'admin') {
            actions += ` <button class="text-xs px-2 py-1 rounded border border-border text-text-muted hover:text-amber-400 hover:border-amber-500/30 transition-colors" data-reset-pw="${u.id}" data-reset-name="${esc(u.nickname || u.username)}">改密</button>`;
            actions += ` <button class="text-xs px-2 py-1 rounded border border-border text-text-muted hover:text-blue-400 hover:border-blue-500/30 transition-colors" data-rename-user="${u.id}" data-rename-name="${esc(u.username)}">改名</button>`;
            actions += ` <button class="text-xs px-2 py-1 rounded border border-border text-text-muted hover:text-red-400 hover:border-red-500/30 transition-colors" onclick="deleteUser(${u.id})">删除</button>`;
        }
"""
if source.count(expected) != 1:
    raise SystemExit("administrator user-row action visibility patch is missing or duplicated")

ha_root_paths = (
    "resource: 'api/ha/status',",
    "resource: 'api/ha/feed-today',",
    "resource: 'api/ha/last-feed',",
    "resource: 'api/ha/excrete-today',",
    'resource: "${base}/${cfg.resource}"',
    'resource: "${base}/api/ha/button/${sw.id}"',
)
missing = [value for value in ha_root_paths if source.count(value) != 1]
if missing:
    raise SystemExit(f"HA root API paths are missing or duplicated: {missing}")
if "resource: '/api/ha/" in source:
    raise SystemExit("HA sensor paths still start with /api/ and can be rewritten by the fnOS gateway")
PY
    grep -q 'TRIM_DATA_SHARE_PATHS' "${PACK_DIR}/cmd/main" || die "data-share mapping is missing."
    if grep -q 'LEGACY_LAN_CIDRS_FILE\|migrate_data_dir\|pre-data-share' "${PACK_DIR}/cmd/main"; then
        die "Legacy install/upgrade compatibility logic is still packaged."
    fi
    grep -q -- '--bind "${bind_address}:${service_port}"' "${PACK_DIR}/cmd/main" || die "Service port must bind to the configured LAN address."
    if grep -q -- '--bind "0.0.0.0:${service_port}"' "${PACK_DIR}/cmd/main"; then
        die "Launcher must not bind the service port to 0.0.0.0."
    fi
    grep -q 'GATEWAY_SOCKET' "${PACK_DIR}/cmd/main" || die "Gateway Unix Socket is missing."
    grep -q 'GatewayPrefixMiddleware' "${SERVER_DIR}/wsgi.py" || die "Gateway prefix middleware is missing."
    if grep -q 'LanAccessMiddleware' "${SERVER_DIR}/wsgi.py"; then
        die "Legacy LAN CIDR allowlist middleware is still packaged."
    fi
    grep -q 'b"`"' "${SERVER_DIR}/wsgi.py" || die "Gateway template-literal URL rewriting is missing."
    if grep -q 'reset_watcher' "${SERVER_DIR}/wsgi.py"; then
        die "Legacy reset-password watcher is still referenced."
    fi
    [ -s "${SERVER_DIR}/static/vendor/tailwindcss.min.js" ] || die "Tailwind runtime is missing."
    [ -s "${SERVER_DIR}/static/vendor/lucide.min.js" ] || die "Lucide runtime is missing."
    [ -s "${SERVER_DIR}/static/vendor/chart.js-4.4.7.min.js" ] || die "Chart.js runtime is missing."
    [ -n "$(find "${SERVER_DIR}/wheelhouse" -maxdepth 1 -type f -name '*.whl' -print -quit)" ] || die "wheelhouse is empty."
    jq empty "${PACK_DIR}/config/privilege"
    jq empty "${PACK_DIR}/config/resource"
    jq -e '."data-share".shares | any(.name == "baby-tracker/data")' "${PACK_DIR}/config/resource" >/dev/null || die "data-share resource is incomplete."
    jq empty "${PACK_DIR}/app/ui/config"
    jq empty "${PACK_DIR}/wizard/install"
    jq -e 'any(.[].items[]; .field == "wizard_port") and any(.[].items[]; .field == "wizard_bind_address") and all(.[].items[]; (.field == null or .field == "wizard_port" or .field == "wizard_bind_address"))' "${PACK_DIR}/wizard/install" >/dev/null || die "Install wizard must configure the service port and LAN bind address."
    grep -q '引导设置管理密码' "${PACK_DIR}/wizard/install" || die "Install wizard is missing the admin password setup guidance."
    jq -e 'any(.[].items[]; .field == "wizard_bind_address" and (([.rules[] | has("min") or has("max")] | any) | not) and any(.rules[]; has("pattern")))' "${PACK_DIR}/wizard/install" >/dev/null || die "LAN bind address wizard validation is missing."
    jq -e 'any(.[].items[]; .field == "wizard_port" and (([.rules[] | has("min") or has("max")] | any) | not) and any(.rules[]; has("pattern")))' "${PACK_DIR}/wizard/install" >/dev/null || die "Port wizard validation must use pattern-only numeric range rules."
    port_pattern="$(jq -r '.[].items[] | select(.field == "wizard_port") | .rules[] | select(.pattern != null) | .pattern' "${PACK_DIR}/wizard/install")"
    for port in 1024 8964 65535; do
        regex_matches "${port_pattern}" "${port}" || die "Port pattern rejects ${port}."
    done
    for port in 1023 65536; do
        if regex_matches "${port_pattern}" "${port}"; then
            die "Port pattern accepts out-of-range value ${port}."
        fi
    done
    bind_pattern="$(jq -r '.[].items[] | select(.field == "wizard_bind_address") | .rules[] | select(.pattern != null) | .pattern' "${PACK_DIR}/wizard/install")"
    for address in '192.168.1.10' '10.1.2.3' '172.16.8.9'; do
        regex_matches "${bind_pattern}" "${address}" || die "Bind address pattern rejects ${address}."
    done
    for address in '999.1.1.1' '192.168.1.10/24' '192.168.1.10,10.0.0.1'; do
        if regex_matches "${bind_pattern}" "${address}"; then
            die "Bind address pattern accepts invalid value ${address}."
        fi
    done
    jq -e '.".url"."baby-tracker.main" | .gatewayPrefix == "/app/baby-tracker" and .gatewaySocket == "app.sock" and .url == "/app/baby-tracker"' "${PACK_DIR}/app/ui/config" >/dev/null || die "Unified gateway desktop entry is incomplete."
    bash -n "${PACK_DIR}/cmd/main"
    bash -n "${PACK_DIR}/cmd/install_callback"
    bash -n "${PACK_DIR}/cmd/upgrade_callback"
    bash -n "${PACK_DIR}/cmd/uninstall_init"
    PYTHONPYCACHEPREFIX="${ROOT_DIR}/.build/pycache" "${PYTHON_BIN:-python3}" -m py_compile "${ROOT_DIR}/scripts/patch_source.py" "${ROOT_DIR}/scripts/patch_frontend.py" "${SERVER_DIR}/bootstrap.py" "${SERVER_DIR}/wsgi.py"
    chmod +x "${PACK_DIR}/cmd/"*
}

main() {
    local fnpack_bin commit
    fnpack_bin="$(ensure_fnpack)"
    build_wheelhouse
    stage_payload
    validate_package

    mkdir -p "${DIST_DIR}"
    commit="$(git -C "${ROOT_DIR}" rev-parse HEAD 2>/dev/null || printf 'unknown')"
    {
        printf 'repository=%s\n' "${REPO_URL}"
        printf 'commit=%s\n' "${commit}"
        printf 'built_at=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
        printf 'fnpack_version=%s\n' "${FNPACK_VERSION}"
    } > "${DIST_DIR}/SOURCE_INFO.txt"

    log "Building FPK with fnpack"
    (cd "${ROOT_DIR}" && "${fnpack_bin}" build --directory "${PACK_DIR}")
    rm -f "${ROOT_DIR}/app.tgz"

    local generated
    generated="$(find "${ROOT_DIR}" -maxdepth 1 -type f -name 'baby-tracker*.fpk' -print -quit)"
    if [ -z "${generated}" ]; then
        generated="$(find "${ROOT_DIR}/packaging" -maxdepth 1 -type f -name 'baby-tracker*.fpk' -print -quit)"
    fi
    [ -n "${generated}" ] || die "fnpack completed but no FPK was found."
    mv "${generated}" "${DIST_DIR}/baby-tracker.fpk"
    log "Created ${DIST_DIR}/baby-tracker.fpk"
}

main "$@"
