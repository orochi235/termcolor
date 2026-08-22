# Adjust syntax and expanded color names

Design for two changes to `hued`: a reworked `mod`/`adjust` grammar, and a
987-name color vocabulary replacing the current 676 X11 entries. Written for
whoever implements it; assumes familiarity with `bin/hued` and `pastel`.

## Part 1 — `mod` / `adjust` grammar

Today (`bin/hued:201-244`) the form is fixed at `hued mod <bg|fg> <op> [args]`,
one op per invocation, and negative arguments fail two ways: `_hued_parse_amount`
matches only `^[0-9.]+%$`, and `pastel` rejects a bare leading-dash value
(`error: unexpected argument '-0'`).

New grammar:

```
hued mod [bg|fg] <op> [args...] [<op> [args...]]...
```

### Channel is optional

Defaults to `background`, matching `hued set <color>`. Unambiguous because no op
is named `bg` or `fg`: if the token after `mod` is a known op, the channel is
implied.

### Negatives flip the verb

hued inverts the operation rather than forwarding a negative to `pastel`:

| Written | Executed |
|---|---|
| `darken -10%` | `lighten 10%` |
| `lighten -10%` | `darken 10%` |
| `saturate -10%` | `desaturate 10%` |
| `desaturate -10%` | `saturate 10%` |
| `rotate -30deg` | `pastel rotate -- -30` |

`rotate` has no inverse verb, so it is the one case that forwards a negative —
which requires the `--` separator that is missing today. `mix` has no meaningful
inverse; a negative ratio is an error. `complement` and `to-gray` take no args.

### Bare numbers are percent

`darken 20` == `darken 20%`, consistent with `rotate 30` already meaning 30
degrees. This changes the meaning of a bare value that was previously read as a
`pastel` fraction, so values in the open interval `(0,1)` are rejected rather
than silently reinterpreted:

```
$ hued mod bg darken 0.2
hued mod: darken 0.2 is ambiguous — write "0.2%" or "20%"
```

Values `>= 1` were already nonsense as fractions (pastel clamps), so reading
them as percent is a strict improvement with no ambiguous range.

The rule is uniform across every amount-taking op, including `mix`'s ratio and
the absolute forms of `lightness` / `saturation`. That retires the README's
`hued mod bg mix '#0000ff' 0.25`, which now errors and directs the reader to
`25%`; update the example rather than exempting `mix`.

### Signed shorthand ops

Three new ops where the sign selects relative vs absolute:

```
hued mod bg lightness +10%    # relative — same as lighten 10%
hued mod bg lightness 40%     # absolute — pastel set lightness 0.4
hued mod bg saturation -25%
hued mod bg hue +30deg
```

Absolute assignment is new capability, not sugar: it maps to `pastel set`, which
hued does not currently expose. The property names matter — `pastel set
lightness` is *Lab* lightness on a 0-100 scale, so `set lightness 0.4` renders
near-black. `darken`/`lighten`/`saturate`/`desaturate` all operate on HSL, so
the absolute forms must use the HSL properties to stay consistent with them:

| Written | Executed |
|---|---|
| `lightness 40%` | `pastel set hsl-lightness 0.4` |
| `lightness +10%` | `pastel lighten 0.1` |
| `saturation 90%` | `pastel set hsl-saturation 0.9` |
| `saturation -25%` | `pastel desaturate 0.25` |
| `hue 200deg` | `pastel set hsl-hue 200` |
| `hue +30deg` | `pastel rotate -- 30` |

Verified: `pastel set hsl-lightness 0.4 '#336699'` returns `#336699` unchanged,
because that color is already at HSL L=40%.

### Chained ops

One parse pass over the token stream, each op consuming its arity, then a single
`.hued` write and a single repaint:

```
hued mod bg darken 10% rotate 30deg desaturate 5%
```

`mix` is the only variadic op (`mix <color> [ratio]`). In a chain it takes the
ratio only when the next token parses as an amount; op names never parse as
amounts, so this is decidable without lookahead beyond one token.

## Part 2 — color names

### Sources

| Source | Names | License |
|---|---|---|
| CSS Color Module Level 4 named colors | 148 | spec, no license needed |
| [xkcd color survey](https://xkcd.com/color/rgb.txt) | 934 | CC0 |

Union: **987 names**. `hued-names.sh` grows 14 KB -> ~22 KB.

meodai/color-names was evaluated and rejected: at 4,958 entries it is a paint
catalog, not a color vocabulary ("Emerald Ice Palace", "Emerald Whispers"). The
names are not ones anyone would type, and they crowd the reverse lookup with
noise.

The current source, X11 `rgb.txt`, is dropped. Its 676 entries are 519 numbered
variants (`azure1..4`, `gray0..100`) plus 157 names, of which 148 are exactly the
CSS set. Keeping the CSS 148 as a hardcoded list removes the `rgb.txt` fetch from
the generator and one source of drift — the list has not changed since
`rebeccapurple` was added in 2014.

### Precedence: CSS wins

CSS supplies its 148 authoritatively; xkcd supplies the other 839. 95 names appear
in both lists and 92 of them disagree. xkcd is a
perception survey, so left to win ties it reads `red` as `#e50000`, `gray` as
`#bebebe` and `blue` as `#0343df` — defensible as survey data, wrong for a tool
whose whole job is setting terminal colors. Under CSS-wins, no CSS value moves.

### What changes for existing files

Hex is primary — since 7822786 hued writes hex with the name as an inline
comment — so this only affects name resolution at read time, which the resolvers
still support (`_hued_resolve_hex` in `bin/hued`, `hued.sh:23`, `hued.fish:15`).
A hand-edited or pre-7822786 `.hued` naming a color is the only exposure:

- **526 keys stop resolving:** the 519 numbered variants plus `lightgoldenrod`,
  `lightslateblue`, `webgray`, `webgreen`, `webgrey`, `webmaroon`, `webpurple`.
  A `.hued` saying `background=gray50` will no longer resolve and that channel
  goes unset.
- **2 keys change value:** `navyblue` `#000080` -> `#001146` and `violetred`
  `#d02090` -> `#a50055`, both now supplied by xkcd's "navy blue" / "violet red".

Everything else resolves exactly as it does today.

### The `-x` flag

`-x` makes xkcd the preferred vocabulary for the 92 names where the two sources disagree.
It is a per-invocation flag with no env var or `.hued` equivalent:

```
hued set red        -> #ff0000   (CSS)
hued -x set red     -> #e50000   (xkcd)
hued set emerald    -> #01a049   (xkcd-only; -x changes nothing)
```

The generator emits the 92 conflicting values a second time under a namespaced key in the
same file:

```bash
declare -A _HUED_NAMES=(
  [red]=#ff0000
  [emerald]=#01a049
  ...
  [xkcd:red]=#e50000
  [xkcd:gray]=#bebebe
)
```

This preserves the existing grep-based lookup: `grep '\[red\]='` cannot match
`[xkcd:red]=`, so `hued.sh:23` and `hued.fish:15` need no change. With `-x`,
`_hued_resolve_hex` tries `[xkcd:<name>]=` first and falls back to `[<name>]=`.
Cost is ~2 KB.

`-x` is a global flag parsed before the subcommand (`hued -x set red`), because
hued's dispatcher switches on `$1` and a per-subcommand flag would have to be
added to each arm.

`-x` also flips reverse lookup, so `hued -x get bg --name` and `hued -x -i`
prefer xkcd names for a given hex. In Python this means `src/picker/names.py`
exports both `NAMED_COLORS` (CSS-wins) and `XKCD_OVERRIDES` (the 95), with
callers merging the second over the first when `-x` is set.

### Key normalization

Keys are lowercased with spaces, hyphens and apostrophes stripped, so
`hued set "baby poop green"` and `hued set babypoopgreen` are the same lookup.
688 of xkcd's 934 names are multi-word, so this is the common case, not an edge
case. No intra-source key collisions exist after normalization.

### One generator, two outputs

`hued-names.sh` (bash associative array) and `src/picker/names.py` (Python dict)
today hold the same 676 entries produced by two different generators, and stay
in sync only by luck. `scripts/names_to_py.py` is already dead: its input
`src/picker/lib/names.ts` does not exist on `main`.

`scripts/generate-names.sh` becomes the single generator emitting both files.
`scripts/names_to_py.py` is deleted.

### Reverse lookup

`src/picker/colors.py:179 nearest_name()` already does nearest-color naming for
the picker. At 987 names it can name far more hex values than today, which makes two
things worth doing:

- Expose it on the CLI as `hued get [bg|fg] --name`.
- The inline-comment naming in `_hued_set_key` currently almost never fires
  (only on exact-name input); with a dense list it can name picker-chosen hex
  values too.

`nearest_name()` is a linear scan run per render. 676 -> 987 comparisons is a
1.5x increase, not the 8x the meodai list would have caused, so no index is
needed — but the picker benchmark should confirm the per-render cost before and
after.

## Testing

- `test/hued.bats`: each negative form and its equivalent positive; bare-number
  percent equivalence; the `(0,1)` ambiguity error; channel-omitted forms;
  absolute vs relative signed ops; a chain applying all transforms with exactly
  one file write.
- `test/hued.bats`: `hued set emerald` resolves to `#01a049`; a multi-word name
  (`hued set "baby poop green"`) resolves; every canonical CSS keyword still
  resolves to its CSS value (`red` -> `#ff0000`, `gray` -> `#808080`); a dropped
  numbered variant (`gray50`) no longer resolves.
- `tests/picker/`: `nearest_name()` returns a known name for a known hex at 987
  entries, and per-render cost stays within budget.
- Generator: `hued-names.sh` and `src/picker/names.py` contain identical
  key/value sets.
