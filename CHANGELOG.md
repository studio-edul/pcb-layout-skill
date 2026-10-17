# Changelog

Versions follow [semantic versioning](https://semver.org). The version is set in
`skills/pcb-layout-design/SKILL.md` (`metadata.version`) and `.claude-plugin/plugin.json`; bump both.

## 1.2.0 - 2026-10-17

Less tied to the stepper-driver board the skill was written on.
- `SKILL.md` section 5: block rules B16-B24 - boost, Li-ion charger / protection, LED driver, relay / solenoid,
  op-amp / precision analog, audio, RF module / antenna, Ethernet PHY / magnetics, I2C pull-ups. Each number names
  its source (TI SLVA773, bq2408x / BQ24753A, LMC660, TPA3113D2, SNLA387; TE coil suppression; ADI; Espressif ESP32
  hardware design guidelines; NXP UM10204) or is marked heuristic.
- `SKILL.md` section 6: clearance by voltage after IPC-2221B Table 6-1 replaces "0.30 mm on 24 V nets"; a 2-layer
  stackup paragraph next to the 4-layer one; "PWM / STEP" made generic.
- `references/emc_protection.md`: the full IPC-2221B Table 6-1 with notes; Ethernet MDI routing (TI SNLA387).
- `references/late_changes.md` section 3: a pin-move checklist for any MCU (function belongs to the pin, state before
  firmware, connector voltage, shared resources, where the edit happens), with STM32G431 and ESP32 (strapping pins,
  input-only pins, ADC2 and Wi-Fi; ESP32 datasheet v5.3, ESP32-WROOM-32E datasheet v2.1) as worked examples.
- `references/power_thermal.md`, `references/routing_review.md`: the stepper-driver board is labelled as one example;
  TMC2240 loss, CoolStep and the motor end cap moved under a worked-example heading.
- Three evals without a motor: a 2-layer I2C sensor board, a 48 V LED board, an ESP32 module board.

## 1.1.1 - 2026-10-09

Fixes found by running the skill against another PCB skill on the same four tasks.
- `scripts/placement_check.py`: parts at angles that are not 90 deg steps are checked with the box around the rotated
  courtyard (a 45 deg 0805 was checked as 2.1 x 1.3 mm instead of 2.4 x 2.4 mm). Connectors and modules keep their
  edge-rule exemption only where a side reaches the edge: a side inside the edge band but short of the edge is a WARN
  (a module 2.25 mm from both edges of a 2.5 mm band passed before). The bundled example's module now sits flush.
- `scripts/placement_from_easyeda.js`: parts at odd angles get the box around the rotated courtyard, as the KiCad
  importer already did.
- `scripts/pcbcalc.py microstrip` / `diff-microstrip`: a 2D field solver with copper thickness and solder mask when
  numpy and scipy are installed (`--copper-um`, `--mask-um`, `--mask-er`, `--model`); otherwise Hammerstad-Jensen
  with a thickness correction, and the output says which model ran. The old zero-thickness estimate read 8-15 % high
  on a masked JLC 4-layer stackup: 90 ohm on 0.2104 mm prepreg with 0.20 mm spacing is 0.288 mm wide, not 0.334 mm.
  Inputs are validated (height, permittivities, NaN), and both models return the same output keys.
- `SKILL.md`: reviews and checker `why` fields give a rule ID together with what it requires, because the reader does
  not have the rule table; the edge rule for connectors and modules is described as the checker applies it.

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
