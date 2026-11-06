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
# VNC_PASSWORD 留空，网页桌面免密码进入。
docker-compose pull
docker-compose up -d
docker-compose ps
```

若镜像保持私有，每台新服务器只需执行一次 `docker login`。若已经在 GitHub
Packages 中将该镜像设置为 Public，则可跳过登录步骤。

## 3. 使用

- 网页界面：`http://服务器IP:6080/vnc.html?autoconnect=1&resize=remote&path=websockify`
- 默认不弹出 noVNC 密码和系统钥匙环解锁提示。免密码时应限制 6080 端口访问来源。
- HTTP/SOCKS5 代理：`服务器IP:7890`
- 登录 Fastlink、连接节点，设置 Mixed Port 为 `7890` 并开启 Allow LAN。
- 保持 TUN 关闭；无需 TUN 设备、管理员网络权限或透明代理规则。

## 4. 更新

```bash
docker-compose pull
docker-compose up -d
```

登录和订阅配置保存在 `fastlink-home` 数据卷，普通更新不会删除。独立钥匙环在
启动时自动解锁，旧钥匙环文件保持原样；首次切换可能需要重新登录一次，之后新凭据
可持久保存。自动生成的解锁密钥与钥匙环保存在同一数据卷，应限制该卷访问。

从旧版升级时，将现有 `.env` 中的 `VNC_PASSWORD` 改为空。包含启动脚本变更的新镜像
构建并发布后，再拉取并重新创建；仅修改本地配置不会更新已发布的镜像：

```bash
docker-compose pull
docker-compose up -d --force-recreate
```

## 5. 资源与日志

```bash
docker stats fastlink
docker-compose logs --tail=100 -f
```

默认 `1280×800`、共享内存 256 MB、内存上限 1 GB。如果 Fastlink 被 OOM killer
终止，把 `.env` 的 `FASTLINK_MEMORY_LIMIT` 改为 `1536m` 或 `2g`，然后执行
`docker-compose up -d`。
