# -*- coding: utf-8 -*-
"""Comfyui-Anima-Wardrobe-V6 桥接层。

两个数据源，按 K2ED_ANIMA_SOURCE 决定顺序（auto / live / bundle）：

  · live   —— `<custom_nodes>/Comfyui-Anima-Wardrobe-V6/presets/`，随 Anima 更新
  · bundle —— 本插件自带的 `presets/anima/`（数据）+ `thumbs/anima/`（角色图）

`auto`（默认）= 有 Anima 用实时、没有就用内置。这样本机始终跟着 Anima 更新，
而整个插件目录单独拷走（没有 Anima）时角色页依然完整——分发包靠的就是这一点。

读取内容（数量随 Anima 增长，不写死）：
  · 角色库      anima_v4_characters.json（tags / hair / eyes / pop / thumb）
  · 角色服装预设 character_outfits.json（每角色 2 套原作服装，tag 式）
  · 服装库      outfit_library.json（11 类，tag 式 + level）
  · 角色图      thumbs/<thumb>.webp（均 9 KB）
  ⚠ 内置副本 `presets/anima/` 是**打包时快照**（角色 2432 / 图 2432 / 服装库 135 套），
    不跟 Anima 自动同步；要更新快照得重新打包，别指望它自己变。

⚠️ 数据是 **tag 体系**，K2 是长自然语言体系。这里只做两件事：
   ① 把 tags 组装成「身份锚点句」（够用，但不如手写精确）
   ② 把服装 tags 交给装配器作为「单品清单」叠加在版型段之后
"""
from __future__ import annotations

import json
import os

import folder_paths

HERE = os.path.dirname(os.path.abspath(__file__))
ANIMA_DIR_NAME = "Comfyui-Anima-Wardrobe-V6"

# 内置副本（随插件分发）
BUNDLE_DATA = os.path.join(HERE, "presets", "anima")
BUNDLE_THUMBS = os.path.join(HERE, "thumbs", "anima")
BUNDLE_MARK = os.path.join(BUNDLE_DATA, "_bundle.json")

# 本地手写角色的 id → Anima 官方 tag。手写版质量更高所以优先，
# 但服装预设、角色图这些还得回 Anima 那边按官方 tag 找。
ALIAS = {
    "miku": "hatsune_miku",
    "furina": "furina_(genshin_impact)",
}


def alias_key(key: str) -> str:
    return ALIAS.get(key, key)


def alias_targets() -> set[str]:
    return set(ALIAS.values())

_CACHE: dict[str, tuple[float, object]] = {}

COLOR_MAP = {
    "blue": "cobalt and deep ultramarine", "aqua": "aqua and icy cyan",
    "cyan": "aqua and icy cyan", "black": "graphite black and matte carbon",
    "brown": "umber brown and warm caramel", "blonde": "champagne gold and pale honey",
    "yellow": "champagne gold and pale honey", "red": "deep crimson and oxidized red",
    "silver": "mirror silver and pale platinum", "grey": "mirror silver and pale platinum",
    "gray": "mirror silver and pale platinum", "white": "pearl white and ivory",
    "pink": "dusty rose and pale pink", "purple": "deep violet and muted lavender",
    "violet": "deep violet and muted lavender", "green": "deep teal and moss green",
    "orange": "burnt orange and warm amber",
}
SHORT_COLOR = {
    "blue": "cobalt", "aqua": "aqua", "cyan": "aqua", "black": "graphite",
    "brown": "umber", "blonde": "champagne", "yellow": "champagne", "red": "crimson",
    "silver": "platinum", "grey": "platinum", "gray": "platinum", "white": "ivory",
    "pink": "rose", "purple": "violet", "violet": "violet", "green": "teal",
    "orange": "amber",
}
WORK_LABEL = {
    "genshin impact": "Genshin Impact", "honkai: star rail": "Honkai: Star Rail",
    "blue archive": "Blue Archive", "arknights": "Arknights", "fate": "Fate",
    "azur lane": "Azur Lane", "wuthering waves": "Wuthering Waves",
    "zenless zone zero": "Zenless Zone Zero", "touhou": "Touhou Project",
    "vocaloid": "Vocaloid", "kantai collection": "Kantai Collection",
    "hololive": "hololive", "idolmaster": "The Idolmaster", "umamusume": "Uma Musume",
}
DROP = {"1girl", "1boy", "solo", "female", "male", "multiple girls", "2girls",
        "large breasts", "medium breasts", "small breasts", "cleavage", "flat chest",
        "thighs", "bare legs", "barefoot", "bare shoulders", "collarbone", "navel",
        "midriff", "stomach"}
LENGTH_TAGS = ["absurdly long hair", "very long hair", "medium hair", "long hair",
               "short hair", "bob cut", "hime cut", "hair up"]
STYLE_TAGS = ["twintails", "twin braids", "single braid", "side ponytail", "ponytail",
              "drills", "side up", "one side up"]
PRIORITY = ["horn", "ear", "hat", "halo", "wing", "crown", "mask", "veil", "ornament",
            "bow", "ribbon", "tail", "armor", "scarf", "headpiece", "hairband"]


def prefer() -> str:
    """auto（默认）/ live（只认实时）/ bundle（只认内置，用于验证分发效果）。"""
    v = (os.environ.get("K2ED_ANIMA_SOURCE") or "auto").strip().lower()
    return v if v in ("auto", "live", "bundle") else "auto"


def live_dir() -> str | None:
    """Anima 插件在不在场；在场返回它的 presets 目录。"""
    try:
        for base in folder_paths.get_folder_paths("custom_nodes"):
            p = os.path.join(base, ANIMA_DIR_NAME, "presets")
            if os.path.isdir(p):
                return p
    except Exception:
        pass
    p = os.path.join(os.path.dirname(HERE), ANIMA_DIR_NAME, "presets")
    return p if os.path.isdir(p) else None


def sources() -> list[tuple[str, str]]:
    """按优先级返回 [(kind, data_dir)]，kind = live / bundle。"""
    live = live_dir()
    bundle = BUNDLE_DATA if os.path.isdir(BUNDLE_DATA) else None
    mode = prefer()
    if mode == "live":
        cand = [("live", live)]
    elif mode == "bundle":
        cand = [("bundle", bundle)]
    else:
        cand = [("live", live), ("bundle", bundle)]
    return [(k, p) for k, p in cand if p and os.path.isdir(p)]


def presets_dir() -> str | None:
    """当前生效的数据目录（兼容旧调用）。"""
    src = sources()
    return src[0][1] if src else None


def available() -> bool:
    return bool(sources())


def _bundle_meta() -> dict:
    try:
        with open(BUNDLE_MARK, encoding="utf-8") as fh:
            return json.load(fh) or {}
    except Exception:
        return {}


_THUMB_COUNT_CACHE: dict = {}


def _bundle_thumb_count() -> int:
    """listdir 2432 个文件约 5ms，而 /manifest 每次都要 → 按目录指纹缓存。"""
    if not os.path.isdir(BUNDLE_THUMBS):
        return 0
    key = _stamp(BUNDLE_THUMBS)
    hit = _THUMB_COUNT_CACHE.get("v")
    if hit and hit[0] == key:
        return hit[1]
    n = sum(1 for f in os.listdir(BUNDLE_THUMBS) if f.endswith(".webp"))
    _THUMB_COUNT_CACHE["v"] = (key, n)
    return n


def status() -> dict:
    """给面板显示用：内置/实时各在不在、当前用的是谁、角色数。"""
    src = sources()
    meta = _bundle_meta()
    return {
        "prefer": prefer(),
        "live": bool(live_dir()),
        "bundle": os.path.isdir(BUNDLE_DATA),
        "source": src[0][0] if src else "none",
        "chars": len(index()) if src else 0,
        "thumbs": _bundle_thumb_count(),
        "built_at": meta.get("built_at", ""),
    }


_THUMB_DIRS_CACHE: dict = {}


def _thumb_dirs() -> list[str]:
    """角色图目录：跟着数据源走，再互相兜底（实时新加的角色在内置里必然还没有）。

    每张缩略图请求都会走这里（一屏 72 张 = 72 次），按「数据源 + 目录在不在」缓存。
    """
    key = (prefer(), os.path.isdir(BUNDLE_THUMBS), bool(live_dir()))
    hit = _THUMB_DIRS_CACHE.get("v")
    if hit and hit[0] == key:
        return hit[1]
    out: list[str] = []
    for kind, d in sources():
        p = os.path.join(d, "thumbs") if kind == "live" else BUNDLE_THUMBS
        if os.path.isdir(p) and p not in out:
            out.append(p)
    for p in (BUNDLE_THUMBS, os.path.join(live_dir() or "", "thumbs")):
        if p and os.path.isdir(p) and p not in out:
            out.append(p)
    _THUMB_DIRS_CACHE["v"] = (key, out)
    return out


def _stamp(path: str) -> tuple:
    try:
        st = os.stat(path)
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return (0, 0)


def _load(name: str):
    """按指纹缓存：Anima 那边改了数据，这边不用重启也能读到。"""
    for _kind, d in sources():
        path = os.path.join(d, name)
        if not os.path.isfile(path):
            continue
        try:
            mt = _stamp(path)
        except OSError:
            continue
        hit = _CACHE.get(path)
        if hit and hit[0] == mt:
            return hit[1]
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            continue
        _CACHE[path] = (mt, data)
        return data
    return None


def _work_label(slug: str) -> str:
    return WORK_LABEL.get(slug, " ".join(w.capitalize() for w in (slug or "").split()))


def work_zh(en: str) -> str:
    return _works_zh().get((en or "").strip().lower(), _work_label(en))


def _pick_tags(tags: list[str]):
    ts = [t for t in tags if t not in DROP]
    eyes = next((t for t in ts if t.endswith(" eyes") and not t.startswith("hair")), "")
    length = next((t for t in LENGTH_TAGS if t in ts), "")
    style = next((t for t in STYLE_TAGS if t in ts), "")
    colors = []
    for t in ts:
        if t.endswith(" hair") and t not in LENGTH_TAGS:
            c = t[:-5].strip()
            if c and c != "hair" and c not in colors:
                colors.append(c)
    color = colors[0] if colors else ""
    length_core = length[:-5].strip() if length.endswith(" hair") else length
    hair = " ".join(x for x in (length_core, color, "hair") if x) or "hair"
    if style:
        hair += f" worn in {style}"

    used = {eyes, style, "hair between eyes"} | set(LENGTH_TAGS) | {f"{c} hair" for c in colors}
    raw = [t for t in ts if t not in used and not t.endswith(" eyes")]
    sig: list[str] = []
    for t in raw:
        words = set(t.split())
        if any(words < set(o.split()) for o in raw if o != t):
            continue
        if t not in sig:
            sig.append(t)
    one = ""
    for p in PRIORITY:
        one = next((t for t in sig if p in t), "")
        if one:
            break
    return (eyes or "expressive eyes"), hair, (one or (sig[0] if sig else "silhouette")), sig


def build_entry(rec: dict) -> dict:
    """Anima 角色记录 → K2 角色插槽（五段全部不含母题名词）。"""
    raw_name = rec.get("name") or rec.get("tag", "")
    import re
    raw_name = re.sub(r"\s*\([^)]*\)\s*$", "", raw_name).strip()
    name = " ".join(w.capitalize() for w in raw_name.split()) or rec.get("tag", "")
    short = name.split()[0] if name else rec.get("tag", "").title()
    eyes, hair, sig_one, sig = _pick_tags(rec.get("tags") or [])
    sig_txt = ", ".join(sig[:4]) if sig else "her signature silhouette"
    hair_c = (rec.get("hair") or "white").lower()
    eye_c = (rec.get("eyes") or hair_c).lower()
    wl = _work_label(rec.get("work", ""))
    # ⚠ 兜底色不能是 aqua/cobalt —— 那是 Miku 的配色。认不出的瞳色曾经一律兜到 aqua，
    #    于是任意角色都被写上「aqua 缝线 / aqua 轮廓」，出图一片青绿（用户报的残留色）。
    accent = SHORT_COLOR.get(eye_c) or SHORT_COLOR.get(hair_c, "ivory")
    block = SHORT_COLOR.get(hair_c, "graphite")

    return {
        "name": name,
        "feature_clause": f"featuring {name} from {wl} as the only physical character",
        "short": short,
        "identity": (
            f"Preserve {short}’s unmistakable canonical identity: {eyes}, {hair}, {sig_txt}, "
            f"youthful anime facial structure, and a clearly recognizable {short} silhouette. "
            f"Keep her face, eyes, hands and {sig_one} immediately readable even inside this "
            f"dense structure."
        ),
        "hair_desc": hair,
        "design_language": f"her {wl} design language",
        "accent": accent,
        "palette": [
            ["pearl white, pure white and pale silver", 62],
            [COLOR_MAP.get(hair_c, "pearl white and pale silver"), 14],
            [COLOR_MAP.get(eye_c) or COLOR_MAP.get(hair_c, "pearl white and pale silver"), 10],
            ["graphite black and matte carbon", 6],
            ["mirror silver and glass contrast", 5],
            ["champagne gold", 2],
            [f"a single vivid {block} registration accent", 1],
        ],
        "ink": block, "block": block, "stain": accent,
        "metal": "champagne-gold", "minor": accent,
        "guard": f"no duplicate {short}, no generic anime girl, no missing {sig_one}",
        "work": wl, "zh": rec.get("zh", ""), "pop": rec.get("pop", 0),
        "thumb_anima": rec.get("thumb", ""), "generated": True, "source": "anima",
    }


def _by_tag() -> dict[str, dict]:
    d = _load("anima_v4_characters.json") or {}
    out = {}
    for rec in d.get("characters") or []:
        if rec.get("tag"):
            out[rec["tag"]] = rec
    return out


def char_entry(key: str) -> dict | None:
    rec = _by_tag().get(key)
    return build_entry(rec) if rec else None


def _works_zh() -> dict[str, str]:
    """en slug（小写）→ 中文名。Anima 的作品表自带 zh，直接用。"""
    d = _load("anima_v4_characters.json") or {}
    out = {}
    for w in d.get("works") or []:
        en = (w.get("en") or "").strip().lower()
        if en:
            out[en] = w.get("zh") or w.get("en") or en
    return out


_INDEX_CACHE: dict = {}


def index() -> list[dict]:
    """全量角色索引（轻量，给分页用）。

    2432 行 dict + 排序约 12.8ms，而 /chars 每请求要查两次（_merged_chars + works），
    原先等于每次翻页重建两遍。按数据文件指纹缓存，返回的 dict 只读（不许原地改）。
    """
    key = tuple((k, d, _stamp(os.path.join(d, "anima_v4_characters.json")))
                for k, d in sources())
    hit = _INDEX_CACHE.get("v")
    if hit and hit[0] == key:
        return hit[1]
    zh_of = _works_zh()
    rows = []
    for rec in (_load("anima_v4_characters.json") or {}).get("characters") or []:
        if not rec.get("tag"):
            continue
        work_en = rec.get("work", "") or ""
        rows.append({
            "id": rec["tag"],
            "zh": rec.get("zh") or rec.get("name", ""),
            "work": _work_label(work_en),
            "work_en": work_en,
            "work_zh": zh_of.get(work_en.lower(), _work_label(work_en)),
            "thumb": f"anima/{rec['thumb']}.webp" if rec.get("thumb") else "",
            "accent": (SHORT_COLOR.get((rec.get("eyes") or "").lower())
                       or SHORT_COLOR.get((rec.get("hair") or "").lower(), "ivory")),
            "pop": rec.get("pop", 0),
        })
    rows.sort(key=lambda r: -r["pop"])
    _INDEX_CACHE["v"] = (key, rows)
    return rows


def works() -> list[dict]:
    """作品列表（en / zh / 人数），按人物数排序。"""
    from collections import Counter
    cnt = Counter(r["work_en"] for r in index())
    zh_of = _works_zh()
    out = [{"en": en, "zh": zh_of.get(en.lower(), _work_label(en)), "count": n}
           for en, n in cnt.items() if en]
    out.sort(key=lambda w: -w["count"])
    return out


def outfit_library() -> list[dict]:
    d = _load("outfit_library.json") or {}
    return [{"id": o["id"], "zh": o.get("zh", o["id"]), "cat": o.get("cat", ""),
             "tags": o.get("tags") or [], "level": o.get("level", 0),
             "note": o.get("note", "")} for o in (d.get("outfits") or [])]


def outfit_categories() -> list[dict]:
    d = _load("outfit_library.json") or {}
    return [{"id": c["id"], "zh": c["zh"]} for c in
            ((d.get("_meta") or {}).get("categories") or [])]


def char_outfits(key: str) -> list[dict]:
    d = _load("character_outfits.json") or {}
    rec = (d.get("outfits") or {}).get(alias_key(key)) or {}
    return [{"id": o.get("id", ""), "zh": o.get("zh", ""),
             "tags": o.get("tags") or [], "level": o.get("level", 0),
             "note": o.get("note", ""), "verified": bool(o.get("verified"))}
            for o in (rec.get("list") or [])]


def outfit_tags(kind: str, oid: str, char_key: str = "") -> list[str]:
    """kind = 'char'（角色专属预设）| 'lib'（服装库单品）"""
    if kind == "char":
        for o in char_outfits(char_key):
            if o["id"] == oid:
                return o["tags"]
        return []
    for o in outfit_library():
        if o["id"] == oid:
            return o["tags"]
    return []


def thumb_path(name: str) -> str | None:
    if not name:
        return None
    base = os.path.basename(name)
    for d in _thumb_dirs():
        p = os.path.join(d, base)
        if os.path.isfile(p):
            return p
    return None
