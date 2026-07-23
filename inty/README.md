# Inty

Inter, made ours. A 2-axis **variable font** (wght 100–900, opsz 14–32) derived
from InterVariable 4.001 with three changes baked in as the defaults:

1. **Square punctuation** — rsms's own ss07 set (square tittles on i/j, square
   period/colon/semicolon/!/?/ellipsis/comma, square dieresis + dot accents on
   250+ accented glyphs), frozen on. Plus hand-squared dots on ¡ ¿ ÷ which ss07
   misses.
2. **Single-story a** — rsms's cv11, frozen on (including all accented a
   forms). The italic needs no freeze: Inter Italic's a is single-story natively.
3. **Straight lowercase t** — the curved foot removed; straight vertical stem,
   stock crossbar. Custom outline surgery across the full design space (also
   applied to the compact-t alternate). This glyph does not exist in stock Inter.

Stock `y`, stock quotes, stock everything else. All of Inter's OpenType features
remain live and toggleable — notably `ss03` (round quotes & commas back),
`ss08` (square quotes), `tnum`, `case`, `zero`.

## Files

| File | Use |
|------|-----|
| `Inty-Web.woff2` (46 KB) | **Production sites** — English-only + smart punctuation, hints stripped |
| `Inty-Italic-Web.woff2` (50 KB) | Production italic, same subset |
| `Inty-Variable.woff2` (344 KB) | Web, full glyph set |
| `Inty-Variable-subset.woff2` (142 KB) | Web, Latin + punctuation (accented chars) |
| `Inty-Italic-Variable.woff2` (378 KB) | Web italic, full glyph set |
| `Inty-Italic-Variable-subset.woff2` (156 KB) | Web italic, Latin + punctuation |
| `Inty-Variable.ttf` / `Inty-Italic-Variable.ttf` | Desktop install / design tools (Figma etc.) |
| `inty.css` | @font-face declarations (roman + italic) |
| `index.html` | Self-contained specimen/preview (fonts embedded) |
| `build.py` | Reproducible build (needs local InterVariable.ttf + fontTools) |

## Usage

```css
@font-face {
  font-family: "Inty";
  font-style: normal;
  font-weight: 100 900;
  font-display: swap;
  src: url("Inty-Variable-subset.woff2") format("woff2");
}
```

Weight is fully variable (`font-weight: 640` works). Optical size follows
`font-optical-sizing: auto` (default): text sizes get the Text cut, headline
sizes the Display cut.

## Notes

- Italic: same treatment (ss07 frozen, straight t as a parallelogram at the
  9.4° italic angle, squared ¡ ¿ ÷). Use normal CSS `font-style: italic`.
- The `-Web` files keep both variable axes and the useful features (ss03, ss08,
  tnum, zero, case, kern, calt) but drop everything else: ASCII + curly
  quotes/dashes/ellipsis/¡¿©®™°·•×÷€£¥¢§ only, no hinting, no small caps or
  fraction machinery. Accented characters fall back to the next font in the
  stack — swap in the `-subset` files if a page needs them.
- License: SIL OFL 1.1 (Inter, Copyright 2020 The Inter Project Authors),
  renamed per OFL. Free for anything, don't sell it standalone.
- Sibling of `../bitsy/` (static Inter Display cut w/ square tittles + straight
  y). Inty keeps stock y, adds the straight t and single-story a, and is
  variable. Build workshop: `/Users/x/claude/inty-vf/` (local).
