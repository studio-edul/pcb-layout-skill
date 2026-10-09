# Contributing

Thanks for helping. This skill is only useful if its numbers are right, so contributions need evidence.

## Rules and numbers
- Every new or changed number in `SKILL.md` or `references/` needs a source: datasheet (part, document, page), fab
  capability page, standard, or a measurement on a real board (what, how, result). Mark heuristics as heuristics.
- Keep rule IDs stable (B1, B2 ...). Add new IDs at the end; mark retired ones instead of reusing them.
- `SKILL.md` stays under 500 lines and about 5,000 tokens; detail goes to `references/` (one level deep).
- Board-specific lessons are welcome as examples, without private design data (no customer names, no full
  netlists or Gerbers you may not share).

## Scripts
- Python 3.9+, standard library where possible (numpy / Pillow / scipy / matplotlib only where already used).
- Every behaviour change comes with a test in `tests/` that fails without it. Test data is synthetic
  (`tests/fixtures.py` writes a small board); do not add real Gerbers.
- `python -m unittest discover -s tests -v` must pass; CI runs it on Linux, macOS and Windows.

## New EDA tools
An importer writes the placement JSON described at the top of `scripts/placement_check.py`. Add it as
`scripts/placement_from_<tool>.*`, document it in `SKILL.md` (scripts table) and in a short `references/<tool>_notes.md`,
and add a test with a small synthetic input.

## Checks before a pull request
```
python -m unittest discover -s tests -v
claude plugin validate .          # if you have Claude Code
```
Update `CHANGELOG.md`. Version bumps happen at release time.
