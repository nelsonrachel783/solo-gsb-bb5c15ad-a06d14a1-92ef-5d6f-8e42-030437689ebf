"""几何核心 folding.py 的单元测试：python3 -m unittest test_folding -v"""
import unittest

import folding


def hole_xy(result):
    return sorted((h["x"], h["y"]) for h in result["holes"])


class UnfoldTest(unittest.TestCase):
    def test_single_vertical_fold(self):
        # 200x100，左折向右，折线 x=100，折叠面为 [100,200]x[0,100]
        r = folding.compute_unfold(200, 100, [{"axis": "v", "side": "left"}], [(150.0, 50.0)])
        self.assertEqual(r["folded"]["x0"], 100)
        self.assertEqual(r["layers"], 2)
        self.assertEqual(hole_xy(r), [(50.0, 50.0), (150.0, 50.0)])
        self.assertEqual(len(r["creases"]), 1)
        self.assertEqual(r["creases"][0]["x1"], 100)
        self.assertEqual(r["warnings"], [])

    def test_side_right_keeps_left_half(self):
        r = folding.compute_unfold(200, 100, [{"axis": "v", "side": "right"}], [(50.0, 50.0)])
        self.assertEqual(r["folded"]["x1"], 100)
        self.assertEqual(hole_xy(r), [(50.0, 50.0), (150.0, 50.0)])

    def test_two_perpendicular_folds_four_holes(self):
        folds = [{"axis": "v", "side": "left"}, {"axis": "h", "side": "top"}]
        r = folding.compute_unfold(200, 100, folds, [(175.0, 75.0)])
        self.assertEqual(r["layers"], 4)
        self.assertEqual(len(r["holes"]), 4)
        # 折痕：x=100 一条竖线 + y=50 一条横线（合并后共 2 条）
        self.assertEqual(len(r["creases"]), 2)

    def test_double_vertical_crease_grid(self):
        # 连续两次左折向右：折痕应出现在 x = 50, 100, 150
        folds = [{"axis": "v", "side": "left"}, {"axis": "v", "side": "left"}]
        r = folding.compute_unfold(200, 100, folds, [(190.0, 50.0)])
        xs = sorted(c["x1"] for c in r["creases"])
        self.assertEqual(xs, [50, 100, 150])
        self.assertEqual(len(r["holes"]), 4)
        self.assertEqual(hole_xy(r), [(10.0, 50.0), (90.0, 50.0), (110.0, 50.0), (190.0, 50.0)])

    def test_punch_on_fold_edge_warns_and_dedupes(self):
        # 打孔点正好压在折痕边上：展开后两孔重合，只画一次并给出提示
        r = folding.compute_unfold(200, 100, [{"axis": "v", "side": "left"}], [(100.0, 50.0)])
        self.assertEqual(len(r["holes"]), 1)
        self.assertEqual(r["hole_count_total"], 2)
        self.assertTrue(any("折痕边" in w for w in r["warnings"]))

    def test_punch_on_paper_edge_warns(self):
        r = folding.compute_unfold(200, 100, [], [(0.0, 50.0)])
        self.assertTrue(any("边界" in w or "边缘" in w for w in r["warnings"]))

    def test_punch_outside_folded_face_ignored(self):
        r = folding.compute_unfold(200, 100, [{"axis": "v", "side": "left"}], [(10.0, 50.0)])
        self.assertEqual(len(r["holes"]), 0)
        self.assertTrue(any("不在折叠面范围内" in w for w in r["warnings"]))

    def test_coincident_holes_across_punches_merged(self):
        # 两个打孔点展开后产生重合位置，只保留一个
        folds = [{"axis": "v", "side": "left"}]
        r = folding.compute_unfold(200, 100, folds, [(150.0, 50.0), (150.0, 50.0)])
        self.assertEqual(r["hole_count_total"], 4)
        self.assertEqual(r["hole_count_unique"], 2)

    def test_horizontal_fold_bottom_to_top(self):
        r = folding.compute_unfold(100, 200, [{"axis": "h", "side": "bottom"}], [(50.0, 50.0)])
        self.assertEqual(r["folded"]["y1"], 100)
        self.assertEqual(hole_xy(r), [(50.0, 50.0), (50.0, 150.0)])

    def test_svg_export_contains_holes(self):
        r = folding.compute_unfold(200, 100, [{"axis": "v", "side": "left"}], [(150.0, 50.0)])
        svg = folding.build_unfolded_svg(200, 100, r, 2.0)
        self.assertIn("<svg", svg)
        self.assertEqual(svg.count("<circle"), 2)
        self.assertIn('width="200mm"', svg)

    def test_invalid_fold_rejected(self):
        with self.assertRaises(ValueError):
            folding.validate_fold({"axis": "v", "side": "top"})
        with self.assertRaises(ValueError):
            folding.validate_fold({"axis": "x", "side": "left"})


if __name__ == "__main__":
    unittest.main()
