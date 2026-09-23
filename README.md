# Baby Tracker 原生飞牛 fpk

本目录是 [XiGeMaX/Baby_tracker](https://github.com/XiGeMaX/Baby_tracker) 的原生飞牛 fnOS 打包工程。上游源码位于 `upstream/`，可安装包由 `fnpack` 生成到 `dist/baby-tracker.fpk`。

## 打包方式

- 原生进程，不使用 Docker。
- 通过 `install_dep_apps=python312` 使用 fnOS Python 3.12 运行时。
- Flask、Gunicorn、Werkzeug、Pillow 以 x86_64 与 arm64 离线 wheelhouse 随包提供。
- Tailwind CSS、Lucide 和 Chart.js 已内置到 fpk，不依赖前端 CDN。
- 首次安装时，在 `TRIM_PKGVAR` 中创建独立虚拟环境，不修改系统 Python。
- SQLite 数据库保存在 `data-share` 共享目录；虚拟环境、PID 和日志保存在 fnOS 的持久化应用数据目录。
- 已接入飞牛统一网关，桌面入口统一从 `/app/baby-tracker` 打开，并通过 `app.sock` 转发。
- 安装向导填写 NAS 的局域网 IPv4 地址和服务端口；应用仅绑定该地址，不监听 `0.0.0.0`，也不会在其他网卡或公网接口上开放 TCP 端口。
- 首次从飞牛桌面进入时，当前飞牛账号会自动成为唯一管理员，并引导设置管理密码。
- 管理密码设置后，可在局域网中通过 `http://BIND_IP:端口` 使用当前飞牛账号和新密码登录。
- 用户管理中的默认管理员账号不显示“改名/改密”按钮；管理员凭据和 Home Assistant 服务地址统一在“管理配置”卡片中维护。
- “管理配置”可修改服务绑定地址和监听端口，保存后应用自动重启，新的地址和端口会同步到 Home Assistant 配置第二步。
- 退出登录后会进入应用登录页，可点击“使用飞牛账号登录”重新建立应用会话。
- 飞牛桌面入口会补齐模板字符串中的网关前缀，快速记录及动态 API 请求不会错误发往 NAS 根路径。
- 通过 `http://BIND_IP:端口` 或 `http://127.0.0.1:端口` 直接访问时，登录页不会显示仅适用于飞牛统一网关的“使用飞牛账号登录”按钮。
- 忘记管理密码时，从飞牛桌面重新进入应用，通过统一网关一键登录后在管理页面修改。
- 所有业务页面和 API 均要求登录；TCP 端口只监听指定局域网地址，网关身份只在 Unix Socket 请求中信任。

## 构建

要求：`bash`、`git`、`curl`、`jq`、Python 3.12、网络连接。

```bash
./scripts/build.sh
```

构建脚本会：

1. 使用当前 `upstream/` 克隆；如果不存在则自动克隆。
2. 复制上游运行文件并生成 fnOS 启动入口。
3. 移除上游默认管理员，加入飞牛账号鉴权补丁和首次登录设置管理密码页面。
4. 下载 Linux x86_64 和 arm64 的 Python 3.12 wheels。
5. 校验 Manifest、安装向导、JSON、生命周期脚本和包目录。
6. 调用官方 `fnpack 1.2.3` 生成 `dist/baby-tracker.fpk`。

如需先更新上游代码：

```bash
FPK_UPDATE_SOURCE=1 ./scripts/build.sh
```

如果 wheelhouse 已经完整且需要离线重建：

```bash
FPK_OFFLINE_WHEELS=1 ./scripts/build.sh
```

## 测试

```bash
./scripts/test.sh
```

测试会运行上游单元测试，并在本地启动打包后的 Gunicorn/WSGI 应用，检查登录页、静态资源、内置前端库和动态 PWA 图标。

测试会验证新安装数据库不预置任何本地用户、首次网关登录会创建飞牛账号管理员、`data-share` 会映射为全新数据目录、首次登录会要求设置管理密码、管理页面改密后可通过局域网端口登录，并确认默认账号不再生效。

管理页测试还会检查默认管理员行不显示改名和改密按钮，管理员统一使用“管理配置”卡片，服务配置变更后会同步 Home Assistant 第二步地址，普通用户操作不受影响。

网关相关测试还会校验飞牛入口下反引号模板字符串的 API 地址带有 `/app/baby-tracker` 前缀，以及端口登录页不会显示统一网关登录按钮。

网络监听测试会验证启动参数只使用向导配置的 `bind_address`，并拒绝 `0.0.0.0`、回环地址、公网地址和无效 IPv4，同时确认旧的 CIDR 白名单中间件不再打包。

鉴权冒烟测试还会检查未登录页面重定向、未登录 API 返回 `401`、TCP 端伪造网关身份被拒绝、Unix Socket 普通用户无法访问管理员 API、Home Assistant 接口必须使用有效 API Key，以及 SPA 网关前缀重写。

## 统一网关与鉴权

应用按飞牛网关注册文档提供 `app/ui/config`：

```json
{
  ".url": {
    "baby-tracker.main": {
      "gatewayPrefix": "/app/baby-tracker",
      "gatewaySocket": "app.sock",
      "url": "/app/baby-tracker"
    }
  }
}
```

`manifest` 中设置 `disable_authorization_path = false`，由飞牛统一网关先校验 NAS 登录态。应用服务同时监听 `${TRIM_APPDEST}/app.sock` 和安装时配置的 `${bind_address}:${wizard_port}`，其中：

- 通过 `app.sock` 的请求可由飞牛网关注入 `X-Trim-Userid`、`X-Trim-Username` 和 `X-Trim-Isadmin`。
- 网关用户首次访问时会自动映射为应用用户；`X-Trim-Isadmin=true` 会成为唯一管理员。
- 管理员首次通过网关登录且尚未设置管理密码时，会先跳转到设置管理密码页面；设置完成后才能进入业务页面。
- 通过局域网 TCP 端口访问时不会信任任何 `X-Trim-*` 请求头，必须使用应用登录页建立会话。
- 服务端口不再使用来源 CIDR 白名单，也不监听 `0.0.0.0`；如果需要阻止同一局域网内的其他设备访问，应由路由器、VLAN 或飞牛防火墙在网络层处理。
- 业务页面未登录时重定向到登录页，业务 API 未登录时返回 `401`，管理员 API 会继续检查应用内管理员角色。
- Home Assistant 的 `/api/ha/*` 接口不在网关匿名白名单内，传感器和按钮请求必须携带管理员在应用内生成的有效 API Key。

应用自身始终保留业务鉴权，不把飞牛网关登录态当作授权绕过。

## 安装

通过飞牛应用中心的“手动安装”选择 `dist/baby-tracker.fpk`，或在设备上执行：

```bash
appcenter-cli install-fpk dist/baby-tracker.fpk
```

安装向导的“服务设置”包含“服务绑定地址”和“监听端口”。绑定地址必须是 NAS 本机网卡上的私有 IPv4 地址，端口范围为 `1024-65535`。安装完成后首次从飞牛桌面进入，应用会自动使用当前飞牛账号建立唯一管理员，并引导设置管理密码。

安装完成后可从飞牛桌面入口 `/app/baby-tracker` 访问，也可在局域网中通过 `http://BIND_IP:8964` 访问。应用只在该绑定地址上开放 TCP 端口，不会自动开放公网或其他网卡地址。

安装完成后，可在“管理 > 管理配置”中调整绑定地址和监听端口。保存前会校验地址是否属于当前 NAS 网卡；保存成功后应用自动重启，飞牛网关和局域网端口会短暂中断。新的地址和端口会同步到 Home Assistant 配置第二步。

## 运行目录

fnOS 安装后会提供以下环境变量：

- `TRIM_APPDEST`：应用运行文件，数据库与虚拟环境不写在这里。
- `TRIM_PKGVAR`：持久化运行数据，包含指向共享目录的 `data` 链接、`venv/`、`app.log` 和 `app.pid`。
- `TRIM_PKGETC`：持久化配置，包含 `secret_key`、`service_port`、`bind_address` 和数据库初始化标记。
- `TRIM_PKGTMP`：临时文件。
- `TRIM_DATA_SHARE_PATHS`：fnOS 创建的共享目录路径；本应用使用 `baby-tracker/data`。

应用运行目录中还会创建 `app.sock` 供飞牛统一网关转发；该 Socket 由应用进程监听，不对局域网 TCP 端口开放。

`config/resource` 声明了 `baby-tracker/data`。首次安装时，`${TRIM_PKGVAR}/data` 会直接映射到该共享目录；当前版本未提供旧版本升级数据迁移，已安装旧开发版本时请先卸载再重新安装。

应用进程使用 `config/privilege` 中声明的专用 `baby_tracker` 用户和用户组运行，不请求 root 权限。

## 目录说明

```text
baby-tracker-fnos-fpk/
├── upstream/                       # 克隆的上游源码
├── packaging/
│   ├── baby-tracker/               # fnpack 应用包目录
│   │   └── wizard/                 # 安装向导表单
│   └── build-assets/               # WSGI 入口、依赖清单和图标源文件
├── scripts/
│   ├── build.sh                    # 构建 fpk
│   ├── patch_source.py             # 注入飞牛账号鉴权和管理员归一化逻辑
│   └── test.sh                     # 单元测试和运行冒烟测试
├── tools/                          # fnpack 二进制工具
├── dist/                           # 最终 fpk 和构建来源信息
└── README.md
```

## 数据备份

最稳妥的方式是在应用管理页面导出 JSON 备份。共享目录位于 `baby-tracker/data`，也可以通过 `/var/apps/baby-tracker/share/data` 访问。若需要直接备份 SQLite，请先停止应用，再复制该目录中的 `baby.db`，避免遗漏 WAL 中的数据。

## 忘记管理密码

1. 从飞牛桌面重新打开 Baby Tracker。
2. 通过飞牛统一网关一键登录，不需要使用浏览器端口登录。
3. 进入“管理”页面，在“管理配置”卡片中点击“修改管理密码”。
4. 如需调整局域网访问地址，可在同一卡片中修改“服务绑定地址”和“监听端口”后保存。
5. 设置新的 `8-128` 位密码并保存。
6. 如使用局域网内绑定地址的端口访问，使用当前飞牛用户名和新管理密码登录。

首次通过网关登录且尚未设置管理密码时，应用会直接跳转到设置管理密码页面。
