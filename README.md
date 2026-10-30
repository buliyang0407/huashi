# 画室 Huashi

运行在本地电脑或个人 NAS 上的视觉创作工作台。当前整理版本：2026-10-30。

画室分为三个空间：

- **创作间**：选择 RunningHub / RunPod 画布，上传参考图，填写提示词，查看队列、历史及结果。
- **灵感屋**：浏览自有图像与动画资料、管理提示词，以及使用独立的人像工坊。
- **陈列室**：整理作品，浏览人物、服装和姿势参考，查看原图并作为创作输入。

人像工坊支持分类、目录筛选、搜索、分页和参考词复制。图片可装入平铺的“素材袋”，在每个上传口自行选择一张。工坊、素材袋、陈列室及选图窗口使用缩略图；大图详情和任务输入使用原图。素材袋保存在当前浏览器，不跨设备同步。浏览素材和复制参考词不依赖大模型 API。

本仓库保存应用代码、测试、工作流及构建工具。个人素材、作品、任务数据库、收藏、密钥、生成索引和缩略图不随仓库分发。没有素材或 API 配置也能启动空工作台；实际生成需要自行配置对应服务。项目面向可信的个人局域网，没有登录及多人权限体系。

## 本地启动

需要 Python 3.12 及以上版本。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m huashi.server --host 127.0.0.1 --port 8787 --data data
```

打开 <http://127.0.0.1:8787/>。启动会在自己的 `data/` 下创建数据库和内置图标，不写入个人素材目录。macOS 用户也可以在激活虚拟环境后使用启动脚本。

需要生成服务时，在自己的部署目录从 `.env.example` 创建 `.env`，手动配置必要变量；不需要的服务保持空白。请勿复制他人的密钥或提交真实配置。

## Docker

```sh
mkdir -p data pose promptscreation inspiration/user-data
docker build -t huashi:local .
```

在新部署目录准备自己的 `.env` 后，运行 `docker compose up -d --build`，访问宿主机的 8787 端口。Compose 将运行数据和素材保存在宿主目录，素材挂载为只读。代码更新和数据库迁移前先做好一致备份，尤其不要拿空目录覆盖现有部署的数据。

详细说明见 [部署与数据边界](docs/DEPLOYMENT.md)；个人素材索引及缩略图的构建见 [素材构建](docs/MATERIALS.md)。

## 配置

| 配置 | 用途 |
| --- | --- |
| `RUNNINGHUB_API_KEY` | RunningHub 任务服务，可留空 |
| `RUNPOD_API_KEY`、`RUNPOD_QWEN_ENDPOINT_ID` | RunPod Serverless 任务，可留空 |
| `RUNPOD_PROXY_URL` | 当前 RunPod 客户端要求的独立 HTTP 代理，不改变其他服务的网络配置 |
| `HUASHI_POSE_DIR` | 姿势及服装参考目录；默认 `pose` |
| `HUASHI_FACE_LIBRARY_DIR` | 人物参考目录；默认 `data/faces` |
| `HUASHI_PORTRAIT_MATERIAL_DIR` | 旧人像工坊素材；默认 `promptscreation` |

旧提示词模型集成代码保留兼容性，其配置为选填。新的工坊和素材袋不调用这些模型。RunPod 的模型权重、远端 Worker、网络卷和商业服务不包含在仓库中，生成费用由使用者自行控制。

## 验证

```sh
.venv/bin/python -m unittest discover -s tests -v
node --test tests/*.cjs scripts/test_*.cjs
```

在 macOS 上，部分文件边界测试需要使用解析后的临时目录，可运行 `TMPDIR=/private/tmp .venv/bin/python -m unittest discover -s tests -v`。测试使用临时目录和模拟客户端，不需要真实密钥或付费生成。

公开测试不包含私人素材包的历史审稿检查及 NAS 特定数量快照；改以合成图片验证索引、缩略图和原图保全。发布验证详情见 [版本记录](CHANGELOG.md)。

## 资源与维护

本仓库不提供第三方素材图库或模型权重。接入自有素材时应保留来源及适用条款，见 [第三方资源说明](THIRD_PARTY_NOTICES.md)。目前未新增或变更项目许可证。

更新经过分支和 Pull Request 审阅。GitHub 代码更新不自动修改任何 NAS 部署。
