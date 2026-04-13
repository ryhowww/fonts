---
name: font-modification
version: 1.0.0
owner: ryan
category: fonts
tags: [typography, fonttools, glyph-editing, woff2, webfonts]
when_to_use: When modifying glyph shapes in an existing font — replacing curves with rectangles, straightening strokes, swapping tails, adjusting heights, or any contour-level surgery.
when_not_to_use: When generating entirely new fonts from scratch or when the task is CSS-only (font-feature-settings, variable font axes). Not for font hosting/deployment — that's a theme task.
requires: [python3, fonttools, brotli]
---

# Font Modification

## Purpose

Modify existing open-source fonts (Inter, Poppins, etc.) at the glyph level using Python and fonttools. Produce renamed custom variants with specific letter modifications (shape changes, dot styles, proportional adjustments) shipped as subset WOFF2 webfonts.

## When to Use This Skill

- When replacing circular dots with rectangular ones (i, j, period, colon, !, ?, etc.)
- When modifying a specific letter's shape (y descender, Q tail, t height)
- When adjusting font metrics (cap height, dot alignment, sidebearings)
- When subsetting a font to a specific character set for performance
- When building a new custom font variant from an existing base

## When NOT to Use This Skill

- Don't use for CSS-level font feature toggles (font-feature-settings, font-variant)
- Don't use for variable font axis manipulation at runtime
- Don't use for generating weight variants from scratch (algorithmic bold generation is experimental — see Questrial POC in `/Users/x/claude/questrial/`)

## Critical Lessons Learned

These are hard-won rules from real debugging sessions. Follow them every time.

### 1. Never trust composite offsets — decompose to flat outlines

**Problem:** Composite glyphs (like `i` = `dotlessi` + `uni0307`) have per-component x/y offsets that vary by weight. Modifying the referenced glyph (e.g., making uni0307 rectangular) and zeroing offsets produces misaligned results because the offsets existed to center a wider circle over a narrower stem.

**Rule:** When modifying a dot or component that's referenced by a composite glyph, **decompose the composite into flat outlines** and place coordinates directly. No composite offsets to go wrong.

```python
# WRONG: modify uni0307 and zero the composite offset
# RIGHT: decompose i into [dot_contour] + [stem_contour] as flat outlines
i_g.numberOfContours = len(new_ends)
i_g.components = None
i_g.program = Program()  # required for decomposed glyphs
i_g.coordinates = GlyphCoordinates(new_coords)
i_g.flags = bytes(new_flags)
i_g.endPtsOfContours = new_ends
```

**Don't forget `Program()`** — decomposed glyphs need an empty instruction program or fonttools crashes on save with `AttributeError: 'Glyph' object has no attribute 'program'`.

### 2. Use geometry detection, not point indices

**Problem:** Point indices shift between weights (Thin might have 21 points, Regular 20, SemiBold 19 for the same glyph). Hardcoded indices break across the weight range.

**Rule:** Find structural landmarks by their geometric properties:
- Top of letter: `max(c[1] for c in coords)`
- Crossbar levels: y-values with 4+ ON-curve points
- Stem edges: x-values at crossbar levels, sorted

```python
# WRONG: stem_left_x = coords[11][0]
# RIGHT: find by geometry
y_groups = {}
for i, (x, y) in enumerate(coords):
    if flags[i] & 1:
        y_groups.setdefault(y, []).append(x)
crossbar_ys = sorted([y for y, xs in y_groups.items() if len(xs) >= 4], reverse=True)
```

### 3. Save original metrics before modifying the glyph

**Problem:** If you calculate `orig_rsb = orig_aw - g.xMax` after already writing new coordinates to `g`, you're measuring the new shape, not the original.

**Rule:** Capture advance width, LSB, and RSB from `hmtx` and `g.xMax` **before any coordinate changes**.

### 4. Dot width must match stem width exactly

**Problem:** The original circular dot is wider than the stem (by 26-62 units in Inter). A rectangular dot at circle bounds is too wide.

**Rule:** Get stem width from `dotlessi` (or equivalent stem-only glyph). Set dot width = stem width. For the i dot, anchor the dot top to the `l` ascender height so i dot, j dot, and l all align.

### 5. Anchor dots to real landmarks, not arbitrary centers

**Rule for i/j dots:** Top of dot = top of `l` (ascender height). Work backward: `dot_y_center = l_top - dot_h / 2`.

**Rule for period:** Bottom at y=0 (baseline). Top at y=dot_h.

**Rule for colon:** Bottom dot = period (at baseline). Top dot top = t crossbar top.

**Rule for semicolon:** Top dot matches colon top dot exactly. Comma top aligns with colon bottom dot top.

### 6. Per-weight calculations, not global constants

**Problem:** A fixed shift value (e.g., 25 units for the y junction) works for Regular but destroys the left arm at ExtraLight and is insufficient at Black.

**Rule:** Calculate weight-specific values dynamically. For the y junction shift, binary-search for the minimum shift that places the junction at y >= 0.

### 7. Inter Display vs Inter Text

Inter ships two optical size variants:
- **Inter Text** (opsz=14): thicker strokes, more open, slanted t tab. For body text.
- **Inter Display** (opsz=32): thinner, crisper, dead vertical t. For headings.

The specimen sites (rsms.me/inter, Google Fonts) show the variable font with auto optical sizing, which renders as Display at large preview sizes. **Build from InterDisplay** static files to match what users see on specimen sites.

Static files location: `inter-source/extras/ttf/InterDisplay-{Weight}.ttf`

### 8. Font renaming checklist

When renaming a font family, update these name table IDs:
- 0: Copyright (add modification note)
- 1: Family name
- 3: Unique ID (`{FamilyNoSpaces}-{Weight}`)
- 4: Full name (`{Family} {Subfamily}`)
- 6: PostScript name
- 16: Typographic family
- 17: Typographic subfamily

Set for both platform IDs 1 (Mac) and 3 (Windows).

## How It Works

### Setup

```bash
pip3 install fonttools brotli
```

### Build Script Pattern

Every font variant has a `build.py` at its root that:

1. Reads source TTFs (one per weight)
2. Applies glyph modifications in order
3. Renames the font family
4. Saves modified TTFs
5. Subsets to Latin and exports WOFF2

```python
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
from fontTools.ttLib.tables.ttProgram import Program
from fontTools import subset
```

### Replacing a circular contour with a rectangle

```python
def replace_dot_contour(g, contour_idx, x_center, y_bottom, rect_w, rect_h):
    """Replace one circular contour with a rectangle."""
    coords = list(g.coordinates)
    flags_list = list(g.flags)
    ends = list(g.endPtsOfContours)

    c_start = 0 if contour_idx == 0 else ends[contour_idx - 1] + 1
    c_end = ends[contour_idx]

    new_dot = [
        (round(x_center - rect_w / 2), y_bottom),
        (round(x_center - rect_w / 2), y_bottom + rect_h),
        (round(x_center + rect_w / 2), y_bottom + rect_h),
        (round(x_center + rect_w / 2), y_bottom),
    ]

    before = list(coords[:c_start])
    after = list(coords[c_end + 1:])
    before_f = list(flags_list[:c_start])
    after_f = list(flags_list[c_end + 1:])

    all_coords = before + new_dot + after
    all_flags = before_f + [1, 1, 1, 1] + after_f

    old_len = c_end - c_start + 1
    delta = 4 - old_len
    new_ends = []
    for i, e in enumerate(ends):
        if i < contour_idx:
            new_ends.append(e)
        elif i == contour_idx:
            new_ends.append(c_start + 3)
        else:
            new_ends.append(e + delta)

    return all_coords, all_flags, new_ends
```

### Subsetting to WOFF2

```python
def subset_font(input_path, output_path):
    subsetter = subset.Subsetter()
    subsetter.populate(unicodes=range(0x0000, 0x024F + 1))  # Latin
    font = TTFont(input_path)
    subsetter.subset(font)
    font.flavor = "woff2"
    font.save(output_path)
    font.close()
```

## Inputs

| Input | Required | Description |
|-------|----------|-------------|
| Source TTFs | Yes | Original font files (one per weight) |
| Modification spec | Yes | Which glyphs to change and how |
| Family name | Yes | New font family name to avoid conflicts |
| Character subset | No | Unicode ranges to include (default: Latin U+0000-024F) |

## Outputs

| Output | Location | Description |
|--------|----------|-------------|
| Modified TTFs | `output/ttf/` | Full modified font files per weight |
| WOFF2 files | `output/woff2/` | Subset compressed webfonts (~8-34KB each) |
| CSS file | `{font}.css` | @font-face declarations for all weights |
| Preview HTML | `output/preview.html` | Browser comparison page (modified vs original) |

## Current Font Variants

| Font | Base | Repo path | Weights | Key modifications |
|------|------|-----------|---------|-------------------|
| Pops | Poppins | `fonts/pops/` | 100-900 + italic | Straight t, rect dots, Q tail, scaled caps |
| Pips | Pops subset | `fonts/pips/` | 200-800 + italic | English-only charset (~7.5KB/weight) |
| Nter | Inter Display | `fonts/nter/` | 200-900 | Angled y, rect dots, raised t, aligned punctuation |

## References

- fonttools docs: https://fonttools.readthedocs.io/
- Inter source: https://github.com/rsms/inter
- Poppins source: https://github.com/google/fonts/tree/main/ofl/poppins
- SIL Open Font License: https://openfontlicense.org/
- Working directories: `/Users/x/claude/poppins-custom/`, `/Users/x/claude/inty/`, `/Users/x/claude/inter-straight/`
