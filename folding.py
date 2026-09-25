"""纸张对折-打孔-展开的几何核心。

坐标系约定：始终以原纸为坐标系，原点在纸张左上角，x 向右，y 向下。
每次对折只让当前折叠面（一个矩形）的一半反射到另一半，坐标系本身不移动，
因此折叠面始终是原纸坐标系中的一个子矩形，折叠线/打孔点/折痕全部用原纸坐标表示。

对折记录 fold = {"axis": "v"|"h", "side": ...}：
  axis="v"  沿垂直中线对折，side="left" 表示左侧折向右侧，"right" 反之；
  axis="h"  沿水平中线对折，side="top"  表示上侧折向下侧，"bottom" 反之。
"""
from __future__ import annotations

EPS = 1e-9
# 孔心距折痕/边界小于该值（mm）即视为“落在上面或过近”，提示用户调整
WARN_TOL = 0.5

AXES = {"v": ("left", "right"), "h": ("top", "bottom")}


def validate_fold(fold):
    """校验并规范化一条对折指令，非法时抛 ValueError。"""
    if not isinstance(fold, dict):
        raise ValueError("对折参数必须是对象")
    axis = fold.get("axis")
    side = fold.get("side")
    if axis not in AXES or side not in AXES[axis]:
        raise ValueError(f"非法对折参数: axis={axis!r} side={side!r}")
    return {"axis": axis, "side": side}


def _fold_line(rect, fold):
    """当前矩形内该次对折的折线：(方向, 线坐标, 段起点, 段终点)。"""
    x0, y0, x1, y1 = rect
    if fold["axis"] == "v":
        c = (x0 + x1) / 2.0
        return ("v", c, y0, y1)
    c = (y0 + y1) / 2.0
    return ("h", c, x0, x1)


def _apply_fold(rect, fold):
    """对折后折叠面占据的矩形（保持不动的那一半）。"""
    x0, y0, x1, y1 = rect
    if fold["axis"] == "v":
        c = (x0 + x1) / 2.0
        return (c, y0, x1, y1) if fold["side"] == "left" else (x0, y0, c, y1)
    c = (y0 + y1) / 2.0
    return (x0, c, x1, y1) if fold["side"] == "top" else (x0, y0, x1, c)


def _reflect_pt(p, line):
    o, c, _, _ = line
    x, y = p
    return (2.0 * c - x, y) if o == "v" else (x, 2.0 * c - y)


def _reflect_seg(seg, line):
    o, c, _, _ = line
    so, a, lo, hi = seg
    if so == o:  # 与镜面平行：平移坐标被反射
        return (so, 2.0 * c - a, lo, hi)
    # 与镜面垂直：区间被反射
    nlo, nhi = 2.0 * c - hi, 2.0 * c - lo
    return (so, a, min(nlo, nhi), max(nlo, nhi))


def _merge_segs(segs):
    """合并同一直线上相接/重叠的段，让折痕渲染更干净。"""
    groups = {}
    for o, a, lo, hi in segs:
        groups.setdefault((o, round(a, 9)), []).append((lo, hi))
    out = []
    for (o, a), ivs in groups.items():
        ivs.sort()
        clo, chi = ivs[0]
        for lo, hi in ivs[1:]:
            if lo <= chi + 1e-9:
                chi = max(chi, hi)
            else:
                out.append((o, a, clo, chi))
                clo, chi = lo, hi
        out.append((o, a, clo, chi))
    return out


def _dedupe_pts(pts):
    seen = {}
    for x, y in pts:
        seen[(round(x, 9), round(y, 9))] = (x, y)
    return list(seen.values())


def _edge_kind(o, at, lines):
    """折叠面的某条边是折痕边还是纸张原始边缘。"""
    for lo, a, _, _ in lines:
        if lo == o and abs(a - at) < 1e-6:
            return "折痕边"
    return "纸张边缘"


def _r6(v):
    return round(float(v), 6)


def compute_unfold(paper_w, paper_h, folds, punches, warn_tol=WARN_TOL):
    """核心计算。

    参数：纸张宽高、对折序列、打孔点列表 [(x, y), ...]（折叠面/原纸坐标系）。
    返回 JSON 友好的 dict：折叠面矩形、层数、折痕、去重后的全部孔位、警告列表。
    """
    paper_w = float(paper_w)
    paper_h = float(paper_h)

    rects = [(0.0, 0.0, paper_w, paper_h)]
    lines = []
    for f in folds:
        lines.append(_fold_line(rects[-1], f))
        rects.append(_apply_fold(rects[-1], f))
    folded = rects[-1]

    # 折痕：第 i 折的折线存在于当时纸叠的每一层上，
    # 因此把它按第 i 折之前的各折逆序展开反射，得到原纸上的全部折痕。
    crease_segs = []
    for i, seg in enumerate(lines):
        segs = [seg]
        for j in range(i - 1, -1, -1):
            segs += [_reflect_seg(s, lines[j]) for s in segs]
        crease_segs.extend(segs)
    crease_segs = _merge_segs(crease_segs)

    fx0, fy0, fx1, fy1 = folded
    warnings = []
    valid = []
    for idx, (x, y) in enumerate(punches):
        if not (fx0 - EPS <= x <= fx1 + EPS and fy0 - EPS <= y <= fy1 + EPS):
            warnings.append(
                f"第 {idx + 1} 个打孔点 ({x:.1f}, {y:.1f}) 不在折叠面范围内，已忽略，请调整。"
            )
            continue
        valid.append((x, y))
        # 距折叠面四条边（折痕边或纸边）过近时结果会重合/残缺，必须提示
        cands = [
            (x - fx0, "v", fx0), (fx1 - x, "v", fx1),
            (y - fy0, "h", fy0), (fy1 - y, "h", fy1),
        ]
        d, o, at = min(cands, key=lambda t: t[0])
        if d < warn_tol:
            kind = _edge_kind(o, at, lines)
            warnings.append(
                f"第 {idx + 1} 个打孔点 ({x:.1f}, {y:.1f}) 落在折叠面的{kind}上或距离过近，"
                "展开后孔会重合或残缺，请调整位置。"
            )

    # 打孔逆推：按折叠顺序的逆序，每展开一折，所有已有点对镜反射出另一半
    holes = []
    for p in valid:
        pts = [p]
        for j in range(len(lines) - 1, -1, -1):
            pts += [_reflect_pt(q, lines[j]) for q in pts]
        holes.extend(pts)
    total = len(holes)
    holes = _dedupe_pts(holes)  # 重合位置只画一次

    # 展开结果落在折痕或纸张边界上/过近时提示调整
    for hx, hy in holes:
        if min(hx, paper_w - hx, hy, paper_h - hy) < warn_tol:
            warnings.append(
                f"展开孔 ({hx:.1f}, {hy:.1f}) 落在纸张边界上或距离过近，请调整打孔位置。"
            )
            continue
        for o, a, lo, hi in crease_segs:
            on = (
                (o == "v" and abs(hx - a) < warn_tol and lo - warn_tol <= hy <= hi + warn_tol)
                or (o == "h" and abs(hy - a) < warn_tol and lo - warn_tol <= hx <= hi + warn_tol)
            )
            if on:
                warnings.append(
                    f"展开孔 ({hx:.1f}, {hy:.1f}) 落在折痕上或距离过近，请调整打孔位置。"
                )
                break

    warnings = list(dict.fromkeys(warnings))  # 去重保序

    creases = []
    for o, a, lo, hi in crease_segs:
        if o == "v":
            creases.append({"x1": _r6(a), "y1": _r6(lo), "x2": _r6(a), "y2": _r6(hi)})
        else:
            creases.append({"x1": _r6(lo), "y1": _r6(a), "x2": _r6(hi), "y2": _r6(a)})

    return {
        "folded": {
            "x0": _r6(fx0), "y0": _r6(fy0), "x1": _r6(fx1), "y1": _r6(fy1),
            "w": _r6(fx1 - fx0), "h": _r6(fy1 - fy0),
        },
        "layers": 1 << len(folds),
        "fold_edges": [{"orientation": o, "at": _r6(a)} for o, a, _, _ in lines],
        "creases": creases,
        "holes": [{"x": _r6(x), "y": _r6(y)} for x, y in holes],
        "hole_count_total": total,
        "hole_count_unique": len(holes),
        "warnings": warnings,
    }


def build_unfolded_svg(paper_w, paper_h, result, hole_r):
    """根据计算结果生成可下载的展开图 SVG 文件内容。"""
    def n(v):
        s = f"{float(v):.3f}".rstrip("0").rstrip(".")
        return s if s not in ("", "-0") else "0"

    w, h = float(paper_w), float(paper_h)
    m = max(w, h) * 0.06 + hole_r * 2
    sw = max(w, h) / 500.0
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{n(w)}mm" height="{n(h)}mm" '
        f'viewBox="{n(-m)} {n(-m)} {n(w + 2 * m)} {n(h + 2 * m)}">',
        f"<title>纸张展开图 {n(w)} × {n(h)} mm，{result['hole_count_unique']} 个孔</title>",
        f'<rect x="0" y="0" width="{n(w)}" height="{n(h)}" fill="#ffffff" '
        f'stroke="#1f2329" stroke-width="{n(sw)}"/>',
    ]
    for c in result["creases"]:
        parts.append(
            f'<line x1="{n(c["x1"])}" y1="{n(c["y1"])}" x2="{n(c["x2"])}" y2="{n(c["y2"])}" '
            f'stroke="#2563eb" stroke-width="{n(sw * 0.6)}" '
            f'stroke-dasharray="{n(sw * 3)},{n(sw * 2)}"/>'
        )
    for p in result["holes"]:
        parts.append(
            f'<circle cx="{n(p["x"])}" cy="{n(p["y"])}" r="{n(hole_r)}" '
            f'fill="#dc2626" fill-opacity="0.85" stroke="#7f1d1d" stroke-width="{n(sw * 0.5)}"/>'
        )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"
