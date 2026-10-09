# KiCad with this skill (pcb-layout-design)

Menu names are from KiCad 7-9; older versions differ slightly.

## Placement in, placement out
- `python scripts/placement_from_kicad.py board.kicad_pcb -o placement.json` reads footprints (`footprint` and the
  older `module` form), their courtyards (`F.CrtYd` / `B.CrtYd`), sides and rotations, and the `Edge.Cuts` extent.
  Footprints without a courtyard get pads + 0.25 mm (0.15 mm for 0402 / 0603 sizes) and a `note`.
- KiCad's y axis points down; the placement JSON uses y up (y_json = -y_kicad).
- Applying a checked placement back to KiCad is manual in this version. The JSON holds **courtyard centres**, not
  footprint origins: for parts whose courtyard is centred on the origin (most passives and ICs) set the position to
  (x, -y) and the rotation; for connectors and other off-centre footprints move the part until its courtyard centre
  lands there, then re-import and run `placement_check.py` and `baseline_diff.py` again.
- Rotations that are not multiples of 90 deg come out as an axis-aligned bounding box with `rot` 0, the real angle in
  `rot_actual` (compared by `baseline_diff.py`) and a note. Repeated references (`REF**`) become `REF**#2`, ...
- Classes are guessed from the reference prefix (U ic/module, Q/K/F and large L/C power, J/P connector, H/MH/TP/FID
  mech, rest passive): correct them, then add zones, keep-outs and near / apart pairs (SKILL.md section 5).

## The project's rule set
- File -> Board Setup -> Design Rules holds the clearances, net classes (width, via size, pair gap) and custom rules;
  Inspect -> Constraints Resolution shows which rule applies to one selected item. Read both before placing and
  compare them with the fab's capability and `pcbcalc.py` results.

## Fabrication files for gerber_check.py
- Gerbers: File -> Fabrication Outputs -> Gerbers. Keep "Use Protel filename extensions" off or on - both are
  recognised; X2 attributes (`%TF.FileFunction%`) are used when present.
- Drill: same dialog, "Generate Drill Files", Excellon, separate PTH and NPTH files (the names contain `PTH` /
  `NPTH`, which the checker uses to tell plated from non-plated).
- Netlist: File -> Fabrication Outputs -> IPC-D-356 Netlist File.
- Use the same origin for all three (absolute or the drill / place file origin). If `netcheck` reports most pads
  without copper, the netlist and the Gerbers use different origins: pass `--offset dx,dy` (mm). A mirrored y axis
  is detected and corrected automatically.

## Release check order
1. KiCad DRC with the fab's rule file, 0 errors, unconnected 0.
2. `python scripts/audit_release.py gerbers/ --pcb-only --layers <n>` (or with BOM / CPL).
3. `python scripts/gerber_check.py netcheck gerbers/ --ipc board.d356` -> shorts 0, opens 0.
4. `python scripts/gerber_check.py render gerbers/ --out preview` and open both PNGs.
