Working prototypes from the 2026-08-22 design session. See
`docs/superpowers/specs/2026-08-22-terminal-identity-design.md` for what they are for.
None of this is wired to anything yet.

- `gen-background.py <accent> <base> out.png [CORE=0.07] [LTOP=0.66] [LRIGHT=1.00]`
  The boomerang accent PNG. Normalized coords, so it survives iTerm's stretch-to-fill.
- `mint-color.py` — `mint(repo, branch)` in OKLCH; chroma as a fraction of gamut max.
- `solve-blend.py <target> <bg> [blend=0.5]` — authored color that *renders* as target
  through iTerm's image blend.
- `swatch-sheet.py` — writes swatches.html comparing minting policies. Needs branches.txt
  (one branch name per line) beside it.
