/* =============================================================================
 * Comfyui-K2-Editorial · 设置面板 v3
 *
 * 三页：① 角色（Anima 全量 2432，分页 + 搜索 + 作品筛选）
 *       ② 服装（版型 8 / 角色专属预设 / 服装库，数量随 Anima 增长）
 *       ③ 场景（母题，中文名为主、英文原名为副）
 * 右侧固定预览栏：角色 / 版型 / 单品 / 场景 + 画幅 + 动作按钮。
 *
 * 口径：
 *   · 同一个设置只留一个入口 —— 五个控件在节点上折叠隐藏，只在面板里选。
 *   · 隐藏不能丢值 —— 节点正文用 onDrawForeground 画摘要。
 *   · ⚠️ 多行 STRING 是 DOM 控件，必须同时关 element，只归零 computeSize 藏不住。
 *   · 选中/搜索一律就地切换或分页请求，不整页重建（重建会丢焦点、滚回顶部）。
 * ========================================================================== */

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const NODE_NAME = "K2EditorialBuilder";
const HIDDEN = ["随机种子", "每次重随机", "角色", "母题", "画幅", "服装", "单品",
                "覆盖提示词", "画面英文文字", "画面不显示英文", "画面文字模式",
                "角色随机池", "角色随机作品", "场景随机池", "LORA服装触发词",
                // 「⚙ 打开设置面板」不再用 widget：widget 的点击命中按 litegraph 的
                // last_y 判，节点一收缩就落在节点外（画得出来、点不着）。改由节点自绘 + onMouseDown。
                "⚙ 打开设置面板"];
const BTN_LABEL = "⚙ 打开设置面板";
const BTN_H = 26;
const PAGE_SIZE = 72;
const SEED_MAX = 0xFFFFFFFF;

const ASPECT_SIZE = {
    "16:9": [1920, 1088], "3:2": [1728, 1152], "4:3": [1664, 1248],
    "1:1": [1536, 1536], "4:5": [1536, 1920], "3:4": [1248, 1664],
    "2:3": [1152, 1728], "9:16": [1088, 1920],
};
/* XB_ImageParamsMaster 的 aspect_ratio 枚举只认这几个，其余必须走 Free + 显式宽高 */
const ASPECT_NATIVE = new Set(["16:9", "9:16", "4:3", "3:4", "1:1"]);
const ACCENT_HEX = {
    aqua: "#5DCAA5", cobalt: "#378ADD", violet: "#7F77DD", crimson: "#E24B4A",
    teal: "#1D9E75", graphite: "#5F5E5A", ivory: "#D3D1C7", champagne: "#EF9F27",
    platinum: "#B4B2A9", umber: "#993C1D", rose: "#D4537E", amber: "#BA7517",
};

let MAN = null;
let PANEL = null;
let CUR = null;

const STATE = {
    tab: "char", char: "miku", motif: "", aspect: "16:9",
    costume: "自动（跟随母题）", item: "",
    text: "", edited: false, showText: false,
    q: "", work: "", offset: 0, total: 0, works: [], chars: [],
    outfits: null, outfitCat: "", charMeta: null, allTotal: 0,
    favs: { characters: [], costumes: [], motifs: [], works: [] },
    favOnlyCostume: false, favOnlyMotif: false, motifAspect: "", motifBranch: "",
    motifRef: "",               // 人物参考图模式：front = 正面全身 / sheet = 四视图
    motifQ: "",                 // 场景页：关键词搜索
    /* 场景页筛选改成多选（集合）：同一维度内 OR，维度之间 AND。
       单选时代没法问「室内 + 夜间」，只能一个个试。 */
    motifTags: new Set(), motifGenres: new Set(), motifSeries: new Set(),
    motifShots: new Set(),      // 景别：特写 / 近景 / 中景 / 远景 / 超远景
    motifView: "group",         // group = 按风格系列分组平铺 / grid = 全部平铺
    motifMulti: false,          // 分类多选总开关（默认关 = 同维度单选）
    motifLast: { tags: "", genres: "", series: "", shots: "" },   // 各维度最后点的一项，关多选时只留它
    addedOnly: false,           // 场景页：只看新增（入库批次）
    displayText: "", noText: false, lora: false, hairlock: false,
    /* 随机池：模式写回节点（可复现），勾选的场景 id 存服务端（可能几百条） */
    charPool: "关闭", charPoolWork: "", motifPool: "关闭", picks: [],
    locks: {},
    _syncedAspect: "",          // 上次同步到参数节点的画幅，避免每次点选都重复写
    seedMode: "random", seed: 0,   // 随机种子：random = 每次运行换一个 / fixed = 固定可复现
};

/* ---------------- 场景页滚动记忆（只在面板开着期间有效，不写盘） ----------------
   只记「滚动像素位置」，不记锚点卡片。
   曾经试过「记住视口第一张卡 + 偏移」的锚点方案：筛选一变分组增减、卡片换行数变化，
   锚点算出来的目标位置会偏离几百像素，表现就是「取消一个分类、列表自己跳到下面」。
   现在统一按像素复原：筛选前后页面纹丝不动，只有内容变短时才被夹到新的底部。
   重绘期间挂起 scroll 监听，避免 innerHTML="" 触发的归零把记忆覆盖成 0。 */
let MOTIF_SCROLL = { top: 0 };
let _motifPaintDepth = 0;

function captureMotifScroll(force) {
    if (STATE.tab !== "motif") return;              // 页签已切走：保留旧记忆
    if (!force && _motifPaintDepth > 0) return;     // 重绘中：别被归零事件污染
    const page = pageEl();
    if (!page) return;
    MOTIF_SCROLL.top = page.scrollTop;
}

function restoreMotifScroll() {
    const page = pageEl();
    if (!page || STATE.tab !== "motif") return;
    const clamp = () => Math.max(0, page.scrollHeight - page.clientHeight);
    const want = Math.max(0, Math.min(MOTIF_SCROLL.top, clamp()));
    page.scrollTop = want;
    // 重建当帧赋值可能仍被布局夹到 0，下一帧再压一次（同角色页 renderWorkList）。
    requestAnimationFrame(() => {
        if (page.isConnected) page.scrollTop = Math.max(0, Math.min(want, clamp()));
    });
}

function motifPaintBegin() {
    if (STATE.tab !== "motif") return;
    if (_motifPaintDepth === 0) captureMotifScroll(true);
    _motifPaintDepth++;
}
function motifPaintEnd() {
    if (_motifPaintDepth === 0) return;
    _motifPaintDepth--;
    if (_motifPaintDepth === 0 && STATE.tab === "motif") restoreMotifScroll();
}
function bindMotifScrollMemory() {
    const page = pageEl();
    if (!page || page.dataset.scrollMem) return;
    page.dataset.scrollMem = "1";
    page.addEventListener("scroll", () => captureMotifScroll(false), { passive: true });
}

/* ⚠️ 第二个参数是「类名或内联样式」二选一：
   含 ; 或 : 当内联样式（cssText），否则当 className。
   早期版本一律当 cssText，导致 el("span","lb") / el("img","im") 这类调用
   静默丢类名 —— 布局与图片比例全部失效，且不报错。 */
const el = (tag, css, text) => {
    const n = document.createElement(tag);
    if (css) {
        if (/[;:]/.test(css)) n.style.cssText = css;
        else n.className = css;
    }
    if (text !== undefined) n.textContent = text;
    return n;
};
/* ?v= 是缩略图文件的 mtime：ComfyUI 静态服务给 .webp 发 24 小时强缓存，
   而路径固定 —— 不拼版本号的话换图后浏览器会一直显示旧图。 */
const thumbURL = (p, v) => (p
    ? api.apiURL("/k2ed/thumb/" + p.replace(/^\/+/, "")) + (v ? `?v=${v}` : "")
    : "");
const getW = (node, name) => node.widgets?.find((w) => w.name === name);
const pageEl = () => PANEL.panel.querySelector("#k2ed-page");

/* ---------------- 节点摘要用的只读名字表 ----------------
   ⚠ 摘要必须只读「本节点 widget + 这张表」，绝不能读全局 STATE。
   STATE 是面板的单例（一份 DOM、一份选择）：画布上放两个本节点时，
   后打开面板的那个会把两个节点的摘要一起改掉，看上去像 A 选了 B 的场景。
   这里只缓存「id → 中文名」，由面板渲染/取数时顺手登记，与选择状态无关。 */
const CHAR_NAME = new Map();          // 角色 id → { zh, work }
const ITEM_NAME = new Map();          // 单品 id（含 char: / lib: 前缀）→ 中文名

function noteChar(c) {
    if (c && c.id) CHAR_NAME.set(c.id, { zh: c.zh || c.id, work: c.work_zh || c.work || "" });
}
function noteItems(outfits) {
    if (!outfits) return;
    for (const o of (outfits.character || [])) ITEM_NAME.set("char:" + o.id, o.zh || o.id);
    for (const o of (outfits.library || [])) ITEM_NAME.set("lib:" + o.id, o.zh || o.id);
}
let MOTIF_MAP = null;                 // 母题 id → manifest 条目（395 条，别在每帧 find）
function motifMeta(id) {
    if (!id || !MAN) return null;
    if (!MOTIF_MAP) {
        MOTIF_MAP = new Map();
        for (const m of (MAN.motifs || [])) MOTIF_MAP.set(m.id, m);
    }
    return MOTIF_MAP.get(id) || null;
}

async function manifest() {
    if (MAN) return MAN;
    const r = await api.fetchApi("/k2ed/manifest");
    MAN = await r.json();
    MOTIF_MAP = null;
    if (!MAN.costume_templates) MAN.costume_templates = [];
    return MAN;
}

/* ---------------- 随机池：勾选的场景 id 在服务端 ---------------- */
let _poolsLoaded = false;
async function loadPicks(force) {
    if (_poolsLoaded && !force) return STATE.picks;
    try {
        const r = await api.fetchApi("/k2ed/pick");
        const d = await r.json();
        STATE.picks = d.motif || [];
        _poolsLoaded = true;
    } catch (e) {
        STATE.picks = [];
    }
    return STATE.picks;
}

async function savePicks(payload) {
    try {
        const r = await api.fetchApi("/k2ed/pick", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const d = await r.json();
        STATE.picks = d.motif || [];
    } catch (e) {
        PANEL?.stat("⚠ 勾选保存失败：" + e);
    }
    return STATE.picks;
}

function setW(node, name, val) {
    const w = getW(node, name);
    if (!w) return false;
    w.value = val;
    // BOOLEAN 在新前端是 DOM 复选框：只改 value 会让界面勾选状态不同步
    const inp = w.inputEl
        || (w.element && w.element.querySelector?.("input[type=checkbox]"));
    if (inp && inp.type === "checkbox") inp.checked = !!val;
    try { w.callback?.(val, app.canvas, node, {}); } catch (e) { /* noop */ }
    return true;
}

/* ---------------- 折叠隐藏控件（含 DOM 控件） ---------------- */
function hideWidgets(node) {
    for (const name of HIDDEN) {
        const w = getW(node, name);
        if (!w) continue;
        w.computeSize = () => [0, -4];
        w.draw = () => {};
        if (w.element) w.element.style.display = "none";
        if (w.inputEl) w.inputEl.style.display = "none";
    }
}

function tplZh(id) {
    const t = (MAN?.costume_templates || []).find((x) => x.id === id);
    return t ? t.zh : "";
}

/* 单品中文名：改用 ITEM_NAME 名字表（noteItems 登记），摘要不再读 STATE */

function installSummary(node) {
    if (node._k2ed_sum) return;
    node._k2ed_sum = true;
    const of = node.onDrawForeground;
    node.onDrawForeground = function (ctx) {
        of?.apply(this, arguments);
        /* 只读本节点 widget：多节点并存时各画各的，互不干扰 */
        const val = (n) => getW(node, n)?.value;
        const cid = val("角色") || "";
        const mid = val("母题") || "";
        const cName = (CHAR_NAME.get(cid) || {}).zh || cid;
        const m = motifMeta(mid);
        const cos = val("服装") || "";
        const item = val("单品") || "";
        const bits = [cName, val("画幅") || ""];
        /* MAN 在面板打开前是 null，这里用字面量兜底，否则「保持母题原样」会显示成「版型」 */
        const TPL_AUTO = MAN?.auto || "自动（跟随母题）";
        const TPL_KEEP = MAN?.keep || "保持母题原样";
        if (cos && cos !== TPL_AUTO) {
            bits.push(cos === TPL_KEEP ? "保持母题原样" : (tplZh(cos) || "版型"));
        }
        if (item) bits.push(ITEM_NAME.get(item) || "单品");
        const rv = val("每次重随机");
        const isRand = !(rv === false || rv === "false" || rv === 0);
        const seedTxt = isRand ? "种子 随机"
            : `种子 #${(parseInt(val("随机种子"), 10) || 0) >>> 0}`;
        const lines = [bits.join("　·　"),
                       `${m ? (m.zh || m.title || m.id) : (mid || "未选场景")}　·　${seedTxt}`];
        ctx.save();
        ctx.font = "12px sans-serif";
        ctx.fillStyle = (typeof LiteGraph !== "undefined" && LiteGraph.WIDGET_TEXT_COLOR) || "#ddd";
        let y = 26;
        for (const t of lines) { ctx.fillText(t, 12, y); y += 15; }
        ctx.restore();

        // 按钮已改为 DOM widget（见 onNodeCreated），这里只画摘要文字
    };
}

function syncStateFromNode(node) {
    STATE.char = getW(node, "角色")?.value || STATE.char;
    STATE.motif = getW(node, "母题")?.value || STATE.motif;
    STATE.aspect = getW(node, "画幅")?.value || STATE.aspect;
    STATE.costume = getW(node, "服装")?.value || MAN?.auto || "自动（跟随母题）";
    STATE.item = getW(node, "单品")?.value || "";
    STATE.displayText = getW(node, "画面英文文字")?.value || "";
    const nt = getW(node, "画面不显示英文")?.value;
    STATE.noText = (nt === true || nt === "true" || nt === 1);
    const lo = getW(node, "LORA服装触发词")?.value;
    STATE.lora = (lo === true || lo === "true" || lo === 1);
    const hl = getW(node, "锁定发色")?.value;
    STATE.hairlock = (hl === true || hl === "true" || hl === 1);
    const rand = getW(node, "每次重随机")?.value;
    STATE.seedMode = (rand === false || rand === "false" || rand === 0) ? "fixed" : "random";
    const sv = parseInt(getW(node, "随机种子")?.value, 10);
    if (Number.isFinite(sv)) STATE.seed = sv >>> 0;
    STATE.charPool = getW(node, "角色随机池")?.value || "关闭";
    STATE.charPoolWork = getW(node, "角色随机作品")?.value || "";
    STATE.motifPool = getW(node, "场景随机池")?.value || "关闭";
}

/* ---------------- 面板骨架 ---------------- */
function ensurePanel() {
    // ⚠ 不能只判 null：ComfyUI 换工作流 / 前端重挂时 body 可能被重建，
    //   PANEL 还指着已经脱离文档的旧节点 —— 之后 display:flex 设了也看不见，
    //   表现就是「点打开设置面板没反应」（用户报的间歇性问题）。
    if (PANEL && PANEL.mask && document.body.contains(PANEL.mask)) return PANEL;
    if (PANEL) { try { PANEL.mask.remove(); } catch (e) { /* 已脱离文档 */ } }
    PANEL = null;

    const style = el("style", "");
    style.textContent = `
    .k2ed-mask{position:fixed;inset:0;background:rgba(0,0,0,.58);z-index:10000;
      display:flex;align-items:center;justify-content:center;
      font-family:system-ui,"Microsoft YaHei",sans-serif}
    .k2ed-panel{position:relative;width:min(1600px,96vw);height:min(950px,94vh);background:#16171b;
      color:#e6e6e6;border:1px solid #33353d;border-radius:14px;display:flex;flex-direction:column;
      overflow:hidden;box-shadow:0 24px 70px rgba(0,0,0,.6)}
    .k2ed-hd{display:flex;align-items:baseline;gap:12px;padding:12px 16px 8px}
    .k2ed-hd b{font-size:15px;font-weight:500}
    /* 副标题可压缩：加了三个外链按钮后，窗口窄时先截断它，别把按钮挤到第二行 */
    .k2ed-hd .sub{font-size:12px;color:#8b8f98;flex:0 1 auto;min-width:0;
      overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .k2ed-x{margin-left:auto;cursor:pointer;border:1px solid #3a3d45;background:#22242a;color:#ccc;
      border-radius:8px;padding:4px 10px;font-size:13px}
    .k2ed-x:hover{background:#2e3138;color:#fff}
    /* 顶部外链组：教学视频 / 图片欣赏 / GitHub。auto 推挤放在这组上，
       免责声明与关闭排在它右侧（原来 auto 在免责声明身上）。
       ⚠ 模板字符串里不能写反引号注释，只能这样写块注释。 */
    .k2ed-hd .k2ed-links{margin-left:auto;display:flex;align-items:center;gap:6px;
      align-self:center;flex:0 0 auto}
    .k2ed-hd .k2ed-links a{cursor:pointer;border:1px solid #3a3d45;background:#1e2026;
      color:#b9bdc6;border-radius:8px;padding:4px 10px;font-size:12.5px;line-height:1.5;
      text-decoration:none;display:inline-flex;align-items:center;gap:5px;white-space:nowrap}
    .k2ed-hd .k2ed-links a:hover{background:#2e3138;color:#8fd0ff;border-color:#3d6a86}
    /* 免责声明入口：紧跟外链组，「关闭」再跟其后 */
    .k2ed-hd .k2ed-dis{margin-left:0;cursor:pointer;border:1px solid #3a3d45;background:#1e2026;
      color:#b9bdc6;border-radius:8px;padding:4px 10px;font-size:12.5px;line-height:1.5;
      display:inline-flex;align-items:center;gap:5px;flex:0 0 auto}
    .k2ed-hd .k2ed-dis:hover{background:#2e3138;color:#e8c96a;border-color:#5c4d29}
    .k2ed-hd .k2ed-dis .dot{color:#8b8f98;font-size:11px}
    .k2ed-hd .k2ed-x{margin-left:0;flex:0 0 auto}
    /* flex-wrap：页签行现在有 4 个页签 + LORA 开关 + 角色自检 + 锁定发色 + 右侧画幅/种子，
       窄屏或放大字号时靠 wrap 兜底，别把右侧的种子框挤没 */
    .k2ed-tabs{display:flex;align-items:center;gap:6px;row-gap:6px;flex-wrap:wrap;
      padding:0 16px 10px;border-bottom:1px solid #2a2c33}
    .k2ed-tab{padding:6px 16px;border-radius:8px;cursor:pointer;font-size:13px;border:1px solid transparent;
      color:#b9bdc6;background:transparent}
    .k2ed-tab:hover{background:#1f2127}
    .k2ed-tab.on{background:#22303a;border-color:#3d6a86;color:#fff}
    .k2ed-tabs .right{margin-left:auto;display:flex;align-items:center;gap:8px}
    .k2ed-lbl{font-size:12px;color:#8b8f98}
    /* 场景页筛选行：一条维度一行，grid 两列（标签列 + 内容列），换行也保持对齐 */
    .k2ed-row{display:grid;grid-template-columns:56px minmax(0,1fr);gap:8px;
      align-items:start;margin-bottom:8px;padding-bottom:8px;
      border-bottom:1px solid #202228}
    .k2ed-row:last-of-type{border-bottom:0}
    .k2ed-row > .k2ed-lbl{text-align:right;font-size:11.5px;color:#7f848e;
      letter-spacing:.5px;padding-top:5px;white-space:nowrap}
    .k2ed-row > .k2ed-chips{margin-bottom:0}
    .k2ed-sublbl{font-size:11px;color:#6f747e;margin-right:1px;align-self:center}
    .k2ed-rnd{border-bottom:0}
    /* 右侧栏「回到顶部」：常驻按钮行下方，滚到底后一键回列表顶 */
    .k2ed-topbtn{margin:0 12px 6px;padding:6px 0;background:#1b1d23;
      border:1px solid #33363e;color:#9aa0aa;border-radius:6px;font-size:12px;
      cursor:pointer;flex:none;transition:background .12s,color .12s,border-color .12s}
    .k2ed-topbtn:hover{background:#262a31;color:#fff;border-color:#4a7fa1}
    .k2ed-q{flex:1 1 260px;min-width:200px;max-width:380px;background:#1e2026;
      border:1px solid #363943;border-radius:8px;color:#dfe3e8;padding:5px 10px;
      font-size:12.5px;outline:none}
    .k2ed-q:focus{border-color:#3d6a86}
    .k2ed-q::placeholder{color:#6d7178}
    .k2ed-seg{display:flex;border:1px solid #363943;border-radius:8px;overflow:hidden}
    .k2ed-seg button{background:#1e2026;border:0;color:#c9ccd3;padding:5px 10px;font-size:12px;cursor:pointer}
    .k2ed-seg button.on{background:#3d6a86;color:#fff}
    .k2ed-seedin{width:92px;background:#1e2026;border:1px solid #363943;border-radius:7px;color:#dfe3e8;
      padding:4px 7px;font-size:12px;font-family:ui-monospace,Consolas,monospace;outline:none}
    .k2ed-seedin:focus{border-color:#3d6a86}
    .k2ed-seedin:disabled{opacity:.4}
    .k2ed-dice{background:#1e2026;border:1px solid #363943;border-radius:7px;color:#c9ccd3;
      padding:3px 8px;font-size:12px;cursor:pointer;line-height:1.4}
    .k2ed-dice:hover{background:#2a2d35;color:#fff}
    .k2ed-dice:disabled{opacity:.4;cursor:default}
    .k2ed-loratog{display:flex;align-items:center;gap:5px;cursor:pointer;
      margin-left:10px;padding:3px 9px;border:1px solid #363943;border-radius:7px;
      background:#1e2026;color:#8b8f98;white-space:nowrap}
    .k2ed-loratog:hover{background:#2a2d35;color:#dfe3e8}
    .k2ed-loratog.on{background:#23384a;border-color:#3d6a86;color:#cfe6f5}
    .k2ed-loratog input{accent-color:#3d6a86;cursor:pointer;margin:0}
    /* 页签行统一行高：页签 / LORA 开关 / 自检按钮 / 画幅分段 / 种子框 / 勾选项
       逐个 padding 对不齐，统一成 28px + inline-flex 居中 */
    .k2ed-tabs{min-height:28px}
    .k2ed-tab,.k2ed-loratog,.k2ed-chkbtn{height:28px;display:inline-flex;align-items:center;
      line-height:1;box-sizing:border-box}
    .k2ed-tab{padding:0 16px}
    .k2ed-tabs .right{height:28px}
    .k2ed-tabs .right > *{height:28px;box-sizing:border-box}
    .k2ed-tabs .k2ed-seg{display:flex;align-items:stretch}
    .k2ed-tabs .k2ed-seg button{padding:0 10px;line-height:1}
    .k2ed-tabs .k2ed-seedin{padding:0 7px}
    .k2ed-tabs .k2ed-dice{padding:0 8px;height:28px;display:inline-flex;
      align-items:center;line-height:1}
    .k2ed-tabs label.k2ed-lbl{display:inline-flex;align-items:center;gap:5px;line-height:1}
    .k2ed-chkbtn{margin-left:6px;padding:0 10px;border:1px solid #363943;border-radius:7px;
      background:#1e2026;color:#8b8f98;font-size:12px;font-family:inherit;cursor:pointer;
      white-space:nowrap}
    .k2ed-chkbtn:hover{background:#2a2d35;color:#dfe3e8}
    .k2ed-dispin{width:100%;box-sizing:border-box;background:#1e2026;border:1px solid #363943;
      border-radius:7px;color:#dfe3e8;padding:5px 8px;font-size:12px;outline:none;margin-top:3px}
    .k2ed-dispin:focus{border-color:#3d6a86}
    .k2ed-bd{flex:1;display:flex;min-height:0}
    .k2ed-page{flex:1;overflow-y:auto;padding:14px 16px}
    .k2ed-side{width:330px;flex:none;border-left:1px solid #2a2c33;display:flex;flex-direction:column;
      gap:9px;padding:12px;overflow:hidden;background:#141519}
    .k2ed-sidebody{flex:1;min-height:0;overflow-y:auto;display:flex;flex-direction:column;
      gap:9px;padding-right:2px}
    .k2ed-blk{background:#1b1d22;border:1px solid #2b2e36;border-radius:10px;padding:9px;flex:none}
    .k2ed-blk .cap{font-size:11px;color:#7f848e;margin-bottom:6px;letter-spacing:.4px}
    .k2ed-pv{display:flex;gap:10px;align-items:center}
    .k2ed-pv img{width:60px;height:60px;border-radius:9px;object-fit:cover;background:#25272e;flex:none}
    .k2ed-pv .nm{font-size:14px}
    .k2ed-pv .wk{font-size:11.5px;color:#7f848e;margin-top:2px}
    .k2ed-simg{width:100%;border-radius:8px;display:block;background:#25272e;aspect-ratio:16/9;
      object-fit:cover}
    .k2ed-ttl{font-size:13px;margin-top:6px;color:#e2e5ea;line-height:1.35}
    .k2ed-en{font-size:11px;color:#7f848e;margin-top:1px;letter-spacing:.5px}
    .k2ed-meta{font-size:11px;color:#7f848e;margin-top:3px}
    .k2ed-desc{font-size:12px;color:#a9aeb8;line-height:1.45;margin-top:3px}
    .k2ed-grid{display:grid;gap:10px;align-content:start}
    .k2ed-grid.ch{grid-template-columns:repeat(auto-fill,minmax(132px,1fr))}
    .k2ed-grid.co{grid-template-columns:repeat(auto-fill,minmax(236px,1fr))}
    .k2ed-grid.mo{grid-template-columns:repeat(auto-fill,minmax(232px,1fr))}
    .k2ed-card{border:1px solid #2d3038;border-radius:10px;overflow:hidden;cursor:pointer;
      background:#1b1d22;transition:border-color .12s}
    .k2ed-card:hover{border-color:#4a4e59}
    .k2ed-card.on{border-color:#3d6a86;box-shadow:0 0 0 1px #3d6a86 inset}
    .k2ed-card .im{width:100%;aspect-ratio:1/1;object-fit:cover;display:block;background:#22242a}
    .k2ed-card .im16{width:100%;aspect-ratio:16/9;object-fit:cover;display:block;background:#22242a}
    .k2ed-card .im34{width:100%;aspect-ratio:3/4;object-fit:cover;display:block;background:#22242a}
    .k2ed-card .im11{width:100%;aspect-ratio:1/1;object-fit:cover;display:block;background:#22242a}
    .k2ed-card .cp{padding:6px 8px 8px}
    .k2ed-card .n{font-size:12.5px;line-height:1.3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    /* 角色卡名字行：名字占满剩余宽度，官方预设套数角标贴右 */
    .k2ed-nline{display:flex;align-items:center;gap:6px}
    .k2ed-nline .n{flex:1;min-width:0}
    .k2ed-oc{flex:none;font-size:10.5px;line-height:14px;padding:0 5px;border-radius:5px;
      background:rgba(61,106,134,.2);border:1px solid rgba(61,106,134,.42);color:#9fd2ff;
      font-variant-numeric:tabular-nums}
    .k2ed-card .w{font-size:11px;color:#7f848e;margin-top:2px;white-space:nowrap;overflow:hidden;
      text-overflow:ellipsis}
    .k2ed-card .ds{font-size:11.5px;color:#9aa0aa;line-height:1.45;margin-top:3px}
    .k2ed-cbar{height:5px}
    .k2ed-tools{display:flex;gap:8px;align-items:center;margin-bottom:12px;flex-wrap:wrap}
    .k2ed-search{flex:1;min-width:180px;padding:8px 11px;background:#1e2026;border:1px solid #33363e;
      border-radius:8px;color:#ddd;font-size:13px;outline:none}
    select.k2ed-sel{background:#1e2026;border:1px solid #33363e;color:#ddd;border-radius:8px;
      padding:7px 9px;font-size:12.5px;outline:none}
    .k2ed-pager{display:flex;gap:8px;align-items:center;justify-content:center;margin:14px 0 4px;
      font-size:12px;color:#8b8f98}
    .k2ed-sect{font-size:12.5px;color:#c9ccd3;margin:16px 0 8px;padding-left:8px;
      border-left:2px solid #3d6a86}
    .k2ed-sect:first-child{margin-top:0}
    .k2ed-chips{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px}
    /* 场景页系列段头：按批次分段平铺，段头点一下 = 只看这一系列 */
    .k2ed-sec{display:flex;align-items:baseline;gap:8px;margin:16px 0 8px;padding:7px 10px;
      border-left:3px solid #4a7fa1;background:#1b1d23;border-radius:4px;cursor:pointer;
      user-select:none}
    .k2ed-sec:hover{background:#23262e}
    .k2ed-sec .t{font-size:13px;font-weight:600;color:#e6e9ef;letter-spacing:.3px}
    .k2ed-sec .c{font-size:11px;color:#8b919c}
    .k2ed-chip{background:#1e2026;border:1px solid #33363e;color:#b9bdc6;border-radius:999px;
      padding:4px 11px;font-size:12px;cursor:pointer}
    .k2ed-chip.on{background:#3d6a86;border-color:#4a7fa1;color:#fff}
    .k2ed-acts{display:flex;flex-wrap:wrap;gap:7px;flex:none}
    .k2ed-btn{background:#262932;border:1px solid #3a3e48;color:#dfe2e8;border-radius:9px;
      padding:7px 11px;font-size:12.5px;cursor:pointer}
    .k2ed-btn:hover{background:#2f333d}
    .k2ed-btn.pri{background:#3d6a86;border-color:#4a7fa1;color:#fff}
    .k2ed-btn.pri:hover{background:#46809f}
    .k2ed-btn:disabled{opacity:.45;cursor:default}
    .k2ed-stat{font-size:11.5px;color:#8b8f98;min-height:16px;line-height:1.4;flex:none;
      max-height:44px;overflow:hidden}
    /* 角色自检不一致：红字提醒，但不拦生成 */
    .k2ed-stat.warn{color:#f07178}
    .k2ed-charwrap{display:flex;gap:14px;height:100%;min-height:0}
    .k2ed-works{width:196px;flex:none;overflow-y:auto;padding-right:6px;border-right:1px solid #2a2c33}
    .k2ed-wk{display:flex;align-items:center;gap:6px;padding:6px 8px;border-radius:8px;cursor:pointer;
      font-size:12.5px;color:#c2c6cd;border:1px solid transparent;line-height:1.3}
    .k2ed-wk:hover{background:#1f2127}
    .k2ed-wk.on{background:#22303a;border-color:#3d6a86;color:#fff}
    .k2ed-wk .c{margin-left:auto;font-size:11px;color:#7f848e;flex:none}
    /* 作品行：[名称 flex] [★] [人数] —— 名称撑开，星标和人数靠右 */
    .k2ed-wk .lb{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .k2ed-wk .c{margin-left:4px}
    .k2ed-wkstar{color:#4d5158;font-size:12px;flex:none;padding:0 3px;cursor:pointer}
    .k2ed-wkstar:hover{color:#e8c96a}
    .k2ed-wkstar.on{color:#e8c96a}
    .k2ed-wk.fav{color:#e8c96a}
    .k2ed-wkhead{font-size:11px;color:#7f848e;padding:2px 8px 6px;letter-spacing:.4px}
    .k2ed-charright{flex:1;min-width:0;display:flex;flex-direction:column;min-height:0}
    .k2ed-charright .scroll{flex:1;overflow-y:auto}
    .k2ed-card{position:relative}
    .k2ed-pick{position:absolute;left:6px;top:6px;width:19px;height:19px;border-radius:5px;
      background:rgba(14,15,19,.74);border:1px solid #4a4e58;color:transparent;
      display:flex;align-items:center;justify-content:center;font-size:12px;line-height:1;
      z-index:2;cursor:pointer;user-select:none}
    .k2ed-pick:hover{border-color:#6d7178;color:#6d7178}
    .k2ed-pick.on{background:#2f6b4f;border-color:#57b98a;color:#eafff5}
    .k2ed-sep{width:1px;height:16px;background:#33353d;margin:0 3px;align-self:center}
    .k2ed-star{position:absolute;top:5px;right:5px;width:22px;height:22px;border-radius:50%;
      background:rgba(10,11,14,.62);color:#9aa0aa;font-size:13px;line-height:22px;text-align:center;
      cursor:pointer;z-index:2;user-select:none}
    .k2ed-star:hover{background:rgba(10,11,14,.85);color:#e8c96a}
    .k2ed-star.on{color:#e8c96a}
    .k2ed-lock{position:absolute;left:5px;top:5px;background:rgba(10,11,14,.66);border-radius:6px;
      padding:1px 6px;font-size:10.5px;color:#e8c96a;z-index:2;max-width:78%;overflow:hidden;
      text-overflow:ellipsis;white-space:nowrap}
    .k2ed-aspbadge{position:absolute;left:5px;top:5px;background:rgba(10,11,14,.68);border-radius:6px;
      padding:1px 6px;font-size:10.5px;line-height:15px;color:#cfd3da;z-index:2;letter-spacing:.5px}
    .k2ed-aspbadge.portrait{color:#9fd2ff}
    .k2ed-aspbadge.both{color:#d8cf8a}
    .k2ed-aspbadge.square{color:#c7a4ef}
    /* 徽标现在是 <button>（点一下改默认画幅）：清掉浏览器默认外观，补上可点手感 */
    .k2ed-aspbadge{cursor:pointer;font-family:inherit;border:0;appearance:none;-webkit-appearance:none;
      transition:background .12s ease,color .12s ease}
    .k2ed-aspbadge:hover{background:rgba(58,64,78,.95);color:#fff}
    .k2ed-aspbadge:active{transform:translateY(1px)}
    .k2ed-aspbadge[data-busy]{opacity:.5;cursor:progress}
    /* 场景卡左上角工具条：勾选框 + 推荐画幅同排流式布局。
       原来两个 absolute 都钉在 left:5/top:5，勾选框正好压住「横屏/竖屏」只露半个字。
       父层收 pointer-events，避免透明空隙挡住卡片本身的点选。 */
    .k2ed-corner{position:absolute;left:5px;top:5px;z-index:3;display:flex;align-items:center;
      gap:5px;max-width:calc(100% - 36px);pointer-events:none}
    .k2ed-corner > *{pointer-events:auto}
    .k2ed-corner .k2ed-pick{position:static;flex:none}
    .k2ed-corner .k2ed-aspbadge{position:static;flex:none;max-width:96px;white-space:nowrap;
      overflow:hidden;text-overflow:ellipsis}
    .k2ed-star-inline{display:inline-block;margin-left:7px;cursor:pointer;color:#8b8f98;font-size:14px;
      vertical-align:middle}
    .k2ed-star-inline:hover{color:#e8c96a}
    .k2ed-star-inline.on{color:#e8c96a}
    .k2ed-txt{border-top:1px solid #2a2c33;padding:10px 14px 12px;display:none}
    .k2ed-ta{width:100%;height:132px;box-sizing:border-box;background:#101116;color:#d7dae1;
      border:1px solid #2d3038;border-radius:9px;padding:9px;font-size:12px;line-height:1.55;
      font-family:ui-monospace,Consolas,monospace;resize:vertical;outline:none}
    /* 免责声明浮层：只在面板内部铺满，不遮整个 ComfyUI 画布 */
    .k2ed-dis-wrap{position:absolute;inset:0;background:rgba(8,9,12,.74);display:none;
      align-items:center;justify-content:center;z-index:30;padding:26px}
    .k2ed-dis-box{width:min(640px,94%);max-height:84%;background:#1b1d22;border:1px solid #3a3d45;
      border-radius:12px;display:flex;flex-direction:column;overflow:hidden;
      box-shadow:0 18px 52px rgba(0,0,0,.6)}
    .k2ed-dis-hd{padding:13px 18px 10px;border-bottom:1px solid #2a2c33;font-size:14px;color:#fff;
      letter-spacing:.4px;display:flex;align-items:baseline;gap:8px}
    .k2ed-dis-hd .tag{font-size:11px;color:#7f848e;letter-spacing:0}
    .k2ed-dis-bd{padding:14px 18px 4px;overflow-y:auto;font-size:12.5px;line-height:1.8;color:#c2c6cd}
    .k2ed-dis-bd p{margin:0 0 9px}
    .k2ed-dis-bd ol{margin:0 0 10px;padding-left:20px}
    .k2ed-dis-bd li{margin-bottom:5px}
    .k2ed-dis-bd b{color:#e8c96a;font-weight:500}
    .k2ed-dis-credit{border-top:1px dashed #34373f;margin-top:2px;padding:12px 0 8px}
    .k2ed-dis-credit .row{display:flex;gap:9px;margin-bottom:6px;font-size:12.5px;line-height:1.7}
    .k2ed-dis-credit .k{flex:none;color:#8b8f98}
    .k2ed-dis-credit .v{color:#e3e5e9}
    .k2ed-dis-credit .v b{color:#e8c96a;font-weight:500}
    .k2ed-dis-ft{padding:10px 18px 14px;display:flex;justify-content:flex-end;gap:8px;
      border-top:1px solid #2a2c33}
    `;
    document.head.appendChild(style);

    const mask = el("div", "");
    mask.className = "k2ed-mask";
    mask.style.display = "none";
    const panel = el("div", "");
    panel.className = "k2ed-panel";
    panel.innerHTML = `
      <div class="k2ed-hd">
        <b>K2 长文出题 · 白垩光</b>
        <span class="sub">角色 / 服装 / 场景 分三页选，选了立刻写回节点（无需再点应用）</span>
        <div class="k2ed-links">
          <a href="https://space.bilibili.com/516891894" target="_blank" rel="noopener noreferrer"
             title="作者 B 站空间 · 插件使用教学视频">▶ 使用教学</a>
          <a href="https://space.bilibili.com/1522948414" target="_blank" rel="noopener noreferrer"
             title="母题创作者 B 站空间 · 图片欣赏">🖼 图片欣赏</a>
          <a href="https://github.com/lingdongbudong/Comfyui-K2-Editorial" target="_blank"
             rel="noopener noreferrer" title="GitHub 仓库 · 源码、更新与问题反馈">🐙 GitHub</a>
        </div>
        <button class="k2ed-dis" id="k2ed-dis" title="使用条款与致谢">ⓘ 免责声明</button>
        <button class="k2ed-x" id="k2ed-close">关闭 ✕</button>
      </div>
      <div class="k2ed-tabs">
        <button class="k2ed-tab" data-tab="char">① 角色</button>
        <button class="k2ed-tab" data-tab="costume">② 服装</button>
        <button class="k2ed-tab" data-tab="motif">③ 场景</button>
        <label class="k2ed-lbl k2ed-loratog" id="k2ed-lorawrap"
               title="开启后不再生成任何服装提示词（单品 / 版型 / 官方预设 / 母题自带服装全部停写），服装交给角色 LORA 的触发词">
          <input type="checkbox" id="k2ed-lora"> LORA 服装触发词模式
        </label>
        <button class="k2ed-chkbtn" id="k2ed-chk"
                title="比对节点角色、图里的角色 LoRA 与触发词是否同一个人；随机池开着也会提醒">🔍 角色自检</button>
        <label class="k2ed-lbl k2ed-loratog" id="k2ed-hairwrap"
               title="开启后发色不参与母题/角色的色彩比例分配，避免被画面色调洗淡、压暗或改色（发色失真的根因是色盘里头发只占 14%）">
          <input type="checkbox" id="k2ed-hairlock"> 🔒 锁定发色
        </label>
        <div class="right">
          <span class="k2ed-lbl">画幅</span>
          <div class="k2ed-seg" id="k2ed-asp"></div>
          <span class="k2ed-lbl">种子</span>
          <div class="k2ed-seg" id="k2ed-seedmode"></div>
          <input class="k2ed-seedin" id="k2ed-seednum" type="text" inputmode="numeric">
          <button class="k2ed-dice" id="k2ed-dice" title="换一个种子">🎲</button>
          <label class="k2ed-lbl" style="display:flex;align-items:center;gap:5px;cursor:pointer">
            <input type="checkbox" id="k2ed-sync" checked> 同步参数节点
          </label>
        </div>
      </div>
      <div class="k2ed-bd">
        <div class="k2ed-page" id="k2ed-page"></div>
        <div class="k2ed-side">
          <div class="k2ed-sidebody">
            <div class="k2ed-blk"><div class="cap">角色</div><div class="k2ed-pv" id="k2ed-pv-char"></div></div>
            <div class="k2ed-blk"><div class="cap">版型</div><div id="k2ed-pv-cos"></div></div>
            <div class="k2ed-blk"><div class="cap">单品</div><div id="k2ed-pv-item"></div></div>
            <div class="k2ed-blk"><div class="cap">场景</div><div id="k2ed-pv-mo"></div></div>
          </div>
          <div class="k2ed-acts">
            <button class="k2ed-btn" id="k2ed-rnd">🎲 随机</button>
            <button class="k2ed-btn" id="k2ed-gen">刷新预览</button>
            <button class="k2ed-btn" id="k2ed-copy">复制</button>
            <button class="k2ed-btn" id="k2ed-tgl">显示提示词</button>
          </div>
          <button class="k2ed-topbtn" id="k2ed-top" title="一键回到列表顶部">↑ 回到顶部</button>
          <div class="k2ed-stat" id="k2ed-stat"></div>
        </div>
      </div>
      <div class="k2ed-txt" id="k2ed-txt">
        <textarea class="k2ed-ta" id="k2ed-ta"></textarea>
      </div>
      <div class="k2ed-dis-wrap" id="k2ed-dis-wrap">
        <div class="k2ed-dis-box">
          <div class="k2ed-dis-hd">免责声明<span class="tag">使用条款 · 素材来源</span></div>
          <div class="k2ed-dis-bd">
            <p>本插件是本地运行的 ComfyUI 自定义节点，只做一件事：把「角色 / 服装 / 场景」
            组装成一条 Krea2 长文提示词。它<b>不联网、不上传任何数据</b>，生成全部发生在你自己的机器上。</p>
            <ol>
              <li>画面与提示词由 AI 模型产出，<b>不含人工审核</b>。是否适合公开、投稿或商用，请自行判断。</li>
              <li>请在遵守所在地法律法规、模型许可协议与平台规则的前提下使用；因使用本插件产生的后果由使用者自行承担。</li>
              <li>内置预设场景的<b>提示词与预览图版权归原作者</b>，随插件提供仅用于学习交流，请勿单独提取商用或二次分发。</li>
              <li>画面中的角色形象版权归各自 IP 方所有，本插件不主张任何角色权利。</li>
              <li>插件按「现状」提供，不附带任何明示或暗示的担保。</li>
            </ol>
            <div class="k2ed-dis-credit">
              <div class="row"><span class="k">插件作者</span><span class="v"><b>灵冻不冻</b></span></div>
              <div class="row"><span class="k">素材致谢</span><span class="v">预设场景提示词与预览图由 <b>辞雪沐春</b> 大佬提供</span></div>
            </div>
          </div>
          <div class="k2ed-dis-ft">
            <button class="k2ed-btn pri" id="k2ed-dis-ok">我知道了</button>
          </div>
        </div>
      </div>`;
    mask.appendChild(panel);
    document.body.appendChild(mask);

    mask.addEventListener("mousedown", (e) => { if (e.target === mask) closePanel(); });
    panel.querySelector("#k2ed-close").onclick = closePanel;

    /* 角色一致性自检：节点角色 vs 图里的角色 LoRA / 触发词 vs 随机池 */
    panel.querySelector("#k2ed-chk").onclick = () => runCharCheck();

    /* LORA 服装触发词模式：开了就一个服装词都不写，服装交给角色 LORA 的触发词 */
    const loraBox = panel.querySelector("#k2ed-lora");
    if (loraBox) {
        loraBox.checked = !!STATE.lora;
        loraBox.onchange = async () => {
            STATE.lora = loraBox.checked;
            panel.querySelector("#k2ed-lorawrap")?.classList.toggle("on", STATE.lora);
            if (CUR) setW(CUR, "LORA服装触发词", STATE.lora);
            app.graph.setDirtyCanvas(true, true);
            PANEL.stat(STATE.lora
                ? "LORA 服装触发词模式：已写回节点，不再生成任何服装提示词（单品 / 版型 / 官方预设 / 母题自带服装全部停写）"
                : "已关闭 LORA 服装模式，恢复正常的服装提示词");
            renderSide();
            if (STATE.showText) await doGenerate();
        };
    }

    /* 锁定发色：发色不参与色盘比例，写回节点（节点上是 optional 末尾的「锁定发色」） */
    const hairBox = panel.querySelector("#k2ed-hairlock");
    if (hairBox) {
        hairBox.checked = !!STATE.hairlock;
        panel.querySelector("#k2ed-hairwrap")?.classList.toggle("on", STATE.hairlock);
        hairBox.onchange = async () => {
            STATE.hairlock = hairBox.checked;
            panel.querySelector("#k2ed-hairwrap")?.classList.toggle("on", STATE.hairlock);
            if (CUR) setW(CUR, "锁定发色", STATE.hairlock);
            app.graph.setDirtyCanvas(true, true);
            PANEL.stat(STATE.hairlock
                ? "锁定发色：已写回节点。发色不再参与色盘比例分配，画面整体色调不许把头发洗淡或改色"
                : "已关闭发色锁定，头发重新跟随画面色彩比例");
            if (STATE.showText) await doGenerate();
        };
    }

    /* 免责声明浮层：点按钮开、点「我知道了」或浮层空白/ESC 关；不影响面板状态 */
    const disWrap = panel.querySelector("#k2ed-dis-wrap");
    const showDis = () => { disWrap.style.display = "flex"; };
    const hideDis = () => { disWrap.style.display = "none"; };
    panel.querySelector("#k2ed-dis").onclick = showDis;
    panel.querySelector("#k2ed-dis-ok").onclick = hideDis;
    disWrap.addEventListener("mousedown", (e) => { if (e.target === disWrap) hideDis(); });

    document.addEventListener("keydown", (e) => {
        if (e.key !== "Escape" || mask.style.display === "none") return;
        // ESC 先关最上层的浮层，再关面板
        if (disWrap.style.display !== "none") { hideDis(); return; }
        closePanel();
    });

    PANEL = { mask, panel, dis: disWrap, built: false,
              stat: (t, kind) => {
                  const s = panel.querySelector("#k2ed-stat");
                  s.textContent = t || "";
                  s.classList.toggle("warn", kind === "warn");
              } };
    return PANEL;
}

/* ---------------- 公共 ---------------- */
function markSelected() {
    pageEl().querySelectorAll(".k2ed-card").forEach((k) => {
        const id = k.dataset.id;
        let on = false;
        if (STATE.tab === "char") on = id === STATE.char;
        else if (STATE.tab === "costume") {
            on = k.dataset.kind === "tpl"
                ? (id === "__auto__" ? STATE.costume === MAN.auto : id === STATE.costume)
                : id === STATE.item;
        } else on = id === STATE.motif;
        k.classList.toggle("on", on);
    });
}

function card(on, onclick) {
    const c = el("div", "");
    c.className = "k2ed-card" + (on ? " on" : "");
    c.onclick = onclick;
    return c;
}

async function fetchChars(reset) {
    if (reset) STATE.offset = 0;
    const q = new URLSearchParams({
        offset: STATE.offset, limit: PAGE_SIZE, q: STATE.q, work: STATE.work,
    });
    const r = await api.fetchApi("/k2ed/chars?" + q.toString());
    const d = await r.json();
    STATE.chars = d.items;
    STATE.total = d.total;
    STATE.works = d.works || [];
    if (d.fav) STATE.favs.characters = d.fav;
    if (!STATE.q && !STATE.work) STATE.allTotal = d.total;
    return d;
}

async function fetchOutfits() {
    const r = await api.fetchApi("/k2ed/outfits?char=" + encodeURIComponent(STATE.char));
    STATE.outfits = await r.json();
    noteItems(STATE.outfits);          // 单品中文名进名字表，摘要用
    return STATE.outfits;
}

/* 选中项未必在当前分页里，缺了就按 id 单独取一次 */
async function charMeta() {
    if (STATE.charMeta && STATE.charMeta.id === STATE.char) return STATE.charMeta;
    const hit = STATE.chars.find((x) => x.id === STATE.char);
    if (hit) { STATE.charMeta = hit; noteChar(hit); return hit; }
    try {
        const r = await api.fetchApi("/k2ed/char?id=" + encodeURIComponent(STATE.char));
        if (r.ok) { STATE.charMeta = await r.json(); noteChar(STATE.charMeta); return STATE.charMeta; }
    } catch (e) { /* 忽略 */ }
    STATE.charMeta = { id: STATE.char, zh: STATE.char, work: "", thumb: "", accent: "aqua" };
    return STATE.charMeta;
}

/* ---------------- ① 角色页（左：常驻作品栏 / 右：网格） ---------------- */
/* ⚠️ 骨架只建一次，之后左右各自局部刷新。
   早期版本每次点作品都 page.innerHTML="" 整页重建 → 左栏 scrollTop 归零，
   表现就是「选了下面的作品，列表弹回顶部」。与 Anima v6.7.1 / v6.9.4 同一个坑。 */
let CHARUI = null;

function buildCharShell(page) {
    page.innerHTML = "";
    const wrap = el("div", "");
    wrap.className = "k2ed-charwrap";

    const works = el("div", "");
    works.className = "k2ed-works";
    wrap.appendChild(works);

    const right = el("div", "");
    right.className = "k2ed-charright";

    const tools = el("div", "k2ed-tools");
    const search = el("input", "");
    search.className = "k2ed-search";
    search.placeholder = "搜索角色 / 作品…（全量 2400+）";
    search.value = STATE.q;
    let timer = null;
    search.oninput = () => {
        STATE.q = search.value;
        clearTimeout(timer);
        timer = setTimeout(async () => {
            await fetchChars(true);
            renderWorkList();
            renderCharGrid();
        }, 260);
    };
    tools.appendChild(search);
    const count = el("span", "k2ed-lbl", "");
    tools.appendChild(count);

    // 角色库来源：实时（跟着 Anima 更新）/ 内置（分发包自带）
    const st = MAN.anima_status || {};
    const srcLbl = el("span", "k2ed-lbl", "");
    if (st.source === "live") {
        srcLbl.textContent = "角色库：实时";
        srcLbl.title = `读自 Comfyui-Anima-Wardrobe-V6（${st.chars} 个角色）`;
    } else if (st.source === "bundle") {
        srcLbl.textContent = `角色库：内置 ${st.thumbs} 张图`;
        srcLbl.title = `本插件自带副本，${st.built_at || ""} 打包（${st.chars} 个角色）`;
    } else {
        srcLbl.textContent = "角色库：缺失";
        srcLbl.title = "既没找到 Anima 插件，也没有内置副本";
    }
    tools.appendChild(srcLbl);
    right.appendChild(tools);

    /* 随机抽取行：内容由 renderCharRand() 填（切模式要能就地刷新） */
    const rand = el("div", "k2ed-chips");
    rand.style.margin = "2px 0 0";
    right.appendChild(rand);

    const scroll = el("div", "");
    scroll.className = "scroll";
    right.appendChild(scroll);

    wrap.appendChild(right);
    page.appendChild(wrap);
    return { wrap, works, right, scroll, count, rand };
}

async function renderCharPage() {
    const page = pageEl();
    page.style.overflow = "hidden";
    if (!CHARUI || !page.contains(CHARUI.wrap)) CHARUI = buildCharShell(page);
    renderWorkList();
    renderCharGrid();
    renderCharRand();
}

/* 角色随机抽取行（收藏角色 / 指定作品）。单独渲染：切模式后 chip 与池大小要跟着变 */
function renderCharRand() {
    const box = CHARUI.rand;
    if (!box) return;
    box.innerHTML = "";
    box.appendChild(el("span", "k2ed-lbl", "🎲 每次运行随机角色"));

    const hint = el("span", "k2ed-lbl", "");
    const setHint = () => {
        if (STATE.charPool === "关闭") { hint.textContent = "池：不随机"; return; }
        if (STATE.charPool === "收藏角色") {
            const n = (STATE.favs.characters || []).length;
            hint.textContent = n ? `池：${n} 人` : "池：⚠ 空 → 回退全库";
            return;
        }
        const w = STATE.works.find((x) => x.en === STATE.charPoolWork);
        hint.textContent = w
            ? `池：${w.zh || w.en}（${w.count} 人）`
            : "池：⚠ 未选作品（点左栏作品设定）→ 回退全库";
    };

    [["关闭", "关闭", "不做随机，用面板当前角色"],
     ["收藏角色", "★ 收藏角色", "在 ★ 收藏的角色里随机"],
     ["指定作品", "作品内", "在左栏选中的作品里随机；点左栏作品即设定池子"]]
        .forEach(([k, label, tip]) => {
            const b = el("button", "", label);
            b.className = "k2ed-chip" + (STATE.charPool === k ? " on" : "");
            b.title = tip;
            b.onclick = () => {
                STATE.charPool = STATE.charPool === k ? "关闭" : k;
                if (STATE.charPool === "指定作品" && !STATE.charPoolWork
                    && STATE.work && STATE.work !== "__fav__") {
                    STATE.charPoolWork = STATE.work;   // 当前筛选的作品顺手当池子
                }
                applySelect(`角色随机池 ${STATE.charPool}`);
                renderCharPage();
            };
            box.appendChild(b);
        });
    setHint();
    box.appendChild(hint);
}

/* 左栏：作品列表（收藏置顶）。重建时保留 scrollTop —— 这是这个 bug 的根修。 */
function renderWorkList() {
    const box = CHARUI.works;
    const keep = box.scrollTop;
    box.innerHTML = "";

    const favRow = el("div", "");
    favRow.className = "k2ed-wk fav" + (STATE.work === "__fav__" ? " on" : "");
    favRow.appendChild(el("span", "lb", "★ 收藏"));
    favRow.appendChild(el("span", "c", String(STATE.favs.characters.length)));
    favRow.title = "只看收藏的角色";
    favRow.onclick = () => selectWork("__fav__");
    box.appendChild(favRow);

    box.appendChild(el("div", "k2ed-wkhead", `全部作品 ${STATE.works.length}`));

    const favWorks = STATE.favs.works || [];
    const rows = STATE.works.slice().sort((a, b) => {
        const fa = favWorks.indexOf(a.en);
        const fb = favWorks.indexOf(b.en);
        if (fa >= 0 && fb >= 0) return fa - fb;      // 都在收藏：按收藏先后
        if (fa >= 0) return -1;                       // 收藏的排前面
        if (fb >= 0) return 1;
        return b.count - a.count;                     // 其余按人数降序
    });

    const mk = (key, label, count, isFav) => {
        const r = el("div", "");
        r.className = "k2ed-wk" + (STATE.work === key ? " on" : "");
        r.appendChild(el("span", "lb", label));
        if (key) {
            const st = el("span", "", "★");
            st.className = "k2ed-wkstar" + (isFav ? " on" : "");
            st.title = "收藏该作品（收藏的排在前面）";
            st.onclick = async (ev) => {
                ev.stopPropagation();
                const on = !st.classList.contains("on");
                st.classList.toggle("on", on);
                await toggleFav("works", key, on);
                renderWorkList();          // 重新排序，内部保留滚动位置
            };
            r.appendChild(st);
        }
        r.appendChild(el("span", "c", String(count)));
        r.title = label;
        r.onclick = () => selectWork(key);
        box.appendChild(r);
    };

    mk("", "全部", STATE.allTotal || STATE.total, false);
    rows.forEach((w) => mk(w.en, w.zh || w.en, w.count, favWorks.includes(w.en)));

    box.scrollTop = keep;
    // 赋值可能被尚未完成的布局夹到 0，下一帧再压一次
    requestAnimationFrame(() => { if (box.isConnected) box.scrollTop = keep; });
}

function selectWork(key) {
    STATE.work = (key === "__fav__" && STATE.work === "__fav__") ? "" : key;
    // 「指定作品」模式下，点左栏作品即设定随机池（其余模式不动，避免误改）
    if (STATE.charPool === "指定作品" && key && key !== "__fav__") {
        STATE.charPoolWork = key;
        if (CUR) setW(CUR, "角色随机作品", key);
        const w = STATE.works.find((x) => x.en === key);
        PANEL?.stat(`🎲 随机作品池 → ${w ? (w.zh || w.en) : key}`);
    }
    charGridReload();
}

async function charGridReload() {
    await fetchChars(true);
    renderWorkList();
    renderCharGrid();
    renderCharRand();     // 作品池人数要跟着刷新
}

/* 右栏：角色网格 + 分页（这一块重建是安全的，滚动位置自己恢复） */
function renderCharGrid() {
    const box = CHARUI.scroll;
    const keep = box.scrollTop;
    box.innerHTML = "";

    const curWork = STATE.work === "__fav__"
        ? "★ 收藏"
        : (STATE.works.find((w) => w.en === STATE.work)?.zh || "全部作品");
    CHARUI.count.textContent = `${curWork}　共 ${STATE.total} 个`;

    const grid = el("div", "");
    grid.className = "k2ed-grid ch";
    STATE.chars.forEach((c) => {
        noteChar(c);                       // 当前页的角色名进名字表（摘要显示中文）
        const k = card(c.id === STATE.char, async () => {
            STATE.char = c.id;
            STATE.charMeta = c;
            STATE.outfits = null;
            if (!(MAN.costume_templates || []).some((t) => t.id === STATE.costume)
                && STATE.costume !== MAN.keep) STATE.costume = MAN.auto;
            // 该角色锁定了官方服装 → 自动带出
            STATE.item = STATE.locks[c.id] ? "char:" + STATE.locks[c.id] : "";
            markSelected();
            applySelect("角色 " + (c.zh || c.id));
            await renderSide();
        });
        k.dataset.id = c.id;
        k.dataset.kind = "char";
        if (c.thumb) {
            const im = el("img", "");
            im.className = "im";
            im.loading = "lazy";
            im.src = thumbURL(c.thumb, c.thumb_v);
            k.appendChild(im);
        } else k.appendChild(el("div", "aspect-ratio:1/1;background:#25272e"));

        const star = favStar("characters", c.id, false);
        star.onclick = async (ev) => {
            ev.stopPropagation();
            const wasOn = star.classList.contains("on");
            const on = !wasOn;
            star.classList.toggle("on", on);
            await toggleFav("characters", c.id, on);
            const n = CHARUI.works.querySelector(".k2ed-wk.fav .c");
            if (n) n.textContent = String(STATE.favs.characters.length);
            // 在收藏视图里取消收藏 → 就地隐藏，不重建网格
            if (STATE.work === "__fav__" && wasOn) k.style.display = "none";
        };
        k.appendChild(star);
        if (STATE.locks[c.id]) {
            const b = el("div", "", "👗");
            b.className = "k2ed-lock";
            b.title = "已锁定官方预设服装";
            k.appendChild(b);
        }

        const cp = el("div", "cp");
        const nl = el("div", "k2ed-nline");
        nl.appendChild(el("div", "n", c.zh || c.id));
        if (c.n_outfits) {
            // 官方预设套数（character_outfits.json 里该角色的 list 条数）
            const oc = el("span", "k2ed-oc", String(c.n_outfits));
            oc.title = `官方预设服装 ${c.n_outfits} 套`;
            nl.appendChild(oc);
        }
        cp.appendChild(nl);
        cp.appendChild(el("div", "w", c.work_zh || c.work || ""));
        k.appendChild(cp);
        grid.appendChild(k);
    });
    box.appendChild(grid);

    const pages = Math.max(1, Math.ceil(STATE.total / PAGE_SIZE));
    const curPage = Math.floor(STATE.offset / PAGE_SIZE) + 1;
    const pager = el("div", "k2ed-pager");
    const prev = el("button", "k2ed-btn", "上一页");
    const next = el("button", "k2ed-btn", "下一页");
    prev.disabled = curPage <= 1;
    next.disabled = curPage >= pages;
    prev.onclick = async () => {
        STATE.offset = Math.max(0, STATE.offset - PAGE_SIZE);
        await fetchChars(false);
        renderCharGrid();
    };
    next.onclick = async () => {
        STATE.offset = Math.min((pages - 1) * PAGE_SIZE, STATE.offset + PAGE_SIZE);
        await fetchChars(false);
        renderCharGrid();
    };
    pager.appendChild(prev);
    pager.appendChild(el("span", "", `第 ${curPage} / ${pages} 页`));
    pager.appendChild(next);
    box.appendChild(pager);

    box.scrollTop = keep;
    // 赋值可能被尚未完成的布局夹到 0，下一帧再压一次
    requestAnimationFrame(() => { if (box.isConnected) box.scrollTop = keep; });
}

async function fetchLocks() {
    try {
        const r = await api.fetchApi("/k2ed/charoutfit");
        if (!r.ok) return;
        const d = await r.json();
        STATE.locks = d.locks || {};
    } catch (e) { /* 锁定表读不到不该挡住面板 */ }
}

async function saveLock(char, oid) {
    try {
        const r = await api.fetchApi("/k2ed/charoutfit", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ char, id: oid }),
        });
        if (r.ok) {
            const d = await r.json();
            STATE.locks = d.locks || {};
        }
    } catch (e) { PANEL.stat("保存官方服装失败：" + e); }
}

async function fetchFavs() {
    try {
        const r = await api.fetchApi("/k2ed/favs");
        if (!r.ok) return;
        const d = await r.json();
        STATE.favs = {
            characters: d.characters || [],
            costumes: d.costumes || [],
            motifs: d.motifs || [],
            works: d.works || [],
        };
    } catch (e) { /* 收藏读不到不该挡住面板 */ }
}

async function toggleFav(kind, id, on) {
    try {
        const r = await api.fetchApi("/k2ed/favs", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ kind, id, on }),
        });
        if (r.ok) {
            const d = await r.json();
            STATE.favs = {
                characters: d.characters || [],
                costumes: d.costumes || [],
                motifs: d.motifs || [],
                works: d.works || [],
            };
        }
    } catch (e) {
        PANEL.stat("收藏失败：" + e);
    }
}

function favStar(kind, id, inline) {
    const list = STATE.favs[kind] || [];
    const s = el("span", "", "★");
    s.className = (inline ? "k2ed-star-inline" : "k2ed-star") + (list.includes(id) ? " on" : "");
    s.title = "收藏 / 取消收藏";
    s.onclick = async (ev) => {
        ev.stopPropagation();
        const on = !s.classList.contains("on");
        s.classList.toggle("on", on);
        await toggleFav(kind, id, on);
        if (!on) s.classList.remove("on"); else s.classList.add("on");
    };
    return s;
}

/* ---------------- ② 服装页 ---------------- */
async function renderCostumePage() {
    const page = pageEl();
    page.style.overflow = "";
    page.innerHTML = "";
    if (!STATE.outfits) {
        page.appendChild(el("div", "k2ed-desc", "读取服装数据…"));
        await fetchOutfits();
        page.innerHTML = "";
    }
    const c = await charMeta();
    const hex = ACCENT_HEX[c.accent] || "#5DCAA5";

    // 收藏筛选（服装页）
    const favs = STATE.favs.costumes || [];
    const topChips = el("div", "k2ed-chips");
    const fb = el("button", "", `★ 只看收藏（${favs.length}）`);
    fb.className = "k2ed-chip" + (STATE.favOnlyCostume ? " on" : "");
    fb.onclick = () => { STATE.favOnlyCostume = !STATE.favOnlyCostume; renderCostumePage(); };
    topChips.appendChild(fb);
    page.appendChild(topChips);
    const pass = (id) => !STATE.favOnlyCostume || favs.includes(id);

    // —— 版型 ——
    page.appendChild(el("div", "k2ed-sect", "版型 · 决定剪裁与材质统一（8 套，任意角色可用）"));
    const g1 = el("div", "");
    g1.className = "k2ed-grid co";
    if (!STATE.favOnlyCostume) {
        const auto = card(STATE.costume === MAN.auto, () => {
            STATE.costume = MAN.auto; markSelected(); applySelect("版型 自动"); renderSide();
        });
        auto.dataset.id = "__auto__";
        auto.dataset.kind = "tpl";
        auto.appendChild(el("div", "k2ed-cbar", "")).style.background =
            "linear-gradient(90deg," + hex + ",#3d6a86)";
        const ap = el("div", "cp");
        ap.appendChild(el("div", "n", "自动（跟随母题）"));
        ap.appendChild(el("div", "ds", "按角色推荐顺序随机挑一套。"));
        auto.appendChild(ap);
        g1.appendChild(auto);
    }

    (MAN.costume_templates || []).forEach((t, i) => {
        const fid = "tpl:" + t.id;
        if (!pass(fid)) return;
        const k = card(STATE.costume === t.id, () => {
            STATE.costume = t.id; markSelected(); applySelect("版型 " + t.zh); renderSide();
        });
        k.dataset.id = t.id;
        k.dataset.kind = "tpl";
        const bar = el("div", "k2ed-cbar", "");
        bar.style.background = i % 2 ? hex : "#3d6a86";
        k.appendChild(bar);
        k.appendChild(favStar("costumes", fid, false));
        const cp = el("div", "cp");
        cp.appendChild(el("div", "n", `${i + 1}. ${t.zh}`));
        cp.appendChild(el("div", "ds", t.desc || ""));
        k.appendChild(cp);
        g1.appendChild(k);
    });
    page.appendChild(g1);

    // —— 角色专属预设 ——
    const chOutfits = STATE.outfits.character || [];
    page.appendChild(el("div", "k2ed-sect",
        `角色专属 · ${c.zh || STATE.char} 的原作服装（${chOutfits.length} 套，来自 Anima）`));
    const g2 = el("div", "");
    g2.className = "k2ed-grid co";
    let n2 = 0;
    chOutfits.forEach((o) => {
        const id = "char:" + o.id;
        const fid = `pout:${STATE.char}:${o.id}`;
        if (!pass(fid)) return;
        n2++;
        const k = card(STATE.item === id, () => {
            STATE.item = STATE.item === id ? "" : id;
            markSelected();
            applySelect(STATE.item ? "原作服装 " + (o.zh || o.id) : "取消原作服装");
            renderSide();
        });
        k.dataset.id = id;
        k.dataset.kind = "item";
        const bar = el("div", "k2ed-cbar", "");
        bar.style.background = "#8a6d3b";
        k.appendChild(bar);
        k.appendChild(favStar("costumes", fid, false));
        const cp = el("div", "cp");
        cp.appendChild(el("div", "n", o.zh || o.id));
        k.appendChild(cp);
        k.title = (o.tags || []).join(" · ");
        g2.appendChild(k);
    });
    if (n2) page.appendChild(g2);
    else if (!chOutfits.length) {
        page.appendChild(el("div", "k2ed-desc", "该角色没有专属服装预设，用下面的服装库单品。"));
    } else {
        page.appendChild(el("div", "k2ed-desc", "该角色没有收藏的专属服装。"));
    }

    // —— 服装库单品 ——
    page.appendChild(el("div", "k2ed-sect",
        `服装库 · ${(STATE.outfits.library || []).length} 套单品（来自 Anima 服装库）`));
    const chips = el("div", "k2ed-chips");
    const mkChip = (id, label) => {
        const b = el("button", "", label);
        b.className = "k2ed-chip" + (STATE.outfitCat === id ? " on" : "");
        b.onclick = () => { STATE.outfitCat = id; renderCostumePage(); };
        chips.appendChild(b);
    };
    mkChip("", "全部");
    (STATE.outfits.categories || []).forEach((cat) => mkChip(cat.id, cat.zh));
    page.appendChild(chips);

    const g3 = el("div", "");
    g3.className = "k2ed-grid co";
    (STATE.outfits.library || [])
        .filter((o) => !STATE.outfitCat || o.cat === STATE.outfitCat)
        .forEach((o) => {
            const id = "lib:" + o.id;
            const fid = "lib:" + o.id;
            if (!pass(fid)) return;
            const k = card(STATE.item === id, () => {
                STATE.item = STATE.item === id ? "" : id;
                markSelected();
                applySelect(STATE.item ? "单品 " + (o.zh || o.id) : "取消单品");
                renderSide();
            });
            k.dataset.id = id;
            k.dataset.kind = "item";
            const bar = el("div", "k2ed-cbar", "");
            bar.style.background = "#3d6a86";
            k.appendChild(bar);
            k.appendChild(favStar("costumes", fid, false));
            const cp = el("div", "cp");
            cp.appendChild(el("div", "n", o.zh || o.id));
            k.appendChild(cp);
            k.title = (o.tags || []).join(" · ");
            g3.appendChild(k);
        });
    page.appendChild(g3);
}

/* ---------------- 场景默认画幅（卡片徽标） ----------------
   徽标点一下改「这条母题的默认画幅」，三态循环：竖 → 横 → 方 → 竖。
   「通用（both）」不在三态里，点一下先落竖屏，之后照常走循环。
   改完同时把当前工作流画幅切过去（竖 3:4 / 横 16:9 / 方 1:1），
   与 Anima-Wardrobe 那边的徽标行为保持一致。 */
const MOTIF_ASP_CYCLE = ["portrait", "landscape", "square"];
const MOTIF_ASP_ZH = { portrait: "竖屏", landscape: "横屏", both: "通用", square: "方屏" };
const MOTIF_ASP_FRAME = { portrait: "3:4", landscape: "16:9", square: "1:1" };

function nextMotifAspect(cur) {
    if (cur === "both") return "portrait";      // 通用 → 竖屏，然后进循环
    const i = MOTIF_ASP_CYCLE.indexOf(cur);
    /* indexOf 为 -1（脏数据）时 (i+1)%3 = 0 → portrait，也算合理回落 */
    return MOTIF_ASP_CYCLE[(i + 1) % MOTIF_ASP_CYCLE.length];
}

async function postMotifAspect(id, aspect) {
    const r = await api.fetchApi("/k2ed/motif/aspect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, aspect }),
    });
    if (!r.ok) throw new Error("HTTP " + r.status);
    return await r.json();
}

/* 点徽标：改默认画幅 → 跟着切当前画幅。
   ⚠️ 必须 stopPropagation：卡片本身的 onclick 是「选中这个场景」。 */
async function cycleMotifAspect(ev, m, badge) {
    ev.stopPropagation();
    ev.preventDefault();
    if (badge.dataset.busy) return;             // 连点保护，避免写入交错
    badge.dataset.busy = "1";
    try {
        const nxt = nextMotifAspect(m.aspect || "landscape");
        const d = await postMotifAspect(m.id, nxt);
        const eff = d.aspect || nxt;            // 服务端回的是生效值
        m.aspect = eff;                         // 前端内存同步：筛选 / 角标 / 右侧预览都读它
        badge.textContent = MOTIF_ASP_ZH[eff] || eff;
        badge.className = "k2ed-aspbadge " + eff;
        badge.title = `默认画幅：${MOTIF_ASP_ZH[eff] || eff}`
            + (m.ratio ? `（${m.ratio}）` : "") + "\n点击切换：竖 → 横 → 方";

        /* 只动画幅相关的东西：不碰「覆盖提示词」，也不重写角色/场景选择 */
        const want = MOTIF_ASP_FRAME[eff];
        let tail = "";
        if (want && STATE.aspect !== want) {
            STATE.aspect = want;
            renderAspects();
            if (CUR) setW(CUR, "画幅", want);
            const syncEl = PANEL.panel.querySelector("#k2ed-sync");
            if (syncEl && syncEl.checked && want !== STATE._syncedAspect) {
                tail = "　|　" + syncAspect(want);
                STATE._syncedAspect = want;
            }
            app.graph.setDirtyCanvas(true, true);
        }
        PANEL.stat(`${m.zh || m.title || m.id}　默认画幅 → ${MOTIF_ASP_ZH[eff] || eff}`
            + (want ? `，当前画幅 ${want}` : "") + tail);
        if (STATE.motif === m.id) renderSide();   // 右侧「推荐画幅」那行要跟着改
    } catch (e) {
        PANEL.stat("⚠ 默认画幅保存失败：" + e);
    } finally {
        delete badge.dataset.busy;
    }
}

/* ---------------- ③ 场景页 ---------------- */
function renderMotifPage() {
    bindMotifScrollMemory();
    motifPaintBegin();
    try {
    const page = pageEl();
    page.style.overflow = "";
    page.innerHTML = "";
    /* 勾选池存在服务端：首次进页先拉一次，拉回来再刷一遍（避免先渲染成 0 条） */
    if (!_poolsLoaded) loadPicks().then(() => { if (STATE.tab === "motif") renderMotifPage(); });

    const favs = STATE.favs.motifs || [];
    const ASP_ZH = { landscape: "横屏", portrait: "竖屏",
                     both: "通用", square: "方屏" };

    /* 每行一条筛选维度：grid 两列（标签列 + 内容列），chip 换行后仍与标签列对齐。
       返回的是 chip 容器，调用方往里塞 chip 即可。 */
    const mkRow = (label) => {
        const r = el("div", "k2ed-row");
        r.appendChild(el("span", "k2ed-lbl", label));
        const box = el("div", "k2ed-chips");
        r.appendChild(box);
        page.appendChild(r);
        return box;
    };
    /* key/val 用来就地刷新选中态（repaintFilters）；动作按钮不传 */
    const mkChip = (on, label, fn, host, key, val) => {
        const b = el("button", "", label);
        b.className = "k2ed-chip" + (on ? " on" : "");
        if (key) { b.dataset.k = key; b.dataset.v = val === undefined ? "" : val; }
        /* 不让按钮拿焦点：点完网格重排时，浏览器会为「保持焦点元素可见」自动滚动页面，
           表现就是点一下分类、列表自己滑走。preventDefault 不影响 click。 */
        b.onmousedown = (ev) => ev.preventDefault();
        b.onclick = fn;
        (host || page).appendChild(b);
        return b;
    };
    /* 单选 / 多选统一入口：多选开关关着时，点新的一项先清同维度其余项 */
    const pick = (setKey, set, val) => {
        if (set.has(val)) { set.delete(val); return; }
        if (!STATE.motifMulti) set.clear();
        set.add(val);
        STATE.motifLast[setKey] = val;
    };
    /* 筛选就地重绘：只重建网格，不整页 renderMotifPage()。
       整页重建要重做 395 张卡 + 搜索框，约 60ms，还会丢输入框焦点。 */
    const repaintFilters = () => {
        /* 点击这一刻的位置：paintGrid 内部还会再记一次，但若点击本身已经让浏览器
           滚过一截（焦点/重排），这里记的才是「用户看到的原位」，最后用它兜底。 */
        const keep = page.scrollTop;
        page.querySelectorAll(".k2ed-chip[data-k]").forEach((b) => {
            const k = b.dataset.k, v = b.dataset.v;
            const on = k === "fav" ? STATE.favOnlyMotif
                : k === "added" ? STATE.addedOnly
                : k === "multi" ? STATE.motifMulti
                : k === "view" ? STATE.motifView === v
                    : k === "ref" ? STATE.motifRef === v
                        : k === "branch" ? STATE.motifBranch === v
                        : k === "aspect" ? STATE.motifAspect === v
                            : k === "tag" ? STATE.motifTags.has(v)
                                : k === "genre" ? STATE.motifGenres.has(v)
                                    : k === "series" ? STATE.motifSeries.has(v)
                                        : k === "shot" ? STATE.motifShots.has(v)
                                            : false;
            b.classList.toggle("on", on);
        });
        paintGrid();
        /* 兜底：内容变短时按新的底部夹紧，否则回到点击前的位置，绝不主动往下走 */
        const max = Math.max(0, page.scrollHeight - page.clientHeight);
        const want = Math.min(keep, max);
        if (Math.abs(page.scrollTop - want) > 2) page.scrollTop = want;
        /* 自检：还有偏移就在状态栏报数值，方便判断是「内容变短被夹」还是「真跳了」 */
        if (Math.abs(keep - page.scrollTop) > 4) {
            PANEL?.stat(`滚动自检：${Math.round(keep)} → ${Math.round(page.scrollTop)}`
                + `（内容高 ${Math.round(page.scrollHeight)}，可视 ${Math.round(page.clientHeight)}）`);
        }
    };

    /* 行 1：视图 / 收藏 / 分类 */
    const rowView = mkRow("视图");
    [["group", "按系列分组"], ["grid", "全部平铺"]]
        .forEach(([k, label]) => mkChip(STATE.motifView === k, label, () => {
            STATE.motifView = k; repaintFilters();
        }, rowView, "view", k));
    rowView.appendChild(el("span", "k2ed-sep"));
    mkChip(STATE.favOnlyMotif, `★ 收藏（${favs.length}）`, () => {
        STATE.favOnlyMotif = !STATE.favOnlyMotif; repaintFilters();
    }, rowView, "fav");
    /* 只看新增：manifest 里 added 有值的母题（按入库批次标记） */
    const addedN = MAN.added_count || MAN.motifs.filter((m) => m.added).length;
    if (addedN) {
        mkChip(STATE.addedOnly, `✦ 新增（${addedN}）`, () => {
            STATE.addedOnly = !STATE.addedOnly; repaintFilters();
        }, rowView, "added");
    }
    rowView.appendChild(el("span", "k2ed-sep"));
    rowView.appendChild(el("span", "k2ed-sublbl", "分类"));
    [["", "全部"], ["scene", "3D 场景"], ["poster", "平面海报"],
     ["short", "短提示词"]]
        .forEach(([k, label]) => mkChip(STATE.motifBranch === k, label, () => {
            STATE.motifBranch = k; repaintFilters();
        }, rowView, "branch", k));

    /* 视图行末：人物参考图模式（白底单人 / 白底四视图），点一下只看那一类，再点取消 */
    const refN = MAN.motifs.filter((m) => m.ref).length;
    if (refN) {
        rowView.appendChild(el("span", "k2ed-sep"));
        [["front", "参考图·正面全身"], ["sheet", "参考图·四视图"]].forEach(([k, label]) => {
            mkChip(STATE.motifRef === k, label, () => {
                STATE.motifRef = STATE.motifRef === k ? "" : k;
                repaintFilters();
            }, rowView, "ref", k);
        });
    }

    /* 行 2：推荐画幅 / 多选开关 / 清除 / 搜索 */
    const rowAsp = mkRow("画幅");
    [["", "全部"], ["landscape", "横屏"], ["portrait", "竖屏"],
     ["both", "通用"], ["square", "方屏"]]
        .forEach(([k, label]) => mkChip(STATE.motifAspect === k, label, () => {
            STATE.motifAspect = k; repaintFilters();
        }, rowAsp, "aspect", k));
    rowAsp.appendChild(el("span", "k2ed-sep"));
    mkChip(STATE.motifMulti, STATE.motifMulti ? "☑ 多选分类" : "☐ 多选分类", () => {
        STATE.motifMulti = !STATE.motifMulti;
        /* 关掉多选时每个维度只留最后点的那一个，行为可预测 */
        if (!STATE.motifMulti) {
            [["tags", STATE.motifTags], ["genres", STATE.motifGenres],
             ["series", STATE.motifSeries], ["shots", STATE.motifShots]].forEach(([k, set]) => {
                if (set.size > 1) {
                    const keep = STATE.motifLast[k];
                    set.clear();
                    if (keep) set.add(keep);
                }
            });
        }
        renderMotifPage();
        PANEL?.stat(STATE.motifMulti ? "分类多选：开（可同时选多个）" : "分类多选：关（单选）");
    }, rowAsp, "multi", "1");
    if (STATE.motifQ || STATE.motifTags.size || STATE.motifGenres.size
            || STATE.motifSeries.size || STATE.motifShots.size
            || STATE.motifRef || STATE.addedOnly) {
        mkChip(false, "✕ 清除筛选", () => {
            STATE.motifQ = "";
            STATE.motifTags.clear(); STATE.motifGenres.clear();
            STATE.motifSeries.clear(); STATE.motifShots.clear();
            STATE.motifRef = "";
            STATE.addedOnly = false;
            renderMotifPage();
            PANEL?.stat("筛选已清除");
        }, rowAsp);
    }
    const inp = el("input", "");
    inp.className = "k2ed-q";
    inp.type = "search";
    inp.placeholder = "搜索：场景名 / 英文标题 / 母题 id";
    inp.value = STATE.motifQ;
    rowAsp.appendChild(inp);

    /* 行 2.5：景别（人像 = 脸到胸以上 / 半身 = 腰膝以上 / 全景 = 全身及更小） */
    const SHOT_ORDER = ["人像", "半身", "全景"];
    const shotCount = {};
    MAN.motifs.forEach((m) => {
        if (m.shot) shotCount[m.shot] = (shotCount[m.shot] || 0) + 1;
    });
    if (Object.keys(shotCount).length) {
        const shotRow = mkRow("景别");
        SHOT_ORDER.forEach((s) => {
            if (!shotCount[s]) return;
            mkChip(STATE.motifShots.has(s), `${s} ${shotCount[s]}`, () => {
                pick("shots", STATE.motifShots, s);
                repaintFilters();
            }, shotRow, "shot", s);
        });
    }

    /* 行 3：风格系列（10 个批次，风格一致性最高，浏览母题最顺手的维度） */
    const seriesRow = mkRow("系列");
    (MAN.series || []).forEach((s) => {
        mkChip(STATE.motifSeries.has(s.key), `${s.zh} ${s.count}`, () => {
            pick("series", STATE.motifSeries, s.key);
            repaintFilters();
        }, seriesRow, "series", s.key);
    });

    /* 行 4：题材第二维度（「其他」= 正文线索不足，诚实留白不硬猜） */
    if ((MAN.genres || []).length) {
        const genresRow = mkRow("题材");
        MAN.genres.forEach((g) => {
            mkChip(STATE.motifGenres.has(g.key), `${g.zh} ${g.count}`, () => {
                pick("genres", STATE.motifGenres, g.key);
                repaintFilters();
            }, genresRow, "genre", g.key);
        });
    }
    /* 行 5：场景标签（多数由 build_manifest 按正文关键词生成；「坐姿」是 motif_tags.json 手工标注，
       姿势没法从关键词可靠判定 —— 站姿母题里也常出现 seated 的否定句） */
    const tagsRow = mkRow("标签");
    (MAN.tags || []).forEach((t) => {
        mkChip(STATE.motifTags.has(t.key), `${t.zh} ${t.count}`, () => {
            pick("tags", STATE.motifTags, t.key);
            repaintFilters();
        }, tagsRow, "tag", t.key);
    });

    /* 行 6：随机抽取 + 勾选（全选/反选的作用域 = 当前筛选结果） */
    const rnd = mkRow("🎲 随机池");
    rnd.parentElement.classList.add("k2ed-rnd");

    let pickChip = null;
    const poolHint = el("span", "k2ed-lbl", "");
    const syncLabels = () => {
        if (pickChip) pickChip.textContent = `☑ 勾选场景 ${STATE.picks.length}`;
        if (STATE.motifPool === "关闭") poolHint.textContent = "池：不随机";
        else if (STATE.motifPool === "收藏场景") {
            poolHint.textContent = favs.length ? `池：${favs.length} 条` : "池：⚠ 空 → 回退全库";
        } else {
            poolHint.textContent = STATE.picks.length
                ? `池：${STATE.picks.length} 条` : "池：⚠ 空 → 回退全库";
        }
    };
    const mkPool = (key, label) => mkChip(STATE.motifPool === key, label, () => {
        STATE.motifPool = STATE.motifPool === key ? "关闭" : key;
        applySelect(`场景随机池 ${STATE.motifPool}`);
        renderMotifPage();
    }, rnd);

    mkPool("关闭", "关闭");
    mkPool("收藏场景", `★ 收藏场景（${favs.length}）`);
    pickChip = mkPool("勾选场景", `☑ 勾选场景 ${STATE.picks.length}`);

    rnd.appendChild(el("span", "k2ed-sep"));
    mkChip(false, "☑ 全选当前", async (ev) => {
        ev.stopPropagation();
        const ids = filtered().map((m) => m.id);
        if (!ids.length) return;
        await savePicks({ add: ids });
        syncLabels(); paintGrid();
        PANEL?.stat(`勾选池 +${ids.length}（当前筛选全部）　共 ${STATE.picks.length} 条`);
    }, rnd);
    mkChip(false, "⇄ 反选", async (ev) => {
        ev.stopPropagation();
        const ids = filtered().map((m) => m.id);
        if (!ids.length) return;
        const on = new Set(STATE.picks);
        await savePicks({ add: ids.filter((i) => !on.has(i)),
                          remove: ids.filter((i) => on.has(i)) });
        syncLabels(); paintGrid();
        PANEL?.stat(`反选完成　共 ${STATE.picks.length} 条`);
    }, rnd);
    mkChip(false, "✕ 清空勾选", async (ev) => {
        ev.stopPropagation();
        if (!STATE.picks.length) return;
        await savePicks({ clear: true });
        syncLabels(); paintGrid();
        PANEL?.stat("勾选池已清空");
    }, rnd);
    rnd.appendChild(poolHint);

    const holder = el("div", "");
    page.appendChild(holder);

    const matchQ = (m) => {
        const q = STATE.motifQ.toLowerCase();
        if (!q) return true;
        return [m.zh, m.title, m.title_zh, m.id, m.ratio]
            .some((v) => String(v || "").toLowerCase().includes(q));
    };
    const filtered = () => MAN.motifs
        .filter((m) => !STATE.favOnlyMotif || favs.includes(m.id))
        .filter((m) => !STATE.addedOnly || m.added)
        .filter((m) => !STATE.motifBranch || (m.branch || "scene") === STATE.motifBranch)
        .filter((m) => !STATE.motifAspect || (m.aspect || "landscape") === STATE.motifAspect)
        .filter((m) => !STATE.motifTags.size || (m.tags || []).some((t) => STATE.motifTags.has(t)))
        .filter((m) => !STATE.motifGenres.size || STATE.motifGenres.has(m.genre))
        .filter((m) => !STATE.motifSeries.size || STATE.motifSeries.has(m.series))
        .filter((m) => !STATE.motifShots.size || STATE.motifShots.has(m.shot))
        .filter((m) => !STATE.motifRef || m.ref === STATE.motifRef)
        .filter(matchQ);

    const paintGrid = () => {
        motifPaintBegin();
        try {
        holder.innerHTML = "";
        const rows = filtered();
        /* 分组平铺：同一系列的母题风格一致，按批次分段比混在 558 张里好找。
           段头可点 = 只保留该系列的筛选（等于「只看这一类」）。 */
        const grids = {};
        let solo = null;
        if (STATE.motifView === "group") {
            const byKey = {};
            rows.forEach((m) => {
                const k = m.series || "";
                (byKey[k] = byKey[k] || []).push(m);
            });
            (MAN.series || []).map((s) => s.key).filter((k) => byKey[k]).forEach((k) => {
                const meta = (MAN.series || []).find((s) => s.key === k) || { zh: k };
                const sec = el("div", "k2ed-sec");
                sec.dataset.series = k;
                sec.appendChild(el("span", "t", meta.zh));
                sec.appendChild(el("span", "c", `${byKey[k].length} 条`));
                sec.title = "点击 = 只看这个系列";
                sec.onclick = () => {
                    STATE.motifSeries.clear();
                    STATE.motifSeries.add(k);
                    repaintFilters();
                };
                holder.appendChild(sec);
                const g = el("div", "k2ed-grid mo");
                holder.appendChild(g);
                grids[k] = g;
            });
            Object.keys(byKey).forEach((k) => {      // 未登记的系列兜底
                if (grids[k]) return;
                const g = el("div", "k2ed-grid mo");
                holder.appendChild(g);
                grids[k] = g;
            });
        } else {
            solo = el("div", "k2ed-grid mo");
            holder.appendChild(solo);
        }
        const slot = (m) => solo || grids[m.series || ""] || Object.values(grids)[0] || holder;
        rows.forEach((m) => {
            const k = card(m.id === STATE.motif, () => pickMotif(m));
            k.dataset.id = m.id;
            k.dataset.kind = "motif";
            if (m.thumb) {
                const im = el("img", "");
                im.className = m.aspect === "portrait" ? "im34"
                    : (m.aspect === "square" ? "im11" : "im16");
                im.loading = "lazy";
                im.src = thumbURL(m.thumb, m.thumb_v);
                k.appendChild(im);
            }
            const asp = m.aspect || "landscape";
            /* 左上角工具条：勾选框 + 推荐画幅角标同排。
               原来两者各写 absolute left:5/top:5，勾选框压住「横屏/竖屏」只露半个字。 */
            const corner = el("div", "k2ed-corner");
            /* 勾选方块：只是加入随机池，不影响「当前场景」 */
            const pk = el("span", "k2ed-pick" + (STATE.picks.includes(m.id) ? " on" : ""));
            pk.textContent = "✓";
            pk.title = "加入 / 移出随机勾选池";
            pk.onclick = async (ev) => {
                ev.stopPropagation();
                const on = !pk.classList.contains("on");
                pk.classList.toggle("on", on);
                await savePicks(on ? { add: [m.id] } : { remove: [m.id] });
                syncLabels();
            };
            corner.appendChild(pk);
            /* 默认画幅徽标 = 按钮：点一下循环切（竖 → 横 → 方），点它不会选中卡片 */
            const badge = el("button", "", ASP_ZH[asp] || "");
            badge.type = "button";
            badge.className = "k2ed-aspbadge " + asp;
            badge.title = "默认画幅：" + (ASP_ZH[asp] || "横屏")
                + (m.ratio ? "（母题原比例 " + m.ratio + "）" : "")
                + "\n点击切换：竖 → 横 → 方";
            badge.onclick = (ev) => cycleMotifAspect(ev, m, badge);
            corner.appendChild(badge);
            k.appendChild(corner);
            k.appendChild(favStar("motifs", m.id, false));
            const cp = el("div", "cp");
            const nm = el("div", "n", m.zh || m.title || m.id);
            /* 新增角标：manifest 的 added 字段有值就显示（入库批次日期见 title 提示） */
            if (m.added) {
                const nb = el("span", "", "NEW");
                nb.style.cssText = "margin-left:6px;padding:0 4px;border-radius:3px;"
                    + "font-size:9px;letter-spacing:.5px;line-height:14px;"
                    + "background:#2f6f4e;color:#eafff4;vertical-align:middle;";
                nb.title = `本次新增（${m.added} 入库）`;
                nm.appendChild(nb);
            }
            cp.appendChild(nm);
            cp.appendChild(el("div", "w",
                `${m.branch === "poster" ? "海报 · " : ""}`
                + `${m.title && m.zh ? m.title + "　" : ""}`
                + `${m.ratio ? m.ratio + "　" : ""}${m.words} 词`));
            k.appendChild(cp);
            k.title = `${m.zh || ""}${m.zh ? "\n" : ""}${m.title || m.id}\n`
                + `${m.words} 词 / ${m.paras} 段　${m.branch_zh || "3D 场景"}　`
                + `推荐画幅：${ASP_ZH[asp] || "横屏"}${m.ratio ? "（" + m.ratio + "）" : ""}\n`
                + `标签：${(m.tags || []).join(" / ") || "—"}`
                + `${m.genre ? `\n题材：${(MAN.genres || []).find((g) => g.key === m.genre)?.zh || m.genre}` : ""}`
                + `${m.series ? `\n系列：${(MAN.series || []).find((s) => s.key === m.series)?.zh || m.series}` : ""}`
                + `${STATE.picks.includes(m.id) ? "\n☑ 已在随机勾选池" : ""}`;
            slot(m).appendChild(k);
        });
        if (!rows.length) {
            holder.appendChild(el("div", "k2ed-desc",
                "没有符合条件的结果，清掉筛选或换个关键词。"));
            return;
        }
        holder.appendChild(el("div", "k2ed-desc", `共 ${rows.length} 条`));
        } finally { motifPaintEnd(); }
    };

    /* 输入防抖：只重绘网格，不重建输入框（重建会丢焦点） */
    let _qt = null;
    inp.oninput = () => {
        clearTimeout(_qt);
        _qt = setTimeout(() => { STATE.motifQ = inp.value.trim(); paintGrid(); }, 200);
    };
    syncLabels();
    paintGrid();
    } finally { motifPaintEnd(); }
}

/* 选场景：立即写回节点；按推荐画幅切换画幅，按母题登记的推荐角色切换角色。
   ⚠ 只在「换到另一个母题」时带出角色：重复点同一条不覆盖用户后来手选的角色。
   recommend_char 是独立字段，只来自 motifs_new/_meta.json 的 character（角色库 key），
   不与参考图那批描述性的 character 文本混用。 */
function pickMotif(m) {
    const switching = STATE.motif !== m.id;
    if (switching) STATE.displayText = "";   // 换母题不用上一题的自定义英文
    STATE.motif = m.id;
    const asp = m.aspect || "landscape";
    let switched = "";
    if (asp !== "both") {
        /* 人物参考图母题（ref）按 ratio 精确切：它们的比例是设计的一部分（9:16），
           不能折进「竖屏 → 3:4」的粗映射里 —— 会把 9:16 的参考图强行变成 3:4。
           其余母题保持原手感（竖 3:4 / 横 16:9 / 方 1:1）。 */
        const exact = (m.ref && ASPECT_SIZE[m.ratio]) ? m.ratio : "";
        const want = exact || (asp === "portrait" ? "3:4"
            : (asp === "square" ? "1:1" : "16:9"));
        if (STATE.aspect !== want) {
            STATE.aspect = want;
            switched = `，画幅切到 ${want}`;
            renderAspects();
        }
    }
    const rc = m.recommend_char || "";
    if (switching && rc && /^[a-z0-9_()\-:.]+$/i.test(rc)) {
        if (rc !== STATE.char) {
            STATE.char = rc;
            STATE.charMeta = null;
            STATE.outfits = null;
            STATE.item = STATE.locks[rc] ? "char:" + STATE.locks[rc] : "";
            switched += `，角色带出 ${rc}`;
        }
        /* IP 名场面：服装必须「保持母题原样」，否则装配器会用随机版型换掉原作服装。
           lock_palette=true 保住色盘，这一段保住服装，两者缺一不可。 */
        if (STATE.costume !== MAN.keep) {
            STATE.costume = MAN.keep;
            switched += "，服装保持母题原样";
        }
    }
    markSelected();
    applySelect(`场景 ${m.zh || m.title || m.id}${switched}`);
    renderSide();
}

/* ---------------- 右侧预览 ---------------- */
async function renderSide() {
    const p = PANEL.panel;
    const c = await charMeta();
    const box = p.querySelector("#k2ed-pv-char");
    box.innerHTML = "";
    if (c.thumb) {
        const im = el("img", "");
        im.src = thumbURL(c.thumb, c.thumb_v);
        box.appendChild(im);
    }
    const ci = el("div", "");
    const nmLine = el("div", "nm", c.zh || STATE.char);
    const s = favStar("characters", STATE.char, true);
    s.onclick = async (ev) => {
        ev.stopPropagation();
        const on = !s.classList.contains("on");
        s.classList.toggle("on", on);
        await toggleFav("characters", STATE.char, on);
        if (STATE.tab === "char") {
            const star = pageEl().querySelector(`.k2ed-card[data-id="${CSS.escape(STATE.char)}"] .k2ed-star`);
            if (star) star.classList.toggle("on", on);
        }
    };
    nmLine.appendChild(s);
    ci.appendChild(nmLine);
    ci.appendChild(el("div", "wk", c.work_zh || c.work || ""));
    box.appendChild(ci);

    /* 官方预设服装：每角色记住一套（对齐 Anima 的 character_outfits 语义） */
    if (!STATE.outfits) { try { await fetchOutfits(); } catch (e) { /* noop */ } }
    const chOut = STATE.outfits?.character || [];
    if (chOut.length) {
        const row = el("div", "");
        row.style.cssText = "display:flex;align-items:center;gap:6px;margin-top:8px;flex-wrap:wrap";
        row.appendChild(el("span", "k2ed-lbl", "官方服装"));
        const sel = el("select", "");
        sel.className = "k2ed-sel";
        sel.style.flex = "1";
        const none = el("option", "", "不套用");
        none.value = "";
        sel.appendChild(none);
        chOut.forEach((o) => {
            const op = el("option", "", o.zh || o.id);
            op.value = o.id;
            sel.appendChild(op);
        });
        sel.value = STATE.locks[STATE.char] || "";
        sel.onchange = async () => {
            await saveLock(STATE.char, sel.value);
            STATE.item = sel.value ? "char:" + sel.value : "";
            if (STATE.tab === "char") renderCharPage();
            markSelected();
            applySelect(sel.value ? "官方服装已锁定" : "取消锁定服装");
            await renderSide();
        };
        row.appendChild(sel);
        box.appendChild(row);
    }

    const cos = p.querySelector("#k2ed-pv-cos");
    cos.innerHTML = "";
    if (STATE.costume === MAN.auto) cos.appendChild(el("div", "desc", "自动：按角色推荐顺序随机"));
    else if (STATE.costume === MAN.keep) cos.appendChild(el("div", "desc", "保持母题原样（不换装）"));
    else {
        const t = (MAN.costume_templates || []).find((x) => x.id === STATE.costume);
        cos.appendChild(el("div", "ttl", t ? t.zh : STATE.costume));
        cos.appendChild(el("div", "desc", t ? t.desc : ""));
    }

    const ib = p.querySelector("#k2ed-pv-item");
    ib.innerHTML = "";
    if (STATE.lora) {
        // LORA 模式下一个服装词都不写，单品 / 版型选择只是留档，不生效
        ib.appendChild(el("div", "desc",
            "LORA 服装触发词模式：单品与版型都不写进提示词，服装由角色 LORA 的触发词决定"));
    } else if (!STATE.item) ib.appendChild(el("div", "desc", "未叠加单品"));
    else {
        if (!STATE.outfits) await fetchOutfits();
        let tags = [];
        let name = "";
        if (STATE.item.startsWith("char:")) {
            const o = (STATE.outfits.character || []).find((x) => x.id === STATE.item.slice(5));
            name = o ? o.zh : ""; tags = o ? o.tags : [];
        } else {
            const o = (STATE.outfits.library || []).find((x) => x.id === STATE.item.slice(4));
            name = o ? o.zh : ""; tags = o ? o.tags : [];
        }
        ib.appendChild(el("div", "ttl", name || STATE.item));
        ib.appendChild(el("div", "desc", (tags || []).join(" · ")));
    }

    const mo = p.querySelector("#k2ed-pv-mo");
    mo.innerHTML = "";
    const m = MAN.motifs.find((x) => x.id === STATE.motif);
    if (m) {
        if (m.thumb) {
            const im = el("img", "");
            im.className = "k2ed-simg";
            const nat = (m.ratio || "").replace(":", " / ");
            if (nat) im.style.aspectRatio = nat;
            else if (m.aspect === "portrait") im.style.aspectRatio = "3 / 4";
            im.src = thumbURL(m.thumb, m.thumb_v);
            mo.appendChild(im);
        }
        mo.appendChild(el("div", "ttl", m.zh || m.title || m.id));
        if (m.title) mo.appendChild(el("div", "k2ed-en", m.title));
        mo.appendChild(el("div", "k2ed-meta", `${m.words} 词 · ${m.paras} 段`));
        const AZ = { landscape: "横屏", portrait: "竖屏",
                     both: "通用", square: "方屏" };
        mo.appendChild(el("div", "k2ed-meta",
            `分类：${m.branch_zh || "3D 场景"}　·　`
            + `推荐画幅：${AZ[m.aspect || "landscape"]}`
            + (m.ratio ? `（${m.ratio}）` : "")));
        if (m.workflow) {
            const wf = el("div", "k2ed-meta", `建议工作流：${m.workflow}`);
            wf.style.color = "#e8c96a";
            mo.appendChild(wf);
        }
        if (m.branch === "poster" || m.branch === "short") {
            mo.appendChild(el("div", "k2ed-desc",
                m.branch === "poster"
                    ? "平面海报分支：保留版式与大标题，角色 / 版型 / 单品按海报语法适配。"
                    : "短提示词分支：保留 4–8 段短句构图，只换身份并追加一句服装说明。"));
        }

        /* 画面英文：可编辑，写回节点；显示母题真正的画内原文与中文释义 */
        const headRow = el("div", "display:flex;align-items:center;justify-content:space-between;gap:8px");
        headRow.appendChild(el("div", "k2ed-lbl", "画面英文（留空 = 用母题原文）"));
        const ntLabel = el("label", "k2ed-lbl");
        ntLabel.style.cssText = "display:flex;align-items:center;gap:4px;cursor:pointer;white-space:nowrap";
        const ntBox = el("input", "");
        ntBox.type = "checkbox";
        ntBox.checked = !!STATE.noText;
        ntBox.style.cssText = "accent-color:#3d6a86;cursor:pointer;margin:0";
        ntLabel.appendChild(ntBox);
        ntLabel.appendChild(el("span", "", "不显示文字"));
        headRow.appendChild(ntLabel);
        mo.appendChild(headRow);
        const din = el("input", "");
        din.className = "k2ed-dispin";
        din.placeholder = m.display_orig || m.title || "填入要画在画面里的英文";
        din.value = STATE.displayText || "";
        din.disabled = !!STATE.noText;
        if (STATE.noText) din.style.opacity = ".45";
        ntBox.onchange = async () => {
            STATE.noText = ntBox.checked;
            din.disabled = ntBox.checked;
            din.style.opacity = ntBox.checked ? ".45" : "";
            if (CUR) setW(CUR, "画面不显示英文", ntBox.checked);
            PANEL.stat(ntBox.checked
                ? "画面不显示文字：已写回节点，母题里的标题 / 编号 / 排版文字全部清除"
                : "已恢复母题原有的画内文字");
            app.graph.setDirtyCanvas(true, true);
            if (STATE.showText) await doGenerate();
        };
        din.oninput = () => {
            STATE.displayText = din.value;
            clearTimeout(_dispTimer);
            _dispTimer = setTimeout(async () => {
                if (!CUR) return;
                setW(CUR, "画面英文文字", STATE.displayText);
                const src = m.display_orig || m.title || "（母题原本无文字）";
                PANEL.stat(STATE.displayText
                    ? `画面英文「${STATE.displayText}」已写回节点，将替换画内文字「${src}」`
                    : "画面英文已清空，恢复母题原文");
                app.graph.setDirtyCanvas(true, true);
                // 预览框已经展开时顺手刷新，让用户直接看到正文里的新文字
                if (STATE.showText) await doGenerate();
            }, 400);
        };
        mo.appendChild(din);
        if (m.display_orig) {
            mo.appendChild(el("div", "k2ed-desc",
                `原文「${m.display_orig}」中文释义：${m.title_zh || "（未登记）"}`));
        }
        mo.appendChild(el("div", "k2ed-desc",
            "填写后替换画面里的文字，位置 / 字体 / 材质描述保持不变；母题原本无文字时会新增一行排印。"));
    } else mo.appendChild(el("div", "desc", "还没选场景"));

    renderAspects();
}

/* ---------------- 随机种子：固定 / 随机 ---------------- */
function renderSeed() {
    const seg = PANEL.panel.querySelector("#k2ed-seedmode");
    seg.innerHTML = "";
    [["fixed", "固定"], ["random", "随机"]].forEach(([k, label]) => {
        const b = el("button", "", label);
        if (STATE.seedMode === k) b.className = "on";
        b.onclick = () => setSeedMode(k);
        seg.appendChild(b);
    });
    const inp = PANEL.panel.querySelector("#k2ed-seednum");
    const fixed = STATE.seedMode === "fixed";
    inp.value = fixed ? String(STATE.seed) : "";
    inp.placeholder = fixed ? "" : "每次换";
    inp.disabled = !fixed;
    inp.title = fixed ? "固定种子：同参数重跑出同一张图" : "随机：每次排队都换一个种子";
    const dice = PANEL.panel.querySelector("#k2ed-dice");
    dice.disabled = !fixed;
}

function writeSeed() {
    if (!CUR) return;
    setW(CUR, "随机种子", STATE.seed >>> 0);
    setW(CUR, "每次重随机", STATE.seedMode === "random");
    app.graph.setDirtyCanvas(true, true);
    CUR.setDirtyCanvas?.(true, true);
}

function setSeedMode(mode) {
    if (mode === STATE.seedMode) return;
    if (mode === "fixed" && STATE.seedMode === "random") {
        // 从「随机」切到「固定」：立刻冻结一个种子，否则固定下来的是上一次的旧值
        STATE.seed = Math.floor(Math.random() * SEED_MAX);
    }
    STATE.seedMode = mode;
    renderSeed();
    writeSeed();
    PANEL.stat(mode === "fixed"
        ? `种子已固定为 ${STATE.seed}（同参数重跑可复现）`
        : "种子改为随机：每次排队都换一个");
}

function bindSeed() {
    const inp = PANEL.panel.querySelector("#k2ed-seednum");
    const commit = () => {
        const v = parseInt((inp.value || "").replace(/[^\d]/g, ""), 10);
        if (!Number.isFinite(v)) { renderSeed(); return; }
        STATE.seed = Math.min(SEED_MAX, Math.max(0, v));
        STATE.seedMode = "fixed";
        renderSeed();
        writeSeed();
        PANEL.stat(`种子已固定为 ${STATE.seed}`);
    };
    inp.onchange = commit;
    inp.onblur = commit;
    inp.onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); inp.blur(); } };
    PANEL.panel.querySelector("#k2ed-dice").onclick = () => {
        STATE.seed = Math.floor(Math.random() * SEED_MAX);
        STATE.seedMode = "fixed";
        renderSeed();
        writeSeed();
        PANEL.stat(`新种子 ${STATE.seed}（已固定）`);
    };
}

function renderAspects() {
    const seg = PANEL.panel.querySelector("#k2ed-asp");
    seg.innerHTML = "";
    (MAN.aspects || ["16:9", "3:4"]).forEach((a) => {
        const b = el("button", "", a);
        if (a === STATE.aspect) b.className = "on";
        b.onclick = () => {
            STATE.aspect = a;
            renderAspects();
            applySelect("画幅 " + a);
            renderSide();
        };
        seg.appendChild(b);
    });
}

function renderTabs() {
    PANEL.panel.querySelectorAll(".k2ed-tab").forEach((b) => {
        b.classList.toggle("on", b.dataset.tab === STATE.tab);
        b.onclick = () => { STATE.tab = b.dataset.tab; renderTabs(); renderPage(); };
    });
    const wrap = PANEL.panel.querySelector("#k2ed-lorawrap");
    const box = PANEL.panel.querySelector("#k2ed-lora");
    if (box) box.checked = !!STATE.lora;
    if (wrap) wrap.classList.toggle("on", !!STATE.lora);
}

async function renderPage() {
    if (STATE.tab === "char") {
        if (!STATE.chars.length) await fetchChars(true);
        return renderCharPage();
    }
    if (STATE.tab === "costume") return renderCostumePage();
    return renderMotifPage();
}

/* ---------------- 动作 ---------------- */
async function doGenerate() {
    if (!STATE.motif) {
        PANEL.stat("先在「③ 场景」选一个母题");
        STATE.tab = "motif"; renderTabs(); renderPage();
        return;
    }
    /* 生成前自检：角色 / LoRA / 触发词 / 随机池不一致时红字提醒，但照常生成 */
    const chk = await charCheck();
    if (chk?.bad) PANEL.stat(`⚠ 角色自检：${chk.text}　|　生成中…`, "warn");
    else PANEL.stat("生成中…");
    try {
        const q = new URLSearchParams({
            motif: STATE.motif, char: STATE.char, aspect: STATE.aspect,
            costume: STATE.costume || MAN.auto, item: STATE.item || "",
            display: STATE.displayText || "",
            notext: STATE.noText ? "1" : "",
            lora: STATE.lora ? "1" : "",
            hairlock: STATE.hairlock ? "1" : "",
        });
        const r = await api.fetchApi("/k2ed/build?" + q.toString());
        const d = await r.json();
        if (!d.ok) { PANEL.stat("失败：" + d.error); return; }
        STATE.text = d.text;
        STATE.edited = false;
        PANEL.panel.querySelector("#k2ed-ta").value = d.text;
        if (!STATE.showText) toggleText(true);
        PANEL.stat(`已生成 ${d.words} 词 / ${d.paras} 段 / 色盘 ${d.pct}`
            + (d.outfit_tags?.length ? `　单品 ${d.outfit_tags.length} 条` : "")
            + (d.issues?.length ? "　⚠ " + d.issues.join("；") : "　✓")
            + (chk?.bad ? `　|　⚠ 角色自检：${chk.text}` : ""),
            (chk?.bad || d.issues?.length) ? "warn" : "");
    } catch (e) {
        PANEL.stat("请求失败：" + e);
    }
}

function toggleText(on) {
    STATE.showText = on === undefined ? !STATE.showText : on;
    PANEL.panel.querySelector("#k2ed-txt").style.display = STATE.showText ? "block" : "none";
    PANEL.panel.querySelector("#k2ed-tgl").textContent = STATE.showText ? "隐藏提示词" : "显示提示词";
}

function syncAspect(aspect) {
    const nodes = (app.graph?._nodes || []).filter((n) => n.type === "XB_ImageParamsMaster");
    if (nodes.length === 0) return "未找到「图片参数大全」节点";
    if (nodes.length > 1) return `画布上有 ${nodes.length} 个参数节点，未自动同步`;
    const sz = ASPECT_SIZE[aspect];
    if (!sz) return `画幅 ${aspect} 无预设尺寸`;
    const arValue = ASPECT_NATIVE.has(aspect) ? aspect : "Free";
    for (const [k, v] of [["aspect_ratio", arValue], ["width", sz[0]], ["height", sz[1]]]) {
        const w = getW(nodes[0], k);
        if (w) w.value = v;
    }
    app.graph.setDirtyCanvas(true, true);
    return `画幅 → ${aspect} ${sz[0]}×${sz[1]}`;
}

let _dispTimer = null;

/* ---------------- 角色一致性自检 ----------------
   踩过的坑（2026-11-26 实测）：节点「角色」写 hsin，但「角色随机池=收藏角色 · genshin impact」
   把提示词换成了雷电将军 / 甘雨；同时触发词串里还挂着 Hsin 的 white horns / fox-like ears。
   三套身份一起进模型 → 紫发 + 角 + 狐耳全冒出来。这个自检就是把这三者摆到一起看。 */
async function runCharCheck() {
    const r = await charCheck();
    if (r) PANEL.stat(r.text, r.bad ? "warn" : "");
}

/* 返回 { text, bad }；生成前会自动调用（不一致只红字提醒，不拦生成） */
async function charCheck() {
    if (!CUR) return null;
    if (!STATE.chars.length) { try { await fetchChars(true); } catch (e) { /* noop */ } }
    const key = getW(CUR, "角色")?.value || "";
    const c = (STATE.chars || []).find((x) => x.id === key) || {};
    const label = c.zh || c.name || key || "（未选角色）";
    const toks = [String(key).split("_(")[0], c.name, c.zh]
        .filter((t) => t && String(t).length >= 1)
        .map((t) => String(t).toLowerCase());

    const loras = new Set(), active = new Set();
    let trig = "";
    for (const n of (app.graph?._nodes || [])) {
        const ws = n.widgets || [];
        const isLora = /lora/i.test(n.type || "");
        for (const w of ws) {
            if (typeof w.value === "string") {
                for (const m of w.value.matchAll(/<lora:([^:>]+)/gi)) {
                    loras.add(m[1]);
                    active.add(m[1]);        // <lora:…> 写法本身就是启用
                }
            } else if (isLora && Array.isArray(w.value)) {
                for (const it of w.value) {
                    if (!it || !it.name) continue;
                    loras.add(it.name);
                    if (it.active !== false) active.add(it.name);
                }
            }
        }
        if (/TriggerWord/i.test(n.type || "")) {
            trig += " " + ws.map((w) => String(w.value ?? "")).join(" ");
        }
    }
    const lowTrig = trig.toLowerCase();
    const hitLora = [...active].filter((n) => {
        const ln = n.toLowerCase();
        return toks.some((t) => {
            if (!t) return false;
            if (ln === t) return true;
            if (t.length >= 3 && (ln.includes(t) || t.includes(ln))) return true;
            // 中文名常常只取一个字（角色「心」↔ LoRA「心月狐 / 心·月狐形态」）
            return ln.startsWith(t) && ln.length >= 2;
        });
    });
    const hitTrig = toks.some((t) => lowTrig.includes(t));

    const parts = [`角色 ${label}`];
    let bad = false;
    if (!loras.size) {
        parts.push("图里没找到 LoRA 节点");
    } else {
        parts.push(`LoRA ${[...loras].join(" / ")}`);
        if (hitLora.length) {
            parts.push(`✓ 与角色一致（${hitLora.join(" / ")}）`);
        } else {
            bad = true;
            parts.push(`与角色不一致 —— 提示词写 ${label}，LoRA 是 `
                + `${[...active].join(" / ") || "无启用的"}`);
        }
    }
    if (trig.trim()) {
        if (hitTrig) parts.push("触发词含该角色");
        else { bad = true; parts.push(`触发词里没有「${label}」`); }
    }
    if (STATE.charPool && STATE.charPool !== "关闭") {
        bad = true;
        parts.push(`角色随机池=「${STATE.charPool}」`
            + (STATE.charPoolWork ? `·${STATE.charPoolWork}` : "")
            + "，提示词里的角色每张都会被随机替换（面板上选的角色等于没选）");
    }
    return { text: parts.join("　|　"), bad };
}

/* 选中即写回：不必先生成预览，也不用再点「应用」 */
function applySelect(reason) {
    if (!CUR) return;
    const syncEl = PANEL.panel.querySelector("#k2ed-sync");
    setW(CUR, "角色", STATE.char);
    setW(CUR, "母题", STATE.motif);
    setW(CUR, "画幅", STATE.aspect);
    setW(CUR, "服装", STATE.costume || MAN.auto);
    setW(CUR, "单品", STATE.item || "");
    setW(CUR, "覆盖提示词", "");        // 换了选择，之前手改的文本作废
    setW(CUR, "画面英文文字", STATE.displayText || "");
    setW(CUR, "画面不显示英文", !!STATE.noText);
    setW(CUR, "LORA服装触发词", !!STATE.lora);
    setW(CUR, "角色随机池", STATE.charPool || "关闭");
    setW(CUR, "角色随机作品", STATE.charPoolWork || "");
    setW(CUR, "场景随机池", STATE.motifPool || "关闭");
    STATE.edited = false;

    let msg = "✓ 已写回节点" + (reason ? `（${reason}）` : "");
    if (syncEl.checked && STATE.aspect !== STATE._syncedAspect) {
        const r = syncAspect(STATE.aspect);
        STATE._syncedAspect = STATE.aspect;   // 成功与否都记下，避免每次点选都重复提示
        msg += "　|　" + r;
    }
    const ta = PANEL.panel.querySelector("#k2ed-ta");
    if (STATE.text && ta.value.trim()) msg += "　|　预览已过期，点「刷新预览」";
    PANEL.stat(msg);
    app.graph.setDirtyCanvas(true, true);
    CUR.setDirtyCanvas?.(true, true);
}

/* 手动改文本框：防抖写回「覆盖提示词」，同样不用点按钮 */
let _txtTimer = null;
function onTextEdited() {
    if (!CUR) return;
    STATE.edited = true;
    clearTimeout(_txtTimer);
    _txtTimer = setTimeout(() => {
        const v = PANEL.panel.querySelector("#k2ed-ta").value;
        setW(CUR, "覆盖提示词", v);
        PANEL.stat(`✓ 已写回编辑后的提示词（${v.length} 字符）`);
        app.graph.setDirtyCanvas(true, true);
    }, 600);
}

/* ---------------- 打开 / 关闭 ---------------- */
/* 超时包装：某个请求挂住时不能把整个面板拖死（openPanel 里每个 await 都要能放手） */
function withTimeout(promise, ms, label) {
    return Promise.race([
        promise,
        new Promise((_, rej) => setTimeout(() => rej(new Error(label + " 超时")), ms)),
    ]);
}

/* ⚠ 不能用布尔锁：上一个版本用 `if (_opening) return` + finally 复位，
   只要某个 await 永不返回（fetch 挂住 / 缩略图批量加载卡住），
   finally 就永远不执行，之后每次点击都被静默拦掉 —— 表现就是「点了一点反应都没有」。
   改成时间戳：超过 20 秒自动视为失效，允许重试。 */
// 版本埋点：面板打不开时让用户按 F12 就能确认浏览器加载的是哪一版 JS
const PANEL_VER = "1.20.9";
console.log("[K2Editorial] 面板脚本 v" + PANEL_VER + " 已加载");

let _openingSince = 0;
const OPEN_GUARD_MS = 20000;

async function openPanel(node) {
    const now = Date.now();
    if (_openingSince && now - _openingSince < OPEN_GUARD_MS) return false;
    _openingSince = now;
    CUR = node;
    try {
        const p = ensurePanel();
        if (p.dis) p.dis.style.display = "none";   // 上次若停在免责声明上，重开不继承
        // ⚠ 先亮面板再加载数据：原来 display:flex 放在函数最末尾，中间任何一步 await
        //   抛异常都会导致「点了完全没反应」——现在至少能看到面板 + 报错。
        p.mask.style.display = "flex";
        p.stat("正在加载…");
        try {
            await withTimeout(manifest(), 10000, "加载母题库");
        } catch (e) {
            p.stat("加载库失败：" + (e?.message || e) + "（确认已重启加载插件）");
            return false;
        }
        syncStateFromNode(node);
        if (!MAN || !Array.isArray(MAN.motifs) || !MAN.motifs.length) {
            p.stat("母题库为空：manifest 没读到数据，检查插件是否正常加载");
            return false;
        }
        if (!MAN.motifs.some((m) => m.id === STATE.motif)) STATE.motif = MAN.motifs[0].id;
        // 打开面板不主动改参数节点；之后只有画幅真的变了才同步
        STATE._syncedAspect = STATE.aspect;

        if (!p.built) {
            // built 只在绑定**全部成功**后才置 true：中途抛错会让按钮永远不响应，
            // 而且下次打开会跳过绑定 —— 这是「有时打得开有时打不开」的另一半原因。
            try {
                bindPanelOnce(p);
                p.built = true;
            } catch (e) {
                p.stat("面板初始化失败：" + (e?.message || e));
                console.error("[K2Editorial] bindPanelOnce", e);
                return false;
            }
        }

        if (!STATE.chars.length) {
            try { await withTimeout(fetchChars(true), 10000, "加载角色表"); } catch (e) { /* noop */ }
        }
        try { await withTimeout(fetchFavs(), 6000, "加载收藏"); } catch (e) { /* noop */ }
        try { await withTimeout(fetchLocks(), 6000, "加载服装锁定"); } catch (e) { /* noop */ }
        // 没有手动选单品时，用该角色锁定的官方服装
        if (!STATE.item && STATE.locks[STATE.char]) STATE.item = "char:" + STATE.locks[STATE.char];
        const ov = getW(node, "覆盖提示词")?.value || "";
        STATE.text = ov;
        STATE.edited = !!ov;
        p.panel.querySelector("#k2ed-ta").value = STATE.text;
        toggleText(STATE.showText);

        // 渲染分步容错：某一块画不出来不该让整个面板消失
        try { renderTabs(); } catch (e) { console.error("[K2Editorial] renderTabs", e); }
        try { renderSeed(); } catch (e) { console.error("[K2Editorial] renderSeed", e); }
        try { await withTimeout(renderPage(), 12000, "渲染场景页"); }
        catch (e) {
            p.stat("场景页渲染：" + (e?.message || e) + "（可继续用其它页签）");
            console.error("[K2Editorial] renderPage", e);
        }
        try { await withTimeout(renderSide(), 8000, "渲染侧栏"); }
        catch (e) { console.error("[K2Editorial] renderSide", e); }
        if (!p.panel.querySelector("#k2ed-stat").textContent) p.stat("");
        p.mask.style.display = "flex";
        app.graph?.setDirtyCanvas(true, true);   // 名字表刚登记，让节点摘要用中文重画
        return true;
    } catch (e) {
        // 最后兜底：无论如何要让面板亮出来并说明原因，不能「点了没反应」
        try {
            const p = ensurePanel();
            p.mask.style.display = "flex";
            p.stat("打开面板出错：" + (e?.message || e));
        } catch (e2) { /* 连面板都建不起来 */ }
        console.error("[K2Editorial] openPanel", e);
        window.__k2ed && (window.__k2ed.lastError = String((e && e.stack) || e));
    } finally {
        _openingSince = 0;
    }
}

/* 一次性绑定：只在 p.built 为 false 时调用；失败可重试 */
function bindPanelOnce(p) {
    p.panel.querySelector("#k2ed-gen").onclick = doGenerate;
    p.panel.querySelector("#k2ed-tgl").onclick = () => toggleText();
    /* 回到顶部：三个页签共用同一个滚动容器，滚到底后一键回列表顶部 */
    p.panel.querySelector("#k2ed-top").onclick = () => {
        const pg = pageEl();
        if (!pg) return;
        pg.scrollTo({ top: 0, behavior: "smooth" });
    };
    p.panel.querySelector("#k2ed-rnd").onclick = async () => {
        const pick = MAN.motifs[Math.floor(Math.random() * MAN.motifs.length)];
        STATE.costume = MAN.auto;
        STATE.item = "";
        pickMotif(pick);
        await renderSide();
    };
    p.panel.querySelector("#k2ed-copy").onclick = async () => {
        const t = p.panel.querySelector("#k2ed-ta").value;
        try { await navigator.clipboard.writeText(t); PANEL.stat("已复制 " + t.length + " 字符"); }
        catch { PANEL.stat("复制失败，请手动全选"); }
    };
    p.panel.querySelector("#k2ed-ta").addEventListener("input", onTextEdited);
    bindSeed();
}

function closePanel() {
    if (PANEL) PANEL.mask.style.display = "none";
    /* 关闭即清空滚动记忆：openPanel 每次都会重新 renderPage，下次从顶部开始 */
    MOTIF_SCROLL = { top: 0 };
    _motifPaintDepth = 0;
    CUR = null;
}

/* ---------------- 扩展注册 ---------------- */
/* 诊断入口：面板按钮没反应时，可以让用户在 Console 执行
     __k2ed.nodes()      列出图上的 K2 节点
     __k2ed.open()       绕过按钮直接打开第一个节点面板
     __k2ed.lastError    最近一次失败原因 */
window.__k2ed = {
    ver: PANEL_VER,
    lastError: null,
    nodes: () => (app.graph?._nodes || [])
        .filter((n) => n.type === NODE_NAME || n.comfyClass === NODE_NAME)
        .map((n, i) => ({ i, id: n.id, widgets: (n.widgets || []).map((w) => w.name + ":" + w.type) })),
    // 打印按钮与各 widget 的实际坐标，用来判断「按钮画在 widget 下面还是被盖住/画出界」
    debug: () => {
        const n = (app.graph?._nodes || []).find((x) => x.type === NODE_NAME || x.comfyClass === NODE_NAME);
        if (!n) return "no-node";
        return {
            size: n.size,
            btnEl: !!n.__k2edBtnEl,
            widgets_full: (n.widgets || []).map((w) => w.name),
            userResized: !!n.__k2edUserResized,
            widgets: (n.widgets || []).map((w) => ({ name: w.name, last_y: w.last_y, h: w.height })),
        };
    },
    open: (idx = 0) => {
        const ns = (app.graph?._nodes || []).filter((n) => n.type === NODE_NAME || n.comfyClass === NODE_NAME);
        if (!ns.length) { console.warn("[K2Editorial] 图上没有 K2 节点"); return "no-node"; }
        console.log("[K2Editorial] 手动打开", ns[idx]?.id);
        return openPanel(ns[idx || 0]);
    },
};

app.registerExtension({
    name: "K2Editorial.Panel",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE_NAME) return;

        const onCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            onCreated?.apply(this, arguments);
            if (this._k2ed_done) return;
            this._k2ed_done = true;

            // 「⚙ 打开设置面板」用 **DOM widget**：canvas 自绘会被 DOM 层盖住，
            // 而 litegraph 的老式 canvas button 命中又依赖 last_y，节点一收缩就点不着。
            // DOM 元素走浏览器自己的点击事件，不经过任何坐标换算 —— 这是最稳的一层。
            try {
                const btnEl = document.createElement("button");
                btnEl.type = "button";
                btnEl.textContent = BTN_LABEL;
                btnEl.style.cssText = [
                    "width:100%", "height:28px", "margin:4px 0 2px", "padding:0 10px",
                    "border-radius:7px", "border:1px solid #3a3d47", "background:#2b2d35",
                    "color:#dfe3e8", "font:13px/26px system-ui,'Microsoft YaHei',sans-serif",
                    "cursor:pointer", "box-sizing:border-box",
                ].join(";");
                btnEl.addEventListener("mouseenter", () => {
                    btnEl.style.background = "#2f3a46";
                    btnEl.style.borderColor = "#4b7fa3";
                    btnEl.style.color = "#cfe6f5";
                });
                btnEl.addEventListener("mouseleave", () => {
                    btnEl.style.background = "#2b2d35";
                    btnEl.style.borderColor = "#3a3d47";
                    btnEl.style.color = "#dfe3e8";
                });
                btnEl.addEventListener("click", (e) => {
                    e.stopPropagation();
                    e.preventDefault();
                    console.log("[K2Editorial] DOM 按钮点击 → openPanel");
                    openPanel(this);
                });
                if (typeof this.addDOMWidget === "function") {
                    // 注意：type 不能传 "button"，否则 ComfyUI Vue Nodes 2.0 会将其当作原生 WidgetButton 渲染，
                    // 忽略自定义 btnEl 并只显示 widget.name（"k2ed-open"），点击时也只调 widget.callback 而不触发 btnEl 的 click。
                    const w = this.addDOMWidget("k2ed-open", "k2ed_button", btnEl, {
                        serialize: false,
                        getHeight: () => 34,
                        getMinHeight: () => 34,
                    });
                    if (w) {
                        w.label = BTN_LABEL;
                    }
                } else {
                    // 老版本没有 addDOMWidget：退回到把节点挂在 DOM 上（比 canvas 自绘可靠）
                    const w = this.addWidget("button", BTN_LABEL, null, () => openPanel(this),
                                             { serialize: false });
                    w.serialize = false;
                }
                this.__k2edBtnEl = btnEl;
            } catch (e) {
                console.error("[K2Editorial] 创建打开按钮失败", e);
            }

            syncStateFromNode(this);
            installSummary(this);
            const self = this;
            const fold = () => {
                hideWidgets(self);
                // 折叠后可见内容：摘要（2 行，画到 y≈56）+ 锁定发色（≈26）+ DOM 按钮（≈34）
                // 高度写死 104 会把按钮挤出节点；这里按内容给足，并保证不小于 150。
                self.setSize([Math.max(self.size[0], 320), 150]);
                self.setDirtyCanvas(true, true);
            };
            setTimeout(fold, 30);
            setTimeout(fold, 260);

            // 备用入口：双击节点打开面板。按钮回调失效时用它判断是「按钮没绑上」
            // 还是「openPanel 本身有问题」—— 双击能开 = 按钮绑定问题，双击也开不了 = openPanel 问题
            this.onDblClick = (e, pos, canvas) => {
                console.log("[K2Editorial] 节点双击 → openPanel");
                openPanel(this);
            };
        };

        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            onConfigure?.apply(this, arguments);
            const self = this;
            setTimeout(() => { hideWidgets(self); syncStateFromNode(self); self.setDirtyCanvas(true, true); }, 60);
        };

        const onExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            onExecuted?.apply(this, arguments);
            // 只回写「面板当前打开的那个节点」：否则画布上的 A 执行完，
            // 会把正在编辑的 B 的预览框换成 A 的正文。
            if (CUR !== this) return;
            const t = message?.k2ed_text?.[0];
            if (!t) return;
            STATE.text = t;
            STATE.edited = false;
            if (PANEL && PANEL.mask.style.display !== "none") {
                PANEL.panel.querySelector("#k2ed-ta").value = t;
                PANEL.stat("节点已执行，预览已刷新");
            }
            const pk = message?.k2ed_picked?.[0];
            if (pk && PANEL) {
                try {
                    const d = JSON.parse(pk);
                    const bits = [];
                    if (d.char) bits.push(`角色 ${d.char_zh || d.char}〔${d.char_why || ""}〕`);
                    if (d.motif) bits.push(`场景 ${d.motif_zh || d.motif}〔${d.motif_why || ""}〕`);
                    if (bits.length) PANEL.stat("🎲 本次抽中：" + bits.join(" ｜ "));
                } catch (e) { /* 非 JSON 忽略 */ }
            }
        };
    },
});
