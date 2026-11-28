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

# ⚠ 这份模板是照 Miku 的双马尾写的 ——「the nearer length / the farther length」把头发写死成**两束**。
# 换角色只换 {hair} 这个词、结构不变，模型就照样画成两股马尾（用户报的「换人后变初音双马尾」）。
# 非双马尾角色改走下面这份：一个整体发团 + 一小缕上挑，不再承诺束数。
HAIR_TPL_SINGLE = (
    "Integrate {name}’s {hair} into the nearest monumental structure as one continuous falling mass. "
    "Its outer sweep drops past the closest structural edge, passes behind the dominant object, appears "
    "magnified and doubled inside one transparent panel, and reappears as three clean {accent} contours "
    "lying across the floor plane. A single narrow section lifts behind her head, crosses one horizontal "
    "band of the main structure, threads between two joints, and terminates as one thin {accent} contour "
    "beside the frame edge. Keep the mass dense, solid and recognizable around her head and down her back, "
    "falling loose from a single parting instead of being split to either side of the head; allow "
    "transparency, doubling and fragmentation only where the hair physically intersects transparent or "
    "reflective material."
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

# 指定了具名单品（lib: / char:）且版型为 auto 时，整段服装只写单品。
# 原因：版型模板（仪式礼服 / 流体褶裥…）比单品 tags 更具体、更靠前，两套衣服同一段里
# 打架 → 模型偏向版型，用户选的服装被压成局部元素（实测：露肩针织+百褶裙出成带礼帽的礼服）。
OUTFIT_ONLY_TPL = (
    "Dress {short} exactly in these garments and in nothing else: {tags}. "
    "Read them as ordinary clothing worn naturally, with every seam, cuff, hem and fold "
    "visible, and keep the silhouette that of normal daywear rather than ceremonial costume."
)
# 母题只要上半身（特写）→ 只写上衣，不提下装与鞋，也不说 "nothing else"
# （否则等于宣告她没有下半身衣服，模型很可能把取景往下拉去补裙子）
OUTFIT_ONLY_UPPER_TPL = (
    "Dress {short}'s upper body in only these garments: {tags}. Read every seam, cuff, "
    "neckline and fold as ordinary clothing rather than costume."
)
OUTFIT_ONLY_LOWER_TPL = (
    "Dress {short}'s lower body in only these garments: {tags}. Read every seam, hem and "
    "fold as ordinary clothing rather than costume."
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
# 指定单品 + 版型 auto 时用这版：不写 {cut} 剪裁（否则会随机套一套西装/礼服，
# 跟所选单品打架 —— 实测方形专辑选露肩针织+百褶裙，封面还是「利落西装式」）。
COSTUME_POSTER_ONLY_TPL = (
    "Dress {short}{scope} in only these garments, rendered as flat printed shapes rather than "
    "a three-dimensional garment: {tags}. Draw them in {design}, built from crisp {M1} and "
    "{M2} color planes with {accent} hairline seams and one small {block} registration "
    "block, kept secondary to the display typography."
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


# ---------------------------------------------------------------------------
# 锁定发色（面板「🔒 锁定发色」开关，2026-11-28）
# ---------------------------------------------------------------------------
# 色盘段把头发色按 14% 分配进整幅画面的色彩比例里，模型会照着比例给所有表面
# （包括头发）一起上色 —— 深紫发被压成灰紫、金发被环境色洗成白，都是这个原因。
# 开启后补一句硬声明：头发是**固定局部色**，不参与这套比例。
# 独立成句而不是改色盘段本身，是因为 lock_palette=true 的母题色盘段压根不替换，
# 改那里对它们无效。
HAIR_LOCK_SENT = (
    "Hold her hair to its exact color: {hair} keeps its precise hue, saturation and highlight "
    "structure across the whole frame. Treat the hair as a fixed local color that the surrounding "
    "palette may never tint, desaturate, bloom out, wash or re-grade, even where every other "
    "surface is pushed toward {primary} or toward the scene’s dominant grade. Every strand, tip, "
    "lock and brush stroke of that hair carries the same single color from root to end, so the "
    "scene’s cool blues, cyans and violet lights stay on its surfaces, rims and highlights while "
    "the hair itself holds one continuous hue."
)
_HAIR_LOCK_CUE = "Hold her hair to its exact color"


def apply_hair_lock(text: str, ch: dict, log: list[str], tag: str = "角色") -> str:
    """把发色从色彩比例里摘出来。幂等：已经写过就不再重复。"""
    ps = paras(text)
    if any(_HAIR_LOCK_CUE in p for p in ps):
        return text
    pal = ch.get("palette") or []
    primary = pal[0][0] if pal else "the surrounding palette"
    sent = HAIR_LOCK_SENT.format(hair=ch.get("hair_desc") or "her hair", primary=primary)
    # 优先贴身份句：那里才是「她的头发是什么颜色」的正主。
    # ⚠ 不能退到「第一个含 hair 的段」就算了 —— tag 流母题的首段也写 hair
    #   （唱片店：`short icy-blue bob hair`），贴上去会和角色的长发声明同段打架。
    idx = next((i for i, p in enumerate(ps) if "canonical identity" in p.lower()), -1)
    if idx < 0:
        idx = next((i for i, p in enumerate(ps)
                    if len(re.findall(r"\bpercent\b", p, re.I)) >= 3), -1)
    if idx < 0:
        idx = next((i for i, p in enumerate(ps) if "hair" in p.lower()), -1)
    if idx >= 0:
        ps[idx] = ps[idx].rstrip().rstrip(".") + ". " + sent
    else:
        ps.insert(min(1, len(ps)), sent)
    log.append(f"{tag}: 发色已锁定（不参与色彩比例）")
    return join(ps)


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
        if strong["hair"] < 0 and (
                (low.startswith(HAIR_STRONG) and ("hair" in low or "tail" in low))
                # "Let Miku's extremely long twin tails stream inland…" —— HAIR_STRONG 里只有
                # 「let her …」，换成角色名所有格就漏了；漏了之后弱信号会被前面那段**姿态描述**
                # 抢走（段里顺带一句 twin tails），结果姿态段被整段换成发型模板、真正的发型段
                # 原样留下 → 双马尾结构（both lengths / nearer / farther / two tails）全保留。
                # ⚠ 必须要求「所有格」：光看 "let " 会把 "Let the pale field make both tails…"
                # 这类**环境段**也吞进来（那句里的 tails 是头发，但主语是原野）。
                or (re.match(r"let\s+\S+['’]s\b", low)
                    and ("hair" in low[:80] or "tail" in low[:80]))):
            strong["hair"] = i
        if strong["costume"] < 0 and low.startswith(COSTUME_STRONG):
            strong["costume"] = i
        if strong["palette"] < 0 and low.startswith(PALETTE_STRONG) and "percent" in low:
            strong["palette"] = i
        if gfx < 0 and ("ink bloom" in low or "graphic language" in low):
            gfx = i

        # 弱信号只看**段首**：姿态段 / 环境段里顺带提一句 twin tails 不能算发型段
        if weak["hair"] < 0 and any(k in low[:60] for k in HAIR_WEAK) and (
                "hair" in low[:60] or "tail" in low[:60]):
            weak["hair"] = i
        if weak["costume"] < 0 and any(k in low for k in COSTUME_WEAK):
            weak["costume"] = i
        if weak["palette"] < 0 and any(k in low for k in PALETTE_WEAK):
            weak["palette"] = i

    def pick(k: str) -> int:
        return strong[k] if strong[k] >= 0 else weak[k]

    return pick("hair"), pick("costume"), pick("palette"), gfx


# ---------------------------------------------------------------- 服装句原地改写
# 母题正文自带的服装描述（"She wears a … dress" / tag 流里的 "wearing …"）与用户
# 显式选中的服装库单品会**互相打架**：模型偏向先出现、且贴着角色的那套，于是
# 「选了露肩针织 + 百褶裙，出图还是母题自带的吊带连衣裙」。
# 旧做法是把单品句追加到全文末尾 —— 在 400 词长文里等于同时给了两套衣服。
# 所以指定单品时必须**原地**把服装枚举换成单品清单（保留原句主语与动词，
# 语法不破、位置不变，服装仍然贴着角色）。
GARMENT_NOUNS = (
    "dress", "skirt", "blouse", "sweater", "cardigan", "shirt", "t-shirt", "tshirt",
    "uniform", "coat", "jacket", "robe", "kimono", "hoodie", "jeans", "trousers",
    "pants", "shorts", "socks", "stockings", "tights", "boots", "shoes", "loafers",
    "sandals", "sneakers", "heels", "apron", "swimsuit", "bikini", "leotard",
    "camisole", "tunic", "cloak", "gown", "corset", "outfit", "clothes", "clothing",
    "attire", "costume", "vest", "necktie", "gloves", "scarf", "bodice", "collar",
    "sleeve", "hem", "cuff", "ensemble", "loungewear", "knitwear",
    # 和风/民族/其它布料名词：实测母题里写 "in a yukata" / "a navy qipao" 都不在表里 → 漏改
    "yukata", "cheongsam", "hanfu", "sarong", "poncho", "tuxedo", "trench", "sundress",
    "hakama", "bloomers", "frock", "jumper", "pullover", "waistcoat", "suspenders",
    # ⚠ "top" 之前一直不在表里 —— 实测整条母题写 "white top / dark skirt" 却完全没被识别
    "top", "parka", "sweatshirt", "blazer", "qipao", "tracksuit", "sweatpants",
    # 腿部/袜类：短提示词母题里的 "black thighhighs" 一直漏网（不在表里 → 换装后
    # 还穿着原角色的过膝袜），补上后再由 GARMENT_RE 的 e?s 后缀吃掉复数
    "thighhigh", "thigh-high", "kneehigh", "knee-high", "pantyhose", "leggings",
    "legwear", "armwear", "headwear",
)
GARMENT_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(n) for n in GARMENT_NOUNS) + r")(?:e?s)?\b", re.I)
# 只认「穿」的动词，不认 "Dress Miku in …"（那是版型段，已经换过了）
GAR_MARK_RE = re.compile(
    r"\b(?:is\s+wearing|is\s+dressed\s+in|dressed\s+in|clad\s+in|wearing|wears)\b", re.I)
_SEG_RE = re.compile(r"[,;]|\.(?=\s|$)")
# 枚举段一旦以这些词头出现就不再是服装（"no SAM armor" / "keep the wear linear"）
_SEG_STOP_RE = re.compile(
    r"^(?:no|not|without|avoid|never|only|perfectly|keep|let|render|use|position|place|"
    r"camera|composition)\b", re.I)
# 枚举里换了话题（换成「她/画面/机位」当主语）就不再是同一串服装
_SEG_TOPIC_RE = re.compile(
    r"^(?:she|he|her|his|the (?:young )?(?:woman|girl|figure|character|body)|then|after|"
    r"before|while|when|as she|position|place|let|build|hold|add|show|lift)\b", re.I)
# 非服装段里出现这些动词 = 已经不在列衣服了
_SEG_VERB_RE = re.compile(
    r"\b(?:is|are|was|were|walks?|walking|stands?|standing|sits?|sitting|holds?|holding|"
    r"looks?|looking|turns?|turning|leans?|leaning|sells?|hangs?|hanging|drags?|drapes?|"
    r"falls?|falling|rests?|resting|waits?|waiting|listens?|speaks?)\b", re.I)
# 这些 tag 是姿势/状态，不是服装 —— 塞进 "wears …" 会变成 "She wears crossed legs"
# 既不是服装也不是姿势的 tag（动作 / 天气 / 场景），写进服装句会变成 "she wears holding umbrella"
_DROP_TAG_RE = re.compile(
    r"^(?:holding|carrying|sitting|standing|walking|leaning|looking|waiting|smiling|"
    r"sleeping|lying|kneeling|reaching|pointing)\b|\b(?:sunny|rainy|snowy|cloudy) day\b",
    re.I)
# 头饰永远保留：戴在头上，不进画面下方，且是角色识别度的一部分（furina 的高帽）
_HEADWEAR_RE = re.compile(r"\b(?:hat|cap|beret|headband|headpiece|hairband|halo|crown|"
                          r"headdress|tiara|veil)\b", re.I)
_POSE_TAGS = {"crossed legs", "sitting", "standing", "lying on back", "on back",
              "on stomach", "legs up", "hands behind back", "arms behind back"}
_DRESSISH = ("dress", "gown", "robe", "kimono", "one-piece", "overall")


def _garment_span(text: str, m) -> int:
    """从「穿」的动词之后，一直吃到最后一个像服装的枚举段，返回结束偏移。

    ⚠ 不能「连续两段不是服装就停」：实测 "uniform: coat, collar, blouse,
    ribbon bow, identification badge, skirt, tights, shoes" 里夹着 bow / badge
    两段非服装，早停会把后半套（裙子、鞋）留在正文里。
    改成「只要后面还有服装就继续，碰到句子/换主语/动词段才收」。
    """
    pos = end = m.end()
    gap = 0
    while pos < len(text):
        sep = _SEG_RE.search(text, pos)
        stop = sep.start() if sep else len(text)
        seg = text[pos:stop].strip()
        if seg:
            is_garment = bool(GARMENT_RE.search(seg))
            if is_garment:
                # 段里有服装名词就consume —— "clean white sneakers" 不能被 clean 挡掉
                if re.match(r"^(?:no|not|without|avoid|never)\b", seg, re.I):
                    break
                end, gap = stop, 0
            else:
                if _SEG_STOP_RE.match(seg) or _SEG_TOPIC_RE.match(seg):
                    break
                gap += 1
                # 非服装段里带动词 = 已经换话题（"walking through the market …"）
                if gap >= 4 or _SEG_VERB_RE.search(seg):
                    break
        if not sep or sep.group() == ".":
            break
        pos = sep.end()
    return end


def _drop_garment_clauses(s: str) -> tuple[str, int]:
    """摘掉含服装名词的逗号项（"aqua eyes, very long hair, detached sleeves, youthful …"）。"""
    chunks = s.split(", ")
    keep, dropped = [], 0
    for c in chunks:
        if GARMENT_RE.search(c) and not _PROP_CUE.search(c) and "identity" not in c.lower():
            dropped += 1
        else:
            keep.append(c)
    if not dropped:
        return s, 0
    out = ", ".join(keep)
    out = re.sub(r",\s*and\b", ", and", out)
    out = re.sub(r"(,\s*)+", ", ", out)
    out = re.sub(r"\s*,\s*\.", ".", out)
    return out, dropped


def costume_free_char(ch: dict, log: list[str] | None = None) -> dict:
    """选了服装库单品时，把身份的「原作服装」剥掉，只留脸 / 发型 / 眼睛 / 轮廓。

    不剥的后果实测：方形海报给 furina 选露肩针织，出图还是全套礼仪服 + 深蓝高帽
    —— identity 里写着 "her recognizable … ceremonial outfit"，guard 里还钉着
    "no missing top hat"，两句都比服装指令更硬。

    手写角色可以在 characters.json 里直接给 `identity_plain` / `guard_plain`（更精确）；
    没有就走通用剥离：删掉带服装名词的逗号项 + 护盾里带服装的条目。
    """
    log = log if log is not None else []
    out = dict(ch)
    if ch.get("identity_plain"):
        out["identity"] = ch["identity_plain"]
    else:
        new, k = _drop_garment_clauses(ch.get("identity", ""))
        if k:
            out["identity"] = new
            log.append(f"角色: 身份句里的原作服装已剥离 {k} 项")
    if ch.get("guard_plain"):
        out["guard"] = ch["guard_plain"]
    else:
        items = [x.strip() for x in (ch.get("guard") or "").split(",") if x.strip()]
        kept = [x for x in items if not GARMENT_RE.search(x)]
        if len(kept) != len(items):
            out["guard"] = ", ".join(kept)
            log.append(f"角色: 护盾里「no missing 服装」已去掉 {len(items) - len(kept)} 条")
    return out


def garment_tags(tags: list[str] | None) -> tuple[list[str], list[str]]:
    """把单品 tags 拆成 (服装, 姿势)。

    Anima 服装库是 tag 袋，里面混着 "crossed legs" 这类姿势/状态 tag。
    写进 "She wears …" 会变成「她穿着盘腿」，所以这里先分流：姿势交回母题。
    """
    body, pose = [], []
    for t in tags or []:
        t = (t or "").strip()
        if not t:
            continue
        low = t.lower()
        if low in _POSE_TAGS:
            pose.append(t)
        elif _DROP_TAG_RE.search(low):
            pose.append(t)          # "holding umbrella" / "sunny day" 之类，既不是衣服也不是姿势
        else:
            body.append(t)
    return body, pose


# ---------------------------------------------------------------- 按部位拆分
# 服装库的 tag 是平铺的（"white off-shoulder sweater / black pleated skirt /
# brown loafers"），整套写进提示词会出事：
#   · 方形专辑是上半身特写 → 写了裙子+鞋，模型把取景往下拉，画出腿和鞋；
#   · 展纸母题写的是连衣裙、没写鞋 → 补了乐福鞋后，构图变成坐窗台双腿垂下。
# 所以按部位拆开，只写「母题本身描述到的部位」。
#   上装 upper / 下装 lower / 连衣裙 dress（=上+下）/ 腿部 leg / 鞋子 foot / 配饰 acc
_ZONE_ORDER = ("upper", "dress", "lower", "leg", "foot", "acc")
_ZONE_KW = {
    "dress": ("camisole dress", "slip dress", "apron dress", "sundress", "dress", "gown",
              "kimono", "yukata", "robe", "qipao", "cheongsam", "hanfu", "one-piece",
              "jumpsuit", "overalls", "bodysuit", "leotard", "babydoll", "lingerie",
              "nightgown", "teddy",
              # 2026-11-24 补：全身/连体的几种写法，原来一律判 style 挂空、整组丢失
              "bodystocking", "strapless", "pajama",
              # 泳装：Anima 里 "striped bikini" / "white print bikini" / "one-piece swimsuit"
              # 都是常见官方皮肤标签，判不出部位就整组被丢（泳装角色只剩 halo）
              "bikini", "swimsuit"),
    "foot": ("boots", "boot", "shoes", "shoe", "loafers", "sneakers", "sandals", "heels",
             "pumps", "mary jane", "oxfords", "flats", "mules", "slippers", "geta",
             "footwear", "barefoot", "tabi"),
    "leg": ("thighhigh", "thigh-high", "kneehigh", "knee-high", "knee socks", "ankle socks",
            "tights", "stockings", "socks", "pantyhose", "garter", "leg warmers", "legwear",
            "thigh strap", "bare legs"),
    "lower": ("skirt", "pants", "trousers", "jeans", "shorts", "leggings", "culottes",
              "slacks", "bloomers", "hakama", "panties", "underwear"),
    "upper": ("sweater", "cardigan", "blouse", "t-shirt", "shirt", "turtleneck", "hoodie",
              "jacket", "coat", "camisole", "bodice", "jersey", "parka", "blazer",
              "tunic", "polo", "apron", "corset", "cape", "cloak", "uniform", "suit",
              "vest", "top", "tee", "bra", "wrap",
              # 2026-11-24 补：兜帽 / 衣领 / 泛指的 clothes / 盔甲。这几个词在
              # GARMENT_NOUNS 里早就有（用于句子识别），却没进制部位判定，
              # 于是 sayu 的 "animal hood"、passionlip 的 "belt collar" 全被丢掉。
              # ⚠ 故意不加 "sleeve"：袖子是主衣的附属描述，判成独立 upper 后
              #   会在「裙子优先」的挑选里被挤掉（甘雨的 detached sleeves 就会消失）。
              "hood", "collar", "clothes", "armor"),
    "acc": ("necklace", "choker", "earring", "bracelet", "bag", "tote", "gloves", "scarf",
            "belt", "hat", "cap", "beret", "headband", "hairband", "headphones",
            "headset", "glasses", "suspenders", "ribbon", "piercing",
            # 2026-11-24 补：同样只在 GARMENT_NOUNS 里、没进部位表的两类配饰
            "veil", "necktie"),
}
# 取景：只看到上半身的母题，别再往下写
_FRAME_UPPER = re.compile(
    r"\b(?:close-up|close up|head and shoulders|upper chest|upper body|bust shot|"
    r"waist[- ]up|chest[- ]up|cropped at the (?:waist|hip)|from the chest|portrait crop|"
    r"face and shoulders|half[- ]length portrait)\b", re.I)
_FRAME_FULL = re.compile(
    r"\b(?:full[- ]body|head to toe|whole body|entire figure|full[- ]length|"
    r"from head to (?:toe|foot)|standing on|her feet|both feet|sitting on|legs (?:dangl|hang))\b",
    re.I)


# 短关键词必须整词匹配：acc 里的 "cap" 会吃掉 "cape"（披风被判成帽子 → 该角色
# 只有 acc、没有上装，装配时整组服装被清空，静默回落随机版型）。
# 长关键词保留子串匹配，"sundress" / "belted" / "overshoes" 这类复合词才不会漏。
_SHORT_KW = 3


def _kw_hit(k: str, low: str) -> bool:
    if len(k) > _SHORT_KW:
        return k in low
    return re.search(r"(?<![a-z])" + re.escape(k) + r"(?:s|es)?(?![a-z])", low) is not None


# acc 里的长词（belt / suspenders / scarf / gloves…）会抢走同一 tag 里的上装：
# "belted coat" → 被 "belt" 判成配饰 → 该角色整条上装丢失（和 cape 那个 bug 同源）。
# 所以 acc 只在「没命中上装长词」时才生效；"top hat" 里 "top" 是 3 字母短词、
# 不算 core，仍然规规矩矩归 acc。
_CORE_UPPER_KW = tuple(k for k in _ZONE_KW["upper"] if len(k) > _SHORT_KW)


def zone_of_tag(tag: str) -> str:
    """单条 tag → 部位；认不出返回 "style"（材质/风格词，跟着前一件衣服走）。

    ⚠ 顺序有意义：
      1. dress/foot/leg/lower 先判 —— 这几个部位不会被配饰词误伤；
      2. acc 次之，但要给「上装主体」让位（"belted coat" / "suspenders jacket"）；
      3. upper 最后 —— 否则 "top hat" 会被 upper 的 "top" 抢走。
    """
    low = (tag or "").lower()
    for zone in ("dress", "foot", "leg", "lower"):
        if any(_kw_hit(k, low) for k in _ZONE_KW[zone]):
            return zone
    if any(_kw_hit(k, low) for k in _CORE_UPPER_KW):
        return "upper"
    if any(_kw_hit(k, low) for k in _ZONE_KW["acc"]):
        return "acc"
    if any(_kw_hit(k, low) for k in _ZONE_KW["upper"]):
        return "upper"
    return "style"


def zone_map(tags: list[str] | None) -> dict[str, list[str]]:
    """tags → {部位: [tag…]}，顺序按 _ZONE_ORDER；认不出的挂到前一件同部位的后面。"""
    out: dict[str, list[str]] = {}
    last = last_core = first_core = ""
    for t in tags or []:
        t = (t or "").strip()
        if not t:
            continue
        z = zone_of_tag(t)
        if z == "style":
            # "knitwear" / "long sleeves" 这类修饰词描述的是主体那件衣服，挂到**第一件**
            # 核心服装（上装优先）上；挂「最近一件」会跑到裙子上、挂鞋上更离谱
            z = first_core or last_core or last
            if not z:
                continue
        else:
            last = z
            if z in ("upper", "lower", "dress"):
                last_core = z
                if not first_core:
                    first_core = z
        out.setdefault(z, []).append(t)
    return {z: out[z] for z in _ZONE_ORDER if z in out}


def frame_zones(text: str) -> set[str]:
    """取景决定「这条母题要写哪些部位」。

    特写（close-up / upper chest）→ 只上装；全身（full body / 站在地上 / 脚）→ 全写；
    其余默认只写核心部位（上装 + 下装）：宁可多写一套下装，也不要把裙子丢掉。
    """
    if _FRAME_UPPER.search(text) and not _FRAME_FULL.search(text):
        return {"upper"}
    if _FRAME_FULL.search(text):
        return {"upper", "lower", "leg", "foot"}
    return {"upper", "lower"}


def motif_zones(motif_text: str, log: list[str] | None = None) -> set[str]:
    """母题正文里「她自己穿的衣服」涉及哪些部位。

    只看同时满足「有服装名词」且「像在描述她」的句子（带 wears / her / 两个以上服装名词），
    避免把室内描述里的 "coat hooks"、道具 "scarf" 算进来。
    母题完全没写服装时，退回取景线索（特写 → 只上装）。
    """
    log = log if log is not None else []
    text = motif_text or ""
    zones: set[str] = set()
    for s in _SENT_SPLIT.split(text):
        if not GARMENT_RE.search(s) or _PROP_CUE.search(s):
            continue
        low = s.lower()
        if not (GAR_MARK_RE.search(s) or re.search(r"\b(?:her|his|she)\b", low)
                or len({m.group(0).lower() for m in GARMENT_RE.finditer(s)}) >= 2):
            continue
        for zone, kws in _ZONE_KW.items():
            if any(k in low for k in kws):
                zones.add(zone)
    frame = frame_zones(text)
    if zones:
        # 特写取景 → 只写上半身（母题提到配饰才带配饰）；
        # 其余情况以取景的「核心部位」为准，母题描述只补腿/鞋/配饰这类外围部位。
        # ⚠ 旧写法只看「母题提到哪些部位」：影院门外只写了 "coat collar pulled up"，
        #   于是整条裙子被判定为「不需要」而丢掉。
        if frame == {"upper"}:
            return {"upper"} | (zones & {"acc"})
        return zones | frame
    return frame


def select_outfit(tags: list[str] | None, zones: set[str],
                  log: list[str] | None = None) -> tuple[list[str], str]:
    """按母题需要的部位挑单品 → (要写的 tags, 模式 upper / lower / full)。

    规则：
      · 母题写连衣裙 → 优先用服装库的连衣裙；服装库只有上下装就拆成「上装 + 下装」；
      · 母题只写上半身（特写）→ 只写 upper（连衣裙也算 upper）；
      · 腿 / 鞋 / 配饰只在母题自己提到时才写；
      · 母题需要的部位在服装库里是空的 → 该部位不写（用户确认的口径）。
    """
    log = log if log is not None else []
    zm = zone_map(tags)
    if not zm:
        return [], "full"
    want_dress = "dress" in zones
    want_up = ("upper" in zones) or want_dress
    want_lo = ("lower" in zones) or want_dress
    if want_lo and not want_up:
        want_up = True                 # 只写裙子 → 上身留空，补上装
        log.append("服装: 母题只提到下装 → 顺带补上装，避免上身留空")

    dress = list(zm.get("dress", []))
    picked: list[str] = []
    if dress and (want_up or want_lo):
        picked += dress
    else:
        if want_up:
            picked += zm.get("upper", [])
        if want_lo:
            picked += zm.get("lower", [])
    if "leg" in zones:
        picked += zm.get("leg", [])
    if "foot" in zones:
        picked += zm.get("foot", [])
    if "acc" in zones:
        picked += zm.get("acc", [])
    else:
        # 母题没提配饰，但头饰（高帽/贝雷帽）是角色识别度的一部分，且永远在画面内。
        # 同一个帽子在 Anima 数据里常有 "top hat" + "blue hat" 两条 → 只留第一条
        for t in zm.get("acc", []):
            if _HEADWEAR_RE.search(t):
                picked.append(t)
                break

    only_up = want_up and not (want_lo or "leg" in zones or "foot" in zones)
    mode = "upper" if only_up else "full"
    seen, out = set(), []
    for t in picked:
        if t not in seen:
            seen.add(t)
            out.append(t)
    missing = [z for z in ("upper", "lower", "leg", "foot", "acc")
               if z in zones and not zm.get(z) and not (z in ("upper", "lower") and dress)]
    if missing:
        log.append(f"服装: 服装库缺部位 {', '.join(missing)} → 该部位不写")
    return out, mode


def prepare_outfit(outfit_tags: list[str] | None, motif_text: str,
                   log: list[str] | None = None) -> tuple[list[str] | None, str]:
    """三个分支共用：姿势过滤 → 部位判定 → 只保留母题需要的部位。

    服装库单品（lib）与角色官方服装预设（char）都走这条路，所以官方服装同样会按部位拆。
    """
    log = log if log is not None else []
    g_tags, p_tags = garment_tags(outfit_tags)
    if p_tags:
        log.append(f"服装: 姿势类 tag 不进服装句 → {', '.join(p_tags)}")
    if not g_tags:
        return None, "full"
    zones = motif_zones(motif_text, log)
    picked, mode = select_outfit(g_tags, zones)
    if not picked:
        # 空结果分两种：真的没有交集（母题只要上半身、包里只有裙），和
        # **这套预设压根没有衣服**（全是角/手套/弓这类身份与配饰 —— 词频统计的
        # 典型产物）。后者不是装配能修的，必须回数据层补服装，所以日志要分开写，
        # 否则用户永远只看得到「没有交集」，以为插件坏了。
        zm = zone_map(g_tags)
        if not (set(zm) & {"upper", "lower", "dress", "leg", "foot"}):
            log.append(f"服装: 这套预设里一件真正的衣物都没有（{' / '.join(g_tags[:5])}）"
                       " → 需要修该角色的服装预设，装配层补不了")
        else:
            log.append("服装: 服装库与母题部位没有交集 → 不写服装句")
        return None, "full"
    dropped = [t for t in g_tags if t not in picked]
    if dropped:
        log.append(f"服装: 按部位只写 {len(picked)} 条（略过 {len(dropped)} 条："
                   f"{', '.join(dropped[:4])}{'…' if len(dropped) > 4 else ''}）")
    if mode == "upper":
        log.append("服装: 母题只要上半身 → 不写裙/袜/鞋")
    return picked, mode


def swap_garments(text: str, tags: list[str], only: bool = True,
                  log: list[str] | None = None, limit: int = 3) -> tuple[str, int]:
    """把母题自带的服装枚举原地换成单品，返回 (新正文, 替换处数)。

    "She wears a … dress." → "She wears only these garments: …."
    只换动词后面那串服装，主语/动词沿用原文，所以段落语法与位置都不动。
    """
    log = log if log is not None else []
    body_tags = [t for t in tags if t and t.strip().lower() not in _POSE_TAGS]
    pose_tags = [t for t in tags if t and t.strip().lower() in _POSE_TAGS]
    if not body_tags:
        return text, 0
    if pose_tags:
        # 姿势类 tag 只属于 Anima 的 tag 流；进了 "wears …" 会变成「她穿着盘腿」，
        # 而且会和母题自己的构图抢姿势。构图归母题，这里只取服装。
        log.append(f"服装: 单品里的姿势类 tag 不进正文 → {', '.join(pose_tags)}")
    body = ", ".join(body_tags[:14])
    n = 0
    out_ps = []
    for p in paras(text):
        if n >= limit:
            out_ps.append(p)
            continue
        pos = 0
        while n < limit:
            m = GAR_MARK_RE.search(p, pos)
            if not m:
                break
            end = _garment_span(p, m)
            if end <= m.end():          # 后面不是服装（"instead of wearing them"）
                pos = m.end()
                continue
            rep = f"{m.group()} {'only ' if only else ''}these garments: {body}"
            p = p[:m.start()] + rep + p[end:]
            pos = m.start() + len(rep)
            n += 1
        out_ps.append(p)
    return join(out_ps), n


def neutralize_dress(text: str, tags: list[str]) -> tuple[str, int]:
    """所选单品里没有裙装 → 正文残留的 "the dress" 改称 "the outfit"，免得两套衣服并存。"""
    if any(k in (t or "").lower() for t in tags for k in _DRESSISH):
        return text, 0
    pat = re.compile(r"\b(the|her|The|Her|this|that)\s+(?:[a-z][a-z\-]+\s+){0,2}dress\b")
    out, n = pat.subn(lambda m: f"{m.group(1)} outfit", text)
    return out, n


# ---- 服装改写的四类写法 --------------------------------------------------
# 实测：只有「带穿字动词」那一类被旧代码处理过，另外三类会让旧衣服照样画出来。
#   ① "She wears a … dress."                    —— 动词法（保留主语+动词，原地换宾语）
#   ② "A dark navy coat hangs open over it."    —— 衣服自己做主语
#   ③ 整段都在讲服装（海报 "Let the clothing behave like clothing: …"）
#   ④ tag 流里夹着的裸单品（"sailor school uniform, pleated skirt, …"）
_GARMENT_ONLY_UPPER_TPL = OUTFIT_ONLY_UPPER_TPL
_GARMENT_ONLY_LOWER_TPL = OUTFIT_ONLY_LOWER_TPL
_GARMENT_ONLY_TPL = (
    "Dress {short} in only these garments: {tags}. Keep every seam, cuff and hem visible "
    "so the fabric catches the light and reads as ordinary clothing."
)
_GARMENT_SPECIFIC_TPL = (
    "Dress {short} in these specific garments: {tags}. Keep every seam, cuff and hem visible."
)
_GARMENT_SPECIFIC_UPPER_TPL = (
    "Dress {short}'s upper body in these specific garments: {tags}. Keep every seam, cuff and "
    "neckline visible."
)
_GARMENT_SPECIFIC_LOWER_TPL = (
    "Dress {short}'s lower body in these specific garments: {tags}. Keep every seam, hem and "
    "fold visible."
)


# 外套类体积大，靠在窗台/栏杆上容易穿模（实测：官方蓝外套 + 高帽那一套压在石窗台上，
# 袖子直接穿进石头里）。选中外套时补一句接触点收尾，让布料停在接触面。
_BULKY_RE = re.compile(r"\b(?:jacket|coat|trench|cloak|cape|parka|blazer|robe|cardigan|"
                       r"armor|overcoat)\b", re.I)
_CLIP_GUARD = (" Keep the garment volume clear of every surface she leans on or rests "
               "against, so sleeves, cuffs and hems stop at the contact instead of "
               "passing through it.")


def outfit_directive(short: str, body: str, mode: str = "full", only: bool = True) -> str:
    """按部位选模板：full / upper / lower。"""
    if mode == "upper":
        out = (_GARMENT_ONLY_UPPER_TPL if only else _GARMENT_SPECIFIC_UPPER_TPL).format(
            short=short, tags=body)
    elif mode == "lower":
        out = (_GARMENT_ONLY_LOWER_TPL if only else _GARMENT_SPECIFIC_LOWER_TPL).format(
            short=short, tags=body)
    else:
        out = (_GARMENT_ONLY_TPL if only else _GARMENT_SPECIFIC_TPL).format(
            short=short, tags=body)
    if _BULKY_RE.search(body):
        out += _CLIP_GUARD
    return out
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
# 衣架 / 衣柜 / 货架 —— 服装是场景道具，不是穿在她身上的
_PROP_CUE = re.compile(r"\b(?:rack|shelf|shelves|hanger|mannequin|wardrobe|dresser|laundry|"
                       r"basket|pile|stack|display case|boutique|tailor shop|cd sleeve|"
                       r"vinyl sleeve|album sleeve|record sleeve|jewel case|photobash)\b", re.I)
# 多套装扮属于设计项（四格反射各穿一套），统一成一套反而毁构图
# ⚠ 不能只写 "reflection of"：材料段里的 "no reflection of a body" 会被误判整段跳过
_SCENE_CUE = re.compile(r"\b(?:reflections? of (?:her|him|the character|Hatsune|Miku)|"
                        r"each in a different|facet (?:one|two|three|four))\b", re.I)
_FINITE_RE = re.compile(r"\b(?:is|are|was|were|has|have|had|will|would|can|could|may|might|"
                        r"must|should|does|do|did|stands|sits|hangs|lies|wears|keeps|reads|"
                        r"runs|holds|rests|cuts|covers)\b", re.I)


def _clause_stats(s: str) -> tuple[int, int]:
    """→ (子句总数, 含服装名词的子句数)。"""
    clauses = [c.strip() for c in re.split(r"[,;]", s) if c.strip()]
    if not clauses:
        return 0, 0
    return len(clauses), sum(1 for c in clauses if GARMENT_RE.search(c))


def _is_tag_stream(s: str) -> bool:
    """纯 tag 流：>=6 个子句、平均子句 <=12 词、没有限定动词（散文不算）。"""
    n, _g = _clause_stats(s)
    if n < 6 or len(s.split()) / n > 12:
        return False
    return not _FINITE_RE.search(s)


_HER_RE = re.compile(r"\b(?:her|hers|she|herself)\b", re.I)


# 结构/材质/光线段的段首动词 —— 这些段落里的 scarf/cloak 往往是画面主体，不是她穿的
_STRUCT_PARA = re.compile(
    r"^(?:construct|build|print|let|add|assign|hold|separate|light|compose|render|use|"
    r"show|make|give|drive|finish|treat|define|establish|layer|tone|grade|etch|inset|"
    r"cast|carve|repeat|extend|run|carry|include|push|pull|raise|drop|leave|retain|"
    r"maintain|reserve|limit|confine|reduce|increase|open|close|fill|set|frame|place|"
    r"position|mask|erase|grade)\b", re.I)

# 「Preserve her recognizable A, B, and C.」= 角色特征列举句（外貌和服装混写）。
# _STRUCT_PARA 只按**段落首词**判定结构段，段落以 "Give …" / "Keep …" 开头时会把
# 后面的身份列举句一起按 need_is（只摘 "her dress is heavy cotton"）放过 —— 镜潮歌剧
# 6 个服装子句因此一个都没摘掉。这类句子要单独认出来，按普通服装句处理。
_KEEP_LIST_RE = re.compile(r"^(?:preserve|keep|retain|maintain)\s+(?:her|his)\b", re.I)


def _excise_clauses(s: str, require_her: bool = False,
                    need_is: bool = False) -> tuple[str, int]:
    """删掉含服装名词的子句。

    `require_her` = 散文里只摘「她的衣服」那些子句（"her dress is heavy cotton"），
    不动道具/巨构（"one deep red knitted length of scarf" —— 那是画面主体，不是她穿的）。
    tag 流不需要这条：tag 里的单品默认就是穿在角色身上的。
    """
    parts = re.split(r"([,;])", s)
    out, dropped, i = [], 0, 0
    while i < len(parts):
        cl = parts[i]
        sep = parts[i + 1] if i + 1 < len(parts) else ""
        # 裸名词短语（"coat collar pulled up" / "white top and dark skirt"）没有主语，
        # 不该被 require_her 挡住；只有**成句**（带限定动词）的才要求提到她
        full_clause = bool(_FINITE_RE.search(cl))
        hit = (cl.strip() and GARMENT_RE.search(cl) and not _PROP_CUE.search(cl)
               and (not require_her or not full_clause or _HER_RE.search(cl))
               # need_is：只摘「her dress is heavy cotton」这类材质指派，
               # 放过「her boots and her striding legs」这种构图序列
               and (not need_is or re.search(r"\bis\b|\bare\b", cl)))
        if hit:
            dropped += 1
        else:
            out.append(cl + sep)
        i += 2
    txt = "".join(out)
    txt = re.sub(r"[,;]\s*(?=[,;.]|$)", "", txt)
    txt = re.sub(r"^\s*[,;]+\s*", "", txt)
    txt = re.sub(r"(\s*,\s*)+", ", ", txt)
    return txt.strip(" ;,"), dropped


# 衣服常以「介词 + 冠词 + 名词」的形式塞在场景/姿势句里：
#   "standing on the grassy slope of a river embankment at night in a yukata"
#   "waiting outside a cinema after rain, coat collar pulled up"
# 这类写法整句并不「都在讲衣服」，按整句/子句处理都会漏 → 单独做介词短语替换。
# ⚠ 修饰词位不能吃进功能词：否则 "scuffed in a broad arc where boots have turned"
#   会被当成「穿着一双靴子」，替换成 "in the selected outfit" 把句子搞烂。
_INLINE_ADJ = (r"(?!(?:where|which|that|who|and|or|of|with|in|on|at|for|to|from|under|"
               r"over|near|beside|above|below|is|are|was|were)\b)[a-z][a-z\-]+\s+")
_INLINE_GARMENT_RE = re.compile(
    r"(?P<pre>\s+(?:in|wearing|dressed in|clad in)\s+)"
    r"(?:(?:a|an|the|her|his|their)\s+)?"
    r"(?:" + _INLINE_ADJ + r"){0,3}(?:"
    + "|".join(re.escape(n) for n in GARMENT_NOUNS) +
    r")(?:e?s)?\b", re.I)
# 这些是「空间定位」不是穿着（in front of her boots / near the coat hooks）
_SPATIAL_CUE = re.compile(
    r"\b(?:front of|behind|beside|near|next to|left of|right of|edge of|top of|bottom of|"
    r"middle of|shadow of|light of|hooks?)\b", re.I)
_DIRECTION_CUE = re.compile(r"^\s*(?:left|right|corner|half|third|quarter|edge|frame|"
                            r"canvas|image)", re.I)


_ZONE_WORD = {"upper": "her top", "lower": "her skirt", "foot": "her footwear",
              "leg": "her legwear", "dress": "her outfit", "acc": "her accessory"}
_OWNER_GARMENT_RE = re.compile(
    r"\b(?:her|his)\s+(?:[a-z][a-z\-]+\s+){0,2}(?:"
    + "|".join(re.escape(n) for n in GARMENT_NOUNS) + r")(?:e?s)?\b", re.I)


# "the coat's collar" / "her dress's hem" —— 所有格形式，之前只处理 "her coat" 漏了带 's 的
_POSS_GARMENT_RE = re.compile(
    r"\b(?:the|her|his)\s+(?:[a-z][a-z\-]+\s+){0,2}(?:"
    + "|".join(re.escape(n) for n in GARMENT_NOUNS) + r")(?:e?s)?['’]s\b", re.I)


def neutralize_owner_garments(p: str) -> tuple[str, int]:
    """「她的浴衣下摆」「她的木屐」这类所有格写法 → 按部位换成泛称。

    它们藏在构图/光线段里（"then her wooden sandals and the hem of her yukata"），
    整段是讲画面结构的，不能删；但衣服已经换了，把名词换成"她的上衣/鞋/裙"即可。
    """
    def rep(m):
        z = zone_of_tag(m.group(0))
        return _ZONE_WORD.get(z, "her outfit")
    out, n = _POSS_GARMENT_RE.subn("the outfit's", p)      # 先处理 "the coat's"
    out, k = _OWNER_GARMENT_RE.subn(rep, out)
    return out, n + k


# ---------------------------------------------------------------------------
# LORA 服装触发词模式（v1.19.6）
# ---------------------------------------------------------------------------
# 角色 LORA 自己带整套服装的触发词时，提示词里任何服装词都会跟它抢：
# 服装库单品 / 版型句 / 母题自带的 "heavy charcoal wool coat" 全都要让位，
# 否则出图是「LORA 的衣服 + 母题的外套」缝在一起。
# 做法：服装段整段换成 NO_OUTFIT_SEG，全文按逗号项摘掉服装枚举，
# 护盾里「no missing 礼帽」这类服装否定项也去掉（服装已经不归提示词管）。
NO_OUTFIT_SEG = ("Let her character trigger carry what she wears: read one soft unbroken "
                 "silhouette from shoulders to feet, its folds and edges shaped only by "
                 "light, shadow and material grain.")
# ⚠ 不能直接拿 GARMENT_RE 扫正文：表里有 "top"，`the top edge of the frame` 会被当成
#   衣服整项摘掉（实测 34 条母题误伤）。"top" 只在带颜色/款式修饰词时才算上衣。
_LORA_GARMENT_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(n) for n in GARMENT_NOUNS if n != "top")
    + r")(?:e?s)?\b"
    r"|\b(?:white|black|dark|blue|red|pale|cropped|crop|knit|tank|tube|halter|mesh|silk|"
    r"velvet|pleated|collared)\s+tops?\b", re.I)
_GARMENT_OR_HEAD_RE = re.compile(
    _LORA_GARMENT_RE.pattern + "|" + _HEADWEAR_RE.pattern, re.I)
_PCT_RE = re.compile(r"(?P<num>[a-z\-]+|\d+)(?=\s+percent)", re.I)


_ASPECT_CLAUSE = re.compile(r"^(?:Create|Square|Portrait|Horizontal|Vertical)\b", re.I)


def _drop_clauses_rx(q: str, rx) -> tuple[str, int]:
    """逗号枚举里含 rx 的整项摘掉（同 _drop_garment_clauses，只是换正则）。

    ⚠ 首句头一个子句（`Create a wide 16:9 … titled “SCARF”`）必须保住：
    标题本身可能就叫 SCARF / COAT，被当成服装摘掉会让首句丢画幅 token。
    """
    chunks = q.split(", ")
    keep = [c for c in chunks if not rx.search(c) or _ASPECT_CLAUSE.match(c.strip())]
    if len(keep) == len(chunks):
        return q, 0
    out = ", ".join(keep)
    out = re.sub(r",\s*and\b", ", and", out)
    out = re.sub(r"(,\s*)+", ", ", out)
    out = re.sub(r"\s*,\s*\.", ".", out)
    return out, len(chunks) - len(keep)


def _renormalize_palette(p: str) -> str:
    """摘掉「十二 percent 是她的外套」之后色盘和不再等于 100 → 按比例归一。

    原文百分比是英文数字词（thirty-two percent），所以要 words2num 反解再 num2words 写回。
    """
    ms = list(_PCT_RE.finditer(p))
    vals = []
    for m in ms:
        tok = m.group("num")
        v = int(tok) if tok.isdigit() else words2num(tok)
        if v is None:
            return p
        vals.append(v)
    if not vals or sum(vals) == 100:
        return p
    total = sum(vals)
    scaled = [max(1, round(v * 100 / total)) for v in vals]
    # 最大余数法补到正好 100（否则 99/101 会被 validate 抓）
    while sum(scaled) != 100:
        diff = 100 - sum(scaled)
        order = sorted(range(len(scaled)),
                       key=lambda i: vals[i] * 100 / total - scaled[i],
                       reverse=diff < 0)
        moved = False
        for idx in order:
            if diff > 0:
                scaled[idx] += 1
                moved = True
                break
            if scaled[idx] > 1:
                scaled[idx] -= 1
                moved = True
                break
        if not moved:
            break
    out, last = [], 0
    for m, v in zip(ms, scaled):
        out.append(p[last:m.start()])
        out.append(str(v) if m.group("num").isdigit()
                   else ("one hundred" if v == 100 else num2words(v)))
        last = m.end()
    out.append(p[last:])
    return "".join(out)


def strip_all_garments(text: str, log: list[str]) -> str:
    """LORA 模式下的收尾：把正文里剩下的服装词清干净（姿态 / 解剖词一个不动）。"""
    out, n_own, n_drop, n_guard, n_pct = [], 0, 0, 0, 0
    for p in paras(text):
        if p.strip() == NO_OUTFIT_SEG:
            out.append(p)
            continue
        q, c = neutralize_owner_garments(p)          # 先处理所有格 / 单数提及
        n_own += c
        if is_guard(p):
            keep = []
            for i, it in enumerate(x.strip() for x in q.split(",") if x.strip()):
                if i and _GARMENT_OR_HEAD_RE.search(it):
                    n_guard += 1
                    continue
                keep.append(it)
            q = ", ".join(keep)
        else:
            q, c2 = _drop_clauses_rx(q, _LORA_GARMENT_RE)
            n_drop += c2
            if "percent of the image" in q.lower():
                before = q
                q = _renormalize_palette(q)
                n_pct += q != before
        out.append(q if len(q.split()) >= 6 else NO_OUTFIT_SEG)
    body = join(out)
    if n_own or n_drop or n_guard or n_pct:
        log.append(f"LORA 服装: 所有格中性化 {n_own} / 摘枚举 {n_drop} / "
                   f"护盾去服装项 {n_guard} / 色盘归一 {n_pct}")
    # 短提示词只有一百来词，摘几句会掉到 validate 下限（100 词）以下 → 补一句
    if len(body.split()) < 100:
        body = body.rstrip() + "\n\n" + NO_OUTFIT_SEG
    return body


_G_ALT = "|".join(re.escape(n) for n in GARMENT_NOUNS)
# 袖口 / 下摆 / 领子这类「部件」不适合作整名替换（把 "white cuff" 换成整套衣服很荒唐）
_PART_NOUN_RE = re.compile(r"\b(?:cuffs?|hem|hems|collars?|sleeves?|bodice|seams?|waistband|"
                           r"lacing|buttons?|pockets?)\b", re.I)


def canonical_phrases(text: str) -> list[str]:
    """从母题里挑出「她这身衣服的标准叫法」（服装名词最密的那一段）。

    有些母题整篇围着一套衣服写（"white top / dark skirt" 在 9 个段落里反复出现），
    只改服装段不够 —— 于是把这些叫法提出来，全文统一替换成所选单品。
    """
    scored, primary = [], []
    for p in paras(text):
        if is_guard(p) or _STRUCT_PARA.match(p.strip()) or _PROP_CUE.search(p):
            continue
        n = len({m.group(0).lower() for m in GARMENT_RE.finditer(p)})
        if n < 2:
            continue
        scored.append((n, p))
        n_cl, n_gar = _clause_stats(p)
        low = p.strip().lower()
        # 服装段优先：以 Dress / Wearing 开头，或超过一半子句都在讲衣服
        if low.startswith(("dress ", "wearing ", "she wears")) or (
                n_gar / max(1, n_cl) >= 0.5):
            primary.append(p)
    if not scored:
        return []
    scored.sort(key=lambda x: -x[0])
    picked = primary[:1] + [p for _n, p in scored[:2] if p not in primary[:1]]
    best = " ".join(picked)
    out = []
    for m in re.finditer(rf"\b(?:[a-z][a-z\-]+\s+){{0,2}}(?:{_G_ALT})(?:e?s)?\b", best, re.I):
        # "dark navy top hat" 里的 top 不是上衣 —— 全文替换会把 "dark navy top" 换成整套
        # 单品、留下半截 "… evening gown hat"（镜潮歌剧实测语法崩坏 + 帽子仍在）
        if _HEADWEAR_RE.match(best[m.end():m.end() + 12].lstrip(" ")):
            continue
        words = [w for w in m.group(0).strip(" ,.;").split()
                 if w.lower() not in ("and", "of", "with", "the", "her", "his", "a", "an",
                                      "canonical", "original", "signature", "recognizable")]
        if len(words) < 2:
            continue
        ph = " ".join(words)
        if (_PART_NOUN_RE.search(ph) or ph.lower() in {x.lower() for x in out}
                or zone_of_tag(ph) == "style"):
            continue
        out.append(ph)
    return out[:10]


def retarget_phrases(text: str, tags: list[str], raw: str | None = None,
                     log: list[str] | None = None) -> tuple[str, int]:
    """母题里反复点名的原作服装 → 换成所选单品（按部位配对）。"""
    log = log if log is not None else []
    zm = zone_map(tags)
    repl = {z: " and ".join(v[:2]) for z, v in zm.items() if v}
    if not repl:
        return text, 0
    # 连衣裙类旧写法（qipao / yukata / dress）→ 所选上装+下装（服装库没有连衣裙时）
    if not repl.get("dress"):
        up, lo = repl.get("upper"), repl.get("lower")
        if up and lo:
            repl["dress"] = f"{up} and {lo}"
        elif up or lo:
            repl["dress"] = up or lo
    n = 0
    for ph in canonical_phrases(raw or text):
        zone = zone_of_tag(ph)
        rep = repl.get(zone) or repl.get("dress")
        joined_new = " ".join(tags).lower()
        if (not rep or rep.lower() == ph.lower() or rep.lower() in ph.lower()
                or ph.lower() in joined_new):
            continue
        text, k = re.subn(rf"\b{re.escape(ph)}\b", rep, text, flags=re.I)
        if k:
            n += k
            log.append(f"服装: 全文替换「{ph}」→「{rep}」×{k}")
    return text, n


def rewrite_inline_garments(s: str, log: list[str] | None = None) -> tuple[str, int]:
    """把「in a yukata / wearing a sailor uniform」换成「in the selected outfit」。"""
    log = log if log is not None else []
    n = 0
    out = s
    pos = 0
    while True:
        m = _INLINE_GARMENT_RE.search(out, pos)
        if not m:
            break
        span = m.group(0)
        tail = out[m.end():m.end() + 12]
        if (_SPATIAL_CUE.search(span) or _DIRECTION_CUE.match(tail)
                or _PROP_CUE.search(span)):
            pos = m.end()
            continue
        rep = m.group("pre") + "the selected outfit"
        out = out[:m.start()] + rep + out[m.end():]
        pos = m.start() + len(rep)
        n += 1
    return out, n


# 自己插进去的模板句特征 —— 这些段落不许再被改写
_OWN_TPL_CUE = ("these garments", "specific garments", "flat printed",
                "keeping the outfit clean")


def _append_directive(p: str, directive: str) -> str:
    """把单品指令接到段落末尾，缺句号先补一个（删子句后常丢句号）。"""
    p = p.rstrip()
    if p and p[-1] not in ".!?":
        p += "."
    return (p + " " + directive).strip()


def _neutralize_guard(s: str, parts: bool = False) -> tuple[str, int]:
    """负面护盾句里的旧衣服改称 outfit（整句不能删——它还在挡重复人物/多手多脚）。

    `parts=True` 连「袖口/下摆/领口」这类部位词一起改（色盘段 "twelve percent … one
    pale cuff" 需要它）；普通护盾段不改部位词，否则 "the cuff and the corner" 会变怪句。
    """
    extra = "|collar|sleeves?|cuffs?|hem" if parts else ""
    pat = re.compile(
        r"\b(?:(?:her|the|a|an)\s+)?(?:[a-z][a-z\-]+\s+){0,2}"
        r"(?:dress|skirt|blouse|sweater|cardigan|shirt|uniform|coat|jacket|robe|kimono|"
        r"hoodie|jeans|trousers|shorts|camisole|gown|outfit|clothing|attire|costume|"
        r"bodice|vest" + extra + r")\b", re.I)
    out, n = pat.subn("outfit", s)
    if n:
        out = re.sub(r"\boutfit outfit\b", "outfit", out, flags=re.I)
        out = re.sub(r"\s{2,}", " ", out)
    return out, n


_OUTFIT_TAG_EXTRA = re.compile(r"^\s*(?:[\w-]+\s+)?(?:trims?|accent lines?|linings?|stitch\w*)\s*$",
                               re.I)


def replace_tag_stream_outfit(text: str, body_tags: list[str],
                              log: list[str] | None = None) -> tuple[str, int]:
    """短提示词（tag 流）里**整组**替换服装 tag。

    母题自带的是原角色官方服装，形如
        "black sleeveless top, teal trim, detached sleeves, black thighhighs"
    逐条摘除会被 swap_garments 的 limit 截断，留下半套（实测 thighhighs 留在成品里，
    出图就是「换了脸还穿着初音那身」）。tag 流本来就是逗号分隔的平铺列表，
    按 tag 粒度整组换成目标角色的服装最稳。

    只处理 `_is_tag_stream()` 认的段落 —— 散文句仍交给 rewrite_clothing。
    """
    log = log if log is not None else []
    if not body_tags:
        return text, 0
    out, n = [], 0
    for p in paras(text):
        if is_guard(p) or not _is_tag_stream(p):
            out.append(p)
            continue
        segs = [s.strip() for s in p.split(",") if s.strip()]
        keep, placed = [], False
        for seg in segs:
            is_gar = bool(GARMENT_RE.search(seg)) or bool(_OUTFIT_TAG_EXTRA.match(seg))
            if is_gar and not _SEG_STOP_RE.match(seg) and not _SEG_TOPIC_RE.match(seg):
                if not placed:
                    keep.extend(body_tags[:14])
                    placed = True
                    n += 1
                continue
            keep.append(seg)
        out.append(", ".join(keep) if placed else p)
    if n:
        log.append(f"服装: tag 流整组替换 {n} 段 → {', '.join(body_tags[:3])}…")
    return join(out), n


def rewrite_clothing(text: str, tags: list[str], short: str = "", only: bool = True,
                     log: list[str] | None = None,
                     already_placed: bool = False,
                     bold: bool = True, mode: str = "full",
                     raw: str | None = None,
                     skip_tag_stream: bool = False) -> tuple[str, int]:
    """把母题正文里**所有**在描述别的衣服的地方改写成所选单品。

    `already_placed` = 调用方已经在别处写过单品清单（scene 分支的服装段），
    这时正文里其余的旧服装句直接删掉/摘掉，不再重复列一遍。
    `skip_tag_stream` = 调用方已经用 replace_tag_stream_outfit 整组换过 tag 流段落，
    这些段落现在是**新衣服**，不能再当旧衣服改写 —— 否则会被 swap_garments 当成
    「别人的服装」摘掉，最后只剩一个配饰 tag 挂在姿势段末尾（v1.20.10 修的 bug）。
    `bold=False`（长篇场景分支）：不做「整句替换」，也不摘不带 "her" 的子句 ——
    巨构母题里 scarf / cloak / cape 常常是画面主体，误伤会把构图描述整段换掉。
    返回 (新正文, 改动处数)。0 = 母题根本没写服装，由调用方插入指令句。
    """
    log = log if log is not None else []
    body_tags, _pose = garment_tags(tags)
    if not body_tags:
        return text, 0
    body = ", ".join(body_tags[:14])
    directive = outfit_directive(short or "her", body, mode, only)
    total = 0
    placed = already_placed
    out_ps = []
    for p in paras(text):
        # tag 流段落已由 replace_tag_stream_outfit 整组写成新单品，跳过改写
        if skip_tag_stream and _is_tag_stream(p):
            out_ps.append(p)
            continue

        # 自己刚插进去的服装段（海报/场景版型段）不能再被改写，否则会被拆成碎句
        if (is_guard(p) or _SCENE_CUE.search(p)
                or any(c in p for c in _OWN_TPL_CUE)):
            out_ps.append(p)
            continue
        # ① 动词法：保留原句主语与动词，只换宾语（already_placed 也照做，
        #    宁可把同一套单品列两遍，也不能让「She wears a black dress」留在原地）
        p2, k0 = neutralize_owner_garments(p)
        p2, k1 = swap_garments(p2, body_tags, only=only, log=[], limit=3)
        k1 += k0
        total += k1
        placed = placed or k1 > 0
        changed = k1 > 0
        struct = bool(_STRUCT_PARA.match(p.strip())) and not bold
        keep = []
        for s in [x for x in _SENT_SPLIT.split(p2) if x.strip()]:
            if "these garments" in s or not GARMENT_RE.search(s):
                keep.append(s)
                continue
            low = s.strip().lower()
            if re.search(r"identity (?:must|should) (?:read|be)|\bher identity\b", low):
                # 伪身份段（"She is Miku and her identity must read at a glance: …"）：
                # 里面混着头/眼/服装，摘子句会把句子拆烂，留给身份锚点句去压
                keep.append(s)
                continue
            s, k_inline = rewrite_inline_garments(s)
            if k_inline:
                total += k_inline
                changed = True
                if not GARMENT_RE.search(s):
                    keep.append(s)
                    continue
            n_cl, n_gar = _clause_stats(s)
            tag_stream = _is_tag_stream(s)
            if "percent" in low:
                # 色盘段用「十二 percent 一件浅色衬衣」这种说法分配面积 —— 摘子句会破句，
                # 只把衣服名换成 outfit
                s2, kg = _neutralize_guard(s)
                total += kg
                keep.append(s2)
                continue
            if re.search(r"\bnever\b|\bdo not\b|\bdon't\b|\bnot\b|\bno\b", low):
                # 负面护盾句：整句不能删（它还在挡重复人物/多手多脚）
                if n_gar and n_gar / max(1, n_cl) >= 0.5:
                    # 整句都在说「不要 xx 衣服」→ 改称 outfit 即可
                    s2, kg = _neutralize_guard(s)
                    total += kg
                    keep.append(s2)
                    continue
                cut, k = _excise_clauses(s, require_her=not tag_stream, need_is=struct)
                if k and len(cut.split()) >= 4:
                    cut = cut.rstrip()
                    if cut and cut[-1] not in ".!?":
                        cut += "."
                    keep.append(cut)
                    total += 1
                    changed = True
                else:
                    s2, kg = _neutralize_guard(s)
                    total += kg
                    keep.append(s2)
                continue
            ratio = n_gar / max(1, n_cl)
            # 「Preserve her recognizable A, B, C, and D.」是**角色特征列举句**，外貌和服装
            # 混写在一起，不是材质指派、也不是构图序列。镜潮歌剧就栽在这：这段以
            # "Give Furina an expression…" 开头 → _STRUCT_PARA 命中 → struct=True →
            # need_is=True → 只摘带 is/are 的子句 → 这句 6 个服装子句一个都没摘，
            # 深蓝外套下摆 / 白褶皱 / 金边 / 过膝靴整套留在成品里，换了衣服也画回原套装。
            _identity_list = bool(_KEEP_LIST_RE.match(s.strip())) and s.count(",") >= 3
            # ⚠ 不要给 scene 分支加「ratio 很高就整句替换」的旁路：单子句里出现一个服装词
            # 就 100%，实测把「机位低于她的上衣高度」「裙摆开叉、双腿裸露」这类构图句整句删掉。
            if ((bold and ratio >= 0.5) or (_identity_list and n_gar >= 3)) \
                    and n_gar and not _PROP_CUE.search(s):
                # ②③ 整句都在讲服装 → 换成本次所选单品（全文已有服装清单就整句删掉）
                changed = True
                total += 1
                if not placed:
                    keep.append(directive)
                    placed = True
            elif n_gar and (tag_stream or n_cl >= 3):
                # ④ tag 流 / 长串里夹着的服装子句 → 只摘掉那几个子句
                cut, k = _excise_clauses(s, require_her=not tag_stream,
                                         need_is=struct and not _identity_list)
                if k and len(cut.split()) >= 4:
                    cut = cut.rstrip()
                    if cut and cut[-1] not in ".!?":
                        cut += "."
                    keep.append(cut)
                    total += 1
                    changed = True
                else:
                    keep.append(s)
            else:
                keep.append(s)
        p3 = re.sub(r"\s{2,}", " ", " ".join(keep)).strip()
        if changed and not placed:
            p3 = _append_directive(p3, directive)    # 改过但全文还没交代新衣服
            placed = True
            total += 1
        if p3:
            out_ps.append(p3)
    out = join(out_ps)
    # ⚠ 整篇替换必须放在最后：放在开头会被后面的句子处理当成「旧衣服」再摘掉
    #   （实测：换好的 "white off-shoulder sweater" 又被 excise 掉，成品里一件衣服都没有）
    out, n_retarget = retarget_phrases(out, body_tags, raw=raw, log=log)
    total += n_retarget
    # 兜底：只要动过，成品里就必须出现所选单品（防止中途被摘掉/段落被丢）
    if total and body_tags[0].lower() not in out.lower():
        ps2 = paras(out)
        idx = next((i for i, x in enumerate(ps2) if "canonical identity" in x.lower()), -1)
        ps2.insert(idx + 1 if idx >= 0 else min(1, len(ps2)), directive)
        out = join(ps2)
    # 外套类体积大，靠在窗台/栏杆上会穿模 → 在服装句所在段补一句接触点收尾
    if placed and _BULKY_RE.search(body) and _CLIP_GUARD.strip() not in out:
        ps3 = paras(out)
        for i, p in enumerate(ps3):
            if "these garments" not in p:
                continue
            # 紧跟在服装句后面（句末插入），比甩到段落末尾权重大
            sents = [x for x in _SENT_SPLIT.split(p) if x.strip()]
            for j, sent in enumerate(sents):
                if "these garments" in sent:
                    head = sent.rstrip()
                    if head and head[-1] not in ".!?":
                        head += "."
                    sents.insert(j + 1, _CLIP_GUARD.strip())
                    break
            ps3[i] = " ".join(sents)
            break
        out = join(ps3)
    if total and not placed:
        # 只中和了护盾句、或改动没落在服装段里 → 紧跟身份锚点段补一句，别扔到全文末尾
        ps2 = paras(out)
        idx = next((i for i, x in enumerate(ps2) if "canonical identity" in x.lower()), 0)
        ps2.insert(idx + 1, directive)
        out = join(ps2)
    return out, total


# [^.] 天然匹配换行，所以段内硬换行不再是障碍；`. (?=\d)` 放过 "Vol.01" 这种缩写点
_IDENT_RE = re.compile(r"Preserve (?:[^.]|\.(?=\d))*?\.")


def replace_identity(text: str, ch: dict, tag: str, log: list[str],
                     drop_keep: bool = False, fallback: str | None = None,
                     keep_fallback: bool = False) -> tuple[str, bool]:
    """把母题的「Preserve …」身份句换成角色身份句。

    ⚠ 必须**逐段 + 允许段内换行**：母题原文有 38 条带硬换行，老写法 `Preserve [^\\n]*?\\.`
    跨不过换行 → 整句替换静默失败 → 原文那套「aqua eyes + teal-and-black outfit」
    原样留下（换角色等于没换，服装当然也换不掉）。段与段之间仍不跨，避免吞掉服装段。
    """
    if drop_keep:
        new, k = re.subn(r"(?<=[.!;] )Keep (?:her|the)[^\n]*?"
                         r"(?:readable|unobstructed|unoccluded)[^\n]*?\.", "", text, count=1)
        log.append(f"{tag}: 旧保护句 {'已删' if k else '无'}")
        text = new
    ps = paras(text)
    for i, p in enumerate(ps):
        if "Preserve " not in p or ("Preserve " + ch["identity"]) in p:
            continue
        new, n = _IDENT_RE.subn(ch["identity"], p, count=1)
        if n:
            ps[i] = new
            log.append(f"{tag}: 身份锚点 已换")
            return join(ps), True
    if fallback:
        new, n = re.subn(fallback, ch["identity"], text, count=1)
        if n:
            log.append(f"{tag}: 身份锚点 已换(兜底)")
            return new, True
    if keep_fallback:
        new, n = re.subn(r"Keep [^\n]*?(?:identity|silhouette)[^\n]*?\.", ch["identity"],
                         text, count=1)
        log.append(f"{tag}: 身份锚点 {'已换(兜底)' if n else '未命中'}")
        return new, bool(n)
    log.append(f"{tag}: 身份锚点 未命中")
    return text, False


def set_character(text: str, ch: dict, log: list[str], costume: str = "auto",
                  char_key: str = "", motif_text: str = "",
                  outfit_tags: list[str] | None = None,
                  graphics_phys: bool = False, lock_palette: bool = False,
                  no_outfit: bool = False, hair_lock: bool = False) -> str:
    if no_outfit:
        # LORA 触发词模式：单品 / 版型 / 官方预设一个都不写，服装交给 LORA
        outfit_tags, costume = [], "keep"

    # 单品 tags 先分流：姿势类（crossed legs 等）不进服装句，姿势仍由母题决定
    # 服装：姿势过滤 → 部位判定 → 只取母题需要的部位（官方服装 / 服装库同一套逻辑）
    submitted = bool(outfit_tags)
    outfit_tags, zone_mode = prepare_outfit(outfit_tags, motif_text, log)

    # v1.19.6 单品优先：只要单品**最终有效**（过完部位/姿势筛选还剩东西），
    # 「保持母题原样」就不再吞掉它 —— 用户选单品就是明确要换装。
    # ⚠ 必须在 prepare_outfit 之后判断：若单品被部位规则全筛掉，这里不能改语义，
    #   否则会静默退回「随机套版型」，比原来的「忽略单品」更难排查。
    if costume == "keep" and outfit_tags:
        log.append("服装: 已选单品 → 覆盖「保持母题原样」，按单品换装")
        costume = "auto"

    # 1) featuring 从句
    new, n = re.subn(r"featuring .{2,80}? as the only (?:physical )?character",
                     ch["feature_clause"], text, count=1)
    log.append(f"角色: featuring 从句 {'已换' if n else '未命中'}")
    text = new

    # 2) 身份锚点句
    # ⚠ 只在同一段内替换，绝不能用跨段正则：旧版母题写 "Preserve canonical identity:
    #   ... silhouette immediately readable ..."（silhouette 后面不是句号），跨段正则会一路吃到
    #   后面某个 "readable" 才收，把发型/服装段整块吞掉。
    # 先删掉原文自带的 "Keep … readable/unobstructed …" 保护句，再整句换成角色身份句
    # （身份句里已经带了一句 Keep，不先删会重复）。
    text, _id_ok = replace_identity(text, ch, "角色", log, drop_keep=True,
                                     keep_fallback=True)

    ps = paras(text)
    hair_i, costume_i, palette_i, graphics_i = locate_sections(ps)

    if hair_i >= 0:
        # 双马尾角色用两束版（那是她本人结构），其余一律单束版 —— 否则换谁都画成两股马尾
        hair_tpl = HAIR_TPL if has_twin_tail(ch) else HAIR_TPL_SINGLE
        ps[hair_i] = hair_tpl.format(name=ch["short"], hair=ch["hair_desc"], accent=ch["accent"])
    log.append(f"角色: 发型段 {'已换' if hair_i >= 0 else '未命中(跳过)'}"
               + ("（双马尾版）" if hair_i >= 0 and has_twin_tail(ch) else ""))

    # 指定具名单品 + 版型 auto → 整段只写单品，不套幻想版型（见 OUTFIT_ONLY_TPL 注释）
    garment_only = bool(outfit_tags) and costume == "auto" and costume_i >= 0
    if garment_only:
        ps[costume_i] = outfit_directive(ch["short"], ", ".join(outfit_tags[:14]),
                                         zone_mode, only=True)
        log.append(f"服装: 指定单品 → 跳过版型，只用 {len(outfit_tags)} 条单品"
                   + ("（仅上半身）" if zone_mode == "upper" else ""))
    elif costume_i >= 0 and not (submitted and costume != "keep"):
        tpl, cid, czh = pick_costume(char_key, costume, log)
        if tpl is None:
            log.append("服装: 保留母题原样的服装段")
        else:
            m1, m2 = garment_materials(motif_text or text)
            log.append(f"服装: 材质取母题「{m1} / {m2}」")
            ps[costume_i] = tpl.format(short=ch["short"], design=ch["design_language"],
                                       M1=m1, M2=m2, accent=ch["accent"],
                                       block=ch["block"], minor=ch["minor"])
    elif costume_i >= 0:
        # 选了服装但筛不出单品 → 保留母题服装段，不套随机版型（同短提示分支的理由）
        log.append("服装: 所选服装筛不出可用单品 → 保留母题服装段，不套随机版型")
    log.append(f"角色: 服装段 {'已换' if costume_i >= 0 and costume != 'keep' else '未替换'}")

    # 单品层：来自 Anima 服装库 / 角色服装预设的 tags，追加在版型段之后
    if outfit_tags:
        if garment_only:
            pass                              # 上面已整段写进，不重复追加
        elif costume_i >= 0 and costume != "keep":
            ps[costume_i] = ps[costume_i].rstrip() + " " + OUTFIT_TPL.format(
                tags=", ".join(outfit_tags))
            log.append(f"服装: 叠加单品 {len(outfit_tags)} 条 → {', '.join(outfit_tags[:3])}…")
        elif costume == "keep":
            log.append("服装: 版型为「保持母题原样」，已忽略单品"
                       "（要换装请把服装设为「自动」）")
        else:
            log.append("服装: 母题没有独立服装段 → 就地改写自带的服装句")

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

    # 2.35) 锁定发色：贴在色盘段后面，保证不被后续段落处理顶掉
    if hair_lock:
        text = apply_hair_lock(text, ch, log, "角色")
        ps = paras(text)

    # 2.4) 发型段没定位到的母题（单段 / 措辞不在 HAIR_STRONG 表里）→ 短发角色兜底。
    #      ⚠ 只在 hair_i < 0 时跑：定位成功时 ps[hair_i] 已经换成 HAIR_TPL，
    #      那段里的 "The nearer length falls past…" 会被误判成长发句整段摘掉。
    if hair_i < 0:
        text = drop_long_hair_sentences(text, ch, log, "角色")

    # 2.45) 母题身材句兜底（同短提示分支），放在服装改写之前 —— 它会删掉
    #       ", a flat chest and" 这类前缀，"wears …" 还留着，后面的服装改写照样命中。
    text = strip_motif_body(text, ch, log, "角色")

    # 2.5) 指定单品时：把母题**别处**（机位段 / 短提示词）还写着的服装枚举原地换掉。
    #      这是「选了服装库服装、出图还是母题自带那套」的根因——只换服装段不够，
    #      机位段里那句 "She wears a black technical dress" 同样会赢。
    if outfit_tags and costume != "keep":
        text, n_swap = rewrite_clothing(
            text, outfit_tags, short=ch["short"], only=(costume == "auto"), log=log,
            already_placed=bool(garment_only or (costume_i >= 0 and costume != "keep")),
            bold=False, mode=zone_mode, raw=motif_text)
        if n_swap:
            log.append(f"服装: 就地替换母题自带服装 {n_swap} 处 → "
                       f"{', '.join(outfit_tags[:3])}…")
        elif costume_i < 0:
            ps = paras(text)
            ps.insert(min(1, len(ps)), outfit_directive(
                ch["short"], ", ".join(outfit_tags[:14]), zone_mode, only=True))
            text = join(ps)
            log.append(f"服装: 母题未写服装 → 紧跟概念段插入单品段"
                       f"（{len(outfit_tags)} 条）")
        text, n_dress = neutralize_dress(text, outfit_tags)
        if n_dress:
            log.append(f"服装: 残留「dress」改称 outfit {n_dress} 处")

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
    if not has_twin_tail(ch):
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
# 指定具名单品 + 版型 auto → 不写版型句，只写单品（与 scene 分支的 OUTFIT_ONLY_TPL 同理）
OUTFIT_SHORT_ONLY_TPL = (
    "Dress {short} exactly in these garments and nothing else: {tags}. "
    "Keep every seam, cuff and hem visible so the outfit reads as ordinary clothing."
)


# ---------------------------------------------------------------- 正文里的长发句
# 短提示母题常把「原型角色是一头长发」写死在正文里（原型多是初音那样的长发），
# 而它不像 scene 分支那样有独立发型段可整段替换 —— 单段母题的 locate_sections 什么都定位不到。
# 实测 k2s_abandoned_garden_2（paras=1）：
#   "She has waist-length, long and silky very long hair falling in a smooth uncurled sheet."
#   "Her long straight very long hair should descend over the windowsill and continue downward
#    along the weathered wall."
# 换成短发角色 anis_(nikke) 时，身份句写着 short brown hair，正文这两句还在说腰长发垂过窗台 →
# 出图窗台左右各垂一束长发（Krea2-文生图_00102_）。
# 所以：**只在短发角色上**摘掉这类句子，并在原位补一句正确发型；长发角色一个字都不动（零漂移）。
_SHORT_HAIR_RE = re.compile(r"\b(short|bob|cropped|pixie|buzz)\b", re.I)
_HAIR_WORD_RE = re.compile(r"\b(?:hair|tresses|locks)\b", re.I)
_HAIR_LEN_RE = re.compile(
    r"\b(?:waist[- ]length|hip[- ]length|knee[- ]length|ankle[- ]length|floor[- ]length|"
    r"shoulder[- ]length|very long|long|length)\b", re.I)
_HAIR_DRAPE_RE = re.compile(
    r"\b(?:descends?|descending|falls?|falling|hangs?|hanging|spills?|spilling|"
    r"cascades?|cascading|trails?|trailing|drapes?|draping|flows?|flowing)\b", re.I)
# 配饰与墙面裂纹不是发型：摘掉会破坏 "no hair ornament" 约束句与建筑描述
_HAIR_ACC_RE = re.compile(
    r"\b(?:hair ?ornament|hair ?pin|hair ?accessor\w*|hairband|hair ?band|hair ?clip|"
    r"hair ?tie|hair ?bow|hair ?scrunchie|hairline)\b", re.I)


def is_short_hair(ch: dict) -> bool:
    """只看角色发型串里有没有 short / bob / cropped / pixie / buzz 这类明确的短发词。"""
    return bool(_SHORT_HAIR_RE.search(ch.get("hair_desc") or ""))


def drop_long_hair_sentences(text: str, ch: dict, log: list[str],
                             tag: str = "短提示") -> str:
    """短发角色：把正文里「她有一头腰长发 / 发丝垂过窗台」的句子换成正确发型。

    ⚠ 只认「含 hair 词 + 长度词或垂落动词」的句子，且跳过配饰句与身份句；
      长发角色直接 return，不进任何分支 —— 保证既有基线逐字节不变。
    """
    if not is_short_hair(ch):
        return text
    # ⚠ 按段落处理：整篇 split/join 会把 \n\n 抹平 → 段落数变少 → validate 报「段落偏少」
    n_drop = 0
    ps = []
    for p in paras(text):
        out, dropped, first = [], 0, True
        for s in _SENT_SPLIT.split(p):
            low = s.lower()
            hit = ("canonical identity" not in low
                   and _HAIR_WORD_RE.search(s) is not None
                   and _HAIR_ACC_RE.search(s) is None
                   and (_HAIR_LEN_RE.search(s) or _HAIR_DRAPE_RE.search(s)))
            if not hit:
                out.append(s)
                continue
            dropped += 1
            if first:                  # 第一处被摘掉的位置补一句真实发型
                out.append(f"She has {ch['hair_desc']}.")
                first = False
        if dropped:
            n_drop += dropped
            ps.append(" ".join(x for x in out if x.strip()))
        else:
            ps.append(p)
    if not n_drop:
        log.append(f"{tag}: 正文无长发描述（{ch['short']} 短发），未改动")
        return text
    log.append(f"{tag}: 短发角色 → 正文长发描述替换 {n_drop} 处（{ch['hair_desc']}）")
    return join(ps)


# ---------------------------------------------------------------- 母题身材句
# 同批母题（k2s_* / k2x_*，同一个脚本渲染出来的）正文里写死了 "a flat chest"。
# 换成有身材设定的角色就自相矛盾：身份句是 "huge breasts"，正文还在说平胸、甚至
# 约束句还写着 "Do not alter the … flat chest"（Krea2-文生图_00102_ 那批）。
# 处理：只在**角色身份句本身带身材词**时，把母题里那一部分摘掉，让身份句唯一发言；
#      身份句没写身材的角色保持原样，不留空档。
_BODY_PHR = (r"(?:a\s+)?(?:naturally\s+)?(?:flat\s+chest|"
             r"(?:large|huge|big|medium|small)\s+breasts?|"
             r"(?:slim|slender|delicate|graceful|petite|youthful)(?:\s+[a-z]+){0,2}\s+"
             r"(?:figure|body|build|frame|physique|proportions))")
_BODY_RE = re.compile(r"\b" + _BODY_PHR + r"\b", re.I)
_BODY_SUBJ_RE = re.compile(
    r"\b(?:she|her|the woman|the girl|the character|young woman)\b", re.I)
_BODY_CONSTR_RE = re.compile(r"\b(?:do not|don't|preserve|keep|avoid|never)\b", re.I)
# 环境句里的 "slender rusted metal frame" 不是身材，含这些词的一律跳过
_BODY_SKIP_RE = re.compile(
    r"\b(?:greenhouse|roof|metal|rusted|masonry|facade|wall|window|column|beam|arch)\b", re.I)
_CH_BODY_RE = re.compile(r"\b(?:chest|breasts?|bust)\b", re.I)


def _clean_body_mention(s: str) -> str:
    """摘掉身材短语并修补留下的连接词 / 逗号。"""
    s = re.sub(r"\bno\s+" + _BODY_PHR + r"\s*,\s*", "", s, flags=re.I)
    s = re.sub(r"\b(?:not|without|avoid)\s+" + _BODY_PHR + r"\s*,\s*", "", s, flags=re.I)
    s = re.sub(r",\s*" + _BODY_PHR + r"\s+(and|or)\s+", r" \1 ", s, flags=re.I)
    s = re.sub(r"\b" + _BODY_PHR + r"\s+(and|or)\s+", r" \1 ", s, flags=re.I)
    s = re.sub(r",\s*" + _BODY_PHR + r"\b", "", s, flags=re.I)
    s = re.sub(r"\b" + _BODY_PHR + r"\s*,\s*", "", s, flags=re.I)
    s = re.sub(r"\b" + _BODY_PHR + r"\b", "", s, flags=re.I)
    s = re.sub(r"\s*,\s*,+", ",", s)
    s = re.sub(r"\s*,\s*(?=[.;])", "", s)
    s = re.sub(r"\bhas\s+(?:and|or)\s+", "has ", s)          # "She has and clear eyes"
    s = re.sub(r"\b(?:and|or)\s+(?=(?:with|wearing|in)\b)", "", s, flags=re.I)
    s = re.sub(r"\bhas\s+(?:and|or)\s*\.", ".", s)
    s = re.sub(r",\s+(and|or)\s+", r" \1 ", s)               # ", and wears" → " and wears"
    s = re.sub(r"\s+([.;,])", r"\1", s)
    s = re.sub(r"\s{2,}", " ", s)
    s = re.sub(r"\b(?:She|The woman)\s+has\s*\.\s*", "", s)  # 摘空的句子整句丢
    return s.strip()


def strip_motif_body(text: str, ch: dict, log: list[str], tag: str = "短提示") -> str:
    """母题里的身材描写是**原型角色**的属性，换任何角色都不该照搬。

    ⚠ 不做「角色有没有身材词」的门槛：`build_entry` 的 identity 只装前几个标签，
    胸部标签常常进不去，用它当门槛会让 97% 的角色照样被写成平胸。
    角色自己的设定由身份句负责；母题末尾的 "no oversized breasts" 仍然兜着 SFW。
    ⚠ 必须**按段落**处理：直接对整篇 split/join 会把 \n\n 抹成空格，
    段落数变少 → validate 报「段落偏少」（实测 k2x_indus_* 42 组）。
    """
    n = 0
    ps = []
    for p in paras(text):
        out, hit = [], 0
        for s in _SENT_SPLIT.split(p):
            if not _BODY_RE.search(s):
                out.append(s)
                continue
            is_c = bool(_BODY_CONSTR_RE.search(s)) or bool(
                re.search(r"\bno\s+" + _BODY_PHR, s, re.I))
            if ("canonical identity" in s.lower()
                    or (not _BODY_SUBJ_RE.search(s) and not is_c)
                    or (_BODY_SKIP_RE.search(s) and not is_c)):
                out.append(s)                # 身份句 / 环境句 / 非人物主语 → 不动
                continue
            new = _clean_body_mention(s)
            hit += 1
            if new and not re.fullmatch(r"[A-Za-z' ]{0,30}has\.?", new):
                out.append(new)
        if hit:
            n += hit
            ps.append(" ".join(x for x in out if x.strip()))
        else:
            ps.append(p)
    if not n:
        return text
    log.append(f"{tag}: 母题写死的身材描述 → 摘掉 {n} 处（改由角色身份句决定）")
    return join(ps)


# ---------------------------------------------------------------------------
# 母题首段写死的「原型人物外观」
# ---------------------------------------------------------------------------
# 有一批短提示母题是从**参考图**转写的，首段把画面原型直接写死：
#   "solo teenage girl with short apricot hair, freckles and a sky-blue windbreaker,
#    wearing her date's slightly oversized navy baseball cap, low wide-angle POV …"
# 身份句换成目标角色之后，这段仍然在说「杏色短发 + 雀斑 + 天蓝风衣 + 海军蓝棒球帽」——
# 模型两边都听，结果就是换了角色帽子和外套还挂在身上（海边栏杆实测）。
# 修饰词位不能吃掉功能词：否则 "girl with short apricot hair" 里的 with 会被一起换掉，
# 变成 "solo teenage girl long purple hair"（实测第一版就是这样）。
# 每个词位都带 \b：不加的话正则会从 "with" 中间的回溯位置 "ith " 起步，断言就看不到了。
LOOK_HAIR_RE = re.compile(
    r"\b(?:(?:a|an|the)\s+)?"
    r"(?:(?!\b(?:with|and|of|her|his|its)\b)\b[a-z\-]+\s+){0,3}hair\b", re.I)
# 写死的瞳色（"honey-brown eyes"）同样是原型的，身份句里有角色自己的
LOOK_EYE_RE = re.compile(r"(?:(?!\b(?:with|and|of|her|his)\b)\b[a-z\-]+\s+){1,2}eyes?\b", re.I)
# 发型上的配饰（"large blue ribbon"），原型角色的标志，换人后要摘
LOOK_ACC_RE = re.compile(r"\b(?:ribbons?|bows?|hairbands?|headbands?|hairpins?|clips?)\b", re.I)
LOOK_FACE_RE = re.compile(r"\b(?:freckles?|beauty marks?|moles?)\b", re.I)
LOOK_WEAR_RE = re.compile(r"^(?:wearing|dressed in|clad in)\b", re.I)
# 构图/机位段不能当外观段删掉（"low wide-angle POV from the bench beside a railing"）
LOOK_SPATIAL_RE = re.compile(
    r"\b(?:pov|angle|camera|lens|from the|beside|behind|under|next to|edge of|top of|"
    r"middle of|bottom of|left of|right of|in front of)\b", re.I)


def neutralize_motif_look(text: str, ch: dict, log: list[str], tag: str = "短提示") -> str:
    """首段里写死的原型外观/服饰 → 发型换成角色自己的，服装与配饰整段摘掉。"""
    ps = paras(text)
    if not ps:
        return text
    head = ps[0]
    # ⚠ 只认 **tag 流母题**：短（<500 字）且带 tag 流特征 —— 比例开头，或
    #   "canonical character design" 这类写法（唱片店：`Dynamic cinematic anime illustration,
    #   Hatsune Miku, canonical character design, short icy-blue bob hair, …`）。
    #   放宽成「含 girl/woman with」会把长文母题的首段拆烂 ——
    #   k2s_abandoned_garden_2 / k2s_window_light_4 就是这么被摘掉 7~8 段的。
    if len(head) > 500:
        return text
    tagflow = bool(re.match(r"^\s*\d+:\d+\b", head)) or "canonical character design" in head.lower()
    if not tagflow:
        return text
    # tag 流里没有 "girl with" 这种句式，人物直接跟在角色名后面，所以两种入口都放行
    if not (re.search(r"\b(?:girl|woman|figure|character)\s+with\b", head, re.I)
            or "canonical character design" in head.lower()):
        return text
    segs = re.split(r",\s*", head)
    out, hair_done, dropped, hat_gone = [], False, 0, False
    for seg in segs:
        low = seg.lower()
        if LOOK_SPATIAL_RE.search(low):
            out.append(seg)
            continue
        if LOOK_HAIR_RE.search(low):
            if hair_done:
                dropped += 1
                continue
            seg = LOOK_HAIR_RE.sub(ch.get("hair_desc") or "hair", seg, count=1)
            hair_done = True
            out.append(seg)
            continue
        if (GARMENT_RE.search(low) or LOOK_FACE_RE.search(low) or LOOK_EYE_RE.search(low)
                or LOOK_ACC_RE.search(low)
                or _HEADWEAR_RE.search(low) or LOOK_WEAR_RE.match(low)):
            if _HEADWEAR_RE.search(low):
                hat_gone = True
            dropped += 1
            continue
        out.append(seg)
    if not dropped and not hair_done:
        return text
    new_head = re.sub(r",\s*,", ",", ", ".join(x.strip() for x in out if x.strip()))
    ps[0] = new_head
    text = join(ps)
    if hat_gone:
        # 帽子被摘掉后，"掀起帽檐 / 帽檐下的眼睛"这些动作就没依托了 —— 模型会照着把帽子
        # 画回来。把帽檐指代整体换成头发，动作仍然成立。
        text = re.sub(r"\bbeneath (?:the|her|his) brim\b", "beneath her hair", text, flags=re.I)
        text = re.sub(r"\b(?:the|her|his) (?:cap|hat)\b", "her hair", text, flags=re.I)
        text = re.sub(r"\bthe brim\b", "her hair", text, flags=re.I)
        log.append(f"{tag}: 帽子已摘 → 帽檐指代改为头发")
    log.append(f"{tag}: 首段原型外观 → 摘掉 {dropped} 段"
               + ("、发型换成角色设定" if hair_done else ""))
    return text


def _char_eye_desc(ch: dict) -> str:
    """从身份句里取角色的瞳色短语（"purple eyes"）。"""
    m = re.search(r"([a-z][\w\-]*(?:\s+[a-z][\w\-]*)?\s+eyes?)\b",
                  (ch.get("identity") or "").lower())
    return m.group(1).strip() if m else ""


# 母题写死的「别人的发色/瞳色/发饰」——v1.20.3
# 这批母题的正文写死了原型角色的外貌（silver hair / brown hair / white hair / red bow），
# 而 neutralize_residual_traits 只认 Miku 的 aqua / twin tails，一律放过。
# 修法不是逐个句式打补丁（散文列举、光影句、"Keep the woman's…"、首段 tag 流各一种），
# 而是按词重定向：把发色短语整体换成角色的 hair_desc，瞳色换颜色词，发饰摘掉。
_LEN_W = r"(?:very long|waist-length|shoulder-length|medium-length|medium|short|long|tiny)"
_MOD_W = r"(?:dark|warm|cold|cool|light|pale|soft|deep|muted|ash|bright|straight|windblown|side-parted)"
_COL_W = (r"(?:icy-blue|ice-blue|aqua|teal|cyan|blue|pink|red|white|silver|silvery|black|brown|"
          r"blonde|blond|gold|golden|green|purple|violet|orange|grey|gray|apricot|honey|"
          r"ash-black|copper-red|blue-white|black-and-red|red-and-black|red-black|silver-black|"
          r"dark-brown|chestnut|scarlet-red|muted-long)")
HAIR_COLOR_TAG = re.compile(
    rf"\b(?:(?:{_LEN_W}|{_MOD_W})\s+)*(?:{_COL_W})(?:[\w\-]*)?\s+"
    rf"(?:hair|bob|braid|bangs|ponytail|twintails?)\b", re.I)
EYE_COLOR_TAG = re.compile(rf"\b(?:{_COL_W})\s+eyes?\b", re.I)
# "bow" 同时是「蝴蝶结」和「弓」：k2x_bow_drawn 首段整段在讲拉弓，第一版把里面的 bow
# 当发饰删了 6 次，首句的画幅 token 都被拆没了（测试 05 抓到）。所以带武器词的段落整段跳过。
HAIR_ACC_TAG = re.compile(
    r"\b(?:(?:her|his)\s+)?(?:(?:large|small|big|tiny|enormous|giant|oversized|crimson|"
    r"scarlet|blue|red|white|black|pink|purple|yellow|left|right|neck|head)\s+){0,2}"
    r"(?:ribbons?|bows?|hairbands?|hairpins?)\b", re.I)
_BOW_WEAPON_CUE = re.compile(
    r"\b(?:weapon|bow\s*drawn|drawn\s*bow|longbow|crossbow|arrows?|archery|quiver|bowstring|"
    r"bow\s*limb|recurve)\b", re.I)


def retarget_motif_appearance(text: str, ch: dict, log: list[str],
                              tag: str = "角色") -> str:
    """把母题写死的发色 / 瞳色 / 发型配饰换成角色自己的。

    ⚠ 只替换**完整发色短语**（连修饰词一起），否则会留下 `long dark long purple hair`
    这类重复；瞳色只换颜色词、保留 `vivid / large` 修饰；发饰整段摘掉并修逗号。
    """
    hd = (ch.get("hair_desc") or "").strip()
    eye = _char_eye_desc(ch)
    n_h = n_e = n_a = 0

    def _hair(m):
        nonlocal n_h
        g = m.group(0)
        # 已经是角色发色（含其主色词）就不动，避免二次替换
        if hd and hd.split()[-2].lower() in g.lower():
            return g
        n_h += 1
        return hd or g

    if hd:
        text = HAIR_COLOR_TAG.sub(_hair, text)
    if eye:
        # 异色瞳（"one deep blue eye and one pale ice-blue eye"）整组换成角色瞳色，
        # 否则会变成 "one purple eyes and one purple eyes"
        text = re.sub(r"\bone\s+(?:[\w\-]+\s+){0,2}eyes?\s+and\s+one\s+"
                      r"(?:[\w\-]+\s+){0,2}eyes?\b", eye, text, flags=re.I)
        def _eye(m):
            nonlocal n_e
            n_e += 1
            return eye
        text = EYE_COLOR_TAG.sub(_eye, text)

    def _acc(m):
        nonlocal n_a
        n_a += 1
        return ""

    if n_h or n_e:
        # 发饰只在**人物描述段**里摘（段内含 hair / head / eyes）：
        # 否则会误删场景里的 "flowing tidal ribbons"（海面纹理，k2s_hy_086 实测）
        ps = paras(text)
        for i, p in enumerate(ps):
            if not re.search(r"\bhair\b|\bhead\b|\beyes?\b|\bbraids?\b|\bponytails?\b|\bbangs?\b", p, re.I):
                continue
            if _BOW_WEAPON_CUE.search(p):
                continue                     # 这段的 bow 是弓，不是蝴蝶结
            p = HAIR_ACC_TAG.sub(_acc, p)
            # 摘掉发饰后会留下孤立的位置词（"sits beside her left ."），一并清掉
            p = re.sub(r"\b(?:her|his)\s+(?:left|right)\s+(?=[,.])", "", p, flags=re.I)
            p = re.sub(r"\b(?:the)\s+(?:left|right)\s+(?=[,.])", "", p, flags=re.I)
            p = re.sub(r"\b(?:a|an|the|her|his)\s+(?=[,.])", "", p, flags=re.I)
            p = re.sub(r"\s+with\s*,", ",", p)            # "tied with <ribbon>" → "tied with ,"
            p = re.sub(r"\s+,", ",", p)
            p = re.sub(r"\s*,\s*(?=,|\.|$)", "", p)
            p = re.sub(r",\s*,", ",", p)
            p = re.sub(r"\band\s+(?=,|\.)", "", p)
            p = re.sub(r"\bbeside\s+\.", "beside her.", p)
            p = re.sub(r"\s{2,}", " ", p)
            ps[i] = p
        text = join(ps)
    if n_h or n_e or n_a:
        log.append(f"{tag}: 母题写死的外貌 → 发色 {n_h} 处 / 瞳色 {n_e} 处 / 发饰 {n_a} 处"
                   f"（改为 {hd or '角色设定'}）")
    return text


def set_character_short(text: str, ch: dict, log: list[str], costume: str = "auto",
                        char_key: str = "", motif_text: str = "",
                        outfit_tags: list[str] | None = None,
                        no_outfit: bool = False, hair_lock: bool = False) -> str:
    """短提示词分支的轻量适配：不动构图，只换身份 + 追加一两句服装。"""
    if no_outfit:
        # LORA 触发词模式：单品 / 版型 / 官方预设一个都不写，服装交给 LORA
        outfit_tags, costume = [], "keep"

    # 服装：姿势过滤 → 部位判定 → 只取母题需要的部位（官方服装 / 服装库同一套逻辑）
    submitted = bool(outfit_tags)          # 用户是否真的选了服装（区别于"筛完为空"）
    outfit_tags, zone_mode = prepare_outfit(outfit_tags, motif_text, log)
    # v1.19.6 单品优先：单品有效就覆盖「保持母题原样」（理由同 set_character）
    if costume == "keep" and outfit_tags:
        log.append("短提示: 已选单品 → 覆盖「保持母题原样」，按单品换装")
        costume = "auto"
    ps = paras(text)

    text, _id_ok = replace_identity(
        text, ch, "短提示", log,
        fallback=r"(recognizable [^.\n]*?(?:silhouette|twin-tail silhouette)[^.\n]*\.)")
    ps = paras(text)
    if not _id_ok:
        ps.insert(1, ch["identity"])
        log.append("短提示: 身份锚点 原文无，改为插入")

    # 1.4) 首段写死的原型外观（发色/雀斑/外套/棒球帽）→ 发型换成角色设定，其余摘掉
    text = neutralize_motif_look(join(ps), ch, log, "短提示")
    ps = paras(text)

    # 1.5) 短发角色：摘掉正文里残留的长发描述（见 drop_long_hair_sentences 的注释）。
    #      必须排在身份句替换之后 —— 身份句里是 "short brown hair"，先摘会误伤。
    text = drop_long_hair_sentences(join(ps), ch, log, "短提示")
    ps = paras(text)

    # 1.6) 母题写死的 flat chest / slim figure 与身份句的身材冲突 → 摘掉母题那份。
    text = strip_motif_body(join(ps), ch, log, "短提示")
    ps = paras(text)

    # 服装：指定单品时**先就地改写**母题自带的服装句（"She wears a … dress"），
    # 再决定要不要补版型句；没有可改写的句子才退回到「紧跟身份段插入」。
    if outfit_tags and costume != "keep":
        # tag 流母题（k2s_*）的服装是平铺 tag 列表，整组替换最稳；
        # 散文句留给 rewrite_clothing 逐句处理。
        text, n_tag = replace_tag_stream_outfit(join(ps), outfit_tags, log=log)
        ps = paras(text)
        text, n_swap = rewrite_clothing(text, outfit_tags, short=ch["short"],
                                        only=(costume == "auto"), log=log,
                                        mode=zone_mode, raw=motif_text,
                                        already_placed=bool(n_tag),
                                        skip_tag_stream=bool(n_tag))
        ps = paras(text)
        n_swap += n_tag
        if n_swap:
            log.append(f"短提示: 就地替换母题自带服装 {n_swap} 处 → "
                       f"{', '.join(outfit_tags[:3])}…")
        else:
            directive = outfit_directive(ch["short"], ", ".join(outfit_tags[:12]),
                                         zone_mode, only=(costume == "auto"))
            idx = next((i for i, p in enumerate(ps)
                        if "canonical identity" in p.lower()), -1)
            ps.insert(idx + 1 if idx >= 0 else 1, directive)
            log.append(f"短提示: 母题未写服装 → 紧跟身份段插入 {len(outfit_tags)} 个单品")
        text, n_dress = neutralize_dress(join(ps), outfit_tags)
        ps = paras(text)
        if n_dress:
            log.append(f"短提示: 残留「dress」改称 outfit {n_dress} 处")

    if outfit_tags and costume == "keep":
        log.append("短提示: 版型为「保持母题原样」，已忽略单品"
                   "（要换装请把服装设为「自动」）")
    elif outfit_tags and costume == "auto":
        # 指定了具名单品 → 跳过版型，只写单品（否则「仪式礼服」会盖过「露肩针织」）
        log.append(f"短提示: 指定单品 → 跳过版型，只写 {len(outfit_tags)} 个单品")
    elif submitted and costume != "keep":
        # 选了服装但筛不出单品（角色预设没衣服 / 部位无交集）→ **不追加随机版型句**。
        # 旧行为是静默回落到 pick_costume，随机塞一句 "Render X in a panel armor…"，
        # 与母题自带服装句并存互相抢 —— 这正是「选了官服，出图还是母题那套」的假象来源。
        log.append("短提示: 所选服装筛不出可用单品 → 不追加随机版型句"
                   "（母题自带服装句保持原样；请先修该角色的服装预设）")
    else:
        tpl, cid, czh = pick_costume(char_key, costume, log)
        if cid == "keep":
            log.append("短提示: 服装保持母题原样，不追加版型句")
        else:
            cut = next((t["id"].replace("_", " ") for t in ALL_TPLS if t["id"] == cid), "") \
                or cid.replace("_", " ") or "auto"
            ps.append(COSTUME_SHORT_TPL.format(short=ch["short"], cut=cut,
                                               accent=ch["accent"], block=ch["block"]))
            log.append(f"短提示: 已追加版型句「{cut}」")
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

    if not has_twin_tail(ch):
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
    if hair_lock:
        text = apply_hair_lock(text, ch, log, "短提示")
    return text


def set_character_poster(text: str, ch: dict, log: list[str], costume: str = "auto",
                         char_key: str = "", motif_text: str = "",
                         outfit_tags: list[str] | None = None,
                         no_outfit: bool = False, hair_lock: bool = False) -> str:
    """平面海报分支的角色/服装适配。

    海报没有 3D 母题那 7 个锚点（只有 1/19 有 Dress 段），所以不能走 set_character：
    这里保留整张版式、大标题与印刷色盘，只做四件有边界的替换。
    """
    if no_outfit:
        # LORA 触发词模式：单品 / 版型 / 官方预设一个都不写，服装交给 LORA
        outfit_tags, costume = [], "keep"

    # 服装：姿势过滤 → 部位判定 → 只取母题需要的部位（官方服装 / 服装库同一套逻辑）
    submitted = bool(outfit_tags)
    outfit_tags, zone_mode = prepare_outfit(outfit_tags, motif_text, log)
    # v1.19.6 单品优先：单品有效就覆盖「保持母题原样」（理由同 set_character）
    if costume == "keep" and outfit_tags:
        log.append("海报: 已选单品 → 覆盖「保持母题原样」，按单品换装")
        costume = "auto"
    ps = paras(text)

    # 1) 身份锚点：16/19 有 Preserve 句；没有的就在首段后补一段
    text, _id_ok = replace_identity(text, ch, "海报", log, drop_keep=True)
    ps = paras(text)
    if not _id_ok:
        ps.insert(1, ch["identity"])
        log.append("海报: 身份锚点 原文无，改为插入")

    # 2) 服装：所选版型 + 单品 → 一小段平面化说明，插在首段（概念）之后
    #    指定单品 + 版型 auto → **不套随机剪裁**（否则封面会变成「利落西装式」那类，
    #    与所选单品打架，等于又回到「选的服装没用上」）。这里连 random 都不吃。
    m1, m2 = garment_materials(motif_text or text)
    if outfit_tags and costume == "auto":
        cpara = COSTUME_POSTER_ONLY_TPL.format(
            short=ch["short"], tags=", ".join(outfit_tags[:14]),
            scope={"upper": "'s upper body", "lower": "'s lower body"}.get(zone_mode, ""),
            design=ch["design_language"], M1=m1, M2=m2,
            accent=ch["accent"], block=ch["block"])
        log.append(f"海报: 指定单品 → 跳过版型，只写 {len(outfit_tags)} 个单品")
    elif submitted and costume != "keep":
        # 选了服装但筛不出单品 → 不插随机版型段（同短提示分支的理由），保留原版式写法
        cpara = ""
        log.append("海报: 所选服装筛不出可用单品 → 不插随机版型段"
                   "（请先修该角色的服装预设）")
    else:
        tpl, cid, czh = pick_costume(char_key, costume, log)
        # ⚠ 版型的 zh 是中文，绝不能进英文提示词；用 id 还原成英文短语
        cut = next((t["id"].replace("_", " ") for t in ALL_TPLS if t["id"] == cid), "") \
            or cid.replace("_", " ") or "auto"
        cpara = COSTUME_POSTER_TPL.format(short=ch["short"], cut=cut,
                                          design=ch["design_language"], M1=m1, M2=m2,
                                          accent=ch["accent"], block=ch["block"])
        if outfit_tags:
            cpara += " " + OUTFIT_POSTER_TPL.format(tags=", ".join(outfit_tags[:14]))
        log.append(f"海报: 已插入服装段「{cut}」"
                   + (f" + {len(outfit_tags)} 个单品" if outfit_tags else ""))
    if cpara:
        ps.insert(1, cpara)

    # 2.4) 海报母题常把原型角色的长发写进版式描述（"her long hair spills across the title"），
    #      短发角色照样会被画成长发 → 同样兜底。函数内部只对短发角色生效。
    text = drop_long_hair_sentences(join(ps), ch, log, "海报")
    text = strip_motif_body(text, ch, log, "海报")
    ps = paras(text)

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

    # 3.5) 指定单品 → 版式里若还写着 "wearing …"（tag 流海报很常见）就地换掉
    #      服装段（cpara）已经列过一次单品 → 别处旧服装句直接删，不再重复列
    if outfit_tags and costume != "keep":
        text, n_swap = rewrite_clothing(text, outfit_tags, short=ch["short"],
                                        only=(costume == "auto"), log=log,
                                        already_placed=True, mode=zone_mode, raw=motif_text)
        if n_swap:
            log.append(f"海报: 就地替换母题自带服装 {n_swap} 处 → "
                       f"{', '.join(outfit_tags[:3])}…")
        text, n_dress = neutralize_dress(text, outfit_tags)
        if n_dress:
            log.append(f"海报: 残留「dress」改称 outfit {n_dress} 处")

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
    if not has_twin_tail(ch):
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
    if hair_lock:
        text = apply_hair_lock(text, ch, log, "海报")
    return text


# ===========================================================================
# 残留角色特征清洗（换角色后仍带原角色特征）
# ---------------------------------------------------------------------------
# 母题库是围绕 Hatsune Miku 写的。装配会整段换掉「身份句 / 发型段 / 服装段 / 色盘段」，
# 但正文里还散落着一批**角色特征锚点**，它们不是独立段，所以一路留到输出：
#
#   · "full body from boots to hair ornaments"            ← 取景用发饰当身体上限
#   · "her face, eyes, hands and hair ornaments must …"   ← 可读性锚点
#   · "both aqua eyes clearly visible" / "aqua hair"      ← 写死 Miku 的颜色
#   · "the outer twin-tail ends" / "aqua twintails"       ← 连字符/无空格写法
#   · "no duplicate Miku" / "no missing twin tails"       ← 旧角色否定护盾
#   · "virtual-singer stillness" / "virtual singer"（tag）← 身份 tag
#
# 换角色后这些必须一起中性化，否则模型把 aqua + twin-tail 当角色特征画出来，
# 就是用户看到的「换了对象还是青绿色双马尾」。只在非 Miku 角色上跑，Miku 本人原样保留。
# ---------------------------------------------------------------------------
def _is_miku_like(ch: dict) -> bool:
    s = f"{ch.get('short', '')} {ch.get('name', '')} {ch.get('work', '')}".lower()
    return "miku" in s or "hatsune" in s


def has_twin_tail(ch: dict) -> bool:
    """角色本身是不是双马尾。

    ⚠ 不能只查 "twin tail" 这一种写法：Anima 那套 tag 写的是 "worn in twintails"，
    旧判定认不出 → 把 Miku 的双马尾在正文里中性化成 "long hair strands"，角色自己的
    标志反而被抹掉（换回 Miku 也画不出双马尾）。
    """
    return bool(re.search(r"twin[\s-]?tails?|twintails?|twin[\s-]?ponytails?",
                          ch.get("hair_desc") or "", flags=re.I))


def _match_case(src: str, dst: str) -> str:
    """让替换词跟原文大小写照抄：画内文字 "HATSUNE MIKU" → "CIRNO"。"""
    if not dst:
        return dst
    if src.isupper() and len(src) > 1:
        return dst.upper()
    if src.islower():
        return dst.lower()
    return dst[:1].upper() + dst[1:]


TWIN_RE = re.compile(r"\btwin[\s-]?tails?\b|\btwin[\s-]?ponytails?\b|\btwintails?\b", re.I)
# 只吃「紧跟 eyes/bangs/hair 的颜色词」，场景里的 aqua 水/玻璃一律不碰
CHARCOLOR_RE = re.compile(r"\b(?:luminous|bright|pale|deep)\s+(?=(?:aqua|teal|cyan|turquoise)\b)"
                          r"|\b(?:aqua|teal|cyan|turquoise)\s+(?=(?:\w+\s+){0,2}"
                          r"(?:eyes?|bangs?|hair|twintails?|tails?)\b)", re.I)
VS_RE = re.compile(r"\bvirtual[\s-]singer\b", re.I)
# 廉价预检：干净文本（没有这些词）直接返回，省掉 3318 组装配里的重正则开销。
# 只列「角色特征」词，场景里的 aqua 水/玻璃不算 —— 否则几乎每条母题都会进慢路径。
RESIDUE_CUE = re.compile(r"\b(?:Miku|Hatsune)\b|twin[\s-]?tails?\b|twintails?\b"
                         r"|twin[\s-]?ponytails?\b|hair ornaments?\b|virtual[\s-]singer\b"
                         r"|\bblue-haired girl\b|\bno short hair\b"
                         r"|\b(?:aqua|teal|cyan)\s+(?:eyes?|bangs?)\b"
                         r"|\b(?:aqua|teal|cyan)\s+(?:trim|accent|lining|stitch)\b", re.I)


def neutralize_residual_traits(text: str, ch: dict, log: list[str]) -> str:
    if _is_miku_like(ch):
        log.append("残留特征: 角色即 Miku 本人 → 跳过清洗")
        return text
    if not RESIDUE_CUE.search(text):
        log.append("残留特征: 无可清洗项")
        return text

    name = ch.get("name") or ch.get("short") or "her"
    short = ch.get("short") or name
    n = {"twin": 0, "orn": 0, "col": 0, "name": 0, "vs": 0, "guard": 0}
    out = []
    for p in paras(text):
        guard = is_guard(p)
        if guard:
            # 旧角色的否定项在换角色后是反向召唤：先整项删掉，再由护盾重写补新角色的
            p, c = re.subn(r",?\s*no (?:duplicate )?(?:Miku|Hatsune)\b", "", p, flags=re.I)
            p, c2 = re.subn(r",?\s*no (?:missing )?(?:aqua |teal )?twin[\s-]?tails?(?: silhouette)?\b",
                            "", p, flags=re.I)
            p, c3 = re.subn(r",?\s*no (?:missing )?(?:aqua |teal )?twintails?\b", "", p, flags=re.I)
            p, c4 = re.subn(r",?\s*no (?:generic )?(?:blue-haired girl|blue hair girl)\b", "", p,
                            flags=re.I)
            # "no short hair" 只对长发角色成立；目标是短发角色时它会把头发强行拉长
            c5 = 0
            if "short" in (ch.get("hair_desc") or "").lower():
                p, c5 = re.subn(r",?\s*no short hair\b", "", p, flags=re.I)
            # "no second virtual singer" 是 Miku 身份约束，换角色后应退回普通人物否定
            p, c6 = re.subn(r"\bno second virtual[\s-]singer\b", "no second figure", p, flags=re.I)
            n["guard"] += c + c2 + c3 + c4 + c5 + c6
        else:
            # 1) 双马尾（含 twin-tail / twintails / twin ponytails）
            #    ⚠ 目标角色本人就是双马尾时必须放过：这段正文里的 "worn in twintails"
            #    是她自己的 hair_desc 刚写进去的，不是母题库里的 Miku 残留。
            #    另三处残留清洗（蒙版 / 景深 / 护盾）早有 has_twin_tail 守卫，这里漏了 ——
            #    结果双马尾角色（花火等）的 twintails 被一律换成 "long hair strands"，
            #    出图变成普通长发。
            if has_twin_tail(ch):
                c = 0
            else:
                p, c = TWIN_RE.subn("long hair strands", p)
            n["twin"] += c
            p = re.sub(r"\blong hair strands strands\b", "long hair strands", p, flags=re.I)
            p = re.sub(r"\bextremely long long hair\b", "extremely long hair", p, flags=re.I)

            # 2) 发饰锚点：三种固定句式，逐条换掉
            p, c = re.subn(r",?\s*and hair ornaments?\b(?=\s+(?:must|immediately|stay))", "", p,
                           flags=re.I)
            n["orn"] += c
            p, c = re.subn(r"from boots to hair ornaments?\b",
                           "from boots to the top of her head", p, flags=re.I)
            n["orn"] += c
            p, c = re.subn(r"\bhair ornaments? and both hands\b", "and both hands", p, flags=re.I)
            n["orn"] += c
            p, c = re.subn(r"one (?:aqua |teal )?eye and one hair ornament\b",
                           "one eye and one signature accessory", p, flags=re.I)
            n["orn"] += c
            p, c = re.subn(r"\bhair ornaments?\b(?=,?\s*(?:and )?(?:fragments|dissolving|contours))",
                           "hair", p, flags=re.I)
            n["orn"] += c
            p, c = re.subn(r"\bhair ornaments?\b", "hair details", p, flags=re.I)
            n["orn"] += c

            # 3) 写死的青绿：只吃紧贴 eyes/bangs 的修饰词（aqua hair 交给发型段/服装段）
            p, c = CHARCOLOR_RE.subn("", p, count=0)
            n["col"] += c
            # 服装上的 Miku 色（teal trim / teal accent lines）换成目标角色的主色，
            # 衣服结构不动 —— 短提示词里那身是母题自带造型，删 tag 会变成没穿衣服。
            p, c = re.subn(r"\b(?:teal|aqua|cyan)\s+(?=(?:trim|accent|lining|stitch)\b)",
                           f"{ch.get('accent', 'ivory')} ", p, flags=re.I)
            n["col"] += c
            p = re.sub(r"\b(?:luminous|bright|pale|deep)\s{2,}", "", p)
            # "extremely long teal long hair strands" → 删掉 teal 后剩 "long long"，
            # 上面那次压缩跑在删色之前，这里补一刀
            p = re.sub(r"\blong\s+long\s+(hair|strands)\b", r"long \1", p, flags=re.I)
            p = re.sub(r"\s{2,}", " ", p).strip()

            # 4) virtual-singer
            p, c = re.subn(r"virtual-singer stillness", f"{short}’s stillness", p, flags=re.I)
            n["vs"] += c
            p, c = re.subn(r",\s*virtual[\s-]singer\b", "", p, flags=re.I)
            n["vs"] += c
            p, c = re.subn(r"virtual[\s-]singer", "character", p, flags=re.I)
            n["vs"] += c

        # 5) 名字：大小写不敏感（原写法 \bHatsune Miku\b 匹配不到小写 tag "hatsune miku"）
        def _nm(m):
            return _match_case(m.group(0), short if m.group(0).islower() else name)
        p, c = re.subn(r"\bHatsune Miku\b|\bHatsune\b|\bMiku\b", _nm, p, flags=re.I)
        n["name"] += c
        out.append(p)

    msg = (f"残留特征: 双马尾 {n['twin']} / 发饰 {n['orn']} / 角色色 {n['col']} / "
           f"护盾旧否定 {n['guard']} / virtual-singer {n['vs']} / 旧角色名 {n['name']}")
    log.append(msg)
    return join(out)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 母题自带的角色装饰（例：甘雨背上的六片水晶翼）
# ---------------------------------------------------------------------------
# 少数母题当初是照着某个角色写的，正文里直接写进了她的专属装饰（水晶翼）。那不是
# 场景陈设 —— 换角色后模型照样把装饰画在别人背上（阿尔托莉雅版「榻榻米房」实测：
# 428 词里三处 wing 全在，出图就有了水晶翼）。母题在 motifs_new/_meta.json 用
# owner_char 登记「装饰所属角色」，装配时按选中角色分流：
#   · 选中角色 == owner_char → 原样保留（那是她的特征）
#   · 选中其他角色           → 连子句一起摘掉
#   · 没选角色（keep / 空）  → 原样保留（用户要的就是母题原貌）
# ⚠ 只摘「带 wing 的那个子句」，同段其它内容（发型 / 光线 / 构图）一个字不动。
OWNER_PROP_RE = re.compile(
    r"\b(?:ice[\s-]crystal|crystalline|ice|crystal)\s+wings?\b|\bwings?\b", re.I)


def strip_owner_props(text: str, log: list[str], owner_char: str = "",
                      char_key: str = "", tag: str = "") -> str:
    if not owner_char:
        return text                          # 母题没登记装饰 → 什么都不做
    if not char_key or char_key == owner_char:
        if char_key:
            log.append(f"{tag}母题装饰: 选中角色即 {owner_char}，水晶翼保留")
        return text
    out, n = [], 0
    for p in paras(text):
        if not OWNER_PROP_RE.search(p):
            out.append(p)
            continue
        keep = []
        for seg in re.split(r",\s*", p):
            if OWNER_PROP_RE.search(seg):
                n += 1                       # "ribbon and ice wings" 整枚子句丢掉
                continue
            keep.append(seg)
        q = ", ".join(s for s in keep if s.strip())
        q = re.sub(r",\s*,", ",", q)
        q = re.sub(r"\s{2,}", " ", q).strip()
        # 短提示词的段尾本来就用逗号收口（下文紧接另一段），别被摘成句号
        if p.rstrip().endswith(",") and q and not q.endswith((",", ".", ";")):
            q += ","
        if q.strip():
            out.append(q)
    if n:
        log.append(f"{tag}母题装饰: 水晶翼 {n} 处已摘（属于 {owner_char}，非 {char_key}）")
    return join(out)


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
# 被摘掉的是一整段长段（>45 词）时，用长一点的留白句补齐篇幅，否则长文会掉到 1000 词以下
NO_TEXT_SEG_LONG = ("Let that whole area stay bare and unmarked: one flat lit surface, soft "
                    "tonal steps, faint material grain and a single clean shadow edge, with "
                    "no mark, number or sign anywhere on it.")
# 极少数母题（如把排版当主体的 k2x_indus_mega_field）摘完掉到 1000 词以下 → 补一段
NO_TEXT_FILL = ("Hold the whole frame in matte material and even light: worn concrete, brushed "
                "steel, soft grain, faint dust along the seams, one clean bright edge on every "
                "volume and a narrow step of shadow beneath it, with the air kept pale and "
                "still from edge to edge and the values reading as one disciplined run of "
                "greys from the floor to the top of the frame, so the eye stays on the "
                "structure and never on any surface incident.")

# ---------------------------------------------------------------------------
# 「画面不显示文字」的第二层：不只是引号里那个词，而是**所有**催模型写字的分句
# ---------------------------------------------------------------------------
# 踩过的坑：玄关母题写着 `Let a second, much smaller exact readable line “UNIT 9” sit on
# a small enamel plate…` —— 引号内容被删了，句子还剩 `readable line … on a small enamel
# plate`，模型照样画出一排小字；电梯的 `stencilled word` 同理。
# 所以按**句子**判定「这句在指挥写字」，而不是只删引号。
_TEXT_EXACT = re.compile(r"\b(exact|readable|legible|spelled|spelt|letter-perfect)\b", re.I)
_TEXT_NOUN = re.compile(
    r"\b(lettering|letters?|words?|lines?|text|titles?|subtitles?|captions?|labels?|"
    r"signage|sign|wordmark|typeface|typography|letterforms?|glyphs?|script|"
    r"numerals?|digits?|strings?|enamel plate|plate|stencil)\b", re.I)
_TEXT_VERB = re.compile(
    r"\b(reads?|readable|legible|spell(?:s|ed|ing)?|print(?:s|ed|ing)?|stencil(?:led|s|ing)?|"
    r"engrav(?:ed|es|ing)?|emboss(?:ed|es)?|inscri(?:bed|ption)|typeset|lettered|"
    r"sits?|sit|carries?|carry|painted?|set)\b", re.I)
_TEXT_TYPO = re.compile(
    r"\b(lettering|letterforms?|wordmark|typograph\w*|typeface|typeset|"
    r"engrav\w*|emboss\w*|inscri\w*|stencil\w*|glyphs?|serif|sans-serif)\b", re.I)
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _is_text_instruction(s: str) -> bool:
    """这一句是不是「把某个词画进画面」的指令（不是「画面读起来像…」那种比喻）。

    ⚠ 不能只认 print —— `screen print` / `risograph print` / `printed graphic
    language` 是画风描述，删了会把风格段整段废掉。所以要求「文字名词 + 精确/可读」
    同时出现，或者干脆出现排版专用词（typography / lettering / wordmark / stencil）。
    """
    s = s.strip().rstrip(".")
    # 「with no lettering」「no readable text anywhere」是我们要的结论句，不是指令
    if re.search(r"\b(?:no|without|avoid|never|free of|free from)\b[^.;]{0,48}"
                 r"\b(lettering|readable text|text anywhere|text|words?|typography|"
                 r"logo|letters)\b", s, re.I):
        return False
    quoted = bool(re.search(r"[“\"][^”\"\n]{1,60}[”\"]", s))
    # 引号里只要真有字（字母 / 数字 / 假名 / 汉字），就是画内文字：
    # 海报母题会写 `the left vertical stem of the "H" continues downward` —— 一个引号
    # 字母都没有 "readable"，但模型照样把 H 画出来。
    # 英文母题里出现假名 / 汉字，只可能是画内标题（`Render あ and ら in warm white`、
    # `the final し cross onto the circle`）—— 逐字写进正文，整句必须摘。
    if re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", s):
        return True
    q = re.search(r"[“\"]([^”\"\n]{1,60})[”\"]", s)
    if q and re.search(r"[A-Za-z0-9\u3040-\u30ff\u4e00-\u9fff]", q.group(1)):
        return True
    # 字形/排版部位 + 排版动词（title / letter / stem / stroke / glyph）
    if (re.search(r"\b(titles?|words?|letters?|letterforms?|glyphs?|stems?|"
                  r"strokes?|counters?)\b", s, re.I)
            and re.search(r"\b(render|print|place|set|carry|hang|paint|switch|route|extend|"
                          r"continue|cross|build|decide|break|stack|align|typeset|engrave|"
                          r"emboss|stencil|inscribe)\b", s, re.I)
            and not re.search(r"\b(reads?|reading|like)\b", s, re.I)):
        return True
    exact = bool(_TEXT_EXACT.search(s))
    noun = bool(_TEXT_NOUN.search(s))
    verb = bool(_TEXT_VERB.search(s))
    if quoted and (noun or exact or verb):
        return True
    if exact and noun:
        return True
    if _TEXT_TYPO.search(s) and (noun or quoted or exact):
        return True
    if noun and verb and exact:
        return True
    return False


# 首句画幅 token / 身份句绝不能当写字指令删掉：`Create a 2:3 … plate titled “X”` 里
# 带着引号，会被引号规则误判 → 整句没了 → validate 报「首句画幅token缺失」。
_PROTECT_SENT = re.compile(r"^(?:Create\b|Preserve\b|Square\b|Portrait\b|Horizontal\b|"
                           r"Vertical\b)", re.I)


_CJK_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]+")


def _clean_protected(s: str) -> str:
    """受保护的句子（首句 / 身份句）保留，但把句内的画内标题摘干净。

    首句常写成 `Create a wide 16:9 … titled あらし …`，整句删掉会丢画幅 token，
    所以只摘引号与中日文字符，句子骨架保留。
    """
    s = re.sub(r"[“\"][^”\"\n]{1,60}[”\"]", " ", s)
    s = _CJK_RE.sub(" ", s)
    s = re.sub(r"\btitled\s*[,.;]", "with no lettering,", s, flags=re.I)
    s = re.sub(r"\btitled\b", "with no lettering", s, flags=re.I)
    return re.sub(r"\s{2,}", " ", s).strip()


def scrub_lettering(text: str, log: list[str]) -> str:
    """逐句摘掉写字指令，整段被摘空就换成留白句（保住段数，validate 有下限）。"""
    out, dropped = [], 0
    for p in paras(text):
        if is_guard(p):
            out.append(p)
            continue
        sents = _SENT_SPLIT.split(p)
        keep = []
        for s_ in sents:
            if _PROTECT_SENT.match(s_.strip()):
                keep.append(_clean_protected(s_))       # 保留首句，只摘句内标题
            elif not _is_text_instruction(s_):
                keep.append(s_)
        n = len(sents) - len(keep)
        if not n:
            out.append(p)
            continue
        dropped += n
        q = re.sub(r"[ \t]{2,}", " ", " ".join(keep)).strip()
        # 还剩「…and numbers belonging to the specimen system」这种：数字也会被画出来，
        # 改成刻度记号，保住测量感又不留字。
        q = re.sub(r"\band numbers?\b", "and graduated ticks", q, flags=re.I)
        q = re.sub(r"\b(numbers|digits|numerals)\b", "ticks", q, flags=re.I)
        q = _tidy_punct(q) if q else q
        filler = NO_TEXT_SEG_LONG if len(p.split()) >= 45 else NO_TEXT_SEG
        out.append(q if len(q.split()) >= 8 else filler)
    if dropped:
        log.append(f"画面文字: 摘掉写字分句 {dropped} 处（含小字 / 编号 / 铭牌）")
    body = join(out)
    # 短提示词只有一百来词，摘两句就掉到 validate 下限（100 词）以下 → 补一句留白
    if dropped and len(body.split()) < 110:
        out.append(NO_TEXT_SEG)
        body = join(out)
    return body


def _scrub_guard_lettering(p: str) -> str:
    """护盾里的「除上文那个词以外不许有字」在无文字模式下自相矛盾，改写掉。

    ⚠ 不能只认 `no readable text beyond the`：实测还有
    `no readable floor numbers beyond the one display` 这种变体。
    ⚠ 也绝不能一看到 `beyond the` 就改 —— `no gardener beyond the gate` 是场景否定。
    """
    p = re.sub(r"no readable [^,]{0,70}?\b(?:beyond|except|other than)\b[^,]*",
               "no readable text anywhere in the image", p, flags=re.I)
    # 「只有那个词可以看得见」= 反向许可，无文字模式下必须拔掉
    p = re.sub(r"(?:[.;]\s*)?Only the exact[^.]*?(?:readable|legible)[^.]*\.?", ". ", p,
               flags=re.I)
    p = re.sub(r"(?:[.;]\s*)?Only the [^.]{0,40}?hiragana[^.]*\.?", ". ", p, flags=re.I)
    p = re.sub(r"\.\s*\.", ".", p)
    p = re.sub(r"\s{2,}", " ", p).strip()
    p = re.sub(r",?\s*no lettering touching or cropped by any frame edge", "", p, flags=re.I)
    p = re.sub(r"[ \t]{2,}", " ", p)
    return p


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
        # ⚠ 不能无脑全删：母题 `Construct the megastructure from…` 里那个普通名词
        #    和画内标题同名，整篇删完会变成 `Construct the from…`（实测）。
        #    只在「附近真在讲字」时才删（title / text / lettering / readable 之类）。
        if re.search(r"[A-Za-z]", p):
            pat = re.compile(r"(?<![A-Za-z0-9])" + esc + r"(?![A-Za-z0-9])", re.I)

            def _bare(m):
                occ = m.group(0)
                # 全大写的基本就是画内标题本体 → 删；小写的往往只是正文里提到这个词
                if occ.isupper() and len(occ) > 1:
                    return " "
                # 否则看**同一句**里有没有写字线索（跨句会误伤下一句的 title 描述）
                cs = max(text.rfind(". ", 0, m.start()), text.rfind("\n", 0, m.start()))
                ce = text.find(". ", m.end())
                win = text[cs + 1: ce if ce > 0 else m.end() + 90]
                return " " if re.search(
                    r"\b(title|text|word|lettering|readable|legible|caption|label|"
                    r"font|typeface|typography|stencil)\b", win, re.I) else m.group(0)

            text = pat.sub(_bare, text)
        else:
            text = text.replace(p, " ")
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    # 短提示里 "PLATE 39" 这类被拆掉一半会剩 `“ 39,”` —— 光秃秃的引号同样催字
    text = re.sub(r"[“\"]\s*[\d\s,.;:'’-]{0,8}\s*[”\"]", " ", text)
    text = text.replace("“", "").replace("”", "")

    # ①.5 逐句摘掉「写字」指令 —— 只删引号内容时，剩下的
    #      `smaller exact readable line … on a small enamel plate` 照样催出小字。
    text = scrub_lettering(text, log)

    TITLE_SEG = re.compile(
        r"\b(title|titled|lettering|readable text|typography|caption|label|wordmark|display text)\b",
        re.I)
    KEEP = re.compile(
        r"\b(Create|featuring|canonical identity|Dress|Preserve|Integrate|Weave|percent|No additional)\b",
        re.I)
    ps = paras(text)
    for i, p in enumerate(ps):
        if is_guard(p):
            ps[i] = _scrub_guard_lettering(p)
        elif (len(p.split()) <= 70 and TITLE_SEG.search(p) and not KEEP.search(p)
                and "carries no lettering" not in p):
            ps[i] = NO_TEXT_SEG
    # 逐句摘完之后可能又空出一段（整段都是写字指令）→ 补留白句，保段数
    for i, p in enumerate(ps):
        if p is not None and len(p.split()) < 6 and not is_guard(p):
            ps[i] = NO_TEXT_SEG
    ps[0] = re.sub(r"\btitled\s*,", "with no lettering,", ps[0], flags=re.I)
    ps[0] = re.sub(r"\btitled\s+(?=[a-z])", "with no lettering ", ps[0], flags=re.I)
    ps[0] = re.sub(r"\btitled\s+titled\b", "with no lettering", ps[0], flags=re.I)
    # 删掉 "titled “X” by concept only" 之后会剩半句尾巴，收拾干净
    ps[0] = re.sub(r"\bwith no lettering\b[\s,]*\bby concept only\b",
                   "with no lettering", ps[0], flags=re.I)
    ps[0] = re.sub(r"(\bwith no lettering[^,.]*),\s*Feature\b", r"\1, featuring", ps[0])
    ps[0] = re.sub(r"(\bwith no lettering[^,.]*),\s*Render\b", r"\1, rendering", ps[0])
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
             display_mode: str = "all", no_outfit: bool = False,
             hair_lock: bool = False) -> tuple[str, list[str]]:
    seeds, chars = load()
    if seed_id not in seeds:
        raise AssembleError(f"未知种子: {seed_id}")
    seed = seeds[seed_id]
    branch = seed.get("branch") or "scene"
    raw_mode = branch in ("poster", "short")
    text, log = seed["raw"], []
    # 母题自带的角色装饰（水晶翼一类）在**角色替换之前**摘掉，只针对「选中角色不是登记角色」。
    # ⚠ 不能放到装配之后：像琪露诺这种本人就有冰翼的角色，身份句 / 护盾里写着 "ice wings"，
    #    装配后统一摘会把角色自己的翼一起删掉（实测 6 处全没了，人变没翼的冰精）。
    base_text = strip_owner_props(text, log, seed.get("owner_char") or "", char_key or "")
    text = base_text
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
        if outfit_tags or no_outfit:
            # 选了单品 / LORA 服装模式 → 身份句 / 护盾里写死的原作服装要让位，
            # 否则模型永远画回原套装（furina：identity 有 "ceremonial outfit"、
            # guard 有 "no missing top hat"）
            ch = costume_free_char(ch, log)
        if branch == "poster":
            text = set_character_poster(text, ch, log, costume, char_key, base_text,
                                        outfit_tags, no_outfit=no_outfit, hair_lock=hair_lock)
        elif branch == "short":
            text = set_character_short(text, ch, log, costume, char_key, base_text,
                                       outfit_tags, no_outfit=no_outfit, hair_lock=hair_lock)
        else:
            text = set_character(text, ch, log, costume, char_key, base_text, outfit_tags,
                                 graphics_phys=(seed.get("source") == "authored"),
                                 lock_palette=bool(seed.get("lock_palette")),
                                 no_outfit=no_outfit, hair_lock=hair_lock)
        # 三个分支共用：把母题里写死的原角色特征（双马尾 / 发饰 / 青绿眼 / Miku 名）
        # 中性化。放在分支之后、画内文字处理之前 —— 不能改用户填的标题。
        text = neutralize_residual_traits(text, ch, log)
        # 母题写死的别人的发色/瞳色/发饰 → 换成角色自己的（Miku 本人跳过）
        if not _is_miku_like(ch):
            text = retarget_motif_appearance(text, ch, log, "角色")
        # LORA 服装触发词模式：服装全交给 LORA，正文里一个服装词都不留
        if no_outfit:
            text = strip_all_garments(text, log)
    if no_text:
        # 优先级最高：勾了「画面不显示英文」就不再管填了什么文字
        text = remove_display_text(text, find_display_text(seed["raw"]), log)
        # 摘字摘太多会跌到 1000 词（validate 下限）→ 补一段无字材质句，篇幅回来
        if (seed.get("branch") or "scene") == "scene" and len(text.split()) < 1000:
            text = text.rstrip() + "\n\n" + NO_TEXT_FILL
            log.append("画面文字: 篇幅不足 1000 词，已补一段无字材质句")
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
