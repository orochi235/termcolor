# Adjust syntax and expanded color names

Design for two changes to `hued`: a reworked `mod`/`adjust` grammar, and a
~5,700-name color vocabulary replacing the current 676 X11 entries. Written for
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

Absolute assignment is new capability, not sugar: it maps to `pastel set
<property> <value> <color>`, which hued does not currently expose.

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
| [meodai/color-names](https://github.com/meodai/color-names) `colornames.bestof.csv` | 4,958 | MIT |

Union: **5,709 names**. `hued-names.sh` grows 14 KB -> ~131 KB.

The current source, X11 `rgb.txt`, is dropped. Its 676 entries are 519 numbered
variants (`azure1..4`, `gray0..100`) plus 157 names, of which 148 are exactly the
CSS set and 9 are X11-only leftovers (`webgray`, `webgreen`, `webgrey`,
`webmaroon`, `webpurple`, `navyblue`, `violetred`, `lightslateblue`,
`lightgoldenrod`). Keeping the CSS 148 as a hardcoded list removes the
`rgb.txt` fetch from the generator and one source of drift — the list has not
changed since `rebeccapurple` was added in 2014.

### Precedence: longer list wins

Applied in order CSS -> xkcd -> meodai, each overwriting the last. CSS therefore
supplies only the 41 names no other source has; 76 of its 148 values are
overridden.

Six canonical keywords move: `green` `#008000` -> `#00ff00`, `lime` `#00ff00` ->
`#aaff32`, `navy` `#000080` -> `#01153e`, and small shifts in `aqua`, `fuchsia`,
`olive`. `gray`, `red`, `blue`, `black`, `white`, `yellow`, `teal`, `purple`,
`maroon` and `silver` are unaffected.

Hex is primary, so the blast radius is small: since 7822786 hued writes hex with
the name as an inline comment, and precedence affects only what `hued set <name>`
resolves at input time.

The exception is read-time name resolution, which the resolvers still support —
`_hued_resolve_hex` in `bin/hued`, plus `hued.sh:23` and `hued.fish:15`. A
hand-edited `.hued`, or one written before 7822786, can still carry
`background=navy` and would repaint to `#01153e` rather than `#000080`. Nothing
hued has written recently is affected.

### Key normalization

Keys are lowercased with spaces, hyphens and apostrophes stripped, so
`hued set "emerald bliss"` and `hued set emeraldbliss` are the same lookup.
One intra-source collision exists (`stardust` in meodai); first entry wins.

### One generator, two outputs

`hued-names.sh` (bash associative array) and `src/picker/names.py` (Python dict)
today hold the same 676 entries produced by two different generators, and stay
in sync only by luck. `scripts/names_to_py.py` is already dead: its input
`src/picker/lib/names.ts` does not exist on `main`.

`scripts/generate-names.sh` becomes the single generator emitting both files.
`scripts/names_to_py.py` is deleted.

### Reverse lookup

`src/picker/colors.py:179 nearest_name()` already does nearest-color naming for
the picker. At 5,709 names it can name essentially any hex, which makes two
things worth doing:

- Expose it on the CLI as `hued get [bg|fg] --name`.
- The inline-comment naming in `_hued_set_key` currently almost never fires
  (only on exact-name input); with a dense list it can name picker-chosen hex
  values too.

`nearest_name()` is a linear scan run per render. Going 676 -> 5,709 comparisons
needs a precomputed structure — bucket by quantized RGB, or precompute the
name list into a spatial index at generation time — so the live picker does not
regress.

## Testing

- `test/hued.bats`: each negative form and its equivalent positive; bare-number
  percent equivalence; the `(0,1)` ambiguity error; channel-omitted forms;
  absolute vs relative signed ops; a chain applying all transforms with exactly
  one file write.
- `test/hued.bats`: `hued set emerald` resolves; a multi-word name resolves;
  the six shifted keywords resolve to their new values; the 41 CSS-only names
  still resolve.
- `tests/picker/`: `nearest_name()` returns identical results before and after
  the index change for a fixed sample, and stays within budget at 5,709 names.
- Generator: `hued-names.sh` and `src/picker/names.py` contain identical
  key/value sets.
