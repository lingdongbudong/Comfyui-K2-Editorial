# -*- coding: utf-8 -*-
"""生成面板数据层 presets/manifest.json（P2 面板的纯数据）。

包含三块：
  characters —— 角色（id / 中文名 / 作品 / 角色图路径）
  costumes   —— 每个角色可选的服装条目
  motifs     —— 母题（id / 标题 / 预览图 / 词数），预览图从 MIKU 成品图压成 480px webp

为什么不直接引用 MIKU 原图：单张 5–8MB，32 张 200MB，面板里用不起。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys

from PIL import Image

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import assembler as A  # noqa: E402  —— 画内文字提取器以装配器为单一真源
SEEDS = os.path.join(HERE, "presets", "seeds_motifs.json")
SEEDS_EXTRA = os.path.join(HERE, "presets", "seeds_extra.json")
CHARS = os.path.join(HERE, "presets", "characters.json")
COSTUMES = os.path.join(HERE, "presets", "costumes.json")
NAMES_ZH = os.path.join(HERE, "presets", "motif_names_zh.json")
ASPECTS = os.path.join(HERE, "presets", "motif_aspects.json")
TRANSLATIONS = os.path.join(HERE, "presets", "title_translations.json")
GLOSSARY = os.path.join(HERE, "presets", "title_glossary.json")
GENRES = os.path.join(HERE, "presets", "motif_genres.json")
ADDED = os.path.join(HERE, "presets", "motif_added.json")
REF = os.path.join(HERE, "presets", "motif_ref.json")


def gloss_translate(title: str, gloss: dict, stop: set[str]) -> str:
    """未登记短语的逐词直译；有一个词认不出就返回空（不硬翻）。"""
    if not title or not re.search(r"[A-Za-z]", title):
        return ""                       # 日文 / 中文标题不直译
    out = []
    for w in re.findall(r"[A-Za-z]+|\d+(?::\d+)?", title):
        u = w.upper()
        if u in stop:
            continue
        if u in gloss:
            out.append(gloss[u])
        elif w[:1].isdigit():
            out.append(w)               # 编号 / 时间照抄
        else:
            return ""
    return "".join(out) if out else ""


def aspect_of(raw: str) -> str:
    """从首句判推荐画幅：wide/16:9 → landscape；tall/vertical/2:3 → portrait。
    判不出来就 both（通用）。覆盖写在 motif_aspects.json 里。"""
    head = raw[:90]
    m = re.search(r"(\d+)\s*:\s*(\d+)", head)
    portrait = bool(re.search(r"\bvertical\b|\btall\b", head, re.I))
    landscape = bool(re.search(r"\bwide\b|\bhorizontal\b", head, re.I))
    if m:
        w, h = int(m.group(1)), int(m.group(2))
        if h > w:
            return "portrait"
        if w > h and landscape:
            return "landscape"
    if portrait:
        return "portrait"
    if landscape:
        return "landscape"
    return "both"
OUT = os.path.join(HERE, "presets", "manifest.json")
def _thumb_v(path: str) -> int:
    """缩略图版本号（文件 mtime 秒）。

    ComfyUI 静态服务对 .webp 返回 `Cache-Control: public, max-age=86400`，
    而缩略图路径是固定的 —— 换图后浏览器 24 小时内仍会拿旧图（看起来像「没更新」）。
    前端把它拼成 `...?v=<mtime>`，只有文件真变了 URL 才变。
    """
    try:
        return int(os.path.getmtime(path))
    except OSError:
        return 0


MOTIF_THUMBS = os.path.join(HERE, "thumbs", "motifs")
THUMB_W = 480


def ratio_of(raw: str) -> str:
    """从母题首句抠出真实比例（`Create a wide 16:9 …` / `tall 2:3` / `square 1:1`）。

    手写母题（motifs_new/*.txt）不带 ratio 字段，以前 manifest 里一律是空的，
    面板就只能显示画幅徽章、显示不出比例。这里补上，跑图脚本也可以少探一次。
    """
    # 白名单：只认常见画幅，避免 "2.35:1" 被截成 "35:1"、或正文里的时间/编号误命中
    COMMON = ("16:9", "9:16", "4:5", "5:4", "3:4", "4:3", "2:3", "3:2",
              "1:1", "21:9", "2.35:1")
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*[:：]\s*(\d+(?:\.\d+)?)", raw[:160]):
        r = f"{m.group(1)}:{m.group(2)}"
        if r in COMMON:
            return r
    return ""


TAG_RULES = {
    # ⚠️ 不能收裸 `lift`：装配后的每条母题都有 "Lift Miku's extremely long twin
    # tails" 这句服装/发型指令，会把全库判成室内（实测室内从 121 掉到 40 多）。
    # ⚠️ 也不能收 `interior`：材质段固定写 "its interior holding fine inclusions"，
    # 那是水晶内部，不是室内。
    "interior": r"\b(room|bedroom|studio|apartment|library|lounge|corridor|elevator|"
                r"lift shaft|indoor|"
                r"shop|store|cafe|kiosk|bakery|barber|laundrette|hall|carriage|platform|"
                r"underpass|alley|tunnel|shelter)\b",
    # ⚠️ 不收 `field`：印刷段有 "the field's own marker"（指画面），服装段有
    # "field archer"，会把外景判断带偏。
    "exterior": r"\b(outdoor|open air|sky|horizon|shore|lake|river|cliff|forest|meadow|"
                r"street|rooftop|pier|quay|deck|snowfield|desert|mountain|summit|valley)\b",
    "night": r"\b(night|midnight|nocturnal|moonlit|lamplit|twilight|dusk|blue hour|neon|"
             r"lantern|star|aurora)\b",
    "day": r"\b(morning|daylight|noon|midday|afternoon|sunlit|sunlight|dawn|first light)\b",
    # ⚠️ 不收 `stone`：墙面材质句 "damp stone with a wet tide line" 会命中室内外景。
    "nature": r"\b(forest|lake|river|cliff|canyon|meadow|shore|beach|sea|ocean|wheat|"
              r"tree|grove|moss|fern|petal|blossom|ginkgo|cave|snow|tidal|rock|pine)\b",
    "street": r"\b(street|alley|lane|market|sidewalk|pavement|overpass|footbridge|parkade|"
              r"bus stop|kiosk|shopfront|neon|traffic|car park|underpass)\b",
    # ⚠️ 不收 `beam`：灯光段 "one thin beam of light" 不是梁。
    "architecture": r"\b(brick|concrete|timber|column|facade|lintel|arch|window|shutter|"
                    r"scaffold|masonry|parapet|pier deck)\b",
    # 魔法：只认明确语汇。⚠️ 不收裸 `circle` / `ring`（地板圆形、光圈太多）；
    # ⚠️ 也不收 `spell` / `spell\w*`：海报母题里到处是 "spelled correctly"（拼写正确）。
    "magic": r"\b(magic circle|arcane|conjur\w*|summon\w*|incantation|sorcery|"
             r"witchcraft|sigil|enchant\w*)\b",
    "season": r"\b(spring|summer|autumn|winter|snowfall|first snow|blossom|petal|ginkgo|"
              r"harvest|midsummer|late autumn)\b",
    # 兵器：只认实体兵装与握持动作用词。⚠️ 不收 staff —— 库里大量「staff of light」
    # 指的是光柱，会在抽象巨构母题里造出一堆假兵器条目。
    "weapon": r"\b(sword|blade|katana|longsword|greatsword|spear|lance|halberd|glaive|axe|"
              r"scythe|dagger|knife|mace|flail|bow|arrow|crossbow|rifle|pistol|firearm|"
              r"gauntlet|shield|weapon|wielding|quillon|crossguard|pommel|haft)\b",
}
GENRE_ZH = {"daily": "日常", "urban": "城市", "nature": "自然", "landscape": "风景",
            "hall": "宏大厅堂", "fantasy": "奇幻", "shop": "店铺", "industrial": "工业",
            "other": "其他"}
# 风格系列：顺序即面板分组平铺的先后（先原典、再专题、最后杂项）。
SERIES = os.path.join(HERE, "presets", "motif_series.json")
SERIES_ZH = [
    ("origin", "白垩原典"), ("cx", "晨曦海报"), ("hy", "黑曜暗调"), ("v6", "V6 场景"),
    ("indus", "工业构造"), ("circle", "圆环几何"), ("clsc", "经典人物"),
    ("ref", "人物参考图"),
    ("scene_misc", "场景合集"), ("short_misc", "短提示杂项"), ("poster", "平面海报"),
]
TAG_ZH = {"interior": "室内", "exterior": "室外", "night": "夜间", "day": "白昼",
          "nature": "自然", "street": "街道", "architecture": "建筑", "season": "季节",
          "weapon": "兵器", "magic": "魔法",
          # 姿势类：只标真正坐姿的母题（k2x_clsc_seat_* / throne），站姿的不标
          "sitting": "坐姿"}


def tags_of(raw: str) -> list[str]:
    """按正文关键词打场景标签。室内优先于室外（同一条不会两个都打）。

    ⚠️ 只扫**内容段**，必须剔除负向段。负向段通篇是「不要什么」
    （`no neon glow, no crowd, no window ...`），一旦参与判定，全库都会被打成
    夜间 / 街道（2026-11-11 实测：夜间 124 条、街道 80 条，绝大多数是假阳性）。
    """
    paras = [p for p in raw.split("\n\n") if p.strip()]
    content = [p for p in paras if not p.lstrip().lower().startswith("no ")]
    if len(content) >= 3:
        content = content[:-1]          # 收束段（The final image should feel like…）
    low = "\n\n".join(content).lower()
    got = [k for k, pat in TAG_RULES.items() if re.search(pat, low)]
    if "interior" in got and "exterior" in got:
        got.remove("exterior")
    # 兵器要看**密度**：低频命中多半是「a blade of grass」「a bow of light」这类比喻。
    # 实测真兵器场景最少 15 次，误判条目最高 4 次，取 8 做分界。
    if "weapon" in got and len(re.findall(TAG_RULES["weapon"], low)) < 8:
        got.remove("weapon")
    return got


def main() -> int:
    seeds = json.load(open(SEEDS, encoding="utf-8"))["seeds"]
    if os.path.exists(SEEDS_EXTRA):
        seeds = seeds + json.load(open(SEEDS_EXTRA, encoding="utf-8")).get("seeds", [])
    chars = json.load(open(CHARS, encoding="utf-8"))["characters"]
    cos = json.load(open(COSTUMES, encoding="utf-8"))
    tpls = cos.get("templates") or []
    char_def = cos.get("character_default") or {}
    names_zh = json.load(open(NAMES_ZH, encoding="utf-8")).get("names", {}) \
        if os.path.exists(NAMES_ZH) else {}
    asp_override = json.load(open(ASPECTS, encoding="utf-8")).get("aspects", {}) \
        if os.path.exists(ASPECTS) else {}
    trans = json.load(open(TRANSLATIONS, encoding="utf-8")).get("titles", {}) \
        if os.path.exists(TRANSLATIONS) else {}
    gl = json.load(open(GLOSSARY, encoding="utf-8")) if os.path.exists(GLOSSARY) else {}
    gloss, stop = gl.get("gloss", {}), set(gl.get("stop", []))

    os.makedirs(MOTIF_THUMBS, exist_ok=True)
    motifs, missing = [], 0
    # 手工标签覆盖（可选）：{"k2x_rain_mart": ["night", "street"]}
    tags_override = {}
    tagp = os.path.join(HERE, "presets", "motif_tags.json")
    if os.path.exists(tagp):
        try:
            raw_tags = json.load(open(tagp, encoding="utf-8"))
            tags_override = {k: v for k, v in raw_tags.items()
                             if not k.startswith("_") and isinstance(v, list)}
        except Exception as exc:
            print(f"  !! motif_tags.json 读取失败：{exc}")

    # 题材第二维度 + 新增标记
    genre_of = {}
    if os.path.exists(GENRES):
        raw_g = json.load(open(GENRES, encoding="utf-8"))
        genre_of = {k: v for k, v in raw_g.items() if not k.startswith("_")}
    series_of = {}
    if os.path.exists(SERIES):
        raw_s = json.load(open(SERIES, encoding="utf-8"))
        series_of = {k: v for k, v in raw_s.items() if not k.startswith("_")}
    added_of = {}
    if os.path.exists(ADDED):
        raw_a = json.load(open(ADDED, encoding="utf-8"))
        added_of = {k: v for k, v in raw_a.items() if not k.startswith("_")}
    # 人物参考图模式（front = 正面全身照 / sheet = 四视图全身照），面板据此出筛选 chip
    ref_of = {}
    if os.path.exists(REF):
        raw_r = json.load(open(REF, encoding="utf-8"))
        ref_of = {k: v for k, v in raw_r.items() if not k.startswith("_")}

    for s in seeds:
        dst = os.path.join(MOTIF_THUMBS, f"{s['id']}.webp")
        if not os.path.exists(dst) and str(s.get("file", "")).lower().endswith(
                (".png", ".jpg", ".jpeg", ".webp")):
            try:
                im = Image.open(s["file"]).convert("RGB")
                im.thumbnail((THUMB_W, THUMB_W), Image.LANCZOS)
                im.save(dst, "WEBP", quality=82, method=4)
            except Exception as exc:                      # 单张坏了不该拖垮整批
                print("  预览图失败", s["id"], exc)
                missing += 1
        # 海报分支自带画幅（16:9 / 4:5 / 1:1）；旧 _meta 里还有 "3:4" 这种比例串，先归一
        declared = ""
        raw_asp = (s.get("aspect") or "").strip().lower()
        if raw_asp in ("landscape", "portrait", "both", "square"):
            declared = raw_asp
        elif re.match(r"^\d+:\d+$", raw_asp):
            rw, rh = (int(x) for x in raw_asp.split(":"))
            declared = "portrait" if rh > rw else ("landscape" if rw > rh else "square")
        asp = asp_override.get(s["id"]) or declared or aspect_of(s["raw"])
        branch = ("poster" if s.get("branch") == "poster" else
                  "short" if s.get("branch") == "short" else "scene")
        bzh = {"poster": "平面海报", "short": "短提示词", "scene": "3D 场景"}[branch]
        # 母题正文里真正「要画进画面」的文字（不是 title 字段，短提示词多为
        # the exact title “X” / large English words “X” 这类写法，title 是空的）
        disp_all = A.find_display_text(s["raw"])
        disp_orig = (s.get("title") or "").strip() or (disp_all[0] if disp_all else "")
        motifs.append({
            "id": s["id"],
            "title": s["title"] or "",      # 无英文标题的母题留空，面板不必显示内部 id
            "zh": names_zh.get(s["id"], ""),
            "title_zh": (trans.get((s["title"] or "").strip(), "")
                         or trans.get(disp_orig, "")
                         or gloss_translate(disp_orig, gloss, stop)),
            "display_orig": disp_orig,
            "display_all": disp_all[:8],
            "aspect": asp,
            "aspect_zh": {"landscape": "横屏", "portrait": "竖屏",
                          "both": "通用", "square": "方屏"}[asp],
            # ⚠️ 首句优先：seeds 里的 ratio 字段与正文有 18 处不一致（旧的 short 母题
            # 一律标 2:3，正文其实是 9:16），字段只作兜底。
            "ratio": ratio_of(s["raw"]) or (s.get("ratio") or "").strip(),
            "tags": tags_override.get(s["id"]) or tags_of(s["raw"]),
            "branch": branch,
            "branch_zh": bzh,
            "workflow": s.get("workflow") or (
                "Krea2-白垩光标准档.json" if branch == "scene" else ""),
            "words": s["words"],
            "paras": s["paras"],
            "thumb": f"thumbs/motifs/{s['id']}.webp" if os.path.exists(dst) else "",
            "thumb_v": _thumb_v(dst),
            "character": s["character"],
            # 母题显式登记的推荐角色（角色库 key），供面板选母题时自动带出。
            # 与参考图那批描述性 character 文本分开，避免把 "Hatsune Miku" 当成 key。
            "recommend_char": s.get("recommend_char") or "",
            # 母题自带的角色装饰归属（如甘雨的水晶翼）：装配时只有这个角色保留，换人就摘掉。
            "owner_char": s.get("owner_char") or "",
            # 题材第二维度（daily/urban/nature/landscape/hall/fantasy/shop/industrial）
            "genre": genre_of.get(s["id"], ""),
            # 风格系列（面板默认按它分组平铺）
            "series": series_of.get(s["id"], ""),
            # 新增标记：入库批次日期，面板据此显示 NEW 角标与「只看新增」
            "added": added_of.get(s["id"], ""),
            # 人物参考图模式：front = 正面全身 / sheet = 四视图；空 = 普通母题
            "ref": ref_of.get(s["id"], ""),
        })


    man = {
        "_meta": {
            "note": "面板数据层。thumbs/ 与 presets/ 同级；路径相对插件根目录。",
            "counts": {"characters": len(chars), "motifs": len(motifs),
                       "costumes": len(tpls)},
        },
        "tags": [{"key": k, "zh": zh,
                  "count": sum(1 for m in motifs if k in m["tags"])}
                 for k, zh in TAG_ZH.items()
                 if any(k in m["tags"] for m in motifs)],
        "genres": [{"key": k, "zh": zh,
                    "count": sum(1 for m in motifs if m.get("genre") == k)}
                   for k, zh in GENRE_ZH.items()
                   if any(m.get("genre") == k for m in motifs)],
        "series": [{"key": k, "zh": zh,
                    "count": sum(1 for m in motifs if m.get("series") == k)}
                   for k, zh in SERIES_ZH
                   if any(m.get("series") == k for m in motifs)],
        "added_count": sum(1 for m in motifs if m.get("added")),
        "characters": [
            {
                "id": k,
                "name": v.get("short", k),
                "full_name": v["name"],
                "zh": v.get("zh", ""),
                "work": v.get("work", ""),
                "thumb": f"thumbs/{v['thumb']}.webp" if v.get("thumb") else "",
                "thumb_v": (_thumb_v(os.path.join(HERE, "thumbs", f"{v['thumb']}.webp"))
                            if v.get("thumb") else 0),
                "curated": bool(v.get("curated") or not v.get("generated")),
                "pop": v.get("pop", 0),
                "accent": v.get("accent", "aqua"),
                "costume_default": char_def.get(k, []),
            }
            for k, v in chars.items()
        ],
        "costume_templates": [
            {"id": t["id"], "zh": t["zh"], "desc": t.get("desc", "")}
            for t in tpls
        ],
        "motifs": motifs,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(man, fh, ensure_ascii=False, indent=1)

    with_thumb = sum(1 for m in motifs if m["thumb"])
    print(f"manifest -> {OUT}")
    print(f"  角色 {len(chars)}（有图 {sum(1 for c in man['characters'] if c['thumb'])}）"
          f" / 母题 {len(motifs)}（有图 {with_thumb}）"
          f" / 服装 {man['_meta']['counts']['costumes']} 套")
    if missing:
        print(f"  ⚠ {missing} 张预览图生成失败")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
