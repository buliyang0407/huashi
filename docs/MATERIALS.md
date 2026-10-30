# 自有素材索引与缩略图

仓库不携带人物、姿势、服装图库和私人索引。请在自己的新部署目录操作，先备份已有资料；不将这些例子直接套到使用中的数据库上。

## 目录与构建

素材来自 `pose/`、`promptscreation/` 和 `data/faces/`。可选服装根为 `pose/.costume-library/`；存在 `.metadata/catalog.json` 时保留来源参考词及稳定ID，没有该文件也能读取图片名称。工具只读原图，不下载第三方图库。

先生成普通索引：

```sh
mkdir -p material-build
.venv/bin/python scripts/build_portrait_bag_catalog.py --app-root . > material-build/portrait-materials.json
```

核对后，将索引安装到自己部署的 `web/portrait-materials.json`，再生成缩略图包：

```sh
.venv/bin/python scripts/build_portrait_bag_thumbnails.py --app-root . > material-build/thumbnails.tar
```

把自己生成的tar先解到空暂存目录，核对报告和文件名后，再安装到部署的 `web/`。包内只有内容哈希命名的 `portrait-thumbs/*.webp`、带thumbnail字段的索引及生成报告；不含原图。不要解包来源不明的tar或覆盖原图目录。用Python的 `gzip.compress()` 从最终JSON同步生成 `web/portrait-materials.json.gz`。

浏览副本最长边480像素，大图和RunPod输入仍是原图。更新素材时，普通JSON、gzip和缩略图须配套更新，同时更新前端索引缓存版本。不能只更新JSON而保留旧gzip。

## Docker持久化

基础Compose可以直接启动空工作台。需要自己的索引在容器重建后保留时，先准备以下宿主路径，再启用可选覆盖文件：

- `material-index/portrait-materials.json`
- `material-index/portrait-materials.json.gz`
- `material-index/portrait-thumbs/`

```sh
docker compose -f docker-compose.yml -f compose.materials.yml up -d --build
```

文件不存在时不要启用挂载，否则Docker可能创建同名目录。构建脚本不必进入镜像，可以从宿主通过stdin执行，例如：

```sh
docker compose exec -T huashi python - < scripts/build_portrait_bag_catalog.py > material-build/portrait-materials.json
```

先核对普通索引并安装到挂载目录、生成匹配gzip，再通过stdin运行缩略图脚本。它读取容器的 `/app/web/portrait-materials.json`，所以运行前确保索引挂载已生效。输出tar在宿主暂存核验后，更新挂载目录中的派生文件和gzip。整个过程不得覆盖原图、作品或业务数据库。
