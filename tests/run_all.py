# -*- coding: utf-8 -*-
"""Comfyui-K2-Editorial 回归测试。

    python tests/run_all.py            # 全量（约 8–12 秒）
    python tests/run_all.py --fast     # 抽样 40 条母题（约 2 秒）
    python tests/run_all.py --http     # 额外打 8188 端点（需要服务在跑）

覆盖四类：
  ① 数据契约  —— JSON 能解析、母题/版型 id 唯一、manifest 与缩略图齐全
  ② 装配行为  —— 全量母题 × 角色 × 文本模式、确定性、角色名不残留
  ③ 基础设施  —— 缓存命中与失效、原子写、版本号一致、控件顺序不变量
  ④ 可选冒烟  —— HTTP 端点与前端 JS 语法（有 node 才跑）

设计口径：只用插件目录内的数据 + `characters.json` 里手写的两个角色，
所以没有 Anima 插件、没有 ComfyUI 也能跑（缺 Anima 时自动回落到内置副本）。
"""
from __future__ import annotations

import io
import json
import os
import random
import shutil
import subprocess
import sys
import time
import types
import contextlib
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PRESETS = os.path.join(ROOT, "presets")
FAST = "--fast" in sys.argv
WITH_HTTP = "--http" in sys.argv

try:                                  # Windows 控制台默认 GBK，中文+符号会炸
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# --------------------------------------------------------------------------
# 加载插件（包形式，因为 k2ed_node 用的是相对 import）
# --------------------------------------------------------------------------
if "folder_paths" not in sys.modules:
    try:
        if os.path.abspath(os.path.join(ROOT, "..", "..")) not in sys.path:
            sys.path.insert(0, os.path.abspath(os.path.join(ROOT, "..", "..")))
        import folder_paths          # noqa: F401  （在 ComfyUI 根目录下跑时可用真的）
    except Exception:
        _fp = types.ModuleType("folder_paths")
        _fp.get_folder_paths = lambda key: [os.path.dirname(ROOT)]
        _fp.models_dir = os.path.join(os.path.dirname(ROOT), "models")
        sys.modules["folder_paths"] = _fp

_boot = io.StringIO()
with contextlib.redirect_stdout(_boot):     # 插件 import 时会 print 版本 / 跳过路由
    _spec = importlib.util.spec_from_file_location(
        "k2ed", os.path.join(ROOT, "__init__.py"), submodule_search_locations=[ROOT])
    pkg = importlib.util.module_from_spec(_spec)
    sys.modules["k2ed"] = pkg
    _spec.loader.exec_module(pkg)

A = pkg.assembler
B = pkg.anima_bridge
N = pkg.k2ed_node

CHECKS = []


def check(name):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


def _json(name):
    with open(os.path.join(PRESETS, name), encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------
# ① 数据契约
# --------------------------------------------------------------------------
@check("数据文件可解析")
def t_files():
    names = ["seeds_motifs.json", "seeds_extra.json", "characters.json",
             "costumes.json", "manifest.json"]
    seeds, chars = A.load()
    tpl = A.ALL_TPLS
    return True, (f"{len(names)} 份 JSON / 母题 {len(seeds)} / 版型 {len(tpl)} / "
                  f"手写角色 {len(chars)}")


@check("母题 id 唯一且字段齐")
def t_seed_shape():
    """注意：`seeds.branch` 是**来源标记**（scene / portrait-pose / night /
    material-narrative / baieguang-import / 缺省…），装配时凡不在
    (poster, short) 的都走 scene 路径。真正的分类契约在 manifest.branch，
    由 build_manifest 归一成三类，见 t_manifest。
    """
    bad = []
    for f in ("seeds_motifs.json", "seeds_extra.json"):
        p = os.path.join(PRESETS, f)
        if not os.path.exists(p):
            continue
        for s in _json(f).get("seeds") or []:
            for k in ("id", "raw", "words"):
                if k not in s:
                    bad.append(f"{f}:{s.get('id', '?')} 缺 {k}")
            if not str(s.get("raw") or "").strip():
                bad.append(f"{s.get('id')} 正文为空")
    seeds, _ = A.load()
    total = sum(len(_json(f).get("seeds") or [])
                for f in ("seeds_motifs.json", "seeds_extra.json")
                if os.path.exists(os.path.join(PRESETS, f)))
    if len(seeds) != total:
        bad.append(f"合并后 {len(seeds)} 条 != 源文件合计 {total} 条（id 有重复）")
    from collections import Counter
    dist = Counter((s.get("branch") or "(缺省)") for s in
                   _json("seeds_motifs.json").get("seeds", []) +
                   (_json("seeds_extra.json").get("seeds", [])
                    if os.path.exists(os.path.join(PRESETS, "seeds_extra.json")) else []))
    return (not bad), (f"{len(seeds)} 条 / 来源标记 {len(dist)} 种" if not bad
                       else "; ".join(bad[:6]))


@check("manifest 覆盖母题 + 缩略图齐全")
def t_manifest():
    man = _json("manifest.json")
    seeds, _ = A.load()
    ids = {m["id"] for m in man.get("motifs") or []}
    miss = [i for i in seeds if i not in ids]
    nofile, nothumb = [], []
    BAD_BRANCH = set()
    for m in man.get("motifs") or []:
        if m.get("branch") not in ("scene", "poster", "short"):
            BAD_BRANCH.add(f"{m['id']}:{m.get('branch')}")
        if not m.get("thumb"):
            nothumb.append(m["id"])
            continue
        if not os.path.isfile(os.path.join(ROOT, m["thumb"])):
            nofile.append(m["id"])
        if not m.get("zh"):
            nofile.append(m["id"] + "(无中文名)")
    ok = not miss and not nofile and not nothumb and not BAD_BRANCH
    return ok, (f"{len(ids)} 条全部有图，分类均为 scene/poster/short" if ok
                else f"缺条目 {len(miss)} / 缺图 {len(nofile)} / 无 thumb 字段 {len(nothumb)}"
                     f" / 分类越界 {len(BAD_BRANCH)}"
                     f"：{list(BAD_BRANCH)[:3] or (miss + nofile + nothumb)[:5]}")


@check("版型与手写角色完整")
def t_chars():
    A.load()                       # ALL_TPLS / ALL_CHARS 是 load() 的副作用
    bad = []
    seen = set()
    for t in A.ALL_TPLS:
        if t["id"] in seen:
            bad.append(f"版型重复 {t['id']}")
        seen.add(t["id"])
    _, chars = A.load()
    for key, ch in chars.items():
        for k in ("name", "identity", "feature_clause", "palette"):
            if k not in ch:
                bad.append(f"{key} 缺 {k}")
        if ch.get("palette") and sum(p[1] for p in ch["palette"]) != 100:
            bad.append(f"{key} 色盘和 != 100")
    return (not bad), (f"版型 {len(seen)} / 角色 {len(chars)}" if not bad else "; ".join(bad[:6]))


# --------------------------------------------------------------------------
# ② 装配行为
# --------------------------------------------------------------------------
@check("全量装配零异常零告警")
def t_assemble():
    seeds, chars = A.load()
    keys = list(seeds)
    if FAST:
        keys = keys[:40]
    modes = ({}, {"no_text": True},
             {"display_text": "AURORA 07", "display_mode": "title"})
    bad, n = [], 0
    t0 = time.perf_counter()
    for sid in keys:
        branch = seeds[sid].get("branch") or "scene"
        for ck in chars:
            for kw in modes:
                n += 1
                try:
                    random.seed(7)                 # costume=auto 会抽版型，固定才可复现
                    txt, _log = A.assemble(sid, ck, "16:9", "auto", **kw)
                except BaseException as exc:
                    bad.append(f"{sid}/{ck}: {type(exc).__name__} {exc}")
                    continue
                # 传 orig_char：全量覆盖「母题原角色名残留」这条泛化检查
                rep = A.validate(txt, ck, branch, A.seed_character(sid))
                if rep["issues"]:
                    bad.append(f"{sid}/{ck}: {rep['issues'][:2]}")
    dt = time.perf_counter() - t0
    ok = not bad
    return ok, (f"{n} 组 / {dt:.1f}s / {dt / max(n, 1) * 1000:.1f} ms 每组" if ok
                else f"{len(bad)} 组有问题：" + "; ".join(bad[:4]))


@check("同参装配可复现")
def t_deterministic():
    seeds, chars = A.load()
    ck = list(chars)[0]
    diff = []
    for sid in list(seeds)[:12]:
        random.seed(3)
        a, _ = A.assemble(sid, ck, "16:9", "auto")
        random.seed(3)
        b, _ = A.assemble(sid, ck, "16:9", "auto")
        if a != b:
            diff.append(sid)
    return (not diff), ("12 条两次一致" if not diff else f"不一致 {diff[:3]}")


@check("角色名不互相残留")
def t_no_leak():
    import re
    seeds, chars = A.load()
    keys = list(seeds)[: (40 if FAST else 999)]
    bad = []
    for sid in keys:
        for ck, ch in chars.items():
            random.seed(5)
            txt, _ = A.assemble(sid, ck, "16:9", "auto")
            for other, och in chars.items():
                if other == ck:
                    continue
                first = (och.get("name") or "").split()[0]
                if first and re.search(rf"\b{re.escape(first)}\b", txt):
                    bad.append(f"{sid}/{ck} 残留 {first}")
    return (not bad), (f"{len(keys)}×{len(chars)} 组干净" if not bad else "; ".join(bad[:4]))


@check("非法母题/角色抛 ValueError")
def t_raises():
    """⚠ 必须是 Exception 子类：SystemExit 会让整个 HTTP 服务不响应。"""
    seeds, chars = A.load()
    bad = []
    for call, label in (
        (lambda: A.assemble("__不存在__", list(chars)[0], "16:9", "auto"), "母题"),
        (lambda: A.assemble(list(seeds)[0], "__不存在__", "16:9", "auto"), "角色"),
    ):
        try:
            call()
            bad.append(f"{label}未抛错")
        except A.AssembleError as exc:
            if not isinstance(exc, Exception):
                bad.append(f"{label}不是 Exception 子类")
        except BaseException as exc:
            bad.append(f"{label}抛的是 {type(exc).__name__}")
    return (not bad), ("两类都抛 AssembleError(ValueError)" if not bad else "; ".join(bad))


@check("不污染全局 random 状态")
def t_random_isolated():
    """generate() 用完必须复原 random 全局状态。

    不收口的话，同一工作流下游的随机节点（Anima 抽场景等）会被本节点的种子钉住，
    表现为「改了种子，下游画面纹丝不动」。
    """
    seeds, _ = A.load()
    mid = list(seeds)[0]
    node = N.K2EditorialBuilder()
    bad = []
    for flag, label in ((True, "每次重随机=True"), (False, "每次重随机=False")):
        random.seed(4242)
        before = random.getstate()
        node.generate(7, flag, 角色="miku", 母题=mid, 画幅="16:9", 服装=N.AUTO)
        if random.getstate() != before:
            bad.append(label)
    return (not bad), ("两种模式均复原" if not bad else "有污染：" + "、".join(bad))


# --------------------------------------------------------------------------
# ③ 基础设施
# --------------------------------------------------------------------------
@check("load() 缓存命中与失效")
def t_cache():
    tmp = os.path.join(ROOT, "tests", "_tmp_cache")
    os.makedirs(tmp, exist_ok=True)
    try:
        for f in ("seeds_motifs.json", "seeds_extra.json", "characters.json", "costumes.json"):
            shutil.copyfile(os.path.join(PRESETS, f), os.path.join(tmp, f))
        keep = (A.SEEDS, A.SEEDS_EXTRA, A.CHARS, A.COSTUMES)
        A.SEEDS = os.path.join(tmp, "seeds_motifs.json")
        A.SEEDS_EXTRA = os.path.join(tmp, "seeds_extra.json")
        A.CHARS = os.path.join(tmp, "characters.json")
        A.COSTUMES = os.path.join(tmp, "costumes.json")
        A._LOAD_CACHE.clear()
        t0 = time.perf_counter(); A.load(); cold = (time.perf_counter() - t0) * 1000
        t0 = time.perf_counter()
        for _ in range(5):
            A.load()
        hit = (time.perf_counter() - t0) / 5 * 1000
        p = os.path.join(tmp, "seeds_extra.json")
        st = os.stat(p)
        os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
        t0 = time.perf_counter(); A.load(); after = (time.perf_counter() - t0) * 1000
        ok = hit < cold / 3 and after > hit * 3
        return ok, f"首次 {cold:.1f}ms / 命中 {hit:.2f}ms / 改盘后 {after:.1f}ms"
    finally:
        A.SEEDS, A.SEEDS_EXTRA, A.CHARS, A.COSTUMES = (
            os.path.join(PRESETS, "seeds_motifs.json"),
            os.path.join(PRESETS, "seeds_extra.json"),
            os.path.join(PRESETS, "characters.json"),
            os.path.join(PRESETS, "costumes.json"))
        A._LOAD_CACHE.clear()
        A.load()
        shutil.rmtree(tmp, ignore_errors=True)


@check("原子写：失败不损坏原文件")
def t_atomic():
    tmp = os.path.join(ROOT, "tests", "_tmp_atomic")
    os.makedirs(tmp, exist_ok=True)
    try:
        p = os.path.join(tmp, "x.json")
        N._write_json(p, {"a": 1})
        good = json.load(open(p, encoding="utf-8")) == {"a": 1}
        try:
            N._write_json(p, {"bad": {1, 2}})        # set 不可 JSON 序列化
            raised = False
        except TypeError:
            raised = True
        intact = json.load(open(p, encoding="utf-8")) == {"a": 1}
        left = [f for f in os.listdir(tmp) if f != "x.json"]
        ok = good and raised and intact and not left
        return ok, (f"写入正常 / 失败回滚 / 残留 {len(left)} 个临时文件")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@check("场景默认画幅：覆盖层读写 / 合流 / 不污染缓存")
def t_motif_aspect():
    """卡片徽标点出来的覆盖值（v1.13.0）。

    三条不变量：写进去读得回、合流只改返回的副本（manifest 缓存对象不许被改写）、
    传 both 能把覆盖删干净。全程用临时文件，不碰用户真实数据。
    """
    tmp = os.path.join(ROOT, "tests", "_tmp_asp")
    os.makedirs(tmp, exist_ok=True)
    keep = N.MOTIF_ASPECT_FILE
    try:
        N.MOTIF_ASPECT_FILE = os.path.join(tmp, "user_motif_aspect.json")
        cached = N._load_json(N.MANIFEST, {})
        items = [m for m in (cached.get("motifs") or []) if m.get("id")]
        if not items:
            return False, "manifest 没有母题"
        # 必须挑一条「推荐值 ≠ 要写的值」的，否则覆盖前后看不出差别
        pick = next((m for m in items
                     if (m.get("aspect") or "landscape") != "portrait"), items[0])
        mid = pick["id"]
        base = pick.get("aspect") or "landscape"
        want = "square" if base == "portrait" else "portrait"

        N.save_motif_aspect(mid, want)
        readback = N.motif_aspect_user().get(mid)

        merged = N.merge_motif_aspect({"motifs": list(cached.get("motifs") or [])})
        eff = next((m.get("aspect") for m in merged["motifs"] if m.get("id") == mid), None)
        cache_kept = next((m.get("aspect") for m in
                           (N._load_json(N.MANIFEST, {}).get("motifs") or [])
                           if m.get("id") == mid), None)

        N.save_motif_aspect(mid, "both")          # 删覆盖 = 回推荐值
        cleared = mid not in N.motif_aspect_user()

        ok = (readback == want and eff == want
              and cache_kept == base and cleared and base != want)
        return ok, (f"{mid} 推荐 {base} → 覆盖 {want} / 合流 {eff} / "
                    f"缓存仍是 {cache_kept} / 删覆盖 {'OK' if cleared else '失败'}")
    finally:
        N.MOTIF_ASPECT_FILE = keep
        shutil.rmtree(tmp, ignore_errors=True)


@check("徽标按钮 + 三态循环链")
def t_js_aspect_badge():
    """前端不变量：徽标是 <button>、点击接 cycleMotifAspect、循环链是竖→横→方。"""
    p = os.path.join(ROOT, "js", "k2ed_panel.js")
    src = open(p, encoding="utf-8").read()
    need = ['MOTIF_ASP_CYCLE = ["portrait", "landscape", "square"]',
            'if (cur === "both") return "portrait"',
            'badge.onclick = (ev) => cycleMotifAspect(ev, m, badge)',
            'el("button", "", ASP_ZH[asp]',
            'if (badge.dataset.busy) return']
    miss = [n for n in need if n not in src]
    return (not miss), ("徽标按钮 / 循环链 / 连点保护都就位" if not miss
                        else f"缺：{miss}")


@check("服装库单品：就地覆盖母题自带服装")
def t_outfit_swap():
    """指定单品必须**替换**母题正文里那套衣服，而不是追加一句了事。

    实测过的问题：选了「露肩针织 + 百褶裙」，出图还是母题自带的吊带连衣裙，
    因为母题正文里 "She wears a … dress" 贴角色、位置更靠前，追加在末尾的
    单品句根本压不住 —— 等于同时给了两套衣服。
    """
    tags = ["white off-shoulder sweater", "black pleated skirt", "brown loafers"]
    seeds, _ = A.load()
    probe = "k2s_abandoned_garden_2"          # 短提示词分支，母题自带 spaghetti-strap dress
    issues = []

    if probe not in seeds:
        return True, "跳过（母题库已无该样本）"

    t, _log = A.assemble(probe, "miku", "keep", "auto", outfit_tags=tags)
    if "spaghetti-strap" in t:
        issues.append("母题自带连衣裙仍在正文")
    if tags[0] not in t:
        issues.append("单品未进正文")
    if "these garments" not in t:
        issues.append("未生成服装指令句")

    # 姿势类 tag（Anima 服装库里混着的 "crossed legs"）不能写成「她穿着盘腿」
    t2, _ = A.assemble(probe, "miku", "keep", "auto", outfit_tags=tags + ["crossed legs"])
    if "crossed legs" in t2:
        issues.append("姿势 tag 进了正文")

    # 不选单品 → 母题原服装句必须原样保留（零漂移）
    t3, _ = A.assemble(probe, "miku", "keep", "auto")
    if "spaghetti-strap" not in t3:
        issues.append("未选单品却动了母题服装")

    # 服装 = 保持母题原样 → 明确忽略单品，不偷换
    t4, _ = A.assemble(probe, "miku", "keep", "keep", outfit_tags=tags)
    if tags[0] in t4:
        issues.append("keep 模式下仍强行换装")

    # 三个分支都要覆盖（短提示 / 长篇场景 / 平面海报）
    probes = [probe,
              "k2x_blackbody",                                  # scene：服装句藏在机位段
              next((i for i, s in seeds.items()
                    if (s.get("branch") or "scene") == "poster"), "")]
    for sid in [p for p in probes if p and p in seeds]:
        tt, _ = A.assemble(sid, "miku", "keep", "auto", outfit_tags=tags)
        if tags[0] not in tt:
            issues.append(f"{sid} 单品未进正文")
    return (not issues), ("短提示 / 场景 / 海报三分支均就地换装，姿势 tag 已过滤"
                          if not issues else "；".join(issues))


@check("选单品时：身份句的原作服装与海报随机版型都让位")
def t_outfit_identity():
    """角色身份句里写死的原作服装必须让位，否则选了单品也照样画回原套装。

    实测：方形专辑母题给 furina 选「露肩针织 · 百褶裙」，出图还是全套 Fontaine
    礼仪服 + 深蓝高帽 —— identity 写着 "ceremonial outfit"、guard 钉着
    "no missing top hat"，两句都比服装指令硬；海报还额外随机套了一套「西装式」剪裁。
    """
    tags = ["white off-shoulder sweater", "black pleated skirt", "brown loafers"]
    seeds, chars = A.load()
    fur = chars.get("furina")
    if not fur:
        return True, "跳过（角色库无 furina）"
    issues = []

    t, _ = A.assemble("k2p_square_album", "furina", "keep", "auto",
                      outfit_tags=tags, char_obj=fur)
    low = t.lower()
    for w in ("ceremonial outfit", "top hat"):
        if w in low:
            issues.append(f"身份句仍写死「{w}」")
    if tags[0] not in t:
        issues.append("单品未进正文")
    if t.count("these garments") > 1:
        issues.append(f"服装指令重复 {t.count('these garments')} 次")
    if "tailored suit" in low or "a close-fitting technical bodysuit" in low:
        issues.append("海报仍随机套了一套版型剪裁")

    # 生成角色（Anima 桥）身份句里的服装类 signature 也要能剥掉
    gen = B.char_entry("hatsune_miku")
    if gen:
        cf = A.costume_free_char(gen)
        if "detached sleeves" in cf["identity"]:
            issues.append("生成角色身份句仍留着 detached sleeves")
    return (not issues), ("身份句 / 护盾 / 海报版型三处都已让位"
                          if not issues else "；".join(issues))


@check("按部位替换：上半身母题不写裙/鞋（服装库与官方服装都生效）")
def t_outfit_zones():
    """整套写入会把取景拉远：上半身特写也写「百褶裙 + 乐福鞋」，模型就去补腿和鞋。

    口径：以母题自带服装描述为准，只换它写到的部位；官方服装（char:）走同一条路。
    """
    tags_lib = B.outfit_tags("lib", "ol_knit_pleated")
    if not tags_lib:
        return True, "跳过（服装库无 ol_knit_pleated）"
    issues = []
    seeds, _chars = A.load()

    # 方形专辑：母题只写 cardigan / camisole / choker（上半身特写）
    if "k2p_square_album" in seeds:
        t, _ = A.assemble("k2p_square_album", "furina", "keep", "auto", outfit_tags=tags_lib)
        low = t.lower()
        for w in ("pleated skirt", "loafers"):
            if w in low:
                issues.append(f"上半身母题仍写了「{w}」")
        if "upper body in only these garments" not in low:
            issues.append("没切到 upper 模式")

    # 展纸：母题写的是连衣裙、没写鞋 → 裙子要写、鞋不写
    if "k2s_abandoned_garden_2" in seeds:
        t2, _ = A.assemble("k2s_abandoned_garden_2", "furina", "keep", "auto",
                           outfit_tags=tags_lib)
        low2 = t2.lower()
        if "loafers" in low2:
            issues.append("展纸（母题无鞋）仍写了乐福鞋")
        if "pleated skirt" not in low2:
            issues.append("展纸丢了裙子")

    # 官方服装：furina default = hat / jacket / gloves / shorts / thigh strap
    co = B.char_outfits("furina")
    if co and "k2p_square_album" in seeds:
        tags_co = B.outfit_tags("char", co[0]["id"], "furina")
        t3, _ = A.assemble("k2p_square_album", "furina", "keep", "auto", outfit_tags=tags_co)
        low3 = t3.lower()
        if "shorts" in low3:
            issues.append("官方服装的 shorts 仍写进上半身母题")
        if "jacket" not in low3:
            issues.append("官方服装的上装没写进去")
    return (not issues), ("上半身母题只写 upper，官方服装同样按部位拆"
                          if not issues else "；".join(issues))


@check("版本号 pyproject 与包一致")
def t_version():
    p = os.path.join(ROOT, "pyproject.toml")
    if not os.path.exists(p):
        return False, "缺 pyproject.toml"
    try:
        import tomllib
    except ImportError:
        return True, f"包版本 {pkg.__version__}（无 tomllib，跳过比对）"
    with open(p, "rb") as fh:
        v = (tomllib.load(fh).get("project") or {}).get("version", "")
    return (v == pkg.__version__), f"包 {pkg.__version__} / pyproject {v or '缺失'}"


@check("控件顺序：随机池在 optional 末尾")
def t_widget_order():
    """⚠ 新增控件必须放末尾：插到中间会让老工作流 widgets_values 错位。"""
    it = N.K2EditorialBuilder.INPUT_TYPES()
    opt = list((it.get("optional") or {}).keys())
    tail = opt[-3:]
    want = ["角色随机池", "角色随机作品", "场景随机池"]
    return (tail == want), f"optional 末尾 = {tail}"


# --------------------------------------------------------------------------
# ④ 可选冒烟
# --------------------------------------------------------------------------
@check("前端 JS 语法")
def t_js_syntax():
    js = os.path.join(ROOT, "js", "k2ed_panel.js")
    if not shutil.which("node"):
        return True, "跳过（本机无 node）"
    r = subprocess.run(["node", "--check", js], capture_output=True, text=True)
    return (r.returncode == 0), ("node --check 通过" if r.returncode == 0
                                 else (r.stderr or "")[:200])


@check("HTTP 端点冒烟")
def t_http():
    if not WITH_HTTP:
        return True, "跳过（加 --http 才跑）"
    import urllib.request
    import urllib.error
    api = "http://127.0.0.1:8188"
    seeds, chars = A.load()

    def get(path):
        with urllib.request.urlopen(api + path, timeout=30) as r:
            return r.status, r.read()

    try:
        st, body = get("/k2ed/manifest")
        man = json.loads(body)
        st2, body2 = get("/k2ed/build?motif=" + list(seeds)[0]
                         + "&char=" + list(chars)[0].replace("(", "%28").replace(")", "%29"))
        d = json.loads(body2)
    except Exception as exc:
        return False, f"请求失败：{exc}"
    # 路径穿越：用 realpath + commonpath 挡，编码过的 ../ 也要挡住
    leaks = []
    for p in ("/k2ed/thumb/../assembler.py",
              "/k2ed/thumb/%2E%2E%2Fassembler.py",
              "/k2ed/thumb/thumbs/../../presets/seeds_motifs.json"):
        try:
            with urllib.request.urlopen(api + p, timeout=10) as r:
                leaks.append(f"{p} → {r.status}")
        except urllib.error.HTTPError as e:
            if e.code != 404:
                leaks.append(f"{p} → {e.code}")
        except Exception:
            pass                      # 连接层直接拒绝也算挡住
    ok = (st == 200 and st2 == 200 and d.get("ok") and not leaks
          and len(man.get("motifs") or []) == len(seeds))
    return ok, (f"manifest {len(man.get('motifs') or [])} 条 / build {d.get('words')} 词 / "
                f"穿越 {3 - len(leaks)}/3 拦住" if ok
                else f"异常：{leaks or (st, st2, d.get('ok'))}")


# --------------------------------------------------------------------------
# runner
# --------------------------------------------------------------------------
def main() -> int:
    print(f"Comfyui-K2-Editorial v{pkg.__version__} 回归测试"
          f"{'  [fast]' if FAST else ''}{'  [http]' if WITH_HTTP else ''}")
    print(f"插件目录 {ROOT}")
    src = B.status()
    print(f"角色数据源：{src['source']}（{src['chars']} 角色 / 内置图 {src['thumbs']} 张）")
    print("-" * 78)
    passed = failed = 0
    fails = []
    for i, (name, fn) in enumerate(CHECKS, 1):
        t0 = time.perf_counter()
        try:
            ok, detail = fn()
        except Exception as exc:
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        dt = (time.perf_counter() - t0) * 1000
        print(f"[{i:02d}] {name:<26} {'PASS' if ok else 'FAIL':<5} "
              f"{dt:6.0f}ms  {detail}")
        if ok:
            passed += 1
        else:
            failed += 1
            fails.append((name, detail))
    print("-" * 78)
    total = len(CHECKS)
    print(f"{passed}/{total} 通过" + (f"，{failed} 失败" if failed else "，全绿"))
    for name, detail in fails:
        print(f"  ✗ {name}: {detail}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
