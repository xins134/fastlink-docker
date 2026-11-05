# Debian 服务器部署（无需构建）

服务器只需要 `docker-compose.yml`、`.env` 和 Docker；无需上传 `.deb`，也无需
运行 `docker-compose build`。Fastlink 已通过 GitHub Actions 安装到 amd64 镜像中。

## 1. 登录私有镜像仓库

使用具有该仓库只读权限的 GitHub 个人访问令牌：

```bash
printf '%s' '你的GitHub只读Token' | docker login ghcr.io -u 你的GitHub用户名 --password-stdin
```

不要把 Token 直接写在命令参数或 `.env` 中。

## 2. 配置与启动

```bash
cp .env.example .env
# 修改 .env 中的 VNC_PASSWORD；它必须恰好为 8 个可打印字符。
docker-compose pull
docker-compose up -d
docker-compose ps
```

若镜像保持私有，每台新服务器只需执行一次 `docker login`。若已经在 GitHub
Packages 中将该镜像设置为 Public，则可跳过登录步骤。

## 3. 使用

- 网页界面：`http://服务器IP:6080/vnc.html?autoconnect=1&resize=remote&path=websockify`
- HTTP/SOCKS5 代理：`服务器IP:7890`
- 登录 Fastlink、连接节点，设置 Mixed Port 为 `7890` 并开启 Allow LAN。
- 保持 TUN 关闭；无需 TUN 设备、管理员网络权限或透明代理规则。

## 4. 更新

```bash
docker-compose pull
docker-compose up -d
```

登录和订阅配置保存在 `fastlink-home` 数据卷，普通更新不会删除。由于未启动
GNOME Keyring，某些登录凭据可能无法持久保存。

## 5. 资源与日志

```bash
docker stats fastlink
docker-compose logs --tail=100 -f
```

默认 `1280×800`、共享内存 256 MB、内存上限 1 GB。如果 Fastlink 被 OOM killer
终止，把 `.env` 的 `FASTLINK_MEMORY_LIMIT` 改为 `1536m` 或 `2g`，然后执行
`docker-compose up -d`。
