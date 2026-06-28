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
  [ "$status" -eq 0 ]
  run cat "$OUT"
  [[ "$output" == *"${ESC}]11;rgb:1a/0a/0a${BEL}"* ]]
  [[ "$output" == *"${ESC}]10;rgb:c8/ff/59${BEL}"* ]]
}

@test "apply: resolves named colors via hued-names.sh" {
  printf "background=midnightblue\n" > .hued
  HUED_TTY="$OUT" run "$HUED" apply
  [ "$status" -eq 0 ]
  run cat "$OUT"
  [[ "$output" == *"${ESC}]11;rgb:19/19/70${BEL}"* ]]
}

@test "apply: none resets the channel" {
  printf "background=none\nforeground=#ffffff\n" > .hued
  HUED_TTY="$OUT" run "$HUED" apply
  [ "$status" -eq 0 ]
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
