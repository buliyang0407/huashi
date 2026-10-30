# 部署与数据边界

需要 Python 3.12+ 和 Pillow，也可以使用 Docker。没有 API 配置或个人素材也能启动空工作台；实际生成需要自行配置对应服务。

## 新部署

本地安装依赖后运行：

```sh
.venv/bin/python -m huashi.server --host 127.0.0.1 --port 8787 --data data
```

需要配置服务时，在自己的新部署目录根据 `.env.example` 创建 `.env`。Docker 用户先建立 `data`、`pose`、`promptscreation`、`inspiration/user-data` 目录，再准备自己的 `.env`，运行 `docker compose up -d --build`。

| 目录 | 内容 |
| --- | --- |
| `data/` | SQLite、任务、上传、结果、作品和备份，必须持久化 |
| `pose/` | 自有姿势和可选服装参考，运行时只读 |
| `promptscreation/` | 旧工坊素材及同名JSON描述，运行时只读 |
| `inspiration/` | 自有灵感归档，不随仓库分发 |
| `inspiration/user-data/` | 收藏及状态，需要持久化 |
| `material-index/` | 私人素材索引、gzip和浏览缩略图，构建后可选挂载 |

空安装缺少素材索引时返回空JSON/gzip，不在源目录自动生成文件。素材接入见 [MATERIALS.md](MATERIALS.md)。

## 服务配置

RunPod需要 API Key、Endpoint ID、独立HTTP代理，以及能执行相应工作流的远端Worker。真实值只存在部署环境。模型权重和LoRA不在仓库内，工作流中的文件名须与自己的Worker匹配。任务提交结果不确定时不要自动重发，以免重复计费。

旧提示词模型配置可留空；新工坊和素材袋不依赖提示词模型API。项目面向可信局域网，没有公网登录及多人权限系统。

## 更新已有部署

先保存当前代码、文件和配置，使用SQLite在线backup API或停写一致快照备份数据库。记录活动任务，在独立目录/镜像验证更新。只安装核对过的代码和新增资产；保留环境文件、原素材、作品、历史及收藏。不要拿本地空目录覆盖已有数据，也不要为了回退代码而恢复旧数据库。

GitHub更新不自动部署到任何NAS。仓库CI只做测试与临时镜像构建，不带部署密钥。
