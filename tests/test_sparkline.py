import json
import subprocess
import unittest
from pathlib import Path


STUB = """
const __made = [];
const document = { createElementNS: (ns, tag) => {
  const el = { tag, ns, attrs: {}, children: [],
    setAttribute(k, v) { this.attrs[k] = v; },
    append(...kids) { this.children.push(...kids); } };
  __made.push(el);
  return el;
} };
"""


class SparklineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path("docs/app.js").read_text(encoding="utf-8")
        cls.source = source[:source.index("function renderCandidates")]

    def run_node(self, expression):
        script = self.source + STUB + "\nprocess.stdout.write(JSON.stringify(" + expression + "));"
        result = subprocess.run(
            ["node", "-e", script], check=True, capture_output=True, text=True
        )
        return json.loads(result.stdout)

    def test_flat_history_is_flat_line(self):
        geometry = self.run_node("sparklineGeometry([5, 5, 5, 5])")
        self.assertEqual(geometry["trend"], "flat")
        self.assertEqual(len(geometry["segments"]), 1)
        self.assertEqual(len(geometry["segments"][0]), 4)
        ys = {point.split(",")[1] for point in geometry["segments"][0]}
        self.assertEqual(len(ys), 1)

    def test_rising_ranks_trend_up_and_climb(self):
        geometry = self.run_node("sparklineGeometry([30, 20, 10, 5])")
        self.assertEqual(geometry["trend"], "up")
        points = geometry["segments"][0]
        first_y = float(points[0].split(",")[1])
        last_y = float(points[-1].split(",")[1])
        self.assertLess(last_y, first_y)
        self.assertEqual(geometry["first"], 30)
        self.assertEqual(geometry["last"], 5)

    def test_falling_ranks_trend_down(self):
        geometry = self.run_node("sparklineGeometry([2, 10, 25])")
        self.assertEqual(geometry["trend"], "down")

    def test_rank_one_maps_to_top_and_max_to_bottom(self):
        geometry = self.run_node("sparklineGeometry([1, 50, 100])")
        points = geometry["segments"][0]
        self.assertEqual(points[0].split(",")[1], "2")
        self.assertEqual(points[-1].split(",")[1], "20")
        xs = [float(point.split(",")[0]) for point in points]
        self.assertEqual(xs[0], 2)
        self.assertEqual(xs[-1], 74)

    def test_nulls_split_segments_and_lone_points_dropped(self):
        geometry = self.run_node("sparklineGeometry([1, null, 5, 6])")
        self.assertEqual(len(geometry["segments"]), 1)
        self.assertEqual(len(geometry["segments"][0]), 2)
        self.assertEqual(geometry["trend"], "down")

    def test_too_few_valid_points_returns_null(self):
        for history in ([], [None, None], [7], [None, 3, None]):
            self.assertIsNone(self.run_node("sparklineGeometry(" + json.dumps(history) + ")"))

    def test_create_sparkline_builds_svg_with_aria_label(self):
        svg = self.run_node(
            "(() => { const s = createSparkline([30, 20, 10, 5]);"
            " return { tag: s.tag, attrs: s.attrs,"
            " lines: s.children.map(c => c.attrs.points) }; })()"
        )
        self.assertEqual(svg["tag"], "svg")
        self.assertEqual(svg["attrs"]["class"], "rank-sparkline trend-up")
        self.assertEqual(svg["attrs"]["role"], "img")
        self.assertIn("30位 → 5位", svg["attrs"]["aria-label"])
        self.assertEqual(len(svg["lines"]), 1)
        self.assertEqual(len(svg["lines"][0].split(" ")), 4)

    def test_create_sparkline_returns_null_without_history(self):
        self.assertIsNone(self.run_node("createSparkline([null])"))

    def test_render_items_wires_sparkline_and_styles_exist(self):
        app = Path("docs/app.js").read_text(encoding="utf-8")
        self.assertIn("createSparkline(insight.rank_history)", app)
        style = Path("docs/style.css").read_text(encoding="utf-8")
        self.assertIn(".rank-sparkline", style)
        self.assertIn("trend-up", style)
        page = Path("docs/index.html").read_text(encoding="utf-8")
        self.assertIn("RANK SPARKLINE", page)


if __name__ == "__main__":
    unittest.main()
