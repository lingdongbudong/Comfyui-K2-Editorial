# -*- coding: utf-8 -*-
"""P0 装配器：母题整块 + 三个替换位（角色 / 画幅 / 服装轻替换）。

设计原则（P0 验证用）：
  * 母题不拆碎 —— 参考图里「母题 → 材料 → 序列 → 支撑」是一体设计，
    拆成可随机组合的池会立刻互相打脸（skill 自列的首号失败模式）。
  * 角色库五段全部不含母题名词，才能跨母题复用。
  * 每个替换动作可单独开关，方便 A/B 定位是哪个动作掉了画质。

用法:
    python assembler.py --list
    python assembler.py --seed "GRAIN SANCTUM" --char furina --aspect 16:9 --out out/x.txt
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re

HERE = os.path.dirname(os.path.abspath(__file__))
SEEDS = os.path.join(HERE, "presets", "seeds_motifs.json")
SEEDS_EXTRA = os.path.join(HERE, "presets", "seeds_extra.json")
CHARS = os.path.join(HERE, "presets", "characters.json")
COSTUMES = os.path.join(HERE, "presets", "costumes.json")

# 服装可用材质（排除玻璃：玻璃衣服不合理）。装配时按母题正文词频挑前 2 种，
# 让服装与巨构同材质体系 —— 这是「角色 × 母题特化」的低成本实现。
MAT_VOCAB = [
    ("membrane", "translucent membrane", "struct"),
    ("vellum", "vellum", "struct"),
    ("acrylic", "frosted acrylic", "struct"),
    ("carbon", "matte carbon", "struct"),
    ("silver", "mirrored silver", "metal"),
    ("gold", "champagne-gold filigree", "metal"),
    ("ceramic", "pearl-white ceramic", "struct"),
    ("lacquer", "black lacquer", "struct"),
    ("brass", "oxidized brass", "metal"),
    ("chrome", "polished chrome", "metal"),
    ("porcelain", "porcelain", "struct"),
    ("crystal", "crystal", "struct"),
]
MAT_FALLBACK = ["brushed metal", "matte composite"]

NUM = {
    20: "twenty", 30: "thirty", 40: "forty", 50: "fifty", 60: "sixty",
    70: "seventy", 80: "eighty", 90: "ninety",
}
ONES = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]


def num2words(n: int) -> str:
    if n < 10:
        return ONES[n]
    if n < 20:
        return {10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen",
                15: "fifteen", 16: "sixteen", 17: "seventeen", 18: "eighteen",
                19: "nineteen"}[n]
    tens, ones = divmod(n, 10)
    base = NUM[tens * 10]
    return base if ones == 0 else f"{base}-{ONES[ones]}"


ASPECT_INFO = {
    "16:9": {"word": "wide", "char_pct": 30, "motif_pct": 72},
    "3:2": {"word": "wide", "char_pct": 32, "motif_pct": 70},
    "4:3": {"word": "wide", "char_pct": 31, "motif_pct": 71},
    "1:1": {"word": "square", "char_pct": 36, "motif_pct": 64},
    "4:5": {"word": "tall", "char_pct": 40, "motif_pct": 58},
    "3:4": {"word": "tall", "char_pct": 42, "motif_pct": 56},
    "2:3": {"word": "tall", "char_pct": 44, "motif_pct": 52},
    "9:16": {"word": "tall", "char_pct": 46, "motif_pct": 50},
}

HAIR_TPL = (
    "Integrate {name}’s {hair} into the nearest monumental structure. The nearer length falls past the "
    "closest structural edge, passes behind the dominant object, appears magnified and doubled inside one "
    "transparent panel, and reappears as three clean {accent} contours lying across the floor plane. The "
    "farther length rises behind her head, crosses one horizontal band of the main structure, threads between "
    "two joints, and terminates as one thin {accent} contour beside the frame edge. Keep dense, solid, "
    "recognizable hair around her head and upper lengths; allow transparency, doubling and fragmentation only "
    "where the hair physically intersects transparent or reflective material."
)

COSTUME_TPL = (
    "Dress {short} in an original ceremonial costume derived from {design}. Use a fitted {M1} bodice with "
    "{accent} luminous seams, a short asymmetric skirt built from stacked {M2} plates whose thick "
    "glazed edges catch a hard highlight, a {block} enamel waist girdle with tiny gold bolts, detached "
    "translucent {accent} sleeves with silver filigree cuffs, dark thigh-high elements with fine gold seams, "
    "pale shoulder ornaments, and exactly three tiny {minor} fasteners. Keep the costume light, editorial and "
    "precise rather than bulky armor, and let one narrow printed sash trail behind her and overlap the shadow "
    "of the main structure."
)

OUTFIT_TPL = (
    "Layer these specific garments over that structure: {tags}. Keep every material, seam and "
    "fastening consistent with the dominant structure, let the plates, cuffs and closures stay "
    "visible at the edges, and do not let the layered garments cover her face, hands or the "
    "core contact point."
)

# 平面海报分支专用：海报是二维印刷品，不能套 3D 巨构那套「材质 / 结构 / 剪裁」措辞。
# 这里把「所选版型 + 单品」写成一小段平面化服装说明，插在首段之后，不碰排版与大标题。
COSTUME_POSTER_TPL = (
    "Render {short}'s costume as flat printed shapes rather than a three-dimensional garment: "
    "a {cut} silhouette drawn in {design}, built from crisp {M1} and {M2} color planes with "
    "{accent} hairline seams and one small {block} registration block. Keep the outfit "
    "secondary to the display typography and the poster's own color system."
)
OUTFIT_POSTER_TPL = (
    "Read these specific garments as flat printed costume marks: {tags}."
)


def palette_para(ch: dict) -> str:
    p = ch["palette"]
    head = ("Use a highly controlled luxury color hierarchy. "
            f"Approximately {num2words(p[0][1])} percent of the image is {p[0][0]}.")
    mid = " ".join(f"{num2words(v)[0].upper()}{num2words(v)[1:]} percent is {t}."
                   for t, v in p[1:6])
    tail = (f"No more than one percent is {p[6][0]}. Reserve the metallic accent strictly for graduation "
            "marks, bearing races, filigree nodes and structural joints, and reserve the rare minor accent "
            "for three costume fasteners and one registration mark.")
    return f"{head} {mid} {tail}"

GRAPHICS_TPL = (
    "Drive the graphic language from {short}’s own palette. Use one large {ink} ink bloom spreading from the "
    "base of the nearest structure across the floor plane like spilled dye. Place two hard-edged {block} "
    "rectangular color blocks: one on the face of a distant monolith, one behind the main structural ring. "
    "Add translucent {stain} stains that appear only on glass surfaces and printed sheets. Let one halftone "
    "dot gradient live inside the central volume, dense near the core and sparse toward the frame edge. Cut "
    "several clean white knockout strips through the far frame. Add rare {metal} microdots exactly on "
    "graduation marks and structural joints. Do not introduce red, orange, magenta or green fields anywhere "
    "except the rare minor accent."
)

# 写实场景（material-narrative / 夜景）专用：
# 上面那版里有「两块硬边矩形色块」「白色挖空条」，在纯白巨构里成立，
# 套到染坊/窑/站台会直接画出贴在墙上的蓝方块。这版把痕迹全部改成"被材料吸收的墨"。
GRAPHICS_TPL_PHYS = (
    "Keep the printed intervention almost invisible in this real room. Allow only a few small {ink} ink "
    "fingerprints on a hand-worn edge, one faint {stain} tide mark where water dried, a scatter of {block} "
    "dots caught in the dust of one corner, and three {metal} microdots on small metal fittings. Let every "
    "mark be small enough to belong to daily use rather than to design, and let none of them form a large "
    "shape, panel, patch or rectangle anywhere in the frame."
)


ALL_CHARS: dict = {}
ALL_TPLS: list = []          # 通用版型（任意角色可用）
CHAR_TPL_DEFAULT: dict = {}  # 角色 → 推荐版型顺序（只影响随机倾向）


def garment_materials(text: str, k: int = 2) -> list[str]:
    """从母题正文挑服装材质：M1 优先结构型（板材/薄膜/陶瓷），M2 取次高。
    避免出现「香槟金花丝做的躯干面板」这种不合理搭配。"""
    low = text.lower()
    scored = sorted(((low.count(key), label, kind) for key, label, kind in MAT_VOCAB),
                    key=lambda x: -x[0])
    structs = [label for c, label, kind in scored if c > 0 and kind == "struct"]
    others = [label for c, label, kind in scored if c > 0 and kind == "metal"]
    out = structs[:1] + (structs[1:2] or others[:1])
    while len(out) < k:
        out.append(MAT_FALLBACK[len(out) % len(MAT_FALLBACK)])
    return out[:k]

# 不同种子里「角色身份否定句」的写法并不统一，这里按模式清，不靠字面枚举
# 约束段（"否定护盾"）的几种开头写法。旧版只认 No additional physical characters，
# 实际母题里还有 "No second human…" / "No extra figures…"，认不出就会被当成发型段吃掉。
GUARD_RE = re.compile(r"^(?:no additional|no second|no extra|no other|no duplicate|no further)\b",
                      re.I)


def is_guard(p: str) -> bool:
    return bool(GUARD_RE.match(p.strip()))


IDENTITY_NEGATIVES = [
    r"no duplicate \w+", r"no Miku", r"no Furina",
    r"no aqua twin tails", r"no twin tails?", r"no generic blue-haired girl",
    r"no missing top hat", r"no unrelated princess", r"no missing twin-tail silhouette",
    r"no incorrect \w+ hair or outfit identity", r"no realistic human interpretation",
]


def _stamp(path: str) -> tuple:
    """(mtime_ns, size) 指纹。用 ns 而不是浮点秒：同秒内两次改盘不会漏检。"""
    try:
        st = os.stat(path)
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return (0, 0)


_LOAD_CACHE: dict = {}


def load() -> tuple[dict, dict]:
    """母题 + 角色 + 版型三份 JSON 共 3.7MB，每装配一条都调一次（原先 14.6ms/次）。

    按四个数据文件的指纹缓存：4 次 stat 约 0.05ms，改盘（mtime/size 变）自动失效。
    返回的 dict 只读使用（seeds/chars 的全部调用点都只 get，不写）。
    """
    global ALL_CHARS, ALL_TPLS, CHAR_TPL_DEFAULT
    key = tuple((p, _stamp(p)) for p in (SEEDS, SEEDS_EXTRA, CHARS, COSTUMES))
    hit = _LOAD_CACHE.get("v")
    if hit and hit[0] == key:
        return hit[1], hit[2]
    seeds = json.load(open(SEEDS, encoding="utf-8"))["seeds"]
    if os.path.exists(SEEDS_EXTRA):          # 人工新写母题，单独文件，不被 extract 覆盖
        seeds = seeds + json.load(open(SEEDS_EXTRA, encoding="utf-8")).get("seeds", [])
    chars = json.load(open(CHARS, encoding="utf-8"))["characters"]
    ALL_CHARS = chars
    if os.path.exists(COSTUMES):
        d = json.load(open(COSTUMES, encoding="utf-8"))
        ALL_TPLS = d.get("templates") or []
        CHAR_TPL_DEFAULT = d.get("character_default") or {}
    by_id = {s["id"]: s for s in seeds}
    _LOAD_CACHE["v"] = (key, by_id, chars)
    return by_id, chars


def paras(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]


def join(ps: list[str]) -> str:
    return "\n\n".join(ps)


def set_aspect(text: str, aspect: str, log: list[str]) -> str:
    info = ASPECT_INFO[aspect]
    out = re.sub(r"Create an? (?:(?:wide|tall|square) )?\d+:\d+(?: (?:vertical|horizontal))?",
                 f"Create a {info['word']} {aspect}", text, count=1)
    if out == text:
        log.append(f"画幅: 首句已是 {aspect}，无需改写")

    ps = paras(out)
    for i, p in enumerate(ps):
        low = p.lower()
        if "percent of the image is " in low:
            continue  # 色盘段，不动
        for m in list(re.finditer(r"approximately ([a-z\-]+) percent of the (?:canvas|image)", low)):
            v = words2num(m.group(1))
            if v is None:
                continue
            role_motif = bool(re.search(r"dominant visual object|colossal", low)) or v >= 50
            target = info["motif_pct"] if role_motif else info["char_pct"]
            if v == target:
                continue
            p = p[:m.start(1)] + num2words(target) + p[m.end(1):]
            log.append(f"画幅: {'母题' if role_motif else '角色'}占比 {v}% -> {target}% (段落{i+1})")
        ps[i] = p
    return join(ps)


def pick_costume(char_key: str, want: str, log: list[str]):
    """→ (tpl 或 None, id, 中文名)。tpl 为 None 表示「保持母题原样」，不替换服装段。"""
    if want == "keep":
        return None, "keep", "保持母题原样"
    if not ALL_TPLS:
        log.append("服装: 无版型库，回退通用模板")
        return COSTUME_TPL, "generic", "通用"
    if want and want != "auto":
        for it in ALL_TPLS:
            if it["id"] == want:
                log.append(f"服装: 指定「{it['zh']}」({it['id']})")
                return it["tpl"], it["id"], it["zh"]
        log.append(f"服装: 未找到 {want}，改用随机")
    pref = [t for t in ALL_TPLS if t["id"] in (CHAR_TPL_DEFAULT.get(char_key) or [])]
    pool = pref or ALL_TPLS
    it = random.choice(pool)
    log.append(f"服装: {'随机' if want == 'auto' else '默认'}「{it['zh']}」"
               f"（{len(pool)} 套候选）")
    return it["tpl"], it["id"], it["zh"]


# 段落定位：不同时期的母题措辞不同（旧版 "Dress Miku in…"，新版 "Redesign the costume…"），
# 所以分「强信号 = 段首动词」/「弱信号 = 内容关键词」两级，强信号优先全区取胜，
# 避免"环境段里提了一句 twin tails 就被当成发型段"这类撞车。
HAIR_STRONG = ("integrate", "weave", "let her hair", "let her extremely long",
               "where the twin", "run her twin", "carry her twin", "her twin tail")
HAIR_WEAK = ("twin tail", "twin ponytail", "hair behave")
COSTUME_STRONG = ("dress ", "redesign the costume", "redesign her costume")
COSTUME_WEAK = ("costume within the same silhouette", "costume in the same silhouette")
PALETTE_STRONG = ("hold the palette", "allocate colour", "allocate color",
                  "use a strict", "build the palette", "set the palette")
PALETTE_WEAK = ("percent of the image is ", "percent of the canvas is")


def locate_sections(ps: list[str]) -> tuple[int, int, int, int]:
    """返回 (发型段, 服装段, 色盘段, 图形段) 的段号，未命中为 -1。"""
    strong = {"hair": -1, "costume": -1, "palette": -1}
    weak = dict(strong)
    gfx = -1
    for i, p in enumerate(ps):
        low = p.lower()
        if low.startswith("create a ") or "canonical identity" in low:
            continue                     # 概念段本身含 twin tails / hair，必须排掉
        if is_guard(p):
            continue                     # ⚠ 约束段里写着 "no aqua twin tails"，会被当成发型段整段吃掉
        if strong["hair"] < 0 and low.startswith(HAIR_STRONG) and (
                "hair" in low or "tail" in low):
            strong["hair"] = i
        if strong["costume"] < 0 and low.startswith(COSTUME_STRONG):
            strong["costume"] = i
        if strong["palette"] < 0 and low.startswith(PALETTE_STRONG) and "percent" in low:
            strong["palette"] = i
        if gfx < 0 and ("ink bloom" in low or "graphic language" in low):
            gfx = i

        if weak["hair"] < 0 and ("hair" in low or "tail" in low) and any(
                k in low for k in HAIR_WEAK):
            weak["hair"] = i
        if weak["costume"] < 0 and any(k in low for k in COSTUME_WEAK):
            weak["costume"] = i
        if weak["palette"] < 0 and any(k in low for k in PALETTE_WEAK):
            weak["palette"] = i

    def pick(k: str) -> int:
        return strong[k] if strong[k] >= 0 else weak[k]

    return pick("hair"), pick("costume"), pick("palette"), gfx


def set_character(text: str, ch: dict, log: list[str], costume: str = "auto",
                  char_key: str = "", motif_text: str = "",
                  outfit_tags: list[str] | None = None,
                  graphics_phys: bool = False, lock_palette: bool = False) -> str:
    # 1) featuring 从句
    new, n = re.subn(r"featuring .{2,80}? as the only (?:physical )?character",
                     ch["feature_clause"], text, count=1)
    log.append(f"角色: featuring 从句 {'已换' if n else '未命中'}")
    text = new

    # 2) 身份锚点句
    # ⚠ 只在同一段内替换（[^\n]），绝不能用 re.S 跨段：新版母题写 "Preserve canonical identity:
    #   ... silhouette immediately readable ..."（silhouette 后面不是句号），跨段正则会一路吃到
    #   后面某个 "readable" 才收，把发型/服装段整块吞掉。
    # 先删掉原文自带的 "Keep … readable/unobstructed …" 保护句，再整句换成角色身份句
    # （身份句里已经带了一句 Keep，不先删会重复）。
    new, k = re.subn(r"(?<=[.!;] )Keep (?:her|the) [^\n]*?"
                     r"(?:readable|unobstructed|unoccluded)[^\n]*?\.", "", text, count=1)
    log.append(f"角色: 旧保护句 {'已删' if k else '无'}")
    new, n = re.subn(r"Preserve [^\n]*?\.", ch["identity"], new, count=1)
    if not n:
        new, n = re.subn(r"Keep [^\n]*?(?:identity|silhouette)[^\n]*?\.", ch["identity"],
                         new, count=1)
    log.append(f"角色: 身份锚点 {'已换' if n else '未命中'}")
    text = new

    ps = paras(text)
    hair_i, costume_i, palette_i, graphics_i = locate_sections(ps)

    if hair_i >= 0:
        ps[hair_i] = HAIR_TPL.format(name=ch["short"], hair=ch["hair_desc"], accent=ch["accent"])
    log.append(f"角色: 发型段 {'已换' if hair_i >= 0 else '未命中(跳过)'}")

    if costume_i >= 0:
        tpl, cid, czh = pick_costume(char_key, costume, log)
        if tpl is None:
            log.append("服装: 保留母题原样的服装段")
        else:
            m1, m2 = garment_materials(motif_text or text)
            log.append(f"服装: 材质取母题「{m1} / {m2}」")
            ps[costume_i] = tpl.format(short=ch["short"], design=ch["design_language"],
                                       M1=m1, M2=m2, accent=ch["accent"],
                                       block=ch["block"], minor=ch["minor"])
    log.append(f"角色: 服装段 {'已换' if costume_i >= 0 and costume != 'keep' else '未替换'}")

    # 单品层：来自 Anima 服装库 / 角色服装预设的 tags，追加在版型段之后
    if outfit_tags:
        if costume_i >= 0 and costume != "keep":
            ps[costume_i] = ps[costume_i].rstrip() + " " + OUTFIT_TPL.format(
                tags=", ".join(outfit_tags))
            log.append(f"服装: 叠加单品 {len(outfit_tags)} 条 → {', '.join(outfit_tags[:3])}…")
        else:
            log.append("服装: 版型为「保持原样」，单品无法叠加，已忽略")

    if palette_i >= 0 and not lock_palette:
        ps[palette_i] = palette_para(ch)
    if lock_palette and palette_i >= 0:
        log.append("角色: 色盘段 已锁（母题 lock_palette=true，保留母题配色）")
    else:
        log.append(f"角色: 色盘段 {'已换' if palette_i >= 0 else '未命中(跳过)'}")

    if graphics_i >= 0:
        ps[graphics_i] = (GRAPHICS_TPL_PHYS if graphics_phys else GRAPHICS_TPL).format(
            short=ch["short"], ink=ch["ink"], block=ch["block"],
            stain=ch["stain"], metal=ch["metal"])
    log.append(f"角色: 图形段 {'已换(写实版)' if graphics_phys else '已换'}" if graphics_i >= 0
               else "角色: 图形段 未命中(跳过)")

    text = join(ps)

    # 3) 全文角色名替换（正文里 Place Miku / Miku’s fingers 等散落引用）
    for src in ALL_CHARS.values():
        if src["short"] == ch["short"]:
            continue
        text = re.sub(rf"\b{re.escape(src['name'])}\b", ch["name"], text)
        text = re.sub(rf"\b{re.escape(src['short'])}\b", ch["short"], text)
    log.append("角色: 全文名称已替换")

    # 4) 约束段里的角色护盾：先按固定模式剔掉旧角色专属否定，再插一条目标角色的
    # ⚠ 约束段的开头不止一种写法：旧版 "No additional physical characters"，
    #    新版还有 "No additional figures or hands"。统一按 "No additional" 认。
    def guard(m: re.Match) -> str:
        body = m.group(0)
        for pat in IDENTITY_NEGATIVES:
            body = re.sub(pat + r",?\s*", "", body, flags=re.I)
        body = re.sub(r"^(?:No additional|No second|No extra|No other|No duplicate|No further)[^,]*,\s*",
                      "No additional physical characters, ", body)
        body = re.sub(r"(,\s*){2,}", ", ", body)
        insert = ", ".join(x.strip() for x in ch["guard"].split(",") if x.strip())
        body = re.sub(r"(No additional physical characters,\s*)", r"\1" + insert + ", ", body, count=1)
        return body

    text, n = re.subn(r"^(?:No additional|No second|No extra|No other|No duplicate|No further)\b[^\n]*",
                      guard, text, count=1, flags=re.M)
    log.append(f"角色: 约束护盾 {'已换' if n else '未命中'}")

    # 5) 散落在正文里的双马尾表述（蒙版段、景深段常提到「the lower twin tail」）
    #    发型段已经整段换过，但这些句子还留着原角色的特征 → 换非双马尾角色会画出两束长发。
    #    用复数名词 "long hair strands" 替换，句子的单复数不用跟着改。
    if "twin tail" not in (ch.get("hair_desc") or "").lower():
        out = []
        k = 0
        for p in paras(text):
            if not is_guard(p):
                p, c = re.subn(r"\btwin tails?\b", "long hair strands", p, flags=re.I)
                p, c2 = re.subn(r"\btwin ponytails?\b", "long hair strands", p, flags=re.I)
                k += c + c2
            out.append(p)
        if k:
            text = join(out)
        log.append(f"角色: 残留双马尾表述 {'已中性化 ' + str(k) + ' 处' if k else '无'}")
    return text


# 短提示词分支：原文只有 4–8 段 tag 流式短句，追加的服装说明也要短，不能塞长段。
COSTUME_SHORT_TPL = (
    "Render {short} in a {cut} with {accent} accents and {block} details, "
    "keeping the outfit clean and secondary to the composition."
)
OUTFIT_SHORT_TPL = "Include these specific garments: {tags}."


def set_character_short(text: str, ch: dict, log: list[str], costume: str = "auto",
                        char_key: str = "", motif_text: str = "",
                        outfit_tags: list[str] | None = None) -> str:
    """短提示词分支的轻量适配：不动构图，只换身份 + 追加一两句服装。"""
    ps = paras(text)

    new, n = re.subn(r"Preserve [^\n]*?\.", ch["identity"], text, count=1)
    if not n:
        new, n = re.subn(r"(recognizable [^.\n]*?(?:silhouette|twin-tail silhouette)[^.\n]*\.)",
                         ch["identity"], text, count=1)
    log.append(f"短提示: 身份锚点 {'已换' if n else '原文无，改为插入'}")
    ps = paras(new)
    if not n:
        ps.insert(1, ch["identity"])

    tpl, cid, czh = pick_costume(char_key, costume, log)
    cut = next((t["id"].replace("_", " ") for t in ALL_TPLS if t["id"] == cid), "") \
        or cid.replace("_", " ") or "auto"
    extra = COSTUME_SHORT_TPL.format(short=ch["short"], cut=cut,
                                     accent=ch["accent"], block=ch["block"])
    if outfit_tags:
        extra += " " + OUTFIT_SHORT_TPL.format(tags=", ".join(outfit_tags[:12]))
    ps.append(extra)
    log.append(f"短提示: 已追加服装句「{cut}」"
               + (f" + {len(outfit_tags)} 个单品" if outfit_tags else ""))
    text = join(ps)

    for src in ALL_CHARS.values():
        if src["short"] == ch["short"]:
            continue
        text = re.sub(rf"\b{re.escape(src['name'])}\b", ch["name"], text)
        text = re.sub(rf"\b{re.escape(src['short'])}\b", ch["short"], text)
    text = re.sub(r"\bMarie Rose\b", ch["name"], text)
    log.append("短提示: 全文角色名已替换")

    ps = paras(text)
    ins = ", ".join(x.strip() for x in ch["guard"].split(",") if x.strip())
    if not any(is_guard(p) for p in ps):
        ps.append("No additional physical characters, " + ins + (
            ", no duplicate face, no extra limbs, no readable text beyond the intended typography."))
    text = join(ps)
    log.append("短提示: 约束护盾已补齐")

    if "twin tail" not in (ch.get("hair_desc") or "").lower():
        out, cnt = [], 0
        for p in paras(text):
            if not is_guard(p):
                p, c = re.subn(r"\btwin tails?\b|\btwin ponytails?\b",
                               "long hair strands", p, flags=re.I)
                cnt += c
            out.append(p)
        if cnt:
            text = join(out)
        log.append(f"短提示: 双马尾表述中性化 {cnt} 处")
    return text


def set_character_poster(text: str, ch: dict, log: list[str], costume: str = "auto",
                         char_key: str = "", motif_text: str = "",
                         outfit_tags: list[str] | None = None) -> str:
    """平面海报分支的角色/服装适配。

    海报没有 3D 母题那 7 个锚点（只有 1/19 有 Dress 段），所以不能走 set_character：
    这里保留整张版式、大标题与印刷色盘，只做四件有边界的替换。
    """
    ps = paras(text)

    # 1) 身份锚点：16/19 有 Preserve 句；没有的就在首段后补一段
    new, _k = re.subn(r"(?<=[.!;] )Keep (?:her|the) [^\n]*?"
                      r"(?:readable|unobstructed|unoccluded)[^\n]*?\.", "", text, count=1)
    new, n = re.subn(r"Preserve [^\n]*?\.", ch["identity"], new, count=1)
    log.append(f"海报: 身份锚点 {'已换' if n else '原文无，改为插入'}")
    ps = paras(new)
    if not n:
        ps.insert(1, ch["identity"])

    # 2) 服装：所选版型 + 单品 → 一小段平面化说明，插在首段（概念）之后
    tpl, cid, czh = pick_costume(char_key, costume, log)
    m1, m2 = garment_materials(motif_text or text)
    # ⚠ 版型的 zh 是中文，绝不能进英文提示词；用 id 还原成英文短语
    cut = next((t["id"].replace("_", " ") for t in ALL_TPLS if t["id"] == cid), "") \
        or cid.replace("_", " ") or "auto"
    cpara = COSTUME_POSTER_TPL.format(short=ch["short"], cut=cut,
                                      design=ch["design_language"], M1=m1, M2=m2,
                                      accent=ch["accent"], block=ch["block"])
    if outfit_tags:
        cpara += " " + OUTFIT_POSTER_TPL.format(tags=", ".join(outfit_tags[:14]))
    ps.insert(1, cpara)
    log.append(f"海报: 已插入服装段「{cut}」" + (f" + {len(outfit_tags)} 个单品" if outfit_tags else ""))

    # 3) 角色色只作为小面积登记色，不改海报自己的印刷色盘
    pidx = next((i for i, p in enumerate(ps) if "percent" in p.lower()
                 or "palette" in p.lower() or "colour" in p.lower()), -1)
    if pidx >= 0:
        ps[pidx] = ps[pidx].rstrip() + (
            f" Carry {ch['short']}'s own {ch['accent']} and {ch['block']} only in the hair, "
            "eyes and one small registration mark.")
        log.append("海报: 角色色已作为登记色挂到色盘段")
    else:
        log.append("海报: 无色盘段，保留原印刷配色")

    text = join(ps)

    # 4) 全文角色名替换（含个别海报用的 Marie Rose）
    for src in ALL_CHARS.values():
        if src["short"] == ch["short"]:
            continue
        text = re.sub(rf"\b{re.escape(src['name'])}\b", ch["name"], text)
        text = re.sub(rf"\b{re.escape(src['short'])}\b", ch["short"], text)
    text = re.sub(r"\bMarie Rose\b", ch["name"], text)
    log.append("海报: 全文角色名已替换")

    # 5) 约束护盾：没写的补一段；写了的重建为目标角色护盾
    ps = paras(text)
    guards = [i for i, p in enumerate(ps) if is_guard(p)]
    ins = ", ".join(x.strip() for x in ch["guard"].split(",") if x.strip())
    shield = "No additional physical characters, " + ins + (
        ", no duplicate face, no extra limbs, no floating interface panels, "
        "no readable text beyond the intended display typography.")
    if guards:
        i = guards[0]
        tail = [x.strip() for x in ps[i].split(",")[1:] if x.strip()]
        ps[i] = "No additional physical characters, " + ins + (
            ", " + ", ".join(tail) if tail else ".")
    else:
        ps.append(shield)
    log.append(f"海报: 约束护盾 {'已重建' if guards else '已补'}")
    text = join(ps)

    # 6) 非双马尾角色：把「twin tails」中性化，避免画出初音的双马尾
    if "twin tail" not in (ch.get("hair_desc") or "").lower():
        out, cnt = [], 0
        for p in paras(text):
            if not is_guard(p):
                p, c = re.subn(r"\btwin tails?\b|\btwin ponytails?\b",
                               "long hair strands", p, flags=re.I)
                cnt += c
            out.append(p)
        if cnt:
            text = join(out)
        log.append(f"海报: 双马尾表述中性化 {cnt} 处")
    return text


# ---------------------------------------------------------------------------
# 画面内文字（画在海报/场景里的英文）
# ⚠️ 172 条母题至少有 20 种写法：titled "X" / the exact title "X" /
#    large readable English title "X" / include the exact readable text "X" /
#    only the exact word "X" / small English subtitle "X" …
#    早期只认 titled "X"，命中率不到 1/3，其余会被当成「原无文字」而在文末
#    追加一句互相矛盾的指令 —— 模型听原句，用户填的字完全不生效（实测踩过）。
# ---------------------------------------------------------------------------
DISPLAY_CUES = (
    "title", "text", "letter", "word", "type", "readab", "paint", "writ",
    "caption", "display", "sign", "logo", "headline", "label", "subtitle",
    "wordmark", "inscription", "engrav", "print", "typeset", "sans", "serif",
)
QUOTE_RE = re.compile(r'[“"]([^”"\n]{2,60})[”"]')
# 单引号版必须靠边界判定：英文所有格（Miku's boots, her cloak's）也是一个 '，
# 若像双引号那样直接配对，会把 "s boots, her cloak" 认成画内文字，
# 替换时正文被改成 Miku"LOVE"s。开引号前、闭引号后都不许紧贴字母或数字。
SQUOTE_RE = re.compile(r"(?<![A-Za-z0-9])'([^'\n]{2,60})'(?![A-Za-z0-9])")


def find_display_text(raw: str) -> list[str]:
    """返回正文里所有「要画进画面的文字」短语，按出现次数降序。

    判据：引号内 2–60 字符的短语，且引号前 140 字符里出现排版/文字类引导词。
    这样既能抓 CINDER DANCE / GRAIN SANCTUM，也能抓 Blooming Frequency、
    あらし、羽化 这类非全大写标题；同时不会把普通描述句当成画内文字。
    """
    hits: dict[str, int] = {}
    for rx in (QUOTE_RE, SQUOTE_RE):
        for m in rx.finditer(raw):
            v = m.group(1).strip()
            if not (2 <= len(v) <= 60):
                continue
            # 逗号 / 分号 / 句号结尾多半是句子而不是标题
            if v[-1] in ",;:" or v.count(",") >= 2:
                continue
            ctx = raw[max(0, m.start() - 140):m.start()].lower()
            if not any(k in ctx for k in DISPLAY_CUES):
                continue
            hits[v] = hits.get(v, 0) + 1
    return [v for v, _ in sorted(hits.items(), key=lambda x: (-x[1], -len(x[0])))]


def set_display_text(text: str, orig_title: str, disp: str, log: list[str],
                     orig_candidates: list[str] | None = None) -> str:
    """把画面里要画出来的文字换成用户指定的内容。

    就地替换所有出现（保留位置、字体、材质描述），绝不追加第二套并列指令。
    一条母题的画内文字通常在提示词里出现 2–3 次（首句 titled / 排版段 /
    刻字段），只改一处会画出两个不同标题。
    """
    disp = (disp or "").strip()
    if not disp:
        return text

    phrases: list[str] = []
    for p in (orig_candidates or []):
        if p and p.strip() not in phrases:
            phrases.append(p.strip())
    if orig_title and orig_title.strip() not in phrases:
        phrases.append(orig_title.strip())
    for p in find_display_text(text):
        if p not in phrases:
            phrases.append(p)
    phrases = [p for p in phrases if p in text and p != disp]

    if not phrases:
        # 母题本来没有画内文字：把指令插在首段之后（靠前，权重高），
        # 而不是甩到全文末尾被长文淹没。
        ps = paras(text)
        ins = (f'Render the only readable lettering in this image as the exact text '
               f'"{disp}", physically integrated into the composition.')
        ps.insert(1, ins)
        log.append(f"画面英文: 原无文字 → 首段后插入「{disp}」")
        return join(ps)

    total = 0
    for p in phrases:
        total += text.count(p)
        text = text.replace(p, disp)
    # 就近强化：在第一个出现新文字的段落末尾补一句「唯一可读文字」，
    # 压住模型自由发挥，同时不新增段落（段落数不变，校验不炸）。
    ps = paras(text)
    for i, p in enumerate(ps):
        if disp in p and "only readable lettering in this image" not in p:
            ps[i] = p.rstrip().rstrip(".") + (
                f'. The only readable lettering in this image is exactly "{disp}".')
            break
    log.append(f"画面英文: 「{phrases[0]}」等 {len(phrases)} 种原文"
               f" → 「{disp}」（替换 {total} 处，原排版描述保留）")
    return join(ps)


# ---------------------------------------------------------------------------
# 「只留主标题」：主标题替换，编号小字（PLATE 04 / VOICE INDEX）删掉
# ---------------------------------------------------------------------------
def _tidy_punct(s: str) -> str:
    """删分句后收拾多出来的标点与空格。"""
    # 删字后标点常被换行挤到下一行，先提回文内
    s = re.sub(r"[ \t]*\n[ \t]*([,;.:])", r"\1", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    s = re.sub(r",\s*([,;.])", r"\1", s)
    s = re.sub(r",\s*,", ",", s)
    s = re.sub(r";\s*([;.])", r"\1", s)
    s = re.sub(r"\(\s*[,;]\s*", "(", s)
    s = re.sub(r"\[\s*[,;]\s*", "[", s)
    s = re.sub(r"^\s*[,;]\s*", "", s, flags=re.M)
    s = re.sub(r"[ \t]+([,;.])", r"\1", s)
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n[ \t]+", "\n", s)
    # 删字符后可能留下「虚词 + 标点」的空尾（readability of. → readability.）
    s = re.sub(r"\b(of|to|in|the|with|from)\s*([.;])", r"\2", s)
    s = re.sub(r"(?<=\s)[,;](?=\s|$)", "", s)
    # 连续标点归一（删副文字常撞出 ,,; 这种东西）
    s = re.sub(r"(?:[,;]\s*){2,}", ", ", s)
    s = re.sub(r",\s*([.;])", r"\1", s)
    s = re.sub(r"\s+([,.;])", r"\1", s)
    return s


LANG_WORDS = r"(?:Japanese|Chinese|Korean|hiragana|katakana|kanji)"
LANG_NOUN = (r"(?:title|lettering|typography|letterform|characters|text|display|"
             r"wordmark|script|calligraphy)")


def _latinize_title_context(text: str, disp: str, log: list[str]) -> str:
    """标题换成英文后，把「Japanese hiragana title」这类语言限定改成 English。

    ⚠️ 只改**标题语境**。`premium Japanese editorial design`、`not Chinese
    calligraphy` 这类风格/负向语境必须留着 —— 改掉会丢风格（实测）。
    日文标题还常被拆成单字写版式（`reading from left to right as あ, ら, し`、
    `the final し`、`Render あ and ら`），整词替换抓不到，**残留一个假名就够
    模型画回原文**，所以要按模式清 + 非 ASCII 兜底。
    """
    PH = "\x01"                       # 保护用户填的非 ASCII 文字不被兜底删掉
    text = text.replace(disp, PH) if disp else text
    n = 0

    def repl(mo):
        nonlocal n
        n += 1
        return "English" + mo.group(1)

    text = re.sub(r"\b" + LANG_WORDS + r"\b(\s+" + LANG_NOUN + r"\b)", repl,
                  text, flags=re.I)
    if n:
        log.append(f"画面英文: 语言限定 → English（{n} 处）")

    before = text
    # ① 字符枚举：as あ, ら, し
    text = re.sub(r"((?:as|reading|reads)\s+)(?:[^\s,.;]+\s*,\s*)+[^\s,.;]+",
                  r"\1the letters of the word", text)
    # ② the final し → the final letter
    text = re.sub(r"\bfinal\s+[^\sA-Za-z0-9][^\s,.;]*", "final letter", text)
    # ③ Render あ and ら → Render the word
    text = re.sub(r"\b(Render|Draw|Paint|Set|Spell)\s+[^\sA-Za-z0-9][^\s,.;]*"
                  r"(?:\s+and\s+[^\sA-Za-z0-9][^\s,.;]*)?", r"\1 the word", text)
    # ④ 兜底：删掉剩余的假名/汉字/全角标点。⚠️ 只删 CJK —— 早先写成
    #    [^\x00-\x7f] 会把 em dash、弯引号一起吃掉，英文的排版节奏全没了。
    text = re.sub(r"[\u3000-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uff00-\uffef]+", "", text)
    if text != before:
        log.append("画面英文: 清理逐字引用（1 轮）")
    return text.replace(PH, disp) if disp else text


def set_display_title_only(text: str, orig_title: str, disp: str, log: list[str],
                           orig_candidates: list[str] | None = None) -> str:
    """只留主标题：主标题全部替换成 disp，其他不同文字的编号小字按分句删除。

    与 set_display_text 的两处关键差别（都靠真机图才发现）：
      1. 主标题**全部替换**，不是只换第一处 —— 原文把标题写 2~7 次，每处带
         位置/字号/字体，是排版指令；只换一处等于把排版描述全删，8 步 turbo
         会直接漏字（k2p_blooming_freq 画面完全无字）。
      2. 副文字按**分句**删除：同句里有主标题时只删短语，否则整句删掉，
         再用 _tidy_punct 收拾残留标点。
    """
    disp = (disp or "").strip()
    if not disp:
        return text

    cands: list[str] = []
    for p in (orig_candidates or []):
        if p and p.strip() not in cands:
            cands.append(p.strip())
    for p in find_display_text(text):
        if p not in cands:
            cands.append(p)
    cands = [p for p in cands if p in text]

    if not cands:
        ps = paras(text)
        ps.insert(1, f'Render the only readable lettering in this image as the exact '
                     f'text "{disp}", physically integrated into the composition.')
        log.append(f"画面英文: 原无文字 → 首段后插入「{disp}」")
        return join(ps)

    title = orig_title if orig_title in cands else max(cands, key=len)
    secondaries = [p for p in cands if p != title]
    orig_paras = len(paras(text))

    # ① 主标题全部替换（引号写法与裸写都要换）
    quoted = re.compile(r'[“"\']\s*' + re.escape(title) + r'\s*[”"\']')
    text, n_q = quoted.subn(f'"{disp}"', text)
    n_bare = text.count(title)
    if n_bare:
        text = text.replace(title, disp)
    n_title = n_q + n_bare

    # ② 副文字：整句删除；同句里还有主标题时退化成只删短语
    removed = 0
    for p in secondaries:
        guard = 0
        while p in text and guard < 40:
            guard += 1
            i = text.find(p)
            cs = max(text.rfind(". ", 0, i), text.rfind("; ", 0, i),
                     text.rfind("\n", 0, i)) + 1
            ce = len(text)
            for sep in (". ", "; ", "\n"):
                j = text.find(sep, i + len(p))
                if j >= 0:
                    ce = min(ce, j + 1)
            clause = text[cs:ce]
            seg = clause
            seg_after = seg[:max(0, i - cs)] + seg[i - cs + len(p):]
            # 整句删掉会让这一段空掉（段数少一段，validate 会报段落不足）→
            # 退化成只删短语，让后面的 NO_TEXT_SEG 兜底保住段数
            if disp in clause or len(seg_after.split()) < 4:
                new_clause = re.sub(r'[“"\']?\s*' + re.escape(p) + r'\s*[”"\']?',
                                    "", clause, count=1)
                text = text[:cs] + new_clause + text[ce:]
            else:
                text = text[:cs] + text[ce:]
            removed += 1

    # 先拉丁化（会删掉中日文字符），再收拾因此产生的空格与标点
    text = _latinize_title_context(text, disp, log)
    text = _tidy_punct(text)

    # ③ 若某段被删空，换成干净留白句（段数由 paras 口径决定，空段本来就不算段）
    ps = paras(text)
    for i, p in enumerate(ps):
        if len(p.split()) < 4:
            ps[i] = NO_TEXT_SEG
    # 整段被删掉时 paras 会少一段 → 补一段留白，保住原段数（validate 有下限）
    while len(ps) < orig_paras and len(ps) >= 2:
        ps.insert(len(ps) - 1, NO_TEXT_SEG)
    # ④ 就近强化：第一处 disp 所在段补一句「唯一可读文字」
    for i, p in enumerate(ps):
        if disp in p and "only readable lettering in this image" not in p:
            ps[i] = p.rstrip(" .;") + (
                f'. The only readable lettering in this image is exactly "{disp}".')
            break
    log.append(f"画面英文: 只留主标题「{title}」→「{disp}」（替换 {n_title} 处，"
               f"删除编号小字 {len(secondaries)} 种/{removed} 处）")
    return join(ps)


NO_TEXT_LEAD = ("The image contains no readable lettering of any kind: every surface that "
                "would normally carry a title, label, number, caption or wordmark stays "
                "clean and unmarked, showing only light, shadow and material grain.")
NO_TEXT_SEG = ("Keep that area as clean unmarked negative space with soft light, faint grain "
               "and gentle shadow only.")


def remove_display_text(text: str, orig_candidates: list[str] | None,
                        log: list[str]) -> str:
    """「画面不显示文字」：清掉母题里所有画内文字及其排版指令。

    ⚠️ 只删引号内容不够 —— 剩下的 `the exact title in small serif lettering,
    elegant and legible` 仍会催模型画字。所以三层一起做：
      ① 删引号内的文字短语
      ② 纯排版描述的短段落整段换成「干净留白」句（段落数不变）
      ③ 首段里的 `titled , featuring` 收拾成通顺的 `with no lettering, …`
      ④ 首段之后插一句总纲（靠前，权重高）
    """
    phrases: list[str] = []
    for p in (orig_candidates or []):
        if p and p.strip() not in phrases:
            phrases.append(p.strip())
    for p in find_display_text(text):
        if p not in phrases:
            phrases.append(p)
    phrases = [p for p in phrases if p in text]
    for p in phrases:
        esc = re.escape(p)
        # ① 带引号的写法
        text = re.sub(r'[“"\']\s*' + esc + r'\s*[”"\']', " ", text)
        # ② 裸写（海报常见：Use the exact Japanese title あらし / …final "R" in VESPER）
        if re.search(r"[A-Za-z]", p):
            text = re.sub(r"(?<![A-Za-z0-9])" + esc + r"(?![A-Za-z0-9])",
                          " ", text, flags=re.I)
        else:
            text = text.replace(p, " ")
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\s+([,.;:])", r"\1", text)

    TITLE_SEG = re.compile(
        r"\b(title|titled|lettering|readable text|typography|caption|label|wordmark|display text)\b",
        re.I)
    KEEP = re.compile(
        r"\b(Create|featuring|canonical identity|Dress|Preserve|Integrate|Weave|percent|No additional)\b",
        re.I)
    ps = paras(text)
    for i, p in enumerate(ps):
        if (len(p.split()) <= 70 and TITLE_SEG.search(p) and not KEEP.search(p)
                and "carries no lettering" not in p):
            ps[i] = NO_TEXT_SEG
    ps[0] = re.sub(r"\btitled\s*,", "with no lettering,", ps[0], flags=re.I)
    ps[0] = re.sub(r"\btitled\s+(?=[a-z])", "with no lettering ", ps[0], flags=re.I)
    if not any("no readable lettering of any kind" in p for p in ps):
        ps.insert(1, NO_TEXT_LEAD)
    log.append(f"画面文字: 已清除 {len(phrases)} 种原文，改为无文字模式")
    return join(ps)


class AssembleError(ValueError):
    """装配入参不合法（母题 / 角色不存在）。

    必须是 Exception 子类：节点的 `except Exception` 和 ComfyUI 的
    execution.py `except Exception` 才接得住。早期这里抛 SystemExit，
    而 SystemExit 继承 BaseException —— 两层都捕不到，会让执行 worker
    直接终止（队列永远停在「执行中」，只能重启）。
    """


def seed_branch(seed_id: str) -> str:
    """母题所属分支：scene（3D 场景）/ poster（平面海报）。"""
    seeds, _ = load()
    return (seeds.get(seed_id) or {}).get("branch", "scene")


def seed_character(seed_id: str) -> str:
    """母题原文登记的角色（如 "Hatsune Miku"）。给 validate 做残留检查用。"""
    seeds, _ = load()
    return (seeds.get(seed_id) or {}).get("character") or ""


def assemble(seed_id: str, char_key: str | None = None, aspect: str | None = None,
             costume: str = "auto", char_obj: dict | None = None,
             outfit_tags: list[str] | None = None,
             display_text: str = "", no_text: bool = False,
             display_mode: str = "all") -> tuple[str, list[str]]:
    seeds, chars = load()
    if seed_id not in seeds:
        raise AssembleError(f"未知种子: {seed_id}")
    seed = seeds[seed_id]
    branch = seed.get("branch") or "scene"
    raw_mode = branch in ("poster", "short")
    text, log = seed["raw"], []
    if aspect and aspect != "keep":
        if raw_mode:
            # 海报/短提示词首句写的是 horizontal 16:9 / vertical 4:5 / Square 1:1
            # 或自由短句，是设计的一部分；强改会毁掉版式。画幅由工作流参数节点决定。
            log.append(f"{'海报' if branch == 'poster' else '短提示'}: 保留原版式画幅写法")
        else:
            text = set_aspect(text, aspect, log)
    if char_key and char_key != "keep":
        ch = char_obj or chars.get(char_key)
        if ch is None:
            raise AssembleError(f"未知角色: {char_key}")
        if branch == "poster":
            text = set_character_poster(text, ch, log, costume, char_key, seed["raw"],
                                        outfit_tags)
        elif branch == "short":
            text = set_character_short(text, ch, log, costume, char_key, seed["raw"],
                                       outfit_tags)
        else:
            text = set_character(text, ch, log, costume, char_key, seed["raw"], outfit_tags,
                                 graphics_phys=(seed.get("source") == "authored"),
                                 lock_palette=bool(seed.get("lock_palette")))
    if no_text:
        # 优先级最高：勾了「画面不显示英文」就不再管填了什么文字
        text = remove_display_text(text, find_display_text(seed["raw"]), log)
    elif display_text:
        # 从「母题原文」里找画内文字（不是装配后的文本，因为角色/服装替换
        # 可能已经动过引号内容，那样会漏掉原句的标题）。
        mode = (display_mode or "all").lower()
        if mode in ("title", "title_only", "only_title", "main"):
            text = set_display_title_only(
                text, seed.get("title", ""), display_text, log,
                orig_candidates=find_display_text(seed["raw"]))
        else:
            text = set_display_text(text, seed.get("title", ""), display_text, log,
                                    orig_candidates=find_display_text(seed["raw"]))
    return text, log


def words2num(w: str) -> int | None:
    w = w.lower().strip()
    for n in range(1, 100):
        if num2words(n) == w:
            return n
    return None


def parse_percents(p: str) -> list[int]:
    out = []
    for m in re.finditer(r"(?:approximately\s+)?([a-z\-]+?)\s+percent", p.lower()):
        v = words2num(m.group(1))
        if v is not None:
            out.append(v)
    return out


# 母题 character 字段有几种写法："Hatsune Miku"、"Furina (Genshin Impact)"、
# "Furina from Genshin Impact"。作品名和介词都不是角色名，做残留检查时必须排除 ——
# 否则正文里正常的 "Genshin Impact" 会被当成没换干净的角色名报出来
# （k2ed 实测误报过 ComfyUI_temp_zmmyf_00011_ 的 "Impact"）。
STOP_WORDS = {
    "genshin", "impact", "honkai", "star", "rail", "blue", "archive", "arknights",
    "fate", "azur", "lane", "wuthering", "waves", "zenless", "zone", "zero",
    "touhou", "project", "vocaloid", "kantai", "collection", "hololive",
    "idolmaster", "musume", "uma", "the", "girl", "girls", "anime",
    "from", "with", "and", "of", "in", "on", "ver", "the",
}


def _char_short_names(orig: str) -> list[str]:
    """母题登记的 "Hatsune Miku" / "Furina from Genshin Impact" → ["Hatsune","Miku"] / ["Furina"]。

    取括号外、长度 ≥3、且不在停用词里的词：任何一个在正文里残留，都说明换角色没换干净。
    """
    s = re.sub(r"\([^)]*\)", " ", orig or "")
    return [w for w in re.split(r"[\s_]+", s.strip())
            if len(w) >= 3 and w.lower() not in STOP_WORDS]


def validate(text: str, want_char: str | None = None,
             branch: str | None = None, orig_char: str = "") -> dict:
    ps = paras(text)
    words = len(text.split())
    poster = branch == "poster"
    shortp = branch == "short"
    lo, minp = (100, 1) if shortp else ((700, 10) if poster else (1000, 18))
    rep = {"words": words, "paras": len(ps), "issues": []}
    if not (lo <= words <= 3400):
        rep["issues"].append(f"篇幅异常 {words} 词")
    if len(ps) < minp:
        rep["issues"].append(f"段落偏少 {len(ps)}")
    head_ok = re.match(r"Create an? (?:(?:wide|tall|square) )?\d+:\d+", text)
    if poster:
        head_ok = re.match(r"^(Create a|Square|Portrait|Horizontal|Vertical)", text, re.I)
    elif shortp:
        head_ok = bool(text.strip())
    if not head_ok:
        rep["issues"].append("首句画幅token缺失")
    pct_sum = None
    for p in ps:
        if "percent of the image is " in p.lower():
            pct_sum = sum(parse_percents(p))
            break
    rep["pct_sum"] = pct_sum
    if pct_sum is not None and not (95 <= pct_sum <= 105):
        rep["issues"].append(f"色盘百分数和 {pct_sum}（应为 100）")
    guard_para = next((p for p in ps if is_guard(p)), "")
    body = "\n\n".join(p for p in ps if not is_guard(p))
    # 母题原文写死了角色名（如 "Hatsune Miku"），换角色后必须清干净。
    # 泛化自早期只认 furina/miku 两条硬编码：现在按母题登记的 character 查，
    # 2432 个角色都适用。
    # ⚠ 判定「是同一个角色」不能逐词比对：手写 key 是简称（want_char="miku"，
    #   登记名是 "Hatsune Miku"），"hatsune" 对不上就会把当前角色自己报成残留。
    #   规则改成「候选词里任一个命中当前角色名 → 同一个角色，整组跳过」。
    if want_char and orig_char:
        names = _char_short_names(orig_char)
        if not any(n.lower() in want_char.lower() for n in names):
            for name in names:
                n = len(re.findall(rf"\b{re.escape(name)}\b", body))
                if n:
                    rep["issues"].append(f"正文残留原角色 {name} 字样 {n} 处")
    if want_char == "furina" and re.search(r"twin tail", body):
        rep["issues"].append("正文残留 twin tail（Furina 无此特征）")
    return rep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--list-costumes", action="store_true")
    ap.add_argument("--seed")
    ap.add_argument("--char", default="keep")
    ap.add_argument("--aspect", default="keep")
    ap.add_argument("--costume", default="auto")
    ap.add_argument("--out")
    a = ap.parse_args()

    if a.list:
        seeds, _ = load()
        for sid, s in seeds.items():
            print(f"{sid:34s} {s['words']:5d}w  {s['title']:26s} {s['character']}")
        return 0

    if a.list_costumes:
        load()
        for it in ALL_TPLS:
            print(f"   {it['id']:20s} {it['zh']:8s} {it.get('desc','')}")
        print(f"   共 {len(ALL_TPLS)} 套通用版型")
        return 0

    try:
        text, log = assemble(a.seed, a.char, a.aspect, a.costume)
    except AssembleError as exc:        # CLI 只在这里兜底；节点/HTTP 各自接 Exception
        print(f"  !! {exc}")
        return 2
    rep = validate(text, None if a.char == "keep" else a.char,
                   seed_branch(a.seed), seed_character(a.seed))
    print("\n".join("  " + x for x in log))
    print(f"  校验: {rep['words']} 词 / {rep['paras']} 段 / 色盘百分数和 {rep.get('pct_sum')}")
    for i in rep["issues"]:
        print("  ⚠ " + i)
    if a.out:
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print("  -> " + a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
