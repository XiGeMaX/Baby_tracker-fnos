# Baby Tracker for fnOS

[![Download Latest FPK](https://img.shields.io/badge/Download-Latest%20FPK-0ea5e9?style=for-the-badge&logo=github)](https://github.com/XiGeMaX/Baby_tracker-fnos/releases/latest)
[![fnOS](https://img.shields.io/badge/fnOS-native%20FPK-0f766e?style=flat-square)](#)
[![Platform](https://img.shields.io/badge/platform-x86__64%20%7C%20arm64-334155?style=flat-square)](#)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](#)
[![Upstream](https://img.shields.io/badge/upstream-Baby__tracker-181717?style=flat-square&logo=github)](https://github.com/XiGeMaX/Baby_tracker)

这是 [XiGeMaX/Baby_tracker](https://github.com/XiGeMaX/Baby_tracker) 的飞牛 fnOS 原生 FPK 打包工程。应用直接运行 Flask/Gunicorn，不使用 Docker，并针对飞牛统一网关、账号体系、Python 3.12、设备架构和共享数据目录完成了适配。

## 下载

[**下载最新 FPK 安装包**](https://github.com/XiGeMaX/Baby_tracker-fnos/releases/latest) · [查看全部 Releases](https://github.com/XiGeMaX/Baby_tracker-fnos/releases)

Release 由 GitHub Actions 在推送 `v*` 标签后自动构建和发布，安装包文件名固定为 `baby-tracker.fpk`，同时提供 SHA256 校验文件和构建来源信息。

<p align="center">
  <img src="https://raw.githubusercontent.com/XiGeMaX/Baby_tracker/main/screenshots/dashboard.png" alt="Baby Tracker dashboard" width="900">
</p>

## 主要特性

- 原生 fnOS 应用进程，不依赖 Docker。
- 支持 x86_64 和 arm64，设备自动使用对应的 Python 3.12 wheelhouse。
- 接入飞牛统一网关，桌面入口通过 `/app/baby-tracker` 和 `app.sock` 访问。
- 支持飞牛账号登录，当前飞牛用户首次访问时映射为应用管理员。
- 首次登录强制设置管理密码，新安装不预置任何本地管理员。
- SQLite 数据库保存在 `data-share`，卸载或升级应用不会误删业务数据。
- Tailwind CSS、Lucide、Chart.js 和 Python 依赖全部内置，不依赖公网 CDN。
- 服务端口只监听安装向导指定的局域网 IPv4 地址，不监听 `0.0.0.0`。
- 业务页面和 API 始终要求登录，Home Assistant API 使用独立 API Key。
- 支持管理页修改管理密码、绑定地址、监听端口和 Home Assistant 服务地址。

## fnOS 适配

| 适配项 | 实现方式 |
| --- | --- |
| 应用运行方式 | Flask + Gunicorn，原生进程，不使用 Docker |
| Python 运行时 | `install_dep_apps=python312` 自动安装飞牛 Python 3.12 |
| Python 环境 | 首次安装时在 `TRIM_PKGVAR` 创建独立虚拟环境，不修改系统 Python |
| 统一网关 | `app.sock` + `/app/baby-tracker` 网关入口 |
| 飞牛账号 | 只信任 Unix Socket 中由飞牛网关注入的 `X-Trim-*` 身份头 |
| 访问控制 | 网关登录和局域网登录分离，TCP 请求不能伪造飞牛身份 |
| 网络监听 | 绑定向导指定的 NAS 局域网 IPv4 地址，端口范围 `1024-65535` |
| 持久化数据 | `data-share` 映射到 `baby-tracker/data` |
| 运行权限 | 使用 `baby_tracker` 专用用户和用户组，不请求 root 权限 |
| 离线安装 | 内置 Python wheelhouse 和前端依赖，不依赖 CDN |
| 系统要求 | fnOS `1.1.3100` 或更高版本 |

## 安装

### 使用 FPK

从[最新 Releases](https://github.com/XiGeMaX/Baby_tracker-fnos/releases/latest)下载 `baby-tracker.fpk`。如果自行构建，安装包会生成到以下位置：

```text
dist/baby-tracker.fpk
```

在飞牛应用中心选择“手动安装”，然后选择该 FPK。也可以在设备上执行：

```bash
appcenter-cli install-fpk dist/baby-tracker.fpk
```

### 安装向导

安装时需要填写：

- 服务绑定地址：NAS 本机网卡上的局域网 IPv4 地址。
- 监听端口：`1024-65535` 范围内的可用端口，默认值为 `8964`。

应用不会自动监听其他网卡，也不会将端口开放到公网。如需限制同一局域网内的其他设备访问，应由路由器、VLAN 或飞牛防火墙在网络层处理。

## 首次登录

1. 安装完成后从飞牛桌面打开 Baby Tracker。
2. 应用通过统一网关获取当前飞牛账号，并将其映射为唯一管理员。
3. 首次进入时必须设置 `8-128` 位管理密码。
4. 设置完成后进入业务页面。

直接使用 `http://BIND_IP:端口` 访问时，不会显示“使用飞牛账号登录”按钮。此时应使用当前飞牛用户名和管理密码登录。退出登录后，可以返回飞牛桌面重新进入，通过统一网关恢复应用会话。

如果忘记管理密码，从飞牛桌面重新打开应用，通过飞牛账号登录，在“管理 > 管理配置”中修改密码。

## 数据与备份

应用的主要持久化位置如下：

| 位置 | 用途 |
| --- | --- |
| `baby-tracker/data` | 飞牛 `data-share` 共享目录 |
| `${TRIM_PKGVAR}/data` | 指向共享目录的符号链接 |
| `${TRIM_PKGVAR}/venv` | 应用虚拟环境 |
| `${TRIM_PKGVAR}/app.log` | 应用日志 |
| `${TRIM_PKGETC}` | 密钥、端口、绑定地址和初始化标记等配置 |

最稳妥的备份方式是在应用管理页面导出 JSON。共享目录通常也可以通过以下路径访问：

```text
/var/apps/baby-tracker/share/data
```

如果直接备份 SQLite，请先停止应用，再复制 `baby.db` 及其 WAL 文件，避免遗漏尚未合并的数据。

当前工程未提供旧开发版本的数据迁移。如果曾安装过其他开发版本，建议先导出数据并卸载旧应用，再安装当前 FPK。

## 构建

构建环境要求：

- `bash`
- `git`
- `curl`
- `jq`
- Python 3.12
- 可访问 GitHub、PyPI 和飞牛 fnpack 下载地址

初始化源码并构建：

```bash
git clone --recurse-submodules https://github.com/XiGeMaX/Baby_tracker-fnos.git
cd Baby_tracker-fnos
./scripts/build.sh
```

如果已经克隆但没有拉取子模块，可以执行：

```bash
git submodule update --init --recursive
```

构建脚本会完成以下操作：

1. 使用 `upstream/` 中的 Baby Tracker 上游源码，必要时自动克隆。
2. 复制上游运行文件并生成 fnOS 启动入口。
3. 注入飞牛账号鉴权和首次密码设置逻辑。
4. 下载 x86_64 与 arm64 的 Python 3.12 wheelhouse。
5. 校验 Manifest、安装向导、JSON、生命周期脚本和应用目录。
6. 调用官方 `fnpack 1.2.3` 生成 `dist/baby-tracker.fpk`。

常用构建选项：

```bash
# 先更新 upstream 子模块
FPK_UPDATE_SOURCE=1 ./scripts/build.sh

# 使用现有 wheelhouse 离线重建
FPK_OFFLINE_WHEELS=1 ./scripts/build.sh

# 指定 fnpack 可执行文件
FNPACK_BIN=/path/to/fnpack ./scripts/build.sh
```

### 自动发布

发布标签必须与 `packaging/baby-tracker/manifest` 中的 `version` 一致。例如当前版本为 `1.6.2` 时：

```bash
git tag v1.6.2
git push origin v1.6.2
```

标签推送后，[release.yml](.github/workflows/release.yml) 会执行构建、安装包测试、SHA256 生成，并将 FPK 自动上传到 GitHub Releases。也可以在 Actions 页面手动运行 `Build and Release FPK` 工作流。

## 测试

```bash
./scripts/test.sh
```

测试会运行上游单元测试，并启动打包后的 Gunicorn/WSGI 应用，检查以下行为：

- 飞牛网关登录、退出和会话建立。
- 新安装数据库不包含默认本地管理员。
- 首次登录设置管理密码。
- `data-share` 数据目录映射。
- 局域网绑定地址和端口校验。
- 未登录页面重定向和 API `401`。
- TCP 端伪造 `X-Trim-*` 身份头会被拒绝。
- 管理页改密和服务配置同步。
- Home Assistant API Key 鉴权。
- PWA 图标、前端静态资源和网关前缀重写。

## 项目结构

```text
Baby_tracker-fnos/
├── .github/workflows/release.yml   # 标签自动构建并发布 FPK
├── upstream/                       # Baby Tracker 上游源码，Git submodule
├── packaging/
│   ├── baby-tracker/               # fnpack 应用包、Manifest、向导和生命周期脚本
│   └── build-assets/               # WSGI、依赖清单、图标和前端运行时
├── scripts/
│   ├── build.sh                    # 构建 FPK
│   ├── patch_source.py             # 注入飞牛鉴权和服务管理逻辑
│   ├── patch_frontend.py           # 适配网关前缀和前端资源
│   └── test.sh                     # 单元测试与安装包冒烟测试
├── tools/                          # fnpack 工具和辅助脚本
├── dist/                           # 构建产物
└── README.md
```

## 安全说明

- 飞牛网关身份只通过 `${TRIM_APPDEST}/app.sock` 传递和信任。
- 局域网 TCP 请求无法通过伪造 `X-Trim-Userid`、`X-Trim-Username` 或 `X-Trim-Isadmin` 获得身份。
- 应用不会监听 `0.0.0.0`、回环地址、公网地址或无效 IPv4 地址。
- 业务页面和业务 API 始终执行应用会话校验。
- 管理员接口会继续执行应用内管理员角色检查。
- `/api/ha/*` 必须携带管理员生成的有效 API Key。

## 上游项目

- 上游应用：[XiGeMaX/Baby_tracker](https://github.com/XiGeMaX/Baby_tracker)
- 上游许可证：[GNU GPL v3](https://github.com/XiGeMaX/Baby_tracker/blob/main/LICENSE)
- 本项目是第三方飞牛 fnOS 适配工程，不是飞牛官方项目。
