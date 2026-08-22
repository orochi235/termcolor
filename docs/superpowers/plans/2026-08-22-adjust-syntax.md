# Adjust Syntax Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework `hued mod`/`adjust` so the channel is optional, amounts accept negatives and bare percentages, three signed HSL ops exist, and multiple ops chain in one invocation.

**Architecture:** The `mod|adjust` arm of the `case` in `bin/hued` is replaced by a token-stream parser. Parsing helpers (`_hued_parse_amount`, `_hued_parse_degrees`, `_hued_invert`, `_hued_is_op`) are pure functions defined above the dispatcher; `_hued_mod_run` walks the arg list, threading a color through one `pastel` call per op, and prints the final hex. The caller writes the file once and repaints once.

**Tech Stack:** bash 4+ (associative arrays, `[[ =~ ]]`), `pastel` for transforms, `awk` for float math, `bats` for tests.

**Spec:** `docs/superpowers/specs/2026-08-22-adjust-syntax-and-color-names-design.md`

---

## File Structure

- `bin/hued:49-62` — replace `_hued_parse_amount` and `_hued_parse_degrees` with validating versions.
- `bin/hued` (new, after the parse helpers) — `_hued_invert`, `_hued_is_op`, `_hued_amount_error`, `_hued_mod_run`.
- `bin/hued:201-244` — replace the `mod|adjust` case arm with the new dispatcher.
- `test/hued.bats:359-520` — migrate 6 existing tests off fractional args, add new coverage.
- `completions/hued.bash:18`, `completions/hued.fish:3`, `completions/_hued:69` — add the three new ops.
- `README.md:97-106` — document the new grammar.

## Bash traps in this plan

Two things will silently break the implementation if ignored:

1. **`set -euo pipefail` is on** (`bin/hued:4`). `amount=$(_hued_parse_amount "$raw")` where the helper returns non-zero aborts the whole script before you can read `$?`. Always use the `&& rc=0 || rc=$?` form shown below, which puts the substitution in a condition context where `set -e` does not fire.
2. **`exit` inside `$( )` exits only the subshell.** Validation helpers must `return` a status the caller checks; they must never try to `exit` the program.

---

## Task 1: Validating amount parser

**Files:**
- Modify: `bin/hued:49-56`
- Test: `test/hued.bats`

- [ ] **Step 1: Write the failing tests**

Add to `test/hued.bats` immediately after the `# --- mod ---` header comment:

```bash
@test "mod bg darken: bare number is percent" {
  command -v pastel >/dev/null 2>&1 || skip "pastel not installed"
  printf "background=#888888\n" > .hued
  "$HUED" mod bg darken 20
  new=$(grep ^background= .hued | cut -d= -f2)
  expected=$(pastel darken 0.2 '#888888' | pastel format hex)
  [[ "$new" == "$expected" ]]
}

@test "mod bg darken: bare fraction is rejected as ambiguous" {
  command -v pastel >/dev/null 2>&1 || skip "pastel not installed"
  printf "background=#888888\n" > .hued
  run "$HUED" mod bg darken 0.2
  [ "$status" -eq 1 ]
  [[ "$output" == *"ambiguous"* ]]
  [[ "$output" == *"20%"* ]]
}

@test "mod bg darken: explicit fractional percent is allowed" {
  command -v pastel >/dev/null 2>&1 || skip "pastel not installed"
  printf "background=#888888\n" > .hued
  "$HUED" mod bg darken 0.2%
  new=$(grep ^background= .hued | cut -d= -f2)
  expected=$(pastel darken 0.002 '#888888' | pastel format hex)
  [[ "$new" == "$expected" ]]
}

@test "mod bg darken: non-numeric amount fails" {
  command -v pastel >/dev/null 2>&1 || skip "pastel not installed"
  printf "background=#888888\n" > .hued
  run "$HUED" mod bg darken banana
  [ "$status" -eq 1 ]
  [[ "$output" == *"not a number"* ]]
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bats test/hued.bats -f "bare number is percent"`
Expected: FAIL — `darken 20` currently forwards `20` to pastel, which clamps to black rather than producing the 20% result.

- [ ] **Step 3: Replace the parser**

In `bin/hued`, replace lines 49-56 (the whole existing `_hued_parse_amount`) with:

```bash
# Parse an amount into a pastel fraction. Accepts "20", "20%", "+20%", "-20%".
# Status 1 = not a number, 2 = ambiguous bare fraction in (0,1).
_hued_parse_amount() {
  local val="$1" n abs
  if [[ "$val" =~ ^([+-]?[0-9]+(\.[0-9]+)?)%$ ]]; then
    n="${BASH_REMATCH[1]}"
  elif [[ "$val" =~ ^([+-]?[0-9]+(\.[0-9]+)?)$ ]]; then
    n="${BASH_REMATCH[1]}"
    abs="${n#[+-]}"
    awk -v a="$abs" 'BEGIN{exit !(a>0 && a<1)}' && return 2
  else
    return 1
  fi
  awk -v n="$n" 'BEGIN{printf "%g", n/100}'
}

# Report a parse failure. $1 is the status from _hued_parse_amount, $2 the raw
# token. Returns 1 when it printed an error, 0 when the parse was fine.
_hued_amount_error() {
  case "$1" in
    1)
      echo "hued mod: '$2' is not a number" >&2
      return 1
      ;;
    2)
      echo "hued mod: $2 is ambiguous — write \"$2%\" for $2 percent, or \"$(awk -v n="$2" 'BEGIN{printf "%g", n*100}')%\"" >&2
      return 1
      ;;
  esac
  return 0
}
```

Note both branches divide by 100, so `20` and `20%` both yield `0.2`, and `0.2%` yields `0.002`.

- [ ] **Step 4: Run the tests**

Run: `bats test/hued.bats -f "mod bg darken"`
Expected: the four new tests PASS. `mod bg darken: 0.2 darkens the background` now FAILS — that is expected and Task 6 migrates it.

- [ ] **Step 5: Commit**

```bash
git add bin/hued test/hued.bats
git commit -m "feat(mod): read bare numbers as percent, reject ambiguous fractions"
```

---

## Task 2: Validating degree parser

**Files:**
- Modify: `bin/hued:58-62`
- Test: `test/hued.bats`

- [ ] **Step 1: Write the failing tests**

```bash
@test "mod bg rotate: accepts a negative angle" {
  command -v pastel >/dev/null 2>&1 || skip "pastel not installed"
  printf "background=#ff0000\n" > .hued
  "$HUED" mod bg rotate -90
  new=$(grep ^background= .hued | cut -d= -f2)
  expected=$(pastel rotate -- -90 '#ff0000' | pastel format hex)
  [[ "$new" == "$expected" ]]
}

@test "mod bg rotate: accepts a negative angle with deg suffix" {
  command -v pastel >/dev/null 2>&1 || skip "pastel not installed"
  printf "background=#ff0000\n" > .hued
  "$HUED" mod bg rotate -90deg
  new=$(grep ^background= .hued | cut -d= -f2)
  expected=$(pastel rotate -- -90 '#ff0000' | pastel format hex)
  [[ "$new" == "$expected" ]]
}

@test "mod bg rotate: non-numeric angle fails" {
  command -v pastel >/dev/null 2>&1 || skip "pastel not installed"
  printf "background=#ff0000\n" > .hued
  run "$HUED" mod bg rotate sideways
  [ "$status" -eq 1 ]
  [[ "$output" == *"degrees"* ]]
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bats test/hued.bats -f "negative angle"`
Expected: FAIL with pastel's `error: unexpected argument '-9' found` — the current code has no `--` separator.

- [ ] **Step 3: Replace the parser**

In `bin/hued`, replace lines 58-62 with:

```bash
# Parse degrees. Accepts "30", "30deg", "30°", each with an optional sign.
# Status 1 = not a number.
_hued_parse_degrees() {
  local val="${1%deg}"
  val="${val%°}"
  [[ "$val" =~ ^[+-]?[0-9]+(\.[0-9]+)?$ ]] || return 1
  printf '%s' "$val"
}
```

The `--` separator is added at the call site in Task 4, not here.

- [ ] **Step 4: Run the tests**

Run: `bats test/hued.bats -f "rotate"`
Expected: the non-numeric test PASSES; the two negative-angle tests still FAIL until Task 4 adds `--`.

- [ ] **Step 5: Commit**

```bash
git add bin/hued test/hued.bats
git commit -m "feat(mod): validate degree arguments and accept a sign"
```

---

## Task 3: Op-name and inversion helpers

**Files:**
- Modify: `bin/hued` (insert after `_hued_parse_degrees`)

These are pure functions with no user-visible behavior yet, so they are covered by the tests in Tasks 4-5 rather than tests of their own.

- [ ] **Step 1: Add the helpers**

Insert immediately after `_hued_parse_degrees` in `bin/hued`:

```bash
_hued_is_op() {
  case "$1" in
    darken|lighten|saturate|desaturate|rotate|complement|to-gray|mix|lightness|saturation|hue)
      return 0 ;;
    *) return 1 ;;
  esac
}

_hued_invert() {
  case "$1" in
    darken)     printf 'lighten' ;;
    lighten)    printf 'darken' ;;
    saturate)   printf 'desaturate' ;;
    desaturate) printf 'saturate' ;;
  esac
}

_HUED_OPS="darken, lighten, saturate, desaturate, rotate, complement, to-gray, mix, lightness, saturation, hue"
```

- [ ] **Step 2: Verify the script still parses**

Run: `bash -n bin/hued && bin/hued -v`
Expected: `hued 3.3.1`

- [ ] **Step 3: Commit**

```bash
git add bin/hued
git commit -m "feat(mod): add op-name and verb-inversion helpers"
```

---

## Task 4: The chain runner

**Files:**
- Modify: `bin/hued` (insert after the Task 3 helpers)

- [ ] **Step 1: Add `_hued_mod_run`**

Insert after `_HUED_OPS` in `bin/hued`:

```bash
# Apply a chain of ops to a color, printing the resulting hex.
# Usage: _hued_mod_run <color> <op> [args...] [<op> [args...]]...
_hued_mod_run() {
  local color="$1"; shift
  local op raw amount deg other verb prop rc

  while [[ $# -gt 0 ]]; do
    op="$1"; shift
    case "$op" in
      darken|lighten|saturate|desaturate)
        [[ $# -gt 0 ]] || { echo "hued mod: $op requires an amount" >&2; return 1; }
        raw="$1"; shift
        amount=$(_hued_parse_amount "$raw") && rc=0 || rc=$?
        _hued_amount_error "$rc" "$raw" || return 1
        if [[ "$amount" == -* ]]; then
          op=$(_hued_invert "$op")
          amount="${amount#-}"
        fi
        color=$(pastel "$op" "$amount" "$color" | pastel format hex) || return 1
        ;;
      rotate)
        [[ $# -gt 0 ]] || { echo "hued mod: rotate requires degrees" >&2; return 1; }
        raw="$1"; shift
        deg=$(_hued_parse_degrees "$raw") || {
          echo "hued mod: '$raw' is not a number of degrees" >&2; return 1; }
        color=$(pastel rotate -- "$deg" "$color" | pastel format hex) || return 1
        ;;
      complement|to-gray)
        color=$(pastel "$op" "$color" | pastel format hex) || return 1
        ;;
      mix)
        [[ $# -gt 0 ]] || { echo "hued mod: mix requires a color" >&2; return 1; }
        other="$1"; shift
        amount="0.5"
        if [[ $# -gt 0 ]] && ! _hued_is_op "$1"; then
          raw="$1"; shift
          amount=$(_hued_parse_amount "$raw") && rc=0 || rc=$?
          _hued_amount_error "$rc" "$raw" || return 1
          [[ "$amount" == -* ]] && {
            echo "hued mod: mix ratio cannot be negative" >&2; return 1; }
        fi
        color=$(pastel mix --fraction "$amount" "$other" "$color" | pastel format hex) || return 1
        ;;
      lightness|saturation)
        [[ $# -gt 0 ]] || { echo "hued mod: $op requires a value" >&2; return 1; }
        raw="$1"; shift
        amount=$(_hued_parse_amount "$raw") && rc=0 || rc=$?
        _hued_amount_error "$rc" "$raw" || return 1
        if [[ "$raw" == [+-]* ]]; then
          if [[ "$op" == "lightness" ]]; then
            verb="lighten"; [[ "$amount" == -* ]] && verb="darken"
          else
            verb="saturate"; [[ "$amount" == -* ]] && verb="desaturate"
          fi
          color=$(pastel "$verb" "${amount#-}" "$color" | pastel format hex) || return 1
        else
          prop="hsl-lightness"
          [[ "$op" == "saturation" ]] && prop="hsl-saturation"
          color=$(pastel set "$prop" "$amount" "$color" | pastel format hex) || return 1
        fi
        ;;
      hue)
        [[ $# -gt 0 ]] || { echo "hued mod: hue requires degrees" >&2; return 1; }
        raw="$1"; shift
        deg=$(_hued_parse_degrees "$raw") || {
          echo "hued mod: '$raw' is not a number of degrees" >&2; return 1; }
        if [[ "$raw" == [+-]* ]]; then
          color=$(pastel rotate -- "$deg" "$color" | pastel format hex) || return 1
        else
          color=$(pastel set hsl-hue "$deg" "$color" | pastel format hex) || return 1
        fi
        ;;
      *)
        echo "hued mod: unknown op '$op' ($_HUED_OPS)" >&2
        return 1
        ;;
    esac
  done

  printf '%s' "$color"
}
```

`hsl-lightness` / `hsl-saturation` / `hsl-hue` are deliberate: bare `pastel set lightness` is Lab lightness on a 0-100 scale and would render near-black, while `darken`/`saturate` operate on HSL.

- [ ] **Step 2: Verify the script still parses**

Run: `bash -n bin/hued && bin/hued -v`
Expected: `hued 3.3.1`

- [ ] **Step 3: Commit**

```bash
git add bin/hued
git commit -m "feat(mod): add chain runner for op sequences"
```

---

## Task 5: Wire up the dispatcher

**Files:**
- Modify: `bin/hued:201-244` (the `mod|adjust` case arm)
- Test: `test/hued.bats`

- [ ] **Step 1: Write the failing tests**

```bash
@test "mod: channel defaults to background" {
  command -v pastel >/dev/null 2>&1 || skip "pastel not installed"
  printf "background=#888888\n" > .hued
  "$HUED" mod darken 20%
  new=$(grep ^background= .hued | cut -d= -f2)
  expected=$(pastel darken 0.2 '#888888' | pastel format hex)
  [[ "$new" == "$expected" ]]
}

@test "mod: unknown leading token fails as unknown op" {
  command -v pastel >/dev/null 2>&1 || skip "pastel not installed"
  printf "background=#888888\n" > .hued
  run "$HUED" mod xyz 20%
  [ "$status" -eq 1 ]
  [[ "$output" == *"unknown op"* ]]
}

@test "mod bg darken: negative amount lightens" {
  command -v pastel >/dev/null 2>&1 || skip "pastel not installed"
  printf "background=#888888\n" > .hued
  "$HUED" mod bg darken -10%
  new=$(grep ^background= .hued | cut -d= -f2)
  expected=$(pastel lighten 0.1 '#888888' | pastel format hex)
  [[ "$new" == "$expected" ]]
}

@test "mod bg saturate: negative amount desaturates" {
  command -v pastel >/dev/null 2>&1 || skip "pastel not installed"
  printf "background=#cc4444\n" > .hued
  "$HUED" mod bg saturate -25%
  new=$(grep ^background= .hued | cut -d= -f2)
  expected=$(pastel desaturate 0.25 '#cc4444' | pastel format hex)
  [[ "$new" == "$expected" ]]
}

@test "mod bg: chained ops apply in order" {
  command -v pastel >/dev/null 2>&1 || skip "pastel not installed"
  printf "background=#888888\n" > .hued
  "$HUED" mod bg darken 10% rotate 30deg
  new=$(grep ^background= .hued | cut -d= -f2)
  step1=$(pastel darken 0.1 '#888888' | pastel format hex)
  expected=$(pastel rotate -- 30 "$step1" | pastel format hex)
  [[ "$new" == "$expected" ]]
}

@test "mod bg: a chain writes the key exactly once" {
  command -v pastel >/dev/null 2>&1 || skip "pastel not installed"
  printf "background=#888888\n" > .hued
  "$HUED" mod bg darken 10% rotate 30deg desaturate 5%
  [ "$(grep -c '^background=' .hued)" -eq 1 ]
}

@test "mod bg: a failing op in a chain leaves the file untouched" {
  command -v pastel >/dev/null 2>&1 || skip "pastel not installed"
  printf "background=#888888\n" > .hued
  run "$HUED" mod bg darken 10% rotate sideways
  [ "$status" -eq 1 ]
  [[ "$(grep ^background= .hued | cut -d= -f2)" == "#888888" ]]
}

@test "mod bg mix: ratio in a chain is distinguished from a following op" {
  command -v pastel >/dev/null 2>&1 || skip "pastel not installed"
  printf "background=#ff0000\n" > .hued
  "$HUED" mod bg mix '#0000ff' darken 10%
  new=$(grep ^background= .hued | cut -d= -f2)
  step1=$(pastel mix --fraction 0.5 '#0000ff' '#ff0000' | pastel format hex)
  expected=$(pastel darken 0.1 "$step1" | pastel format hex)
  [[ "$new" == "$expected" ]]
}

@test "mod bg mix: negative ratio fails" {
  command -v pastel >/dev/null 2>&1 || skip "pastel not installed"
  printf "background=#ff0000\n" > .hued
  run "$HUED" mod bg mix '#0000ff' -25%
  [ "$status" -eq 1 ]
  [[ "$output" == *"cannot be negative"* ]]
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bats test/hued.bats -f "channel defaults"`
Expected: FAIL with `Usage: hued mod [bg|fg]` — the current arm requires a channel.

- [ ] **Step 3: Replace the case arm**

Replace `bin/hued:201-244` in full with:

```bash
  mod|adjust)
    shift
    key="background"
    case "${1:-}" in
      bg|background) key="background"; shift ;;
      fg|foreground) key="foreground"; shift ;;
    esac
    [[ $# -gt 0 ]] || { echo "Usage: hued mod [bg|fg] <op> [<args>...]" >&2; exit 1; }
    _hued_is_op "$1" || {
      echo "hued mod: unknown op '$1' ($_HUED_OPS)" >&2
      exit 1
    }
    command -v pastel >/dev/null 2>&1 || {
      echo "hued mod: requires 'pastel' (brew install pastel)" >&2
      exit 1
    }
    file=$(_hued_find) || { echo "No .hued file found" >&2; exit 1; }
    current=$({ grep -m1 "^${key}=" "$file" || true; } | cut -d= -f2 | awk '{print $1}')
    [[ -z "$current" ]] && { echo "hued mod: ${key} not set in $file" >&2; exit 1; }
    new=$(_hued_mod_run "$current" "$@") || exit 1
    _hued_set_key "$key" "$new"
    _hued_apply_cmd
    ;;
```

`_hued_mod_run` is called in a command substitution, so its `return 1` surfaces as a non-zero status and `|| exit 1` aborts before `_hued_set_key` runs — that is what keeps a failed chain from touching the file.

- [ ] **Step 4: Run the tests**

Run: `bats test/hued.bats -f "mod"`
Expected: all new tests PASS. Six pre-existing tests still FAIL (they pass fractional amounts); Task 6 migrates them.

- [ ] **Step 5: Commit**

```bash
git add bin/hued test/hued.bats
git commit -m "feat(mod): make channel optional and support chained ops"
```

---

## Task 6: Migrate the pre-existing tests

**Files:**
- Modify: `test/hued.bats:367-371, 380-386, 404-412, 423-430, 441-448, 501-509`

Six tests use amounts in the ambiguous `(0,1)` band, and one asserts the old invalid-channel behavior. Each must be rewritten; the `pastel` expectation stays a fraction because that is what pastel takes.

- [ ] **Step 1: Rewrite each test**

`mod: invalid channel fails` — `xyz` is now read as an op, so retitle and re-assert:

```bash
@test "mod: invalid channel is treated as an unknown op" {
  run "$HUED" mod xyz darken 20%
  [ "$status" -eq 1 ]
  [[ "$output" == *"unknown op"* ]]
}
```

`mod bg: fails when channel not set` — change `darken 0.2` to `darken 20%`.

`mod bg: unknown op fails` — change `frobnicate 0.2` to `frobnicate 20%`.

`mod bg darken: 0.2 darkens the background` — retitle and use percent:

```bash
@test "mod bg darken: 20% darkens the background" {
  command -v pastel >/dev/null 2>&1 || skip "pastel not installed"
  printf "background=#888888\n" > .hued
  run "$HUED" mod bg darken 20%
  [ "$status" -eq 0 ]
  new=$(grep ^background= .hued | cut -d= -f2)
  expected=$(pastel darken 0.2 '#888888' | pastel format hex)
  [[ "$new" == "$expected" ]]
}
```

`mod fg lighten: works on foreground` — change `lighten 0.1` to `lighten 10%`.

`mod bg desaturate: applies desaturate` — change `desaturate 0.5` to `desaturate 50%`.

`mod bg mix: accepts explicit ratio` — change `mix '#0000ff' 0.25` to `mix '#0000ff' 25%`; the `pastel mix --fraction 0.25` expectation is unchanged.

`mod bg: fails when pastel not installed` — change `darken 0.2` to `darken 20%`.

- [ ] **Step 2: Run the full mod suite**

Run: `bats test/hued.bats -f "mod"`
Expected: all PASS, no failures.

- [ ] **Step 3: Run the whole suite**

Run: `bats test/`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add test/hued.bats
git commit -m "test(mod): migrate fractional amounts to percent form"
```

---

## Task 7: Signed HSL ops

**Files:**
- Test: `test/hued.bats`

The implementation already landed in Task 4; this task is the test coverage that proves it, including the Lab-vs-HSL trap.

- [ ] **Step 1: Write the tests**

```bash
@test "mod bg lightness: signed value is relative" {
  command -v pastel >/dev/null 2>&1 || skip "pastel not installed"
  printf "background=#336699\n" > .hued
  "$HUED" mod bg lightness +10%
  new=$(grep ^background= .hued | cut -d= -f2)
  expected=$(pastel lighten 0.1 '#336699' | pastel format hex)
  [[ "$new" == "$expected" ]]
}

@test "mod bg lightness: negative signed value darkens" {
  command -v pastel >/dev/null 2>&1 || skip "pastel not installed"
  printf "background=#336699\n" > .hued
  "$HUED" mod bg lightness -10%
  new=$(grep ^background= .hued | cut -d= -f2)
  expected=$(pastel darken 0.1 '#336699' | pastel format hex)
  [[ "$new" == "$expected" ]]
}

@test "mod bg lightness: unsigned value sets HSL lightness absolutely" {
  command -v pastel >/dev/null 2>&1 || skip "pastel not installed"
  printf "background=#336699\n" > .hued
  "$HUED" mod bg lightness 40%
  new=$(grep ^background= .hued | cut -d= -f2)
  [[ "$new" == "#336699" ]]
}

@test "mod bg saturation: unsigned value sets HSL saturation absolutely" {
  command -v pastel >/dev/null 2>&1 || skip "pastel not installed"
  printf "background=#336699\n" > .hued
  "$HUED" mod bg saturation 90%
  new=$(grep ^background= .hued | cut -d= -f2)
  expected=$(pastel set hsl-saturation 0.9 '#336699' | pastel format hex)
  [[ "$new" == "$expected" ]]
}

@test "mod bg saturation: signed value is relative" {
  command -v pastel >/dev/null 2>&1 || skip "pastel not installed"
  printf "background=#cc4444\n" > .hued
  "$HUED" mod bg saturation -25%
  new=$(grep ^background= .hued | cut -d= -f2)
  expected=$(pastel desaturate 0.25 '#cc4444' | pastel format hex)
  [[ "$new" == "$expected" ]]
}

@test "mod bg hue: unsigned value sets hue absolutely" {
  command -v pastel >/dev/null 2>&1 || skip "pastel not installed"
  printf "background=#336699\n" > .hued
  "$HUED" mod bg hue 200deg
  new=$(grep ^background= .hued | cut -d= -f2)
  expected=$(pastel set hsl-hue 200 '#336699' | pastel format hex)
  [[ "$new" == "$expected" ]]
}

@test "mod bg hue: signed value rotates" {
  command -v pastel >/dev/null 2>&1 || skip "pastel not installed"
  printf "background=#336699\n" > .hued
  "$HUED" mod bg hue +30deg
  new=$(grep ^background= .hued | cut -d= -f2)
  expected=$(pastel rotate -- 30 '#336699' | pastel format hex)
  [[ "$new" == "$expected" ]]
}
```

The absolute-lightness test asserts `#336699` unchanged on purpose: that color is already at HSL L=40%, so a correct implementation is a no-op. If the implementation used Lab `lightness` instead, it would return `#000633` and the test would catch it.

- [ ] **Step 2: Run the tests**

Run: `bats test/hued.bats -f "lightness|saturation|hue"`
Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add test/hued.bats
git commit -m "test(mod): cover signed and absolute HSL ops"
```

---

## Task 8: Completions

**Files:**
- Modify: `completions/hued.bash:18`, `completions/hued.fish:3`, `completions/_hued:69`
- Test: `test/completions.bats`

- [ ] **Step 1: Write the failing test**

Add to `test/completions.bats`:

```bash
@test "completions: all three shells list the new HSL ops" {
  for f in completions/hued.bash completions/hued.fish completions/_hued; do
    grep -q "lightness" "$BATS_TEST_DIRNAME/../$f" || {
      echo "missing lightness in $f"; return 1; }
    grep -q "saturation" "$BATS_TEST_DIRNAME/../$f" || {
      echo "missing saturation in $f"; return 1; }
    grep -q "hue" "$BATS_TEST_DIRNAME/../$f" || {
      echo "missing hue in $f"; return 1; }
  done
}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `bats test/completions.bats -f "new HSL ops"`
Expected: FAIL with `missing lightness in completions/hued.bash`.

- [ ] **Step 3: Update all three op lists**

`completions/hued.bash:18` — replace the `-W` word list with:

```bash
    mapfile -t COMPREPLY < <(compgen -W "darken lighten saturate desaturate rotate complement to-gray mix lightness saturation hue" -- "$cur")
```

`completions/hued.fish:3`:

```fish
set -l mod_ops darken lighten saturate desaturate rotate complement to-gray mix lightness saturation hue
```

`completions/_hued:69`:

```zsh
          _describe 'op' '(darken lighten saturate desaturate rotate complement to-gray mix lightness saturation hue)'
```

- [ ] **Step 4: Run the completions suite**

Run: `bats test/completions.bats`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add completions/ test/completions.bats
git commit -m "feat(completions): add lightness, saturation, and hue ops"
```

---

## Task 9: Documentation

**Files:**
- Modify: `README.md:83, 97-106`

- [ ] **Step 1: Update the usage line**

`README.md:83` becomes:

```
hued mod [bg|fg] <op> [<args>]  # apply pastel transforms to a channel
```

- [ ] **Step 2: Replace the mod section**

Replace the `mod` paragraph and example block (`README.md:97-106`) with:

````markdown
`mod` (alias: `adjust`) is sugar for the read-transform-write loop. The channel
is optional and defaults to `bg`.

```
hued mod bg darken 20%      # 20% and 20 are the same; 0.2 is rejected as ambiguous
hued mod bg darken -10%     # a negative amount runs the opposite op
hued mod fg rotate 30deg
hued mod bg mix '#0000ff' 25%
hued mod bg lightness 40%   # unsigned: set HSL lightness
hued mod bg lightness +10%  # signed: relative, same as lighten 10%
hued mod bg hue +30deg
hued mod bg darken 10% rotate 30deg desaturate 5%   # chained, one write
```

Ops: `darken`, `lighten`, `saturate`, `desaturate`, `rotate`, `complement`,
`to-gray`, `mix`, `lightness`, `saturation`, `hue`.
````

- [ ] **Step 3: Verify no stale fractional examples remain**

Run: `grep -n "mod .* 0\.[0-9]" README.md`
Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document the reworked mod grammar"
```

---

## Task 10: Full verification

- [ ] **Step 1: Run every suite**

Run: `bats test/`
Expected: all PASS, zero failures.

- [ ] **Step 2: Exercise the chain by hand**

```bash
cd "$(mktemp -d)"
printf 'background=#336699\n' > .hued
hued mod darken 10% rotate 30deg
hued mod bg lightness +5% saturation -10%
hued
```

Expected: each command prints a `Set background to …` line, `.hued` holds exactly one `background=` line, and no pastel error appears.

- [ ] **Step 3: Confirm the ambiguity guard**

Run: `hued mod bg darken 0.2`
Expected: exit 1, message naming both `0.2%` and `20%`.
