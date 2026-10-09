# Changelog

Versions follow [semantic versioning](https://semver.org). The version is set in
`skills/pcb-layout-design/SKILL.md` (`metadata.version`) and `.claude-plugin/plugin.json`; bump both.

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
