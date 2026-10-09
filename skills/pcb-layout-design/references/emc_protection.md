# EMC, signal routing and protection (pcb-layout-design)

Adapted from github.com/SPREsxm/claude-pcb-designer (MIT) emc-guidelines and protection-reliability.

## Return paths
- At high frequency the return current flows directly under the trace in the nearest plane. A slot or split
  in that plane forces a detour -> loop area -> emissions and crosstalk.
- A layer change moves the return current too. Between two GND references a GND via beside the signal via
  carries it ("within about 2 mm" is a working heuristic). When the reference changes from GND to a power plane,
  the return crosses through the nearest capacitor between the two: put one beside the via, or avoid the change.
- 4-layer with L2 = GND and L3 = power: route fast signals on L1. A fast signal on L4 is referenced to the L3
  power area under it, so it needs that capacitor; a GND via helps only where L4 carries GND pour beside the track.
- Never route long traces in L2. Never let a fast trace cross a gap between two L3 power areas without
  stitching capacitors - prefer routing it on L1 over continuous L2.
- Two signal layers with no plane between them (2-layer boards, some 6-layer stacks) couple broadside: keep an
  aggressor from running on top of a victim for any length; cross at right angles where they must meet.

## Decoupling
- Datasheet value and count first; 100 nF per pin pair is a starting point.
- Smallest capacitor closest; loop = pin -> cap -> via -> plane, as short as possible. A long trace to the
  cap makes a loop antenna.

## Signal routing
| signal | rule |
|---|---|
| SPI (tens of MHz) | MOSI/SCLK matched +-2 mm; series R (~22 ohm) at the source only when the waveform needs it; <= 1 via per signal; edge gap >= 2x width to other nets (3W centre to centre); never parallel to I2C/UART > 5 mm, cross at 90 deg |
| I2C | >= 10x width from SPI SCLK; never parallel to PWM/STEP/LED lines; weak pull-ups make it noise sensitive |
| fast nets in general | <= 2 vias; a return path at every layer change (above); no stubs; clocks point-to-point, terminated at the driver |
| USB HS/FS | 90 ohm differential, equal length, constant spacing, MCU-to-connector <= 50 mm, ESD at the connector |
| CAN | keep H/L together (no impedance control needed at 1 Mbit/s over short boards), ESD at the connector, optional CMC |
| crystal | load caps match the crystal CL; guard ring; no traces under it on any layer |

Crosstalk spacing: the "3W rule" is a heuristic of 3x the track width centre to centre, an edge gap of 2x the width.
Johnson and Graham's estimate for traces over a plane, crosstalk ~ K / (1 + (D / H)^2) with D the centre distance and
H the height above the plane, shows its limit: 0.15 mm tracks 0.45 mm centre to centre (3W) couple about 20 times
less over a 0.1 mm prepreg (4-layer L1) than over a 1.5 mm core (2-layer).

## Quick EMI check before export
- L2 GND has no long slots; every VDD pin decoupled per datasheet and close.
- SPI not parallel to I2C > 5 mm; fast nets have a return path at every layer change (via or capacitor).
- ESD protection at connectors with a short path to GND.
- No floating copper; no traces crossing split planes.

## ESD / surge
- System-level ESD: IEC 61000-4-2 (+-8 kV contact / +-15 kV air typical consumer & industrial), automotive
  ISO 10605. Component HBM ratings (2 kV) are NOT system protection.
- TVS selection: Vrwm >= max signal/rail voltage + 10 %; Vclamp < damage voltage of the protected IC;
  line capacitance acceptable for the signal speed; smallest package, at the connector.
- Placement: CONNECTOR -- <= 5 mm -- TVS -- <= 10 mm -- IC, TVS GND by a short via straight into the plane.
- Data lines on long cables: connector -> series R (~10 ohm) -> TVS -> IC. Telecom/very long lines add a GDT.
- Power input: VIN -> fuse/PTC -> TVS (SMBJ) -> bulk -> circuit. PTC hold = 1.5x normal current, trip ~2x
  hold, voltage rating > max system voltage. eFuses are faster and adjustable.

## Filtering
- Power input pi-filter: ferrite bead -> 10 uF -> 100 nF (bead rated >= 1.5x current, impedance peak at the
  noise frequency, low DCR).
- Common-mode choke for USB/Ethernet/CAN/RS-485 cables when emissions or immunity need it.

## Isolation (when needed)
- User-accessible connectors, long cables with ground loops, medical (IEC 60601), noisy industrial sensors.
- Options: optocoupler (slow), digital isolator, isolator + DC-DC module, transformer. CAN example: ISO1050.
