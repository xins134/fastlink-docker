# Debian 服务器部署（无需构建）

服务器需要 `docker-compose.yml`、`.env.example` 和 Docker。镜像自带 Fastlink 的
初始版本；宿主机 `~/Downloads` 映射到容器后，每次启动都会按其中的 deb 同步软件
版本，无需运行 `docker-compose build`。

## 1. 登录私有镜像仓库

使用具有该仓库只读权限的 GitHub 个人访问令牌：

```bash
printf '%s' '你的GitHub只读Token' | docker login ghcr.io -u 你的GitHub用户名 --password-stdin
```

不要把 Token 直接写在命令参数或 `.env` 中。

## 2. 配置与启动

```bash
cp .env.example .env
mkdir -p "$HOME/Downloads"
# 将要运行的 Fastlink deb 放到 ~/Downloads，只保留一个 Fastlink 包。
# VNC_PASSWORD 留空，网页桌面免密码进入。
docker-compose pull
docker-compose up -d
docker-compose ps
```

若镜像保持私有，每台新服务器只需执行一次 `docker login`。若已经在 GitHub
Packages 中将该镜像设置为 Public，则可跳过登录步骤。

默认目录是 `~/Downloads`，以只读方式映射到 `/home/app/Downloads`。
如果使用其他目录，在 `.env` 中设置
`FASTLINK_DOWNLOAD_DIR=/你的绝对路径`，创建该目录后执行 `docker-compose up -d`。
没有 Fastlink deb 时保留镜像自带的版本。

## 3. 使用

- 网页界面：`http://服务器IP:6080/vnc.html?autoconnect=1&resize=remote&path=websockify`
- 默认不弹出 noVNC 密码和系统钥匙环解锁提示。免密码时应限制 6080 端口访问来源。
- HTTP/SOCKS5 代理：`服务器IP:7890`
- 登录 Fastlink、连接节点，设置 Mixed Port 为 `7890` 并开启 Allow LAN。
- 保持 TUN 关闭；无需 TUN 设备、管理员网络权限或透明代理规则。

每次容器启动时，桌面服务启动后等待约 10 秒，向 Fastlink 发送一次标准 X11 窗口关闭请求，等同点击
标题栏右上角关闭按钮；主窗口出现较慢时最多额外等待 30 秒。软件须支持关闭窗口
后继续后台运行，之后可从底部 Fastlink 托盘菜单重新打开。自动关闭只执行一次，
手动重新打开的窗口不会再次关闭。启动前的软件同步和桌面初始化会耗时，不能保证
宿主机开机后恰好 10 秒关闭。

如果关闭后底部没有图标，且日志出现 `tint2: another systray is running`，是旧版
Fluxbox 的隐藏工具栏占用了系统托盘。此版本使用 `-no-toolbar` 完全关闭该工具栏，
将托盘交给 tint2。更新镜像并重新创建容器后生效，账号和订阅仍保留。

首次登录或配置时，在 `.env` 中设置 `FASTLINK_AUTO_CLOSE_DELAY=0`，执行
`docker-compose up -d --force-recreate` 禁用自动关闭。完成后改回 `10` 并再次执行
该命令即可恢复；修改环境变量后仅运行 `restart` 不会应用新值。

## 4. 软件更新、降级与容器环境更新

软件版本由 `~/Downloads` 中唯一的 Fastlink deb 决定。先将旧 Fastlink deb 移出该目录，
再放入已下载完成的目标 deb，执行：

```bash
docker-compose restart fastlink
docker-compose logs --tail=100 fastlink
```

启动脚本读取 deb 元数据中的 `Package=com.flapp.clients.apex`、`Version` 和
`Architecture`，与 `dpkg-query` 的安装状态比较。同版本且已正常安装时跳过；
版本不同时安装目录中的版本，支持降级。文件名及其时间戳不影响判断。
其他有效软件包会被忽略；多个 Fastlink 包、损坏的 deb 或错误架构会阻止启动。
依赖已满足时无需联网；若安装失败，会刷新 APT 元数据并重试，新增依赖可能需要联网。

账号、订阅和设置保存在 `fastlink-home` 数据卷，替换 deb、普通重启和重建容器
都会保留。软件安装在容器内；重建后启动检查会重新应用 `~/Downloads` 的目标版本。

更新 Dockerfile 或启动脚本时，需要先构建并发布新镜像，再执行：

```bash
docker-compose pull
docker-compose up -d --force-recreate
```

首次采用 deb 启动同步或延迟关闭窗口功能也需要上述步骤。仅修改服务器的 Compose
文件或重启旧镜像，不能加入新的启动脚本。已移除原来的 `pull_policy: always`
配置；后续只更新软件包时执行 `restart` 即可，不涉及镜像拉取。

## 5. 配置路径与宿主机数据映射

默认已持久化整个 `/home/app`，无需额外映射即可保留登录、订阅和配置。路径说明：

| 容器路径 | 用途与确认情况 |
| --- | --- |
| `/home/app/.local/share/com.flapp.clients.apex/` | 根据安装包 ID 和 Flutter Linux 插件规则推定的应用数据根；默认偏好文件为 `shared_preferences.json`，尚未运行 Linux 应用确认。 |
| `/home/app/.local/share/apex-client/` | Flutter 插件可能继续使用的旧版兼容数据根。 |
| `/home/app/.local/share/fastlink-keyring/` | 启动脚本确定的独立钥匙环目录，含 `keyrings/` 与 `unlock.password`。 |
| `/home/app/.config/` | XDG/桌面配置目录。 |

包内还含 `profiles`、`running_config.yaml` 字符串；它们的运行时位置未确认。
可在软件运行后查看实际文件：

```bash
docker-compose exec fastlink find /home/app/.local/share /home/app/.config -maxdepth 4 -type f
```

如果希望配置直接出现在宿主机目录，把 `docker-compose.bind.yml` 一并复制到服务器。
它将 `~/.local/share/fastlink-docker` 映射到 `/home/app`，同时保留 `~/Downloads` 的独立
只读映射。在 `.env` 中设置 `FASTLINK_DATA_DIR=/你的绝对路径` 可自定义数据目录。

首次部署、没有旧数据时：

```bash
mkdir -p "$HOME/.local/share/fastlink-docker"
docker-compose -f docker-compose.yml -f docker-compose.bind.yml up -d
```

已有 `fastlink-home` 数据时，先停止应用并复制数据，再启用映射，避免进入一个空的
配置目录。以下示例使用默认数据目录；如果设置了 `FASTLINK_DATA_DIR`，将命令中的
目录换成相同路径。目标目录应为空：

```bash
docker-compose stop fastlink
mkdir -p "$HOME/.local/share/fastlink-docker"
FASTLINK_MIGRATION_IMAGE=$(docker inspect --format '{{.Image}}' fastlink)
docker run --rm --volumes-from fastlink:ro --entrypoint /bin/tar "$FASTLINK_MIGRATION_IMAGE" \
  --exclude=./Downloads -C /home/app -cf - . \
  | tar -xf - -C "$HOME/.local/share/fastlink-docker"
sudo chown -R 1000:1000 "$HOME/.local/share/fastlink-docker"
sudo chmod 700 "$HOME/.local/share/fastlink-docker"
docker-compose -f docker-compose.yml -f docker-compose.bind.yml up -d --force-recreate
```

迁移命令排除了单独映射的 `Downloads`，避免重复复制安装包及其他下载文件。
之后使用同一组 `-f` 参数运行 `up`、`restart`、`logs` 等命令；本地构建模式将第一个
文件换成 `docker-compose.local.yml`。保留旧命名卷作为备份，确认迁移完成后自行处理。
独立钥匙环启动时自动解锁，解锁密钥与钥匙环必须一起持久化和迁移。
能读取这些数据的人也能解锁凭据，因此应限制数据目录访问。

## 6. 资源与日志

```bash
docker stats fastlink
docker-compose logs --tail=100 -f
```

默认 `1280×800`、共享内存 256 MB、内存上限 1 GB。如果 Fastlink 被 OOM killer
终止，把 `.env` 的 `FASTLINK_MEMORY_LIMIT` 改为 `1536m` 或 `2g`，然后执行
`docker-compose up -d`。

### 启动时提示找不到壁纸工具

如果出现 `fbsetbg: I can't find an app to set the wallpaper with`，说明镜像缺少
Fluxbox 默认背景设置所调用的壁纸工具。运行 Fastlink 无需壁纸功能，本配置通过
`background: unset` 完全禁用背景设置，不安装 `feh` 或 Eterm。

启动时从镜像模板生成可写的 Fluxbox 配置，并明确加载它，避免已有数据卷中的旧
桌面配置再次调用壁纸工具。Xvfb 提供黑色背景并关闭屏幕保护，无需额外背景程序。
VNC 连接只使用现有的 x11vnc，已移除重复的 TigerVNC 服务端和工具包。

服务器拉取模式：先构建并发布包含修复的新镜像，再执行：

```bash
docker-compose pull
docker-compose up -d --force-recreate
```

本地构建模式：

```bash
docker-compose -f docker-compose.local.yml build
docker-compose -f docker-compose.local.yml up -d --force-recreate
```

仅重启旧镜像不会应用此修复。上述更新会保留已有账号、订阅和设置，无需删除数据卷。
