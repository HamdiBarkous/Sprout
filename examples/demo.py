"""Visual smoke tests for the Sprout character.

uv run manim -qh examples/demo.py SproutDemo
uv run manim -qh examples/demo.py SproutShowcase
uv run manim -qh examples/demo.py SproutInteractions
uv run manim -qh examples/demo.py SproutTalk
uv run manim -qh examples/demo.py SproutClassroom
uv run manim -qh examples/demo.py SproutLivingLeaf
"""

from manim import (
    DOWN,
    LEFT,
    ORIGIN,
    RIGHT,
    UP,
    YELLOW,
    Dot,
    FadeIn,
    FadeOut,
    Scene,
    Text,
    VGroup,
)

from sprout import (
    AVAILABLE_MODES,
    Blink,
    LeafGlow,
    Says,
    Sprout,
    SproutClassroomScene,
    SproutIn,
    SproutOut,
    Thinks,
    spawn_leaf_motes,
)


class SproutShowcase(Scene):
    """All modes in a grid."""

    def construct(self):
        modes = list(AVAILABLE_MODES)
        sprouts = [Sprout(mode=m).scale(0.45) for m in modes]
        labels = [Text(m, font_size=18) for m in modes]
        cells = [
            VGroup(s, lbl).arrange(DOWN, buff=0.1) for s, lbl in zip(sprouts, labels)
        ]
        grid = VGroup(*cells).arrange_in_grid(rows=3, buff=0.4)
        grid.scale_to_fit_height(7)
        self.add(grid)
        self.wait(1)


class SproutInteractions(Scene):
    """Mode swaps (with arms morphing in place), look_at, blink."""

    def construct(self):
        sprout = Sprout(mode="plain").scale(2.0).to_edge(LEFT, buff=1.5)
        self.play(SproutIn(sprout))
        self.wait(0.2)

        for mode in [
            "happy",
            "wave",
            "celebrate",
            "thinking",
            "point_right",
            "surprised",
            "sad",
            "angry",
            "love",
            "sleepy",
            "plain",
        ]:
            label = Text(mode, font_size=28).to_edge(UP)
            self.play(
                sprout.change_mode_anim(mode),
                FadeIn(label, shift=DOWN * 0.2),
                run_time=0.5,
            )
            self.wait(0.25)
            self.play(FadeOut(label), run_time=0.15)

        # Eye tracking
        target = Dot(point=RIGHT * 3 + UP * 1.5, color=YELLOW, radius=0.12)
        self.play(FadeIn(target))
        for pos in [RIGHT * 4 + UP * 1.5, RIGHT * 4 + DOWN * 1.5, RIGHT * 1, ORIGIN]:
            self.play(target.animate.move_to(pos), run_time=0.4)
            sprout.look_at(target)
            self.wait(0.1)
        self.play(FadeOut(target))

        # Blink (as proper Animation class)
        self.play(Blink(sprout))
        self.wait(0.15)
        self.play(Blink(sprout))
        self.wait(0.4)


class SproutTalk(Scene):
    """Speech and thought bubbles."""

    def construct(self):
        sprout = Sprout(mode="plain").scale(1.4).to_corner(DOWN + LEFT, buff=1.0)
        self.play(SproutIn(sprout))

        self.play(Says(sprout, "Hello! I'm Sprout."), run_time=1.2)
        self.wait(0.6)
        self.play(sprout.remove_bubble_anim(), run_time=0.4)

        self.play(Thinks(sprout, "Hmm, interesting..."), run_time=1.2)
        self.wait(0.6)
        self.play(sprout.remove_bubble_anim(), run_time=0.4)

        self.play(
            Says(sprout, "Let me show you something cool!", mode="celebrate"),
            run_time=1.2,
        )
        self.wait(0.6)


class SproutDemo(Scene):
    """EXHAUSTIVE capability tour — every mode, motion, and effect.

    Sections: entrance · all 14 modes · gaze + blink · bubbles ·
    friend duet (eye contact, turn-taking) · corner-creature layout ·
    living leaf (glow, insight flare, motes) · exit. The leaf sway runs
    from entrance to exit, across everything.
    """

    def cap_to(self, text: str, run_time: float = 0.25, at_top: bool = True):
        # Captions sit on top, except while bubbles are on screen — those
        # always grow upward off the shoulder and would cover them.
        edge = UP if at_top else DOWN
        new = Text(text, font_size=26).to_edge(edge, buff=0.35).set_opacity(0.75)
        old = getattr(self, "_cap", None)
        if old is None:
            self.play(FadeIn(new, shift=DOWN * 0.15), run_time=run_time)
        elif getattr(self, "_cap_edge", None) is not at_top:
            # Switching edges: morphing would drag scrambled glyphs across
            # the frame, so hand over with a crossfade instead.
            self.play(FadeOut(old), FadeIn(new), run_time=run_time)
        else:
            self.play(old.animate.become(new), run_time=run_time)
            new = old
        self._cap = new
        self._cap_edge = at_top

    def construct(self):
        # ------- Entrance: grow from the ground (never fade a sprout —
        # translucent mid-fade frames expose the arm layers behind the body).
        sprout = Sprout(mode="plain").scale(1.5).move_to(DOWN * 0.3)
        glow = LeafGlow(sprout)  # level 0 = invisible until the finale
        self.add(glow)  # added first → sits behind the character
        # Leaf sway + ambient motes are intrinsic — on from the entrance.
        self.play(SproutIn(sprout))
        self.wait(0.4)

        # ------- Every expression / pose, morphing in place
        tour = [m for m in AVAILABLE_MODES if m != "plain"] + ["plain"]
        for mode in tour:
            self.cap_to(f"mode · {mode}", run_time=0.2)
            self.play(sprout.change_mode_anim(mode), run_time=0.45)
            self.wait(0.3)

        # ------- Gaze: pupils track a wandering target; blink
        self.cap_to("gaze tracking")
        dot = Dot(point=UP * 2.2 + RIGHT * 3, color=YELLOW, radius=0.13)
        self.play(FadeIn(dot, scale=0.5), run_time=0.3)
        for pos in [
            RIGHT * 5 + UP * 1.0,
            RIGHT * 3 + DOWN * 2.2,
            LEFT * 4 + DOWN * 1.5,
            LEFT * 5 + UP * 2.0,
            UP * 2.8,
        ]:
            self.play(
                dot.animate.move_to(pos),
                sprout.animate.look_at(pos),
                run_time=0.5,
            )
        self.play(FadeOut(dot), run_time=0.25)
        self.cap_to("blink")
        self.play(Blink(sprout))
        self.wait(0.3)
        self.play(Blink(sprout))
        sprout.look_at_viewer()  # turn back to the audience
        self.wait(0.3)

        # ------- Bubbles
        self.cap_to("speech bubble", at_top=False)
        self.play(Says(sprout, "Hi! I'm Sprout."), run_time=0.9)
        self.wait(0.8)
        self.play(sprout.remove_bubble_anim(), run_time=0.35)
        self.cap_to("thought bubble", at_top=False)
        self.play(Thinks(sprout, "Hmm, interesting..."), run_time=0.9)
        self.wait(0.8)
        self.play(sprout.remove_bubble_anim(), run_time=0.35)

        # ------- Friend duet: eye contact and turn-taking (facing is done
        # with gaze — Sprout keeps one silhouette, he never mirrors)
        self.cap_to("eye contact + duet", at_top=False)
        self.play(sprout.animate.shift(LEFT * 2.8), run_time=0.5)
        friend = Sprout(mode="plain").scale(1.5).move_to(RIGHT * 2.8 + DOWN * 0.3)
        self.play(SproutIn(friend))
        sprout.make_eye_contact(friend)
        self.wait(0.5)
        # Take turns. Two facing sprouts both pin their bubble toward the
        # side they face, so simultaneous bubbles collide in the middle —
        # and a conversation reads better as an exchange anyway.
        self.play(Says(sprout, "Ready?"), run_time=0.8)
        self.wait(0.7)
        self.play(sprout.remove_bubble_anim(), run_time=0.3)
        self.play(Says(friend, "Let's go!", mode="happy"), run_time=0.8)
        self.wait(0.7)
        self.play(friend.remove_bubble_anim(back_to="celebrate"), run_time=0.3)
        self.play(Blink(sprout), Blink(friend))
        self.wait(0.3)
        self.play(SproutOut(friend), sprout.animate.shift(RIGHT * 2.8), run_time=0.5)

        # ------- Corner-creature layout (commentator position)
        self.cap_to("corner creature")
        self.play(
            sprout.animate.scale(0.55).to_corner(DOWN + RIGHT, buff=0.45),
            run_time=0.6,
        )
        sprout.look_at(ORIGIN + UP * 0.5)  # watching the "content"
        self.wait(0.6)
        self.play(Blink(sprout))
        self.wait(0.4)
        self.play(sprout.animate.scale(1 / 0.55).move_to(DOWN * 0.3), run_time=0.6)
        sprout.look_at_viewer()

        # ------- Finale: the living leaf (glow, insight flare, motes)
        self.cap_to("thinking glow")
        self.play(
            sprout.change_mode_anim("thinking"),
            glow.level.animate.set_value(0.38),
            run_time=1.0,
        )
        self.wait(1.6)
        self.cap_to("insight!")
        self.play(sprout.change_mode_anim("surprised"), run_time=0.35)
        spawn_leaf_motes(self, sprout, n=10, seed=11)
        self.play(glow.level.animate.set_value(1.0), run_time=0.35)
        self.play(
            sprout.change_mode_anim("celebrate"),
            glow.level.animate.set_value(0.4),
            run_time=1.2,
        )
        self.wait(1.6)

        # ------- Wave goodbye and shrink back into the ground
        self.cap_to("bye!")
        self.play(
            sprout.change_mode_anim("wave"),
            glow.level.animate.set_value(0.0),
            run_time=0.5,
        )
        self.wait(0.6)
        glow.clear_updaters()
        self.play(SproutOut(sprout), FadeOut(self._cap), run_time=0.4)
        self.wait(0.3)


class SproutLivingLeaf(Scene):
    """Living-leaf tiers: idle sway → thinking glow → insight flare + motes.

    Also exercises the sway's rebase logic: the sway stays ON through every
    change_mode_anim and shift below — no pause/resume needed.
    """

    def construct(self):
        sprout = Sprout(mode="plain").scale(1.6).shift(DOWN * 0.4)
        glow = LeafGlow(sprout)
        self.add(glow)

        self.play(SproutIn(sprout))  # sway + ambient motes come with it
        self.wait(2.2)

        # Thinking: glow breathes up while the mode morphs (sway stays on).
        self.play(
            sprout.change_mode_anim("thinking"),
            self.glow_to(glow, 0.38, run_time=1.0),
        )
        self.wait(2.0)

        # Insight! Flare + mote burst.
        self.play(sprout.change_mode_anim("surprised"), run_time=0.35)
        spawn_leaf_motes(self, sprout, n=10, seed=11)
        self.play(self.glow_to(glow, 1.0, run_time=0.35))
        self.play(
            sprout.change_mode_anim("celebrate"),
            self.glow_to(glow, 0.45, run_time=1.2),
        )
        self.wait(1.4)

        # Settle: afterglow; sway + ambient motes survive a shift too.
        self.play(
            sprout.change_mode_anim("happy"),
            sprout.animate.shift(LEFT * 2),
            self.glow_to(glow, 0.18, run_time=0.8),
        )
        self.wait(2.4)

        glow.clear_updaters()
        self.play(SproutOut(sprout), FadeOut(glow))
        self.wait(0.3)

    @staticmethod
    def glow_to(glow, level, run_time=1.0):
        return glow.level.animate(run_time=run_time).set_value(level)


class SproutClassroom(SproutClassroomScene):
    """Teacher-students preset scene."""

    def construct(self):
        self.fade_in_classroom()
        self.wait(0.3)
        self.teacher_says("Today, we'll see how learning emerges.")
        self.wait(0.5)
        self.change_student_modes("thinking", "happy", "surprised")
        self.wait(0.5)
        self.remove_teacher_bubble(back_to="plain")
        self.teacher_thinks("How do I explain this...")
        self.wait(0.5)
        self.remove_teacher_bubble(back_to="speaking")
        self.teacher_says("It starts with a simple rule.", mode="point_left")
        self.change_student_modes("happy", "happy", "happy")
        self.wait(0.8)
