# KiCad with this skill (pcb-layout-design)

Menu names are from KiCad 7-9; older versions differ slightly.

## Placement in, placement out
- `python scripts/placement_from_kicad.py board.kicad_pcb -o placement.json` reads footprints (`footprint` and the
  older `module` form), their courtyards (`F.CrtYd` / `B.CrtYd`), sides and rotations, and the `Edge.Cuts` extent.
  Footprints without a courtyard get pads + 0.25 mm (0.15 mm for 0402 / 0603 sizes) and a `note`.
- KiCad's y axis points down; the placement JSON uses y up (y_json = -y_kicad). Apply results back with that sign.
- Rotations that are not multiples of 90 deg come out as an axis-aligned bounding box with `rot` 0 and a note.
- Classes are guessed from the reference prefix (U ic/module, Q/K/F and large L/C power, J/P connector, H/MH/TP/FID
  mech, rest passive): correct them, then add zones, keep-outs and near / apart pairs (SKILL.md section 5).

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
