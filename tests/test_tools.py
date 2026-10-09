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
        self.assertIn("SUMMARY ERROR 6, WARN 6", out)
        for kind in ("OVERLAP", "EDGE", "KEEPOUT", "FAR", "GRID", "ROT"):
            self.assertIn(kind, out)
        self.assertIn("WARN  EDGE U1 side 2.25 mm from the edge", out)          # module neither at the edge nor clear

    def test_help_does_not_need_a_file(self):
        rc, out = run_script("placement_check.py", "--help")
        self.assertEqual(rc, 0)
        self.assertIn("usage:", out)

    def test_good_layout_is_clean(self):
        rc, out = run_script("placement_check.py", DATA / "placement_good.json")
        self.assertEqual(rc, 0)
        self.assertIn("SUMMARY ERROR 0, WARN 0", out)

    def test_occupancy_is_on_usable_area(self):
        _, out = run_script("placement_check.py", DATA / "placement_bad.json")
        # 40 x 30 board, 2.5 mm edge band, 18 x 3.5 mm of the antenna keep-out inside it -> about 65 %, "dense"
        self.assertIn("top occupancy 65% of usable area (dense; 45% of the whole board", out)

    def check(self, parts, **board):
        mod = load("placement_check")
        d = {"board": {"w": 40, "h": 30, "edge_clearance": 2.5, "grid": 0.25, **board}, "parts": parts}
        errs, warns, *_ = mod.check(d)
        return errs, warns, mod

    def test_rotated_part_uses_the_rotated_box(self):
        mod = load("placement_check")
        x1, y1, x2, y2 = mod.rect({"x": 10, "y": 10, "w": 2.1, "h": 1.3, "rot": 45})
        self.assertAlmostEqual(x2 - x1, 3.4 / 2 ** 0.5, places=6)           # (2.1 + 1.3) cos 45
        errs, _, _ = self.check([{"ref": "R1", "x": 10, "y": 10, "w": 2.1, "h": 1.3, "rot": 45, "class": "passive"},
                                 {"ref": "R2", "x": 11.4, "y": 10, "w": 0.5, "h": 0.5, "class": "passive"}])
        self.assertTrue(any(e.startswith("OVERLAP R1-R2") for e in errs), errs)   # missed with the 0 deg box

    def test_edge_parts_reach_the_edge_or_keep_the_band(self):
        mod_part = {"ref": "U1", "w": 18, "h": 10, "class": "module"}
        _, warns, _ = self.check([dict(mod_part, x=31, y=25)])                 # flush right + top
        self.assertEqual(warns, [])
        _, warns, _ = self.check([dict(mod_part, x=30.5, y=25)])               # top flush, right side 0.5 mm in
        self.assertTrue(any("EDGE U1 side 0.50 mm" in w for w in warns), warns)
        errs, warns, _ = self.check([dict(mod_part, x=20, y=15)])               # well inside: fine
        self.assertEqual((errs, warns), ([], []))
        _, warns, _ = self.check([{"ref": "H1", "x": 3, "y": 3, "w": 5, "h": 5, "class": "mech"}])
        self.assertEqual(warns, [])                                             # holes keep their exemption

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

    def test_microstrip_closed_form(self):
        base = ("diff-microstrip", "--width-mm", "0.29", "--spacing-mm", "0.2", "--height-mm", "0.2104", "--er", "4.4",
                "--model", "closed")
        thin = self.calc(*base, "--copper-um", "0")
        self.assertAlmostEqual(thin["zdiff_ohm"], 97.3, delta=0.1)            # v1.1.0 zero-thickness value
        thick = self.calc(*base)
        self.assertLess(thick["zdiff_ohm"], thin["zdiff_ohm"] - 3)             # 35 um copper lowers it
        self.assertIn("thickness correction", thick["model"])

    @unittest.skipUnless(load("pcbcalc").have_field_solver(), "needs numpy and scipy")
    def test_microstrip_field_solver(self):
        se = self.calc("microstrip", "--width-mm", "0.4", "--height-mm", "0.2104", "--er", "4.4", "--copper-um", "0",
                       "--mask-um", "0")
        self.assertEqual(se["model"], "2D field solver")
        self.assertAlmostEqual(se["z0_ohm"], 50.2, delta=0.5)                 # Hammerstad-Jensen 50.21
        d = self.calc("diff-microstrip", "--target-ohm", "90", "--spacing-mm", "0.2", "--height-mm", "0.2104",
                      "--er", "4.4")
        self.assertAlmostEqual(d["zdiff_ohm"], 90, delta=0.3)
        self.assertAlmostEqual(d["width_mm"], 0.288, delta=0.01)              # 35 um copper, 20 um mask

    def test_closed_form_value_and_keys(self):
        d = self.calc("microstrip", "--width-mm", "0.36", "--height-mm", "0.2104", "--er", "4.4", "--model", "closed")
        self.assertAlmostEqual(d["z0_ohm"], 50.93, delta=0.05)                # Hammerstad-Jensen, 35 um copper
        self.assertFalse(d["inputs"]["mask_modelled"])
        p = self.calc("diff-microstrip", "--width-mm", "0.29", "--spacing-mm", "0.2", "--height-mm", "0.2104", "--er",
                      "4.4", "--model", "closed")
        self.assertEqual(set(p) >= {"zdiff_ohm", "z_odd_ohm", "z_common_ohm", "e_eff", "delay_ps_per_mm"}, True)

    def test_impedance_rejects_bad_inputs(self):
        for bad in (("--height-mm", "-0.2"), ("--height-mm", "nan"), ("--er", "0.5"), ("--mask-er", "0")):
            args = {"--width-mm": "0.3", "--spacing-mm": "0.2", "--height-mm": "0.2104", "--er": "4.4"}
            args[bad[0]] = bad[1]
            rc, out = run_script("pcbcalc.py", "diff-microstrip", *[x for kv in args.items() for x in kv], "--json")
            self.assertEqual(rc, 2, (bad, out))

    def test_auto_model_names_what_it_used(self):
        d = self.calc("microstrip", "--width-mm", "0.36", "--height-mm", "0.2104", "--er", "4.4")
        self.assertEqual(d["model"] == "2D field solver", load("pcbcalc").have_field_solver())

    @unittest.skipUnless(load("pcbcalc").have_field_solver(), "needs numpy and scipy")
    def test_field_solver_physics(self):
        base = ("--height-mm", "0.2104", "--er", "4.4")
        bare = self.calc("microstrip", "--width-mm", "0.36", *base, "--mask-um", "0")
        coated = self.calc("microstrip", "--width-mm", "0.36", *base)
        self.assertLess(coated["z0_ohm"], bare["z0_ohm"] - 1)                  # mask lowers the impedance
        self.assertTrue(coated["inputs"]["mask_modelled"])
        wide = self.calc("diff-microstrip", "--width-mm", "0.36", "--spacing-mm", "5", *base)
        self.assertAlmostEqual(wide["zdiff_ohm"], 2 * coated["z0_ohm"], delta=0.02 * wide["zdiff_ohm"])
        self.assertGreater(wide["z_common_ohm"], 0)
        thick = self.calc("microstrip", "--target-ohm", "50", "--height-mm", "1.5", "--er", "4.5")   # 2-layer core
        self.assertAlmostEqual(thick["z0_ohm"], 50, delta=0.3)

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
        self.assertEqual((p["J1"]["rot"], p["J1"]["rot_actual"], p["J1"]["class"]), (0, 45.0, "connector"))
        self.assertTrue(any("J1" in n for n in notes))                                     # 45 deg -> bounding box
        self.assertNotIn("rot_actual", p["R1"])

    def test_repeated_references_get_unique_names(self):
        fp = '(footprint "R" (layer "F.Cu") (at {x} 105) (fp_text reference "REF**" (at 0 0) (layer "F.SilkS"))' \
             '(fp_rect (start -1 -1) (end 1 1) (layer "F.CrtYd")))'
        data, notes = load("placement_from_kicad").convert("(kicad_pcb " + fp.format(x=1) + fp.format(x=5) + fp.format(x=9) + ")")
        self.assertEqual([p["ref"] for p in data["parts"]], ["REF**", "REF**#2", "REF**#3"])
        self.assertEqual(sum("repeated reference" in n for n in notes), 2)

    def test_output_runs_through_the_checker(self):
        mod = load("placement_from_kicad")
        with tempfile.TemporaryDirectory() as t:
            src, out = Path(t) / "b.kicad_pcb", Path(t) / "p.json"
            src.write_text(self.BOARD)
            rc, _ = call(mod, src, "-o", out)
            self.assertEqual(rc, 0)
            rc, text = run_script("placement_check.py", out)
            self.assertIn("SUMMARY", text)


class BaselineDiff(unittest.TestCase):
    BASE = {"board": {"w": 42, "h": 42, "origin": [-21, -21]},
            "keepouts": [{"name": "antenna", "rect": [10, 10, 20, 20], "allow": ["U2"]}],
            "parts": [{"ref": "J1", "x": 0, "y": -17.25, "w": 10, "h": 8, "rot": 0, "class": "connector", "locked": True},
                      {"ref": "H1", "x": -15.5, "y": -15.5, "w": 6, "h": 6, "class": "mech", "locked": True},
                      {"ref": "U1", "x": -4.5, "y": 5.5, "w": 9, "h": 9, "rot": 270, "class": "ic", "locked": True},
                      {"ref": "J2", "x": 15, "y": 0, "w": 6, "h": 4, "class": "connector"},
                      {"ref": "R1", "x": 1, "y": 1, "w": 1.6, "h": 0.8, "class": "passive"}]}

    def run_pair(self, change, *args, base=None):
        base = base or self.BASE
        cur = json.loads(json.dumps(base))
        change(cur)
        with tempfile.TemporaryDirectory() as t:
            b, c = Path(t) / "b.json", Path(t) / "c.json"
            b.write_text(json.dumps(base)); c.write_text(json.dumps(cur))
            return call(load("baseline_diff"), b, c, *args)

    def test_unchanged(self):
        rc, out = self.run_pair(lambda d: None)
        self.assertEqual(rc, 0)
        self.assertIn("SUMMARY baseline changes 0", out)

    def test_unlocked_parts_are_only_counted(self):
        def change(d):
            d["parts"][3]["x"] = 16                             # unlocked connector
            d["parts"][4]["x"] = 3                              # passive
            d["parts"].append({"ref": "C9", "x": 0, "y": 0, "w": 1, "h": 1})
        rc, out = self.run_pair(change)
        self.assertEqual(rc, 0)
        self.assertIn("INFO  3 other change(s)", out)
        rc, out = self.run_pair(change, "--list-others")
        self.assertIn("MOVED J2", out)
        self.assertIn("1 part(s) not in the baseline: C9", out)
        rc, out = self.run_pair(change, "--classes", "connector")
        self.assertEqual(rc, 1)
        self.assertIn("ERROR MOVED J2", out)

    def test_locked_parts_are_watched(self):
        def change(d):
            d["parts"][0]["x"] += 0.2                           # connector moved
            d["parts"][1]["side"] = "bottom"                    # mounting hole flipped
            d["parts"][2]["rot"] = 0                            # IC turned
        rc, out = self.run_pair(change)
        self.assertEqual(rc, 1)
        for m in ("MOVED J1 by (+0.200, +0.000)", "SIDE H1 top -> bottom", "ROTATED U1 270 -> 0", "SUMMARY baseline changes 3"):
            self.assertIn(m, out)

    def test_removed_part_outline_and_tolerance(self):
        def change(d):
            del d["parts"][0]
            d["board"]["w"] = 42.5
            d["parts"][1]["x"] += 0.005                          # U1, inside the 0.01 mm tolerance
            d["parts"][1]["rot"] = -90                           # same as 270
        rc, out = self.run_pair(change)
        self.assertEqual(rc, 1)
        self.assertIn("REMOVED J1", out)
        self.assertIn("OUTLINE w 42 -> 42.5", out)
        self.assertNotIn("U1", out)
        rc, out = self.run_pair(lambda d: d.pop("board"))
        self.assertIn("OUTLINE board missing", out)

    def test_size_and_keepouts(self):
        def change(d):
            d["parts"][0]["w"] = 11                              # footprint update resized J1
            d["keepouts"][0]["allow"].append("C3")              # keep-out loosened
            d["keepouts"].append({"name": "screw", "circle": [0, 0, 3]})
        rc, out = self.run_pair(change, "--list-others")
        self.assertEqual(rc, 1)
        self.assertIn("SIZE J1 10 x 8 -> 11 x 8 mm", out)
        self.assertIn("ERROR KEEPOUT antenna now allows C3", out)
        self.assertIn("INFO  KEEPOUT screw added", out)
        rc, out = self.run_pair(lambda d: d["keepouts"].clear())
        self.assertIn("ERROR KEEPOUT antenna removed", out)

    def test_rot_actual_is_compared(self):
        base = json.loads(json.dumps(self.BASE))
        base["parts"][2].update(rot=0, rot_actual=45.0)
        rc, out = self.run_pair(lambda d: d["parts"][2].update(rot_actual=30.0), base=base)
        self.assertEqual(rc, 1)
        self.assertIn("ROTATED U1 45 -> 30", out)

    def test_nothing_watched_is_not_a_pass(self):
        base = json.loads(json.dumps(self.BASE))
        for p in base["parts"]:
            p.pop("locked", None)
        with contextlib.redirect_stderr(io.StringIO()) as err:
            rc, _ = self.run_pair(lambda d: None, base=base)
        self.assertEqual(rc, 2)
        self.assertIn("nothing to watch", err.getvalue())
        rc, out = self.run_pair(lambda d: None, "--classes", "connector", base=base)
        self.assertEqual(rc, 0)
        self.assertIn("SUMMARY baseline changes 0 (2 watched part(s), 1 keep-out(s))", out)

    def test_refs_and_all(self):
        rc, out = self.run_pair(lambda d: d["parts"][4].update(x=3), "--refs", " R1 , X9")
        self.assertEqual(rc, 1)
        self.assertIn("ERROR MOVED R1", out)
        rc, _ = self.run_pair(lambda d: d["parts"][4].update(x=3), "--all")
        self.assertEqual(rc, 1)

    def test_unusable_input_exits_2(self):
        for change in (lambda d: d["parts"].append(dict(d["parts"][4])),       # duplicate ref
                       lambda d: d["parts"][4].update(x="1.0"),               # string number
                       lambda d: d["parts"][4].update(locked="yes"),
                       lambda d: d["keepouts"][0].update(allow=None),
                       lambda d: d["keepouts"][0].update(rect=[0, 0, 1])):
            with self.assertRaises(SystemExit) as e, contextlib.redirect_stderr(io.StringIO()):
                self.run_pair(change)
            self.assertEqual(e.exception.code, 2)


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
