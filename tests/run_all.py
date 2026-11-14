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
