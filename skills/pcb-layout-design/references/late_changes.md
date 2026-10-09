# Late changes to a laid-out board (pcb-layout-design)

Learned on the same 42 x 42 mm stepper-driver board as `routing_review.md`. After placement and routing were done,
every later change - a resistor value, a connector, a pin move - put something already confirmed at risk.

Contents: 1 what late changes broke - 2 catching it with `baseline_diff.py` - 3 moving MCU signals (STM32G431)

## 1. What late changes broke
- EasyEDA Pro's "apply changes" proposed to delete and re-add every part, because the script-placed parts had other
  link ids than the schematic. It was never applied; values were changed by swapping parts in place
  (`easyeda_pro_api.md`).
- Re-creating a part to change its value left a second copy of its tracks behind, and once turned the schematic
  symbol by 180 deg, so the wire drawn across it shorted two pins.
- A screw terminal came in turned by 180 deg: its wire entries faced into the board.
- The connectors were fixed by the motor flange and the cable exits. When a new part needed room, the protection and
  power parts around them had to move instead.
Each of these showed up only by comparing the board before and after the change.

## 2. Catching it with `baseline_diff.py`
1. Once the user has confirmed the fixed parts, save the importer output as `baseline.json` and set
   `"locked": true` on them (on that board: the connectors fixed by the flange and the cable exits). With no locked
   part the tool refuses to run. Add the keep-outs; the board extent comes from the importer.
2. After each change of the kind listed in section 1, import the board again as `current.json` and run
   `python scripts/baseline_diff.py baseline.json current.json`.
3. Every `ERROR` line is a locked part, the board extent or a keep-out that changed. Put it back - or, when the user
   wanted the change, save the baseline again. Unlocked parts that moved are counted in one `INFO` line
   (`--list-others` lists them). `SUMMARY baseline changes 0` closes the step.
The JSON has no stackup, design rules or zones: read those back from the EDA tool after a sync.

## 3. Moving MCU signals (STM32G431)
Re-assigning pins after placement untangled the buses on that board. What each move had to respect:
- **The function belongs to the pin.** PA5 is SPI1_SCK and PA7 is SPI1_MOSI; swapping them does not uncross SCK and
  MOSI. The way out is another pin pair from the alternate-function table (SPI1 also sits on PB3 / PB5) or a
  different route; PB3 is JTDO / SWO at reset, so SCK there costs the SWO trace. PA7 reaches ADC2 only, so a signal
  moved there is read with ADC2 in firmware.
- **What the pin does before firmware runs.** PB6 and PB4 carry the USB-PD dead-battery pull-downs (5.1 kOhm). They
  switch on with a high level on PA9 / PA10 (UCPD1_DBCC1 / DBCC2) - an idle-high USART1_TX on PA9 turns on the
  pull-down on PB6 - until firmware sets UCPD1_DBDIS in PWR_CR3. PB4 is also JTRST with a pull-up at reset: an LED
  there glows until firmware reconfigures the pin.
- **Voltage at a connector.** Pins marked TT_a take 4 V at most. FT pins take 4 V above the lowest of VDD / VDDA /
  VREF+, up to 5.5 V - so about 4 V while the MCU is unpowered. Neither accepts positive injection current: a pin
  that faces a connector gets a series resistor and a clamp.
- **Shared resources.** EXTI line n serves pin n of every port (PA3 and PB3 cannot both interrupt). PWM outputs that
  must stay in step belong to one timer.
- **Where the edit happens.** Each move started in the schematic, then the board was synced, the exported netlists
  were compared and the firmware pin map was updated in the same commit.

Signals that look interchangeable:
- CC1 / CC2 can swap when nothing reads the plug orientation (a sink with plain Rd resistors, a PD controller that
  handles either). They cannot when a SuperSpeed or alternate-mode mux, firmware that assumes CC1, or the G4's
  dead-battery pairing (PA9 with PB6, PA10 with PB4) depends on which is which.
- Stepper coils: swapping the two coils, or the two ends of one coil, reverses the direction - flip the direction
  bit in firmware.
