# Comfyui-K2-Editorial

<p align="right">
  <b>中文</b> ｜ <a href="README.en.md">English</a>
</p>

> [!CAUTION]
> **⛔ 未经许可禁止商用 · 禁止二次包装分发** —— 版权所有 © 2026 灵冻不冻（lingdongbudong），保留所有权利。
> 本仓库自 **2026-11-24** 起采用 **[PolyForm Strict License 1.0.0](LICENSE)**。
>
> - **❌ 禁止商业使用** —— 未经书面许可，不得将本插件（含源码、词库、场景库、角色库、服装库、预设数据及任何衍生物）用于任何商业目的：付费分发、捆绑销售、代跑收费、商业课程、以本插件作为商业服务的技术底座等。
> - **❌ 禁止二次包装与再分发** —— 不得重新打包、改名、套壳、二次封装发布，不得上传至第三方整合包、网盘合集、资源站或任何分发渠道，**无论是否修改**。
> - **❌ 禁止移除或篡改**本声明、作者署名与来源链接。
> - **✅ 允许** —— 个人非商业使用（研究、学习、爱好、自己出图）、修改源码自用；保留完整署名与本声明的前提下引用截图／录屏做非商业分享（如 B 站教程）。
>
> **商业 / 二次开发 / 转载授权** → [B 站私信作者](https://space.bilibili.com/516891894) 取得书面许可。
> **历史版本**：本次变更前发布的版本仍按其发布时的许可证（AGPL-3.0）授权，不因本次变更而撤回。
> 完整条款与来源声明见 **[NOTICE.md](NOTICE.md)**。

---

**Krea2「白垩光 / 未来奢华编辑主视觉」长文提示词的自动装配节点** —— 选角色、母题、画幅、服装，输出 1500–2700 词的英文长提示词。一个母题决定整张画面，不是 tag 随机池。

![ComfyUI](https://img.shields.io/badge/ComfyUI-0.42.x-2f6f4e?style=flat-square)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776ab?style=flat-square)
![License](https://img.shields.io/badge/license-PolyForm%20Strict%201.0.0-red?style=flat-square)
![Dependencies](https://img.shields.io/badge/dependencies-none-success?style=flat-square)
![Offline](https://img.shields.io/badge/runtime-100%25%20offline-informational?style=flat-square)

> ⚠️ **使用边界**：本插件只生成**文字提示词**，不生成图片，运行时零联网、不调用任何大模型。
> 内置角色数据与立绘快照来自 [Comfyui-Anima-Wardrobe-V6](https://github.com/lingdongbudong)，
> 角色名与作品名（初音未来、原神、Fate、蔚蓝档案、明日方舟、碧蓝航线、鸣潮、绝区零、崩坏：星穹铁道等）
> **归各自权利人所有**，此处仅作提示词组装用的描述性标识，不代表任何授权或关联。
> 服装库已精简为 SFW（L0–L1，剔除 `nsfw_outfit` 分类），不含成人向条目。
> 若你所在地区对 AI 生成内容有额外限制，请自行确认合规后再使用。

## 作者与更新

| 角色 | 作者 | B 站主页 |
| --- | --- | --- |
| 插件作者 | **灵冻不冻** | [space.bilibili.com/516891894](https://space.bilibili.com/516891894) |
| 母题创作者 | **辞雪沐春** | [space.bilibili.com/1522948414](https://space.bilibili.com/1522948414/dynamic) |

**插件作者在 B 站有插件使用教学视频**：安装、三种母题分支（3D 场景 / 平面海报 / 短提示词）的区别、
角色与服装怎么选、画幅徽标怎么联动工作流，都有对应演示。

**版本更新进度也以 B 站动态为准** —— 新增母题、角色库同步、Bug 修复会先在那里说明，
比翻 commit 记录好读得多。

想反馈问题、点名某个角色的官方服装、或者投喂母题创意，欢迎到 B 站留言。
**感谢每一位使用者与反馈者的支持。**

## 目录

- [作者与更新](#作者与更新)
- [这是什么](#这是什么)
- [节点与用法链路](#节点与用法链路)
- [安装](#安装)
- [快速上手](#快速上手)
- [参数速查](#参数速查)
- [示例工作流](#示例工作流)
- [常见问题](#常见问题)
- [文档](#文档)
- [兼容性与已知限制](#兼容性与已知限制)
- [更新日志](#更新日志)
- [署名与来源](#署名与来源)
- [许可证](#许可证)

## 这是什么

Krea2 的「白垩光」是一套**一体化长文提示词**：25 段结构里母题（巨构场景 / 平面海报）决定整张画面的构图、材质、光位与排版语言，只能做有限替换。拆成随机池组合会立刻互相矛盾，所以本节点的设计是「**母题整块 + 有限替换位**」。

| 特性 | 说明 |
| --- | --- |
| 母题 | 558 条长文（3D 场景 317 / 平面海报 15 / 短提示词 226），每条自带画幅建议与中英文标题 |
| 角色 | 2432 位，跟 Anima-Wardrobe-V6 实时同步；没装则用内置快照（2432 位 / 2444 张立绘） |
| 服装 | 8 套通用版型 + 角色官方预设 2800 套（2434 位） + 服装库 113 套（内置 SFW 快照 10 类；装了 Anima 即读其完整库 167 套 / 11 类） |
| 服装替换 | 按部位（上装 / 下装 / 连衣裙 / 腿部 / 鞋 / 配饰）只写母题需要的部位；长文里各种旧服装写法自动让位 |
| 替换位 | 角色身份 / 画幅 / 服装材质 / 单品 / 画内排印文字 |
| 画幅联动 | 卡片徽标点一下 `竖 → 横 → 方 → 竖` 循环，同时切当前工作流画幅 |
| 输出 | 3 个 STRING：`提示词` / `自检报告` / `元数据` |
| 运行开销 | 单次装配约 1.7 ms，无模型、无显存占用 |
| 自检 | `python tests/run_all.py` → 23 项全绿 |

三种母题分支的写法不同，节点会自动适配：

- **scene（3D 场景）** — 20–25 段，带机位、材质分区、色盘百分比、五层景深
- **poster（平面海报）** — 保留版式与大标题，角色按海报语法适配
- **short（短提示词）** — 4–8 段短句，只换身份并追加一句服装说明

## 节点与用法链路

```
[★ K2 长文出题 · 白垩光]  ──提示词(STRING)──▶  CLIP Text Encode (positive)
        │                                    ──▶  采样 / 画幅参数节点
        └──元数据(STRING)──▶  PreviewAny（可选，排查用）
```

节点在 `Krea2/提示词` 分类下，画布上显示两行摘要（角色 · 画幅 · 服装 / 母题 · 种子）。
五个核心控件在节点上**折叠隐藏**，只在「⚙ 打开设置面板」里选 —— 同一个设置只留一个入口，但隐藏不影响工作流序列化。

面板三页：**① 角色**（2432 位，分页 + 搜索 + 作品筛选 + 收藏）、**② 服装**（版型 / 角色预设 / 服装库）、**③ 场景**（558 原始母题，默认**按风格系列分组平铺**，另有系列 / 题材 / 场景标签三组多选筛选 + 勾选池 + 画幅徽标）。右侧常驻预览栏。选中即写回节点，不需要点「应用」。

## 安装

需要 ComfyUI **0.42.x** 与 **Python ≥ 3.10**（实测 3.13），无第三方依赖，不需要 `pip install`。

**方式一：git clone**

```bash
cd <ComfyUI>/custom_nodes
git clone https://github.com/lingdongbudong/Comfyui-K2-Editorial.git
```

**方式二：下载 ZIP**

在仓库页点 `Code → Download ZIP`，解压到 `<ComfyUI>/custom_nodes/Comfyui-K2-Editorial/`（注意目录名保持一致）。

装完**重启 ComfyUI**，启动日志出现下面这行即成功：

```
[K2-Editorial] v1.15.3 已加载：['K2EditorialBuilder']
```

## 快速上手

1. 画布空白处右键 → `Krea2/提示词` → **★ K2 长文出题 · 白垩光**
2. 点节点上的 **⚙ 打开设置面板** → ③ 场景选一条母题（会自动带出推荐画幅）
3. ① 角色选人 → 关面板 → 把 `提示词` 接到 `CLIP Text Encode` 的 positive → 排队

最短验证：`python tests/run_all.py --http` 能跑通，说明插件与服务都正常。

## 参数速查

常用项列在这里，**完整参数表见 [docs/USAGE.md](docs/USAGE.md#参数全表)**。

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `随机种子` | `0` | 勾了「每次重随机」时本项无效 |
| `每次重随机` | `true` | 关闭后同种子可复现；固定种子下改母题库会自动失效缓存 |
| `角色` | `miku` | 字符串，不是下拉（2432 条做成 combo 会让 `/object_info` 膨胀） |
| `母题` | 首条 | 558 条；**新增母题要重启**才进下拉，HTTP 直传 id 不用 |
| `画幅` | `16:9` | 8 种；海报 / 短提示词分支保留原版式写法 |
| `服装` | `自动（跟随母题）` | 也可选 8 套版型或「保持母题原样」 |
| `单品` | 空 | `char:<预设 id>` 或 `lib:<服装库 id>`，叠在版型段之后 |
| `覆盖提示词` | 空 | 非空则跳过装配，直接输出这段文本 |
| `画面英文文字` / `画面不显示英文` | — | 控制画内排印文字 |
| `角色随机池` / `场景随机池` | `关闭` | ⚠ 三个随机池必须在控件末尾，别往前插 |

## 示例工作流

| 文件 | 用途 | 额外依赖 |
| --- | --- | --- |
| `workflows/K2-白垩光_出题节点已接线(参考).json` | 最小接线示例：出题节点 → 文本编码 | 无 |
| `workflows/Krea2-白垩光标准档.json` | 完整出图链路（采样 / 参数 / 保存） | 需 XB_ToolBox 的 `XB_ImageParamsMaster` |
| `workflows/Krea2-平面设计档.json` | 海报分支链路，走平面图形语法 | 同上 |

前两个工作流里的 `XB_ImageParamsMaster` 是可选依赖，没有它也能跑（画幅由节点输出决定）。

## 常见问题

**Q：装完节点列表里找不到？**
看启动日志有没有 `[K2-Editorial] v... 已加载`。没有的话检查目录名是否为 `Comfyui-K2-Editorial`（`__init__.py` 必须直接在目录下，不能套一层）。

**Q：母题下拉是空的 / 只有一条？**
`presets/seeds_motifs.json` 与 `seeds_extra.json` 缺失或损坏。跑 `python tests/run_all.py` 会明确报出哪份文件读不出来。

**Q：角色页只有 2 个人（miku / furina）？**
说明既没装 Anima-Wardrobe-V6，内置副本也没被读出来。检查 `presets/anima/anima_v4_characters.json` 与 `thumbs/anima/` 是否都在；或用 `K2ED_ANIMA_SOURCE=bundle` 强制走内置。

**Q：改了母题正文，出图没变？**
母题内容在 `presets/seeds_*.json`，改完必须**重启** ComfyUI（缓存与 combo 列表都在进程内存里）。

**Q：自检报告显示 `!! 装配失败: ...`？**
首行就是原因，常见是角色 id 不存在（手写 key 只有 `miku` / `furina`，其他要用 Anima 的完整 tag）。

其余问题见 [docs/USAGE.md 的 FAQ（20+ 条）](docs/USAGE.md#常见问题-faq)。

## 文档

| 文档 | 内容 |
| --- | --- |
| [docs/USAGE.md](docs/USAGE.md) | 完整使用说明：安装细节、参数全表、面板逐项、5 个典型示例、20+ 条 FAQ、限制 |
| [docs/MAINTAINERS.md](docs/MAINTAINERS.md) | 维护者指南：改代码前必读的红线、目录结构、数据链路、测试基线、发版流程 |
| [README.md](README.md) | 本文件（门面） |

## 兼容性与已知限制

- **ComfyUI 0.42.x** 实测通过；前端依赖 `app.registerExtension` 与 `LiteGraph`，更老的版本可能缺 `widget.inputEl`。
- **Python ≥ 3.10**（用了 `X | None` 注解 + `from __future__ import annotations`）。
- **新增控件必须加在 `INPUT_TYPES["optional"]` 末尾**：放进 required 或插到中间，会让老工作流的 `widgets_values` 错位、丢掉整张输出。
- **禁止在节点代码里 `raise SystemExit`**：它继承 `BaseException`，ComfyUI 的 `execution.py` 接不住 —— 实测会让 8188 端口仍 LISTENING 但整个 HTTP 服务不再响应，只能重启。一律用 `ValueError` 子类。
- **固定种子 + 改数据文件**：`IS_CHANGED` 已纳入母题库 / 版型 / 收藏 / 勾选池的指纹与代码 mtime，改盘会自动失效输出缓存。
- **仓库体积约 45 MB**（角色立绘 22 MB + 母题预览 14 MB + 数据与代码 8 MB），clone 会比普通节点慢。没有这些图也能跑，只是面板无预览。
- **角色名残留自检**只对母题里登记过 `character` 的 30 条生效（29 条 Hatsune Miku + 1 条 Furina）；其余母题不写死角色，无需检查。

## 更新日志

### v1.20.17

- **修：点选两条人物参考图母题后，画幅被强制切成 3:4 而不是 9:16**。
  `pickMotif()` 原来的映射只看粗类：`aspect === "portrait"` 一律给 `"3:4"`，
  完全不读母题自己的 `ratio`。两条参考图母题在 manifest 里是 `aspect=portrait` + `ratio=9:16`，
  于是被折进「竖屏 → 3:4」，卡片角标写着 9:16、节点画幅却是 3:4。
  - 改法：`ref` 母题优先按 `ratio` 精确切（要求 `ratio` 在 `ASPECT_SIZE` 里），
    其余母题保持原手感（竖 3:4 / 横 16:9 / 方 1:1），558 条既有行为不变。
  - 验证：`ref front → 9:16`、`ref sheet → 9:16`、普通竖屏仍 `3:4`、横屏 `16:9`、方屏 `1:1`。
- 回归 **29/29 全绿**。

### v1.20.16

- **修：参考图母题出图变成俯视，人被压成头大身短**（联机实测，卡芙卡 / 甘雨各跑 3 轮）。
  排查过程：先怀疑 9:16 太窄 → 换 3:4 仍俯视；再加 `level camera at chest height, no tilt` 无效；
  加 `orthographic front elevation, parallel projection` 也无效。
  **最后用一句极简提示词直出（`full body standing front view of one woman, eye level camera, straight on,
  pure white seamless studio background`）得到完全正确的平视全身** —— 证明不是模型/画幅先验，
  是母题里的词把构图带偏了。
  - 元凶：`character reference sheet` 被理解成「多视角设定图」（要压视角塞多面），
    `orthographic front elevation / parallel projection` 被理解成「工程正投影」（要俯视压缩）。
  - 改法：正面全身母题改成 `full body standing front view … eye level camera looking straight ahead`，
    去掉 reference sheet / orthographic / 「占画面 85%」；四视图保留 `turnaround sheet` + 2×2 grid，
    去掉 orthographic。两张白底改成 `flat even high-key lighting … no vignette`。
- 联机验证（Krea2 8 步，1088×1920）：
  - `k2s_ref_front` 甘雨：平视、头顶到鞋完整、白底干净、角/铃铛/礼服/黑丝/鞋全对。
  - `k2s_ref_sheet` 甘雨：2×2 正确，上左正面头肩 / 上右侧面头肩 / 下左正面全身 / 下右背面全身，四格特征一致。
- 母题词数：front 245w（装配后 357w）、sheet 406w（装配后 503w）。回归 **29/29 全绿**。

### v1.20.15

- **两条人物参考图母题统一 9:16**：`k2s_ref_front`（正面全身）由 3:4 改为 9:16，与四视图一致；
  竖长画幅下全身留白更足，脚不会被画框挤掉。
- **四视图上两格改成头部特写**：原来写 `from the crown of her head to mid-chest`，
  模型给到半身；现在改成
  `a tight front head-and-neck close-up framed from the crown of her head down to the base of her neck,
  the whole head filling that panel edge to edge`，侧脸同口径。
  下两格仍是正面 / 背面的全身站姿，四格同一比例、同一地面线。
  正文措辞同步把 `full-body` 换成 `full-height`，避开 `GARMENT_NOUNS` 的误判。
- 回归 **29/29 全绿**。

### v1.20.14

- **新增「人物参考图」母题两条 + 视图行筛选**（面板场景页「视图」行末）：
  - `参考图·正面全身`（`k2s_ref_front`，3:4）：纯白无缝底、单人、正面站姿、头顶到双脚全在画内。
  - `参考图·四视图`（`k2s_ref_sheet`，9:16）：2×2 四格 —— 上左正面头肩 / 上右侧面头肩 / 下左正面全身 / 下右背面全身。
  - 两个 chip 单选，再点一次取消；归入新系列「人物参考图」，母题总数 558 → **560**。
  - 数据走 `presets/motif_ref.json`（`front` / `sheet`），`build_manifest.py` 透传成 `motifs[].ref`。
- **写这类白底母题时要避开服装名词**：`GARMENT_NOUNS` 里有 `top`，所以
  `the top-left panel` / `from the top of her head` 会被判成服装句，整段被 `rewrite_clothing`
  当成旧衣服摘掉（四视图的 2×2 布局段一开始整段消失，只剩一条 Dress 指令）。
  改写口径：`top-left/right` → `upper-left/right`、`bottom-*` → `lower-*`、
  `the top of her head` → `the crown of her head`；`shoes` 一律换成 `feet`。
- 回归 **29/29 全绿**。

### v1.20.13

- **景别从五档收敛成三档**：人像 / 半身 / 全景。
  - 人像 = 特写 + 近景（脸到胸以上，人物占满大半个画面）
  - 半身 = 中景（腰或膝以上，人物 + 少量环境）
  - 全景 = 远景 + 超远景（人物全身甚至很小，环境 / 巨构为主）
- 原因：v1.20.12 的五档要求「近景 vs 中景」这种很细的边界，而母题文案与参考图本来就大面积不一致
  （`k2x_clsc_railgun` 写 close-up、图是中景；`k2p_blooming_freq` 写 half-body、图是全身），
  边界越细错得越多。三档宽容得多，人工校对的 49 条全部按新档位归并。
- 内部仍保留五档判定再映射，脚本 `tools/classify_shots.py` 的 `--set` 可直接写三档名，
  也因此可以写五档名（自动归并）。`presets/motif_shots_override.json` 里的旧五档值已归并。
- 当前分布：人像 22 / 半身 135 / 全景 401。
- 回归 **29/29 全绿**。

### v1.20.12

- **新增「景别」筛选行**（面板场景页，画幅行下面）：特写 / 近景 / 中景 / 远景 / 超远景 五档，
  带各档数量。同一维度内多选 OR、跨维度 AND，跟标签 / 题材 / 系列一致；关多选时自动收敛单项。
- 数据侧：`manifest.json` 每条母题新增 `shot` 字段；`tools/classify_shots.py` 可按正文重算，
  人工校正写在 `presets/motif_shots_override.json`，重跑规则不会覆盖。
  - 判定顺序：显式取景词（附近要有人物词）→ 人物高度占比（只认 `percent of the canvas height`）
    → 分支默认（scene/short→远景或中景、poster→中景）。
  - 已知坑：`close-up` / `half-body` 这类词在母题里常被滥用（`k2p_blooming_freq` 写 half-body、
    参考图是全身），**文本规则与参考图对不上是母题库的老毛病**，所以低置信度的必须用缩略图校正。
    `small seated figure` 不算超远景（那是娇小身材，不是画面小）。
- 当前分布：特写 3 / 近景 19 / 中景 135 / 远景 338 / 超远景 63，其中 49 条已人工按缩略图校正。
  剩余仍是规则推定，筛完请以缩略图为准。
- 回归 **29/29 全绿**（新增第 04 条：景别字段齐全 + 五档非空）。

### v1.20.11

- **修正：开了「锁定发色」，发色仍被母题自带的颜色词污染**（`k2s_cx_064` 人像 06、`k2s_cx_061` 海报 31 实测）。
  根因不在锁定声明本身 —— 声明挡的是「周围色盘不许染发」，而这两条母题**在正文里直接指定头发是蓝色**：
  - 064：`long twin tails … breaking into controlled cobalt and ivory brushlike strokes`
  - 061：`her twin tails trail into fine blue filaments that cross the image`
  正面断言盖过了声明，模型照画，出图就是紫发渐变到蓝发梢。
  - 母题改写：`cobalt and ivory brushlike strokes` → `dry-brush strokes that hold one unbroken hair color`；
    `fine blue filaments` → `fine filaments of the same hair color`。
  - `HAIR_LOCK_SENT` 补一句覆盖**发丝 / 发梢 / 笔触**：`Every strand, tip, lock and brush stroke of that hair
    carries the same single color from root to end, so the scene's cool blues, cyans and violet lights stay on
    its surfaces, rims and highlights while the hair itself holds one continuous hue.`
- **口径提醒：锁定发色只能压「色盘比例 / 环境冷光」，压不住「头发本体被写成某个颜色」。**
  扫描 241 条短提示 / 海报母题，装配后仍出现「头发 + 蓝/青」子句的有 97 条，其中大部分是环境词
  （`cool blue shadows` / `silver-blue moonlight` / `cyan rim light`）—— 这类开着锁定就够；
  真正要改文案的是把颜色写死在发丝、发梢、笔触上的那些。
- 回归 **28/28 全绿**。

### v1.20.10

- **修正：短提示 + 官方服装时，服装清单被替换两次，只剩一个配饰**。
  `set_character_short()` 先用 `replace_tag_stream_outfit()` 把 tag 流段落整组写成新单品，
  紧接着 `rewrite_clothing()` 又把刚写进去的新衣服当成「母题自带的旧衣服」再处理一遍 ——
  `swap_garments()` 逐条摘除，最后姿势段只剩一个 `sunglasses.`，完整服装清单反而丢失。
  - 新增 `rewrite_clothing(..., skip_tag_stream=True)`：已整组替换过的 tag 流段落直接跳过。
  - 症状：正文出现「…both hands visible, sunglasses.」这种半截服装句，服装约束变弱，
    模型容易自己补下半身和鞋。
- **修正：`k2s_cx_011`（晨曦·暗调 02 / 星象仪）取景与正文不一致**。
  文案写 `full-body` + `full figure clearly separated`，而参考图实际是**画框裁在裙摆的构图**。
  模型为同时满足「全身」与 `wide view of the dome`，把机位压成俯视、人物压短，
  头大身短、双手挤在胸前，并把脚拉进画面自补一双鞋。
  - 现改为**上半身照**：`upper-body portrait framed from head to waist`。
  - `both hands visible` → `hands resting loosely in front of her waist`（不再要求「可见」，改写成具体姿势）。
  - `full figure clearly separated / wide view of the dome` → `her upper body occupying the central third of the frame / the dome arching wide behind her`。
  - 顺带两处：`lightweight skirt` → `bodice fabric`（上半身看不到裙摆）；
    光段 `soft reflections on the dark floor` → `faint reflected starlight on the gallery walls`（地面出画）。
  - 因为 `upper-body` 命中 `_FRAME_UPPER`，`frame_zones()` 只返回 `{upper}`，
    服装只写上半身单品 —— 卡芙卡预设里的 `shorts` 会被自动丢掉，不会再往下半身补衣服。
    母题 245w → 267w，段落仍 8 段。
- 回归 **28/28 全绿**。

### v1.20.9

- **「⚙ 打开设置面板」改用真正的 DOM widget（`addDOMWidget`）**，彻底不碰坐标换算。
  前面几版依次试过：canvas 自绘按钮（被 DOM 控件盖住 / 命中坐标随缩放漂移）、
  litegraph 老式 canvas button（命中依赖 `last_y`，节点一收缩就点不着）。
  DOM 元素走浏览器自己的 click 事件，位置由 ComfyUI 布局 —— **既不会看不见，也不会点不着**。
  - 无 `addDOMWidget` 的老版本自动退回 `addWidget("button")`。
  - 按钮宽度 `100%`、高 28px，节点折叠宽度下限提到 320，点按区域更大。
  - 折叠高度固定 150px（摘要 56 + 锁定发色 26 + 按钮 34 + 余量），不再依赖 `computeSize`。
- `__k2ed.debug()` 现在打印 `size / btnEl 是否存在 / 全部 widget 名`，用于确认 DOM 按钮有没有挂上。
- 回归 **28/28 全绿**。

### v1.20.8

- **修正：v1.20.7 改为自绘后按钮「看不见」**。两个原因：
  1. **canvas 自绘被 DOM 控件盖住**。ComfyUI 新版 widget 是 DOM 元素，层级在 canvas 之上；
     而按钮原来画在 `y = 摘要底部 + 6`，正好压在「锁定发色」那一行的下面 → 被整块遮掉。
     现在按钮 y 由**所有 widget 的 `last_y + height` 底部**推出（`Math.max(y+6, wigBot+10)`），
     保证排在控件下方。
  2. **节点高度不收缩**。加载工作流时 `configure()` 会触发 `onResize`，被误判成「用户拖过」，
     自动撑高永久失效 → 节点保持 700px 空壳。折叠态改为**强制按内容收缩**，不再看 `__k2edUserResized`。
- 新增 `__k2ed.debug()`：打印节点尺寸、按钮矩形、每个 widget 的 `last_y / height`。
  按钮位置再出问题时，一条命令就能看出是「画在控件区被盖」还是「画出节点外」。
- 回归 **28/28 全绿**。

### v1.20.7

- **「⚙ 打开设置面板」改为节点自绘，不再用 `addWidget("button")`**。
  用户实测：**双击节点能开、单击按钮不动** —— 证明 `openPanel` 本身没问题，
  问题在 widget 的点击命中：litegraph 按 `widget.last_y` 判命中，节点折叠收缩后按钮会落到
  节点矩形之外，并且 `hideWidgets` 把被隐藏控件的 `computeSize` 改成 `[0,-4]`，
  让 `computeSize()` 算出的总高度也不可信。
  - 现在按钮由 `onDrawForeground` 画（圆角矩形 + 文字 + 悬停高亮），
    `onMouseDown` 用**同一套局部坐标**判定命中，绘制与点击范围天然一致。
  - 节点高度按绘制内容的实际底部动态撑开（`by + BTN_H + 10`），代码自己 `setSize`
    不记作「用户拖过」（`__k2edAutoSize` 标志），避免一次自动撑高就锁死。
  - `pos` 在部分 litegraph 版本是画布坐标，所以**两种坐标都试**一遍。
- 调试：单击按钮时 Console 会打 `[K2Editorial] 自绘按钮点击 → openPanel [x,y]`。
  有这条 = 命中正常；没有 = 节点事件没收到，继续查事件层。
- 回归 **28/28 全绿**。

### v1.20.6

- **修正：折叠后的节点高度写死 104px，把「⚙ 打开设置面板」按钮甩到节点命中区之外** ——
  按钮画得出来、看得见，但鼠标点上去 litegraph 判定不在节点范围内，**回调根本不触发**。
  `锁定发色` 在按钮上方、仍在 104px 内，所以它能交互 —— 这正是用户看到的现象。
  - `fold()` 改成按 `computeSize()` 撑高度（`Math.max(104, 内容高度 + 6)`），不再写死。
- **加诊断入口**（这类「点了没反应」的排查手段）：
  - `window.__k2ed.nodes()` 列出图上 K2 节点及其 widget；
  - `window.__k2ed.open()` 绕过按钮直接打开面板；
  - `window.__k2ed.lastError` 最近一次失败原因；
  - **双击节点**也能打开面板 —— 双击能开 = 按钮绑定/命中问题，双击也开不了 = openPanel 内部问题。
  - 点击按钮时 Console 会打一条 `[K2Editorial] 按钮点击 → openPanel`，用来确认回调是否被触发。
- 回归 **28/28 全绿**。

### v1.20.5

- **修正：v1.20.4 引入的防重入锁会让「打开设置面板」永久失效**。上一版用的是
  `if (_opening) return` + `finally` 复位 —— 只要有一个 `await` 永不返回
  （`fetch` 挂住 / 缩略图批量加载卡住），`finally` 就永远不执行，之后每次点击都被静默拦掉，
  表现就是**「点了一点反应都没有」**（`锁定发色` 这类原生控件仍然正常，因为不经过这条路）。
  - 改用**时间戳 + 20 秒自愈**：`_openingSince`，超时即视为失效，允许重试。
  - 每个关键 `await` 用 `withTimeout()` 包住：母题库 10s / 角色表 10s / 收藏与服装锁定 6s /
    场景页 12s / 侧栏 8s。任何一步超时只影响那一块，面板照样出来并报原因。
- **按钮加了即时反馈**：点下去文字变「⏳ 正在打开…」，结束恢复；被防重入拦下时显示
  「⏳ 还在打开中…」1.5 秒 —— 这样能一眼区分「没点中」「卡住」「被拦」。
- **版本埋点**：面板脚本加载时 `console.log("[K2Editorial] 面板脚本 v1.20.5 已加载")`，
  按 F12 就能确认浏览器跑的是哪一版（旧 JS 缓存是这类问题的常见来源）。
- 回归 **28/28 全绿**。

### v1.20.4

- **修正：点「⚙ 打开设置面板」偶尔完全没反应**。三个原因叠在一起：
  1. **面板 DOM 被前端重建后仍复用旧引用**。`ensurePanel()` 原来只判 `if (PANEL) return PANEL`，
     而 ComfyUI 换工作流 / 前端重挂时 `body` 可能被重建，`PANEL.mask` 还指着已经脱离文档的旧节点 ——
     之后 `display:flex` 设了也看不见。现在加 `document.body.contains()` 存活检查，失效就重建。
  2. **`display:flex` 写在函数最末尾**。中间任何一步 `await` 抛异常都会走到「点了没反应」。
     现在**先亮面板**再加载数据，任何一步失败都变成「面板开着 + 状态栏报错」。
  3. **`built` 早于初始化置位**。原来 `p.built = true` 写在绑定事件之前，一旦某个
     `querySelector` 抛错，事件永远绑不上、下次打开还会跳过绑定。现在绑定抽成
     `bindPanelOnce()`，**全部成功才置 `built`**，失败可重试。
- 另外：`openPanel` 加防重入锁（连点两次会把 STATE 和渲染跑两遍）、`manifest` 空数据保护、
  `renderTabs / renderSeed / renderPage / renderSide` 分步容错 —— 某一块画不出来不再连累整个面板。
- 回归 **28/28 全绿**。

### v1.20.3

- **全库排查：母题写死的「别人的发色 / 瞳色 / 发型配饰」统一重定向到角色设定。**
  558 条里 **61 条**有残留，其中 50 条是真问题，分四种写法 —— 首段 tag 流、散文外貌串
  （`unmistakable very long hair, enormous red bow`）、保留句（`Keep the woman's straight white hair,
  golden eyes`）、IP 名场面整段（`Her long dark brown hair falls past her shoulders`）。
  根因是 `neutralize_residual_traits()` 只认 Miku 的 `aqua` / `twin tails`，不认识别人的发色。
  按句式打补丁修不完，改成按词重定向：
  - 新增 `retarget_motif_appearance()`：发色**完整短语**（连修饰词）换成 `hair_desc`、
    瞳色只换颜色词保留 `vivid / large` 修饰、发型配饰（ribbon / hairband / hairpin）摘掉并修逗号。
  - 异色瞳（`one deep blue eye and one pale ice-blue eye`）整组换掉，否则会变成
    `one purple eyes and one purple eyes`。
  - 发饰只在**人物描述段**（含 hair / head / eyes / braid / ponytail / bangs）里摘 ——
    否则会误删场景里的 `flowing tidal ribbons`（海面纹理）。
  - **`bow` 带武器词守卫**：它同时是蝴蝶结和弓，`k2x_bow_drawn` 首段整段在讲拉弓，
    第一版把 bow 当发饰删了 6 次、首句画幅 token 都被拆掉（测试 05 抓到）。
    段内出现 `weapon / drawn bow / longbow / crossbow / arrows / quiver` 就整段跳过。
- 结果：全库 **非角色发色 0 处 / 非角色瞳色 0 处**，残留发饰 6 处（IP 名场面发饰 + 印刷元素的
  `black ribbon`，属正常保留）。影响 121 条母题。
- 回归 **28/28 全绿**。

### v1.20.2

- **修正：tag 流母题首段的「另一个角色的外貌」也能替换了**。唱片店 / 榻榻米房的首段是
  `Dynamic cinematic anime illustration, Hatsune Miku, canonical character design, short icy-blue bob hair, large blue ribbon, vivid blue eyes, blue-and-simple dress …`
  —— 登记为 Miku，实际写的是**琪露诺**的外貌。v1.20.1 的首段清理只认「以 `16:9` 开头」，
  这条以 `Dynamic …` 开头，整个跳过了，于是换谁都是冰蓝短 bob + 蓝丝带。
  - 识别条件补一路：首段含 `canonical character design` 也算 tag 流（仍要求 < 500 字，
    避免把长文母题的首段拆烂）。
  - 补 `LOOK_ACC_RE`：`ribbon / bow / hairband / hairpin` 这类**发型配饰**一并摘掉。
- **修正：锁定发色句不再插进首段**。它原来退到「第一个含 hair 的段」，而 tag 流母题的首段
  正好写着别人的发色 —— 结果同一句里既有 `short icy-blue bob hair` 又有 `long purple hair`，
  模型选前面那个（这正是用户报的「开了锁定发色还是不对」）。
  现在优先贴 `canonical identity` 身份句，其次色盘段，最后才退到含 hair 的段。
- 影响范围：558 条里 **6 条**（`k2s_record_store` / `k2s_tatami_room` 新增，另 4 条微调）。
- 回归 **28/28 全绿**。

### v1.20.1

- **修正：母题首段写死的「原型人物外观」不再残留**。有一批短提示母题是从参考图转写的，
  首段把画面原型直接写死：
  `16:9 dynamic anime illustration, solo teenage girl with short apricot hair, freckles and a sky-blue windbreaker, wearing her date's slightly oversized navy baseball cap, …`
  —— 身份句换成目标角色之后，这段仍在说「杏色短发 + 雀斑 + 天蓝风衣 + 海军蓝棒球帽」，
  模型两边都听，结果换了角色帽子和外套还挂在身上（海边栏杆实测）。
  - 新增 `neutralize_motif_look()`：首段的发色/发型换成角色自己的，雀斑 / 瞳色 / 服装 / 配饰整段摘掉，
    构图与机位段（`POV` / `from the` / `beside` / `edge of`…）一律保留。
  - 帽子被摘掉后，正文里 `the brim` / `the cap` 的指代一并改成 `her hair` —— 否则
    「掀起帽檐」这个动作会失去依托，模型照样把帽子画回来。
  - **只认 tag 流母题**：首段必须以画幅比例开头（`16:9 …`）且短于 500 字符。放宽到
    「含 girl/woman with」会把长文母题的首段拆烂（实测 `k2s_abandoned_garden_2` /
    `k2s_window_light_4` 被摘掉 7~8 段）。
  - 受影响范围：558 条里 **4 条**（`k2s_seaside_rail` / `k2s_cinema_wait_3` /
    `k2s_dessert_shop` / `k2s_manga_shop`），其余零改动。
- 回归 **28/28 全绿**。

### v1.20.0

- **换角色后不再画成初音的双马尾**。发型段模板 `HAIR_TPL` 是照 Miku 写的，
  正文写的是 **the nearer length / the farther length** —— 把头发写死成**两束**。
  换角色只替换 `{hair}` 这个词、结构不动，模型就照样画成两股马尾（435/558 条母题走这份模板）。
  - 新增 `HAIR_TPL_SINGLE`：一个连续下落的发团 + 一小缕上挑，不作束数承诺，
    并写明 `falling loose from a single parting instead of being split to either side`。
  - `has_twin_tail(ch)` 为真（角色本人就是双马尾，如花火）才用两束版，其余一律单束版；
    装配日志会标「（双马尾版）」。
  - 短提示 / 海报分支里散落的 `twin tails` 仍由 `neutralize_residual_traits` 中性化，不变。
- **新增「锁定发色」开关**（面板页签行「🔍 角色自检」右侧，节点上是 optional 末尾的 `锁定发色`）：
  开启后发色**不参与**母题/角色的色彩比例分配。
  - 起因：色盘段把头发色按 **14%** 掺进整幅画面的色彩占比，模型会照比例给所有表面（含头发）
    一起上色 —— 深紫发被压成灰紫、金发被环境色洗成白。
  - 做法：在色盘段末尾补一条硬声明（`Hold her hair to its exact color: …`），把头发定义成
    **固定局部色**，画面其余部分朝着主色/主调压色时头发不许被 tint / desaturate / bloom / wash / re-grade。
  - 独立成句而不是改色盘段本身：`lock_palette=true` 的母题色盘段根本不替换，改那里对它们无效。
  - 三个分支（场景 / 短提示 / 海报）都生效；`IS_CHANGED` 已纳入该开关，固定种子下切换也会重算。
- 回归 **28/28 全绿**（控件顺序用例已把 `锁定发色` 纳入末尾断言）。

### v1.19.9

- **「角色自检」改成生成前自动跑**：每次点「刷新预览」/ 生成之前，自动比对
  **节点角色 · 图里的角色 LoRA · 触发词串 · 角色随机池**，不一致时状态栏**红字**提醒
  （`⚠ 角色自检：…`），**但不拦生成** —— 预览照常出，结果行里也会再带一次红字警告，
  直到配置改好为止。手动按钮仍保留，随时可点。
- 状态栏 `stat()` 支持第二个参数（`"warn"` → 红色），其它提示仍用默认灰。

### v1.19.8

- **面板新增「🔍 角色自检」**（页签行「③ 场景」/「LORA 服装触发词模式」右侧）：点一下把
  **节点角色 · 图里的角色 LoRA · 触发词串 · 角色随机池** 摆到一起比对，结果显示在右下状态栏。
  - 起因：实测遇到「节点写 hsin，但角色随机池=收藏角色·genshin impact 把提示词换成了雷电将军 / 甘雨，
    触发词串里又挂着 Hsin 的 white horns / fox-like ears」——三套身份一起进模型，出图就是紫发 + 角 + 狐耳。
  - 判定：LoRA 名或触发词里出现角色名（英文整词 / 中文前缀，`心` ↔ `心月狐`）算一致；
    随机池非「关闭」时无条件警告「面板上选的角色等于没选」。
- **页签行统一行高 28px + inline-flex 居中**：页签、LORA 开关、自检按钮、画幅分段、种子框、
  骰子、同步勾选框逐个 padding 对不齐的问题一并收掉。
- 回归 28/28（本次只动前端，JS 语法用例覆盖）。

### v1.19.7

- **新增「LORA 服装触发词模式」**：面板页签行「③ 场景」右侧多一个开关（节点上是 optional 末尾的
  `LORA服装触发词` 布尔控件，只追加在最后，老工作流不会错位）。开启后插件**一个服装词都不写**，
  服装交给角色 LORA 的触发词 —— 避免提示词里的衣服和 LORA 自带的整套服装缝在一起。
  - 服装库单品、8 套版型、角色官方预设：全部跳过（面板「单品」栏会写明该模式下不生效）；
  - 母题自带的服装段整段换成中性句 `Let her character trigger carry what she wears…`；
  - 全文按逗号项摘掉服装枚举（`a heavy charcoal wool coat, dark trousers, leather boots …`），
    所有格 `her coat's collar` 中性化，护盾里 `no missing top hat` 这类服装否定项一起去掉；
  - 色盘段里「十二 percent 是她的外套」被摘走后，**百分比按比例重算回 100**（附最大余数法校正）；
  - 身份句 / 护盾里写死的原作服装让位（复用 `costume_free_char`）；
  - 短提示词摘到不足 100 词时自动补一句中性留白句。
  - ⚠ 两个坑写进注释了：① 不能拿 `GARMENT_RE` 直接扫正文 —— 表里的 `top` 会把
    `the top edge of the frame` 当衣服整项摘掉（实测 34 条误伤）；② 首句头个子句必须保命 ——
    母题标题本身可能就叫 `SCARF` / `COAT`，摘掉会让首句丢画幅 token。
- 全量验证：**558 条母题 × LORA 模式 = 0 残留服装词、色盘全 100、篇幅合规**。
- 回归测试 **28/28 全绿**（新增：LORA 模式零服装词；控件顺序用例改为「新控件只准追加在末尾」）。

### v1.19.6

- **单品优先**：`服装 = 保持母题原样` 不再静默吞掉单品。只要单品**过完部位/姿势筛选后仍有内容**，
  装配器就把它当成「明确要换装」，覆盖 keep，走已验证的「指定单品 → 整段只写单品」路径
  （日志新增 `服装: 已选单品 → 覆盖「保持母题原样」，按单品换装`）。
  - 之前的行为：keep 下选单品只写一行 `已忽略单品（要换装请把服装设为「自动」）`，
    用户在界面上看着单品已选、出图却还是母题写死的那套衣服 —— 这是最容易被误判成
    「LoRA 锁死了官服」的坑。
  - ⚠ **单品被全部筛掉时语义不变**：归一化刻意放在 `prepare_outfit()` **之后**执行。
    若放到之前，选了袜鞋但母题只要上半身 → 单品清零却已把 keep 改成 auto →
    装配器会**随机套一套版型**，比原来的「忽略单品」更难排查。
  - keep 在**没选单品**时行为逐字节不变（IP 名场面照搬母题原作服装的能力保留）。
- 三个分支（场景 `set_character` / 短提示 `set_character_short` / 海报 `set_character_poster`）同一套归一化，
  日志前缀分别是 `服装:` / `短提示:` / `海报:`。
- 测试：原用例「keep 模式下仍强行换装」反转为「keep+单品 必须与 auto+单品 输出**完全一致**」，
  并新增反向守卫「单品全被筛掉时不得触发覆盖」。回归 **27/27**。

### v1.19.5

- **选母题不再自动换角色**：`clsc`（经典人物）系列 18 条全部解除 `recommend_char` 绑定，
  点开母题只用**你当前选的人物**，想换人在面板上换就行，不用再操作一步。
  新加的「坐姿」那 6 条本来就在 `clsc` 里，一并生效。
  - 之前的行为：点这些母题会自动把角色切成阿尔托莉雅/蒂法/2B 等，并把 `服装` 强行设成
    「保持母题原样」—— 想用自己选的角色必须手动改回去两次。
  - 现在与其他母题一致：不碰角色、不碰服装，只按推荐画幅切画幅。
  - 母题正文里「照原角色写的」那部分（身份句 / 发型段 / 服装段 / 色盘段）本来就会按所选角色整段替换，
    所以解绑后成图身份直接跟着你选的人走。
- 数据侧：`motifs_new/_meta.json` 的 `character` 全部置空 → 重打包 `seeds_extra.json`（只这 18 条变化，
  正文零改动）→ `manifest.json` 的 `recommend_char` 同步清空。
- 回归测试 **27/27 全绿**（新增用例：经典人物 / 坐姿母题不得再绑定角色）。

### v1.19.4

- **新增「坐姿」分类**（标签 key `sitting`，中文「坐姿」）：先收录 **6 条正文真是坐姿**的母题 ——
  河岸晨光 / 窗边余温 / 后巷霓虹 / 石厅逆光 / 雪后站台 / 王座加冕，面板「分类」行多一个「坐姿」chip（带条数）。
- **这 6 条改名为「场景·坐姿」**，把角色名从名字里拿掉（英文标题 FIRST LIGHT / HALL LIGHT 等不动）：
  `河岸晨光·阿尔托莉雅` → `河岸晨光·坐姿`，其余同理。
  - `recommend_char` 当时保留（点开自动带出原角色）——**v1.19.5 起已全部解绑**，见上一条。
- ⚠️ `clsc` 系列共 18 条，另 12 条（湖畔持剑 / 超电磁炮 / 吧台回望 …）正文首句是 **standing**，
  这次没改也没进「坐姿」分类 —— 名字与正文不符比缺分类更麻烦。
- 标签来源：`presets/motif_tags.json` 手工标注（姿势类没法从正文关键词可靠自动判），
  `build_manifest.py` 的 `TAG_ZH` 已登记 `sitting: 坐姿`，重建 manifest 不会丢。
- 回归测试 **26/26 全绿**（新增用例：坐姿分类的标签 / 名字 / 正文三方一致）。

### v1.19.3

- **「画面不显示文字」现在把小字母也一起清掉**。原来只删引号里那个词，母题剩下的半句
  （`Let a second, much smaller exact readable line … sit on a small enamel plate`、
  `stencilled word`、`the left vertical stem of the "H"`）照样把编号小字、铭牌、钢印字催出来。
  现在按**句子**判定「这句是不是在指挥写字」，三层一起做：
  - 引号里只要真有字（字母 / 数字 / 假名 / 汉字）就整句摘掉，残留的半截引号 `“ 39,”` 也清掉；
  - `readable / legible / exact` + 文字名词、或 `typography / lettering / wordmark / stencil /
    stem / stroke` 这类排版词 + 排版动词，一律摘；
  - 被摘空的段落换成留白句（段数不变），长文掉到 1000 词以下自动补一段「无字材质句」。
- 护盾里的 `no readable text beyond the string named above` 在无文字模式下自相矛盾，改写成
  `no readable text anywhere in the image`（`no readable floor numbers beyond the one display`
  这类变体也覆盖；`no gardener beyond the gate` 这种场景否定不动）。
- 母题里和画内标题同名的**普通名词**不再被误删：`Construct the megastructure from…` 只在
  「同一句里真在讲字」或该词全大写时才摘（之前会变成 `Construct the from…`）。
- 全量验证：**558 条母题 × 无文字模式 = 0 条残留写字句、0 条篇幅告警**。回归测试 **25/25 全绿**
  （新增用例：不显示文字时大字母与小字母一起消失）。

### v1.19.2

- **母题自带的角色装饰按角色分流（水晶翼）**：唱片店 / 榻榻米房正文里写着「六片水晶翼」，
  那是当初照甘雨写的专属装饰，不是场景陈设 —— 换角色后模型照样画在人背上（阿尔托莉雅版实测带翼）。
  现在母题在 `motifs_new/_meta.json` 用 **`owner_char`** 登记归属，装配时分流：
  选中角色 = 登记角色 → 保留；选中其他角色 → **连子句一起摘掉**，同段其它内容不动；没选角色 → 原样保留。
  - `pack_extra_seeds.py` 把 `owner_char` 打进 `seeds_extra.json`，`strip_owner_props()` 负责摘除并记日志；
  - 只对**登记过 owner_char 的母题**生效，其余 556 条母题一字不动。
- **玄关换鞋：门后的人影去掉**。原文「透过磨砂玻璃的第二重构图」写着 `the shadow of a handrail across it`，
  加上「玻璃在**手的高度**被蹭花」，模型两次都把它画成人手 / 人影。现在整段改成**一整片均匀发亮的磨砂玻璃**
  （只有肩高的软蹭痕 + 边框光晕），并在约束段加 `no silhouette or hand-shaped shadow on the frosted panel`。
- **电梯·通勤：改为微俯视 + 坐姿**。原来是「机位几乎正上方、传感器与地面平行」的俯视平面（人站着），
  现在是**机位略高于头顶、下俯约 25°**的 35mm 视角：电梯仍有纵深，门缝保持接近垂直；
  人物**坐在金属地面上**（背轻靠右墙、双膝收拢并拢、双靴平放、左小臂搭膝、右手撑地），
  地板方格 / 门缝 /「FLOOR」钢印字全部保留，并新增 `no aerial plan view` 约束防止退回俯视平面。
- 回归测试 **24/24 全绿**（新增用例：水晶翼按角色分流）。

### v1.19.1

- **修：选分类后再取消，列表自己往下跳（v1.18.0 / v1.19.0 都没修干净）**。这次把锚点方案整个撤掉：
  - 原来记「视口里第一张卡 + 偏移」，筛选一变（分组增减、卡片换行数变化）算出来的目标就偏几百像素；
    改成**只记滚动像素位置**，筛选前后页面纹丝不动，只有内容变短时才夹到新的底部；
  - `repaintFilters` 在**点击瞬间**先记一次位置，重绘后再兜一次底（内容变短按新底部夹紧，否则回原位）；
  - chip 加 `mousedown.preventDefault()`：不让按钮抢焦点 —— 焦点元素在网格重排时会让浏览器
    「为保持焦点可见」自动滚动，这也是「自己滑走」的常见来源；
  - 顺带修掉 v1.19.0 里 `page.style.minHeight` 冻结高度会把面板撑高的副作用（方案已不要）。
- 状态栏加了**滚动自检**：位置真的变了才报 `滚动自检：480 → 1120（内容高 …，可视 …）`，
  一看就知道是「内容变短被夹」还是「真跳了」。
- 回归测试 23/23 全绿。

### v1.19.0

- **场景页筛选区重排**：原来「视图 / 收藏 / 分类 / 画幅 / 系列 / 搜索 + 标签 / 题材 / 随机池」挤成一片，
  搜索框还占掉半行把标签挤到右侧。现在每条维度独占一行、左侧 56px 标签列右对齐（grid 两列，chip 换行后仍对齐）：
  ① 视图（分组/平铺）+ 收藏 + 新增 + 分类 → ② 画幅 + 多选开关 + 清除 + 搜索 → ③ 系列 → ④ 题材 → ⑤ 标签 → ⑥ 随机池。
- **新增「多选分类」总开关**（默认**关**）：关着时每个维度只能选一项，点新的就替换旧的；
  打开后可同时选「室内 + 夜间」「工业系 + 建筑」。关掉开关时，每个维度只保留**最后点的那一个**，行为可预测。
- **修：取消一个分类后列表自己跳到下面**。根因是 v1.18.0 改成按系列分段平铺后，页面里存在多个 `.k2ed-grid.mo`，
  而滚动记忆只从**第一个**网格里找锚点卡片 —— 在第二段以后滚动时锚点必然丢失，重绘后退回绝对 `scrollTop`，
  布局一收缩就跳到别处。现在遍历所有网格找锚点；锚点卡片被筛掉时退回「第一个可见段头」，
  落在同一段的段头位置而不是乱跳。
- **右侧栏新增「↑ 回到顶部」**：常驻在操作按钮下方，一键滚回列表顶部（三个页签共用滚动容器）。
- 回归测试 23/23 全绿。

### v1.18.0

- **场景页重做分类与浏览方式**（原来 558 条混在一个网格里，题材只有 22% 母题有值，点「日常 68」根本看不到大部分日常场景）：
  - **新增「风格系列」维度，10 组、覆盖 100%**：白垩原典 32 / 晨曦海报 68 / 黑曜暗调 37 / V6 场景 66 /
    工业构造 36 / 圆环几何 22 / 经典人物 18 / 场景合集 143 / 短提示杂项 121 / 平面海报 15。
    同系列是同一批写出来的，风格一致 —— 这是浏览「不同场景」最顺手的切法。
  - **默认视图改成「按系列分组平铺」**：每一组一个段头（组名 + 条数），段头点一下 = 只看这一系列；
    顶部可切回「全部平铺」。
  - **题材补全到 100%**（原 121/558）：新增 `urban` 城市、`hall` 宏大厅堂两类，共 9 类
    （日常 81 / 城市 58 / 自然 55 / 风景 30 / 宏大厅堂 14 / 奇幻 73 / 店铺 18 / 工业 21 / 其他 208）。
    ⚠️ 只保留**高置信判定**（关键词命中 ≥3 且领先第二名 ≥50%），线索不足的诚实标「其他」，
    不硬猜 —— 低阈值实测误差约 30%（「零号花园」被判奇幻、「三重套印」被判大厅）。
  - **筛选全部改成多选**（同一维度内 OR，维度之间 AND）：终于能问「室内 + 夜间」或「工业系 + 建筑」。
  - 分类逻辑抽成 `tools/classify_genres.py`，产出 `presets/motif_series.json` + 补全 `presets/motif_genres.json`；
    `build_manifest.py` 输出每条母题的 `series` 字段与 `MAN.series` 分组表。
- 关键词判定两个坑（已修）：① 必须整词边界匹配 —— 子串会把 `seam` 认成 `sea`、`horizontal` 认成 `horizon`、
  `counterweight` 认成 `counter`，礼服类母题会被整批误判成「自然」；② 礼服裙摆是 `train`，会和火车撞车，只能写 `train platform / last train`。
- 回归测试 23/23 全绿；manifest 558 条，series 合计 558、genres 合计 558。

### v1.17.3

- **`k2x_clsc_seat_side` 的腿部改成标准二郎腿**（普通「一条腿搭在另一条腿上」）。上一版两个口径自相矛盾：
  正面要求 `extends forward level with her hip`（腿水平前伸），负面清单里却钉着 `no leg hanging straight down beside the other`，
  模型只能画成「直腿横跨画面」，看着像伸腿、不像翘腿。
  现在：
  - 动作段：`her right thigh lies across her left thigh and her right knee sits above and slightly outside her left knee`
    —— **大腿压大腿**，全身只有这一个接触点；小腿从膝上**斜向内下方垂挂**，脚悬空、脚尖朝下、鞋底朝地，离地一拳；
    踏地那条腿的膝低于座面，小腿垂到底、鞋底平踏，是唯一触地的那只；
  - 负面清单：删掉 `no leg hanging straight down beside the other`（元凶），换成
    `no straight leg held out level / no leg stretched forward across the frame / no dangling foot touching the floor`。
- 其余口径不变：45° 侧前低机位、头后逆光、暗调、无柱、无冠、16:9。
- 实测：标准二郎腿成立（大腿交叠 + 小腿垂挂 + 鞋悬空 + 另一只脚踏地），逆光与暗调保持不变；回归 23/23 全绿。

### v1.17.2

- **`k2x_clsc_seat_side` 按参考图重做构图**，画内标题由 `COLONNADE` 改为 **`HALL LIGHT`**（场景里已经没有柱子，原名不再成立），中文名「石厅逆光」：
  - **机位**：低位 **45° 侧前**（`forty-five degrees across her left side`，水平与座面齐高、上仰 10°），人物在画面中心偏左，腿占右半；
  - **光**：改成**王座背后上方的一束逆光**（原来是从侧面高窗打过来），形成发丝轮廓光 + 腿的边缘光，背景压到近黑；
  - **腿**：从「小腿垂直下垂」改成 `extends forward level with her hip, the shin angling down no more than ten degrees`
    —— 也就是参考图那种**整条小腿水平前伸**的伸展姿态，脚下留一拳空隙；
  - **柱子全部撤掉**（连左侧那排也去掉），背景只剩一整面暗石墙 + 一个拱形壁龛 + 地面，负面加
    `no column / no pillar / no pilaster / no balustrade`；
  - **无王冠**沿用 v1.17.1 的口径（`no crown / no tiara / no diadem / no headpiece`）。
- 色盘按暗调重算（暗厅 38% / 黑缎 20% / 受光石座 14% / 皮肤与腿 10% / 暗石地 8% / 头发 6% / 头后光爆 3% / 鞋底高光 1%），合计 100。
- 实测：45° 侧前、头后逆光、腿水平前伸、暗调、无柱、无冠六项全部达成；伸出的鞋仍会贴近地面（腿全长 + 座高的物理关系，参考图同样如此）。
- 回归测试 23/23 全绿，manifest 558 条 558 图。

### v1.17.1

- **`k2x_clsc_seat_side`（柱厅侧影 / COLONNADE）按反馈重做三处**：
  - 机位从「近正侧 25°」改成 **45° 侧前**，既能读到交叉腿的轮廓，又给脸留出朝向镜头的角度；
  - **去掉王冠**：首句、材质段、阶梯序列、色盘、磨损、收束段里的金冠全部删除，
    负面清单加 `no crown / no tiara / no diadem / no headpiece`，头顶只留她自己的发饰；
  - **右侧柱子撤掉**：柱列只保留在她左后方并跑出画面左边缘，右半画面改成**一整片空白大理石墙 + 地面**，
    只承载四道长斜影。负面清单加 `no column on the right side of the frame / no second row of columns / no pillar at the right edge`。
- 色盘按新构图重算（右侧空墙 30% / 阴影大理石 20% / 黑缎 18% / 皮肤与腿 12% / 头发 8% / 王座 6% / 长影 5% / 鞋面高光 1%），合计 100。
- 实测出图：45° 视角、无王冠、右侧无柱三项全部达成；交叉腿（踝搭膝 + 一条鞋悬空 + 一条鞋踏地）成立。
- 回归测试 23/23 全绿。

### v1.17.0

- **母题库扩到 558 条**（3D 场景 317 / 平面海报 15 / 短提示词 226）。同一坐姿骨架的五条母题，背景全部换成**非王室场景**：
  - `k2x_clsc_seat_dawn` — 河岸晨光（FIRST LIGHT），户外：河堤混凝土防洪墩
  - `k2x_clsc_seat_ember` — 窗边余温（LAST EMBER），室内：老式公寓窗边木箱 + 落地灯
  - `k2x_clsc_seat_neon` — 后巷霓虹（NEON HOUR），夜景朋克：后巷配电箱 + 洋红霓虹管
  - `k2x_clsc_seat_snow` — 雪后站台（SILENT SNOW），户外：废弃站台石台 + 落雪
  - `k2x_clsc_seat_side` — 柱厅侧影（COLONNADE），**侧视 + 王座 + 王冠**，16:9 横屏，大理石柱廊与斜射长影
- **坐姿骨架（右踝搭左膝 / 一条鞋悬空 / 另一条鞋踏地 / 躯干直立 / 双手不举过锁骨）五条逐字一致**，只换承托物、光位、色彩与版式。
- **重写腿部描述 —— 这是本版最关键的一处**。旧写法 `hangs in the air with a visible gap of empty air beneath its sole, sole turned partly toward the camera`
  会被模型读成「把腿水平伸出去、鞋底朝镜头」，再叠加 `shin running diagonally across the planted shin` 直接导致两条小腿穿模。现在的写法是：
  - 右踝搭左膝，**全身只有这一个接触点**；
  - 抬起那条小腿**近乎垂直下垂**在另一条小腿旁，鞋底朝下、脚尖朝下；
  - 踏地那条腿在小腿**斜向前下方伸出**，鞋底平踏、且是唯一触地的那只；
  - 负面清单钉死 `no crossed shins / no shin passing horizontally / no sole turned toward the lens / no foot lifted above the knee`。
- **承托物必须「窄 + 高于膝」**：座面写成 `a full forearm above her knees`，且 `no wider than her hips`，两只膝都悬出前缘。
  台面又宽又矮时会退化成「坐在台边、腿垂在台前」，交叉腿直接消失（实测四张里挂三张）。
- **长礼服会吞腿**：动作段钉死「开衩 + 裙摆整体甩到身后 + 双腿从髋到脚全部外露」，负面加
  `no skirt across her lap / no fabric between her legs and the camera / no dress covering her knees`。
  服装段被单品替换后版型描述会丢，所以这几句只能放动作段。
- 机位统一 **22° 偏前**（正面会把裙摆铺满、腿看不见；侧 40° 以上模型倾向低头侧脸）。侧视那条单独用 25° + 16:9。
- 实跑验证（`Krea2-白垩光标准档.json`，角色 artoria_pendragon_(fate)，单品 `lib:fm_star_evening_black`
  = 黑晚礼服 + 黑星光点丝袜 + 黑高跟 + 肘手套 + 露背）：五条装配 `pct` 100、`issues` 空、五条服装单品全保留；
  出图四条竖屏姿势全部成立（踝-膝接触 + 一条鞋悬空 + 一条鞋踏地）。
- **已知限制**：模型对「交叉腿坐姿 + 正脸看镜头」有强先验，五条里四条成图是**微微低头、眼神上抬**；
  侧视那条脸会被头发遮住。要正脸就把机位再往正面压（但裙摆会回来盖腿），或改侧视构图。
- 回归测试 23/23 全绿，manifest 558 条 558 张缩略图。

### v1.15.5

- **修：选了角色官方服装，出图还是母题自带那套（用户反馈：甘雨 × 植物档案，穿成了白色吊带裙）**。
  根因不在装配，在这条角色预设本身：`ganyu_(genshin_impact)` 的 `default` 是 safebooru 词频统计的产物
  （`goat horns / black gloves / bow`），**一件衣服都没有**，按部位筛完是空 → 静默回落到随机版型句，
  而母题自带的 `spaghetti-strap camisole dress` 贴着角色、位置更靠前，于是白裙胜出。
  现在：
  - 空结果分两种日志 —— 「这套预设里一件真正的衣物都没有（列 tag）→ 需要修角色预设」
    与「服装库与母题部位没有交集」，不再一概而论；
  - **用户选了服装却筛不出单品时，不再追加随机版型句**（短提示 / 场景 / 海报三分支统一），
    免得两套衣服在同一段提示词里互相抢。
  - 甘雨预设按官方设定重写（白短旗袍叠黑露背连体衣 + 白袖套 + 黑长手套 + 黑裤袜 + 黑高跟）。
- **修：`cape` 被当成帽子，披风类角色整组服装丢失**。`zone_of_tag()` 用子串匹配，
  `"cap" in "cape"` 成立 → 披风判成配饰 → 该角色只剩 acc、没有上装。corrin / byleth / malenia /
  artoria(lancer) 等一批 Fire Emblem / 魂系角色都栽在这里（2434 人里 73 人「当前启用那套没有一件核心服装」）。
  - 长度 ≤3 的关键词改**词边界匹配**（长词仍走子串，保住 `sundress` / `belted` / `overshoes`）；
  - acc 不再抢占同一 tag 里的上装主体（`belted coat` / `suspenders jacket` → upper，`top hat` 仍归 acc）；
  - 补 11 个**早就在 `GARMENT_NOUNS` 里、却一直没进部位表**的词：
    `bodystocking / strapless / pajama / bikini / swimsuit`（dress）、`hood / collar / clothes / armor`（upper）、
    `veil / necktie`（acc）。
  - 修完 73 → 17 人，与变空 0 例、`run_all` 23/23。
- **修：短发角色被画成长发垂在窗台两侧（用户反馈：anis × 废弃花园，窗台左右各一束长发）**。
  母题正文写死的是原型角色的长发（`She has waist-length, long and silky very long hair…` /
  `Her long straight very long hair should descend over the windowsill…`），而**短提示分支没有发型处理**
  （它不像场景分支那样有独立发型段可整段替换，单段母题 `locate_sections()` 什么都定位不到）。
  新增 `drop_long_hair_sentences()`：只在 `hair_desc` 含 short/bob/cropped/pixie/buzz 的角色上生效，
  命中「含 hair 词 + 长度词或垂落动词」的句子就换成真实发型，配饰句（`hair ornament`）与
  身份句不动；场景分支仅在发型段没定位到时兜底（否则会误删 `HAIR_TPL`）。
  **553 个母题里 226 条短提示，其中 103 条正文写死长发** —— 2432 个角色里 525 人是短发。
- **修：母题把身材写死成平胸**。同批母题正文有 `a flat chest`、`a slim delicate figure`，
  约束句甚至写着 `Do not alter the … flat chest`，与角色的 `huge breasts` 正面冲突。
  新增 `strip_motif_body()`：正向描写 / 逗号枚举 / 约束句 / 负面句四种位置都摘，
  跳过身份句与非人物主语句（`Place the old greenhouse … slender rusted metal frame` 里的
  slender 是建筑不是身材）；摘空的句子整句丢。**不做「角色有没有身材词」的门槛** ——
  `build_entry` 的 identity 只装前几个标签，2432 人里仅 60 人带身材词，拿它当门槛等于没修。
- **新增：面板顶栏三个外链按钮** —— 使用教学（作者 B 站）、图片欣赏（母题作者 B 站）、GitHub 仓库。
- **数据：角色官方服装预设补写 27 人**（甘雨 + 26 个原本按部位筛不出任何衣物的角色）。
  官方设定类按原作逐项落地，皮肤类按 safebooru.org 高频服装统计（样本 1–100 张）落地，
  全部标记 `verified: false` 待真机验收，`note` 里记了依据与百分比。
- **数据：内置快照重打包** —— 角色预设 2447 → **2800 套**（2434 人）、服装库 113 套 / 10 类、缩略图 2444 张。
- 回归 23/23 全绿。

### v1.15.4

- **修：换角色后仍带初音特征（用户反馈：约 1/4 母题出图还有青绿色双马尾）**。
  母题库是围绕 Hatsune Miku 写的，装配只整段换掉「身份句 / 发型段 / 服装段 / 色盘段」，
  但正文里还有一批**角色特征锚点**，它们不是独立段，于是一路留到输出：
  - `the outer twin-tail ends` / `aqua twintails` —— 连字符和无空格写法，旧正则只认 `twin tails`；
  - `full body from boots to hair ornaments` —— 取景用「发饰」当身体上限；
  - `her face, eyes, hands and hair ornaments must stay readable` —— 可读性锚点；
  - `both aqua eyes clearly visible` —— 写死的 Miku 瞳色；
  - 护盾里的 `no duplicate Miku` / `no missing twin tails` —— 负面词反而召唤青绿双马尾；
  - `virtual-singer stillness` 与 tag 流里的 `virtual singer`。
  现在统一由 `neutralize_residual_traits()` 在装配末尾中性化（角色是 Miku 本人时原样跳过）。
- **修：短提示词母题不换角色特征**。`k2s_*` 这类 tag 流母题只做名字替换，正文
  `1girl, hatsune miku, ... teal eyes, virtual singer` 原样留下；名字替换还区分大小写，
  小写 tag 匹配不到。现在统一走同一套清洗，并把服装上的 `teal trim` 换成目标角色主色。
- **修：Miku 本人被误伤**。双马尾判定只认 `twin tail` 这一种写法，Anima 那套写
  `worn in twintails` → 认不出 → 把 Miku 的双马尾中性化成 `long hair strands`。
  换成 `has_twin_tail()` 覆盖所有写法。
- **新增：短提示词自动套角色官方服装**。`k2s_*` 这类 tag 流母题自带的是 Miku 的服装 tag
  （`detached sleeves` / `black thighhighs`）。换角色且没手选服装时，现在自动套该角色的
  **官方服装预设**（Anima `character_outfits` 的 `default`），并按 tag 粒度整组替换 ——
  逐条摘除会被 `swap_garments` 的 limit 截断，留下半套。同时补了
  `thighhigh / kneehigh / pantyhose / leggings` 等腿部名词（原先不在 `GARMENT_NOUNS` 里，
  换装后过膝袜一直留在提示词里）。手选单品仍然优先，不会被自动套用覆盖；
  场景 / 海报分支不套（服装段本来就由版型模板接管）。
- **画内文字跟着换角色名**：母题里印在画面上的 `HATSUNE MIKU` 标签会换成目标角色名，
  大小写风格跟随原文（全大写 → 全大写）；用户手填的「画面英文文字」不受影响。
- **修：`furina` 的护盾抄了 Miku 的否定项**（`no Miku, no aqua twin tails`），
  选她出图会主动召唤青绿双马尾。
- **修：Anima 桥接兜底色是 Miku 的**。认不出的瞳色一律兜到 `aqua`（缝线 / 轮廓全青绿），
  现在改为「认不出瞳色 → 用发色 → 再兜中性象牙白」。
- 回归 23 项（新增「换角色后不留原角色特征」「短提示自动套官方服装 + 画内文字换名」）。
- 联机验证（真实工作流 `Krea2-白垩光标准档.json`，8 步 turbo）：同一母题
  `k2x_veil_fall_a` 分别用 Miku / Cirno 出图 —— Miku 保留青绿双马尾，Cirno 出蓝发 + 冰翼 +
  蓝裙，无任何初音特征；`k2s_cx_023` 自动套蓝裙；手选「露肩针织 + 百褶裙」时按手选出图。
- 文档：新增[「作者与更新」](#作者与更新)一节（插件作者 B 站教学视频与更新进度、母题创作者主页），
  回归项数同步为 23；`presets/seeds_motifs.json` 的溯源路径改回相对路径，不再写入本机路径。

### v1.15.3

- **修：所有格形式的旧衣服**（`the coat's collar` / `her dress's hem`）。上一轮只处理
  `her coat`，带 `'s` 的漏了 —— 实测「废墟·地面光带」里 `One small wooden toggle at the
  coat's collar` 活下来，模型就给她加了一件外套。现在统一改成 `the outfit's`。
- 联机验证（真实工作流 `Krea2-白垩光标准档.json`，8 步 turbo，3:4 / 16:9）：
  影院门外 / 忧郁肖像 / 晨曦·暗调 三个点名母题全部换成所选晚礼服；
  随机抽 5 条（2 场景 + 2 短提示 + 1 海报）也全部生效。

### v1.15.2

- **修：影院门外 / 忧郁肖像 这类短提示词母题，换了服装也不生效**。三个具体问题：
  - 母题只写了 `coat collar pulled up` 这种**裸名词短语**（没有 her、没有动词）—— 之前被
    「必须提到她才处理」的规则挡住，外套领子一直留在提示词里，把所选上衣压掉了。
    现在裸名词短语不受该限制（成句的仍然要求提到她，避免误伤场景描述）。
  - **部位判定只看「母题提到哪些部位」**：影院门外只提了外套领子 → 判定为「只要上半身」
    → 整条裙子直接不写，出图自然看不到下装。现在改成**取景决定写哪些部位**（特写才只写上半身，
    其余默认写「上装 + 下装」），母题描述只用来补腿 / 鞋 / 配饰。
  - **全篇服装名替换的时机错了**：替换放在开头，新写进去的单品又被后面的句子处理当成
    「旧衣服」摘掉，成品里一件衣服都没有。现在放到最后执行，并加兜底：
    只要动过服装，成品里就必须出现所选单品。
- 全量 553 条 × 两套服装：断句 0、空清单 0、**每条都有服装句**；「只要上半身」从 34 条降到 25 条
  （多出来的是取景没有明确特写线索的母题，宁可多写一套下装也不丢裙子）。
- 回归测试 21 项。

### v1.15.1

- **修：换装后旧衣服还在（第三轮）**。之前的改写只认「整句列举服装」，实测还有三种写法漏掉：
  - **内联介词短语**：`standing on the grassy slope … at night in a yukata` —— 浴衣母题换了针织，
    出图还是浴衣。现在改成 `in the selected outfit`（`in front of her boots` 这类空间短语有
    白名单挡着，不会被误改）。
  - **所有格**：`the hem of her yukata` / `her wooden sandals` —— 按部位换成 `her outfit` /
    `her footwear` / `her top`。
  - **全篇反复点名**：`white top / dark skirt` 在 9 个段落里出现，只改服装段等于没改。
    现在从母题里提取「这身衣服的标准叫法」，全文统一换成所选单品（按部位配对）；
    袖口 / 下摆 / 领子这类部件词不参与整名替换。
- **服装名词表补漏**：`top` / `qipao` / `yukata` / `parka` / `blazer` / `sweatshirt` 之前不在表里 ——
  整条母题写 `white top` 也识别不出来。
- 全量 553 条 × 两套服装扫描：断句/空清单 0；旧服装残留从 19 条降到 13 条
  （剩下的是「衣架道具 / 四面反射各穿一套 / 伪身份段 / 部件细节」，有意保留）。
- 回归测试 21 项（新增「内联 / 所有格 / 全篇服装名」一项）。

### v1.15.0

- **按部位换装**：服装库和角色官方服装都按 `上装 / 下装 / 连衣裙 / 腿部 / 鞋子 / 配饰`
  六类拆分，**只写母题自己描述到的部位**。
  以前整套写入会把取景拉远：方形专辑是上半身特写，却写进了「百褶裙 + 乐福鞋」，
  模型就去补腿和脚；展纸母题写的是连衣裙、没写鞋，补了乐福鞋后构图变成坐窗台双腿垂下。
- **判定口径**：以母题正文的服装描述为准（写了哪些部位就换哪些）；母题完全没写服装时，
  退回取景线索（`close-up / upper chest` → 只上装，`full body / her feet` → 全套）。
- **空缺部位不写**：母题要鞋但这套没有鞋 → 该部位留空，不硬凑（角色官方服装同理）。
- **几条保护**：头饰（`top hat` / `beret`）永远保留——戴在头上、不进画面下方，且是识别度
  的一部分；只提到下装的母题会顺带补上装（否则上身留空）；`holding umbrella` / `sunny day`
  这类动作天气 tag 直接丢弃，`knitwear` / `long sleeves` 这类修饰词挂到主体上装。
- 效果：34 条母题判为「上半身」，519 条含下半身；全量 553 条 × 两套服装扫描，
  没有出现空清单或断句；回归测试 20 项。

### v1.14.1

- **修：海报 / 方形专辑母题换不掉服装**。除了「She wears …」这一类，实测还有三类写法
  会让旧衣服照样画出来，现在一并覆盖：
  - **衣服自己做主语**（`A dark navy coat hangs open over it.`）—— 同段已有服装清单就整句删掉；
  - **整句/整段都在讲服装**（海报 `Let the clothing behave like clothing: the ivory cardigan…`）
    —— 整句换成本次所选单品；
  - **tag 流里夹着的裸单品**（`sailor school uniform, pleated skirt, …`）—— 只摘掉那几个子句。
- **修：角色身份句里写死的原作服装**。`furina` 的 identity 写着
  `her recognizable … ceremonial outfit`、guard 钉着 `no missing top hat`，两句都比服装
  指令更硬 —— 所以选了露肩针织，出图还是全套 Fontaine 礼仪服 + 高帽。
  现在选单品时会自动剥掉身份句 / 护盾里的原作服装（手写角色可用
  `identity_plain` / `guard_plain` 精确指定；生成角色自动剥离 `detached sleeves` 这类签名）。
- **海报不再随机套版型**：指定单品 + 版型「自动」时直接按单品写平面服装段，
  不再随机抽「利落西装式 / 宫廷礼服」那套（抽中了会跟所选单品打架）。
- **修：母题自带硬换行导致身份句替换静默失败**（38 条母题带段内换行）。
  旧正则 `Preserve [^\n]*?\.` 跨不过换行，原文身份句原样留下 —— 那几条母题换角色等于没换，
  服装自然也换不掉。
- **保守化**：长篇巨构分支（scene）里 `scarf` / `cloak` / `cape` 常是画面主体而不是穿在身上的，
  只对「her dress is heavy cotton」这类材质指派下手，不做整句替换，避免把构图描述整段换掉。
- 已知保留（有意不改）：背景**衣架上的衣服 / 道具服装**、**四面反射各穿一套**这类设计项、
  以及伪身份段（`her identity must read at a glance: …`）里的服装列表 —— 后者交给身份锚点句压。
- 回归测试 19 项（新增「身份句 / 护盾 / 海报版型三处让位」）。

### v1.14.0

- **修：选了服装库服装，出图还是母题自带那套**。原先单品句是追加到**全文末尾**的，
  而母题正文里本来就写着「She wears a … spaghetti-strap dress」——贴着角色、位置更靠前，
  模型两套都读，结果偏母题那套（或干脆混成一件）。
  现在指定单品时**原地改写**母题自带的服装枚举：`She wears a … dress.` →
  `She wears only these garments: 露肩针织, 百褶裙, 乐福鞋.`，主语与动词沿用原文，
  语法不破、位置不变，服装仍然贴着角色。
- 覆盖到**三个分支**：短提示词（含 tag 流的 `wearing …`）、长篇场景（服装句常藏在
  **机位段**里，例如 `k2x_*` 系列）、平面海报。母题完全没写服装时，改成紧跟「身份锚点段」
  插入，而不是扔到末尾。
- 单品里混着的**姿势类 tag**（Anima 服装库里的 `crossed legs` 等）不再写进「她穿着…」，
  姿势交回母题；命中的 tag 会在自检报告里列出来。
- 所选单品里没有裙装时，正文残留的 `the dress` 统一改称 `the outfit`，避免两套衣服并存。
- 顺带修：短提示词分支选「保持母题原样」时会写出 `Render Miku in a keep with …` 这种病句，
  现在直接跳过版型句。
- 不选单品时输出与 v1.13.0 **逐字节一致**（19908 组参数组合比对零差异）。
- 回归测试 18 项（新增「服装库单品：就地覆盖母题自带服装」）。

### v1.13.0

- **场景画幅徽标可点**：③ 场景页的每张卡片上，画幅角标变成按钮，点一下 `竖 → 横 → 方 → 竖` 循环，
  同时切换当前工作流的画幅参数。原来只能看，现在能改。
- **画幅改到哪存哪**：改动写进独立覆盖层 `presets/user_motif_aspect.json`（在 `.gitignore` 里），
  优先级高于 `manifest.json` 的推荐值；删掉那一条就退回推荐值。构建脚本重跑不会覆盖你的改动。
- **母题库扩到 553 条**（3D 场景 312 / 平面海报 15 / 短提示词 226），比 v1.12.0 多 158 条，
  配套缩略图补齐。
- 回归测试 17 项（新增「画幅覆盖层读写」「徽标三态循环链」两项）。

### v1.12.0

- 首次开源发布。

## 署名与来源

- **本插件**：灵冻不冻 · [@lingdongbudong](https://github.com/lingdongbudong) · [B 站主页](https://space.bilibili.com/516891894)（插件使用教学视频与更新进度都在这里）。作者另有 [Comfyui-Anima-Wardrobe-V6](https://github.com/lingdongbudong) 与 Krea2-Portrait 系列。
- **母题库**：来自 **辞雪沐春** · [B 站主页](https://space.bilibili.com/1522948414/dynamic) 提供的参考素材 —— `k2-baieguang` / `k2-chenxiguang` 两个提示词集，以及一套 32 张「MIKU - 未来科幻风格」成品图，其内嵌提示词被拆段、重写并扩展成 553 条母题库。作者口头同意再分发，未指定具体许可文本；**若作者后续声明许可，以其声明为准**。
- **角色数据与立绘**：快照自 Comfyui-Anima-Wardrobe-V6。
- **角色与作品名称**：版权归各自权利人，本项目仅作描述性标识，不主张任何权利。

## 许可证

**[PolyForm Strict 1.0.0](LICENSE)** © 2026 灵冻不冻 · 本项目按「原样」提供，不附带任何担保。

- ❌ **禁止商业使用** —— 需事先取得作者书面许可。
- ❌ **禁止二次包装与再分发** —— 无论是否修改。
- ✅ 个人非商业使用、修改源码自用；保留完整署名前提下做非商业分享。
- **历史版本**（2026-11-24 之前）仍按 **AGPL-3.0** 授权，不因本次变更而撤回。

上游素材的授权状态（母题库来自「辞雪沐春」的口头同意再分发、角色数据快照自
[Comfyui-Anima-Wardrobe-V6](https://github.com/lingdongbudong/Comfyui-Anima-Wardrobe-V6)）
见 [NOTICE.md](NOTICE.md) —— 该文件不属于许可条款，仅作来源声明。

**如果你的使用场景无法接受本许可（例如需要商用或再分发），请先联系作者确认授权范围。**
