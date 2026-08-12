"""Sprout — Frame Zero's PiCreature-style mascot for ManimCE.

Single runtime module. The companion `generate.py` is a CLI tool that
writes the mode SVGs into svg/; nothing here imports it.

What's in here:
    - Bubble classes: SpeechBubble, ThoughtBubble (use 3b1b's bubble SVGs)
    - Sprout: the character itself, swappable modes, look_at, blink, etc.
    - Living leaf, ALWAYS ON (no api): idle sway from __init__, ambient
      mote stream managed by SproutIn/SproutOut. Optional extras:
      LeafGlow halo, spawn_leaf_motes() insight bursts
    - Animations: SproutIn/SproutOut (never fade a sprout), Blink, Says, Thinks
    - Scene preset: SproutClassroomScene (teacher + 3 students)

Quick start:

    from sprout import Sprout, Says, SproutClassroomScene

    sprout = Sprout(mode="plain").scale(1.5)
    self.add(sprout)
    self.play(sprout.change_mode_anim("wave"))
    self.play(sprout.animate.look_at(target))
    self.play(Blink(sprout))
    self.play(Says(sprout, "hello!"))

Every mode SVG shares an identical 20-submobject core layout (see generate.py),
so swapping modes interpolates each named part 1:1. Pose modes (wave/
point/celebrate) move always-present arm paths in place rather than
fading limbs in and out.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterable
from itertools import pairwise
from pathlib import Path

import numpy as np
from manim import (
    BLACK,
    DOWN,
    DR,
    LEFT,
    RIGHT,
    UL,
    UR,
    WHITE,
    Animation,
    AnimationGroup,
    Circle,
    Dot,
    FadeIn,
    FadeOut,
    GrowFromPoint,
    Mobject,
    Scene,
    SVGMobject,
    Text,
    Transform,
    ValueTracker,
    VGroup,
    Wait,
)

SVG_DIR = Path(__file__).parent / "svg"

AVAILABLE_MODES = (
    "plain",
    "happy",
    "sad",
    "angry",
    "surprised",
    "love",
    "thinking",
    "sleepy",
    "speaking",
    "celebrate",
    "wave",
    "point_left",
    "point_right",
    "point_up",
)

# Canonical fixed-layout indices (locked by generate.py).
SHADOW_I = 0
ARM_L_I, HAND_L_I, ARM_R_I, HAND_R_I = 1, 2, 3, 4
LEAF_I = 5
LEAF_SHADE_I = 6
BODY_I = 7
HIGHLIGHT_I = 8  # belly patch
SHADE_SOFT_I, SHADE_CORE_I = 9, 10  # occlusion crescents (over the belly)
EYE_L_I, EYE_R_I = 11, 12
PUPIL_L_I, PUPIL_R_I = 13, 14
MOUTH_I = 15
BLUSH_L_I, BLUSH_R_I = 16, 17
MARK_I = (18, 19, 20, 21)  # singularity mark: ring, blade, two fillets
CORE_COUNT = 22  # everything from index 22 onwards is mode-specific extras

# Stroke bookkeeping (see Sprout._normalize_strokes).
_BELLY_W_SVG = 54.0  # generate.highlight() ellipse: rx=27, identical per mode
_MANIM_STROKE_UNIT = 0.01  # scene units of ink per manim stroke_width unit


# ============================================================== bubbles


class _BubbleBase(SVGMobject):
    """Common pinning + content-fitting behavior for speech/thought bubbles.

    Visual shape comes from 3b1b's hand-drawn bubble SVGs (in svg/).
    """

    SVG_FILE: str = ""
    DEFAULT_HEIGHT = 2.2
    INNER_PAD = 0.75  # content fills this fraction of the body region

    def __init__(
        self,
        content: str | Mobject | None = None,
        height: float | None = None,
        fill_color=WHITE,
        stroke_color=BLACK,
        stroke_width: float = 3,
        flip: bool = False,
        **kwargs,
    ):
        super().__init__(
            str(SVG_DIR / self.SVG_FILE),
            height=height or self.DEFAULT_HEIGHT,
            **kwargs,
        )
        self.set_fill(fill_color, opacity=1)
        self.set_stroke(stroke_color, width=stroke_width)
        self._is_flipped = False
        if flip:
            self.flip_for_left_speaker()
        self.content: Mobject | None = None
        if content is not None and content != "":
            self.add_content(content)

    # Rows at least this wide (as a fraction of the widest row) count as
    # the balloon proper. The tail is narrower and drops out.
    BODY_ROW = 0.55

    # subclass hooks
    def _tail_anchor(self) -> np.ndarray:
        raise NotImplementedError

    def _body_size(self) -> tuple[float, float]:
        raise NotImplementedError

    def _outline_points(self) -> np.ndarray:
        """The bubble shape, densely sampled. Content is excluded, so this
        measures the drawing rather than whatever was written inside it."""
        pts = []
        for part in self.submobjects:
            if part is self.content:
                continue
            for sub in part.family_members_with_points():
                p = sub.points
                for i in range(0, len(p) - 3, 4):
                    a, b, c, d = p[i : i + 4]
                    for t in np.linspace(0.0, 1.0, 10):
                        u = 1.0 - t
                        pts.append(
                            u**3 * a + 3 * u * u * t * b + 3 * u * t * t * c + t**3 * d
                        )
        return np.array(pts)

    def _body_center(self) -> np.ndarray:
        """Where content goes: the center of the balloon proper, measured.

        Scans the shape row by row and keeps the rows at least BODY_ROW as
        wide as the widest one, which is the balloon with the tail (and a
        thought bubble's trailing dots) excluded. Fixed offsets were used
        here before and could not be right: they left short lines visibly
        off-center, and pushed the text the wrong way on flipped bubbles.
        Measuring also means a custom bubble SVG lands its text correctly
        without touching this class.
        """
        pts = self._outline_points()
        ys = pts[:, 1]
        rows = np.linspace(ys.min(), ys.max(), 64)
        widths, lows, highs = [], [], []
        for y0, y1 in pairwise(rows):
            in_row = (ys >= y0) & (ys < y1)
            if in_row.sum() < 2:  # a row the outline barely touches
                widths.append(0.0)
                lows.append(np.nan)
                highs.append(np.nan)
                continue
            xs = pts[in_row, 0]
            widths.append(float(xs.max() - xs.min()))
            lows.append(float(xs.min()))
            highs.append(float(xs.max()))
        widths = np.array(widths)
        body = widths >= self.BODY_ROW * widths.max()
        x0 = np.nanmin(np.array(lows)[body])
        x1 = np.nanmax(np.array(highs)[body])
        y0 = rows[:-1][body].min()
        y1 = rows[1:][body].max()
        return np.array([0.5 * (x0 + x1), 0.5 * (y0 + y1), 0.0])

    # API
    def add_content(self, content: str | Mobject, font_size: int = 28) -> _BubbleBase:
        if self.content is not None:
            self.remove(self.content)
        if isinstance(content, str):
            mob = Text(content, font_size=font_size, color=BLACK)
        else:
            mob = content
        bw, bh = self._body_size()
        if mob.width > bw * self.INNER_PAD:
            mob.scale_to_fit_width(bw * self.INNER_PAD)
        if mob.height > bh * self.INNER_PAD:
            mob.scale_to_fit_height(bh * self.INNER_PAD)
        mob.move_to(self._body_center())
        self.content = mob
        self.add(mob)
        return self

    def flip_for_left_speaker(self) -> _BubbleBase:
        """Flip the bubble shape so the tail points to the right (for a
        speaker on the bubble's right). Call before add_content."""
        old_content = self.content
        if old_content is not None:
            self.remove(old_content)
            self.content = None
        self.flip(axis=np.array([0.0, 1.0, 0.0]))
        self._is_flipped = not self._is_flipped
        if old_content is not None:
            self.add_content(old_content)
        return self

    def pin_to(
        self, speaker: Mobject, direction: np.ndarray | None = None, gap: float = 0.15
    ) -> _BubbleBase:
        """Place the tail tip near `speaker`'s shoulder corner. By default
        the bubble opens toward the center of the frame, so speakers near
        either edge never push their bubble off-screen."""
        if direction is None:
            direction = UL if speaker.get_center()[0] > 0 else UR
        want_flip = direction[0] < 0
        if want_flip != self._is_flipped:
            self.flip_for_left_speaker()
        target = speaker.get_corner(direction)
        anchor = self._tail_anchor()
        offset = np.array([0.0, gap, 0.0])
        self.shift(target + offset - anchor)
        return self


class SpeechBubble(_BubbleBase):
    """3b1b's speech-balloon SVG. Tail at lower-left by default."""

    SVG_FILE = "bubble_speech.svg"

    def _tail_anchor(self) -> np.ndarray:
        path = self.submobjects[0]
        pts = path.points
        idx = pts[:, 1].argmin()  # bottom-most point of the path
        return pts[idx].copy()

    def _body_size(self) -> tuple[float, float]:
        return (0.65 * self.width, 0.55 * self.height)


class ThoughtBubble(_BubbleBase):
    """3b1b's thought-cloud SVG: 3 descending dots + cloud path."""

    SVG_FILE = "bubble_thought.svg"
    DEFAULT_HEIGHT = 2.4

    def _tail_anchor(self) -> np.ndarray:
        # Smallest descending dot is submobject[2].
        return self.submobjects[2].get_center().copy()

    def _body_size(self) -> tuple[float, float]:
        body = self.submobjects[3]  # the cloud, minus the descending dots
        return (body.width, body.height)


# ============================================================== sprout


class Sprout(SVGMobject):
    """Frame Zero mascot — Pi-style swappable expression character."""

    _CANON_BODY_H = 1.35  # body height every mode is normalized to at birth

    def __init__(self, mode: str = "plain", **kwargs):
        if mode not in AVAILABLE_MODES:
            raise ValueError(
                f"Unknown sprout mode {mode!r}; available: {AVAILABLE_MODES}"
            )
        self.mode = mode
        self._active_bubble: Mobject | None = None
        self._motes: _LeafMotes | None = None  # managed by SproutIn/SproutOut
        self.purposeful_looking_direction: np.ndarray | None = None
        super().__init__(str(SVG_DIR / f"{mode}.svg"), **kwargs)
        self._name_parts()
        # SVGMobject normalizes by CONTENT bbox, so poses with raised arms
        # would get a smaller body than "plain". Re-normalize on the body —
        # identical geometry in every mode — so all modes are born with the
        # character at the same true size (1.35 ≈ plain's body at height 2).
        self.scale(self._CANON_BODY_H / self.body.height)
        self._normalize_strokes()
        self._rebuild_pupils()
        # The leaf is ALWAYS alive — sway from birth (the updater only
        # ticks once the sprout is in a scene), motes via SproutIn.
        self._start_leaf_sway()

    # ---------------------------------------------------------------- parts

    def _name_parts(self) -> None:
        subs = self.submobjects
        if len(subs) < CORE_COUNT:
            raise RuntimeError(
                f"Sprout SVG for {self.mode!r} has {len(subs)} submobjects, "
                f"expected at least {CORE_COUNT}. Re-run generate.py."
            )
        self.shadow = subs[SHADOW_I]
        self.left_arm = subs[ARM_L_I]
        self.left_hand = subs[HAND_L_I]
        self.right_arm = subs[ARM_R_I]
        self.right_hand = subs[HAND_R_I]
        self.arms = VGroup(self.left_arm, self.right_arm)
        self.hands = VGroup(self.left_hand, self.right_hand)
        self.leaf = subs[LEAF_I]
        self.leaf_shade = subs[LEAF_SHADE_I]
        self.body = subs[BODY_I]
        self.highlight = subs[HIGHLIGHT_I]
        self.belly = self.highlight
        self.under_shade = VGroup(subs[SHADE_SOFT_I], subs[SHADE_CORE_I])
        self.eyes = VGroup(subs[EYE_L_I], subs[EYE_R_I])
        self.pupils = VGroup(subs[PUPIL_L_I], subs[PUPIL_R_I])
        self.mouth = subs[MOUTH_I]
        self.blush = VGroup(subs[BLUSH_L_I], subs[BLUSH_R_I])
        self.mark = VGroup(*(subs[i] for i in MARK_I))
        self.extras = VGroup(*subs[CORE_COUNT:])

    def _normalize_strokes(self) -> None:
        """Put every SVG stroke back in proportion with the drawing.

        Manim keeps stroke_width in its own frame-relative unit, so a stroked
        path imported from SVG carries the raw SVG number (e.g. 2.3) no matter
        how the geometry was scaled — the ring of the belly mark, the mouth
        and the eye rims all rendered as hairlines, and got *relatively*
        thinner every time the sprout was scaled up. Restate each width as
        the ink thickness the artwork asks for, in scene units.
        """
        f = self.belly.width / _BELLY_W_SVG  # scene units per SVG unit
        for sub in self.family_members_with_points():
            w = sub.get_stroke_width()  # still the raw SVG number here
            if w:
                sub.set_stroke(width=w * f / _MANIM_STROKE_UNIT)
        self._ink_scales = True

    def scale(self, scale_factor, scale_stroke: bool | None = None, **kwargs):
        """Scale ink along with geometry — a sprout is a drawing, not a plot.

        Manim's default (scale_stroke=False) keeps line weights fixed, so
        outlines thin out as the character grows. Only from _normalize_strokes
        onwards though: the scaling manim does while parsing the SVG has to
        leave the authored widths alone for that method to read them.
        """
        if scale_stroke is None:
            scale_stroke = bool(getattr(self, "_ink_scales", False))
        return super().scale(scale_factor, scale_stroke=scale_stroke, **kwargs)

    def _rebuild_pupils(self) -> None:
        """Replace SVG-derived pupils with true Circles for clean look() math."""
        for eye, pupil in zip(self.eyes, self.pupils):
            # Keep the SVG's per-mode pupil size (wide eyes get small pupils
            # etc.) — only swap the path for a true Circle, plus the
            # pi-creature glint dot riding along inside it.
            pupil_r = 0.5 * pupil.get_width()
            replacement = Circle(
                radius=pupil_r,
                color=BLACK,
                fill_opacity=pupil.get_fill_opacity(),
                stroke_width=0,
            )
            glint = Circle(
                radius=0.3 * pupil_r,
                color=WHITE,
                fill_opacity=pupil.get_fill_opacity(),
                stroke_width=0,
            )
            glint.shift(0.35 * pupil_r * UR)
            replacement.add(glint)
            replacement.move_to(pupil)
            pupil.become(replacement)

    # ---------------------------------------------------------------- gaze

    def look_at_viewer(self) -> Sprout:
        """Turn to the audience — centered pupils ARE the facing-camera pose.

        The counterpart to look_at(): a sprout keeps watching whatever you
        pointed it at (through mode changes too), so coming back to the
        viewer is its own beat. There is no direction argument that can
        express it, since look() aims pupils AWAY from center.
        """
        self.purposeful_looking_direction = None
        for eye, pupil in zip(self.eyes, self.pupils):
            pupil.move_to(eye.get_center())
        return self

    def look(self, direction) -> Sprout:
        """Aim pupils along `direction` (3-vector, scene space).

        A zero-length direction ("look at nothing in particular") re-centers
        the pupils rather than silently doing nothing — look(ORIGIN) reading
        as a no-op left characters staring off-screen. Prefer the explicit
        look_at_viewer() in scene code.
        """
        direction = np.asarray(direction, dtype=float)
        norm = np.linalg.norm(direction)
        if norm < 1e-9:
            return self.look_at_viewer()
        d = direction / norm
        self.purposeful_looking_direction = d
        for eye, pupil in zip(self.eyes, self.pupils):
            # Eye-local axes so flipped/scaled eyes still track correctly.
            c = eye.get_center()
            right = eye.get_right() - c
            up = eye.get_top() - c
            vect = d[0] * right + d[1] * up
            v_norm = np.linalg.norm(vect)
            if v_norm < 1e-9:
                continue
            p_radius = 0.5 * pupil.get_width()
            scale = max(v_norm - 0.75 * p_radius, 0.0) / v_norm
            pupil.move_to(c + vect * scale)
        return self

    def look_at(self, point_or_mobject) -> Sprout:
        if hasattr(point_or_mobject, "get_center"):
            point = point_or_mobject.get_center()
        else:
            point = np.asarray(point_or_mobject, dtype=float)
        return self.look(point - self.eyes.get_center())

    def make_eye_contact(self, other: Sprout) -> Sprout:
        self.look_at(other.eyes)
        other.look_at(self.eyes)
        return self

    # ---------------------------------------------------------------- mode

    def get_mode(self) -> str:
        return self.mode

    def change_mode(self, new_mode: str) -> Sprout:
        """Snap to `new_mode` in place (no animation).

        Part-by-part, NOT self.become(target): whole-mobject become aligns
        family sizes by interleaving padding when the extras count differs
        (e.g. love's hearts), which scrambles the fixed core layout.
        """
        if new_mode == self.mode:
            return self
        target = self._build_replacement(new_mode)
        for i in range(CORE_COUNT):
            self.submobjects[i].become(target.submobjects[i])
        for old in list(self.submobjects[CORE_COUNT:]):
            self.remove(old)
        self.add(*target.submobjects[CORE_COUNT:])
        self.mode = new_mode
        self._name_parts()
        return self

    def change_mode_anim(self, new_mode: str, run_time: float = 0.4) -> Animation:
        """Animate to `new_mode`. Per-part Transforms keep things smooth."""
        if new_mode == self.mode:
            # No-op but valid playable Animation — empty AnimationGroups
            # crash when nested inside another group.
            return Wait(0.001)

        target = self._build_replacement(new_mode)

        anims = []
        for i in range(CORE_COUNT):
            anims.append(Transform(self.submobjects[i], target.submobjects[i]))

        old_extras = VGroup(*self.submobjects[CORE_COUNT:])
        new_extras = VGroup(*target.submobjects[CORE_COUNT:])
        if len(old_extras) > 0:
            anims.append(FadeOut(old_extras, run_time=run_time))
        if len(new_extras) > 0:
            self.add(*new_extras)
            anims.append(FadeIn(new_extras, run_time=run_time))

        group = AnimationGroup(*anims, run_time=run_time)
        original_cleanup = group.clean_up_from_scene

        def cleanup(scene):
            original_cleanup(scene)
            for old in old_extras:
                if old in self.submobjects:
                    self.remove(old)
            self.mode = new_mode
            self._name_parts()

        group.clean_up_from_scene = cleanup
        return group

    def _build_replacement(self, new_mode: str) -> Sprout:
        new = Sprout(mode=new_mode)
        # Match size on the BODY (identical geometry in every mode) — the
        # full bbox grows with raised arms, so matching heights on it
        # visibly shrank the character in celebrate/point poses.
        new.scale(self.body.height / new.body.height)
        # Eye-anchored alignment: keep the FACE in the same spot when the
        # arms/extras change the bbox center.
        new.shift(self.eyes.get_center() - new.eyes.get_center())
        if self.purposeful_looking_direction is not None:
            new.look(self.purposeful_looking_direction)
            new.purposeful_looking_direction = self.purposeful_looking_direction
        return new

    # ---------------------------------------------------------------- living leaf

    def _start_leaf_sway(self, amp_ratio: float = 0.05) -> Sprout:
        """Flame-like idle waver (at breeze tempo) — always on, from
        __init__. Not a public API: the leaf being alive is part of what
        a Sprout IS, not an option.

        Safe to leave running across change_mode_anim / shifts / scales:
        each frame the updater diffs the leaf's points against what it wrote
        last frame, and folds any external change (a Transform mid-morph, a
        shift) into its base shape before re-applying the sway offsets.
        `amp_ratio` is the tip amplitude as a fraction of leaf height, so
        it is scale-invariant.
        """
        if getattr(self, "_sway_fn", None) is not None:
            return self
        state = {
            "t": 0.0,
            "owner": self.leaf,
            "leaf": {
                "base": self.leaf.points.copy(),
                "written": self.leaf.points.copy(),
            },
            "shade": {
                "base": self.leaf_shade.points.copy(),
                "written": self.leaf_shade.points.copy(),
            },
        }
        self._sway_state = state
        sprout = self

        def sway(mob, dt):
            # Copies (deepcopy does not remap closures) share THIS state —
            # manim ticks the internal starting/target copies of every
            # animation, and three leaves feeding one rebase state inflate
            # each other. Only the leaf this updater was born on may act.
            # It moves BOTH the leaf and its shade overlay, weighting the
            # shade by the leaf's height range so the layers never tear.
            if mob is not state["owner"]:
                return
            state["t"] += dt
            t = state["t"]
            drift = 0.62 * math.sin(1.3 * t) + 0.38 * math.sin(2.9 * t + 1.7)
            wob_y = math.sin(1.9 * t + 0.9)
            # rebase both parts first, then derive the shared frame
            for part, d in (("leaf", sprout.leaf), ("shade", sprout.leaf_shade)):
                st = state[part]
                if d.points.shape != st["written"].shape:
                    st["base"] = d.points.copy()  # topology changed: adopt
                else:
                    st["base"] = st["base"] + (d.points - st["written"])
            ybase = state["leaf"]["base"][:, 1]
            y0 = ybase.min()
            h = max(ybase.max() - y0, 1e-6)
            amp = amp_ratio * h
            for part, d in (("leaf", sprout.leaf), ("shade", sprout.leaf_shade)):
                st = state[part]
                base = st["base"]
                w = np.clip((base[:, 1] - y0) / h, 0.0, 1.0) ** 1.7
                ripple = 0.25 * np.sin(2.2 * t + 3.0 * w)
                out = base.copy()
                out[:, 0] += amp * w * (drift + ripple)
                out[:, 1] += 0.35 * amp * w * wob_y
                d.points = out
                st["written"] = out.copy()

        self._sway_fn = sway
        self.leaf.add_updater(sway)
        return self

    # ---------------------------------------------------------------- misc

    def to_corner_creature(
        self, vect=None, scale_factor: float = 0.6, buff: float = 0.5
    ) -> Sprout:
        """Pi-style: shrink and tuck into a corner. Defaults to bottom-left."""
        if vect is None:
            vect = DOWN + LEFT
        self.scale(scale_factor)
        self.to_corner(vect, buff=buff)
        return self

    # ---------------------------------------------------------------- bubbles

    def get_bubble(self, content="", bubble_class=None, **kwargs):
        """Build a bubble pinned to this sprout. Returns the bubble mobject."""
        bubble_class = bubble_class or SpeechBubble
        bubble = bubble_class(content, **kwargs)
        bubble.pin_to(self)
        self._active_bubble = bubble
        return bubble

    def says(self, content: str, mode: str = "speaking", **kwargs):
        """Returns (bubble, animation). Caller plays the animation."""
        bubble = self.get_bubble(content, bubble_class=SpeechBubble, **kwargs)
        anim = AnimationGroup(self.change_mode_anim(mode), FadeIn(bubble))
        return bubble, anim

    def thinks(self, content: str, mode: str = "thinking", **kwargs):
        bubble = self.get_bubble(content, bubble_class=ThoughtBubble, **kwargs)
        anim = AnimationGroup(self.change_mode_anim(mode), FadeIn(bubble))
        return bubble, anim

    def remove_bubble_anim(self, back_to: str = "plain"):
        """Animation that fades out the active bubble and returns to a base mode."""
        if self._active_bubble is None:
            return AnimationGroup()
        bubble = self._active_bubble
        self._active_bubble = None
        return AnimationGroup(FadeOut(bubble), self.change_mode_anim(back_to))


# ============================================================== living leaf fx

GLOW_COLOR = "#c8f07a"
MOTE_COLOR = "#e2ff9e"


class LeafGlow(VGroup):
    """Fake radial bioluminescent halo pinned to a sprout's leaf blade.

    Manim has no 2D light sources, so the glow is concentric translucent
    discs that breathe slowly. Drive it through `level`:

        glow = LeafGlow(sprout)
        self.add(glow)
        self.bring_to_back(glow)           # halo sits behind the character
        self.play(glow.level.animate.set_value(0.4))   # thinking
        self.play(glow.level.animate.set_value(1.0), run_time=0.35)  # flare!
        self.play(glow.level.animate.set_value(0.15))  # afterglow

    0 = off, ~0.4 = thinking, 1 = insight flare.
    """

    N_LAYERS = 5

    def __init__(self, sprout: Sprout, color=GLOW_COLOR, max_opacity: float = 0.11):
        super().__init__()
        self.level = ValueTracker(0.0)
        self._t = 0.0
        base_r = [
            0.09 * sprout.height + 0.053 * sprout.height * k
            for k in range(self.N_LAYERS)
        ]
        for r in base_r:
            self.add(
                Circle(radius=r, stroke_width=0, fill_color=color, fill_opacity=0.0)
            )

        def track(mob, dt):
            self._t += dt
            lvl = self.level.get_value()
            pulse = 1.0 + 0.10 * math.sin(2.1 * self._t)
            leaf = sprout.leaf
            anchor = 0.72 * leaf.get_top() + 0.28 * leaf.get_center()
            for k, (c, r0) in enumerate(zip(mob, base_r)):
                c.move_to(anchor)
                c.width = 2 * r0 * pulse * (1.0 + 0.9 * lvl)
                c.set_fill(opacity=lvl * pulse * max_opacity * (1.0 - 0.15 * k))

        self.add_updater(track)


def _ember_step(o, a, u, vx, vy, wob_f, wob_a):
    """Ember physics, shared by ambient motes and insight bursts: the rise
    decelerates as drag wins, and the sideways drift accelerates gently so
    the path bows outward like a spark leaving a campfire."""
    x = o[0] + vx * a + 0.5 * (0.8 * vx) * a * a + wob_a * math.sin(wob_f * a)
    y = o[1] + vy * a * (1.0 - 0.35 * u)
    return np.array([x, y, 0.0])


class _MoteDot(Dot):
    """Pooled ember particle. `flight` holds the in-flight state dict
    (birth time, velocities, wobble) and is None while the dot is idle."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.flight: dict | None = None


class _LeafMotes(VGroup):
    """Ambient sparkle: motes shed off the leaf tip continuously.

    Internal — never instantiated by scene code. SproutIn adds one of
    these per sprout when the character enters; SproutOut removes it.
    The motes being there is part of what a Sprout IS, not an option.

    Cadence is Gaussian — one mote every N(interval, sigma) seconds — so it
    breathes without ticking like a metronome. Each mote samples the leaf
    tip at birth, so the stream follows the character through sway, mode
    changes, and shifts. A fixed pool of dots is recycled: no mobjects are
    ever added mid-scene and long scenes don't accumulate garbage.
    """

    POOL = 8
    _instances = 0  # per-instance seed → duet sprouts don't sparkle in sync

    def __init__(
        self,
        sprout: Sprout,
        interval: float = 0.8,
        sigma: float = 0.1,
        seed: int | None = None,
        color=MOTE_COLOR,
    ):
        super().__init__()
        if seed is None:
            seed = _LeafMotes._instances
            _LeafMotes._instances += 1
        self._sprout = sprout
        self._interval = interval
        self._sigma = sigma
        self._rng = random.Random(seed)
        self._t = 0.0
        self._next = 0.4  # first mote shortly after the emitter appears
        self._pool = [
            _MoteDot(radius=0.01, color=color, fill_opacity=0.0)
            for _ in range(self.POOL)
        ]
        self.add(*self._pool)
        self.add_updater(self._tick)

    def _tick(self, mob, dt):
        self._t += dt
        t = self._t
        rng = self._rng
        if t >= self._next:
            self._next = t + max(rng.gauss(self._interval, self._sigma), 0.1)
            dot = next((d for d in self._pool if d.flight is None), None)
            if dot is not None:  # pool exhausted → silently skip one beat
                h = self._sprout.height
                dot.flight = {
                    "born": t,
                    "life": 1.2 + 0.8 * rng.random(),
                    "o": np.array(self._sprout.leaf.get_top()),
                    "vx": 0.10 * h * (rng.random() - 0.5),
                    "vy": (0.14 + 0.12 * rng.random()) * h,
                    "wob_f": 3.0 + 3.0 * rng.random(),
                    "wob_a": (0.012 + 0.016 * rng.random()) * h,
                }
                dot.width = 2 * (0.005 + 0.006 * rng.random()) * h
        for dot in self._pool:
            m = dot.flight
            if m is None:
                continue
            a = t - m["born"]
            if a > m["life"]:
                dot.set_fill(opacity=0.0)
                dot.flight = None
                continue
            u = a / m["life"]
            dot.move_to(
                _ember_step(m["o"], a, u, m["vx"], m["vy"], m["wob_f"], m["wob_a"])
            )
            dot.set_fill(opacity=0.85 * min(u / 0.2, 1.0) * (1.0 - u) ** 1.4)


def spawn_leaf_motes(
    scene: Scene,
    sprout: Sprout,
    n: int = 8,
    seed: int = 0,
    color=MOTE_COLOR,
) -> None:
    """One-shot burst of motes off the leaf tip — the insight moment.

    (The continuous ambient trickle is built in — this is the extra.) Motes are
    self-driving and fade themselves out — just call and keep animating;
    make sure ~2 s of animation/wait follows so they live out their lives.
    """
    rng = random.Random(seed)
    h = sprout.height
    origin = np.array(sprout.leaf.get_top())
    for _ in range(n):
        r = (0.006 + 0.007 * rng.random()) * h
        mote = Dot(radius=r, color=color, fill_opacity=0.0)
        mote.move_to(origin)
        life = 1.1 + 0.8 * rng.random()
        delay = 0.35 * rng.random()
        vx = 0.28 * h * (rng.random() - 0.5)
        vy = (0.17 + 0.16 * rng.random()) * h
        wob_f = 3.0 + 3.0 * rng.random()
        wob_a = (0.016 + 0.019 * rng.random()) * h
        state = {"age": -delay}
        origin_snapshot = origin.copy()

        def drift(
            mob,
            dt,
            state=state,
            vx=vx,
            vy=vy,
            wob_f=wob_f,
            wob_a=wob_a,
            life=life,
            origin=origin_snapshot,
        ):
            state["age"] += dt
            a = state["age"]
            if a < 0:
                return
            if a > life:
                mob.set_fill(opacity=0.0)
                mob.clear_updaters()
                return
            u = a / life
            mob.move_to(_ember_step(origin, a, u, vx, vy, wob_f, wob_a))
            # Fade in fast, out slow.
            mob.set_fill(opacity=0.95 * min(u / 0.15, 1.0) * (1.0 - u) ** 1.3)

        mote.add_updater(drift)
        scene.add(mote)


# ============================================================== animations


def _clamped_ease_out_back(t: float) -> float:
    # Manim can pass alpha slightly outside [0, 1] on edge frames — clamp
    # first, or the overshoot math extrapolates and the render hangs.
    t = min(max(t, 0.0), 1.0)
    # Softened back-ease: the textbook c1=1.70158 overshoots ~10%, which
    # visibly balloons the long thin leaf for a few frames on entrance.
    # ~4% keeps the bounce without the inflation.
    c1 = 0.75
    u = t - 1.0
    return 1.0 + (c1 + 1.0) * u**3 + c1 * u**2


class SproutIn(GrowFromPoint):
    """Entrance: grow up from the ground with a small overshoot bounce.

    Use this instead of FadeIn. Fading a layered character makes the body
    translucent mid-fade, exposing the arm segments tucked behind it
    (ghost-anatomy). Scaling never goes translucent — and a sprout growing
    out of the ground is on-brand anyway.

    Also switches on the character's ambient mote stream once the entrance
    finishes (SproutOut removes it) — a sprout in a scene is simply alive.
    """

    def __init__(self, sprout: Sprout, run_time: float = 0.5, **kwargs):
        kwargs.setdefault("rate_func", _clamped_ease_out_back)
        super().__init__(sprout, sprout.get_bottom(), run_time=run_time, **kwargs)
        self._sprout = sprout  # self.mobject is only typed as Mobject

    def clean_up_from_scene(self, scene) -> None:
        super().clean_up_from_scene(scene)
        sprout = self._sprout
        if sprout._motes is None:
            sprout._motes = _LeafMotes(sprout)
        scene.add(sprout._motes)


class SproutOut(GrowFromPoint):
    """Exit: shrink back into the ground. The FadeOut replacement."""

    def __init__(self, sprout: Sprout, run_time: float = 0.35, **kwargs):
        kwargs.setdefault("reverse_rate_function", True)
        kwargs.setdefault("remover", True)
        super().__init__(sprout, sprout.get_bottom(), run_time=run_time, **kwargs)
        self._sprout = sprout

    def begin(self):
        # Transform leaves the mobject at the shrunk end state; snapshot it
        # so the sprout is intact if it re-enters the scene later.
        self._restore = self.mobject.copy()
        super().begin()

    def clean_up_from_scene(self, scene):
        super().clean_up_from_scene(scene)
        self.mobject.become(self._restore)
        if self._sprout._motes is not None:
            scene.remove(self._sprout._motes)


class Blink(Animation):
    """Squash the eyes shut and back open. Single-frame, no copy required."""

    def __init__(self, sprout: Sprout, run_time: float = 0.18, **kwargs):
        super().__init__(sprout, run_time=run_time, **kwargs)
        self.sprout = sprout

    def begin(self):
        self.eye_group = VGroup(self.sprout.eyes, self.sprout.pupils)
        self.start_data = [
            np.array(m.points) for m in self.eye_group.family_members_with_points()
        ]
        self.bottom_y = self.eye_group.get_bottom()[1]
        super().begin()

    def interpolate_mobject(self, alpha: float) -> None:
        # Triangle wave: 0 → 1 (closed) → 0.
        squash = 1.0 - abs(2 * alpha - 1)
        for mob, start_pts in zip(
            self.eye_group.family_members_with_points(), self.start_data
        ):
            pts = start_pts.copy()
            pts[:, 1] = start_pts[:, 1] * (1 - squash) + self.bottom_y * squash
            mob.points = pts


class Says(AnimationGroup):
    """Build a speech bubble + change_mode + fade in, all as one animation.

    The bubble is attached to `sprout._active_bubble` so it can be removed
    later via `sprout.remove_bubble_anim()`.
    """

    def __init__(
        self,
        sprout: Sprout,
        content: str,
        mode: str = "speaking",
        bubble_class=None,
        **kwargs,
    ):
        bubble_class = bubble_class or SpeechBubble
        bubble = bubble_class(content)
        bubble.pin_to(sprout)
        sprout._active_bubble = bubble
        super().__init__(sprout.change_mode_anim(mode), FadeIn(bubble), **kwargs)
        self.bubble = bubble


class Thinks(Says):
    def __init__(self, sprout: Sprout, content: str, mode: str = "thinking", **kwargs):
        super().__init__(
            sprout, content, mode=mode, bubble_class=ThoughtBubble, **kwargs
        )


# ============================================================== scene preset


class SproutClassroomScene(Scene):
    """Scene preset with one teacher (right) + three students (left).

    Mirrors 3b1b's `TeacherStudentsScene` interaction patterns.

        class MyExplainer(SproutClassroomScene):
            def construct(self):
                self.fade_in_classroom()
                self.teacher_says("Today we'll see how it works.")
                self.change_student_modes("happy", "thinking", "surprised")
    """

    TEACHER_SCALE = 1.2
    STUDENT_SCALE = 0.9
    TEACHER_BUFF = 1.0
    STUDENT_BUFF = 1.0

    def setup(self):
        super().setup()
        self.teacher = (
            Sprout(mode="plain")
            .scale(self.TEACHER_SCALE)
            .to_corner(DR, buff=self.TEACHER_BUFF)
        )
        # A typed list is the API (students are Sprouts); the VGroup is
        # only the layout/animation handle over the same objects.
        self.students: list[Sprout] = [
            Sprout(mode="plain").scale(self.STUDENT_SCALE) for _ in range(3)
        ]
        self.student_group = (
            VGroup(*self.students)
            .arrange(RIGHT, buff=0.5)
            .to_edge(DOWN, buff=0.5)
            .to_edge(LEFT, buff=self.STUDENT_BUFF)
        )
        for s in self.students:
            s.look_at(self.teacher.eyes)
        # Facing is done with gaze, not mirroring — Sprout has one silhouette.
        self.teacher.look_at(self.student_group)

    # mass changes
    def fade_in_classroom(self, run_time: float = 1.0) -> None:
        # Grow-from-ground, slightly staggered — never crossfade sprouts
        # (translucent bodies expose the arm layers behind them).
        anims = [SproutIn(s) for s in (self.teacher, *self.students)]
        self.play(
            AnimationGroup(*anims, lag_ratio=0.15),
            run_time=run_time,
        )

    def fade_out_classroom(self, run_time: float = 0.6) -> None:
        anims = [SproutOut(s) for s in (self.teacher, *self.students)]
        self.play(AnimationGroup(*anims, lag_ratio=0.1), run_time=run_time)

    # teacher
    def teacher_says(
        self, content, mode: str = "speaking", look_at_arg=None, run_time: float = 1.5
    ) -> None:
        if look_at_arg is not None:
            self.teacher.look_at(look_at_arg)
        self.play(Says(self.teacher, content, mode=mode), run_time=run_time)

    def teacher_thinks(self, content, run_time: float = 1.5) -> None:
        self.play(Thinks(self.teacher, content), run_time=run_time)

    def remove_teacher_bubble(
        self, back_to: str = "plain", run_time: float = 0.5
    ) -> None:
        anim = self.teacher.remove_bubble_anim(back_to=back_to)
        if anim is not None and getattr(anim, "animations", None):
            self.play(anim, run_time=run_time)

    # students
    def change_student_modes(
        self, *modes: str, look_at_arg=None, run_time: float = 0.5
    ) -> None:
        """Pass up to 3 modes; missing slots are left unchanged."""
        anims = []
        for student, mode in zip(self.students, modes):
            if mode is None:
                continue
            anims.append(student.change_mode_anim(mode))
        if look_at_arg is not None:
            for s in self.students:
                s.look_at(look_at_arg)
        if anims:
            self.play(*anims, run_time=run_time)

    def students_say(self, *contents, run_time: float = 1.5) -> None:
        """Each student speaks one bubble simultaneously. Pass None to skip a slot."""
        anims = []
        for student, content in zip(self.students, contents):
            if content is None:
                continue
            anims.append(Says(student, content))
        if anims:
            self.play(*anims, run_time=run_time)

    def look_at(self, target, who: Iterable[Sprout] | None = None) -> None:
        """All sprouts (or a subset) glance at a target. Static — no animation."""
        crew = list(who) if who is not None else [self.teacher, *self.students]
        for s in crew:
            s.look_at(target)
