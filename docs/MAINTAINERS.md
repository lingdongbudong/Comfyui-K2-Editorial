# 维护者指南

给要改这个插件的人（包括三个月后的作者本人）。**动代码前先读完「红线」那一节**，
里面每一条都是踩过并付出过代价的。

- [红线](#红线)
- [目录结构](#目录结构)
- [数据链路](#数据链路)
- [HTTP 路由](#http-路由)
- [CLI](#cli)
- [测试基线](#测试基线)
- [发版流程](#发版流程)

## 红线

### 1. 禁止 `raise SystemExit`

```python
raise AssembleError(f"未知种子: {seed_id}")   # ✅ ValueError 子类
raise SystemExit(f"未知种子: {seed_id}")      # ❌ 会让整个服务失去响应
```

`SystemExit` 继承 `BaseException`，节点的 `except Exception` 和 ComfyUI `execution.py`
的 `except Exception` 都接不住。实测后果不是「单个请求 500」，而是
**8188 端口仍然 LISTENING、python 进程还在，但整个 HTTP 服务彻底不响应** —— 只能重启。

CLI 自己兜底（`assembler.main()` 里 `except AssembleError`），不影响节点与路由。

### 2. 新增控件必须加在 `INPUT_TYPES["optional"]` 末尾

`LiteGraph` 按控件创建顺序把值写进 `widgets_values`。插到中间或放进 `required`，
老工作流的下标会整体错位 —— 表现是「Required input is missing」或读到的值张冠李戴，
整张输出丢掉。测试第 13 项专守这条（断言三个随机池仍在末尾）。

新增控件还要同步三处：`generate()` 的签名、`IS_CHANGED()` 的返回元组、前端 `HIDDEN` 列表。

### 3. 缓存返回的对象按只读对待

数据层有三个指纹缓存：`assembler._LOAD_CACHE`、`anima_bridge._INDEX_CACHE` /
`_CACHE`、`k2ed_node._JSON_CACHE`。拿到的东西**不要原地改**。

之前 `/manifest` handler 直接 `man["aspects"] = ...`，加缓存后就会把运行期字段写进缓存对象。
现在改成 `man = dict(_load_json(...))` 拷一层。

同类坑还有 `merge_motif_aspect()`：把用户覆盖的画幅合进 manifest 时，命中的母题
必须 `dict(m, aspect=ov[id])` **新建**。直接 `m["aspect"] = ...` 会把覆盖值永久写进缓存，
之后用户删掉覆盖也回不去（测试第 12 项守这条）。

缓存键必须包含**路径**（只放 mtime/size，换数据源时会误命中），指纹用 `st_mtime_ns`
（浮点 `getmtime` 同秒内改两次会漏）。

### 4. 前端 CSS 在模板字符串里，注释别写反引号

`const CSS = \`...\`` 是模板字符串。在注释里写一个反引号会截断字符串，
`node --check` 报 `Unexpected identifier`，但错误位置指得很偏。

### 5. `IS_CHANGED` 与 `generate` 必须同参数

固定种子模式下，`IS_CHANGED` 返回的元组决定要不要重跑。新增输入没加进去，
换值不会重跑（看起来像「改了没生效」）。

### 6. 原子写只走 `_write_json()`

收藏 / 勾选池 / 服装锁定 / 场景画幅覆盖四处用户态数据必须用 `_write_json()`（mkstemp + fsync + `os.replace`）。
直接 `open(path, "w")` 写到一半被打断，会留下半截 JSON，下次读取静默回落成空、用户数据全丢。

## 目录结构

```
Comfyui-K2-Editorial/
├── __init__.py              入口：NODE_CLASS_MAPPINGS / WEB_DIRECTORY / register_routes / __version__
├── k2ed_node.py             节点本体：INPUT_TYPES、generate、全部 HTTP 路由、数据缓存与原子写
├── assembler.py             装配器：母题 → 长文（替换位、validate、CLI）。**不依赖 ComfyUI**
├── anima_bridge.py          桥接 Anima-Wardrobe：角色库 / 服装库 / 立绘路径（依赖 folder_paths）
├── js/k2ed_panel.js         设置面板（约 1900 行，单文件）：三页 + 右栏 + 摘要绘制
├── presets/
│   ├── seeds_motifs.json    原始 32 条母题
│   ├── seeds_extra.json     手工新增母题（当前 521 条）
│   ├── manifest.json        面板数据层（母题中文名 / 缩略图 / 标签 / 词数）
│   ├── characters.json      2 位手写角色
│   ├── costumes.json        8 套通用版型 + 角色推荐顺序
│   ├── motif_*.json / title_*.json   构建输入（运行时不读）
│   ├── user_motif_aspect.json  本机生成：场景默认画幅覆盖（不进仓库）
│   └── anima/               Anima 数据快照（角色 2432 / 服装库 98 套 SFW）
├── thumbs/
│   ├── anima/               角色立绘 2432 张（22 MB）
│   └── motifs/              母题预览 553 张（14 MB）
├── workflows/               3 个参考工作流
├── tools/make_sfw_bundle.py 服装库 SFW 精简脚本
├── tests/run_all.py         17 项回归测试
└── docs/                    本文档
```

`assembler.py` 刻意不 import ComfyUI / `folder_paths` —— 这样它能当独立 CLI 用
（`python assembler.py --list`），也方便在无 ComfyUI 环境跑测试。

## 数据链路

### 母题从「加一条」到「面板能用」

```
① 写母题正文
   → presets/seeds_extra.json 的 seeds[]（id / raw / title / character / words）
② 生成或出入图，得到缩略图
   → thumbs/motifs/<id>.webp
③ 重建面板数据（构建脚本在开发机上，不在本仓库）
   → presets/manifest.json 的 motifs[]（zh / title_zh / aspect / ratio / tags / thumb / thumb_v）
④ 重启 ComfyUI
   → 母题 combo 与 /k2ed/manifest 同时更新
```

⚠ 第 ③ 步的构建脚本（`build_manifest.py`）读 `presets/motif_names_zh.json`、
`motif_tags.json`、`motif_aspects.json`、`motif_added.json`、`motif_genres.json`、
`title_glossary.json`、`title_translations.json`。
这 7 份是**输入**，别删（运行时一份都不读，删了只影响重建 manifest）。

`manifest.branch` 必须只有 `scene` / `poster` / `short` 三类（前端按这三类筛选）。
`seeds.branch` 可以写来源标记（如 `portrait-pose`），构建时会被归一。

### 装配路径

```
generate(角色, 母题, 画幅, 服装, ...)
  ├─ 随机池抽取（若开启）→ 覆盖 角色 / 母题
  ├─ resolve_char(角色)             手写 characters.json 优先，否则 anima_bridge.char_entry()
  ├─ B.outfit_tags(kind, id)        单品标签
  ├─ A.assemble(...)                母题整块 + 三处替换（画幅 / 角色身份 / 服装）
  │    ├─ set_aspect / set_character / set_character_poster / set_character_short
  │    └─ remove_display_text / set_display_text
  ├─ A.validate(text, char, branch, orig_char)   自检
  └─ 写回 PNG 元数据（prompt[str(unique_id)] 与 extra_pnginfo）
```

⚠ 元数据**绝不能往 `prompt` 顶层加键**：`execution.py` 结束后会遍历顶层键当节点，
对每个键取 `["class_type"]`，遇到字符串就 `TypeError`，worker 线程死掉、队列永远不结束。
只能挂在「本节点字典内部」与 `extra_pnginfo`。

## HTTP 路由

前缀 `/k2ed`，全部在 `k2ed_node.register_routes()`。

| 方法 | 路径 | 参数 | 返回 |
| --- | --- | --- | --- |
| GET | `/manifest` | — | 母题 + 版型 + 标签 + 数据源状态（约 340 KB） |
| GET | `/chars` | `q` `work` `offset` `limit`(≤200) | `{total, items, works, fav, anima}` |
| GET | `/char` | `id` | 单个角色 |
| GET | `/outfits` | `char` | `{character, library, categories}` |
| GET/POST | `/favs` | POST `{kind, id, on}` | 四个收藏桶 |
| GET/POST | `/pick` | POST `{add?, remove?, set?, clear?}` | 勾选池 id 列表 |
| GET/POST | `/charoutfit` | POST `{char, id}` | 角色服装锁定表 |
| GET/POST | `/motif/aspect` | POST `{id, aspect}` | 场景默认画幅覆盖（`portrait` / `landscape` / `square`；`both` = 删覆盖回推荐值） |
| GET | `/build` | `motif` `char` `aspect` `costume` `item` `display` `notext` `mode` | `{ok, text, log, words, paras, pct, issues}` |
| GET | `/thumb/{path}` | — | `image/webp`，24h 缓存 |

`/thumb` 用 `realpath + commonpath` 判越界（字符串前缀挡不住软链接）。
`{path}` 要带 manifest 里 `thumb` 字段的原值（含 `thumbs/` 前缀）。

## CLI

```bash
python assembler.py --list                    # 列全部母题（id / 词数 / 标题 / 角色）
python assembler.py --list-costumes           # 列板块型
python assembler.py --seed "GRAIN SANCTUM" --char miku --aspect 16:9 --out out.txt
```

`assembler.py` 不依赖 ComfyUI，可以直接用系统 python 跑（不需要 `folder_paths`）。

## 测试基线

```bash
python tests/run_all.py          # 全量 ~8s
python tests/run_all.py --fast   # 抽样 40 条母题
python tests/run_all.py --http   # 加打 8188 端点（服务需在跑）
```

17 项，全绿才算通过。有几项是**专门防回归**的，改代码时别绕过去：

| # | 守什么 |
| --- | --- |
| 05 | 3318 组全量装配零告警（含 `orig_char` 残留检查） |
| 08 | 非法入参必须抛 `Exception` 子类 —— 守住 `SystemExit` 那条红线 |
| 09 | `generate()` 不污染全局 `random` 状态 |
| 10 | `load()` 缓存命中 < 首次 1/3，且改 mtime 后能重新解析 |
| 11 | 原子写失败时原文件不损坏、无 `.tmp` 残留 |
| 12 | 场景画幅覆盖层：样例必须「推荐值 ≠ 覆盖值」才证明生效；合流后缓存里仍是推荐值 |
| 13 | 卡片徽标是 `button`、循环链 `竖→横→方`、连点有 `dataset.busy` 挡 |
| 14 | `__version__` 与 `pyproject.toml` 一致 |
| 15 | 三个随机池仍在 `optional` 末尾 |
| 16 | 前端 JS 过 `node --check` |
| 17 | HTTP 端点 + 路径穿越 3 条用例 |

加新检查的写法：`@check("名字")` 修饰一个返回 `(bool, detail)` 的函数，放进 `CHECKS` 即可。

## 发版流程

1. **确认零漂移**：改装配逻辑的话，用 `--fast` 前后对比指纹（固定 `random.seed` 跑同一批母题，逐字节比对）
2. **改三处版本号**：`__init__.py` 的 `__version__`、`pyproject.toml` 的 `version`、README 的版本行
   （测试第 14 项会校验前两者一致）
3. **跑全量测试**：`python tests/run_all.py --http`
4. **重启验证**：启动日志出现新版本号，`/k2ed/manifest` 正常
5. **重新精简服装库**（仅当更新了 Anima 快照）：
   `python tools/make_sfw_bundle.py --inplace`
6. **提交**：`git add -A && git commit -m "v1.x.y: <一句话>"`
7. **打 tag 并推送**：`git tag v1.x.y && git push --tags`

### 打包一份可分享的 ZIP

仓库里有 45 MB 图片资源，GitHub 的 `Code → Download ZIP` 只带 `HEAD`，且国内直连很慢。
要给别人的话，从本地工作区打一个 `git archive` 包（只含已跟踪文件，自动排除
`.git`、`user_*.json`、`_bak_*/`、`__pycache__`）：

```bash
git archive --format=zip --prefix=Comfyui-K2-Editorial/ \
            -o ../Comfyui-K2-Editorial-v1.13.0.zip HEAD
```

⚠ 打完之后要**改目录名断言**：解压出来的第一层必须是 `Comfyui-K2-Editorial/`，
里面直接是 `__init__.py`（多套一层会让 ComfyUI 加载不到）。

### 关于 ComfyUI Registry

`pyproject.toml` 已按 Registry 格式写好（`[tool.comfy]`）。发布前需要：

- 补 `LICENSE`（已有 AGPL-3.0）并在 pyproject 里启用 `license` 字段
- 确认包体大小：仓库 45 MB，Registry 有单包上限，超了就把 `thumbs/` 排除
- `PublisherId` 需与 Registry 账号一致

### 关于 SFW 精简

公开仓库的 `presets/anima/outfit_library.json` 是精简版（98 套 / 最高 L1 / 无 `nsfw_outfit`）。
从 Anima 同步新版本时，**必须重新跑一次 `tools/make_sfw_bundle.py --inplace`**，
否则会把高档位条目带进公开仓库。

`_meta.sfw_bundle` 字段记录了精简参数，可用它自查。
