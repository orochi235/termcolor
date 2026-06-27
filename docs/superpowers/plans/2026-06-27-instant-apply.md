# Instant Repaint on `hued set` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `hued set`/`unset`/`mod`/`fork`/`unpack` repaint the current terminal immediately (via a new `hued apply` subcommand), instead of waiting for the next prompt.

**Architecture:** Add a canonical `hued apply` to `bin/hued` that walks to the nearest `.hued`, resolves colors (reusing `hued-names.sh`, no `pastel`), and emits OSC 10/11 escapes to `${HUED_TTY:-/dev/tty}` — silently no-op'ing when no terminal can be opened. Mutating commands call it after writing. The shell hook `_hued_apply` (in `hued.sh`) is refactored to delegate to `hued apply` when on `PATH`, with the existing inline implementation preserved as a fallback.

**Tech Stack:** bash, bats (shell tests), OSC terminal escape sequences.

---

## Background for the implementer

- `hued` is a single bash script at `bin/hued` with `set -euo pipefail`. Because of `set -e`, **every `grep` in a pipeline whose match may be empty must be wrapped** as `$({ grep ... || true; } | cut ...)` — see existing code (e.g. the `get` command). Follow that idiom exactly or the script will exit mid-command.
- `_HUED_DIR` in `bin/hued` is the repo/install root (`dirname $0/..`); `hued-names.sh` lives there and maps X11 names to hex via lines like `[midnightblue]=#191970`.
- OSC escapes (matching the existing hook in `hued.sh`):
  - background set: `\e]11;rgb:rr/gg/bb\a`
  - background reset: `\e]111;\a`
  - foreground set: `\e]10;rgb:rr/gg/bb\a`
  - foreground reset: `\e]110;\a`
- The shell hook's public entrypoint is `_hued_apply` (users wire `precmd_functions+=(_hued_apply)`); its name must not change.

## File Structure

- **`bin/hued`** — add three helper functions (`_hued_resolve_hex`, `_hued_emit_osc`, `_hued_apply_cmd`), a new `apply)` case, and `_hued_apply_cmd` calls at the end of `set`/`unset`/`mod`/`fork`/`unpack`. Update the usage string.
- **`hued.sh`** — rename the current `_hued_apply` body to `_hued_apply_fallback`; make `_hued_apply` a dispatcher that delegates to `hued apply` when available.
- **`completions/hued.bash`, `completions/_hued`, `completions/hued.fish`** — add `apply` to subcommand lists.
- **`test/hued-apply.bats`** (new) — tests for `hued apply` and auto-apply, using the `HUED_TTY` temp-file seam.
- **`test/hued-sh.bats`** — repoint existing emit tests at `_hued_apply_fallback`; add dispatcher delegation/fallback tests.
- **`test/completions.bats`** — assert `apply` is offered.
- **`README.md`** — document `hued apply` and the exported-env-vars caveat.

---

## Task 1: `hued apply` subcommand

**Files:**
- Modify: `bin/hued` (add functions before the `case` at line ~81; add `apply)` case)
- Test: `test/hued-apply.bats` (create)

- [ ] **Step 1: Write the failing tests**

Create `test/hued-apply.bats`:

```bash
#!/usr/bin/env bats

HUED="$BATS_TEST_DIRNAME/../bin/hued"

ESC=$'\e'
BEL=$'\a'
BG_RESET="${ESC}]111;${BEL}"
FG_RESET="${ESC}]110;${BEL}"

setup() {
  TMPDIR="$(mktemp -d)"
  cd "$TMPDIR"
  unset HUED_BACKGROUND HUED_FOREGROUND
  OUT="$TMPDIR/tty.out"
}

teardown() {
  rm -rf "$TMPDIR"
}

# --- hued apply: emit logic ---

@test "apply: emits bg escape from .hued to HUED_TTY" {
  printf "background=#1a0a0a\n" > .hued
  HUED_TTY="$OUT" run "$HUED" apply
  [ "$status" -eq 0 ]
  run cat "$OUT"
  [[ "$output" == *"${ESC}]11;rgb:1a/0a/0a${BEL}"* ]]
  [[ "$output" == *"$FG_RESET"* ]]
}

@test "apply: emits both channels" {
  printf "background=#1a0a0a\nforeground=#c8ff59\n" > .hued
  HUED_TTY="$OUT" run "$HUED" apply
  run cat "$OUT"
  [[ "$output" == *"${ESC}]11;rgb:1a/0a/0a${BEL}"* ]]
  [[ "$output" == *"${ESC}]10;rgb:c8/ff/59${BEL}"* ]]
}

@test "apply: resolves named colors via hued-names.sh" {
  printf "background=midnightblue\n" > .hued
  HUED_TTY="$OUT" run "$HUED" apply
  run cat "$OUT"
  [[ "$output" == *"${ESC}]11;rgb:19/19/70${BEL}"* ]]
}

@test "apply: none resets the channel" {
  printf "background=none\nforeground=#ffffff\n" > .hued
  HUED_TTY="$OUT" run "$HUED" apply
  run cat "$OUT"
  [[ "$output" == *"$BG_RESET"* ]]
  [[ "$output" == *"${ESC}]10;rgb:ff/ff/ff${BEL}"* ]]
}

@test "apply: no .hued resets both channels" {
  HUED_TTY="$OUT" run "$HUED" apply
  [ "$status" -eq 0 ]
  run cat "$OUT"
  [[ "$output" == *"$BG_RESET"* ]]
  [[ "$output" == *"$FG_RESET"* ]]
}

@test "apply: HUED_BACKGROUND overrides the file" {
  printf "background=#000000\nforeground=#ffffff\n" > .hued
  HUED_TTY="$OUT" HUED_BACKGROUND="#ff0000" run "$HUED" apply
  run cat "$OUT"
  [[ "$output" == *"${ESC}]11;rgb:ff/00/00${BEL}"* ]]
  [[ "$output" == *"${ESC}]10;rgb:ff/ff/ff${BEL}"* ]]
}

@test "apply: walks up to the nearest .hued" {
  printf "background=#1a0a0a\n" > .hued
  mkdir -p sub/dir
  cd sub/dir
  HUED_TTY="$OUT" run "$HUED" apply
  run cat "$OUT"
  [[ "$output" == *"${ESC}]11;rgb:1a/0a/0a${BEL}"* ]]
}

@test "apply: silent no-op when HUED_TTY target cannot be opened" {
  printf "background=#1a0a0a\n" > .hued
  HUED_TTY="$TMPDIR/nope/tty.out" run "$HUED" apply
  [ "$status" -eq 0 ]
  [ -z "$output" ]
  [ ! -e "$TMPDIR/nope/tty.out" ]
}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `bats test/hued-apply.bats`
Expected: FAIL — `hued apply` is unknown, hits the `*)` usage branch (status 1).

- [ ] **Step 3: Add the helper functions**

In `bin/hued`, immediately after the `_hued_set_key()` function definition (just before `case "${1:-}" in`), add:

```bash
# Resolve a color value (6-hex, 3-hex shorthand, or X11 name) to bare rrggbb.
# Prints an empty string if it cannot be resolved.
_hued_resolve_hex() {
  local key="${1#\#}"
  key="${key// /}"
  key="${key,,}"
  if [[ "$key" =~ ^[0-9a-f]{6}$ ]]; then
    printf '%s' "$key"
  elif [[ "$key" =~ ^[0-9a-f]{3}$ ]]; then
    printf '%s' "${key:0:1}${key:0:1}${key:1:1}${key:1:1}${key:2:1}${key:2:1}"
  else
    local hex
    hex=$({ grep -m1 "\[${key}\]=" "$_HUED_DIR/hued-names.sh" 2>/dev/null || true; } | cut -d= -f2)
    printf '%s' "${hex#\#}"
  fi
}

# Emit OSC 10/11 escapes for the given bg/fg values to stdout.
# Empty value -> reset escape for that channel.
_hued_emit_osc() {
  local bg="$1" fg="$2" hex
  if [[ -n "$bg" ]]; then
    hex="$(_hued_resolve_hex "$bg")"
    [[ -n "$hex" ]] && printf '\e]11;rgb:%s/%s/%s\a' "${hex:0:2}" "${hex:2:2}" "${hex:4:2}"
  else
    printf '\e]111;\a'
  fi
  if [[ -n "$fg" ]]; then
    hex="$(_hued_resolve_hex "$fg")"
    [[ -n "$hex" ]] && printf '\e]10;rgb:%s/%s/%s\a' "${hex:0:2}" "${hex:2:2}" "${hex:4:2}"
  else
    printf '\e]110;\a'
  fi
}

# Repaint the terminal to match the nearest .hued (plus env overrides).
# Writes to ${HUED_TTY:-/dev/tty}; silent no-op if that cannot be opened.
_hued_apply_cmd() {
  local bg="" fg="" dir="$PWD"
  while [[ "$dir" != / && -n "$dir" ]]; do
    if [[ -f "$dir/.hued" ]]; then
      bg=$({ grep -m1 '^background=' "$dir/.hued" || true; } | cut -d= -f2 | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')
      fg=$({ grep -m1 '^foreground=' "$dir/.hued" || true; } | cut -d= -f2 | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')
      [[ -n "$bg" || -n "$fg" ]] && break
    fi
    dir="${dir%/*}"
  done

  if [[ -n "${HUED_BACKGROUND:-}" ]]; then
    bg=$(printf '%s' "$HUED_BACKGROUND" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')
  fi
  if [[ -n "${HUED_FOREGROUND:-}" ]]; then
    fg=$(printf '%s' "$HUED_FOREGROUND" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')
  fi
  [[ "$bg" == "none" ]] && bg=""
  [[ "$fg" == "none" ]] && fg=""

  local target="${HUED_TTY:-/dev/tty}"
  { exec 3>"$target"; } 2>/dev/null || return 0
  _hued_emit_osc "$bg" "$fg" >&3
  exec 3>&-
}
```

- [ ] **Step 4: Add the `apply)` case**

In `bin/hued`, add a new case branch inside the main `case` (place it right after the `where)` branch for readability):

```bash
  apply)
    _hued_apply_cmd
    ;;
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `bats test/hued-apply.bats`
Expected: PASS (all 8 tests).

- [ ] **Step 6: Commit**

```bash
git add bin/hued test/hued-apply.bats
git commit -m "feat(cli): add \`hued apply\` to repaint the terminal from the current .hued"
```

---

## Task 2: Auto-apply on mutating commands

**Files:**
- Modify: `bin/hued` (end of `set`/`unset`/`mod`/`fork`/`unpack` branches)
- Test: `test/hued-apply.bats` (append)

- [ ] **Step 1: Write the failing tests**

Append to `test/hued-apply.bats`:

```bash
# --- mutating commands repaint after writing ---

@test "set bg: repaints after writing" {
  HUED_TTY="$OUT" run "$HUED" set bg "#ff0000"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Set background to #ff0000"* ]]
  run cat "$OUT"
  [[ "$output" == *"${ESC}]11;rgb:ff/00/00${BEL}"* ]]
}

@test "set <color>: repaints after writing" {
  HUED_TTY="$OUT" run "$HUED" set "#00ff00"
  [ "$status" -eq 0 ]
  run cat "$OUT"
  [[ "$output" == *"${ESC}]11;rgb:00/ff/00${BEL}"* ]]
}

@test "mod: repaints after transforming" {
  if ! command -v pastel >/dev/null 2>&1; then skip "pastel not installed"; fi
  printf "background=#808080\n" > .hued
  HUED_TTY="$OUT" run "$HUED" mod bg lighten 50%
  [ "$status" -eq 0 ]
  run cat "$OUT"
  [[ "$output" == *"${ESC}]11;rgb:"* ]]
}

@test "unset: repaints after removing a channel" {
  printf "background=#1a0a0a\nforeground=#ffffff\n" > .hued
  HUED_TTY="$OUT" run "$HUED" unset bg
  [ "$status" -eq 0 ]
  run cat "$OUT"
  [[ "$output" == *"$BG_RESET"* ]]
  [[ "$output" == *"${ESC}]10;rgb:ff/ff/ff${BEL}"* ]]
}

@test "fork: repaints after materializing inherited colors" {
  printf "background=#1a0a0a\n" > .hued
  mkdir sub
  cd sub
  HUED_TTY="$OUT" run "$HUED" fork
  [ "$status" -eq 0 ]
  [ -f .hued ]
  run cat "$OUT"
  [[ "$output" == *"${ESC}]11;rgb:1a/0a/0a${BEL}"* ]]
}

@test "unpack: repaints after restoring" {
  printf '{"%s": {"background": "#1a0a0a"}}' "$TMPDIR" > export.json
  HUED_TTY="$OUT" run "$HUED" unpack export.json --force
  [ "$status" -eq 0 ]
  run cat "$OUT"
  [[ "$output" == *"${ESC}]11;rgb:1a/0a/0a${BEL}"* ]]
}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `bats test/hued-apply.bats -f "repaints|materializing|restoring"`
Expected: FAIL — the mutating commands write the file but emit nothing to `HUED_TTY` (the `cat "$OUT"` assertions fail; the status/message assertions pass).

- [ ] **Step 3: Add `_hued_apply_cmd` calls**

In `bin/hued`, add `_hued_apply_cmd` as the last statement (before the closing `;;`) of each of these branches:

1. **`set)`** — after the inner `esac`:

```bash
    esac
    _hued_apply_cmd
    ;;
```

2. **`mod`/`adjust`)** — after `_hued_set_key "$key" "$new"`:

```bash
    _hued_set_key "$key" "$new"
    _hued_apply_cmd
    ;;
```

3. **`fork)`** — after the second `_hued_set_key` line:

```bash
    if [[ -n "$fg" ]]; then _hued_set_key "foreground" "$fg"; fi
    _hued_apply_cmd
    ;;
```

4. **`unset)`** — after `echo "Unset ${key} in ${PWD}/.hued"`:

```bash
    echo "Unset ${key} in ${PWD}/.hued"
    _hued_apply_cmd
    ;;
```

5. **`unpack)`** — after the closing `PYEOF` of the heredoc:

```bash
PYEOF
    _hued_apply_cmd
    ;;
```

- [ ] **Step 4: Run the full apply test file**

Run: `bats test/hued-apply.bats`
Expected: PASS (all tests, `mod` skipped if `pastel` absent).

- [ ] **Step 5: Run the existing CLI tests to check for regressions**

Run: `bats test/hued.bats`
Expected: PASS — existing tests use `run "$HUED" …` without `HUED_TTY`, so `apply` targets `/dev/tty`, which bats cannot open → silent no-op → no stray output in `$output`.

- [ ] **Step 6: Commit**

```bash
git add bin/hued test/hued-apply.bats
git commit -m "feat(cli): repaint terminal immediately after set/unset/mod/fork/unpack"
```

---

## Task 3: Hook delegates to `hued apply`

**Files:**
- Modify: `hued.sh` (split `_hued_apply` into dispatcher + `_hued_apply_fallback`)
- Test: `test/hued-sh.bats` (repoint existing tests, add 2 dispatcher tests)

- [ ] **Step 1: Update the existing tests to target the fallback, add dispatcher tests**

In `test/hued-sh.bats`, replace every occurrence of `run _hued_apply` with `run _hued_apply_fallback` (there are 13). Use a single sweep:

Run (macOS/BSD sed; every occurrence is at end of line): `sed -i '' 's/run _hued_apply$/run _hued_apply_fallback/' test/hued-sh.bats`

Then verify exactly 13 lines changed and none were missed: `grep -c 'run _hued_apply_fallback' test/hued-sh.bats` (expect `13`) and `grep -n 'run _hued_apply$' test/hued-sh.bats` (expect no output).

Then append two dispatcher tests:

```bash
# --- dispatcher: delegate vs fallback ---

@test "_hued_apply delegates to 'hued apply' when hued is on PATH" {
  hued() { echo "DELEGATED $*"; }
  output="$(_hued_apply)"
  [[ "$output" == "DELEGATED apply" ]]
}

@test "_hued_apply uses the inline fallback when hued is unavailable" {
  # Shadow the 'command' builtin so 'command -v hued' reports not-found.
  command() { return 1; }
  output="$(_hued_apply)"
  [[ "$output" == *"$BG_RESET"* ]]
  [[ "$output" == *"$FG_RESET"* ]]
}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `bats test/hued-sh.bats`
Expected: FAIL — `_hued_apply_fallback` is not defined yet (the 13 renamed tests error), and the dispatcher tests fail because the current `_hued_apply` does not branch.

- [ ] **Step 3: Refactor `hued.sh`**

In `hued.sh`, rename the existing `_hued_apply() {` function header to `_hued_apply_fallback() {` (leave its entire body unchanged). Then, immediately after that function's closing `}`, add the dispatcher:

```bash
_hued_apply() {
  if command -v hued >/dev/null 2>&1; then
    hued apply
  else
    _hued_apply_fallback
  fi
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `bats test/hued-sh.bats`
Expected: PASS (13 renamed emit tests + 2 dispatcher tests).

- [ ] **Step 5: Commit**

```bash
git add hued.sh test/hued-sh.bats
git commit -m "feat(hook): delegate _hued_apply to \`hued apply\` with inline fallback"
```

---

## Task 4: Completions

**Files:**
- Modify: `completions/hued.bash`, `completions/_hued`, `completions/hued.fish`
- Test: `test/completions.bats`

- [ ] **Step 1: Write the failing test**

In `test/completions.bats`, find the `@test "completes top-level subcommands"` block and add this assertion inside it:

```bash
  [[ "${COMPREPLY[*]}" == *"apply"* ]]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `bats test/completions.bats -f "top-level subcommands"`
Expected: FAIL — `apply` is not in the completion word list.

- [ ] **Step 3: Add `apply` to all three completion files**

`completions/hued.bash` — add `apply` to the subcommand word list:

```bash
    mapfile -t COMPREPLY < <(compgen -W "set unset fork get mod apply where resolve pack unpack" -- "$cur")
```

`completions/_hued` — add an entry to the `subcommands` array (next to the others):

```bash
        'apply:repaint the terminal to match the current .hued'
```

`completions/hued.fish` — add `apply` to the `subcommands` list (line 2) and a completion line near the other top-level ones:

```fish
set -l subcommands set unset fork get mod apply where resolve pack unpack
```

```fish
complete -c hued -n "not __fish_seen_subcommand_from $subcommands" -a "apply"   -d "Repaint the terminal to match the current .hued"
```

- [ ] **Step 4: Run the completions tests**

Run: `bats test/completions.bats`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add completions/hued.bash completions/_hued completions/hued.fish test/completions.bats
git commit -m "feat(completions): add \`apply\` subcommand"
```

---

## Task 5: Documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document `hued apply` in the CLI list**

In `README.md`, in the `## CLI` code block, add this line after the `hued mod …` line:

```
hued apply                    # repaint the terminal to match the current .hued
```

- [ ] **Step 2: Note instant repaint and the exported-env caveat**

In `README.md`, at the end of the `## Environment variables` section (after the direnv example), add:

```markdown
`hued set`, `unset`, `mod`, `fork`, and `unpack` repaint the current terminal
immediately (they emit the color escapes to your terminal after writing the
file), so you no longer have to wait for the next prompt. You can also force a
repaint anytime with `hued apply` — handy after editing a `.hued` by hand.

Note: the prompt hook prefers the `hued` binary when it is on your `PATH`. For
`HUED_BACKGROUND` / `HUED_FOREGROUND` to take effect through it, **export** them
(tools like direnv and mise already do). A non-exported shell variable is only
honored by the hook's built-in fallback.
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document \`hued apply\` and instant repaint"
```

---

## Final verification

- [ ] **Run the whole test suite**

Run: `make` (or `bats test/*.bats`)
Expected: all bats suites PASS (picker pytest unaffected).

- [ ] **Manual smoke test in a real terminal**

```bash
cd "$(mktemp -d)"
hued set bg midnightblue   # background should change immediately
hued unset bg              # background should reset immediately
```

---

## Self-review notes (addressed)

- **Spec coverage:** `hued apply` (Task 1), `/dev/tty`+`HUED_TTY` seam & silent no-op (Task 1), auto-apply incl. `fork` (Task 2), hook delegation + fallback (Task 3), README caveat (Task 5). Completions (Task 4) added for hygiene since a new subcommand exists.
- **`set -e` safety:** all new `grep`-in-pipeline reads use the `{ grep … || true; }` guard; `exec 3>"$target"` is guarded by `|| return 0`.
- **Type/name consistency:** `_hued_resolve_hex`, `_hued_emit_osc`, `_hued_apply_cmd` (CLI) and `_hued_apply` / `_hued_apply_fallback` (hook) are used consistently across tasks. `HUED_TTY` is the single output-target override everywhere.
