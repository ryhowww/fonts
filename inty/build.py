#!/usr/bin/env python3
"""
Build Inty — Inter with square punctuation + single-story a ON by default,
plus a straight lowercase t. Roman and Italic variable fonts.

Base: InterVariable.ttf / InterVariable-Italic.ttf 4.001
      (2 axes: opsz 14-32, wght 100-900).

What this does, per source font:
  1. FREEZE ss07 "Square punctuation" and cv11 "Single-story a" (roman only;
     the italic has no cv11 — its a is already single-story) by injecting
     their GSUB lookups into the always-on `ccmp` feature. Lookups apply in
     LookupList order, so every chain (case, tf, calt, ss07+cv11 combos)
     behaves exactly as if the user had enabled the features.
  2. SURGERY on glyphs ss07 misses:
     - t, t.1        : curved foot removed -> straight stem. Roman: rectangle.
                       Italic: parallelogram at the font's italic angle (the
                       slant model reproduces Inter's real stem edges exactly).
     - exclamdown(.case), questiondown : round dot -> rsms's ss07 dot shape
                       (copied from exclam.ss07 / question.ss07 and translated
                       to the circle's center — in the italic those dots are
                       slanted parallelograms, so copy-and-place, not rects)
     - divide(.case/.tf/...) : round dots -> period.ss07 dot shape, same way
     Surgery runs across the full 2-axis design space: outlines are computed
     at the 6 corner/default masters and written back as fresh gvar tuples
     mirroring Inter's own variation model.
  3. RENAME family (Inter -> Inty), keep all OpenType features toggleable
     (ss03 round quotes & commas, ss08 square quotes, tnum, case, ...).

Outputs (output/): Inty-Variable[-Italic].ttf + .woff2 (full) +
-subset.woff2 (Latin + punctuation), combined inty.css
"""
import math
import os
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.ttLib.tables.ttProgram import Program
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools import subset

FAMILY = "Inty"
SRC_DIR = "/Users/x/claude/inter-straight/inter-fresh"
OUT = Path(__file__).parent / "output"

BUILDS = [
    # (source, subfamily, output stem, css font-style)
    (f"{SRC_DIR}/InterVariable.ttf", "Regular", f"{FAMILY}-Variable", "normal"),
    (f"{SRC_DIR}/InterVariable-Italic.ttf", "Italic", f"{FAMILY}-Italic-Variable", "italic"),
]

FREEZE_FEATURES = ["ss07", "cv11"]  # square punctuation + single-story a

# Design-space masters: default + corners (Inter's own model: wght 100/400/900
# crossed with opsz 14/32; avar handles the in-between weight bending).
MASTER_LOCS = [
    {"opsz": 14, "wght": 400},   # 0: default (base outline)
    {"opsz": 32, "wght": 400},   # 1
    {"opsz": 14, "wght": 100},   # 2
    {"opsz": 14, "wght": 900},   # 3
    {"opsz": 32, "wght": 100},   # 4
    {"opsz": 32, "wght": 900},   # 5
]
# gvar tuple axes (mirrors Inter's structure), each paired with the delta kind.
TUPLES = [
    ({"opsz": (0, 1, 1)},                          "opsz"),
    ({"wght": (-1.0, -1.0, 0)},                    "wmin"),
    ({"wght": (0, 1.0, 1.0)},                      "wmax"),
    ({"opsz": (0, 1, 1), "wght": (-1.0, -1.0, 0)}, "corner_min"),
    ({"opsz": (0, 1, 1), "wght": (0, 1.0, 1.0)},   "corner_max"),
]


# ---------------------------------------------------------------------------
# Outline helpers
# ---------------------------------------------------------------------------

def get_outline(glyf, name):
    """(coords, flags, ends) for a simple glyph."""
    g = glyf[name]
    assert not g.isComposite(), f"{name} is composite"
    return list(g.coordinates), list(g.flags), list(g.endPtsOfContours)


def contours_of(coords, flags, ends):
    """Split outline into per-contour (coords, flags) lists."""
    out, start = [], 0
    for e in ends:
        out.append((coords[start:e + 1], flags[start:e + 1]))
        start = e + 1
    return out


def join_contours(contours):
    """Inverse of contours_of -> (coords, flags, ends)."""
    coords, flags, ends = [], [], []
    for c, f in contours:
        coords.extend(c)
        flags.extend(f)
        ends.append(len(coords) - 1)
    return coords, flags, ends


def bbox(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def center(pts):
    x0, y0, x1, y1 = bbox(pts)
    return (x0 + x1) / 2, (y0 + y1) / 2


def find_dot_contour(glyf, ref_name):
    """The dot contour of an ss07 glyph: the smallest-bbox-area 4-point
    contour (the bar of ! is also 4 points, so 'first 4-pt' is wrong).
    Returns its points (roman: rect, italic: slanted parallelogram)."""
    coords, flags, ends = get_outline(glyf, ref_name)
    best = None
    for c, f in contours_of(coords, flags, ends):
        if len(c) == 4:
            x0, y0, x1, y1 = bbox(c)
            area = (x1 - x0) * (y1 - y0)
            if best is None or area < best[0]:
                best = (area, c)
    if best is None:
        raise ValueError(f"no 4-pt dot contour in {ref_name}")
    return best[1]


def place_dot(ref_pts, target_cx, target_cy):
    """Translate a copied dot contour so its bbox center lands on target."""
    cx, cy = center(ref_pts)
    dx, dy = target_cx - cx, target_cy - cy
    return ([(round(x + dx), round(y + dy)) for x, y in ref_pts], [1, 1, 1, 1])


# ---------------------------------------------------------------------------
# Surgery (per pinned instance) — each returns (coords, flags, ends)
# All outputs have FIXED topology across masters by construction.
# ---------------------------------------------------------------------------

def straighten_t(font, name):
    """Replace the curved-foot stem contour with a straight stem.

    Inter's t = crossbar contour (4 pts) + stem contour (16 pts, curves
    right into a foot at the baseline). Keep the crossbar untouched; the
    stem becomes a parallelogram from the horizontal top edge down to the
    baseline at the font's italic angle (slant 0 -> plain rectangle).
    Verified: the slant model reproduces Inter Italic's real stem edges
    to the unit.
    """
    glyf = font["glyf"]
    slant = math.tan(math.radians(-font["post"].italicAngle))
    coords, flags, ends = get_outline(glyf, name)
    cons = contours_of(coords, flags, ends)
    assert len(cons) == 2, f"{name}: expected 2 contours, got {len(cons)}"

    # Stem = contour with more points; crossbar = the 4-pt one
    stem_i = 0 if len(cons[0][0]) > len(cons[1][0]) else 1
    cross = cons[1 - stem_i]
    stem_c, _ = cons[stem_i]

    top_y = max(p[1] for p in stem_c)
    top_xs = sorted({p[0] for p in stem_c if p[1] == top_y})
    assert len(top_xs) == 2, f"{name}: ambiguous stem top {top_xs}"
    tl, tr = top_xs
    bl, br = tl - slant * top_y, tr - slant * top_y

    stem = ([(round(bl), 0), (round(tl), top_y), (round(tr), top_y), (round(br), 0)],
            [1, 1, 1, 1])
    new = [None, None]
    new[1 - stem_i] = cross
    new[stem_i] = stem
    return join_contours(new)


def square_down_dot(font, name, ref):
    """exclamdown/questiondown: replace the round TOP dot with rsms's ss07
    dot shape (copied from the ref glyph, centered on the circle's center —
    his own positioning convention; stays correct for .case variants)."""
    glyf = font["glyf"]
    coords, flags, ends = get_outline(glyf, name)
    cons = contours_of(coords, flags, ends)
    ref_dot = find_dot_contour(glyf, ref)

    # Dot = round contour (>6 pts) whose bbox top is the glyph's top
    tops = [(max(p[1] for p in c), i) for i, (c, f) in enumerate(cons)]
    dot_i = max(tops)[1]
    dot_c, _ = cons[dot_i]
    assert len(dot_c) > 6, f"{name}: dot contour looks wrong ({len(dot_c)} pts)"
    cx, cy = center(dot_c)

    cons[dot_i] = place_dot(ref_dot, cx, cy)
    return join_contours(cons)


def square_divide(font, name):
    """divide: keep the bar, replace both round dots with period.ss07's
    dot shape centered on the original circles."""
    glyf = font["glyf"]
    coords, flags, ends = get_outline(glyf, name)
    cons = contours_of(coords, flags, ends)
    ref_dot = find_dot_contour(glyf, "period.ss07")

    out = []
    for c, f in cons:
        if len(c) > 6:  # circle
            cx, cy = center(c)
            out.append(place_dot(ref_dot, cx, cy))
        else:           # bar
            out.append((c, f))
    return join_contours(out)


SURGERY = [
    ("t",                straighten_t,    ()),
    ("t.1",              straighten_t,    ()),
    ("exclamdown",       square_down_dot, ("exclam.ss07",)),
    ("exclamdown.case",  square_down_dot, ("exclam.ss07",)),
    ("questiondown",     square_down_dot, ("question.ss07",)),
    ("questiondown.case", square_down_dot, ("question.ss07",)),
    ("divide",           square_divide,   ()),
    ("divide.case",      square_divide,   ()),
    ("divide.tf",        square_divide,   ()),
    ("divide.case.tf",   square_divide,   ()),
]


# ---------------------------------------------------------------------------
# Variable-font surgery: write new base outline + fresh gvar tuples
# ---------------------------------------------------------------------------

def apply_vf_surgery(vf, pinned):
    """pinned: list of 6 TTFont statics matching MASTER_LOCS."""
    glyf = vf["glyf"]
    gvar = vf["gvar"]
    hmtx = vf["hmtx"]
    present = set(vf.getGlyphOrder())

    for name, fn, extra in SURGERY:
        if name not in present:
            print(f"    - {name}: not in font, skipped")
            continue
        if glyf[name].isComposite():
            comps = [c.glyphName for c in glyf[name].components]
            print(f"    - {name}: composite of {comps}, inherits")
            continue
        # Compute modified outline at every master
        results = [fn(p, name, *extra) for p in pinned]
        # Topology must be identical everywhere
        _, f0, e0 = results[0]
        for (c, f, e) in results[1:]:
            assert f == f0 and e == e0, f"{name}: topology mismatch across masters"

        base_c = results[0][0]
        npts = len(base_c)

        # Write base glyph (default location)
        g = glyf[name]
        g.numberOfContours = len(e0)
        if hasattr(g, "components"):
            g.components = None
        g.program = Program()
        g.coordinates = GlyphCoordinates([(round(x), round(y)) for x, y in base_c])
        g.flags = bytes(f0)
        g.endPtsOfContours = list(e0)
        g.recalcBounds(glyf)
        aw, _ = hmtx[name]
        hmtx[name] = (aw, g.xMin)

        # Fresh gvar tuples (deltas vs default, corner-master algebra)
        def delta(i):
            return [(results[i][0][k][0] - base_c[k][0],
                     results[i][0][k][1] - base_c[k][1]) for k in range(npts)]

        d_opsz, d_wmin, d_wmax = delta(1), delta(2), delta(3)
        d_cmin = [(a[0] - b[0] - c[0], a[1] - b[1] - c[1])
                  for a, b, c in zip(delta(4), d_opsz, d_wmin)]
        d_cmax = [(a[0] - b[0] - c[0], a[1] - b[1] - c[1])
                  for a, b, c in zip(delta(5), d_opsz, d_wmax)]
        by_kind = {"opsz": d_opsz, "wmin": d_wmin, "wmax": d_wmax,
                   "corner_min": d_cmin, "corner_max": d_cmax}

        tvs = []
        for axes, kind in TUPLES:
            ds = by_kind[kind] + [(0, 0)] * 4  # 4 phantom points
            tvs.append(TupleVariation(dict(axes), ds))
        gvar.variations[name] = tvs
        print(f"    - {name}: {npts} pts, 5 tuples rebuilt")


# ---------------------------------------------------------------------------
# Freeze features by injecting their lookups into always-on `ccmp`
# ---------------------------------------------------------------------------

def freeze_features(vf):
    gsub = vf["GSUB"].table
    inject, found = set(), []
    for fr in gsub.FeatureList.FeatureRecord:
        if fr.FeatureTag in FREEZE_FEATURES:
            inject.update(fr.Feature.LookupListIndex)
            if fr.FeatureTag not in found:
                found.append(fr.FeatureTag)
    missing = [t for t in FREEZE_FEATURES if t not in found]
    if missing:
        print(f"    note: {missing} not in this font (italic a is already single-story)")
    assert inject, "no freeze features found"

    n = 0
    for fr in gsub.FeatureList.FeatureRecord:
        if fr.FeatureTag == "ccmp":
            merged = sorted(set(fr.Feature.LookupListIndex) | inject)
            fr.Feature.LookupListIndex = merged
            fr.Feature.LookupCount = len(merged)
            n += 1
    assert n > 0, "no ccmp feature records to inject into"
    print(f"    lookups {sorted(inject)} ({'+'.join(found)}) injected into {n} ccmp record(s)")


# ---------------------------------------------------------------------------
# Rename
# ---------------------------------------------------------------------------

def rename(vf, subfamily):
    name = vf["name"]
    ps_sub = subfamily.replace(" ", "")
    reps = {
        1: FAMILY,
        3: f"{FAMILY}-Variable-{ps_sub}",
        4: f"{FAMILY} {subfamily}",
        6: f"{FAMILY}-{ps_sub}",
        16: FAMILY,
        25: FAMILY.replace(" ", "") + ("Italic" if subfamily == "Italic" else ""),
    }
    for rec in name.names:
        if rec.nameID == 0:
            reps[0] = str(rec.toUnicode()) + f" Modified {FAMILY} variant (square punctuation + single-story a default, straight t)."
            break
    for nid, val in reps.items():
        existing_platforms = {(r.platformID, r.platEncID, r.langID)
                              for r in name.names if r.nameID == nid}
        targets = existing_platforms or {(3, 1, 0x409)}
        for pid, eid, lid in targets:
            name.setName(val, nid, pid, eid, lid)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

SUBSET_UNICODES = (
    list(range(0x0020, 0x0250)) +        # Latin, Latin-1, Ext-A/B
    list(range(0x02C6, 0x02DE)) +        # spacing modifier accents
    list(range(0x2000, 0x2070)) +        # general punctuation
    [0x20AC, 0x2122, 0x2212, 0x00D7, 0x00F7, 0x2192, 0x2190, 0x2191, 0x2193]
)


def export_subset(ttf_path, out_path):
    opts = subset.Options()
    opts.layout_features = ["*"]         # keep every GSUB/GPOS feature
    opts.name_IDs = ["*"]
    opts.notdef_outline = True
    s = subset.Subsetter(options=opts)
    s.populate(unicodes=SUBSET_UNICODES)
    f = TTFont(str(ttf_path))
    s.subset(f)
    f.flavor = "woff2"
    f.save(str(out_path))
    f.close()


def build_one(src, subfamily, stem):
    print(f"Loading {src}")
    vf = TTFont(src)

    print("  Pinning 6 masters for surgery geometry...")
    pinned = [instantiateVariableFont(TTFont(src), loc, inplace=False)
              for loc in MASTER_LOCS]

    print("  Surgery:")
    apply_vf_surgery(vf, pinned)

    print("  Freezing features:")
    freeze_features(vf)

    rename(vf, subfamily)

    ttf = OUT / f"{stem}.ttf"
    vf.save(str(ttf))
    print(f"  Saved {ttf.name} ({os.path.getsize(ttf)/1024:.0f} KB)")

    w2 = OUT / f"{stem}.woff2"
    f2 = TTFont(str(ttf))
    f2.flavor = "woff2"
    f2.save(str(w2))
    print(f"  Saved {w2.name} ({os.path.getsize(w2)/1024:.0f} KB)")

    ws = OUT / f"{stem}-subset.woff2"
    export_subset(ttf, ws)
    print(f"  Saved {ws.name} ({os.path.getsize(ws)/1024:.0f} KB)")


def main():
    OUT.mkdir(exist_ok=True)
    css_blocks = []
    for src, subfamily, stem, style in BUILDS:
        build_one(src, subfamily, stem)
        css_blocks.append(f"""@font-face {{
  font-family: "{FAMILY}";
  font-style: {style};
  font-weight: 100 900;
  font-display: swap;
  src: url("{stem}-subset.woff2") format("woff2");
}}""")

    css = OUT / "inty.css"
    css.write_text(f"""/* {FAMILY} — Inter with square punctuation + single-story a + straight t (OFL 1.1)
 * Variable: wght 100-900, opsz 14-32 (auto via font-optical-sizing)
 * Inter features intact: ss03 round quotes & commas, ss08 square quotes,
 * tnum, case, ... e.g. font-feature-settings: 'ss03' 1;
 * Swap -subset for the full files if you need beyond Latin+punctuation.
 */
""" + "\n\n".join(css_blocks) + "\n")
    print(f"Saved {css.name}\nDone.")


if __name__ == "__main__":
    main()
