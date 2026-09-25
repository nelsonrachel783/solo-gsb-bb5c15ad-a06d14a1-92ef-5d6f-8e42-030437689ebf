/* 纸张对折打孔展开预览 —— 前端逻辑（原生 SVG，无依赖） */
"use strict";

const state = {
  paper: { w: 210, h: 297 },
  folds: [{ axis: "v", side: "left" }],
  punches: [], // 原纸坐标系（折叠面即原纸的子矩形）
  holeR: 2,
};
let result = null; // 最近一次 /api/compute 的返回

const $ = (id) => document.getElementById(id);
const NS = "http://www.w3.org/2000/svg";
const round3 = (v) => Math.round(v * 1000) / 1000;
const fmt = (v) => String(round3(v));

function el(name, attrs, parent) {
  const n = document.createElementNS(NS, name);
  for (const k in attrs) n.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(n);
  return n;
}

/* ---------- 与服务端通信 ---------- */

function payload() {
  return {
    paper: state.paper,
    folds: state.folds,
    punches: state.punches,
    hole_r: state.holeR,
  };
}

async function compute(isRetry) {
  let data;
  try {
    const res = await fetch("/api/compute", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload()),
    });
    data = await res.json();
  } catch (e) {
    showMessages([{ text: "无法连接服务器：" + e.message, error: true }]);
    return;
  }
  if (!data.ok) {
    showMessages([{ text: data.error || "参数错误", error: true }]);
    return;
  }
  result = data;
  // 折法/纸张变化后，自动清理落在折叠面之外的打孔点
  if (!isRetry && prunePunches()) return compute(true);
  render();
}

function prunePunches() {
  const f = result.folded, eps = 1e-6;
  const before = state.punches.length;
  state.punches = state.punches.filter(
    (p) => p.x >= f.x0 - eps && p.x <= f.x1 + eps && p.y >= f.y0 - eps && p.y <= f.y1 + eps
  );
  return state.punches.length !== before;
}

let timer = null;
function scheduleCompute() {
  clearTimeout(timer);
  timer = setTimeout(() => compute(), 120);
}

/* ---------- 渲染 ---------- */

function render() {
  renderFolded();
  renderUnfolded();
  renderFoldList();
  showMessages(result.warnings.map((w) => ({ text: w, error: false })));
}

function renderFolded() {
  const svg = $("foldedSvg");
  svg.innerHTML = "";
  const f = result.folded;
  const u = Math.max(f.w, f.h) / 300; // 线宽单位，随视图缩放
  const m = Math.max(f.w, f.h) * 0.08 + state.holeR * 3 + 4 * u;
  svg.setAttribute("viewBox", `${f.x0 - m} ${f.y0 - m} ${f.w + 2 * m} ${f.h + 2 * m}`);

  el("rect", {
    x: f.x0, y: f.y0, width: f.w, height: f.h,
    fill: "#ffffff", stroke: "#9aa0a6", "stroke-width": 1.6 * u,
  }, svg);

  // 四条边中是折痕的边用橙色加粗标出
  const edges = [
    { o: "v", at: f.x0, x1: f.x0, y1: f.y0, x2: f.x0, y2: f.y1 },
    { o: "v", at: f.x1, x1: f.x1, y1: f.y0, x2: f.x1, y2: f.y1 },
    { o: "h", at: f.y0, x1: f.x0, y1: f.y0, x2: f.x1, y2: f.y0 },
    { o: "h", at: f.y1, x1: f.x0, y1: f.y1, x2: f.x1, y2: f.y1 },
  ];
  for (const e of edges) {
    const isFold = result.fold_edges.some(
      (g) => g.orientation === e.o && Math.abs(g.at - e.at) < 1e-6
    );
    if (isFold) {
      el("line", {
        x1: e.x1, y1: e.y1, x2: e.x2, y2: e.y2,
        stroke: "#f2994a", "stroke-width": 3 * u, "stroke-linecap": "round",
      }, svg);
    }
  }

  for (const p of state.punches) {
    el("circle", {
      cx: p.x, cy: p.y, r: state.holeR,
      fill: "#dc2626", "fill-opacity": 0.85, stroke: "#7f1d1d", "stroke-width": 0.8 * u,
    }, svg);
  }

  $("foldedInfo").textContent =
    `折叠面尺寸：${fmt(f.w)} × ${fmt(f.h)} mm ｜ 层数：${result.layers} ｜ 打孔点：${state.punches.length} 个`;
}

function renderUnfolded() {
  const svg = $("unfoldedSvg");
  svg.innerHTML = "";
  const W = state.paper.w, H = state.paper.h;
  const u = Math.max(W, H) / 500;
  const m = Math.max(W, H) * 0.05 + state.holeR * 2 + 4 * u;
  svg.setAttribute("viewBox", `${-m} ${-m} ${W + 2 * m} ${H + 2 * m}`);

  el("rect", {
    x: 0, y: 0, width: W, height: H,
    fill: "#ffffff", stroke: "#1f2329", "stroke-width": 1.6 * u,
  }, svg);

  for (const c of result.creases) {
    el("line", {
      x1: c.x1, y1: c.y1, x2: c.x2, y2: c.y2,
      stroke: "#2563eb", "stroke-width": 0.8 * u,
      "stroke-dasharray": `${4 * u},${2.5 * u}`,
    }, svg);
  }

  for (const p of result.holes) {
    el("circle", {
      cx: p.x, cy: p.y, r: state.holeR,
      fill: "#dc2626", "fill-opacity": 0.85, stroke: "#7f1d1d", "stroke-width": 0.6 * u,
    }, svg);
  }

  const merged = result.hole_count_total - result.hole_count_unique;
  $("unfoldedInfo").textContent =
    `展开孔数：${result.hole_count_unique} 个（理论 ${result.hole_count_total} 个` +
    (merged > 0 ? `，重合 ${merged} 个已合并` : "") +
    `）｜ 折痕 ${result.creases.length} 条`;
}

const FOLD_LABEL = {
  "v:left": "垂直中线 · 左→右",
  "v:right": "垂直中线 · 右→左",
  "h:top": "水平中线 · 上→下",
  "h:bottom": "水平中线 · 下→上",
};

function renderFoldList() {
  const box = $("foldList");
  box.innerHTML = "";
  state.folds.forEach((f, i) => {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.textContent = `${i + 1}. ${FOLD_LABEL[f.axis + ":" + f.side]}`;
    const x = document.createElement("button");
    x.textContent = "✕";
    x.title = "删除这一步";
    x.addEventListener("click", () => {
      state.folds.splice(i, 1);
      compute();
    });
    chip.appendChild(x);
    box.appendChild(chip);
  });
}

function showMessages(list) {
  const box = $("messages");
  box.innerHTML = "";
  for (const m of list) {
    const div = document.createElement("div");
    div.className = "msg" + (m.error ? " error" : "");
    div.textContent = (m.error ? "错误：" : "提示：") + m.text;
    box.appendChild(div);
  }
}

/* ---------- 交互 ---------- */

function svgCoords(svg, e) {
  const ctm = svg.getScreenCTM();
  if (!ctm) return null;
  const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse());
  return { x: p.x, y: p.y };
}

$("foldedSvg").addEventListener("click", (e) => {
  if (!result) return;
  const pt = svgCoords($("foldedSvg"), e);
  if (!pt) return;
  const f = result.folded;
  // 点到已有孔附近则删除该孔，否则在折叠面内新增
  const tol = Math.max(f.w, f.h) * 0.03 + state.holeR;
  const idx = state.punches.findIndex(
    (p) => Math.hypot(p.x - pt.x, p.y - pt.y) <= Math.max(tol, state.holeR * 1.2)
  );
  if (idx >= 0) {
    state.punches.splice(idx, 1);
  } else {
    if (pt.x < f.x0 || pt.x > f.x1 || pt.y < f.y0 || pt.y > f.y1) return;
    state.punches.push({ x: round3(pt.x), y: round3(pt.y) });
  }
  compute();
});

document.querySelectorAll("[data-fold]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const [axis, side] = btn.dataset.fold.split(":");
    state.folds.push({ axis, side });
    compute();
  });
});

$("clearFolds").addEventListener("click", () => {
  state.folds = [];
  compute();
});

$("clearPunches").addEventListener("click", () => {
  state.punches = [];
  compute();
});

function bindNumber(id, apply) {
  $(id).addEventListener("input", () => {
    const v = parseFloat($(id).value);
    if (!Number.isFinite(v)) return;
    apply(v);
    scheduleCompute();
  });
}

bindNumber("paperW", (v) => { if (v > 0 && v <= 5000) state.paper.w = v; });
bindNumber("paperH", (v) => { if (v > 0 && v <= 5000) state.paper.h = v; });
bindNumber("holeR", (v) => { if (v > 0 && v <= 50) state.holeR = v; });

$("downloadBtn").addEventListener("click", async () => {
  let res;
  try {
    res = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload()),
    });
  } catch (e) {
    showMessages([{ text: "下载失败：" + e.message, error: true }]);
    return;
  }
  if (!res.ok) {
    showMessages([{ text: "下载失败，请检查参数", error: true }]);
    return;
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "unfolded.svg";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
});

/* ---------- 初始化：先算一次，再在折叠面中心放一个示例孔 ---------- */

compute().then(() => {
  if (result && state.punches.length === 0) {
    const f = result.folded;
    state.punches.push({ x: round3((f.x0 + f.x1) / 2), y: round3((f.y0 + f.y1) / 2) });
    compute();
  }
});
