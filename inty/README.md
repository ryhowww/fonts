# Inty

Inter, made ours. A 2-axis **variable font** (wght 100–900, opsz 14–32) derived
from InterVariable 4.001 with three changes baked in as the defaults:

1. **Square punctuation** — rsms's own ss07 set (square tittles on i/j, square
   period/colon/semicolon/!/?/ellipsis/comma, square dieresis + dot accents on
   250+ accented glyphs), frozen on. Plus hand-squared dots on ¡ ¿ ÷ which ss07
   misses.
2. **Single-story a** — rsms's cv11, frozen on (including all accented a forms).
3. **Straight lowercase t** — the curved foot removed; straight vertical stem,
   stock crossbar. Custom outline surgery across the full design space (also
   applied to the compact-t alternate). This glyph does not exist in stock Inter.

Stock `y`, stock quotes, stock everything else. All of Inter's OpenType features
remain live and toggleable — notably `ss03` (round quotes & commas back),
`ss08` (square quotes), `tnum`, `case`, `zero`.

## Files

| File | Use |
|------|-----|
| `Inty-Variable.woff2` (344 KB) | Web, full glyph set |
| `Inty-Variable-subset.woff2` (142 KB) | Web, Latin + punctuation (use this for sites) |
| `Inty-Variable.ttf` (858 KB) | Desktop install / design tools (Figma etc.) |
| `inty.css` | @font-face declaration |
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

- **No italic yet** — InterVariable-Italic hasn't been run through the build.
- License: SIL OFL 1.1 (Inter, Copyright 2020 The Inter Project Authors),
  renamed per OFL. Free for anything, don't sell it standalone.
- Sibling of `../bitsy/` (static Inter Display cut w/ square tittles + straight
  y). Inty keeps stock y, adds the straight t and single-story a, and is
  variable. Build workshop: `/Users/x/claude/inty-vf/` (local).
