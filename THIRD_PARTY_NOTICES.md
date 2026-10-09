# Third-party notices

## claude-pcb-designer

Parts of this skill are adapted from **claude-pcb-designer** (https://github.com/SPREsxm/claude-pcb-designer),
MIT License, Copyright (c) 2026 RocketBlackBox:

| file in this repository | what was taken |
|---|---|
| `skills/pcb-layout-design/scripts/pcbcalc.py` | the calculator script |
| `skills/pcb-layout-design/scripts/audit_release.py` | the release audit script |
| `skills/pcb-layout-design/references/review_release.md` | review rubric, DFM, release and bring-up checklists (adapted, extended) |
| `skills/pcb-layout-design/references/emc_protection.md` | EMC and protection guidelines (adapted) |
| `skills/pcb-layout-design/references/power_thermal.md` | the theta_JA table (marked in the file) |

Not taken on purpose: its generic part tables, the fixed 15 x 15 mm antenna zone, the 10 mm decoupling tolerance and
its current / width tables (replaced by `pcbcalc.py` results).

Its license:

```
MIT License

Copyright (c) 2026 RocketBlackBox

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
