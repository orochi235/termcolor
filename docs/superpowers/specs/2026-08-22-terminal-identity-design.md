# Per-session terminal identity — design

**What this is:** a design for making a terminal session show, at a glance, which repo and
which branch it belongs to — as color, not text you have to read.
**Who it's for:** whoever builds it next. Assumes you know hued but not this session's history.
**Status:** designed and mechanism-proven 2026-08-22; nothing built.

## The constraint everything else follows from

A Claude Code session holds the foreground for hours. `precmd` never fires, so hued cannot
repaint, and anything that clobbers the background — `/clear`, a profile reapply — stays
clobbered. A hook subprocess has no controlling terminal (`/dev/tty` is "device not configured"),
so it cannot emit OSC either.

The one channel that works is iTerm's AppleScript interface, which reaches the app directly
rather than through the terminal stream. `$ITERM_SESSION_ID` (`w0t0p0:<UUID>`) is inherited into
hook subprocesses and matches a session's `unique ID`, so a hook can always find its own session.
`background image`, `background color` and `transparency` are all read/write.

Rejected on this constraint: gradient prompt bands (no prompt inside a session), and anything
requiring the shell to run.

## Three layers

**Background color** — flat `OSC 11`, what hued does today. Carries the repo's identity.

**Background image** — a generated PNG per session, carrying the accent. Built in normalized
corner-to-corner coordinates so iTerm's stretch-to-fill maps it onto the window's own corners at
any size; low-frequency enough that upscaling costs nothing. Do NOT put text in one: the image is
stretched (~5x on a Retina XDR panel) and never re-rendered on resize.

**Status bar** — real text at native resolution, for repo and branch names. Needs the iTerm
Python API: AppleScript has no user-variable setter, `OSC 1337 SetUserVar` needs a tty, and
`session.name` is contested (Claude Code rewrites the title continuously). The API also allows
per-session profile overrides, which is the only way to color the branch name per repo.
`request cookie` is in the AppleScript dictionary, so auth is scriptable. Decided 2026-08-22.

## The `.hued` format grows

```ini
background=#470013
accent=#ccff00              # optional; the highlight in the background image
branch-hue=+30deg..+90deg   # optional minting policy, inherited if absent
branch-lightness=22%..38%
branch-chroma=70%..100%
```

Signed means relative to this repo's base, unsigned means absolute — the same rule `hued mod`
already uses. Existing parsers grep for `^background=`/`^foreground=` and ignore new keys, so
this is backward compatible; nothing reads `accent` yet.

## Minting branch colors

A global `post-checkout` hook (`git config --global core.hooksPath`) fires on `git checkout -b`,
`git switch -c` and `git worktree add`. It mints a color and writes it to the worktree's `.hued`.
Store rather than derive on the fly, so every consumer — brainhouse, starship, the iTerm hook —
reads one value instead of reimplementing the derivation. Derivation remains the fallback when no
stored value exists.

Caveat: `core.hooksPath` REPLACES per-repo `.git/hooks`. Repos using husky or pre-commit silently
stop running theirs — and husky sets it in local config, which overrides the global one, so those
repos silently lose the color hook instead. Chain to `.git/hooks/post-checkout` if present.

Derivation: `sha256(repo \0 branch)`, with independent byte ranges feeding hue, chroma and
lightness so they do not correlate. Work in OKLCH — equal hue steps in HSL are not perceptually
equal, so a uniform hash clusters. Two rules learned by getting them wrong:

- **Include the repo in the hash.** Otherwise every project's `main` mints the same color.
- **Chroma is a fraction of the maximum available at that L and hue, never an absolute.** At
  L≈0.19 a deep blue holds almost no chroma; an absolute value gets crushed to near-black at some
  hues and clips at others.

Judge results by hued's existing ruler: `theme.ts` rejects `yiq > 220`.

## Image geometry

Accent weight at a point, `u` = distance from the right edge, `v` = from the top:

```
w = 1/(1 + (sqrt(u*v)/CORE)^2)              # hyperbola: thick elbow, arms tapering as 1/distance
w = (w - w_far)/(1 - w_far)                 # rebase so it reaches 0, else the whole screen tints
w *= (1 - smoothstep(0,LTOP,u)) * (1 - smoothstep(0,LRIGHT,v))
```

Tapers are multiplied, never `min()`ed — `min` creases along `u=v` and shows as a visible diagonal
line. For the same reason there is no separate center-scoop mask: `sqrt(u*v)` is only large when
both coordinates are, so lowering `CORE` scoops the center by itself.

Keeping accent near the edges is a legibility requirement, not taste: min-contrast appears to
work off the fg/bg color pair and not to sample the composited image, so bright image regions sit
under text uncorrected.

## Compositing

iTerm renders `render = Blend*image + (1-Blend)*bgcolor`. At the default 0.5 this halves the
accent's brightness AND drags its hue toward the background's — ~16° warm against a dark maroon,
which is why authored colors keep reading yellower than intended. Solve for the authored hue that
*renders* at the target rather than authoring the target.

Raising the profile's Blend toward 1.0 is safe and recommended: the image equals the background
color everywhere except the accent, and blending a color with itself is a no-op.

Compensate only for Blend. Not for transparency — the composite depends on whatever window is
behind, which is unknowable. Not for Night Shift or True Tone — they shift the whole display, and
a terminal correcting for them would be the one thing on screen that disagrees.

## Reconcile, don't fire-and-forget

Session appearance gets reapplied out from under you with no event to hook. `/clear` drops the
background color; writing `transparency` via AppleScript silently drops `background image`. Write
the image last, assume nothing survived, and run a periodic compare-and-repair against what each
session's cwd resolves to. That repair path also fixes the original bug — a session clobbered
mid-flight, which `precmd` can never reach.

## Next increment: file format only, no rendering

Decided 2026-08-22. Nothing above the file format gets built yet. The goal is that external
tools — a Claude hook creating a repo, a `post-checkout` hook, brainhouse — can *write* colour
policy into `.hued` and read it back, while hued itself continues to render only
`background`/`foreground`. Rendering the accent, the image, and the status bar all stay unbuilt.

Verified already working against `main` at be58d38:

- Read paths ignore unknown keys: `hued`, `hued apply`, `hued get bg`, and both fallback hooks
  all resolve `background` normally with `accent` and `branch-*` present.
- `_hued_set_key` preserves unknown lines, so `hued mod` does not eat them.
- `hued pack` carries the new keys into the JSON and `hued unpack` restores them byte-for-byte.

What the increment has to add:

- `hued get <key>` and `hued set <key> <value>` for `accent`, `branch-hue`, `branch-lightness`
  and `branch-chroma`. Today `hued get accent` is a usage error.
- **A footgun to close first:** `set`'s fallback arm treats an unrecognized first argument as a
  colour, so `hued set accent '#ccff00'` silently writes `background=accent` and discards the
  value. An external tool doing the natural thing corrupts the file. Two-argument `set` with an
  unknown key must fail loudly.
- Validation for the range syntax (`+30deg..+90deg`, `22%..38%`), reusing the signed/unsigned
  rule `hued mod` already implements.
- `hued unset <key>`, and documentation of the full format.

## Open

- Cleanup when a session dies without notice; the image outlives it.
- Whether `background color` shares the property-clobber behavior (untested).
- Whether min-contrast samples the image (untested; needs a screenshot to judge).
- A `hued remint` escape hatch — a changed `branch-*` policy does not recolor existing branches.
