# Fastlink 在 Debian Docker 中运行

这个安装包是 Flutter 桌面程序，不是原生 Web 服务。本配置使用 Xvfb、x11vnc
和 noVNC 将轻量图形界面显示在浏览器中，同时映射 Fastlink 的 HTTP/SOCKS5
代理端口。使用 **Fluxbox + tint2**，不含完整 Ubuntu/XFCE 桌面；底部图标栏
保留最小化窗口。Fastlink 最小化后，点击底部图标即可恢复。

## 启动

把整个目录（包括 `.deb`、`.env`、`Dockerfile`、`docker-compose.yml` 和
`docker/`）复制到 Debian Docker 主机，然后执行：

Dockerfile 使用 `fastlinkapp-linux-speed-*-amd64.deb` 通配符自动查找安装包。
更新版本时，用新 `.deb` 替换旧包，保持该前缀和 `amd64.deb` 后缀即可，
不需要修改 Dockerfile。目录中只能保留一个匹配的 `.deb` 文件。

```bash
docker-compose -f docker-compose.local.yml build
docker-compose -f docker-compose.local.yml up -d
docker-compose -f docker-compose.local.yml ps
```

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

```bash
# 查看运行状态和软件日志
docker-compose ps
docker-compose logs -f --tail=100

# 修改 .env 后重新创建
docker-compose up -d --force-recreate

# 替换新版 .deb，或修改 Dockerfile / 启动脚本后重新构建
docker-compose -f docker-compose.local.yml build --no-cache
docker-compose -f docker-compose.local.yml up -d --force-recreate
```

配置不包含 TUN 设备、`NET_ADMIN` 权限或透明代理规则。界面端口为 noVNC 服务，
7890 是 Fastlink 的代理端口，二者用途不同。

## GitHub Actions 云端构建与服务器拉取

仓库中的 `.github/workflows/build-image.yml` 在 GitHub 的 amd64 主机上构建并发布
`ghcr.io/xins134/fastlink-docker:latest`。`.deb` 只在 Actions 构建环境中使用，
服务器无需存放安装包或本地构建。

服务器使用 [README.deploy.md](README.deploy.md) 的步骤登录 GHCR、拉取镜像并启动。
`.env` 已被 `.gitignore` 排除，不会把本机配置提交到 GitHub。
