# -*- coding: utf-8 -*-
"""给母题打「景别」标签（人像 / 半身 / 全景）。

用法:
    python tools/classify_shots.py                 # 写回插件 manifest（规则 + 人工校正）
    python tools/classify_shots.py --check         # 只报告分布，不写盘
    python tools/classify_shots.py --low           # 打印「低置信度」清单（JSON，供缩略图校正）
    python tools/classify_shots.py --set k2x_xxx=半身 [--set ...]   # 人工校正后写盘

三档定义（对外）:
    人像 = 特写 / 近景（脸到胸以上，人物占满大半个画面）
    半身 = 中景（腰或膝以上，人物 + 少量环境）
    全景 = 远景 / 超远景（人物全身甚至很小，环境/巨构为主）

内部先按五档判（特写/近景/中景/远景/超远景），再归并成三档 —— 保留细分判定是为了
以后要拆回五档时不用重跑。⚠ 三档而不是五档的原因：母题文案与参考图大面积不一致，
close-up / half-body 这类词经常对不上图，五档的边界太细必然判错，三档更宽容。

判定顺序（前者优先）:
    1. 显式取景词（要求附近有人物词，避免石像/道具的"肩部特写"）
    2. 人物高度占比（只认 "percent of the canvas height"）
    3. 分支默认（scene→远景 / short→中景 / poster→中景）

人工校正写在 presets/motif_shots_override.json，重跑不会被规则覆盖。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

PLUGIN = os.environ.get("K2_PLUGIN",
                        r"S:/AI_workV5/ComfyUI/custom_nodes/Comfyui-K2-Editorial")
MANIFEST = os.path.join(PLUGIN, "presets", "manifest.json")
SEEDS_EXTRA = os.path.join(PLUGIN, "presets", "seeds_extra.json")
SEEDS_MAIN = os.path.join(PLUGIN, "presets", "seeds_motifs.json")
OVERRIDE = os.path.join(PLUGIN, "presets", "motif_shots_override.json")

# 对外三档
SHOTS = ["人像", "半身", "全景"]
# 内部五档 → 三档
FINE = ["特写", "近景", "中景", "远景", "超远景"]
MAP3 = {"特写": "人像", "近景": "人像", "中景": "半身",
        "远景": "全景", "超远景": "全景"}

PERSON_CTX = re.compile(
    r"\b(?:she|her|miku|figure|character|woman|girl|body|face|portrait)\b", re.I)

PATTERNS = [
    ("特写", re.compile(
        r"\b(?:extreme close[- ]?up|close[- ]?up|face fills the frame|"
        r"fills the frame with her face|profile close[- ]?up|head[- ]shot)\b", re.I)),
    ("近景", re.compile(
        r"\b(?:upper[- ]body|waist[- ]up|chest[- ]up|bust shot|head and shoulders|"
        r"half[- ]length|half[- ]body|shoulders[- ]up)\b", re.I)),
    ("中景", re.compile(
        r"\b(?:three[- ]quarter[- ](?:length|shot)|mid[- ]shot|medium shot|cowboy shot|"
        r"knee[- ]up|thigh[- ]up|from head to (?:mid-?)?thigh)\b", re.I)),
    ("远景", re.compile(
        r"\b(?:full[- ]body|full[- ]length|full figure|head to toe|entire figure|"
        r"whole body|full[- ]height|full[- ]standing)\b", re.I)),
    ("超远景", re.compile(
        r"\b(?:wide shot|extreme wide|aerial|establishing shot|panorama|panoramic|"
        r"bird'?s[- ]eye|long shot|vista|sweeping (?:view|panorama))\b", re.I)),
    # ⚠ 只认 tiny / minuscule / distant / lost，"small" 不算：
    #   "small seated figure" 常指娇小身材，画面其实是中景（v6_car_ride 实测）
    ("超远景", re.compile(
        r"\b(?:tiny|minuscule|distant|lost)\b[^.]{0,60}?\b(?:figure|silhouette|travelers?|"
        r"people|pedestrians?|crowd)\b", re.I)),
    # 「close … view」不是 close-up，而是"贴近拍摄"的近景（饼干店：close wide-angle view）
    ("近景", re.compile(
        r"\bclose (?:wide[- ]angle|wide|three[- ]quarter|low|high)?\s*view\b", re.I)),
]

WORDNUM = {"ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
           "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
           "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
           "seventy": 70, "eighty": 80, "ninety": 90}
HEIGHT = re.compile(r"([\w-]+)(?:\s+to\s+([\w-]+))?\s+percent of the canvas height", re.I)


def num(w: str | None) -> int | None:
    if not w:
        return None
    w = w.lower()
    return int(w) if w.isdigit() else WORDNUM.get(w)


def classify(text: str, branch: str) -> tuple[str, str]:
    """返回 (景别, 依据)。依据用于判断置信度。"""
    hits = []
    for name, rx in PATTERNS:
        for m in rx.finditer(text):
            ctx = text[max(0, m.start() - 120): m.end() + 120]
            if PERSON_CTX.search(ctx):
                hits.append((m.start(), name, m.group(0)))
    if hits:
        hits.sort()
        return hits[0][1], f"词:{hits[0][2][:26]}"

    hv = [v for v in (num(a) or num(b) for a, b in HEIGHT.findall(text)) if v]
    if hv:
        v = max(hv)
        if v >= 85:
            return "特写", f"高占比{v}%"
        if v >= 55:
            return "中景", f"高占比{v}%"
        if v >= 30:
            return "远景", f"高占比{v}%"
        return "超远景", f"高占比{v}%"

    # ⚠ 有巨构不等于人物小：`k2x_still_section` 通篇 colossal，参考图却是全身竖构图（远景）。
    #   所以「巨构」不作为超远景的判据 —— 超远景只由显式词（panoramic / tiny figure / aerial）触发。
    # 分支默认：scene 是"人物全身 + 巨构"，short 多为"人物半身 + 环境"，poster 多半身
    return {"scene": "远景", "poster": "中景",
            "portrait-pose": "中景", "short": "中景"}.get(branch, "远景"), "分支默认"


def load_json(p: str, default):
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--low", action="store_true")
    ap.add_argument("--set", action="append", default=[])
    args = ap.parse_args()

    seeds = {}
    for p in (SEEDS_MAIN, SEEDS_EXTRA):
        for s in load_json(p, {}).get("seeds", []):
            seeds[s["id"]] = s
    man = load_json(MANIFEST, {})
    motifs = man.get("motifs") or []

    ov = load_json(OVERRIDE, {})
    for pair in args.set:
        mid, _, val = pair.partition("=")
        val = MAP3.get(val, val)          # 允许按五档名校正，自动归并
        if val not in SHOTS:
            print(f"非法景别: {pair}（只认 {'/'.join(SHOTS)}，或五档名）")
            return 2
        ov[mid.strip()] = val

    result, low = {}, []
    for m in motifs:
        mid = m["id"]
        if mid in ov:
            result[mid], why = MAP3.get(ov[mid], ov[mid]), "人工"
        else:
            fine, why = classify(seeds.get(mid, {}).get("raw") or "",
                                 m.get("branch") or seeds.get(mid, {}).get("branch") or "scene")
            result[mid] = MAP3.get(fine, fine)
        if why in ("分支默认", "巨构线索") or why.startswith("高占比"):
            low.append({"id": mid, "shot": result[mid], "why": why,
                        "zh": m.get("zh"), "thumb": m.get("thumb"),
                        "branch": m.get("branch")})

    from collections import Counter
    dist = Counter(result.values())
    print("总母题:", len(result))
    for k in SHOTS:
        print(f"  {k:4s} {dist.get(k, 0):4d}")
    print("低置信度:", len(low))

    if args.low:
        print(json.dumps(low, ensure_ascii=False, indent=1))

    if args.check:
        return 0

    if ov:
        ov = {k: MAP3.get(v, v) for k, v in ov.items()}      # 旧五档校正值一并归并
        with open(OVERRIDE, "w", encoding="utf-8") as fh:
            json.dump(dict(sorted(ov.items())), fh, ensure_ascii=False, indent=1)
    for m in motifs:
        m["shot"] = result[m["id"]]
    with open(MANIFEST, "w", encoding="utf-8") as fh:
        json.dump(man, fh, ensure_ascii=False, indent=1)
    print("已写回 manifest")
    return 0


if __name__ == "__main__":
    # 不用 raise SystemExit：与插件内约定一致，避免 BaseException 穿透上层 except
    sys.exit(main())
