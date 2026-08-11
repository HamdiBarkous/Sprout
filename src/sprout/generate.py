"""Generate canonical Sprout SVGs.

Every emitted SVG has the SAME submobject layout in the SAME order so the
Sprout class can swap modes safely (PiCreature-style):

    0  shadow
    1  left_arm        2  left_hand        (default resting at the sides)
    3  right_arm       4  right_hand       (default resting at the sides)
    5  sprout_leaf     (tapered stem + blade, one path — posed per mode)
    6  leaf_shade      (darker half-blade overlay — two-tone leaf)
    7  body
    8  belly           (soft tummy patch)
    9  shade_soft      10 shade_core      (occlusion crescents, over belly)
    11 eye_white_L     12 eye_white_R
    13 pupil_L         14 pupil_R
    15 mouth
    16 blush_L         17 blush_R
    18 mark_ring       19 mark_blade      (belly singularity mark)
    20 mark_fillet_a   21 mark_fillet_b
    22+ extras (eyebrows, lids, hearts — mode-specific decorations)

Indices 0-21 are FIXED across every mode; pose changes (wave/point/celebrate/
thinking) move the arm paths and hand circles in place — never adding or
removing submobjects. The leaf (and its shade) are likewise always paths
with identical command topology, so they droop/perk per mode and still
Transform cleanly. The belly mark is identical in every mode.

Design notes (the anti-clipart rules):
    - The body is a hand-wobbled pear, not a perfect ellipse.
    - The eyes are enormous (pi-creature scale) and bulge above the head —
      they are where the acting happens.
    - The leaf is the identity: two-tone filled blade, posed like a dog's
      ear (droops when sad, stands tall when excited).
    - Two materials, one ramp each: skin (belly/body/arms/ink) descends a
      single OKLCH path — even value steps, warm->cool rotation, chroma
      peaking at the body; the leaf is the accent material and holds the
      chroma crown. Two stacked under-shade crescents give the light story.
    - The belly mark is a singularity (ring + accretion blade + tangent
      fillets): the series ends at the singularity, and Sprout carries
      his destination from frame zero.

Re-run after editing this file:
    uv run python src/sprout/generate.py
"""

import math
from pathlib import Path

OUT_DIR = Path(__file__).parent / "svg"

# Palette — two materials, each on one disciplined OKLCH ramp.
# Skin (belly -> body -> arm -> ink): lightness falls in even steps, hue
# rotates warm->cool monotonically (128 -> 156 deg), chroma peaks at the
# body and tapers at both ends. The leaf is the accent material: the
# chroma crown of the character, lighter and warmer than any skin tone.
BODY = "#85C871"  # skin anchor — L .77 C .137 H 139
TUMMY = "#CEE590"  # belly fill @ .45 over body -> composite L .82 H 132
ARM = "#57A369"  # arms — L .65 H 150: shaded skin, not another material
LEAF = "#BCE45A"  # leaf — L .86 C .170 H 124, the accent
LEAF_DARK = "#8DC45A"  # leaf shade — darker, cooler, LESS chromatic
BLUSH = "#F0A277"  # cheek blush — apricot, the one warm note
INK = "#579769"  # belly-mark ink — a whisper above the belly, L .62 H 152
SHADE = "#29885E"  # under-shade crescents — cool occlusion green
DARK = "#0e1418"
WHITE = "white"
HEART = "#ff6b81"

# Limb geometry — arms are tapered vine stems ending in a rounded tip
# (no explicit hand shape; the taper IS the gesture).
ARM_W_SHOULDER = 11.0  # full width at the shoulder root
ARM_W_WRIST = 6.0  # full width at the tip
EYE_STROKE_W = 1.6

# Canonical geometry (200x200 viewBox)
EYE_L_X, EYE_R_X, EYE_Y = 82, 118, 91
MOUTH_Y = 128

# Shoulders sit INSIDE the body so the silhouette covers the arm root —
# arms emerge organically instead of being tacked onto the edge.
SHOULDER_L = (63, 142)
SHOULDER_R = (137, 142)

HAND_REST_L = (47, 165)
HAND_REST_R = (153, 165)
ARM_REST_L_CTRL = (49, 150)
ARM_REST_R_CTRL = (151, 150)


# ----------------------------------------------------------------- primitives


def shadow():
    return '<ellipse cx="100" cy="184" rx="42" ry="5" fill="#000" fill-opacity="0.18"/>'


def body(color=BODY):
    # Hand-wobbled pear: narrow crown, full belly, no two handles symmetric.
    d = (
        "M 101 80 "
        "C 127 82, 142 105, 145 135 "
        "C 148 164, 126 181, 99 180 "
        "C 72 179, 54 162, 56 133 "
        "C 58 104, 75 79, 101 80 Z"
    )
    return f'<path d="{d}" fill="{color}"/>'


def highlight():
    # Soft belly patch: wide, low, low-contrast — a whisper, not a sticker.
    return f'<ellipse cx="100" cy="154" rx="27" ry="18" fill="{TUMMY}" fill-opacity="0.45"/>'


def blush():
    return [
        f'<ellipse cx="71" cy="119" rx="7.5" ry="4.5" fill="{BLUSH}" fill-opacity="0.5"/>',
        f'<ellipse cx="129" cy="119" rx="7.5" ry="4.5" fill="{BLUSH}" fill-opacity="0.5"/>',
    ]


# ----------------------------------------------------------------- under-shade

# Occlusion shading: two stacked crescents hugging the body's lower
# silhouette — a soft wide pass plus a tighter core, so the terminator
# dissolves like a gradient instead of drawing a hard line. The outer edge
# lies ON the body outline; width swells on a raised cosine (nothing at
# the flanks, fullest under the base); the inner edge is projected out of
# the belly patch so the light center stays clean.
_BODY_BOTTOM = [  # body()'s two lower cubics, verbatim
    ((145, 135), (148, 164), (126, 181), (99, 180)),
    ((99, 180), (72, 179), (54, 162), (56, 133)),
]
_BELLY_RIM = (100, 154, 27, 18)  # highlight()'s ellipse
_SHADE_PASSES = [  # (t0, t1, width, opacity, belly_margin)
    (0.08, 0.92, 16.0, 0.13, 2.0),
    (0.22, 0.78, 10.0, 0.20, 3.5),
]


def _shade_path(t0, t1, width, opacity, margin):
    cx, cy, rx, ry = _BELLY_RIM
    outer, inner = [], []
    n = 90
    for i in range(n + 1):
        u = i / n
        t = t0 + (t1 - t0) * u
        x, y = _chain(_BODY_BOTTOM, t)
        eps = 1e-4
        x1, y1 = _chain(_BODY_BOTTOM, max(0.0, t - eps))
        x2, y2 = _chain(_BODY_BOTTOM, min(1.0, t + eps))
        nx, ny = _unit_perp(x2 - x1, y2 - y1)
        if nx * (100 - x) + ny * (140 - y) < 0:  # point the normal inward
            nx, ny = -nx, -ny
        w = width * 0.5 * (1 - math.cos(2 * math.pi * u))
        ix, iy = x + nx * w, y + ny * w
        k = math.hypot((ix - cx) / (rx + margin), (iy - cy) / (ry + margin))
        if k < 1:  # inside the belly: slide out onto its rim
            ix, iy = cx + (ix - cx) / k, cy + (iy - cy) / k
        outer.append(f"{x:.2f} {y:.2f}")
        inner.append(f"{ix:.2f} {iy:.2f}")
    d = "M " + " L ".join(outer) + " L " + " L ".join(reversed(inner)) + " Z"
    return f'<path d="{d}" fill="{SHADE}" fill-opacity="{opacity}"/>'


def under_shade():
    """The two occlusion crescents — indices 9 (soft) and 10 (core)."""
    return [_shade_path(*p) for p in _SHADE_PASSES]


# ----------------------------------------------------------------- leaf

# Leaf poses: (stem_ctrl, stem_tip, blade_tilt_deg, blade_scale).
# The blade's axis CONTINUES the stem's tangent at the tip — the tilt here
# is relative to that flow, not absolute (so stem and blade always read as
# one connected plant, never a shape balanced on a stick).
LEAF_POSES = {
    "perky": ((99, 64), (105, 52), 2, 1.0),
    "stiff": ((100, 65), (102, 50), -3, 0.95),
    "droop": ((106, 70), (114, 66), 35, 0.92),
    "excited": ((100, 63), (100, 46), -6, 1.15),
}

_STEM_BASE = (100.0, 81.0)
_STEM_W_BASE = 2.6  # half-width where the stem leaves the head
_STEM_W_TIP = 1.4  # half-width where it meets the blade
_BLADE_OVERLAP = 4.5  # how far the blade swallows the stem tip


def _unit_perp(dx, dy):
    n = math.hypot(dx, dy) or 1.0
    return -dy / n, dx / n


def _blade_frame(pose):
    """Blade placement for a pose: (base_x, base_y, cos_t, sin_t, scale).

    Blade axis = stem tangent at the tip plus the pose's relative tilt;
    the base is planted back along that axis so the stem tip ends inside.
    """
    ctrl, tip, rel_tilt, s = LEAF_POSES[pose]
    cx, cy = ctrl
    tx, ty = tip
    dx, dy = tx - cx, ty - cy
    n = math.hypot(dx, dy) or 1.0
    dx, dy = dx / n, dy / n
    c0, s0 = -dy, dx  # rotate local "up" (0,-1) onto the tangent
    th = math.radians(rel_tilt)
    ct, st = math.cos(th), math.sin(th)
    c = c0 * ct - s0 * st
    sn = s0 * ct + c0 * st
    fx, fy = sn, -c  # blade forward direction
    return tx - _BLADE_OVERLAP * s * fx, ty - _BLADE_OVERLAP * s * fy, c, sn, s


def leaf(pose="perky"):
    """S-curved tapered stem flowing into the blade — one path, fixed
    command topology. The blade base overlaps the stem tip so the joint
    is organic, not a point contact."""
    ctrl, tip, _rel_tilt, _s = LEAF_POSES[pose]
    bx0, by0 = _STEM_BASE
    cx, cy = ctrl
    tx, ty = tip
    # Taper along the stem's true perpendicular (matters for droop poses).
    pbx, pby = _unit_perp(cx - bx0, cy - by0)
    pmx, pmy = _unit_perp(tx - bx0, ty - by0)
    ptx, pty = _unit_perp(tx - cx, ty - cy)
    wm = (_STEM_W_BASE + _STEM_W_TIP) / 2
    stem = (
        f"M {bx0 + pbx * _STEM_W_BASE:.1f} {by0 + pby * _STEM_W_BASE:.1f} "
        f"Q {cx + pmx * wm:.1f} {cy + pmy * wm:.1f} "
        f"{tx + ptx * _STEM_W_TIP:.1f} {ty + pty * _STEM_W_TIP:.1f} "
        f"L {tx - ptx * _STEM_W_TIP:.1f} {ty - pty * _STEM_W_TIP:.1f} "
        f"Q {cx - pmx * wm:.1f} {cy - pmy * wm:.1f} "
        f"{bx0 - pbx * _STEM_W_BASE:.1f} {by0 - pby * _STEM_W_BASE:.1f} Z "
    )
    bbx, bby, c, sn, s = _blade_frame(pose)
    blade = _blade_d(bbx, bby, c, sn, s)
    return f'<path d="{stem}{blade}" fill="{LEAF}"/>'


def leaf_shade(pose="perky"):
    """Two-tone leaf: the darker half of the blade, split at the midrib.
    Same transform as the blade, so it follows every pose."""
    bbx, bby, c, sn, s = _blade_frame(pose)

    def world(x, y):
        x, y = x * s, y * s
        return (bbx + x * c - y * sn, bby + x * sn + y * c)

    (bx, by) = world(*BLADE_LOCAL[0])
    (l1x, l1y) = world(*BLADE_LOCAL[1])
    (ax, ay) = world(*BLADE_LOCAL[2])
    d = (
        f"M {bx:.1f} {by:.1f} "
        f"Q {l1x:.1f} {l1y:.1f} {ax:.1f} {ay:.1f} "
        f"L {bx:.1f} {by:.1f} Z"
    )
    return f'<path d="{d}" fill="{LEAF_DARK}"/>'


# ----------------------------------------------------------------- arms


# The blade shape shared by the head leaf and the leaf hands (local coords,
# pointing up, base at origin, slightly asymmetric so it feels hand-drawn).
BLADE_LOCAL = [
    (0.0, 0.0),  # base (M)
    (-12.0, -7.0),  # left ctrl — fuller lower belly
    (1.5, -27.0),  # apex — slightly off-axis, like a real leaf
    (10.0, -13.0),  # right ctrl
]


def _blade_d(base_x, base_y, cos_t, sin_t, scale):
    """Blade path data rotated by (cos_t, sin_t) and planted at base.

    Emitted right-side-first so its winding matches the stem subpath —
    opposite windings would cancel under the nonzero fill rule and punch
    a hole where blade and stem overlap."""
    pts = []
    for x, y in BLADE_LOCAL:
        x, y = x * scale, y * scale
        pts.append((base_x + x * cos_t - y * sin_t, base_y + x * sin_t + y * cos_t))
    (bx, by), (l1x, l1y), (ax, ay), (r1x, r1y) = pts
    return (
        f"M {bx:.1f} {by:.1f} "
        f"Q {r1x:.1f} {r1y:.1f} {ax:.1f} {ay:.1f} "
        f"Q {l1x:.1f} {l1y:.1f} {bx:.1f} {by:.1f} Z"
    )


def _perp(dx, dy):
    n = math.hypot(dx, dy) or 1.0
    return -dy / n, dx / n


def arm_path(shoulder, control, hand_pos):
    """Tapered vine stem: a filled shape thick at the shoulder, narrow at
    the wrist. Fixed command topology (M Q L Q Z) so Transform interpolates
    poses cleanly. The wrist's butt end is covered by the leaf hand."""
    sx, sy = shoulder
    cx, cy = control
    hx, hy = hand_pos
    # Perpendiculars to the local tangent at shoulder, midpoint, and wrist.
    npx_s, npy_s = _perp(cx - sx, cy - sy)
    npx_m, npy_m = _perp(hx - sx, hy - sy)
    npx_h, npy_h = _perp(hx - cx, hy - cy)
    ws, wm, wh = ARM_W_SHOULDER / 2, (ARM_W_SHOULDER + ARM_W_WRIST) / 4, ARM_W_WRIST / 2
    d = (
        f"M {sx + npx_s * ws:.1f} {sy + npy_s * ws:.1f} "
        f"Q {cx + npx_m * wm:.1f} {cy + npy_m * wm:.1f} "
        f"{hx + npx_h * wh:.1f} {hy + npy_h * wh:.1f} "
        f"L {hx - npx_h * wh:.1f} {hy - npy_h * wh:.1f} "
        f"Q {cx - npx_m * wm:.1f} {cy - npy_m * wm:.1f} "
        f"{sx - npx_s * ws:.1f} {sy - npy_s * ws:.1f} Z"
    )
    return f'<path d="{d}" fill="{ARM}"/>'


def hand(pos):
    """Rounded cap that closes the arm's butt end — visually the arm simply
    tapers to a soft tip. Kept as its own submobject to preserve the fixed
    fixed core layout (index 2 / 4)."""
    x, y = pos
    return f'<circle cx="{x}" cy="{y}" r="{ARM_W_WRIST / 2}" fill="{ARM}"/>'


# Pose specs: (control_point, hand_pos). Shoulder is always SHOULDER_L/R.
ARM_POSES_L = {
    "rest": (ARM_REST_L_CTRL, HAND_REST_L),
    "celebrate": ((28, 102), (44, 60)),
    "point_out": ((28, 148), (16, 132)),
}
ARM_POSES_R = {
    "rest": (ARM_REST_R_CTRL, HAND_REST_R),
    "celebrate": ((172, 102), (156, 60)),
    "wave": ((176, 112), (168, 76)),
    # Head-scratch: hand beside the right eye, against the background —
    # a chin-hand would hide behind the body (arms draw at z-index 1-4).
    "thinking": ((178, 110), (148, 84)),
    "point_out": ((172, 148), (184, 132)),
    "point_up": ((166, 104), (158, 64)),
}


def left_arm(pose="rest"):
    ctrl, hpos = ARM_POSES_L[pose]
    return [arm_path(SHOULDER_L, ctrl, hpos), hand(hpos)]


def right_arm(pose="rest"):
    ctrl, hpos = ARM_POSES_R[pose]
    return [arm_path(SHOULDER_R, ctrl, hpos), hand(hpos)]


# ----------------------------------------------------------------- eyes

# Pi-creature eye anatomy: tall near-touching oval whites, pupils well
# under half the eye — the empty white above the pupil is what makes the
# gaze read as thoughtful instead of googly.
EYE_PRESETS = {
    # name      white_rx white_ry stroke_w pupil_r dx  dy white_op pupil_op
    "normal": (16.5, 19.0, EYE_STROKE_W, 6.2, 0, 0, 1, 1),
    "wide": (18.0, 21.0, 1.8, 4.5, 0, 0, 1, 1),
    "droopy": (16.5, 19.0, EYE_STROKE_W, 5.8, 0, 5, 1, 1),
    "glare": (16.5, 19.0, EYE_STROKE_W, 5.5, 0, 3, 1, 1),
    "look_ur": (16.5, 19.0, EYE_STROKE_W, 6.0, 5, -6, 1, 1),
    "hidden": (16.5, 19.0, 0.0, 6.0, 0, 0, 0, 0),
}


def eye_pair(preset):
    wrx, wry, wsw, pr, dx, dy, wop, pop = EYE_PRESETS[preset]
    whites = [
        (
            f'<ellipse cx="{EYE_L_X}" cy="{EYE_Y}" rx="{wrx}" ry="{wry}" fill="{WHITE}" '
            f'fill-opacity="{wop}" stroke="{DARK}" stroke-width="{wsw}" stroke-opacity="{wop}"/>'
        ),
        (
            f'<ellipse cx="{EYE_R_X}" cy="{EYE_Y}" rx="{wrx}" ry="{wry}" fill="{WHITE}" '
            f'fill-opacity="{wop}" stroke="{DARK}" stroke-width="{wsw}" stroke-opacity="{wop}"/>'
        ),
    ]
    pupils = [
        f'<circle cx="{EYE_L_X + dx}" cy="{EYE_Y + dy}" r="{pr}" fill="{DARK}" fill-opacity="{pop}"/>',
        f'<circle cx="{EYE_R_X + dx}" cy="{EYE_Y + dy}" r="{pr}" fill="{DARK}" fill-opacity="{pop}"/>',
    ]
    return whites, pupils


# ----------------------------------------------------------------- mouths


def mouth_line():
    return f'<path d="M 92 {MOUTH_Y + 1} L 108 {MOUTH_Y + 1}" fill="none" stroke="{DARK}" stroke-width="2.6" stroke-linecap="round"/>'


def mouth_smile():
    return f'<path d="M 86 {MOUTH_Y - 2} Q 100 {MOUTH_Y + 13} 114 {MOUTH_Y - 2}" fill="none" stroke="{DARK}" stroke-width="3" stroke-linecap="round"/>'


def mouth_open_smile():
    return (
        f'<path d="M 84 {MOUTH_Y - 2} Q 100 {MOUTH_Y + 16} 116 {MOUTH_Y - 2} '
        f'Q 100 {MOUTH_Y + 5} 84 {MOUTH_Y - 2} Z" fill="{DARK}" stroke="none"/>'
    )


def mouth_frown():
    return f'<path d="M 87 {MOUTH_Y + 5} Q 100 {MOUTH_Y - 7} 113 {MOUTH_Y + 5}" fill="none" stroke="{DARK}" stroke-width="3" stroke-linecap="round"/>'


def mouth_grit():
    return f'<path d="M 90 {MOUTH_Y + 3} L 110 {MOUTH_Y + 3}" fill="none" stroke="{DARK}" stroke-width="3.2" stroke-linecap="round"/>'


def mouth_o():
    return f'<ellipse cx="100" cy="{MOUTH_Y + 4}" rx="5" ry="7" fill="{DARK}"/>'


def mouth_speak():
    """Slightly open mouth for 'speaking' mode."""
    return (
        f'<path d="M 88 {MOUTH_Y - 1} Q 100 {MOUTH_Y + 11} 112 {MOUTH_Y - 1} '
        f'Q 100 {MOUTH_Y + 3} 88 {MOUTH_Y - 1} Z" fill="{DARK}" stroke="none"/>'
    )


# ----------------------------------------------------------------- extras


def angry_brows():
    return [
        f'<path d="M 66 74 L 96 86" fill="none" stroke="{DARK}" stroke-width="4.5" stroke-linecap="round"/>',
        f'<path d="M 134 74 L 104 86" fill="none" stroke="{DARK}" stroke-width="4.5" stroke-linecap="round"/>',
    ]


def lid_arcs():
    return [
        f'<path d="M 66 90 Q 82 99 98 90" fill="none" stroke="{DARK}" stroke-width="2.6" stroke-linecap="round"/>',
        f'<path d="M 102 90 Q 118 99 134 90" fill="none" stroke="{DARK}" stroke-width="2.6" stroke-linecap="round"/>',
    ]


def _heart(cx, cy, s):
    # y-down: tip at bottom, lobes on top.
    def p(x, y):
        return f"{cx + x * s:.1f} {cy + y * s:.1f}"

    return (
        f'<path d="M {p(0, 0.6)} '
        f"C {p(-0.5, 0.2)}, {p(-0.62, -0.12)}, {p(-0.35, -0.32)} "
        f"C {p(-0.15, -0.47)}, {p(0, -0.32)}, {p(0, -0.15)} "
        f"C {p(0, -0.32)}, {p(0.15, -0.47)}, {p(0.35, -0.32)} "
        f'C {p(0.62, -0.12)}, {p(0.5, 0.2)}, {p(0, 0.6)} Z" fill="{HEART}"/>'
    )


def hearts():
    return [
        _heart(EYE_L_X, EYE_Y, 24),
        _heart(EYE_R_X, EYE_Y, 24),
    ]


# ----------------------------------------------------------------- belly mark

# Singularity: hand-drawn event-horizon ring + accretion blade + concave
# tangent fillets where the blade leaves the ring (ink pooling in the
# corners — no bumps). Identical in every mode: 4 fixed submobjects.
MARK_CX, MARK_CY, MARK_R = 100.2, 153.6, 6.8
MARK_RING_W = 2.3
MARK_RING_D = (
    "M 100.2 146.8 "
    "C 95.8 146.7, 93 149.8, 93.1 153.6 "
    "C 93.2 157.5, 96.4 160.5, 100.3 160.4 "
    "C 104.2 160.3, 107.1 157.2, 107 153.4 "
    "C 106.9 149.7, 104 146.9, 100.2 146.8 Z"
)
# Blade edges: chains of two cubics running left tip -> right tip.
MARK_UPPER = [
    ((83.5, 161.5), (91, 157.6), (96, 155.2), (100, 153.1)),
    ((100, 153.1), (104.5, 150.7), (110.5, 148.2), (116.5, 145.2)),
]
MARK_LOWER = [
    ((83.5, 161.5), (90.5, 159.4), (95.8, 156.8), (100.4, 154.6)),
    ((100.4, 154.6), (104.8, 152.4), (110.8, 149.6), (116.5, 145.2)),
]
MARK_FILLET_WRAP = 30.0  # degrees of ring the fillet climbs along
MARK_FILLET_RUN = 0.11  # how far along the blade edge it reaches (t units)


def _bez(p0, p1, p2, p3, t):
    u = 1 - t
    return (
        u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0],
        u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1],
    )


def _chain(chains, t):
    k = len(chains)
    i = min(int(t * k), k - 1)
    p0, p1, p2, p3 = chains[i]
    return _bez(p0, p1, p2, p3, t * k - i)


def _mark_blade():
    n = 110
    up, lo = [], []
    for i in range(n + 1):
        t = i / n
        ux, uy = _chain(MARK_UPPER, t)
        lx, ly = _chain(MARK_LOWER, t)
        up.append(f"{ux:.2f} {uy:.2f}")
        lo.append(f"{lx:.2f} {ly:.2f}")
    d = "M " + " L ".join(up) + " L " + " L ".join(reversed(lo)) + " Z"
    return f'<path d="{d}" fill="{INK}"/>'


def _mark_edge_exit(chain, t0, t1):
    """t where a blade edge crosses the ring's OUTER outline, t0 -> t1."""
    ro = MARK_R + MARK_RING_W / 2
    steps = 200
    prev_t, prev_d = None, None
    for i in range(steps + 1):
        t = t0 + (t1 - t0) * i / steps
        x, y = _chain(chain, t)
        d = math.hypot(x - MARK_CX, y - MARK_CY) - ro
        if prev_d is not None and prev_d * d <= 0:
            return prev_t + (t - prev_t) * prev_d / (prev_d - d + 1e-12)
        prev_t, prev_d = t, d
    return None


def _mark_fillet(chain, t_exit, outward):
    """Concave corner-fill between the ring outline and one blade edge:
    ring arc + blade-edge run + one quadratic tangent to both."""
    ro = MARK_R + MARK_RING_W / 2
    ex, ey = _chain(chain, t_exit)
    a_exit = math.degrees(math.atan2(ey - MARK_CY, ex - MARK_CX))
    a_a = a_exit - MARK_FILLET_WRAP
    ax = MARK_CX + ro * math.cos(math.radians(a_a))
    ay = MARK_CY + ro * math.sin(math.radians(a_a))
    t_b = t_exit + outward * MARK_FILLET_RUN
    bx, by = _chain(chain, t_b)
    ta = (-math.sin(math.radians(a_a)), math.cos(math.radians(a_a)))
    eps = 0.004
    b1 = _chain(chain, max(0.0, t_b - eps))
    b2 = _chain(chain, min(1.0, t_b + eps))
    tb = (b2[0] - b1[0], b2[1] - b1[1])
    det = ta[0] * (-tb[1]) - ta[1] * (-tb[0])
    if abs(det) < 1e-9:
        ctrl = ((ax + bx) / 2, (ay + by) / 2)
    else:
        sfac = ((bx - ax) * (-tb[1]) - (by - ay) * (-tb[0])) / det
        ctrl = (ax + sfac * ta[0], ay + sfac * ta[1])
    narc = 16
    arc = []
    for i in range(narc + 1):
        a = a_a + (a_exit - a_a) * i / narc
        arc.append(
            f"{MARK_CX + ro * math.cos(math.radians(a)):.2f} "
            f"{MARK_CY + ro * math.sin(math.radians(a)):.2f}"
        )
    nrun = 12
    run = []
    for i in range(nrun + 1):
        t = t_exit + (t_b - t_exit) * i / nrun
        x, y = _chain(chain, t)
        run.append(f"{x:.2f} {y:.2f}")
    d = (
        "M "
        + " L ".join(arc)
        + " L "
        + " L ".join(run)
        + f" Q {ctrl[0]:.2f} {ctrl[1]:.2f}, {ax:.2f} {ay:.2f} Z"
    )
    return f'<path d="{d}" fill="{INK}"/>'


def mark_paths():
    """The 4 mark submobjects: ring, blade, and the two fillets."""
    n = 110
    cs = []
    prev = None
    for i in range(n + 1):
        t = i / n
        ux, uy = _chain(MARK_UPPER, t)
        lx, ly = _chain(MARK_LOWER, t)
        x, y = (ux + lx) / 2, (uy + ly) / 2
        d = math.hypot(x - MARK_CX, y - MARK_CY) - MARK_R
        if prev is not None and prev * d <= 0:
            cs.append(t)
        prev = d
    t_in, t_out = cs[0], cs[1]
    ring = (
        f'<path d="{MARK_RING_D}" fill="none" stroke="{INK}" '
        f'stroke-width="{MARK_RING_W}" stroke-linecap="round"/>'
    )
    t_e_r = _mark_edge_exit(MARK_UPPER, t_out - 0.05, min(1.0, t_out + 0.3))
    t_e_l = _mark_edge_exit(MARK_LOWER, t_in + 0.05, max(0.0, t_in - 0.3))
    return [
        ring,
        _mark_blade(),
        _mark_fillet(MARK_UPPER, t_e_r, +1),  # right crossing, upper edge
        _mark_fillet(MARK_LOWER, t_e_l, -1),  # left crossing, lower edge
    ]


# ----------------------------------------------------------------- modes


def mode_spec(
    eyes="normal",
    mouth=mouth_line,
    arm_l="rest",
    arm_r="rest",
    leaf_pose="perky",
    extras=None,
):
    return {
        "eyes": eyes,
        "mouth": mouth,
        "arm_l": arm_l,
        "arm_r": arm_r,
        "leaf": leaf_pose,
        "extras": extras or list,
    }


MODES = {
    "plain": mode_spec(eyes="normal", mouth=mouth_line),
    "happy": mode_spec(eyes="normal", mouth=mouth_smile),
    "sad": mode_spec(eyes="droopy", mouth=mouth_frown, leaf_pose="droop"),
    "angry": mode_spec(
        eyes="glare", mouth=mouth_grit, leaf_pose="stiff", extras=angry_brows
    ),
    "surprised": mode_spec(eyes="wide", mouth=mouth_o, leaf_pose="excited"),
    "love": mode_spec(eyes="hidden", mouth=mouth_smile, extras=hearts),
    "thinking": mode_spec(eyes="look_ur", mouth=mouth_line, arm_r="thinking"),
    "sleepy": mode_spec(
        eyes="hidden", mouth=mouth_line, leaf_pose="droop", extras=lid_arcs
    ),
    "speaking": mode_spec(eyes="normal", mouth=mouth_speak),
    "celebrate": mode_spec(
        eyes="normal",
        mouth=mouth_open_smile,
        arm_l="celebrate",
        arm_r="celebrate",
        leaf_pose="excited",
    ),
    "wave": mode_spec(eyes="normal", mouth=mouth_smile, arm_r="wave"),
    "point_left": mode_spec(eyes="normal", mouth=mouth_smile, arm_l="point_out"),
    "point_right": mode_spec(eyes="normal", mouth=mouth_smile, arm_r="point_out"),
    "point_up": mode_spec(eyes="normal", mouth=mouth_smile, arm_r="point_up"),
}


def render_mode(mode_name, spec):
    whites, pupils = eye_pair(spec["eyes"])
    arm_l_path, arm_l_hand = left_arm(spec["arm_l"])
    arm_r_path, arm_r_hand = right_arm(spec["arm_r"])
    parts = [
        shadow(),  # 0
        arm_l_path,  # 1
        arm_l_hand,  # 2
        arm_r_path,  # 3
        arm_r_hand,  # 4
        leaf(spec["leaf"]),  # 5
        leaf_shade(spec["leaf"]),  # 6
        body(),  # 7
        highlight(),  # 8 belly
        *under_shade(),  # 9, 10 occlusion crescents (over the belly)
        whites[0],  # 11 eye_white_L
        whites[1],  # 12 eye_white_R
        pupils[0],  # 13 pupil_L
        pupils[1],  # 14 pupil_R
        spec["mouth"](),  # 15 mouth
        *blush(),  # 16, 17
        *mark_paths(),  # 18-21 singularity mark
        *spec["extras"](),  # 22+ extras
    ]
    body_xml = "\n  ".join(parts)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" '
        'width="200" height="200">\n  ' + body_xml + "\n</svg>\n"
    )


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # Wipe stale mode files only — bubble_*.svg and other assets stay put.
    valid_modes = set(MODES.keys())
    for f in OUT_DIR.glob("*.svg"):
        stem = f.stem
        if stem not in valid_modes and not stem.startswith("bubble_"):
            f.unlink()
    for name, spec in MODES.items():
        path = OUT_DIR / f"{name}.svg"
        path.write_text(render_mode(name, spec))
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
