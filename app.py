"""Flask 入口：页面、实时计算接口、展开 SVG 下载。"""
import math
import os

from flask import Flask, Response, jsonify, render_template, request

import folding

app = Flask(__name__)

MAX_FOLDS = 10       # 最多对折次数（2^10 = 1024 层）
MAX_PUNCHES = 64     # 最多打孔点数
MAX_DIM = 5000.0     # 纸张边长上限（mm）
DEFAULT_HOLE_R = 2.0


def _payload():
    """解析并校验请求体，返回 (w, h, folds, punches, hole_r)。"""
    data = request.get_json(force=True, silent=True)
    if not isinstance(data, dict):
        raise ValueError("请求体必须是 JSON 对象")

    paper = data.get("paper") or {}
    try:
        w = float(paper["w"])
        h = float(paper["h"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("纸张宽高必须是数字")
    if not (math.isfinite(w) and math.isfinite(h)) or not (0 < w <= MAX_DIM and 0 < h <= MAX_DIM):
        raise ValueError(f"纸张宽高需在 (0, {MAX_DIM:g}] mm 之间")

    folds = data.get("folds") or []
    if not isinstance(folds, list) or len(folds) > MAX_FOLDS:
        raise ValueError(f"对折次数最多 {MAX_FOLDS} 次")
    folds = [folding.validate_fold(f) for f in folds]

    punches = data.get("punches") or []
    if not isinstance(punches, list) or len(punches) > MAX_PUNCHES:
        raise ValueError(f"打孔点最多 {MAX_PUNCHES} 个")
    pts = []
    for p in punches:
        try:
            x, y = float(p["x"]), float(p["y"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("打孔点坐标必须是数字")
        if not (math.isfinite(x) and math.isfinite(y)):
            raise ValueError("打孔点坐标非法")
        pts.append((x, y))

    try:
        hole_r = float(data.get("hole_r") or DEFAULT_HOLE_R)
    except (TypeError, ValueError):
        hole_r = DEFAULT_HOLE_R
    hole_r = min(max(hole_r, 0.1), 50.0) if math.isfinite(hole_r) else DEFAULT_HOLE_R

    return w, h, folds, pts, hole_r


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify({"ok": True})


@app.post("/api/compute")
def api_compute():
    try:
        w, h, folds, punches, hole_r = _payload()
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    result = folding.compute_unfold(w, h, folds, punches)
    result["ok"] = True
    result["hole_r"] = hole_r
    return jsonify(result)


@app.post("/api/download")
def api_download():
    try:
        w, h, folds, punches, hole_r = _payload()
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    result = folding.compute_unfold(w, h, folds, punches)
    svg = folding.build_unfolded_svg(w, h, result, hole_r)
    return Response(
        svg,
        mimetype="image/svg+xml",
        headers={"Content-Disposition": "attachment; filename=unfolded.svg"},
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
