"""Tests for the skill's scripts. Run from the repo root: python -m unittest discover -s tests -v
gerber_check tests need numpy, Pillow and scipy (skipped otherwise); the rest is standard library."""
import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skills" / "pcb-layout-design" / "scripts"
DATA = Path(__file__).resolve().parent / "data"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixtures  # noqa: E402


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_script(name, *args):
    p = subprocess.run([sys.executable, str(SCRIPTS / name), *map(str, args)], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def call(mod, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = mod.main([str(a) for a in args])
    return rc, out.getvalue()


class PlacementCheck(unittest.TestCase):
    def test_bad_layout_reports_every_rule(self):
        rc, out = run_script("placement_check.py", DATA / "placement_bad.json")
        self.assertEqual(rc, 1)
        self.assertIn("SUMMARY ERROR 6, WARN 5", out)
        for kind in ("OVERLAP", "EDGE", "KEEPOUT", "FAR", "GRID", "ROT"):
            self.assertIn(kind, out)

    def test_help_does_not_need_a_file(self):
        rc, out = run_script("placement_check.py", "--help")
        self.assertEqual(rc, 0)
        self.assertIn("usage:", out)

    def test_good_layout_is_clean(self):
        rc, out = run_script("placement_check.py", DATA / "placement_good.json")
        self.assertEqual(rc, 0)
        self.assertIn("SUMMARY ERROR 0, WARN 0", out)

    def test_bundled_example_is_clean(self):
        rc, out = run_script("placement_check.py", ROOT / "skills" / "pcb-layout-design" / "assets" / "placement_example.json")
        self.assertEqual(rc, 0, out)


class PcbCalc(unittest.TestCase):
    def calc(self, *args):
        rc, out = run_script("pcbcalc.py", *args, "--json")
        self.assertEqual(rc, 0, out)
        return json.loads(out)

    def test_trace_width_5a_outer_1oz(self):
        d = self.calc("trace-width", "--current-a", "5")
        self.assertAlmostEqual(d["required_width_mm"], 2.78, delta=0.02)        # IPC-2221, 10 C rise

    def test_via_current(self):
        d = self.calc("via-current", "--hole-mm", "0.3", "--plating-um", "20")
        self.assertAlmostEqual(d["single_via_capacity_a"], 0.53, delta=0.02)

    def test_divider(self):
        d = self.calc("voltage-divider", "--vin", "24", "--r-top-ohm", "100000", "--r-bottom-ohm", "6800")
        self.assertAlmostEqual(d["vout_v"], 24 * 6.8 / 106.8, delta=0.01)


class PlacementFromKicad(unittest.TestCase):
    BOARD = """(kicad_pcb (version 20240108) (generator "pcbnew")
  (gr_rect (start 100 100) (end 130 120) (layer "Edge.Cuts") (stroke (width 0.1) (type default)))
  (footprint "Resistor_SMD:R_0402_1005Metric" (layer "F.Cu") (at 110 105 90)
    (property "Reference" "R1" (at 0 -1.17 90) (layer "F.SilkS"))
    (fp_rect (start -0.93 -0.47) (end 0.93 0.47) (layer "F.CrtYd") (stroke (width 0.05) (type solid)))
    (pad "1" smd roundrect (at -0.48 0 90) (size 0.56 0.62) (layers "F.Cu" "F.Paste" "F.Mask")))
  (footprint "Package_QFP:LQFP-48" (layer "F.Cu") (at 120 110)
    (property "Reference" "U1" (at 0 -6 0) (layer "F.SilkS"))
    (fp_line (start -5.15 -5.15) (end 5.15 -5.15) (layer "F.CrtYd") (stroke (width 0.05) (type solid)))
    (fp_line (start 5.15 -5.15) (end 5.15 5.15) (layer "F.CrtYd") (stroke (width 0.05) (type solid)))
    (fp_line (start 5.15 5.15) (end -5.15 5.15) (layer "F.CrtYd") (stroke (width 0.05) (type solid)))
    (fp_line (start -5.15 5.15) (end -5.15 -5.15) (layer "F.CrtYd") (stroke (width 0.05) (type solid))))
  (footprint "Capacitor_SMD:C_0603" (layer "B.Cu") (at 104 114 180)
    (fp_text reference "C7" (at 0 0) (layer "B.SilkS"))
    (pad "1" smd rect (at -0.775 0 180) (size 0.9 0.95) (layers "B.Cu"))
    (pad "2" smd rect (at 0.775 0 180) (size 0.9 0.95) (layers "B.Cu")))
  (footprint "Connector:USB_C" (layer "F.Cu") (at 101 110 45)
    (property "Reference" "J1" (at 0 0 0) (layer "F.SilkS"))
    (fp_rect (start -1 -2) (end 1 2) (layer "F.CrtYd")))
)"""

    def test_convert(self):
        mod = load("placement_from_kicad")
        data, notes = mod.convert(self.BOARD)
        b = data["board"]
        self.assertEqual((b["w"], b["h"], b["origin"]), (30.0, 20.0, [100.0, -120.0]))   # y up
        p = {x["ref"]: x for x in data["parts"]}
        self.assertEqual((p["R1"]["x"], p["R1"]["y"], p["R1"]["rot"], p["R1"]["class"]), (110.0, -105.0, 90, "passive"))
        self.assertAlmostEqual(p["R1"]["w"], 1.86, places=3)
        self.assertEqual((p["U1"]["w"], p["U1"]["class"]), (10.3, "ic"))
        self.assertEqual((p["C7"]["side"], p["C7"]["note"]), ("bottom", "pads+0.25"))     # no courtyard: pads + margin
        self.assertAlmostEqual(p["C7"]["w"], 2.45 + 0.5, places=3)
        self.assertEqual((p["J1"]["rot"], p["J1"]["class"]), (0, "connector"))
        self.assertTrue(any("J1" in n for n in notes))                                     # 45 deg -> bounding box

    def test_output_runs_through_the_checker(self):
        mod = load("placement_from_kicad")
        with tempfile.TemporaryDirectory() as t:
            src, out = Path(t) / "b.kicad_pcb", Path(t) / "p.json"
            src.write_text(self.BOARD)
            rc, _ = call(mod, src, "-o", out)
            self.assertEqual(rc, 0)
            rc, text = run_script("placement_check.py", out)
            self.assertIn("SUMMARY", text)


try:
    import numpy, PIL, scipy  # noqa: F401
    HAVE_RASTER = True
except ImportError:
    HAVE_RASTER = False


@unittest.skipUnless(HAVE_RASTER, "needs numpy, Pillow, scipy")
class GerberCheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gc = load("gerber_check")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.t = Path(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def board(self, name, **kw):
        return fixtures.write(self.t / name, **kw)

    def test_layers_are_recognised(self):
        for inch in (False, True):
            d, _ = self.board(f"layers{inch}", inch=inch)
            roles = self.gc.classify(self.gc.read_release(d))
            self.assertEqual([o for o, _ in roles["copper"]], [1, 99])
            for k in ("mask_top", "mask_bottom", "silk_top", "outline"):
                self.assertIn(k, roles)
            self.assertEqual(sorted(p for _, p in roles["drill"]), [False, True])

    def test_clean_board_metric_and_inch(self):
        for inch in (False, True):
            d, ipc = self.board(f"clean{inch}", inch=inch)
            rc, out = call(self.gc, "netcheck", d, "--ipc", ipc)
            self.assertEqual(rc, 0, out)
            self.assertIn("SUMMARY shorts 0, opens 0, pads without copper 0, undrilled 0", out)

    def test_short_is_found(self):
        d, ipc = self.board("short", short=True)
        rc, out = call(self.gc, "netcheck", d, "--ipc", ipc)
        self.assertEqual(rc, 1)
        self.assertIn("ERROR SHORT", out)
        self.assertIn("SUMMARY shorts 1, opens 0", out)

    def test_missing_via_is_an_open(self):
        d, ipc = self.board("open", via=False)
        rc, out = call(self.gc, "netcheck", d, "--ipc", ipc)
        self.assertEqual(rc, 1)
        self.assertIn("ERROR OPEN  A:", out)
        self.assertIn("NO_DRILL via (A) at (10.00, 10.00)", out)                # the cause, not only the symptom

    def test_mirrored_netlist_is_detected(self):
        d, ipc = self.board("mirror", inch=True, mirror_y=True)
        rc, out = call(self.gc, "netcheck", d, "--ipc", ipc)
        self.assertEqual(rc, 0, out)
        self.assertIn("mirrored", out)

    def test_render_reports_silk_on_pads_and_edge(self):
        d, _ = self.board("render")
        rc, out = call(self.gc, "render", d, "--out", self.t / "prev")
        self.assertEqual(rc, 0)
        self.assertTrue((self.t / "prev_top.png").exists() and (self.t / "prev_bottom.png").exists())
        silk = float(out.split("silk on mask openings ")[1].split(" mm2")[0])
        self.assertGreater(silk, 0.05)                         # the line across R1-1
        d2, _ = self.board("render_clean", silk_on_pad=False)
        _, out2 = call(self.gc, "render", d2, "--out", self.t / "prev2")
        self.assertIn("silk on mask openings 0.000 mm2", out2)
        self.assertIn("copper to board edge min 3.0", out2)    # nearest copper: the region edge at x = 3, outline at x = 0

    def test_diff_finds_only_the_change(self):
        a, _ = self.board("diff_a")
        b, _ = self.board("diff_b", short=True)
        rc, out = call(self.gc, "diff", a, b)
        self.assertEqual(rc, 1)
        self.assertIn("DIFF  copper L1: 0 only in A, 1 only in B (x 4.00..4.00, y 6.00..10.00)", out)
        self.assertIn("same  copper L99", out)
        rc, out = call(self.gc, "diff", a, a)
        self.assertEqual(rc, 0, out)

    def test_ipc_units(self):
        rows = self.gc.parse_ipc356(fixtures.ipc356(inch=True))
        r1 = [r for r in rows if r["ref"] == "R1" and r["pin"] == "1"][0]
        self.assertAlmostEqual(r1["x"], 4.0, delta=0.003)
        self.assertEqual([r["layer"] for r in rows if r["ref"] in ("VIA", "U1")], ["through", "bottom"])
        self.assertTrue(any(r["net"].startswith("N/C:") for r in rows))


class SkillLayout(unittest.TestCase):
    def test_frontmatter_follows_the_agent_skills_spec(self):
        skill = ROOT / "skills" / "pcb-layout-design" / "SKILL.md"
        text = skill.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        front = text.split("---\n")[1]
        keys = [ln.split(":")[0] for ln in front.splitlines() if ln and not ln.startswith(" ")]
        self.assertTrue(set(keys) <= {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}, keys)
        name = [ln for ln in front.splitlines() if ln.startswith("name:")][0].split(":", 1)[1].strip()
        self.assertEqual(name, skill.parent.name)
        desc = front.split("description:", 1)[1].split("\nlicense:")[0]
        self.assertLessEqual(len(" ".join(desc.split())), 1024)
        self.assertLess(len(text.splitlines()), 500)

    def test_every_referenced_file_exists(self):
        skill_dir = ROOT / "skills" / "pcb-layout-design"
        text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        import re
        for ref in set(re.findall(r"`((?:scripts|references|assets)/[\w./-]+)`", text)):
            self.assertTrue((skill_dir / ref).exists(), ref)


if __name__ == "__main__":
    unittest.main()
