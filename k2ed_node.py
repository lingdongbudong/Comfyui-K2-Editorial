# -*- coding: utf-8 -*-
"""K2 长文出题节点（白垩光·未来奢华编辑主视觉）。

设计要点
--------
* **面板是唯一入口**：角色 / 母题 / 画幅 / 服装 / 单品 五个控件在 JS 里折叠隐藏，
  只在设置面板里选（"同一个设置只留一个入口"）。隐藏不影响序列化。
* **角色走字符串而不是下拉**：角色库接的是 Anima 的 2432 条，
  做成 combo 会让 /object_info 膨胀几百 KB，且每次 Anima 加角色都要重启。
* **可选控件一律放 optional 末尾**：老 API 工作流不带这些键也能跑。
* **IS_CHANGED**：勾了「每次重随机」返回 NaN 强制重跑（否则随机永远不动）。
* 状态全部来自节点输入，没有全局态。
"""
from __future__ import annotations

import json
import os
import random
import tempfile

from . import anima_bridge as B
from . import assembler as A

HERE = os.path.dirname(os.path.abspath(__file__))


def _code_stamp():
    """本插件 py 文件的 mtime 指纹。放进 IS_CHANGED 后，改代码即自动失效旧输出缓存
    （否则同 seed 同输入会复用改动前生成的图，看起来像「改了没生效」）。"""
    t = 0.0
    for f in ("k2ed_node.py", "assembler.py", "anima_bridge.py"):
        try:
            t = max(t, os.path.getmtime(os.path.join(HERE, f)))
        except OSError:
            pass
    return round(t, 3)
THUMBS = os.path.join(HERE, "thumbs")
SEEDS_FILE = os.path.join(HERE, "presets", "seeds_motifs.json")
SEEDS_EXTRA_FILE = os.path.join(HERE, "presets", "seeds_extra.json")
CHARS_FILE = os.path.join(HERE, "presets", "characters.json")
COSTUMES_FILE = os.path.join(HERE, "presets", "costumes.json")
MANIFEST = os.path.join(HERE, "presets", "manifest.json")
FAVS_FILE = os.path.join(HERE, "presets", "user_favs.json")
LOCK_FILE = os.path.join(HERE, "presets", "user_char_outfit.json")
POOLS_FILE = os.path.join(HERE, "presets", "user_random_pools.json")
# 场景默认画幅的用户覆盖层：卡片上点「竖/横/方」徽标写这里。
# ⚠️ 绝不写进 manifest.json —— 那是 build 产物，重跑一次就把用户改的盖回推荐值。
MOTIF_ASPECT_FILE = os.path.join(HERE, "presets", "user_motif_aspect.json")

NODE_NAME = "K2EditorialBuilder"
ASPECTS = ["16:9", "3:2", "4:3", "1:1", "4:5", "3:4", "2:3", "9:16"]
AUTO = "自动（跟随母题）"
KEEP = "保持母题原样"

# 随机池：模式走节点输入（可复现、能进工作流），勾选的大列表走服务端文件
RAND_OFF = "关闭"
CHAR_POOLS = [RAND_OFF, "收藏角色", "指定作品"]
MOTIF_POOLS = [RAND_OFF, "收藏场景", "勾选场景"]


_JSON_CACHE: dict = {}


def _load_json(path: str, default):
    """按 (mtime_ns, size) 缓存。

    热路径三处：`motif_zh()` 每次读 240KB manifest、`seed_choices()` 读 3.7MB 母题、
    `INPUT_TYPES` 每轮 object_info 都要用。返回对象**只读**；要改的调用点自己 dict() 拷一层。
    """
    try:
        st = os.stat(path)
        key = (st.st_mtime_ns, st.st_size)
    except OSError:
        return default
    hit = _JSON_CACHE.get(path)
    if hit and hit[0] == key:
        return hit[1]
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return default
    _JSON_CACHE[path] = (key, data)
    return data


def _write_json(path: str, obj) -> None:
    """临时文件 + os.replace 的原子写。

    收藏 / 勾选池 / 角色服装锁定都是用户态数据，原来直接 open(path,"w")，
    写到一半被杀（或断电）就留下半截 JSON，下次读取静默回落成空、用户数据全丢。
    """
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".k2ed_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=1)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def seed_choices() -> list[str]:
    ids = [s["id"] for s in _load_json(SEEDS_FILE, {}).get("seeds", [])]
    ids += [s["id"] for s in _load_json(SEEDS_EXTRA_FILE, {}).get("seeds", [])]
    return ids or ["ComfyUI_temp_zmmyf_00012_"]


def costume_ids() -> list[str]:
    d = _load_json(COSTUMES_FILE, {})
    return [t["id"] for t in (d.get("templates") or [])]


def resolve_char(key: str):
    """本地手写/缓存优先，找不到再去 Anima 全量库现算。"""
    local = _load_json(CHARS_FILE, {}).get("characters", {})
    if key in local:
        return local[key]
    return B.char_entry(key)


# ---------------------------------------------------------------------------
# 随机池
# ---------------------------------------------------------------------------
def _file_stamp(path: str) -> tuple:
    """mtime + size 指纹，进 IS_CHANGED 用。收藏/勾选改了要能触发重跑。"""
    try:
        st = os.stat(path)
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return (0, 0)


def _favs_all() -> dict:
    d = _load_json(FAVS_FILE, {}) or {}
    return {k: list(d.get(k) or [])
            for k in ("characters", "costumes", "motifs", "works")}


def pool_state() -> dict:
    """勾选的场景 id 存这里（收藏之外唯一的大列表；不塞节点输入是因为可能几百条）。"""
    d = _load_json(POOLS_FILE, {}) or {}
    out = {"motif": [x for x in (d.get("motif") or []) if isinstance(x, str)]}
    out["last"] = d.get("last") or {}
    return out


def save_pool_state(data: dict) -> None:
    try:
        _write_json(POOLS_FILE, {"motif": data.get("motif") or [],
                                 "last": data.get("last") or {}})
    except Exception as exc:
        print(f"[K2-Editorial] 随机池写入失败：{exc}")


# 卡片徽标的三态循环：竖 → 横 → 方（「通用」点一下先进竖屏，之后进入循环）
MOTIF_ASPECT_CYCLE = ("portrait", "landscape", "square")
MOTIF_ASPECT_ZH = {"portrait": "竖屏", "landscape": "横屏",
                   "both": "通用", "square": "方屏"}


def motif_aspect_user() -> dict:
    """用户改过的场景默认画幅：{母题 id: portrait|landscape|square}。

    独立于 manifest.json 保存，优先级更高；删掉一条就恢复推荐值。
    """
    d = _load_json(MOTIF_ASPECT_FILE, {}) or {}
    a = d.get("aspects")
    return dict(a) if isinstance(a, dict) else {}


def save_motif_aspect(mid: str, aspect: str) -> dict:
    """写一条覆盖值。aspect 传 "both" 表示删掉这条、回到 manifest 的推荐值。"""
    cur = motif_aspect_user()
    if aspect == "both":
        cur.pop(mid, None)
    else:
        cur[mid] = aspect
    _write_json(MOTIF_ASPECT_FILE, {
        "_meta": {"note": "场景卡片上「竖/横/方」徽标点出来的用户覆盖层，"
                          "优先级高于 manifest.json 的 aspect。删掉本条即恢复推荐值。",
                  "values": MOTIF_ASPECT_ZH},
        "aspects": cur,
    })
    return cur


def merge_motif_aspect(man: dict) -> dict:
    """把用户覆盖值合进 manifest 的 motifs，就地返回同一个 dict。

    ⚠️ 命中的母题必须 dict(m, ...) 新建：`_load_json` 返回的是缓存对象，
    直接 m["aspect"] = ... 会把覆盖值永久写进缓存，之后删掉用户覆盖也回不去。
    """
    ov = motif_aspect_user()
    if ov:
        man["motifs"] = [(dict(m, aspect=ov[m["id"]]))
                         if isinstance(m, dict) and m.get("id") in ov else m
                         for m in (man.get("motifs") or [])]
    man["aspect_overrides"] = len(ov)
    return man


_ID_CACHE: dict = {}


def char_index() -> list[dict]:
    """B.index() 每次会重建 2400+ 行，抽取一次要查两次，这里按数据文件 mtime 缓存。"""
    stamp = []
    for kind, d in B.sources():
        p = os.path.join(d, "anima_v4_characters.json")
        if os.path.isfile(p):
            stamp.append((kind, _file_stamp(p)))
    key = tuple(stamp)
    hit = _ID_CACHE.get("index")
    if hit and hit[0] == key:
        return hit[1]
    rows = B.index()
    _ID_CACHE["index"] = (key, rows)
    return rows


def all_char_ids() -> list[str]:
    """全库角色（手写 + Anima，排掉被手写占了槽的官方 tag，避免同一角色占两份概率）。"""
    ids = list((_load_json(CHARS_FILE, {}).get("characters") or {}).keys())
    seen = set(ids) | set(B.alias_targets())
    for r in char_index():
        if r["id"] not in seen:
            ids.append(r["id"])
            seen.add(r["id"])
    return ids


def char_pool(mode: str, work: str = "") -> tuple[list[str], str]:
    """返回 (候选 id 列表, 说明)。空池一律回退全库并给出警告文案。"""
    mode = (mode or RAND_OFF).strip()
    if mode == RAND_OFF:
        return [], ""
    if mode == "指定作品":
        w = (work or "").strip().lower()
        if w:
            ids = [r["id"] for r in char_index()
                   if (r.get("work_en") or "").lower() == w]
            if ids:
                return ids, f"作品 {w}（{len(ids)} 人）"
        return all_char_ids(), f"⚠ 作品「{w or '未指定'}」无角色，回退全库"
    valid = set(all_char_ids())
    fav = [i for i in _favs_all()["characters"] if i in valid]
    if fav:
        return fav, f"收藏角色（{len(fav)} 人）"
    return all_char_ids(), "⚠ 收藏角色为空，回退全库"


def motif_pool(mode: str) -> tuple[list[str], str]:
    mode = (mode or RAND_OFF).strip()
    if mode == RAND_OFF:
        return [], ""
    valid = seed_choices()
    vset = set(valid)
    if mode == "收藏场景":
        ids = [i for i in _favs_all()["motifs"] if i in vset]
        if ids:
            return ids, f"收藏场景（{len(ids)} 条）"
        return valid, "⚠ 收藏场景为空，回退全库"
    ids = [i for i in pool_state()["motif"] if i in vset]
    if ids:
        return ids, f"勾选场景（{len(ids)} 条）"
    return valid, "⚠ 勾选场景为空，回退全库"


def motif_zh(mid: str) -> str:
    man = _load_json(MANIFEST, {})
    for m in man.get("motifs") or []:
        if m.get("id") == mid:
            return m.get("zh") or m.get("title") or mid
    return mid


class K2EditorialBuilder:
    @classmethod
    def INPUT_TYPES(cls):
        # seed_choices() 要读 862KB + 2.8MB 两本母题库；原来在同一个 dict 里
        # 调了两次（列表 + 默认值）→ object_info 每次多解一遍 3.7MB。
        seed_list = seed_choices()
        return {
            "required": {
                "随机种子": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFF}),
                "每次重随机": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "角色": ("STRING", {"default": "miku"}),
                "母题": (list(seed_list), {"default": seed_list[0]}),
                "画幅": (ASPECTS, {"default": "16:9"}),
                "服装": ([AUTO, KEEP] + costume_ids(), {"default": AUTO}),
                "单品": ("STRING", {"default": ""}),
                "覆盖提示词": ("STRING", {"default": "", "multiline": True}),
                "画面英文文字": ("STRING", {"default": ""}),
                "画面不显示英文": ("BOOLEAN", {"default": False}),
                "画面文字模式": (["全部替换", "只留主标题"], {"default": "全部替换"}),
                # —— 随机池：必须放 optional 末尾，老工作流不带这些键也能跑 ——
                "角色随机池": (CHAR_POOLS, {"default": RAND_OFF}),
                "角色随机作品": ("STRING", {"default": ""}),
                "场景随机池": (MOTIF_POOLS, {"default": RAND_OFF}),
            },
            "hidden": {
                # ComfyUI 的 SaveImage 会把这份 prompt 原样 json.dumps 进 PNG 元数据。
                # 长文走 1290 中继时 string_b 只是个 link，正文不会进元数据；
                # 这里在运行时把成品写回快照，任何 SaveImage/PreviewImage 都能带上。
                "prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO",
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("提示词", "自检报告", "元数据")
    FUNCTION = "generate"
    CATEGORY = "Krea2/提示词"
    DESCRIPTION = "白垩光长文自动装配：角色 / 版型 / 单品 / 场景 / 画幅 → 1500–2700 词长提示词"

    @classmethod
    def IS_CHANGED(cls, 每次重随机=True, **kw):
        if 每次重随机:
            return float("nan")
        return (kw.get("随机种子"), kw.get("角色"), kw.get("母题"), kw.get("画幅"),
                kw.get("服装"), kw.get("单品"), kw.get("覆盖提示词"),
                kw.get("画面英文文字"), kw.get("画面不显示英文"),
                kw.get("画面文字模式"),
                kw.get("角色随机池"), kw.get("角色随机作品"), kw.get("场景随机池"),
                # 收藏/勾选变了，随机结果也会变，必须打进来，否则固定种子会复用到旧图
                _file_stamp(FAVS_FILE), _file_stamp(POOLS_FILE),
                # 母题库/版型改过 → 同 id 的正文已经不同，固定种子下也必须重跑
                _file_stamp(SEEDS_FILE), _file_stamp(SEEDS_EXTRA_FILE),
                _file_stamp(COSTUMES_FILE),
                _code_stamp())

    def generate(self, 随机种子, 每次重随机, 角色="miku", 母题="", 画幅="16:9",
                 服装=AUTO, 单品="", 覆盖提示词="", 画面英文文字="",
                 画面不显示英文=False, 画面文字模式="全部替换",
                 角色随机池=RAND_OFF, 角色随机作品="", 场景随机池=RAND_OFF,
                 prompt=None, extra_pnginfo=None, unique_id=None):
        ch = None
        picked = {"角色": "", "场景": "", "角色说明": "", "场景说明": ""}
        if 覆盖提示词.strip():
            text = 覆盖提示词.strip()
            log = ["使用「覆盖提示词」，跳过装配与随机抽取"]
        else:
            # 生成种子也走独立实例：`random.Random()` 用系统熵自播种，不消耗全局随机流。
            # 这样整个 generate() 对全局 random 零污染 —— 下游节点拿到的是原本该有的序列。
            seed = (random.Random().randint(0, 0xFFFFFFFF) if 每次重随机
                    else int(随机种子))
            # 只在本节点的抽取期间播种，用完立刻复原全局状态。
            # 否则同一工作流里下游的随机节点（Anima 抽场景、其他 random 节点）
            # 会被这里的种子钉住 —— 表现为「改了种子，下游画面纹丝不动」。
            _rand_state = random.getstate()
            random.seed(seed)
            try:
                # ---- 随机池：必须在 random.seed 之后抽，固定种子才可复现 ------
                # 每次重随机=True 时 seed 本来就变 → 每轮换人；False 时同 seed 同池同结果。
                if (角色随机池 or RAND_OFF) != RAND_OFF:
                    pool, why = char_pool(角色随机池, 角色随机作品)
                    if pool:
                        角色 = random.choice(pool)
                        picked["角色"], picked["角色说明"] = 角色, why
                if (场景随机池 or RAND_OFF) != RAND_OFF:
                    pool, why = motif_pool(场景随机池)
                    if pool:
                        母题 = random.choice(pool)
                        picked["场景"], picked["场景说明"] = 母题, why

                costume = "auto" if 服装 == AUTO else ("keep" if 服装 == KEEP else 服装)

                tags: list[str] = []
                if 单品.startswith("char:"):
                    tags = B.outfit_tags("char", 单品[5:], 角色)
                elif 单品.startswith("lib:"):
                    tags = B.outfit_tags("lib", 单品[4:])

                try:
                    ch = resolve_char(角色)
                    if ch is None:
                        raise ValueError(f"角色不存在：{角色}")
                    text, log = A.assemble(母题, 角色, 画幅, costume,
                                           char_obj=ch, outfit_tags=tags,
                                           display_text=画面英文文字,
                                           no_text=bool(画面不显示英文),
                                           display_mode=("title"
                                                         if 画面文字模式 == "只留主标题"
                                                         else "all"))
                except Exception as exc:          # 不让装配异常吞掉整张图
                    text, log = "", [f"!! 装配失败: {exc}"]
            finally:
                random.setstate(_rand_state)      # 复原：下游节点拿回原本的随机流
        text = text.strip()

        # ---- 把成品长文写进 PNG 元数据 ----------------------------------
        # SaveImage 的 hidden("prompt") 就是 dynprompt.get_original_prompt()，
        # 与这里拿到的是同一个字典对象；执行结束后它被 json.dumps 进 PNG 的 prompt 字段。
        # extra_pnginfo 同理，额外生成一个独立的 "k2ed_prompt" 文本块，方便直接读。
        # ⚠️ 绝不能往 prompt 顶层加键：execution.py 结束后会遍历顶层键当节点，
        #    _is_intermediate_output() 对每个键取 ["class_type"]，遇到字符串就
        #    TypeError → worker 线程死掉 → 图已存盘但队列永远不结束（表现为"卡住"）。
        #    因此只挂在「本节点字典内部」与 extra_pnginfo，两者都会随 SaveImage 序列化。
        try:
            if isinstance(prompt, dict) and unique_id is not None:
                own = prompt.get(str(unique_id))
                if isinstance(own, dict):
                    own["k2ed_prompt"] = text
                    own.setdefault("inputs", {})["k2ed_提示词"] = text
            if isinstance(extra_pnginfo, dict):
                extra_pnginfo["k2ed_prompt"] = text
        except Exception as exc:               # 元数据写失败不能影响出图
            print(f"[K2-Editorial] 元数据写入跳过：{exc}")

        rep = A.validate(text, None if 角色 == "keep" else 角色,
                         A.seed_branch(母题), A.seed_character(母题))
        # 装配异常（角色/母题不存在等）时 log 里是 ["!! 装配失败: ..."]。
        # 这段必须放到报告首行：否则用户只看到「篇幅 0 词 / 段落偏少」，
        # 完全不知道为什么失败（原因原先只藏在第三个输出 meta 里）。
        fail = next((x for x in log if x.startswith("!!")), "")
        bits = []
        if picked["角色"]:
            bits.append(f"角色 {(ch or {}).get('zh') or picked['角色']}"
                        f"〔{picked['角色说明']}〕")
        if picked["场景"]:
            bits.append(f"场景 {motif_zh(picked['场景'])}〔{picked['场景说明']}〕")
        pick_line = ("抽中：" + " ｜ ".join(bits)) if bits else ""
        report = ((fail + "\n") if fail else "")
        report += (f"篇幅 {rep['words']} 词 / {rep['paras']} 段 / 色盘 {rep.get('pct_sum')}"
                   + (f"\n{pick_line}" if pick_line else "")
                   + ("".join("\n⚠ " + i for i in rep["issues"]) if rep["issues"] else "\n✓ 校验通过"))
        meta = json.dumps({
            "角色": 角色, "母题": 母题, "画幅": 画幅, "服装": 服装, "单品": 单品,
            "画面英文文字": 画面英文文字, "画面不显示英文": bool(画面不显示英文),
            "词数": rep["words"], "段数": rep["paras"], "种子": 随机种子, "装配": log,
            "抽中": picked,
        }, ensure_ascii=False)

        return {
            "ui": {"k2ed_text": [text], "k2ed_report": [report],
                   "k2ed_picked": [json.dumps(
                       {"char": picked["角色"], "char_zh": (ch or {}).get("zh") or "",
                        "motif": picked["场景"], "motif_zh": motif_zh(picked["场景"])
                        if picked["场景"] else "",
                        "char_why": picked["角色说明"], "motif_why": picked["场景说明"]},
                       ensure_ascii=False)] if bits else [""]},
            "result": (text, report, meta),
        }


# ----------------------------------------------------------------------------
# HTTP 路由
# ----------------------------------------------------------------------------
ROUTE = "/k2ed"


def register_routes() -> None:
    try:
        from aiohttp import web
        from server import PromptServer
        routes = PromptServer.instance.routes
    except Exception as exc:      # 独立脚本里 import 本包时没有 PromptServer 实例
        print(f"[K2-Editorial] 跳过路由注册（{exc}）")
        return

    def _merged_chars() -> list[dict]:
        """本地（手写优先）在前，Anima 全量在后，按 id 去重。"""
        local = _load_json(CHARS_FILE, {}).get("characters", {})
        rows = []
        for k, v in local.items():
            wen = v.get("work", "")
            rows.append({
                "id": k, "zh": v.get("zh") or v.get("short", k),
                "work": wen, "work_en": wen, "work_zh": B.work_zh(wen) or wen,
                "thumb": f"thumbs/{v['thumb']}.webp" if v.get("thumb") else "",
                "accent": v.get("accent", "aqua"), "pop": v.get("pop", 0),
                "local": True,
            })
        seen = {r["id"] for r in rows}
        # 手写角色占了 miku / furina 两个槽位，Anima 里对应的官方 tag 要排掉，否则重复出现
        skip = B.alias_targets()
        rows += [r for r in B.index() if r["id"] not in seen and r["id"] not in skip]
        return rows

    # 前端传的是复数（characters/costumes/motifs/works），旧脚本传单数 —— 两种都收
    FAV_KINDS = {"character": "characters", "characters": "characters",
                 "costume": "costumes", "costumes": "costumes",
                 "motif": "motifs", "motifs": "motifs",
                 "work": "works", "works": "works"}

    def _favs_all() -> dict:
        d = _load_json(FAVS_FILE, {}) or {}
        return {v: list(d.get(v) or []) for v in FAV_KINDS.values()}

    def _save_favs_all(data: dict) -> None:
        try:
            _write_json(FAVS_FILE, {k: data.get(k, []) for k in FAV_KINDS.values()})
        except Exception as exc:
            print(f"[K2-Editorial] 收藏写入失败：{exc}")

    @routes.get(ROUTE + "/favs")
    async def _favs_get(request):
        return web.json_response(_favs_all())

    @routes.post(ROUTE + "/favs")
    async def _favs_post(request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        body = body or {}
        kind = body.get("kind", "character")
        cid = body.get("id", "")
        if kind not in FAV_KINDS or not cid:
            raise web.HTTPBadRequest(text="bad kind or missing id")
        bucket = FAV_KINDS[kind]
        data = _favs_all()
        ids = data[bucket]
        on = bool(body.get("on"))
        if on and cid not in ids:
            ids.insert(0, cid)
        elif not on and cid in ids:
            ids.remove(cid)
        data[bucket] = ids
        _save_favs_all(data)
        return web.json_response(data)

    @routes.get(ROUTE + "/pick")
    async def _pick_get(request):
        st = pool_state()
        return web.json_response({"motif": st["motif"], "count": len(st["motif"]),
                                  "last": st.get("last") or {}})

    @routes.post(ROUTE + "/pick")
    async def _pick_post(request):
        """勾选场景池。增量（add/remove）而不是整体覆盖 —— 可能几百条，省带宽。"""
        try:
            body = await request.json()
        except Exception:
            body = {}
        body = body or {}
        st = pool_state()
        ids = list(st["motif"])
        if body.get("clear"):
            ids = []
        if isinstance(body.get("set"), list):
            ids = [x for x in body["set"] if isinstance(x, str)]
        for x in (body.get("add") or []):
            if isinstance(x, str) and x not in ids:
                ids.append(x)
        rm = {x for x in (body.get("remove") or []) if isinstance(x, str)}
        if rm:
            ids = [x for x in ids if x not in rm]
        st["motif"] = ids
        save_pool_state(st)
        return web.json_response({"motif": ids, "count": len(ids)})

    @routes.get(ROUTE + "/charoutfit")
    async def _lock_get(request):
        return web.json_response({"locks": _load_json(LOCK_FILE, {}) or {}})

    @routes.post(ROUTE + "/charoutfit")
    async def _lock_post(request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        body = body or {}
        char = (body.get("char") or "").strip()
        oid = (body.get("id") or "").strip()
        if not char:
            raise web.HTTPBadRequest(text="missing char")
        locks = dict(_load_json(LOCK_FILE, {}) or {})
        if oid:
            locks[char] = oid
        else:
            locks.pop(char, None)
        try:
            _write_json(LOCK_FILE, locks)
        except Exception as exc:
            print(f"[K2-Editorial] 角色服装锁定写入失败：{exc}")
        return web.json_response({"locks": locks})

    @routes.get(ROUTE + "/chars")
    async def _chars(request):
        q = (request.query.get("q") or "").strip().lower()
        work = (request.query.get("work") or "").strip()
        offset = max(0, int(request.query.get("offset", 0) or 0))
        limit = min(200, max(1, int(request.query.get("limit", 72) or 72)))
        rows = _merged_chars()
        fav_chars = _favs_all()["characters"]
        if q:
            rows = [r for r in rows if q in (r["zh"] + r["id"] + r["work_en"] + r["work_zh"]).lower()]
        if work == "__fav__":
            fav = set(fav_chars)
            rows = [r for r in rows if r["id"] in fav]
        elif work:
            rows = [r for r in rows if r["work_en"].lower() == work.lower()]
        return web.json_response({
            "total": len(rows), "offset": offset,
            "items": rows[offset:offset + limit],
            "works": B.works(),
            "fav": fav_chars,
            "anima": B.available(),
        })

    @routes.get(ROUTE + "/char")
    async def _char(request):
        key = (request.query.get("id") or "").strip()
        if not key:
            raise web.HTTPBadRequest(text="missing id")
        for r in _merged_chars():
            if r["id"] == key:
                return web.json_response(r)
        raise web.HTTPNotFound()

    @routes.get(ROUTE + "/outfits")
    async def _outfits(request):
        key = request.query.get("char", "")
        return web.json_response({
            "character": B.char_outfits(key) if key else [],
            "library": B.outfit_library(),
            "categories": B.outfit_categories(),
        })

    @routes.get(ROUTE + "/manifest")
    async def _manifest(request):
        # _load_json 现在带缓存：这里必须拷一层再补字段，否则会把 aspects/anima 等
        # 运行期字段写进缓存对象，越积越多（manifest 文件更新后才换新对象）。
        man = dict(_load_json(MANIFEST, {"motifs": [], "costume_templates": []}))
        if "costume_templates" not in man:
            cos = _load_json(os.path.join(HERE, "presets", "costumes.json"), {})
            man["costume_templates"] = [{"id": t["id"], "zh": t["zh"],
                                         "desc": t.get("desc", "")}
                                        for t in (cos.get("templates") or [])]
        man["aspects"] = ASPECTS
        man["auto"] = AUTO
        man["keep"] = KEEP
        man["anima"] = B.available()
        man["anima_status"] = B.status()
        # 用户点徽标改过的默认画幅合流进来（覆盖层优先级高于 manifest 的 aspect）
        merge_motif_aspect(man)
        return web.json_response(man)

    @routes.get(ROUTE + "/motif/aspect")
    async def _masp_get(request):
        ov = motif_aspect_user()
        return web.json_response({"aspects": ov, "count": len(ov)})

    @routes.post(ROUTE + "/motif/aspect")
    async def _masp_post(request):
        """场景默认画幅：卡片徽标点一下改一条。

        值域 portrait / landscape / square；传 both 表示删掉覆盖、回推荐值。
        """
        try:
            body = await request.json()
        except Exception:
            body = {}
        body = body or {}
        mid = str(body.get("id") or "").strip()
        asp = str(body.get("aspect") or "").strip().lower()
        if not mid or len(mid) > 96:
            raise web.HTTPBadRequest(text="missing or bad motif id")
        if asp not in MOTIF_ASPECT_CYCLE and asp != "both":
            raise web.HTTPBadRequest(
                text="aspect must be one of " + str(list(MOTIF_ASPECT_CYCLE) + ["both"]))
        try:
            cur = save_motif_aspect(mid, asp)
        except Exception as exc:
            raise web.HTTPInternalServerError(text=f"write failed: {exc}")
        # 回给前端的是**生效值**：删覆盖时要报 manifest 里的推荐值，否则徽标会停在「通用」
        if asp == "both":
            eff = "landscape"
            for m in (_load_json(MANIFEST, {}).get("motifs") or []):
                if isinstance(m, dict) and m.get("id") == mid:
                    eff = m.get("aspect") or "landscape"
                    break
        else:
            eff = asp
        return web.json_response({"ok": True, "id": mid, "aspect": eff,
                                  "count": len(cur)})

    @routes.get(ROUTE + "/thumb/{tail:.*}")
    async def _thumb(request):
        tail = request.match_info.get("tail", "").replace("\\", "/").lstrip("/")
        if tail.startswith("anima/"):
            path = B.thumb_path(tail[len("anima/"):])
        else:
            # 用 realpath + commonpath 判越界：字符串前缀比较挡不住
            # 软链接（目录里放个指到外面的链接就能读任意文件）。
            path = os.path.realpath(os.path.join(HERE, tail))
            base = os.path.realpath(THUMBS)
            try:
                inside = os.path.commonpath([path, base]) == base
            except ValueError:            # 不同盘符
                inside = False
            if not inside:
                path = None
        if not path or not os.path.isfile(path):
            raise web.HTTPNotFound()
        resp = web.FileResponse(path)
        resp.content_type = "image/webp"
        resp.headers["Cache-Control"] = "public, max-age=86400"
        return resp

    @routes.get(ROUTE + "/build")
    async def _build(request):
        q = request.query
        motif = q.get("motif", "")
        char = q.get("char", "miku")
        aspect = q.get("aspect", "16:9")
        costume = q.get("costume", "auto")
        costume = "auto" if costume == AUTO else ("keep" if costume == KEEP else costume)
        item = q.get("item", "")
        display = q.get("display", "")
        no_text = q.get("notext", "").lower() in ("1", "true", "yes")
        mode = "title" if q.get("mode", "").lower() in ("title", "title_only") else "all"
        tags: list[str] = []
        if item.startswith("char:"):
            tags = B.outfit_tags("char", item[5:], char)
        elif item.startswith("lib:"):
            tags = B.outfit_tags("lib", item[4:])
        try:
            ch = resolve_char(char)
            if ch is None:
                raise ValueError(f"角色不存在：{char}")
            text, log = A.assemble(motif, char, aspect, costume,
                                   char_obj=ch, outfit_tags=tags,
                                   display_text=display, no_text=no_text,
                                   display_mode=mode)
            rep = A.validate(text, None if char == "keep" else char,
                             A.seed_branch(motif), A.seed_character(motif))
            return web.json_response({
                "ok": True, "text": text, "log": log, "outfit_tags": tags,
                "words": rep["words"], "paras": rep["paras"],
                "pct": rep.get("pct_sum"), "issues": rep["issues"],
            })
        except Exception as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)
