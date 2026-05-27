# Docker 部署

## Docker Compose 快速启动

```bash
# 启动网关服务（常驻）
docker-compose up miqi-gateway -d

# CLI 模式
docker-compose run miqi-cli
```

## 服务说明

### miqi-gateway

常驻网关服务，对外提供 API：

```yaml
miqi-gateway:
  build: .
  ports:
    - "127.0.0.1:18790:18790"
  volumes:
    - ~/.miqi:/home/miqi/.miqi
  deploy:
    resources:
      limits:
        cpus: "1"
        memory: 1G
  entrypoint: ["miqi", "gateway", "start"]
```

### miqi-cli

按需 CLI 模式：

```yaml
miqi-cli:
  build: .
  profiles: ["cli"]
  stdin_open: true
  tty: true
  volumes:
    - ~/.miqi:/home/miqi/.miqi
```

## Docker 镜像

### 基础镜像

```
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
```

### 安全配置

- 非 root 用户 `miqi` (UID 1000)
- 工作目录 `/app`
- 配置目录 `~/.miqi`
- 资源限制 1 CPU / 1 GB 内存

### 构建

```bash
docker build -t miqi:latest .
```

## 卷挂载

| 容器路径 | 主机路径 | 说明 |
|----------|----------|------|
| `/home/miqi/.miqi` | `~/.miqi` | 配置文件和数据 |
| `/app` | (构建时复制) | 应用代码 |

## 网络

- Gateway 仅绑定 `127.0.0.1`，不对外暴露
- 所有 MCP 子进程在容器内运行，共享容器网络

## 资源限制

| 服务 | CPU | 内存 |
|------|-----|------|
| miqi-gateway | 1 核 | 1 GB |
| miqi-cli | 无限制 | 无限制 |
