# Instant repaint on `hued set` — design

## Problem

`hued set`/`unset`/`mod`/`fork`/`unpack` only write the `.hued` file. The
terminal's colors don't change until the next prompt, when the shell hook
(`_hued_apply`, run from `precmd`/`PROMPT_COMMAND`) walks to the nearest `.hued`
and emits the OSC 10/11 escapes. There is no way to repaint the current
terminal immediately from the CLI.

The original motivating case — running `!hued set …` inside a Claude Code
session — is **fundamentally unsupportable**: a command spawned by the harness
has no controlling terminal connected to the user's real terminal emulator
(`/dev/tty` is "device not configured"), and the harness captures and
re-renders output rather than passing escape bytes through. The achievable goal
is therefore: make `hued set` (and siblings) repaint **immediately when run from
a real interactive shell**, and degrade to a silent no-op when there is no
terminal to paint (including the Claude Code case, so no escape bytes leak into
captured output).

## Design

### 1. New `hued apply` subcommand (`bin/hued`)

Canonical "make the terminal match the current state" command. Mirrors the
logic in `hued.sh`'s `_hued_apply`:

- Walk `$PWD` upward to the nearest `.hued` that defines `background=` and/or
  `foreground=`; take both channels from that file and stop (same break
  semantics as the hook — does not continue upward for a missing channel).
- Apply `HUED_BACKGROUND` / `HUED_FOREGROUND` overrides. Treat a value of `none`
  (from file or env) as "reset this channel."
- Resolve named colors via `hued-names.sh` (grep lookup, same mechanism the
  hook uses) — **no `pastel` dependency**. Pass 6-hex values through.
- Emit OSC to the output target:
  - bg set:   `\e]11;rgb:rr/gg/bb\a`
  - bg empty: `\e]111;\a` (reset)
  - fg set:   `\e]10;rgb:rr/gg/bb\a`
  - fg empty: `\e]110;\a` (reset)

**Output target.** Escapes are written to `${HUED_TTY:-/dev/tty}`. If the target
cannot be opened for writing (no controlling terminal — the `!hued set` inside
Claude Code case), `hued apply` **silently no-ops**: nothing is written, exit 0.
This guarantees no escape bytes leak into harness-captured output.

`HUED_TTY` is also the **test seam**: tests set `HUED_TTY=<tmpfile>` and assert
on the file contents.

Standalone use works too: `hued apply` typed at a real prompt opens `/dev/tty`
(the user's terminal) and repaints. This is the manual escape hatch for the
Claude Code case — after `!hued set …` writes the file, the user runs
`hued apply` (or just waits for the next prompt) from their real shell.

### 2. Mutating commands auto-apply

`set`, `unset`, `mod`, `fork`, and `unpack` call the apply logic after writing
the file. They print their existing status message (`Set background to …`)
first, then repaint. Implementation: factor the apply body into an internal
function and call it at the end of each of those command branches.

- `fork` is included for a uniform "every mutating command repaints" rule. Its
  repaint is provably a no-op (it copies the already-inherited ancestor colors
  into a local file; effective colors are unchanged), but including it removes a
  special case from the code and the docs, and an invisible redundant escape is
  harmless.
- `pack` and read-only commands (`get`, `where`, `resolve`, the no-arg getter,
  `-v`) do **not** apply.

No opt-out flag. The `/dev/tty`-only target already makes the repaint inert in
scripts and pipelines that have no controlling terminal, which covers the
"don't flicker during automation" concern without new surface area.

### 3. Hook delegates to `hued apply` (`hued.sh`)

`_hued_apply` becomes:

- If `hued` is on `PATH`: run `hued apply` and return. Single source of truth
  for the walk + resolve + emit.
- Otherwise: fall back to the existing inline implementation (preserved
  verbatim), so sourcing `hued.sh` without `hued` installed still works.

During `precmd`, the interactive shell has a real `/dev/tty` equal to the
terminal, so delegating to `hued apply` (which writes to `/dev/tty`) is
equivalent to today's behavior of printing escapes to stdout.

**Caveat (documented in README):** under delegation, `HUED_BACKGROUND` /
`HUED_FOREGROUND` overrides must be **exported** to reach the `hued apply`
subprocess. direnv/mise already export them. A hand-set, non-exported shell
variable would only be honored by the inline fallback. This is the one
behavioral edge introduced by delegation.

## Testing

bats (`test/`):

- `hued apply` with `HUED_TTY=<tmpfile>` emits correct OSC bytes for:
  - 6-hex background / foreground
  - named color resolved via `hued-names.sh`
  - `none` → reset escape (`\e]111;` / `\e]110;`)
  - missing channel → reset escape
  - `HUED_BACKGROUND` / `HUED_FOREGROUND` env override beats the file
  - nearest-ancestor walk (color defined two dirs up)
- `hued apply` writes nothing and exits 0 when the target is unopenable
  (e.g. `HUED_TTY=/nonexistent/dir/tty`).
- `set`, `unset`, `mod`, `fork`, `unpack` each repaint after mutating
  (assert via `HUED_TTY=<tmpfile>`), and still print their status message.

No new pytest coverage (picker is unaffected).

## Out of scope

- Making `!hued set` inside Claude Code repaint the user's real terminal —
  impossible by construction (no fd reaches the emulator).
- An opt-out flag / `HUED_NO_APPLY` env var (YAGNI).
- Changing color resolution or the `pastel` dependency for other commands.
