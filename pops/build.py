#!/usr/bin/env python3
"""
Build custom Poppins variant with:
  1. Straight vertical t (no curved foot — Questrial-style)
  2. Rectangular dot on i and j
  3. Straight j descender (no hook)
  4. Q with crossing diagonal tail (Google Sans Flex style)

Works across all 9 weights. Preserves all other glyphs unchanged.
"""
import math
import os
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
from fontTools import subset

FAMILY_NAME = "Pops"
WEIGHTS = [
    ("Thin", 100, False), ("ExtraLight", 200, False), ("Light", 300, False),
    ("Regular", 400, False), ("Medium", 500, False), ("SemiBold", 600, False),
    ("Bold", 700, False), ("ExtraBold", 800, False), ("Black", 900, False),
    ("Italic", 400, True),
]


def straighten_t(font):
    """Replace Poppins t with a straight vertical stem + crossbar.

    Detects landmarks by geometry rather than point indices so it works
    across all weights (19-21 points, varying topology).

    Detection strategy:
      - Find all y-values that have 4+ ON-curve points: these are the
        crossbar-top and crossbar-bottom levels.
      - The highest y with exactly 2 ON points is the ascender.
      - At each crossbar y, the 4 x-values (sorted) give us:
        crossbar-left, stem-left, stem-right, crossbar-right.
    """
    glyf = font['glyf']
    g = glyf['t']
    coords = list(g.coordinates)
    flags = list(g.flags)

    # Group ON-curve points by y-value
    y_groups = {}
    for i, (x, y) in enumerate(coords):
        if flags[i] & 1:
            y_groups.setdefault(y, []).append(x)

    # Crossbar levels: y-values with 4+ ON points
    crossbar_ys = sorted([y for y, xs in y_groups.items() if len(xs) >= 4], reverse=True)
    if len(crossbar_ys) < 2:
        print("  WARNING: could not find crossbar levels")
        return False

    crossbar_top_y = crossbar_ys[0]
    crossbar_bottom_y = crossbar_ys[1]

    # At crossbar level, extract the 4 x-values
    xs_top = sorted(y_groups[crossbar_top_y])
    xs_bot = sorted(y_groups[crossbar_bottom_y])

    crossbar_left_x = xs_top[0]
    stem_left_x = xs_top[1]
    stem_right_x = xs_top[2]
    crossbar_right_x = xs_top[3]

    # Ascender: highest y with exactly 2 ON points (stem left/right)
    ascender_y = max(y for y, xs in y_groups.items() if len(xs) == 2 and y > crossbar_top_y)

    # Save original metrics before modifying the glyph
    hmtx = font['hmtx']
    cmap = font.getBestCmap()
    t_name = cmap[ord('t')]
    orig_aw, orig_lsb = hmtx.metrics[t_name]
    orig_rsb = orig_aw - g.xMax

    # Re-center the crossbar on the stem.
    # Original Poppins crossbar is asymmetric (wider on the right because of the foot).
    crossbar_width = crossbar_right_x - crossbar_left_x
    stem_center = (stem_left_x + stem_right_x) / 2
    crossbar_left_x = round(stem_center - crossbar_width / 2)
    crossbar_right_x = round(stem_center + crossbar_width / 2)

    # Build new contour: clean rectangle stem + crossbar, no curves
    new_coords = [
        (stem_right_x, 0),
        (stem_right_x, crossbar_bottom_y),
        (crossbar_right_x, crossbar_bottom_y),
        (crossbar_right_x, crossbar_top_y),
        (stem_right_x, crossbar_top_y),
        (stem_right_x, ascender_y),
        (stem_left_x, ascender_y),
        (stem_left_x, crossbar_top_y),
        (crossbar_left_x, crossbar_top_y),
        (crossbar_left_x, crossbar_bottom_y),
        (stem_left_x, crossbar_bottom_y),
        (stem_left_x, 0),
    ]
    new_flags = [1] * 12

    g.coordinates = GlyphCoordinates(new_coords)
    g.flags = bytes(new_flags)
    g.endPtsOfContours = [11]
    g.numberOfContours = 1
    g.recalcBounds(glyf)

    # Apply original LSB and RSB to the new crossbar extents
    lsb = orig_lsb
    rsb = orig_rsb
    # Shift the entire glyph so crossbar_left_x lands at lsb
    shift_x = lsb - crossbar_left_x
    new_coords = [(x + shift_x, y) for x, y in new_coords]
    g.coordinates = GlyphCoordinates(new_coords)
    g.recalcBounds(glyf)

    aw = g.xMax + rsb
    hmtx.metrics[t_name] = (aw, lsb)

    return True


def get_i_stem_bounds(font):
    """Get the i stem left/right x from the i glyph (always a clean rectangle)."""
    glyf = font['glyf']
    cmap = font.getBestCmap()
    g = glyf[cmap[ord('i')]]
    coords = list(g.coordinates)
    ends = g.endPtsOfContours

    # Stem is contour 1 (after dot), always 4 ON-curve rectangle points
    stem_coords = coords[ends[0] + 1:]
    stem_left = min(c[0] for c in stem_coords)
    stem_right = max(c[0] for c in stem_coords)
    return stem_left, stem_right


def make_rect_dot(font, glyph_name):
    """Replace the round dot (contour 0) with a rectangular one.

    Uses the i stem width as reference (not the j stem which includes
    hook coordinates that skew the bounds).
    """
    glyf = font['glyf']
    g = glyf[glyph_name]
    coords = list(g.coordinates)
    flags = list(g.flags)
    ends = g.endPtsOfContours

    # Dot is contour 0 (ends[0] = 11)
    dot_end = ends[0]
    dot_coords = coords[:dot_end + 1]

    # Get dot vertical bounds from actual points
    dot_bottom = min(c[1] for c in dot_coords)
    dot_top = max(c[1] for c in dot_coords)

    # Get stem width from the i glyph (reliable rectangle)
    stem_left, stem_right = get_i_stem_bounds(font)
    stem_width = stem_right - stem_left

    # Rectangle dot: match stem width, keep vertical center of original dot
    dot_center_y = (dot_top + dot_bottom) / 2
    dot_height = round(stem_width * 1.05)  # slightly taller than wide

    new_dot = [
        (stem_left, round(dot_center_y - dot_height / 2)),
        (stem_left, round(dot_center_y + dot_height / 2)),
        (stem_right, round(dot_center_y + dot_height / 2)),
        (stem_right, round(dot_center_y - dot_height / 2)),
    ]
    new_dot_flags = [1, 1, 1, 1]

    # Rebuild: new dot + original stem contour(s)
    remaining_coords = coords[dot_end + 1:]
    remaining_flags = flags[dot_end + 1:]

    all_coords = new_dot + remaining_coords
    all_flags = new_dot_flags + list(remaining_flags)

    new_ends = [3]
    offset = 4 - (dot_end + 1)
    for old_end in ends[1:]:
        new_ends.append(old_end + offset)

    g.coordinates = GlyphCoordinates(all_coords)
    g.flags = bytes(all_flags)
    g.endPtsOfContours = new_ends
    g.numberOfContours = len(new_ends)
    g.recalcBounds(glyf)

    return True


def straighten_j(font):
    """Replace the j's hooked stem with a straight vertical descender.

    Uses the i stem bounds for width (avoids hook coordinates).
    Finds stem top y from the highest point in the stem contour.
    Descender depth preserved from the original glyph's yMin.

    NOTE: This runs AFTER make_rect_dot, so the dot contour is already
    a 4-point rectangle (ends[0] = 3).
    """
    glyf = font['glyf']
    g = glyf['j']
    coords = list(g.coordinates)
    flags = list(g.flags)
    ends = g.endPtsOfContours

    # After make_rect_dot, dot is 4 pts (ends[0] = 3)
    dot_end = ends[0]

    # Get stem width from the i glyph (clean rectangle)
    stem_left_x, stem_right_x = get_i_stem_bounds(font)

    # Stem top y: the highest y in the stem contour
    stem_coords = coords[dot_end + 1:]
    stem_top_y = max(c[1] for c in stem_coords)

    # Descender depth from original glyph bounds
    desc_y = min(c[1] for c in stem_coords)

    # Simple rectangle stem
    new_stem = [
        (stem_right_x, stem_top_y),
        (stem_right_x, desc_y),
        (stem_left_x, desc_y),
        (stem_left_x, stem_top_y),
    ]
    new_stem_flags = [1, 1, 1, 1]

    # Rebuild with current dot (already rectangular) + new stem
    dot_coords = coords[:dot_end + 1]
    dot_flags = flags[:dot_end + 1]

    all_coords = list(dot_coords) + new_stem
    all_flags = list(dot_flags) + new_stem_flags
    new_ends = [dot_end, dot_end + 4]

    g.coordinates = GlyphCoordinates(all_coords)
    g.flags = bytes(all_flags)
    g.endPtsOfContours = new_ends
    g.numberOfContours = 2
    g.recalcBounds(glyf)

    # Match the i glyph's spacing — the straight j should have
    # the same sidebearings as i since the stem is identical.
    hmtx = font['hmtx']
    cmap = font.getBestCmap()
    i_aw, i_lsb = hmtx.metrics[cmap[ord('i')]]
    j_name = cmap[ord('j')]
    hmtx.metrics[j_name] = (i_aw, i_lsb)

    return True


def square_period(font):
    """Replace the round period glyph with a square.

    The period is used by the colon (two periods) and the semicolon
    (period + comma), so this automatically squares the colon dots.
    """
    glyf = font['glyf']
    g = glyf['period']
    coords = list(g.coordinates)

    # Get bounds of the original circle
    x_min = min(c[0] for c in coords)
    x_max = max(c[0] for c in coords)
    y_min = min(c[1] for c in coords)
    y_max = max(c[1] for c in coords)

    # Make it a square with the same center, using the larger dimension
    cx = (x_min + x_max) / 2
    cy = (y_min + y_max) / 2
    size = max(x_max - x_min, y_max - y_min)
    half = size / 2

    new_coords = [
        (round(cx - half), round(cy - half)),
        (round(cx - half), round(cy + half)),
        (round(cx + half), round(cy + half)),
        (round(cx + half), round(cy - half)),
    ]

    g.coordinates = GlyphCoordinates(new_coords)
    g.flags = bytes([1, 1, 1, 1])
    g.endPtsOfContours = [3]
    g.numberOfContours = 1
    g.recalcBounds(glyf)

    return True


def restyle_Q(font):
    """Replace Poppins Q tail with a Google Sans Flex-style crossing diagonal.

    Takes the O glyph (clean oval + counter) and adds a diagonal parallelogram
    tail that crosses through the bottom-right of the oval.

    Tail geometry derived from Google Sans Flex's _tail.Q, normalized to
    the O glyph's bounding box so it scales correctly across all weights.

    The tail center line runs from ~4 o'clock inside the O down to below
    the baseline on the right. Width matches the font's stroke weight.
    """
    glyf = font['glyf']
    cmap = font.getBestCmap()

    # Get the O glyph (clean oval, no tail)
    o_name = cmap[ord('O')]
    g_o = glyf[o_name]
    o_coords = list(g_o.coordinates)
    o_flags = list(g_o.flags)
    o_ends = list(g_o.endPtsOfContours)

    # O bounding box
    ox0, ox1 = g_o.xMin, g_o.xMax
    oy0, oy1 = g_o.yMin, g_o.yMax
    ow = ox1 - ox0
    oh = oy1 - oy0

    # Tail center line endpoints (normalized from Google Sans Flex)
    # Top center (inside O at ~4 o'clock): normalized (0.602, 0.355)
    # Bottom center (below O at ~5 o'clock): normalized (0.867, -0.034)
    top_cx = ox0 + 0.602 * ow
    top_cy = oy0 + 0.355 * oh
    bot_cx = ox0 + 0.867 * ow
    bot_cy = oy0 + (-0.034) * oh

    # Direction and perpendicular vectors
    dx = bot_cx - top_cx
    dy = bot_cy - top_cy
    length = math.sqrt(dx * dx + dy * dy)
    ux, uy = dx / length, dy / length       # unit direction
    px, py = -uy, ux                          # perpendicular (left-hand normal)

    # Tail width = stem width (from i glyph)
    stem_left, stem_right = get_i_stem_bounds(font)
    half_w = (stem_right - stem_left) / 2

    # 4 corner points of the tail parallelogram
    # B (top-left), C (top-right), D (bottom-right), A (bottom-left)
    # Winding: B→C→D→A = CW (same as outer contour)
    B = (round(top_cx - px * half_w), round(top_cy - py * half_w))
    C = (round(top_cx + px * half_w), round(top_cy + py * half_w))
    D = (round(bot_cx + px * half_w), round(bot_cy + py * half_w))
    A = (round(bot_cx - px * half_w), round(bot_cy - py * half_w))

    # Assemble Q: O outer contour + O inner counter + tail
    tail_coords = [B, C, D, A]
    tail_flags = [1, 1, 1, 1]

    all_coords = list(o_coords) + tail_coords
    all_flags = list(o_flags) + tail_flags
    new_ends = list(o_ends) + [len(all_coords) - 1]

    # Write to Q glyph
    q_name = cmap[ord('Q')]
    g_q = glyf[q_name]
    g_q.coordinates = GlyphCoordinates(all_coords)
    g_q.flags = bytes(all_flags)
    g_q.endPtsOfContours = new_ends
    g_q.numberOfContours = len(new_ends)
    g_q.recalcBounds(glyf)

    # Update advance width: keep same as O but add space for tail overshoot
    hmtx = font['hmtx']
    o_aw, o_lsb = hmtx.metrics[o_name]
    # Q advance width: ensure RSB accommodates the tail
    q_rsb = max(D[0], A[0]) - g_q.xMax  # how far tail extends past O
    tail_overshoot = max(0, max(D[0], A[0]) - ox1)
    q_aw = o_aw + tail_overshoot
    hmtx.metrics[q_name] = (q_aw, o_lsb)

    return True


def scale_caps(font):
    """Scale all uppercase letters uniformly by 740/697 in both axes.

    Preserves all stroke proportions perfectly. Letters get ~6% wider.
    Advance widths and LSBs scale proportionally.
    """
    glyf = font['glyf']
    hmtx = font['hmtx']
    cmap = font.getBestCmap()
    scale = 740 / 697

    for ch in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
        gname = cmap.get(ord(ch))
        if not gname:
            continue

        g = glyf[gname]

        if g.numberOfContours <= 0:
            # Composite glyph — scale component offsets
            if g.numberOfContours == -1 and hasattr(g, 'components'):
                for comp in g.components:
                    comp.x = round(comp.x * scale)
                    comp.y = round(comp.y * scale)
            continue

        coords = list(g.coordinates)
        new_coords = [(round(x * scale), round(y * scale)) for x, y in coords]
        g.coordinates = GlyphCoordinates(new_coords)
        g.recalcBounds(glyf)

        aw, lsb = hmtx.metrics[gname]
        hmtx.metrics[gname] = (round(aw * scale), round(lsb * scale))

    # Update OS/2 cap height
    font['OS/2'].sCapHeight = 740

    return True


def rename_font(font, weight_name, weight_value):
    """Rename font family to avoid conflicts."""
    name_table = font['name']

    is_italic = weight_name == "Italic"
    if is_italic:
        subfamily = "Italic"
    elif weight_name == "Regular":
        subfamily = "Regular"
    else:
        subfamily = weight_name

    replacements = {
        0: f"Copyright 2020 The Poppins Project Authors. Modified: {FAMILY_NAME} variant.",
        1: FAMILY_NAME,
        3: f"{FAMILY_NAME}-{weight_name}",
        4: f"{FAMILY_NAME} {subfamily}",
        6: f"{FAMILY_NAME}-{weight_name}",
        16: FAMILY_NAME,
        17: subfamily,
    }

    for name_id, value in replacements.items():
        for plat_id in (1, 3):
            enc_id = 0 if plat_id == 1 else 1
            lang_id = 0 if plat_id == 1 else 0x0409
            name_table.setName(value, name_id, plat_id, enc_id, lang_id)


def subset_font(input_path, output_path):
    """Subset to Latin charset and convert to WOFF2."""
    subsetter = subset.Subsetter()
    subsetter.populate(unicodes=range(0x0000, 0x024F + 1))
    font = TTFont(input_path)
    subsetter.subset(font)
    font.flavor = "woff2"
    font.save(output_path)
    font.close()
    size_kb = os.path.getsize(output_path) / 1024
    print(f"  WOFF2: {output_path.name} ({size_kb:.1f} KB)")


def main():
    output_dir = Path("output")
    ttf_dir = output_dir / "ttf"
    woff2_dir = output_dir / "woff2"
    ttf_dir.mkdir(parents=True, exist_ok=True)
    woff2_dir.mkdir(parents=True, exist_ok=True)

    for weight_name, weight_value, is_italic in WEIGHTS:
        input_path = Path(f"Poppins-{weight_name}.ttf")
        if not input_path.exists():
            print(f"SKIP {weight_name}: {input_path} not found")
            continue

        print(f"\n--- {weight_name} ({weight_value}) ---")
        font = TTFont(str(input_path))

        # Modifications
        ok = straighten_t(font)
        print(f"  t: {'OK' if ok else 'FAIL'}")

        ok = make_rect_dot(font, 'i')
        print(f"  i dot: {'OK' if ok else 'FAIL'}")

        ok = make_rect_dot(font, 'j')
        print(f"  j dot: {'OK' if ok else 'FAIL'}")

        ok = square_period(font)
        print(f"  period: {'OK' if ok else 'FAIL'}")

        ok = restyle_Q(font)
        print(f"  Q tail: {'OK' if ok else 'FAIL'}")

        ok = scale_caps(font)
        print(f"  caps: {'OK' if ok else 'FAIL'}")

        # Rename
        rename_font(font, weight_name, weight_value)

        # Save TTF
        file_slug = f"Pops-{weight_name}"
        ttf_path = ttf_dir / f"{file_slug}.ttf"
        font.save(str(ttf_path))
        font.close()
        print(f"  TTF: {ttf_path.name}")

        # Subset + WOFF2
        woff2_path = woff2_dir / f"{file_slug}.woff2"
        subset_font(ttf_path, woff2_path)

    print("\nDone!")


if __name__ == "__main__":
    os.chdir(Path(__file__).parent)
    main()
