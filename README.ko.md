# pcb-layout-design

**자기 작업을 스스로 검증하는 PCB 레이아웃 스킬입니다.** AI 코딩 에이전트용이고, 다음을 합니다.
- 데이터시트식 배치 규칙을 숫자로 바꿉니다.
- 좌표를 EDA 도구에 넣기 전에 결정적 배치 체커를 반드시 돌립니다.
- 전원 경로를 계산으로 정격합니다.
- 배선 후 DRC가 못 보는 문제를 점검합니다.
- 주문 전에 제조 파일 자체를 검사합니다.

[English README](README.md)

공개 표준인 [Agent Skills](https://agentskills.io) 형식이라 `SKILL.md`를 읽는 에이전트에서 모두 동작합니다(Claude Code, Codex, Gemini CLI, Cursor 등). 특정 EDA에 묶이지 않고, **KiCad**와 **EasyEDA Pro**에서 배치를 불러오는 도구가 들어 있습니다.

## 다른 PCB 도구와 다른 점

기존 AI 하드웨어 도구는 대부분 둘 중 하나입니다. EDA 프로그램을 조작하는 MCP 서버이거나, 완성된 KiCad 설계를 사후 검토하는 도구입니다. 이 스킬은 데이터시트와 레이아웃 사이에서 일하고, 모델의 암산을 믿지 않습니다.

| 단계 | 하는 일 |
|---|---|
| **배치 전** | 블록 규칙을 규칙 ID가 붙은 거리 제한(가까이 / 떨어뜨려)으로 바꿉니다. 대상은 디커플링, 벅 루프, 크리스털, 모터 드라이버, eFuse, 커넥터 ESD, USB-C, CAN입니다. `placement_check.py`가 오류 0이어야 좌표를 EDA로 넘깁니다. |
| **배치·배선 중** | `pcbcalc.py`로 선폭, 비아 전류, 임피던스, LDO 발열, 벅 인덕터를 계산합니다. 전원 경로마다 가장 약한 요소를 적은 정격표를 만듭니다. |
| **배선 후** | DRC가 못 보는 것을 점검합니다. 신호선 굵기로 남은 전원선, 줄줄이 이어진 접지, 커넥터 셸 아래 비아, 플레인의 좁은 목, FB·크리스털 옆을 지나는 노이즈 선 등입니다. |
| **늦은 변경** | 사용자가 확정한 부품은 기준 파일에 `"locked"`로 표시합니다. 부품 교체·동기화·일괄 이동 뒤 `baseline_diff.py`가 그 부품, 보드 크기, 금지 영역 중 바뀐 것을 알려 줍니다. MCU 신호를 다른 핀으로 옮길 때는 STM32G431 보드에서 배운 점을 따릅니다. |
| **주문 전** | `gerber_check.py`가 Gerber 구리와 도금 홀로 연결을 다시 계산해 IPC-D-356 넷리스트와 비교합니다(단락·단선). 실제 인쇄될 모습을 그리고, 두 릴리스를 비교해 늦게 바꾼 부분에 숨은 문제를 잡습니다. |
| **출처** | 실제 4층, 42 × 42 mm 스테퍼 드라이버 보드를 설계하며 만들었습니다(USB-C로 24 V를 잇는 체인, 5 A 전달). 배선 점검표, USB-C 팬아웃 템플릿, EasyEDA API 함정, JLCPCB 주문 메모가 그 보드에서 배운 것입니다. |

비슷한 프로젝트와의 관계 (2026년 10월 기준)
- [kicad-happy](https://github.com/aklofas/kicad-happy): 이미 만든 KiCad 설계를 검토하는 분석기 모음입니다. 이 스킬은 배치 전·중에 쓰고 KiCad에 묶이지 않습니다.
- [claude-pcb-designer](https://github.com/SPREsxm/claude-pcb-designer): 설계 단계와 계산기를 제공합니다. 이 스킬은 그 계산기와 리뷰 기준에서 시작했고([THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)), 다음을 더했습니다.
  - 배치 체커와 숫자 블록 규칙
  - 배선 후 점검
  - 제조 파일 검사
  - KiCad·EasyEDA 배치 가져오기
- [KiCad MCP 서버](https://github.com/mixelpixx/KiCAD-MCP-Server)와 공식 [EasyEDA API 스킬](https://github.com/easyeda/easyeda-api-skill): 에이전트가 EDA를 조작하는 손입니다. 이 스킬(규칙과 검사)과 같이 쓰면 됩니다.

## 설치

**Claude Code (플러그인)**
```
/plugin marketplace add studio-edul/pcb-layout-skill
/plugin install pcb-layout-design@studio-edul
```

**Claude Code (폴더 복사)**: `skills/pcb-layout-design/`를 `~/.claude/skills/`(모든 프로젝트)나 프로젝트의 `.claude/skills/`에 복사합니다.

**다른 에이전트**
| 에이전트 | 방법 |
|---|---|
| [skills.sh](https://skills.sh) 지원 에이전트 | `npx skills add studio-edul/pcb-layout-skill --skill pcb-layout-design` |
| Codex | `skills/pcb-layout-design/`를 저장소의 `.agents/skills/`나 `~/.agents/skills/`에 복사 |
| Gemini CLI | `gemini skills install https://github.com/studio-edul/pcb-layout-skill --path skills/pcb-layout-design --consent` |
| claude.ai / API | `skills/pcb-layout-design/`를 zip으로 묶어 스킬로 업로드 |

**Python** 3.9 이상이 필요합니다.
- `gerber_check.py`에는 numpy, Pillow, scipy가 필요하고, 배치 PNG에는 matplotlib이 필요합니다. 나머지는 표준 라이브러리만 씁니다.
- 한 번에 설치하려면 `pip install -r requirements.txt`를 실행하세요.

## 이렇게 시켜 보세요

- "내 KiCad 보드로 배치 JSON 만들고, 벅과 MCU 디커플링 규칙 넣어서 어긋나는 것 알려줘."
- "이 회로도 부품을 42 × 42 mm 4층 보드에 배치해 줘. NEMA17 장착 구멍, USB-C는 두 변에."
- "배선 끝난 보드를 배선 후 점검표로 리뷰하고 심각도 순으로 정리해 줘."
- "윗면에서 내층 1 oz 플레인으로 5 A 넘기려면 0.3 mm 비아 몇 개, 플레인 폭은 얼마가 필요해?"
- "주문 전에 이 Gerber를 IPC-D-356 넷리스트와 대조하고 양면 그림 보여 줘."
- "리뷰 끝난 뒤 저항값 두 개 바꿨어. 검사했던 릴리스와 비교해 줘."
- "이 보드 리뷰만 해 줘. 아무것도 고치지 말고."
- "MCU 아래에서 SPI가 꼬여. 핀 두 개 바꿔서 풀어도 돼?"

## 도구

`skills/pcb-layout-design/`에서 실행합니다. Python 스크립트에는 모두 `--help`가 있습니다.

| 스크립트 | 하는 일 |
|---|---|
| `scripts/placement_check.py` | 코트야드 겹침, 부품 종류별 간격, 가장자리, 금지 영역, 영역(zone), 거리 규칙, 그리드, 회전, 점유율, PNG |
| `scripts/placement_from_kicad.py` | `.kicad_pcb` (KiCad 6~9 문법, 옛 `module` 형식도 읽음) → 배치 JSON |
| `scripts/placement_from_easyeda.js` | EasyEDA Pro에 열린 보드 → 배치 JSON (EasyEDA 안에서 실행) |
| `scripts/baseline_diff.py` | 배치 JSON 두 개 비교 → 고정(locked) 부품이 움직이거나 돌거나 뒤집히거나 크기가 바뀌거나 사라졌는지, 보드 크기·금지 영역 변화 |
| `scripts/pcbcalc.py` | 선폭, 비아 전류, 임피던스, LDO 발열, 벅 인덕터, RC, 분압, 전력 예산 |
| `scripts/gerber_check.py` | Gerber RS-274X·Excellon의 `layers`, `render`, `netcheck --ipc`, `diff` (EasyEDA·KiCad·Protel 이름, X2 속성, mm·inch) |
| `scripts/audit_release.py` | 릴리스 폴더나 zip: 필수 레이어, 파일 구조, BOM / CPL 일치 |

예시 입력과 출력은 `examples/`에 있습니다.

## 한계

- **엔지니어를 대신하지 않습니다.** 리뷰로는 임피던스, 열, EMC, 안전을 증명할 수 없어서 측정·시뮬레이션·제조사 적층·전문가 검토가 필요한 부분을 따로 적습니다. 상용 전원, 고전압·대전류, 리튬 배터리, 의료·자동차 설계는 사람이 검토해야 합니다.
- **숫자는 계획용 목표치입니다.** 출처는 데이터시트, IPC-2221 / IPC-7351 관행, 실제 보드 한 장입니다. 실제로는 쓰는 부품의 데이터시트와 제조사의 현재 능력이 우선합니다.
- **`gerber_check.py`는 래스터(기본 0.02 mm)로 계산합니다.** 그래서 연결은 증명하지만 제조 규칙상 간격까지 증명하지는 않습니다. 블라인드·베리드 비아는 관통으로 보고, 네거티브 레이어와 반복 배치(step-and-repeat)는 그리지 않고 경고만 냅니다.
- **JLCPCB 메모는 2026년 10월 기준입니다.** 주문 화면과 가격은 바뀝니다.
- **배치 결과를 EDA에 되돌려 넣는 것은 아직 수동입니다.** KiCad·EasyEDA에서 배치를 읽어 오는 도구만 있습니다(`references/kicad_notes.md`).

## 기여·라이선스

규칙 제안은 데이터시트나 측정 근거와 함께 보내 주세요. 다른 EDA용 가져오기 도구, 제조사 프로필, 규칙이 틀렸던 보드 사례도 환영합니다. 자세한 내용은 [CONTRIBUTING.md](CONTRIBUTING.md)에, 변경 내역은 [CHANGELOG.md](CHANGELOG.md)에 있습니다.

라이선스는 MIT입니다([LICENSE](LICENSE)). 일부는 claude-pcb-designer(MIT)에서 가져와 고쳤습니다([THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)).
