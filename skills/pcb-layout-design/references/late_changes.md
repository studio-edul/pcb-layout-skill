# Late changes to a laid-out board (pcb-layout-design)

Sections 1-2 were learned on the 42 x 42 mm stepper-driver board of `routing_review.md`: after placement and routing
were done, every later change - a resistor value, a connector, a pin move - put something already confirmed at risk.
The pin-move checklist in section 3 applies to any MCU; the STM32G431 and ESP32 notes are worked examples.

Contents: 1 what late changes broke - 2 catching it with `baseline_diff.py` - 3 moving MCU signals: checklist,
STM32G431 and ESP32 examples

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

## 3. Moving MCU signals
Re-assigning pins after placement untangles buses (SKILL.md gate 2). Check every move against this list, whatever
the MCU, with its datasheet and reference manual open:
1. **The function belongs to the pin.** Read the pin-mux / alternate-function table. On a fixed mux two pins of one
   peripheral cannot trade functions; the way out is another pin set of the same peripheral or a different route.
   Parts with a routing matrix move most digital signals in firmware, but analog channels, crystal, USB and
   dedicated high-speed pins stay fixed. Note which ADC instance and channel the new pin has.
2. **What the pin does before firmware runs.** Boot / strapping pins sampled at reset, debug pins with pull-ups at
   reset, hard-wired pull-downs or other default functions. Whatever hangs on the pin (an LED, a pull resistor, a
   driver on another board) must neither change a strap value nor act before firmware takes the pin.
3. **Voltage at a connector.** 5 V tolerance is per pin and per power state (powered, unpowered), and injection
   current has its own limit: a pin that faces a connector gets a series resistor and a clamp.
4. **Shared resources.** Interrupt lines shared between ports, PWM outputs that must stay in step (one timer), ADC
   instances, DMA channels.
5. **Where the edit happens.** Each move starts in the schematic, then the board is synced, the exported netlists
   are compared and the firmware pin map is updated in the same commit.

### Example: STM32G431 (the stepper-driver board)
- **Fixed functions.** PA5 is SPI1_SCK and PA7 is SPI1_MOSI; swapping them does not uncross SCK and MOSI. SPI1 also
  sits on PB3 / PB5; PB3 is JTDO / SWO at reset, so SCK there costs the SWO trace. PA7 reaches ADC2 only, so a
  signal moved there is read with ADC2 in firmware.
- **Before firmware.** PB6 and PB4 carry the USB-PD dead-battery pull-downs (5.1 kOhm). They switch on with a high
  level on PA9 / PA10 (UCPD1_DBCC1 / DBCC2) - an idle-high USART1_TX on PA9 turns on the pull-down on PB6 - until
  firmware sets UCPD1_DBDIS in PWR_CR3. PB4 is also JTRST with a pull-up at reset: an LED there glows until
  firmware reconfigures the pin.
- **Connector voltage.** Pins marked TT_a take 4 V at most. FT pins take 4 V above the lowest of VDD / VDDA /
  VREF+, up to 5.5 V - so about 4 V while the MCU is unpowered. Neither accepts positive injection current.
- **Shared.** EXTI line n serves pin n of every port (PA3 and PB3 cannot both interrupt).

### Example: ESP32 (the original ESP32; ESP32 Series Datasheet v5.3, ESP32-WROOM-32E datasheet v2.1)
- **Strapping pins** (datasheet section 3, Table 3-1), latched at reset: GPIO0 (pull-up), GPIO2 (pull-down), MTDI /
  GPIO12 (pull-down), MTDO / GPIO15 (pull-up), GPIO5 (pull-up). GPIO0 low with GPIO2 low enters download boot.
  GPIO12 high powers VDD_SDIO - the flash / PSRAM supply - from the internal 1.8 V LDO instead of the 3.3 V rail, so
  on a part whose flash runs at 3.3 V a pull-up or a high-driving load on GPIO12 stops the boot. MTDO low silences
  the ROM boot log on U0TXD; MTDO and GPIO5 set the SDIO slave timing. The level must hold for 1 ms after CHIP_PU
  rises (Table 3-2). Buttons, LEDs and pull resistors go on other pins, or must leave the reset level intact.
- **Fixed functions.** Digital peripherals reach most pins through the GPIO matrix, so two UART or SPI signals can
  usually trade pins in firmware; ADC, touch and DAC channels stay on their pins. GPIO34-39 are inputs only, without
  internal pull-up / pull-down (a button there needs an external resistor). On the ESP32-WROOM-32E GPIO6-11 are
  wired to the flash inside the module and not brought out.
- **Shared.** ADC2 is shared with the Wi-Fi driver (ESP-IDF ADC documentation): signals that must be sampled while
  Wi-Fi runs go on ADC1 (GPIO32-39).
- Other ESP32 variants (S2, S3, C3, C6 ...) have other strapping pins: read their own datasheet.

Signals that look interchangeable:
- CC1 / CC2 can swap when nothing reads the plug orientation (a sink with plain Rd resistors, a PD controller that
  handles either). They cannot when a SuperSpeed or alternate-mode mux, firmware that assumes CC1, or the G4's
  dead-battery pairing (PA9 with PB6, PA10 with PB4) depends on which is which.
- Stepper coils: swapping the two coils, or the two ends of one coil, reverses the direction - flip the direction
  bit in firmware.
