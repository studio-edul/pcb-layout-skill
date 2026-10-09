# Changelog

Versions follow [semantic versioning](https://semver.org). The version is set in
`skills/pcb-layout-design/SKILL.md` (`metadata.version`) and `.claude-plugin/plugin.json`; bump both.

## 1.1.0 - 2026-10-09

Late changes to a laid-out board, from the stepper-driver board's mistakes.
- `scripts/baseline_diff.py` (new): compares a baseline and a current placement JSON. Watches parts with
  `"locked": true` (plus `--refs`, `--classes` or `--all`), the board extent and the keep-outs; other changes are
  counted as INFO. Exits 2 on duplicate references, non-numeric values or when nothing is watched.
- `references/late_changes.md` (new): what part swaps, syncs and re-created parts broke on that board, the
  `baseline_diff.py` workflow, and moving MCU signals on an STM32G431 (fixed SPI functions, ADC instance, USB-PD
  dead-battery pull-downs, JTRST, TT_a / FT limits, EXTI and timer sharing, CC1 / CC2 and coil swaps).
- `SKILL.md`: operating rule 5 covers review-only jobs, the project's rule set and the baseline check; return current
  at layer changes (GND vs power reference); the 3W rule stated as centre to centre.
- `references/routing_review.md`: section 7, the visual pass (per layer, 3D, track angles, fab render).
- `references/emc_protection.md`: return current at layer changes (fixes the L4 advice, which ignored the L3 power
  reference), broadside coupling, crosstalk spacing with the Johnson-Graham estimate.
- `references/kicad_notes.md`, `references/easyeda_pro_api.md`: where to read the project's rule set; a footprint
  waiver example.
- Importers: repeated references become `REF#2`, `REF#3`; parts at angles that are not 90 deg steps keep their real
  angle in `rot_actual`.
- `scripts/placement_check.py`: occupancy per side on the usable area (board minus edge band and keep-outs) with the
  verdict of SKILL.md section 1 - the example board reads 65 % "dense" instead of 44 % of the whole board. The
  edge-rule exemption of connector / module / mech classes and the antenna keep-out with `allow` are documented.
- Four evals for the new behaviour; tests for `baseline_diff.py`, the importers and occupancy.
- Known gap: writing a checked placement back into KiCad / EasyEDA is manual (`references/kicad_notes.md`).

## 1.0.0 - 2026-10-08

First public release.

- `SKILL.md`: gates, operating rules, numeric placement rules, block rules B1-B15 as near / apart limits, routing and
  EMC summary, a nine-step verification procedure and output formats for designs, reviews and calculations.
- `scripts/placement_check.py`: deterministic placement checker with PNG output.
- `scripts/placement_from_kicad.py`, `scripts/placement_from_easyeda.js`: build the checker input from a KiCad board file
  or from the board open in EasyEDA Pro.
- `scripts/gerber_check.py`: fabrication-file checks independent of the EDA tool - layer detection, print preview with
  silk-on-pad and copper-to-edge, connectivity against an IPC-D-356 netlist (shorts, opens), release diff.
- `scripts/pcbcalc.py`, `scripts/audit_release.py`: calculators and release audit adapted from claude-pcb-designer.
- References: review and release, post-route audit and power-path rating, EMC and protection, power and thermal,
  EasyEDA Pro API notes, JLCPCB ordering (October 2026), KiCad exports.
- Tests (synthetic boards only), CI on Linux, macOS and Windows, evals, Claude Code plugin and marketplace manifests.

Before 1.0.0 the skill evolved privately (v1-v3) while a 4-layer stepper-driver board was designed with it; the
post-route audit, USB-C fan-out, EasyEDA API notes and ordering notes come from that work.
