# Fastlink 在 Debian Docker 中运行

这个安装包是 Flutter 桌面程序，不是原生 Web 服务。本配置使用 Xvfb、x11vnc
和 noVNC 将轻量图形界面显示在浏览器中，同时映射 Fastlink 的 HTTP/SOCKS5
代理端口。使用 **Fluxbox + tint2**，不含完整 Ubuntu/XFCE 桌面；底部图标栏
保留最小化窗口。Fastlink 最小化后，点击底部图标即可恢复。

## 启动

服务器直接拉取镜像的步骤见 [README.deploy.md](README.deploy.md)。
容器每次启动都会检查宿主机 `~/Download` 中的 Fastlink deb 包：版本相同就跳过，
版本不同就安装该包，支持升级和降级，无需为每个软件版本重新构建镜像。
这里使用的是 **Download（单数）**；可通过 `.env` 中的 `FASTLINK_DOWNLOAD_DIR`
指定其他绝对路径，例如 `/home/user/Downloads`。

需要本地构建时，把本目录复制到 Debian Docker 主机，执行：

```bash
cp .env.example .env
mkdir -p "$HOME/Download"
cp fastlinkapp-linux-speed-*-amd64.deb "$HOME/Download/"
docker-compose -f docker-compose.local.yml build
docker-compose -f docker-compose.local.yml up -d
docker-compose -f docker-compose.local.yml ps
```

Dockerfile 仍使用仓库根目录中唯一的 `fastlinkapp-linux-speed-*-amd64.deb`
安装镜像的初始版本；后续软件更新只需替换 `~/Download` 的目标包并重启容器。

如果系统使用 Docker Compose v2 插件，也可以把命令换成 `docker compose`。

**界面地址：** `http://服务器IP:6080/vnc.html?autoconnect=1&resize=remote&path=websockify`

默认免密码进入网页桌面，`.env` 中的 `VNC_PASSWORD` 留空即可。需要恢复连接密码时，
将它设为 **8 个可打印字符**，再重新创建容器。免密码时，应通过防火墙限制
6080 端口的访问来源，或将 `FASTLINK_BIND_ADDRESS` 设为 `127.0.0.1`。

Fastlink 使用独立钥匙环，启动时自动解锁，不再要求手动输入系统钥匙环密码。

## 配置 HTTP 代理

1. 打开上述页面，在 Fastlink 中登录账号、导入订阅并连接可用节点。
2. 在软件的代理设置中，将 **Mixed Port（混合端口）** 设置为 **7890**。
3. 开启 **Allow LAN（允许局域网设备使用代理）**，使代理监听 `0.0.0.0`。
4. 保持 **TUN 模式关闭**。系统代理可以关闭，其他设备直接填写代理地址即可。

**HTTP 代理地址：** `服务器IP:7890`

测试：

```bash
curl -x http://127.0.0.1:7890 https://example.com
```

同一端口也支持 SOCKS5：

```bash
curl --socks5-hostname 127.0.0.1:7890 https://example.com
```

> 仅映射端口不会自动启动代理。必须在软件中连接节点、设置 mixed-port=7890
> 并开启 Allow LAN。7890 端口没有额外认证，不应直接暴露到不可信公网；
> 只需要本机使用时，将 `.env` 中两个 `BIND_ADDRESS` 都改成 `127.0.0.1`。

## 数据与维护

账号、订阅和设置保存在 Compose 命名卷 `fastlink-home` 中，普通重启和重建容器
不会清除。独立钥匙环及自动生成的解锁密钥保存在
`/home/app/.local/share/fastlink-keyring`，密钥文件权限为 `0600`，不会输出到日志。
旧钥匙环文件保持原样；首次切换到此版本可能需要重新登录一次，之后新凭据可持久保存。
解锁密钥与钥匙环位于同一数据卷，能读取该卷的人也能解锁凭据，因此应限制数据卷访问。
默认分辨率为 1280×800、共享内存 256 MB、内存上限 1 GB。内存下限只是预留配置，不会
预先占用等量内存。可以在 `.env` 调整 `SCREEN_WIDTH`、`SCREEN_HEIGHT` 和
`FASTLINK_MEMORY_LIMIT`；若应用出现 OOM，可将上限提高到 `1536m` 或 `2g`。

安装包的 Linux 应用 ID 为 `com.flapp.clients.apex`。结合包内路径相关符号和
Flutter Linux 插件的默认规则，推定应用数据在
`/home/app/.local/share/com.flapp.clients.apex/`，偏好文件为 `shared_preferences.json`；
旧版兼容路径可能为 `/home/app/.local/share/apex-client/`。包内还存在 `profiles` 和
`running_config.yaml` 字符串，其运行时位置需启动 Linux 应用后确认。
这些路径来自静态分析，当前环境未验证实际生成文件。

确定的独立钥匙环路径是 `/home/app/.local/share/fastlink-keyring/`。
`/home/app/.config/` 存放 XDG/桌面配置；默认持久化整个 `/home/app`，覆盖上述路径。
若希望直接在宿主机访问这些文件，可以使用 `docker-compose.bind.yml`，默认映射
`~/.local/share/fastlink-docker` 到 `/home/app`；已有数据的迁移步骤见
[部署文档的数据映射部分](README.deploy.md#5-配置路径与宿主机数据映射)。

### 软件版本同步

- `~/Download` 只保留一个 Fastlink deb；其他软件的有效 deb 会被忽略。
- 根据 deb 的 `Package`、`Version`、`Architecture` 元数据判断，文件名可以修改。
  当前包的 `Version` 为 `7.3.1`，文件名中的时间戳不参与版本比较。
- 目录为空或没有 Fastlink deb 时，使用当前安装版本。
- 多个 Fastlink 包、损坏的 deb 或不匹配的架构会使启动失败，日志会说明原因。
- 完成下载后再重启。更新时先移走旧 Fastlink 包，再放入目标包；推荐先以非 `.deb`
  后缀写入目录，完成后再重命名，避免启动时读到未完成的下载。
- 依赖已满足时直接安装本地包；若安装失败，会刷新 APT 元数据后重试，新增依赖可能
  需要联网。安装失败或安装后的版本验证失败时，不会启动图形界面。
- `~/Download` 以只读方式映射为 `/home/app/Download`。重建容器后仍会自动安装目标版本。

```bash
# 查看运行状态和软件日志
docker-compose ps
docker-compose logs -f --tail=100

# 修改 .env 后重新创建
docker-compose up -d --force-recreate

# ~/Download 中只保留目标 Fastlink deb 后，重启以同步版本
docker-compose restart fastlink

# 修改 Dockerfile / 启动脚本后才需要重新构建本地镜像
docker-compose -f docker-compose.local.yml build --no-cache
docker-compose -f docker-compose.local.yml up -d --force-recreate
```

配置不包含 TUN 设备、`NET_ADMIN` 权限或透明代理规则。界面端口为 noVNC 服务，
7890 是 Fastlink 的代理端口，二者用途不同。

## GitHub Actions 云端构建与服务器拉取

仓库中的 `.github/workflows/build-image.yml` 在 GitHub 的 amd64 主机上构建并发布
`ghcr.io/xins134/fastlink-docker:latest`。镜像自带一个初始版本；服务器可以通过
`~/Download` 中的 deb 选择实际运行版本，无需本地构建。

首次使用新的启动检查逻辑，需要构建并发布包含 `docker/sync-package.sh` 的镜像，
在服务器拉取并重建一次。之后只更新软件包时，替换 deb 并重启即可。
已移除原来的 `pull_policy: always` 配置。软件更新使用 `restart`，无需拉取镜像；
更新容器环境时仍可以显式执行 `docker-compose pull`。

服务器使用 [README.deploy.md](README.deploy.md) 的步骤登录 GHCR、拉取镜像并启动。
`.env` 已被 `.gitignore` 排除，不会把本机配置提交到 GitHub。
