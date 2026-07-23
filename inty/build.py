#!/usr/bin/env python3
"""
Build Inty — Inter with square punctuation ON by default + straight lowercase t.

Base: InterVariable.ttf 4.001 (2 axes: opsz 14-32, wght 100-900).

What this does:
  1. FREEZE ss07 "Square punctuation" — rsms's own square tittles/dots
     (i, j, period, comma, colon, semicolon, !, ?, ellipsis, dieresis,
     dot-accents, 250+ glyphs). Done by injecting the ss07 lookup into the
     always-on `ccmp` feature, so every contextual chain (case, tf, calt)
     behaves exactly as if the user had enabled ss07. Stock `y` untouched.
  2. SURGERY on glyphs ss07 misses:
     - t, t.1        : remove the curved foot -> straight vertical stem
     - exclamdown(.case), questiondown : round dot -> square (sized from
                       exclam.ss07 / question.ss07 dots, top at x-height)
     - divide(.case/.tf/...) : round dots -> squares (sized from period.ss07)
     Surgery is done across the full 2-axis design space: outlines are
     computed at the 6 corner/default masters and written back as fresh
     gvar tuples mirroring Inter's own variation model.
  3. RENAME family (Inter -> Inty), keep all OpenType features working
     (cv11 single-story a, ss03 round quotes & commas, ss08 square quotes,
     tnum, case, ...).

Outputs (output/): Inty-Variable.ttf, Inty-Variable.woff2 (full),
Inty-Variable-subset.woff2 (Latin + punctuation), inty.css
"""
import os
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.ttLib.tables.ttProgram import Program
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools import subset

FAMILY = "Inty"
SRC = "/Users/x/claude/inter-straight/inter-fresh/InterVariable.ttf"
OUT = Path(__file__).parent / "output"

# Design-space masters: default + corners (Inter's own model: wght 100/400/900
# crossed with opsz 14/32; avar handles the in-between weight bending).
DEFAULT_LOC = {"opsz": 14, "wght": 400}
MASTER_LOCS = [
    {"opsz": 14, "wght": 400},   # 0: default (base outline)
    {"opsz": 32, "wght": 400},   # 1
    {"opsz": 14, "wght": 100},   # 2
    {"opsz": 14, "wght": 900},   # 3
    {"opsz": 32, "wght": 100},   # 4
    {"opsz": 32, "wght": 900},   # 5
]
# gvar tuple axes (mirrors Inter's structure), each paired below with the
# master indices used to compute its delta.
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


def make_rect(left, bottom, w, h):
    """4-point on-curve rectangle (CW in TrueType y-up terms)."""
    r, t = round(left + w), round(bottom + h)
    left, bottom = round(left), round(bottom)
    return [(left, bottom), (left, t), (r, t), (r, bottom)], [1, 1, 1, 1]


def find_dot_rect(glyf, ref_name):
    """Width/height of the dot contour in an ss07 glyph: the smallest-area
    4-point rect (the bar of ! is also 4 points, so 'first 4-pt' is wrong)."""
    coords, flags, ends = get_outline(glyf, ref_name)
    best = None
    for c, f in contours_of(coords, flags, ends):
        if len(c) == 4:
            x0, y0, x1, y1 = bbox(c)
            area = (x1 - x0) * (y1 - y0)
            if best is None or area < best[0]:
                best = (area, x1 - x0, y1 - y0)
    if best is None:
        raise ValueError(f"no 4-pt rect contour in {ref_name}")
    return best[1], best[2]


def x_height(font):
    """Top of squared period? No — use OS/2 sxHeight equivalent: top of x."""
    glyf = font["glyf"]
    coords, _, _ = glyf["x"].getCoordinates(glyf)
    return max(p[1] for p in coords)


# ---------------------------------------------------------------------------
# Surgery (per pinned instance) — each returns (coords, flags, ends)
# All outputs have FIXED topology across masters by construction.
# ---------------------------------------------------------------------------

def straighten_t(font, name):
    """Replace the curved-foot stem contour with a straight rectangle.

    Inter's t = crossbar contour (4 pts) + stem contour (16 pts, curves
    right into a foot at the baseline). Keep the crossbar untouched, turn
    the stem into stem_left/right rect from baseline to the original top.
    """
    glyf = font["glyf"]
    coords, flags, ends = get_outline(glyf, name)
    cons = contours_of(coords, flags, ends)
    assert len(cons) == 2, f"{name}: expected 2 contours, got {len(cons)}"

    # Stem = contour with more points; crossbar = the 4-pt rect
    stem_i = 0 if len(cons[0][0]) > len(cons[1][0]) else 1
    cross = cons[1 - stem_i]
    stem_c, _ = cons[stem_i]

    top_y = max(p[1] for p in stem_c)
    # Stem x-edges: the two x values of points AT the top
    top_xs = sorted({p[0] for p in stem_c if p[1] == top_y})
    assert len(top_xs) == 2, f"{name}: ambiguous stem top {top_xs}"
    sl, sr = top_xs

    stem_rect = make_rect(sl, 0, sr - sl, top_y)
    new = [None, None]
    new[1 - stem_i] = cross
    new[stem_i] = stem_rect
    return join_contours(new)


def square_down_dot(font, name, ref):
    """exclamdown/questiondown: replace the round TOP dot with a square.

    Size from the ss07 reference glyph's dot; the circle's center is
    preserved (this is how rsms positions his own ss07 squares, and it
    stays correct for the raised .case variants).
    """
    glyf = font["glyf"]
    coords, flags, ends = get_outline(glyf, name)
    cons = contours_of(coords, flags, ends)
    w, h = find_dot_rect(glyf, ref)

    # Dot = round contour (>6 pts) whose bbox top is the glyph's top
    tops = [(max(p[1] for p in c), i) for i, (c, f) in enumerate(cons)]
    dot_i = max(tops)[1]
    dot_c, _ = cons[dot_i]
    assert len(dot_c) > 6, f"{name}: dot contour looks wrong ({len(dot_c)} pts)"
    x0, y0, x1, y1 = bbox(dot_c)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2

    cons[dot_i] = make_rect(cx - w / 2, cy - h / 2, w, h)
    return join_contours(cons)


def square_divide(font, name):
    """divide: keep the bar, replace both round dots with period.ss07-sized
    squares centered on the original circles."""
    glyf = font["glyf"]
    coords, flags, ends = get_outline(glyf, name)
    cons = contours_of(coords, flags, ends)
    w, h = find_dot_rect(glyf, "period.ss07")

    out = []
    for c, f in cons:
        if len(c) > 6:  # circle
            x0, y0, x1, y1 = bbox(c)
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            out.append(make_rect(cx - w / 2, cy - h / 2, w, h))
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
        results = []
        for p in pinned:
            results.append(fn(p, name, *extra))
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
# Freeze ss07 by injecting its lookups into always-on `ccmp`
# ---------------------------------------------------------------------------

FREEZE_FEATURES = ["ss07", "cv11"]  # square punctuation + single-story a


def freeze_features(vf):
    """Inject the frozen features' lookups into always-on `ccmp`. Lookups
    apply in LookupList order, so chains behave exactly as if the user had
    enabled the features (cv11's lookup 86 runs after ss07's 74 and maps
    the .ss07 composed forms too)."""
    gsub = vf["GSUB"].table
    inject = set()
    for fr in gsub.FeatureList.FeatureRecord:
        if fr.FeatureTag in FREEZE_FEATURES:
            inject.update(fr.Feature.LookupListIndex)
    assert inject, "freeze features not found"

    n = 0
    for fr in gsub.FeatureList.FeatureRecord:
        if fr.FeatureTag == "ccmp":
            merged = sorted(set(fr.Feature.LookupListIndex) | inject)
            fr.Feature.LookupListIndex = merged
            fr.Feature.LookupCount = len(merged)
            n += 1
    assert n > 0, "no ccmp feature records to inject into"
    print(f"    lookups {sorted(inject)} ({'+'.join(FREEZE_FEATURES)}) injected into {n} ccmp record(s)")


# ---------------------------------------------------------------------------
# Rename
# ---------------------------------------------------------------------------

def rename(vf):
    name = vf["name"]
    reps = {
        1: FAMILY,
        3: f"{FAMILY}-Variable",
        4: f"{FAMILY} Regular",
        6: f"{FAMILY}-Regular",
        16: FAMILY,
        25: FAMILY.replace(" ", ""),
    }
    # Copyright: append modification note
    for rec in name.names:
        if rec.nameID == 0:
            reps[0] = str(rec.toUnicode()) + f" Modified {FAMILY} variant (square punctuation default, straight t)."
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
    list(range(0x2000, 0x2070)) +        # general punctuation (quotes, dashes, ellipsis, bullet)
    [0x20AC, 0x2122, 0x2212, 0x00D7, 0x00F7, 0x2192, 0x2190, 0x2191, 0x2193]
)


def export_subset(ttf_path, out_path):
    opts = subset.Options()
    opts.layout_features = ["*"]         # keep every GSUB/GPOS feature
    opts.name_IDs = ["*"]
    opts.notdef_outline = True
    opts.flavor = "woff2"
    s = subset.Subsetter(options=opts)
    s.populate(unicodes=SUBSET_UNICODES)
    f = TTFont(str(ttf_path))
    s.subset(f)
    f.flavor = "woff2"
    f.save(str(out_path))
    f.close()


def main():
    OUT.mkdir(exist_ok=True)
    print(f"Loading {SRC}")
    vf = TTFont(SRC)

    print("  Pinning 6 masters for surgery geometry...")
    pinned = [instantiateVariableFont(TTFont(SRC), loc, inplace=False)
              for loc in MASTER_LOCS]

    print("  Surgery:")
    apply_vf_surgery(vf, pinned)

    print("  Freezing features:")
    freeze_features(vf)

    print("  Renaming:")
    rename(vf)

    ttf = OUT / f"{FAMILY}-Variable.ttf"
    vf.save(str(ttf))
    print(f"  Saved {ttf} ({os.path.getsize(ttf)/1024:.0f} KB)")

    w2 = OUT / f"{FAMILY}-Variable.woff2"
    f2 = TTFont(str(ttf))
    f2.flavor = "woff2"
    f2.save(str(w2))
    print(f"  Saved {w2} ({os.path.getsize(w2)/1024:.0f} KB)")

    ws = OUT / f"{FAMILY}-Variable-subset.woff2"
    export_subset(ttf, ws)
    print(f"  Saved {ws} ({os.path.getsize(ws)/1024:.0f} KB)")

    css = OUT / "inty.css"
    css.write_text(f"""/* {FAMILY} — Inter with square punctuation + straight t (OFL 1.1)
 * Variable: wght 100-900, opsz 14-32 (auto via font-optical-sizing)
 * All Inter features intact: cv11 single-story a, ss03 round quotes & commas,
 * ss08 square quotes, tnum, case, ... e.g. font-feature-settings: 'cv11' 1;
 */
@font-face {{
  font-family: "{FAMILY}";
  font-style: normal;
  font-weight: 100 900;
  font-display: swap;
  src: url("{FAMILY}-Variable.woff2") format("woff2");
}}
""")
    print(f"  Saved {css}")
    print("Done.")


if __name__ == "__main__":
    main()
