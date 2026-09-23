#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UPSTREAM_DIR="${ROOT_DIR}/upstream"
PACK_SERVER_DIR="${ROOT_DIR}/packaging/baby-tracker/app/server"
BUILD_DIR="${ROOT_DIR}/.build"
VENV_DIR="${BUILD_DIR}/test-venv"
SMOKE_DATA_DIR="${BUILD_DIR}/smoke-data"
SMOKE_LOG="${BUILD_DIR}/smoke.log"
SMOKE_SOCKET="${BUILD_DIR}/smoke-app.sock"
SMOKE_COOKIE="${BUILD_DIR}/smoke.cookies"
SMOKE_PORT="18964"
SMOKE_ADMIN_USER="fnosadmin"
SMOKE_ADMIN_PASSWORD="InitialAdmin123!"
SMOKE_CHANGED_ADMIN_PASSWORD="ChangedAdmin456!"
SMOKE_ETC_DIR="${BUILD_DIR}/smoke-etc"
TEST_SERVICE_LAUNCHER="${ROOT_DIR}/scripts/test-service-launcher.py"
DATA_MAP_DIR="${BUILD_DIR}/fresh-data-map"

log() {
    printf '[test] %s\n' "$1"
}

mkdir -p "${BUILD_DIR}"
if [ ! -x "${VENV_DIR}/bin/python" ]; then
    log "Creating test virtual environment"
    python3 -m venv "${VENV_DIR}"
fi
"${VENV_DIR}/bin/python" -m pip install --disable-pip-version-check -r "${UPSTREAM_DIR}/requirements.txt"

log "Validating fpk launcher icons"
"${VENV_DIR}/bin/python" - <<'PY'
from pathlib import Path
from PIL import Image

path = Path('packaging/build-assets/icons/icon_64.png')
image = Image.open(path).convert('RGBA')
bbox = image.getbbox()
if image.size != (64, 64) or bbox is None or bbox[2] - bbox[0] < 60 or bbox[3] - bbox[1] < 60:
    raise SystemExit(f'invalid 64px icon: size={image.size}, bbox={bbox}')
if image.getpixel((32, 2))[3] == 0 or image.getpixel((2, 32))[3] == 0:
    raise SystemExit('64px icon appears cropped')
PY

log "Running upstream unit tests"
(cd "${UPSTREAM_DIR}" && "${VENV_DIR}/bin/python" -m unittest -v)

log "Validating fresh data-share mapping"
rm -rf "${DATA_MAP_DIR}"
mkdir -p "${DATA_MAP_DIR}/share/baby-tracker/data" "${DATA_MAP_DIR}/pkgvar/data"
(
    export TRIM_APPDEST="${DATA_MAP_DIR}/app"
    export TRIM_PKGVAR="${DATA_MAP_DIR}/pkgvar"
    export TRIM_PKGETC="${DATA_MAP_DIR}/etc"
    export TRIM_PKGTMP="${DATA_MAP_DIR}/tmp"
    export TRIM_DATA_SHARE_PATHS="${DATA_MAP_DIR}/share/baby-tracker/data"
    source "${ROOT_DIR}/packaging/baby-tracker/cmd/main"
    map_data_dir
)
[ -L "${DATA_MAP_DIR}/pkgvar/data" ]
[ "$(readlink "${DATA_MAP_DIR}/pkgvar/data")" = "${DATA_MAP_DIR}/share/baby-tracker/data" ]
[ ! -e "${DATA_MAP_DIR}/pkgvar/data.pre-data-share" ]

if [ ! -s "${PACK_SERVER_DIR}/wsgi.py" ]; then
    log "Packaged payload is not built yet; skipping Gunicorn smoke test"
    exit 0
fi

log "Validating LAN bind-only access configuration"
grep -q -- '--bind "${bind_address}:${service_port}"' "${ROOT_DIR}/packaging/baby-tracker/cmd/main"
if grep -q -- '--bind "0.0.0.0:${service_port}"' "${ROOT_DIR}/packaging/baby-tracker/cmd/main"; then
    log "The launcher still binds the service port to 0.0.0.0"
    exit 1
fi
if grep -q 'LanAccessMiddleware' "${PACK_SERVER_DIR}/wsgi.py"; then
    log "The packaged WSGI app still contains the obsolete CIDR allowlist middleware"
    exit 1
fi
if grep -q 'LEGACY_LAN_CIDRS_FILE\|select_bind_address\|migrate_data_dir\|pre-data-share' "${ROOT_DIR}/packaging/baby-tracker/cmd/main"; then
    log "Legacy install/upgrade compatibility logic remains in the launcher"
    exit 1
fi
grep -q "app.run(host='127.0.0.1', port=5000, debug=True)" "${PACK_SERVER_DIR}/app.py"
if grep -q "host='0.0.0.0'" "${PACK_SERVER_DIR}/app.py"; then
    log "The development server fallback is not loopback-only"
    exit 1
fi

test_python="${VENV_DIR}/bin/python"
(
    export TRIM_APPDEST="${BUILD_DIR}/launcher-test/app"
    export TRIM_PKGVAR="${BUILD_DIR}/launcher-test/var"
    export TRIM_PKGETC="${BUILD_DIR}/launcher-test/etc"
    export TRIM_PKGTMP="${BUILD_DIR}/launcher-test/tmp"
    source "${ROOT_DIR}/packaging/baby-tracker/cmd/main"
    find_python() { printf '%s' "${test_python}"; }
    normalized="$(normalize_bind_address ' 192.168.1.10 ')"
    [ "${normalized}" = '192.168.1.10' ]
    wizard_bind_address='192.168.1.20'
    wizard_port='18965'
    local_ipv4_addresses() { printf '%s\n' '192.168.1.20'; }
    validate_install_values
    [ "$(cat "${TRIM_PKGETC}/bind_address")" = '192.168.1.20' ]
    [ "$(cat "${TRIM_PKGETC}/service_port")" = '18965' ]
    for address in '0.0.0.0' '127.0.0.1' '8.8.8.8' '999.1.1.1'; do
        if normalize_bind_address "${address}" >/dev/null 2>&1; then
            exit 1
        fi
    done
)

log "Validating administrator user-row action visibility"
"${VENV_DIR}/bin/python" - "${PACK_SERVER_DIR}/static/js/admin.js" <<'PY'
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

rm -rf "${SMOKE_DATA_DIR}"
rm -f "${SMOKE_COOKIE}"
mkdir -p "${SMOKE_DATA_DIR}"
rm -rf "${SMOKE_ETC_DIR}"
mkdir -p "${SMOKE_ETC_DIR}"
printf '%s\n' '192.168.1.10' > "${SMOKE_ETC_DIR}/bind_address"
printf '%s\n' "${SMOKE_PORT}" > "${SMOKE_ETC_DIR}/service_port"
log "Initializing packaged database without a local administrator"
BABY_TRACKER_DATA_DIR="${SMOKE_DATA_DIR}" \
PYTHONDONTWRITEBYTECODE=1 \
    "${VENV_DIR}/bin/python" "${PACK_SERVER_DIR}/bootstrap.py"
installed_admin_count="$("${VENV_DIR}/bin/python" -c 'import sqlite3, sys; print(sqlite3.connect(sys.argv[1]).execute("SELECT COUNT(*) FROM users WHERE role = ?", ("admin",)).fetchone()[0])' "${SMOKE_DATA_DIR}/baby.db")"
[ "${installed_admin_count}" = "0" ]
installed_user_count="$("${VENV_DIR}/bin/python" -c 'import sqlite3, sys; print(sqlite3.connect(sys.argv[1]).execute("SELECT COUNT(*) FROM users").fetchone()[0])' "${SMOKE_DATA_DIR}/baby.db")"
[ "${installed_user_count}" = "0" ]
log "Starting packaged WSGI application"
chmod +x "${TEST_SERVICE_LAUNCHER}"
rm -f "${SMOKE_ETC_DIR}/restart-called"
rm -f "${SMOKE_SOCKET}"
(
    cd "${PACK_SERVER_DIR}"
    PYTHONDONTWRITEBYTECODE=1 \
    BABY_TRACKER_DATA_DIR="${SMOKE_DATA_DIR}" \
    SECRET_KEY="test-secret" \
    TRIM_PKGETC="${SMOKE_ETC_DIR}" \
    BABY_TRACKER_CMD_MAIN="${TEST_SERVICE_LAUNCHER}" \
    "${VENV_DIR}/bin/gunicorn" \
        --bind "unix:${SMOKE_SOCKET}" \
        --bind "127.0.0.1:${SMOKE_PORT}" \
        --workers 1 \
        --access-logfile - \
        --error-logfile - \
        wsgi:application > "${SMOKE_LOG}" 2>&1
) &
server_pid=$!
trap 'kill "${server_pid}" 2>/dev/null || true' EXIT

for _ in $(seq 1 30); do
    if curl -fsS "http://127.0.0.1:${SMOKE_PORT}/login" >/dev/null 2>&1; then
        break
    fi
    sleep 0.5
done

direct_login_page="$(curl -fsS "http://127.0.0.1:${SMOKE_PORT}/login")"
if printf '%s' "${direct_login_page}" | grep -q 'gateway-login-button'; then
    log "Direct-port login page unexpectedly contains the fnOS gateway sign-in button"
    exit 1
fi
curl -fsS "http://127.0.0.1:${SMOKE_PORT}/static/css/style.css" >/dev/null
curl -fsS "http://127.0.0.1:${SMOKE_PORT}/static/icons/icon-192.png" >/dev/null
curl -fsS "http://127.0.0.1:${SMOKE_PORT}/static/vendor/tailwindcss.min.js" >/dev/null
curl -fsS "http://127.0.0.1:${SMOKE_PORT}/static/vendor/lucide.min.js" >/dev/null
curl -fsS "http://127.0.0.1:${SMOKE_PORT}/static/vendor/chart.js-4.4.7.min.js" >/dev/null
unauthenticated_api_status="$(curl -sS -o /dev/null -w '%{http_code}' "http://127.0.0.1:${SMOKE_PORT}/api/records")"
[ "${unauthenticated_api_status}" = "401" ]
unauthenticated_service_config_status="$(curl -sS -o /dev/null -w '%{http_code}' \
    -X PUT \
    -H 'Content-Type: application/json' \
    -d '{"bind_address":"192.168.1.20","port":"18965"}' \
    "http://127.0.0.1:${SMOKE_PORT}/api/admin/service-config")"
[ "${unauthenticated_service_config_status}" = "401" ]
unauthenticated_page_status="$(curl -sS -o /dev/null -w '%{http_code}' "http://127.0.0.1:${SMOKE_PORT}/")"
[ "${unauthenticated_page_status}" = "302" ]
spoofed_header_status="$(curl -sS -o /dev/null -w '%{http_code}' \
    -H 'X-Trim-Userid: 1000' \
    -H 'X-Trim-Username: fnosadmin' \
    -H 'X-Trim-Isadmin: true' \
    "http://127.0.0.1:${SMOKE_PORT}/api/records")"
[ "${spoofed_header_status}" = "401" ]
unauthenticated_ha_status="$(curl -sS -o /dev/null -w '%{http_code}' "http://127.0.0.1:${SMOKE_PORT}/api/ha/status")"
[ "${unauthenticated_ha_status}" = "401" ]
log "Testing first-login administrator password setup"
gateway_initial_status="$(curl -sS -o /dev/null -w '%{http_code}' --unix-socket "${SMOKE_SOCKET}" \
    -c "${SMOKE_COOKIE}" \
    -H 'X-Trim-Userid: 1000' \
    -H 'X-Trim-Username: fnosadmin' \
    -H 'X-Trim-Isadmin: true' \
    "http://localhost/app/baby-tracker/")"
[ "${gateway_initial_status}" = "302" ]
gateway_setup_required_status="$(curl -sS -o /dev/null -w '%{http_code}' --unix-socket "${SMOKE_SOCKET}" \
    -b "${SMOKE_COOKIE}" \
    -H 'X-Trim-Userid: 1000' \
    -H 'X-Trim-Username: fnosadmin' \
    -H 'X-Trim-Isadmin: true' \
    "http://localhost/app/baby-tracker/api/users")"
[ "${gateway_setup_required_status}" = "403" ]
gateway_setup_page="$(curl -fsS --unix-socket "${SMOKE_SOCKET}" \
    -b "${SMOKE_COOKIE}" -c "${SMOKE_COOKIE}" \
    -H 'X-Trim-Userid: 1000' \
    -H 'X-Trim-Username: fnosadmin' \
    -H 'X-Trim-Isadmin: true' \
    "http://localhost/app/baby-tracker/setup-password")"
printf '%s' "${gateway_setup_page}" | grep -q 'setup-password-input'
gateway_setup_status="$(curl -sS -o /dev/null -w '%{http_code}' --unix-socket "${SMOKE_SOCKET}" \
    -b "${SMOKE_COOKIE}" -c "${SMOKE_COOKIE}" \
    -X POST \
    -H 'Content-Type: application/json' \
    -H 'X-Trim-Userid: 1000' \
    -H 'X-Trim-Username: fnosadmin' \
    -H 'X-Trim-Isadmin: true' \
    -d "{\"password\":\"${SMOKE_ADMIN_PASSWORD}\",\"confirm_password\":\"${SMOKE_ADMIN_PASSWORD}\"}" \
    "http://localhost/app/baby-tracker/api/auth/setup-password")"
[ "${gateway_setup_status}" = "200" ]
gateway_page="$(curl -fsS --unix-socket "${SMOKE_SOCKET}" \
    -b "${SMOKE_COOKIE}" \
    -H 'X-Trim-Userid: 1000' \
    -H 'X-Trim-Username: fnosadmin' \
    -H 'X-Trim-Isadmin: true' \
    "http://localhost/app/baby-tracker/")"
printf '%s' "${gateway_page}" | grep -q '/app/baby-tracker/static/css/style.css'
gateway_dashboard_js="$(curl -fsS --unix-socket "${SMOKE_SOCKET}" \
    -H 'X-Trim-Userid: 1000' \
    -H 'X-Trim-Username: fnosadmin' \
    -H 'X-Trim-Isadmin: true' \
    "http://localhost/app/baby-tracker/static/js/dashboard.js")"
printf '%s' "${gateway_dashboard_js}" | grep -q '/app/baby-tracker/api/records/today'
printf '%s' "${gateway_dashboard_js}" | grep -q '/app/baby-tracker/api/quick-record/'
gateway_admin_js="$(curl -fsS --unix-socket "${SMOKE_SOCKET}" \
    -H 'X-Trim-Userid: 1000' \
    -H 'X-Trim-Username: fnosadmin' \
    -H 'X-Trim-Isadmin: true' \
    "http://localhost/app/baby-tracker/static/js/admin.js")"
[[ "${gateway_admin_js}" == *"resource: 'api/ha/status'"* ]]
[[ "${gateway_admin_js}" == *'resource: "${base}/api/ha/button/${sw.id}"'* ]]
[[ "${gateway_admin_js}" == *'syncHaServiceAddress(config);'* ]]
[[ "${gateway_admin_js}" == *'syncHaServiceAddress(applied);'* ]]
if [[ "${gateway_admin_js}" == *"resource: '/app/baby-tracker/api/ha/status'"* ]]; then
    log "Gateway prefix unexpectedly rewrote the generated HA sensor path"
    exit 1
fi
gateway_admin_status="$(curl -sS -o /dev/null -w '%{http_code}' --unix-socket "${SMOKE_SOCKET}" \
    -b "${SMOKE_COOKIE}" \
    -H 'X-Trim-Userid: 1000' \
    -H 'X-Trim-Username: fnosadmin' \
    -H 'X-Trim-Isadmin: true' \
    "http://localhost/app/baby-tracker/api/users")"
[ "${gateway_admin_status}" = "200" ]
gateway_users="$(curl -fsS --unix-socket "${SMOKE_SOCKET}" \
    -b "${SMOKE_COOKIE}" \
    -H 'X-Trim-Userid: 1000' \
    -H 'X-Trim-Username: fnosadmin' \
    -H 'X-Trim-Isadmin: true' \
    "http://localhost/app/baby-tracker/api/users")"
[ "$(printf '%s' "${gateway_users}" | jq '[.[] | select(.role == "admin")] | length')" = "1" ]
[ "$(printf '%s' "${gateway_users}" | jq -r '.[] | select(.role == "admin") | .username')" = "${SMOKE_ADMIN_USER}" ]
gateway_user_status="$(curl -sS -o /dev/null -w '%{http_code}' --unix-socket "${SMOKE_SOCKET}" \
    -H 'X-Trim-Userid: 1001' \
    -H 'X-Trim-Username: fnosuser' \
    -H 'X-Trim-Isadmin: false' \
    "http://localhost/app/baby-tracker/api/users")"
[ "${gateway_user_status}" = "403" ]
gateway_user_service_config_status="$(curl -sS -o /dev/null -w '%{http_code}' --unix-socket "${SMOKE_SOCKET}" \
    -X PUT \
    -H 'Content-Type: application/json' \
    -H 'X-Trim-Userid: 1001' \
    -H 'X-Trim-Username: fnosuser' \
    -H 'X-Trim-Isadmin: false' \
    -d '{"bind_address":"192.168.1.20","port":"18965"}' \
    "http://localhost/app/baby-tracker/api/admin/service-config")"
[ "${gateway_user_service_config_status}" = "403" ]
gateway_spa_js="$(curl -fsS --unix-socket "${SMOKE_SOCKET}" \
    -H 'X-Trim-Userid: 1000' \
    -H 'X-Trim-Username: fnosadmin' \
    -H 'X-Trim-Isadmin: true' \
    "http://localhost/app/baby-tracker/static/js/spa.js" )"
printf '%s' "${gateway_spa_js}" | grep -q "'/app/baby-tracker/trends':"
log "Testing fnOS gateway logout and sign-in entry"
gateway_logout_status="$(curl -sS -o /dev/null -w '%{http_code}' --unix-socket "${SMOKE_SOCKET}" \
    -b "${SMOKE_COOKIE}" -c "${SMOKE_COOKIE}" \
    -X POST \
    -H 'X-Trim-Userid: 1000' \
    -H 'X-Trim-Username: fnosadmin' \
    -H 'X-Trim-Isadmin: true' \
    "http://localhost/app/baby-tracker/api/auth/logout")"
[ "${gateway_logout_status}" = "200" ]
logged_out_page_status="$(curl -sS -o /dev/null -w '%{http_code}' --unix-socket "${SMOKE_SOCKET}" \
    -b "${SMOKE_COOKIE}" \
    -H 'X-Trim-Userid: 1000' \
    -H 'X-Trim-Username: fnosadmin' \
    -H 'X-Trim-Isadmin: true' \
    "http://localhost/app/baby-tracker/")"
[ "${logged_out_page_status}" = "302" ]
gateway_login_page="$(curl -fsS --unix-socket "${SMOKE_SOCKET}" \
    -b "${SMOKE_COOKIE}" \
    -H 'X-Trim-Userid: 1000' \
    -H 'X-Trim-Username: fnosadmin' \
    -H 'X-Trim-Isadmin: true' \
    "http://localhost/app/baby-tracker/login")"
printf '%s' "${gateway_login_page}" | grep -q 'doGatewayLogin'
printf '%s' "${gateway_login_page}" | grep -q 'gateway-login-button'
gateway_relogin_status="$(curl -sS -o /dev/null -w '%{http_code}' --unix-socket "${SMOKE_SOCKET}" \
    -b "${SMOKE_COOKIE}" -c "${SMOKE_COOKIE}" \
    -X POST \
    -H 'X-Trim-Userid: 1000' \
    -H 'X-Trim-Username: fnosadmin' \
    -H 'X-Trim-Isadmin: true' \
    "http://localhost/app/baby-tracker/api/auth/gateway-login")"
[ "${gateway_relogin_status}" = "200" ]
gateway_admin_after_status="$(curl -sS -o /dev/null -w '%{http_code}' --unix-socket "${SMOKE_SOCKET}" \
    -b "${SMOKE_COOKIE}" \
    -H 'X-Trim-Userid: 1000' \
    -H 'X-Trim-Username: fnosadmin' \
    -H 'X-Trim-Isadmin: true' \
    "http://localhost/app/baby-tracker/api/users")"
[ "${gateway_admin_after_status}" = "200" ]
log "Testing Home Assistant API key"
ha_api_key="$(curl -fsS --unix-socket "${SMOKE_SOCKET}" \
    -b "${SMOKE_COOKIE}" \
    -X POST \
    -H 'X-Trim-Userid: 1000' \
    -H 'X-Trim-Username: fnosadmin' \
    -H 'X-Trim-Isadmin: true' \
    "http://localhost/app/baby-tracker/api/ha/api-key" | jq -r '.api_key')"
[ -n "${ha_api_key}" ] && [ "${ha_api_key}" != "null" ]
ha_key_status="$(curl -sS -o /dev/null -w '%{http_code}' \
    -H "Authorization: Bearer ${ha_api_key}" \
    "http://127.0.0.1:${SMOKE_PORT}/api/ha/status")"
[ "${ha_key_status}" = "200" ]
log "Testing administrator password change from the management page"
gateway_admin_id="$(printf '%s' "${gateway_users}" | jq -r '.[] | select(.role == "admin") | .id')"
[ -n "${gateway_admin_id}" ] && [ "${gateway_admin_id}" != "null" ]
gateway_admin_page="$(curl -fsS --unix-socket "${SMOKE_SOCKET}" \
    -b "${SMOKE_COOKIE}" \
    -H 'X-Trim-Userid: 1000' \
    -H 'X-Trim-Username: fnosadmin' \
    -H 'X-Trim-Isadmin: true' \
    "http://localhost/app/baby-tracker/admin")"
printf '%s' "${gateway_admin_page}" | grep -q 'data-change-admin-pw'
printf '%s' "${gateway_admin_page}" | grep -q '管理配置'
printf '%s' "${gateway_admin_page}" | grep -q 'id="admin-bind-address"'
printf '%s' "${gateway_admin_page}" | grep -q 'id="admin-service-port"'
printf '%s' "${gateway_admin_page}" | grep -q 'data-save-service-config'
gateway_service_config="$(curl -fsS --unix-socket "${SMOKE_SOCKET}" \
    -b "${SMOKE_COOKIE}" \
    -H 'X-Trim-Userid: 1000' \
    -H 'X-Trim-Username: fnosadmin' \
    -H 'X-Trim-Isadmin: true' \
    "http://localhost/app/baby-tracker/api/admin/service-config")"
[ "$(printf '%s' "${gateway_service_config}" | jq -r '.bind_address')" = '192.168.1.10' ]
[ "$(printf '%s' "${gateway_service_config}" | jq -r '.port')" = "${SMOKE_PORT}" ]
gateway_service_config_update="$(curl -fsS --unix-socket "${SMOKE_SOCKET}" \
    -b "${SMOKE_COOKIE}" \
    -X PUT \
    -H 'Content-Type: application/json' \
    -H 'X-Trim-Userid: 1000' \
    -H 'X-Trim-Username: fnosadmin' \
    -H 'X-Trim-Isadmin: true' \
    -d '{"bind_address":"192.168.1.20","port":"18965"}' \
    "http://localhost/app/baby-tracker/api/admin/service-config")"
[ "$(printf '%s' "${gateway_service_config_update}" | jq -r '.bind_address')" = '192.168.1.20' ]
[ "$(printf '%s' "${gateway_service_config_update}" | jq -r '.port')" = '18965' ]
[ "$(printf '%s' "${gateway_service_config_update}" | jq -r '.restarted')" = 'true' ]
for _ in $(seq 1 20); do
    [ -f "${SMOKE_ETC_DIR}/restart-called" ] && break
    sleep 0.1
done
[ -f "${SMOKE_ETC_DIR}/restart-called" ]
[ "$(cat "${SMOKE_ETC_DIR}/bind_address")" = '192.168.1.20' ]
[ "$(cat "${SMOKE_ETC_DIR}/service_port")" = '18965' ]
gateway_admin_change_status="$(curl -sS -o /dev/null -w '%{http_code}' --unix-socket "${SMOKE_SOCKET}" \
    -b "${SMOKE_COOKIE}" \
    -X PUT \
    -H 'Content-Type: application/json' \
    -H 'X-Trim-Userid: 1000' \
    -H 'X-Trim-Username: fnosadmin' \
    -H 'X-Trim-Isadmin: true' \
    -d "{\"password\":\"${SMOKE_CHANGED_ADMIN_PASSWORD}\"}" \
    "http://localhost/app/baby-tracker/api/users/${gateway_admin_id}/password")"
[ "${gateway_admin_change_status}" = "200" ]
new_password_status="$(curl -sS -o /dev/null -w '%{http_code}' \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"${SMOKE_ADMIN_USER}\",\"password\":\"${SMOKE_CHANGED_ADMIN_PASSWORD}\"}" \
    "http://127.0.0.1:${SMOKE_PORT}/api/auth/login")"
[ "${new_password_status}" = "200" ]
old_password_status="$(curl -sS -o /dev/null -w '%{http_code}' \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"${SMOKE_ADMIN_USER}\",\"password\":\"${SMOKE_ADMIN_PASSWORD}\"}" \
    "http://127.0.0.1:${SMOKE_PORT}/api/auth/login")"
[ "${old_password_status}" = "401" ]
admin_rows="$("${VENV_DIR}/bin/python" -c 'import sqlite3, sys; print(",".join(row[0] for row in sqlite3.connect(sys.argv[1]).execute("SELECT username FROM users WHERE role = ? ORDER BY id", ("admin",))))' "${SMOKE_DATA_DIR}/baby.db")"
[ "${admin_rows}" = "${SMOKE_ADMIN_USER}" ]
if curl -fsS \
    -H 'Content-Type: application/json' \
    -d '{"username":"admin","password":"admin123"}' \
    "http://127.0.0.1:${SMOKE_PORT}/api/auth/login" >/dev/null 2>&1; then
    log "Default administrator credentials were unexpectedly accepted"
    exit 1
fi
kill "${server_pid}" 2>/dev/null || true
wait "${server_pid}" 2>/dev/null || true
trap - EXIT
log "Upstream tests and packaged smoke test passed"
