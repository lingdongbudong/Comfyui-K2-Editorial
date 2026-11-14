# -*- coding: utf-8 -*-
"""把 Anima 服装库精简成 SFW 版本（公开发布用）。

本仓库自带的 `presets/anima/` 是 Comfyui-Anima-Wardrobe-V6 服装库的**打包快照**，
原库带档位（L0–L4）。公开版只保留 L0–L1 且剔除 `nsfw_outfit` 分类，
避免把成人向条目分发到公开仓库。

用法：

    # 只看会删掉什么
    python tools/make_sfw_bundle.py --check

    # 就地精简（先备份）
    python tools/make_sfw_bundle.py --inplace

    # 生成到别处
    python tools/make_sfw_bundle.py --out /tmp/outfit_library_sfw.json

规则：`level <= --max-level` 且 `cat` 不在 `--drop-cat` 里。被删条目会打印 id 与档位。
缩略图/角色库不受影响（角色官方预设全 L0）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT = os.path.join(ROOT, "presets", "anima", "outfit_library.json")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def slim(lib: dict, max_level: int, drop_cats: set) -> tuple[dict, list, list]:
    keep, drop = [], []
    for o in lib.get("outfits") or []:
        if int(o.get("level", 0)) <= max_level and (o.get("cat") or "") not in drop_cats:
            keep.append(o)
        else:
            drop.append(o)
    meta = dict(lib.get("_meta") or {})
    cats = [c for c in (meta.get("categories") or []) if c.get("id") not in drop_cats]
    counts = {}
    for o in keep:
        counts[o.get("cat", "")] = counts.get(o.get("cat", ""), 0) + 1
    active = meta.get("active") or ""
    meta.update({
        "count": len(keep),
        "counts": counts,
        "categories": cats,
        # 启用中的那套若被剔除，必须清空，否则后端会指向不存在的 id
        "active": active if any(o["id"] == active for o in keep) else "",
        "sfw_bundle": {"max_level": max_level, "dropped_cats": sorted(drop_cats)},
    })
    return {"_meta": meta, "outfits": keep}, keep, drop


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=DEFAULT)
    ap.add_argument("--out", default="")
    ap.add_argument("--inplace", action="store_true")
    ap.add_argument("--max-level", type=int, default=1)
    ap.add_argument("--drop-cat", default="nsfw_outfit")
    ap.add_argument("--check", action="store_true", help="只报告，不写盘")
    a = ap.parse_args()

    with open(a.src, encoding="utf-8") as fh:
        lib = json.load(fh)
    drop_cats = {c.strip() for c in a.drop_cat.split(",") if c.strip()}
    new, keep, drop = slim(lib, a.max_level, drop_cats)

    print(f"源：{a.src}")
    print(f"  {len(lib.get('outfits') or [])} 套 → 保留 {len(keep)} / 剔除 {len(drop)}"
          f"（level ≤ {a.max_level}，剔除分类 {sorted(drop_cats)}）")
    by_lv = {}
    for o in keep:
        by_lv[o.get("level", 0)] = by_lv.get(o.get("level", 0), 0) + 1
    print("  保留档位：", dict(sorted(by_lv.items())))
    print("  保留分类：", new["_meta"]["counts"])
    if drop:
        print("  剔除：")
        for o in drop:
            print(f"    L{o.get('level', 0)} {o.get('cat', ''):<13} {o['id']:<26} {o.get('zh', '')}")

    if a.check:
        print("\n--check：未写盘")
        return 0
    out = a.src if a.inplace else (a.out or a.src.replace(".json", "_sfw.json"))
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(new, fh, ensure_ascii=False, indent=1)
    print(f"\n已写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
