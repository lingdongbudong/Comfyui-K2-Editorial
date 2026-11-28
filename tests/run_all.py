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
import re
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


@check("景别标签：每条母题都有且值域合法")
def t_shots():
    man = _json("manifest.json")
    SHOTS = {"人像", "半身", "全景"}
    miss = [m["id"] for m in man.get("motifs") or [] if not m.get("shot")]
    bad = [f"{m['id']}:{m.get('shot')}" for m in man.get("motifs") or []
           if m.get("shot") and m["shot"] not in SHOTS]
    dist = {k: sum(1 for m in man.get("motifs") or [] if m.get("shot") == k) for k in SHOTS}
    empty = [k for k, v in dist.items() if v == 0]
    ok = not miss and not bad and not empty
    return ok, ("三档齐全 " + " / ".join(f"{k}{v}" for k, v in dist.items()) if ok
                else f"缺标签 {len(miss)} / 越界 {bad[:3]} / 空档 {empty}")


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

    # v1.19.6 单品优先：服装=保持母题原样 + **有效单品** → 单品生效（不再静默忽略）
    t4, l4 = A.assemble(probe, "miku", "keep", "keep", outfit_tags=tags)
    if t4 != t:
        issues.append("keep+单品 与 auto+单品 输出不一致（应完全等价）")
    if tags[0] not in t4 or "spaghetti-strap" in t4:
        issues.append("keep + 有效单品：单品未替换母题服装")
    if not any("覆盖「保持母题原样」" in x for x in l4):
        issues.append("keep + 有效单品：日志缺少覆盖说明")

    # ⚠ 反向守卫：单品被部位/姿势规则**全筛掉**时，keep 必须保持原语义，
    #   不能静默退回「随机套版型」（那比忽略单品更难排查）
    t5, l5 = A.assemble(probe, "miku", "keep", "keep", outfit_tags=["crossed legs"])
    if "spaghetti-strap" not in t5:
        issues.append("keep + 单品全被筛掉：母题服装被动了（应保持原样）")
    if any("覆盖「保持母题原样」" in x for x in l5):
        issues.append("keep + 单品全被筛掉：不应触发覆盖")

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


@check("内联/所有格/全篇服装名：换装后不留旧衣服")
def t_outfit_inline():
    """衣服有三种「不按整句列举」的写法，旧代码一个都没处理：

    · 内联介词短语：`standing … at night in a yukata`
    · 所有格：`the hem of her yukata` / `her wooden sandals`
    · 全篇反复点名：`white top / dark skirt` 在 9 个段落里出现
    前两类会把构图整段带偏（浴衣 → 雪纺）；第三类只改服装段等于没改。
    """
    tags = B.outfit_tags("lib", "ol_knit_pleated")
    if not tags:
        return True, "跳过（服装库无 ol_knit_pleated）"
    seeds, _ = A.load()
    issues = []
    probes = [("k2x_hanabi_bank", ("yukata", "kimono")),
              ("k2x_clsc_tifa", ("white top", "dark skirt")),
              ("k2s_cinema_wait_14", ("sailor",))]
    for sid, words in probes:
        if sid not in seeds:
            continue
        t, _ = A.assemble(sid, "miku", "keep", "auto", outfit_tags=tags)
        for w in words:
            if w in t.lower():
                issues.append(f"{sid} 仍写着「{w}」")
    # 反例：空间定位不能被当成穿着（"scuffed in a broad arc where boots have turned"）
    if A.rewrite_inline_garments(
            "The stone is scuffed in a broad arc where boots have turned")[1]:
        issues.append("把空间短语误当穿着（broad arc where boots）")
    return (not issues), ("内联/所有格/全篇三类写法都已处理，空间短语不误伤"
                          if not issues else "；".join(issues))


@check("换角色后不留原角色特征")
def t_residue():
    """母题库是围绕 Miku 写的，换角色后这些「角色特征锚点」必须一起中性化：

      · "the outer twin-tail ends" / "aqua twintails"（连字符 / 无空格写法）
      · "full body from boots to hair ornaments"
      · "her face, eyes, hands and hair ornaments must stay readable"
      · 护盾里的 "no duplicate Miku" / "no missing twin tails"
      · "virtual-singer stillness" / tag 里的 virtual singer

    漏掉任何一条，模型都会把 aqua + 双马尾当角色特征画出来 —— 就是用户报的
    「换了对象还是青绿色双马尾」。同时反向验证：Miku 本人的双马尾不能被抹掉。
    """
    seeds, chars = A.load()
    issues = []
    # 1) 非 Miku 角色：逐条母题扫残留
    key = "cirno"
    try:
        ch = B.char_entry("cirno")
    except Exception:
        ch = None
    if not ch:
        key, ch = "furina", chars.get("furina")
    if not ch:
        return True, "跳过（无可用非 Miku 角色）"
    bad = re.compile(r"\bMiku\b|\bHatsune\b|\btwin[\s-]?tails?\b|\btwintails?\b"
                     r"|\bvirtual[\s-]singer\b|\bhair ornaments?\b", re.I)
    hits = []
    for sid, seed in seeds.items():
        txt, _ = A.assemble(sid, key, "keep", "auto", char_obj=ch)
        for para in A.paras(txt):
            # 角色自己的护盾里 "no missing hair ornament" 是合法的，只查正文
            if A.is_guard(para):
                if re.search(r"\bMiku\b|\bHatsune\b|twin[\s-]?tails?|twintails?", para, re.I):
                    hits.append(f"{sid}: 护盾残留")
                continue
            m = bad.search(para)
            if m:
                hits.append(f"{sid}: {m.group(0)}")
                break
        if len(hits) >= 3:
            break
    if hits:
        issues.append("残留 " + "；".join(hits[:3]))

    # 2) 手写角色的 guard 不能抄 Miku 的否定项（"no Miku, no aqua twin tails"）
    for key, c in chars.items():
        g = (c.get("guard") or "") + " " + (c.get("guard_plain") or "")
        if key != "miku" and re.search(r"\bMiku\b|aqua twin tails", g, re.I):
            issues.append(f"{key} 的 guard 抄了 Miku 的否定项")

    # 3) 反向：Miku 本人仍要留下双马尾
    mk = chars.get("miku")
    if mk:
        txt, _ = A.assemble("k2x_veil_fall_a", "miku", "keep", "auto", char_obj=mk)
        if not re.search(r"twin[\s-]?tails?", txt, re.I):
            issues.append("Miku 本人的双马尾被误抹")
    return (not issues), ("全量无残留，Miku 自身不受影响" if not issues else "；".join(issues))


@check("母题角色装饰：只有登记角色保留水晶翼")
def t_owner_props():
    """唱片店 / 榻榻米房正文里写着「六片水晶翼」—— 那是甘雨的专属装饰，不是场景陈设。

    换别人还留着，模型就把翼画在人背上（阿尔托莉雅版实测 428 词里三处 wing 全在）。
    母题用 _meta.json 的 owner_char 登记归属，装配时按角色分流：

      · 选中角色 == owner_char → 保留
      · 选中其他角色           → 连子句一起摘掉，且同段其它内容一个字不动
    """
    seeds, _ = A.load()
    probes = {"k2s_record_store": "icy-blue bob", "k2s_tatami_room": "back rim lighting"}
    issues = []
    for sid, same_para in probes.items():
        seed = seeds.get(sid)
        if not seed:
            issues.append(f"{sid}: 母题缺失")
            continue
        owner = seed.get("owner_char") or ""
        if not owner:
            issues.append(f"{sid}: 未登记 owner_char")
            continue
        if not re.search(r"wings?", seed["raw"], re.I):
            issues.append(f"{sid}: 正文已无翼（本用例失效，需同步更新）")
            continue
        t_own = A.strip_owner_props(seed["raw"], [], owner, owner)
        t_other = A.strip_owner_props(seed["raw"], [], owner, "furina")
        if not re.search(r"wings?", t_own, re.I):
            issues.append(f"{sid}: 原角色的翼被误删")
        if re.search(r"wings?", t_other, re.I):
            issues.append(f"{sid}: 换角色仍带翼")
        if same_para not in t_other:
            issues.append(f"{sid}: 摘翼时误伤同段内容「{same_para}」")
        # 没登记 owner_char 的母题必须原样返回（别把全场母题都洗一遍）
        if A.strip_owner_props("her wings spread", [], "", "furina") != "her wings spread":
            issues.append("未登记母题的正文被改动")
    # 反向：本人就有冰翼的角色（琪露诺）不能被误伤 —— 摘的是母题那一份，不是她的身份
    try:
        cir = B.char_entry("cirno")
    except Exception:
        cir = None
    if cir and re.search(r"wings?", cir.get("identity") or "", re.I):
        t = A.assemble("k2s_record_store", "cirno", "keep", "auto", char_obj=cir)[0]
        if re.search(r"ice-crystal wings|crystalline wings", t, re.I):
            issues.append("琪露诺仍带母题的水晶翼")
        if not re.search(r"wings?", t, re.I):
            issues.append("琪露诺自己的冰翼被误删")
    return (not issues), ("登记角色保留 / 换角色摘除 / 同段内容完好 / 未登记母题不动 / 自带翼角色不受损"
                          if not issues else "；".join(issues))


@check("不显示文字：大字母与小字母一起消失")
def t_no_text():
    """勾「画面不显示文字」后，大标题、编号小字、铭牌、stencil 都不能再进正文。

    踩过的坑：早期只删引号里那个词，`Let a second, much smaller exact readable
    line “UNIT 9” sit on a small enamel plate` 剩下的半句照样催出一排小字。
    """
    seeds, _ = A.load()
    issues = []
    quotes = re.compile(r"[“”]|\"[^\"\n]{1,40}\"")
    for sid, seed in seeds.items():
        txt, _ = A.assemble(sid, None, None, "auto", no_text=True)
        rep = A.validate(txt, None, A.seed_branch(sid), A.seed_character(sid))
        if rep["issues"]:
            issues.append(f"{sid}: {rep['issues'][0]}")
        for p in A.paras(txt):
            if A.is_guard(p) or "no readable lettering of any kind" in p:
                # ⚠ 只查「no readable X beyond/except Y」——`no gardener beyond the gate`
                # 是场景否定，一刀切 beyond 会误报
                if re.search(r"no readable [^,]{0,70}\b(beyond|except|other than)\b", p, re.I):
                    issues.append(f"{sid}: 护盾仍写「除上文那个词」")
                continue
            if quotes.search(p):
                issues.append(f"{sid}: 仍有引号文字")
                break
            for sent in A._SENT_SPLIT.split(p):
                if A._PROTECT_SENT.match(sent.strip()):
                    continue
                if A._is_text_instruction(sent):
                    issues.append(f"{sid}: 仍有写字指令「{sent.strip()[:40]}」")
                    break
        if len(issues) >= 3:
            break
    return (not issues), ("558 条母题：无引号、无写字句、篇幅合规" if not issues
                          else "；".join(issues[:3]))


@check("坐姿分类：标签、名字与正文一致")
def t_sitting_tag():
    """「坐姿」分类里的每一条，正文必须真是坐着的，名字必须带「·坐姿」。

    这个分类是手动标的（motif_tags.json），最容易的漂移是：改了母题姿势却忘摘标签，
    或者反了 —— 正文坐姿但没进分类。两头都查。
    """
    seeds, _ = A.load()
    man = json.load(open(os.path.join(PRESETS, "manifest.json"), encoding="utf-8"))
    issues = []
    entry = next((t for t in man.get("tags", []) if t["key"] == "sitting"), None)
    if not entry:
        return False, "manifest 里没有 sitting 分类"
    if entry.get("zh") != "坐姿":
        issues.append(f"sitting 的中文名是「{entry.get('zh')}」")
    tagged = [m for m in man["motifs"] if "sitting" in m["tags"]]
    if entry.get("count") != len(tagged):
        issues.append(f"count={entry.get('count')} 实际 {len(tagged)}")
    if not tagged:
        issues.append("分类为空")
    for m in tagged:
        raw = (seeds.get(m["id"]) or {}).get("raw", "")
        head = " ".join(A.paras(raw)[:2]).lower()
        if not re.search(r"\b(seated|sitting|sits)\b", head):
            issues.append(f"{m['id']}: 标了坐姿但正文是站姿")
        if not (m.get("zh") or "").endswith("·坐姿"):
            issues.append(f"{m['id']}: 名字没改成「…·坐姿」（{m.get('zh')}）")
    return (not issues), (f"{len(tagged)} 条坐姿母题：标签 / 名字 / 正文三方一致"
                          if not issues else "；".join(issues[:3]))


@check("LORA 服装触发词模式：正文零服装词")
def t_lora_no_outfit():
    """开了 LORA 服装触发词模式，提示词里就不该再出现任何服装词。

    服装库单品 / 版型句 / 官方预设 / 母题自带的 "wool coat" 全都要停写，
    否则出图是「LORA 的衣服 + 母题的外套」缝在一起；色盘段里那些
    「十二 percent 是她的外套」也要一并摘掉并**把百分比重算到 100**。
    """
    seeds, chars = A.load()
    issues = []
    ch = chars.get("furina")
    if not ch:
        return True, "跳过（无可用角色）"
    for sid, seed in seeds.items():
        txt, _ = A.assemble(sid, "furina", "keep", "auto", char_obj=ch, no_outfit=True)
        rep = A.validate(txt, None, A.seed_branch(sid), "")
        if rep["issues"]:
            issues.append(f"{sid}: {rep['issues'][0]}")
        for p in A.paras(txt):
            if A.is_guard(p) or p.strip().startswith("Let her character trigger"):
                continue
            m = A._LORA_GARMENT_RE.search(p)
            if m:
                # 母题标题本身可能就叫 SCARF / COAT，那属于画内文字，不算服装描述
                if re.search(r"titled\s+[“\"]?" + re.escape(m.group(0)), p, re.I):
                    continue
                issues.append(f"{sid}: 残留服装词「{m.group(0)}」")
                break
        if len(issues) >= 3:
            break
    return (not issues), ("558 条母题：零服装词、色盘 100、篇幅合规" if not issues
                          else "；".join(issues[:3]))


@check("经典人物 / 坐姿母题不绑定角色")
def t_no_recommend_char():
    """点母题不再自动换人 —— 面板只在 recommend_char 非空时才切角色。

    v1.19.5 起 clsc（经典人物）18 条全部解绑，「坐姿」那 6 条也在其中。
    这条用例同时查 manifest（面板数据）与 seeds_extra（装配数据），两边都不能残留。
    """
    seeds, _ = A.load()
    man = json.load(open(os.path.join(PRESETS, "manifest.json"), encoding="utf-8"))
    issues = []
    bound = [m["id"] for m in man["motifs"] if m.get("recommend_char")]
    if bound:
        issues.append(f"manifest 仍有 {len(bound)} 条绑定角色：{bound[:3]}")
    for m in man["motifs"]:
        if m.get("series") == "clsc" or "sitting" in (m.get("tags") or []):
            s = seeds.get(m["id"]) or {}
            if s.get("recommend_char"):
                issues.append(f"{m['id']}: seeds_extra 仍写 recommend_char")
    return (not issues), ("经典人物 18 条 + 坐姿 6 条均无推荐角色绑定"
                          if not issues else "；".join(issues[:3]))


@check("短提示自动套官方服装 + 画内文字换名")
def t_auto_official():
    """两件事：

    · 短提示词（tag 流）母题自带的是 Miku 的服装 tag（detached sleeves / thighhighs）。
      换角色且没手选服装 → 自动套该角色的官方服装预设，否则那半套原角色衣服留在提示词里。
      场景 / 海报分支不套（服装段本来就由版型模板接管）。
    · 画内文字 "HATSUNE MIKU" 要跟着换角色名（大小写风格跟着原文）。
    """
    seeds, chars = A.load()
    issues = []
    ch = None
    try:
        ch = B.char_entry("cirno")
    except Exception:
        pass
    ch = ch or chars.get("furina")
    key = "cirno" if ch and ch.get("short") == "Cirno" else "furina"
    if not ch:
        return True, "跳过（无可用角色）"

    tags, _why = N.auto_official_tags(key, "k2s_cx_023", "auto", [])
    if not tags:
        issues.append("短提示未自动套官方服装")
    else:
        t, _ = A.assemble("k2s_cx_023", key, "keep", "auto", char_obj=ch, outfit_tags=tags)
        if re.search(r"detached sleeves|\bthighhighs?\b", t, re.I):
            issues.append("原角色服装 tag 仍在正文")
        if not any(x.lower() in t.lower() for x in tags):
            issues.append("官方服装未进正文")
    if N.auto_official_tags(key, "k2x_veil_fall_a", "auto", [])[0]:
        issues.append("场景分支被误套官方服装")
    keep = ["custom item"]
    if N.auto_official_tags(key, "k2s_cx_023", "auto", keep)[0] != keep:
        issues.append("手选单品被自动覆盖")

    t2, _ = A.assemble("k2s_bridge_line_3", key, "keep", "auto", char_obj=ch)
    if re.search(r"\bMIKU\b|\bHATSUNE\b", t2, re.I):
        issues.append("画内文字仍印 MIKU")
    elif (ch.get("short") or "").upper() not in t2.upper():
        issues.append("画内文字未换成目标角色名")
    return (not issues), ("自动套官方服装 / 分支隔离 / 手选优先 / 画内文字换名均正确"
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


@check("控件顺序：新控件只准追加在 optional 末尾")
def t_widget_order():
    """⚠ 新增控件必须放末尾：插到中间会让老工作流 widgets_values 错位。

    另外随机池那三个必须**连在一起**：它们是一组，拆开会让老工作流的
    「角色随机池」读到「场景随机池」的值（v1.19.6 只在其后再追加 LORA 开关）。
    """
    it = N.K2EditorialBuilder.INPUT_TYPES()
    opt = list((it.get("optional") or {}).keys())
    pools = ["角色随机池", "角色随机作品", "场景随机池"]
    i = opt.index(pools[0]) if pools[0] in opt else -1
    ok_pool = i >= 0 and opt[i:i + 3] == pools
    # 随机池三连 → LORA 服装触发词 → 锁定发色（v1.20.0 追加，仍必须在最末）
    ok_tail = (opt[-2:] == ["LORA服装触发词", "锁定发色"]
               and opt[-5:-2] == pools)
    return (ok_pool and ok_tail), f"optional 末尾 = {opt[-5:]}"


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
