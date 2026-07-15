# skin_highres.py v2 - sculpted-spline Buddy (bear in alien jumpsuit).
# No primitives-as-anatomy: every silhouette is a smooth Catmull-Rom
# curve. Supersampled 3x, one key light (upper-left), contact shadows.
# API unchanged from v1: HighResSkin().frame(emote, blinking,
# wave_angle, pha, phb) -> full-window RGBA PIL image.
import math
from PIL import Image, ImageDraw, ImageChops, ImageFilter

S = 4
W, H = 380, 350
CX, CY = 190, 250          # body center (static; caller applies bob)
HX, HY = 190, 186          # head center

SUIT_TOP = (246, 150, 117)
SUIT_BOT = (228, 106, 74)
SUIT_EDGE = (202, 94, 68)
SUIT_DK = (222, 108, 76)
INNER_EAR = (247, 186, 152)
SKIN_TOP = (250, 216, 178)
SKIN_BOT = (243, 192, 148)
BLUSH = (238, 140, 112)
BELLY_TOP = (252, 246, 236)
BELLY_BOT = (242, 226, 207)
PAW_TOP = (122, 78, 59)
PAW_BOT = (94, 56, 41)
PAD = (245, 227, 205)      # cream palm pad (portrait)
BEAN = (86, 51, 38)
INK = (44, 31, 25)
RED = (224, 69, 90)
WHITE = (255, 255, 255)
MOUTH_IN = (108, 60, 46)
TOOTH = (255, 252, 246)
TEAR = (130, 200, 240)
GREEN = (150, 200, 120)
GLASS_DK = (40, 40, 46)
HORN = (200, 60, 60)
STEAM = (220, 225, 230)


def _x(v):
    return v * S


def _smooth(pts, samples=16):
    """Closed Catmull-Rom spline through control points -> dense outline
    (3x coords). This is what replaces every 'primitive' silhouette."""
    n = len(pts)
    out = []
    for i in range(n):
        p0 = pts[(i - 1) % n]
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        p3 = pts[(i + 2) % n]
        for j in range(samples):
            t = j / samples
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t
                       + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t
                       + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                       + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x * S, y * S))
    return out


def _mask_of(pts, size=None):
    m = Image.new("L", size or (W * S, H * S), 0)
    ImageDraw.Draw(m).polygon(_smooth(pts), fill=255)
    return m


def _grad_fill(layer, pts, ctop, cbot, outline=None, ow=0):
    """Vertical gradient inside a smooth curve (the 3D roundness)."""
    poly = _smooth(pts)
    ys = [p[1] for p in poly]
    xs = [p[0] for p in poly]
    y0, y1 = int(min(ys)), int(max(ys)) + 1
    x0, x1 = int(min(xs)), int(max(xs)) + 1
    h = max(1, y1 - y0)
    grad = Image.new("RGBA", (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        col = tuple(int(ctop[k] + (cbot[k] - ctop[k]) * t)
                    for k in range(3)) + (255,)
        grad.putpixel((0, y), col)
    grad = grad.resize((max(1, x1 - x0), h))
    m = Image.new("L", (max(1, x1 - x0), h), 0)
    ImageDraw.Draw(m).polygon([(p[0] - x0, p[1] - y0) for p in poly],
                              fill=255)
    layer.paste(grad, (x0, y0), m)
    if outline:
        ImageDraw.Draw(layer).line(
            poly + [poly[0]], fill=outline + (255,),
            width=max(1, int(_x(ow))), joint="curve")


def _soft(layer, bbox, color, max_a, steps=24):
    """Radial-falloff soft ellipse: blush, key light, contact shadow."""
    lay = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    x0, y0, x1, y1 = [_x(v) for v in bbox]
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    rx, ry = (x1 - x0) / 2, (y1 - y0) / 2
    for i in range(steps):
        t = (i + 1) / steps
        a = int(max_a * (t ** 1.7))
        f = 1 - (i / steps)
        d.ellipse([cx - rx * f, cy - ry * f, cx + rx * f, cy + ry * f],
                  fill=color + (a,))
    layer.alpha_composite(lay)


def _new():
    return Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))


def _down(img):
    return img.resize((W, H), Image.LANCZOS)


def _shadow_in_mask(layer, mask, bbox, max_a=70, steps=18):
    """Soft occlusion shadow clipped inside a silhouette mask."""
    sh = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    _soft(sh, bbox, (70, 30, 20), max_a, steps)
    sh.putalpha(Image.composite(sh.getchannel("A"),
                                Image.new("L", layer.size, 0), mask))
    layer.alpha_composite(sh)


class HighResSkin:
    def __init__(self):
        base3, self._wave_patch, self._wave_pivot = self._build()
        self.base = _down(base3)
        # clean NO-left-arm base for 'adoring' (both paws raised instead).
        # Rendering the body once without the arm means adoring never has
        # to erase-and-patch, so no seam can appear where the arm used to be.
        self.base_adoring = _down(self._build(draw_left_arm=False)[0])
        # sad_simple: his EARS WILT. They're baked INTO the base (the head is
        # painted over them, which is what sinks them into the hood), so they
        # can't be moved by a layer on top - see _ear_pts. Instead we bake a
        # LADDER of bases with the ear polygons progressively drooped.
        # 10 stages. Stage 0 IS the normal base (droop=0 is identical
        # geometry), so this is only 9 extra _build() calls, ~0.75s of startup.
        # 10 stages across a ~1.5s wilt = the index advances well under 1 step
        # per frame, so it can't alias or visibly step.
        self.sad_bases = [self.base] + [
            _down(self._build(ear_droop=i / 9.0)[0]) for i in range(1, 10)]
        self.right_arm = _down(self._build_right_arm())
        self.belly_paw_arm = _down(self._build_belly_paw_arm())
        self.cold_arms = _down(self._build_cold_arms())
        self.scratch_arm = _down(self._build_scratch_arm())
        self.cheek_paws = _down(self._build_cheek_paws())
        # pleading: the paws PRESS toward you rhythmically (hands that beg
        # MOVE - static hands read as a shrug), and the eyes TWINKLE. Both are
        # keyframed on the same cycle so the press and the sparkle stay in sync.
        self.plead_paws = [_down(self._build_plead_paws(i / 10.0))
                           for i in range(10)]
        self.plead_plates = [_down(self._build_plead_plate(i / 10.0))
                             for i in range(10)]
        # scared: the eyes JITTER. 12 steps, and buddy.py advances the index
        # ~1 per frame (25fps), so this reads as a fast VIBRATION rather than
        # a slow wobble. Keeping the step <= 1/frame is what stops it aliasing
        # into an apparent drift (the wagon-wheel trap that bit dizzy).
        self.scared_plates = [_down(self._build_scared_plate(i, 12))
                              for i in range(12)]
        # anxious: the SWEAT RUNS. 40 keyframes so a bead's slide down his face
        # is smooth rather than steppy. Composited in buddy.py's PIL chain (NOT
        # a frame() branch) so anxious keeps BLINKING - it's in _BLINKABLE with
        # its flag True, and taking that away would be a KeyError.
        self.anx_sweat = [_down(self._build_anx_sweat(i / 40.0))
                          for i in range(40)]
        # crying (and, next, sobbing): ONE small tear sprite, moved / scaled /
        # faded per frame in buddy.py. NOT another 40-keyframe ladder - anxious
        # already pushed skin init from 4.4s to 7.1s and the budget isn't free.
        self.tear = self._build_tear_sprite()
        # exhausted: A REAL DROOP, not a sprite sliding down the screen.
        # His HEAD SINKS into his shoulders (head_dy) and his EARS WILT
        # (ear_droop) - both are BAKED into the base, so the only honest way to
        # move them is to rebuild the base. The body, arms and FEET do not move.
        # draw_left_arm=False because exh_arms draws BOTH arms limp.
        # 8 stages: the index advances well under 1 step/frame, so no aliasing.
        self.exh_bases = [
            _down(self._build(draw_left_arm=False, ear_droop=i / 7.0,
                              head_dy=7.0 * (i / 7.0))[0]) for i in range(8)]
        self.exh_arms = [_down(self._build_exh_arms(i / 7.0))
                         for i in range(8)]
        # mischievous: BOTH PAWS RUBBING TOGETHER - the scheming gesture.
        # 10 keyframes on the rub cycle. Composited over base_adoring (the
        # no-left-arm base), because these draw BOTH arms.
        self.mischief_paws = [_down(self._build_mischief_paws(i / 10.0))
                              for i in range(10)]
        self.bashful_paws = _down(self._build_bashful_paws())
        self.shush_arm = _down(self._build_shush_arm())
        self.giggle_arm = _down(self._build_giggle_arm())
        # forehead-wipe keyframes for relieved: pre-rendered once (building a
        # limb at 4x every frame would be far too slow to animate live)
        self.wipe_arms = [_down(self._build_wipe_arm(i / 8.0))
                          for i in range(9)]
        # yawn face keyframes: the mouth grows and closes across the yawn, so
        # the plate itself has to change - pre-rendered once, same reason.
        self.yawn_plates = [_down(self._build_yawn_plate(i / 10.0))
                            for i in range(11)]
        # yawn arm: rises toward the mouth to cover the yawn (replaces
        # self.right_arm during the yawn)
        self.yawn_arms = [_down(self._build_yawn_arm(i / 8.0))
                          for i in range(9)]
        # nerdy: the arm that shoves his glasses back up his nose
        self.push_arms = [_down(self._build_push_arm(i / 8.0))
                          for i in range(9)]
        # nauseated: two faces (mouth closed / mid-puke) + the green-skin mask
        self.nauseated_plates = [_down(self._build_nauseated_plate(False)),
                                 _down(self._build_nauseated_plate(True))]
        self._nausea_mask = self._build_nausea_mask()
        # hot: pant keyframes - the mouth gapes and the tongue lolls further
        # as he pants, so the plate has to change frame to frame
        self.hot_plates = [_down(self._build_hot_plate(i / 6.0))
                           for i in range(7)]
        # surprised: the startle is an EVENT, so the FACE has to change across
        # it - eyes pop and pupils shrink, brows shoot up, mouth opens, then
        # all of it relaxes back to a residual "oh". 9 keyframes.
        self.surprised_plates = [_down(self._build_surprised_plate(i / 8.0))
                                 for i in range(9)]
        # dizzy: the eye SPIRALS have to spin. 18 keyframes across ONE full
        # turn - 10 was too coarse and the swirl visibly STEPPED rather than
        # spun (which read as a weird drift, not vertigo).
        self.dizzy_plates = [
            _down(self._build_dizzy_plate(i / 18.0 * 2 * math.pi))
            for i in range(18)]
        _hh, _ha = self._build_hug_arms()
        self.hug_heart = _down(_hh)
        self.hug_arms = _down(_ha)
        self.bashful_blush = _down(self._build_bashful_blush())
        # embarrassed: the flush CLIMBS from the cheeks up. Keyframed so it can
        # bloom and pulse - a static blush is bashful's, and it's furniture.
        self.embarrassed_flush = [
            _down(self._build_embarrassed_flush(i / 8.0)) for i in range(9)]
        # innocent: arms taken behind his back (elbows poke out) + a holy
        # halo, both baked so they tilt WITH him on the cute head-tilt.
        self.innocent_hands = _down(self._build_innocent_hands())
        self.innocent_halo = _down(self._build_innocent_halo())
        self._innocent_head_mask = self._build_innocent_head_mask()
        self.alert_ring = _down(self._build_alert_ring())
        self.plates = {k: _down(v) for k, v in self._build_plates().items()}

    # ----- body construction (all splines) -----
    def _body_pts(self):
        return [(CX, CY - 30), (CX + 32, CY - 23), (CX + 50, CY - 4),
                (CX + 54, CY + 20), (CX + 46, CY + 48), (CX + 26, CY + 68),
                (CX, CY + 74), (CX - 26, CY + 68), (CX - 46, CY + 48),
                (CX - 54, CY + 20), (CX - 50, CY - 4), (CX - 32, CY - 23)]

    def _head_pts(self):
        return [(HX, HY - 41), (HX + 26, HY - 34), (HX + 42, HY - 14),
                (HX + 44, HY + 8), (HX + 36, HY + 30), (HX + 18, HY + 40),
                (HX, HY + 42), (HX - 18, HY + 40), (HX - 36, HY + 30),
                (HX - 44, HY + 8), (HX - 42, HY - 14), (HX - 26, HY - 34)]

    def _left_arm_pts(self):
        """The default resting left-arm silhouette. Shared by the base
        build AND by the eraser mask used when a pose needs to replace
        this baked-in arm (e.g. 'adoring' raising both paws)."""
        return [(CX - 38, CY - 2), (CX - 50, CY + 6), (CX - 57, CY + 20),
                (CX - 56, CY + 33), (CX - 49, CY + 41), (CX - 41, CY + 40),
                (CX - 37, CY + 30), (CX - 38, CY + 14)]

    def _ear_pts(self, sx, droop=0.0):
        """Bear-ear polygons (outer, inner) for ONE side.

        `droop` 0..1 wilts the ear OUTWARD and DOWN about the point where it
        sinks into the hood (sad_simple).

        *** WE ROTATE THE POINTS, NOT THE PIXELS. *** The ears are drawn
        FIRST and the head is painted OVER them - that overpaint is what sinks
        them into the hood. So a drooped ear composited as a layer on top
        would FLOAT over the hood instead of sinking into it, and a
        crop-and-rotate would drag head-coloured pixels along with it and
        leave a notch behind. Rotating the control points instead means the
        gradient, the outline and the hood occlusion all come out correct for
        free. Same principle as base_adoring: render it properly once.

        droop=0.0 returns the ORIGINAL geometry exactly, so every other
        emote's ears are byte-for-byte untouched.
        """
        ex = HX + sx * 29
        outer = [(ex, HY - 47), (ex + 10, HY - 43), (ex + 12, HY - 34),
                 (ex + 7, HY - 27), (ex - 7, HY - 27),
                 (ex - 12, HY - 34), (ex - 10, HY - 43)]
        inner = [(ex, HY - 43), (ex + 6, HY - 40), (ex + 7, HY - 34),
                 (ex - 7, HY - 34), (ex - 6, HY - 40)]
        if droop <= 0.0:
            return outer, inner
        # Pivot on the hood line. The sx factor flips the direction so each
        # ear falls AWAY from the centre - without it both would lean left.
        # *** THE ANGLE HAS TO BE BIG. *** The tip sits 18px above the pivot,
        # so rotating by t drops it by 18*(1-cos t). At 30 degrees that is
        # 2.4px - which is NOT a droop, it's a sideways splay, and Chloe
        # (correctly) could not see it at all on the live pet. At 68 degrees
        # the tip drops ~11px and swings out ~17px: the ear genuinely FOLDS
        # OVER, the way a dog pins its ears back. Plus a real downward sink,
        # so they settle into the hood rather than just pivoting in place.
        ang = math.radians(sx * 68.0 * droop)
        px, py = float(ex), HY - 29.0
        ca, sa = math.cos(ang), math.sin(ang)

        def _R(p):
            rx, ry = p[0] - px, p[1] - py
            return (px + rx * ca - ry * sa,
                    py + rx * sa + ry * ca + 3.0 * droop)
        return [_R(p) for p in outer], [_R(p) for p in inner]

    def _build(self, draw_left_arm=True, draw_face_extras=True,
               ear_droop=0.0, head_dy=0.0):
        """`head_dy` SINKS THE HEAD (and its ears, pods and face window) DOWN
        into the shoulders, WITHOUT moving the body, arms or feet. That is what
        an actual HEAD DROOP is. (exhausted only.)

        *** WHY THIS HAD TO GO IN THE BASE BUILDER. *** buddy.py's `bob` just
        TRANSLATES THE WHOLE SPRITE. Chloe caught that immediately: "the thing
        you're calling a droop is just this whole entire body uniformly sinking
        lower on the screen. It's not head and arm droop." She was exactly
        right - a sprite sliding down the screen is not a character sagging.
        The head and ears are BAKED into the base, so the only honest way to
        droop them is to rebuild the base with them lower.

        head_dy=0.0 returns the ORIGINAL geometry exactly, so all 64 other
        emotes are byte-for-byte untouched. (Same contract as ear_droop.)
        """
        img = _new()
        hy = HY + head_dy                      # the head's own baseline
        # -- bear ears: outer + LIGHTER INNER PATCH, sunk into hood --
        # ear_droop > 0 WILTS them (sad_simple, exhausted). See _ear_pts.
        for sx in (-1, 1):
            outer, inner = self._ear_pts(sx, ear_droop)
            if head_dy:
                outer = [(x, y + head_dy) for (x, y) in outer]
                inner = [(x, y + head_dy) for (x, y) in inner]
            _grad_fill(img, outer, SUIT_TOP, SUIT_BOT,
                       outline=SUIT_EDGE, ow=1)
            _grad_fill(img, inner, INNER_EAR, (238, 166, 132))

        # -- side pods: true 4px slivers behind the head edge --
        for sx in (-1, 1):
            px = HX + sx * 44
            pod = [(px, hy - 8), (px + sx * 5, hy - 4), (px + sx * 5, hy + 6),
                   (px, hy + 10), (px - sx * 3, hy + 1)]
            _grad_fill(img, pod, SUIT_DK, SUIT_BOT, outline=SUIT_EDGE, ow=1)
        # -- body --
        body = self._body_pts()
        _grad_fill(img, body, SUIT_TOP, SUIT_BOT, outline=SUIT_EDGE, ow=2)
        body_mask = _mask_of(body)
        _soft(img, (CX - 42, CY - 22, CX - 2, CY + 14), WHITE, 34, 18)
        # -- left resting arm: one sculpted limb curve. SKIPPED for the
        # 'adoring' base variant (draw_left_arm=False), which raises both
        # paws instead. Building a clean no-arm base means adoring never
        # erases-and-patches, so there is no possible seam where the arm
        # used to be. --
        if draw_left_arm:
            arm = self._left_arm_pts()
            self._draw_limb(img, arm, mitten_y=CY + 26)
            self._paw_detail(img, CX - 47, CY + 36, r=6.5, up=False)
        # -- feet (approved design, spline edition) --
        for sx in (-1, 1):
            fx = CX + sx * 22
            foot = [(fx, CY + 54), (fx + 14, CY + 58), (fx + 17, CY + 70),
                    (fx + 12, CY + 81), (fx, CY + 84), (fx - 12, CY + 81),
                    (fx - 17, CY + 70), (fx - 14, CY + 58)]
            _grad_fill(img, foot, PAW_TOP, PAW_BOT, outline=SUIT_EDGE, ow=1)
            _soft(img, (fx - 9, CY + 63, fx + 9, CY + 79),
                  (242, 160, 139), 235, 20)
        # contact shadow: feet against body
        _shadow_in_mask(img, body_mask,
                        (CX - 40, CY + 46, CX + 40, CY + 60), 46)
        # -- belly --
        belly = [(CX, CY + 2), (CX + 22, CY + 8), (CX + 32, CY + 26),
                 (CX + 28, CY + 48), (CX + 12, CY + 60), (CX, CY + 62),
                 (CX - 12, CY + 60), (CX - 28, CY + 48), (CX - 32, CY + 26),
                 (CX - 22, CY + 8)]
        _grad_fill(img, belly, BELLY_TOP, BELLY_BOT)
        # -- head over body + key light + head-on-body contact shadow --
        _shadow_in_mask(img, body_mask,
                        (HX - 30, hy + 30, HX + 30, hy + 52), 60)
        head = self._head_pts()
        if head_dy:
            head = [(x, y + head_dy) for (x, y) in head]
        _grad_fill(img, head, SUIT_TOP, SUIT_BOT, outline=SUIT_EDGE, ow=2)
        _soft(img, (HX - 36, hy - 36, HX + 2, hy - 6), WHITE, 44, 20)
        # -- face window (squircle is the right shape here) --
        x0, y0 = _x(HX - 30), _x(hy - 26)
        x1, y1 = _x(HX + 30), _x(hy + 30)
        grad = Image.new("RGBA", (1, int(y1 - y0)))
        for y in range(int(y1 - y0)):
            t = y / max(1, (y1 - y0) - 1)
            col = tuple(int(SKIN_TOP[k] + (SKIN_BOT[k] - SKIN_TOP[k]) * t)
                        for k in range(3)) + (255,)
            grad.putpixel((0, y), col)
        grad = grad.resize((int(x1 - x0), int(y1 - y0)))
        m = Image.new("L", (int(x1 - x0), int(y1 - y0)), 0)
        ImageDraw.Draw(m).rounded_rectangle(
            [0, 0, int(x1 - x0) - 1, int(y1 - y0) - 1],
            radius=int(_x(21)), fill=255)
        img.paste(grad, (int(x0), int(y0)), m)
        ImageDraw.Draw(img).rounded_rectangle(
            [x0, y0, x1, y1], radius=int(_x(21)),
            outline=SUIT_DK + (255,), width=int(_x(2)))
        if draw_face_extras:
            # soft rosy cheeks
            for sx in (-1, 1):
                bx = HX + sx * 21
                _soft(img, (bx - 9, hy + 6, bx + 9, hy + 18), BLUSH, 84, 22)
            # cute round nose (slightly higher, mouth sits clearly below)
            nose = [(HX, hy + 1), (HX + 5.5, hy + 3), (HX + 6, hy + 7),
                    (HX + 3, hy + 10), (HX - 3, hy + 10), (HX - 6, hy + 7),
                    (HX - 5.5, hy + 3)]
            _grad_fill(img, nose, PAW_TOP, PAW_BOT)
            _soft(img, (HX - 4, hy + 2, HX - 0.5, hy + 5.5), WHITE, 150, 8)
        # pre-sculpted wave arm patch (rotated at shoulder per frame)
        patch, pivot = self._build_wave_patch()
        return img, patch, pivot

    def _draw_limb(self, img, pts, mitten_y, mitten_side="below"):
        """One sculpted limb: suit sleeve with a brown mitten 'dip' that
        follows the limb's own silhouette (no pasted circles).
        mitten_side='below' (default) colors the paw-color band BELOW
        mitten_y (Y increases downward) - correct for hanging arms where
        the paw is the low end. Raised arms need 'above' since their
        paw is the high end (smallest Y)."""
        limb_mask = _mask_of(pts)
        _grad_fill(img, pts, SUIT_TOP, SUIT_BOT, outline=SUIT_EDGE, ow=1.4)
        # mitten: paw color pushed through the limb's own mask below a
        # soft curved boundary
        paw = Image.new("RGBA", img.size, (0, 0, 0, 0))
        _grad_fill(paw, pts, PAW_TOP, PAW_BOT)
        band = Image.new("L", img.size, 0)
        bd = ImageDraw.Draw(band)
        if mitten_side == "below":
            bd.rectangle([0, _x(mitten_y), img.size[0], img.size[1]],
                         fill=255)
        else:
            bd.rectangle([0, 0, img.size[0], _x(mitten_y)], fill=255)
        bd.ellipse([_x(CX - 70), _x(mitten_y - 7), _x(CX + 70),
                    _x(mitten_y + 7)], fill=255)
        paw.putalpha(Image.composite(
            paw.getchannel("A"), Image.new("L", img.size, 0),
            Image.composite(band, Image.new("L", img.size, 0), limb_mask)))
        img.alpha_composite(paw)

    def _paw_detail(self, img, px, py, r=8.0, spread=1.0, up=True,
                    pads=True):
        """Sculpted paw face: raised cream palm pad, four toe beans, and
        soft cute claws. Drawn at paw center (px,py) in 1x coords. `up`
        orients toes above the palm (raised/wave paw) vs below (resting).

        pads=False -> BACK OF THE PAW: skips the palm pad and the toe beans,
        but still draws the CLAWS. Use when the palm is turned away from the
        viewer (e.g. a paw raised to cover the mouth) - you'd see the furred
        back of the hand with the claws showing past the fingertips, not the
        pads.
        """
        s = 1 if up else -1
        if pads:
            # palm pad: rounded cream shape with soft shadow under it
            _soft(img, (px - r * 0.7, py - r * 0.5 - s * r * 0.15,
                        px + r * 0.7, py + r * 0.5 - s * r * 0.15),
                  (70, 40, 30), 60, 12)
            palm = [(px, py - r * 0.55), (px + r * 0.6, py - r * 0.3),
                    (px + r * 0.7, py + r * 0.2),
                    (px + r * 0.4, py + r * 0.55),
                    (px, py + r * 0.62), (px - r * 0.4, py + r * 0.55),
                    (px - r * 0.7, py + r * 0.2),
                    (px - r * 0.6, py - r * 0.3)]
            _grad_fill(img, palm, PAD, (232, 205, 178))
        # four toe beans in a gentle arc above (or below) the palm
        toe_y = py - s * r * 0.95
        for i, fx in enumerate((-0.62, -0.21, 0.21, 0.62)):
            tx = px + fx * r * 1.15
            ty = toe_y - s * (r * 0.14) * (1 - abs(fx) * 0.7)
            tr = r * (0.26 if abs(fx) > 0.5 else 0.30)
            if pads:
                _soft(img, (tx - tr, ty - tr - s * tr * 0.4,
                            tx + tr, ty + tr - s * tr * 0.4),
                      (70, 40, 30), 55, 8)
                _grad_fill(img, [(tx, ty - tr), (tx + tr, ty),
                                 (tx, ty + tr), (tx - tr, ty)],
                           PAD, (232, 205, 178))
            # soft cute claw: tiny crescent above each toe. Drawn even when
            # pads=False - the claws are the whole point of the back-of-paw
            # view.
            cy2 = ty - s * tr * 1.35
            claw = [(tx, cy2 - tr * 0.55), (tx + tr * 0.42, cy2),
                    (tx, cy2 + tr * 0.30), (tx - tr * 0.42, cy2)]
            _grad_fill(img, claw, (250, 240, 226), (222, 205, 186))

    def _paw_shush(self, img, px, py, flen=22.0, fw=3.0):
        """A SINGLE finger extended straight up over the lips, stamped on
        top of the furred fist (the raised limb's rounded end). No spread
        toe-beans and no palm pad - this must read as 'one finger to the
        lips' (shhh), not a whole paw clamped over the mouth. (px, py) is
        the finger's BASE (bottom); it runs up by `flen`, `fw` = half-width
        (kept slim). 1x coords, like _paw_detail."""
        ftop = py - flen
        # soft shadow so the digit lifts off the muzzle
        _soft(img, (px - fw - 1.2, ftop - 1, px + fw + 0.3, py + 2),
              (70, 40, 30), 55, 10)
        # the extended digit: SHORT, tapering to a SHARP claw-like point at
        # the top - the rest of the fingers read as tucked into the fist,
        # so only this one pointed digit shows over the lips.
        _grad_fill(img, [(px, ftop),
                         (px + fw * 0.55, ftop + flen * 0.45),
                         (px + fw, py - 1.5),
                         (px + fw * 0.75, py + 2),
                         (px - fw * 0.75, py + 2),
                         (px - fw, py - 1.5),
                         (px - fw * 0.55, ftop + flen * 0.45)],
                   (250, 240, 226), (223, 202, 183),
                   outline=SUIT_EDGE, ow=1.1)
        # small highlight down its left face
        _soft(img, (px - fw * 0.5, ftop + flen * 0.35, px - fw * 0.05,
                    py - 1), WHITE, 110, 5)
        # subtle furred knuckle bumps at the base = the curled fist
        for kx in (-1.0, 0.0, 1.0):
            bx = px + kx * fw * 1.5
            _soft(img, (bx - fw * 0.8, py - 1, bx + fw * 0.8, py + fw * 1.7),
                  (70, 40, 30), 40, 8)

    def _build_right_arm(self):
        img = _new()
        arm = [(CX + 38, CY - 2), (CX + 50, CY + 6), (CX + 57, CY + 20),
               (CX + 56, CY + 33), (CX + 49, CY + 41), (CX + 41, CY + 40),
               (CX + 37, CY + 30), (CX + 38, CY + 14)]
        self._draw_limb(img, arm, mitten_y=CY + 26)
        self._paw_detail(img, CX + 47, CY + 36, r=6.5, up=False)
        return img

    def _build_belly_paw_arm(self):
        """Right arm bent inward, paw resting flat on the belly - the
        classic 'laughing so hard I'm holding my stomach' pose."""
        img = _new()
        arm = [(CX + 38, CY - 2), (CX + 28, CY + 12), (CX + 18, CY + 24),
               (CX + 10, CY + 32), (CX + 6, CY + 40), (CX + 14, CY + 46),
               (CX + 24, CY + 44), (CX + 30, CY + 34), (CX + 34, CY + 20)]
        self._draw_limb(img, arm, mitten_y=CY + 34)
        self._paw_detail(img, CX + 12, CY + 40, r=7.5, spread=1.0,
                         up=False)
        return img

    def _build_cold_arms(self):
        """BOTH forearms crossed over the chest in a self-hug ('brrr,
        staying warm') - each arm reaches from its shoulder diagonally
        across to grip the opposite side, the two crossing in an X. Used
        for cold, composited over the clean no-left-arm base."""
        img = _new()
        # left-shoulder arm crossing down to the RIGHT ribs (under).
        # Outer edge raised / inner edge lowered vs the first pass so the
        # forearm is a good ~15px thick, matching his side-arm proportions
        # instead of reading skinny.
        larm = [(CX - 43, CY - 3), (CX - 30, CY - 2), (CX - 4, CY + 8),
                (CX + 19, CY + 16), (CX + 31, CY + 21), (CX + 29, CY + 38),
                (CX + 15, CY + 38), (CX - 10, CY + 28), (CX - 33, CY + 16),
                (CX - 43, CY + 12)]
        self._draw_limb(img, larm, mitten_y=CY + 21)
        self._paw_detail(img, CX + 24, CY + 30, r=7.5, up=False)
        # right-shoulder arm crossing down to the LEFT ribs (over)
        rarm = [(CX + 43, CY - 3), (CX + 30, CY - 2), (CX + 4, CY + 8),
                (CX - 19, CY + 16), (CX - 31, CY + 21), (CX - 29, CY + 38),
                (CX - 15, CY + 38), (CX + 10, CY + 28), (CX + 33, CY + 16),
                (CX + 43, CY + 12)]
        self._draw_limb(img, rarm, mitten_y=CY + 21)
        self._paw_detail(img, CX - 24, CY + 30, r=7.5, up=False)
        return img

    def _build_scratch_arm(self):
        """LEFT arm raised just enough for the paw to reach up BEHIND the
        left ear (a sheepish scratch) - NOT stretched all the way to the
        crown. Elbow juts out to screen-left (visible); the forearm + paw
        run up behind the ear and are composited BEHIND the body so the
        head/ear occludes the reach - only the elbow and a peek of the
        paw behind the ear show."""
        img = _new()
        arm = [(CX - 30, CY - 2), (CX - 47, CY - 5), (CX - 58, CY - 28),
               (CX - 57, CY - 54), (CX - 49, CY - 76), (CX - 40, CY - 90),
               (CX - 28, CY - 100), (CX - 19, CY - 91), (CX - 27, CY - 72),
               (CX - 38, CY - 52), (CX - 44, CY - 30), (CX - 34, CY - 8)]
        self._draw_limb(img, arm, mitten_y=CY - 82, mitten_side="above")
        self._paw_detail(img, CX - 33, CY - 96, r=7.5, up=True)
        return img

    def _build_wipe_arm(self, s):
        """RIGHT arm raised to the forehead, mid-WIPE. `s` is 0..1 = the
        paw's travel across the brow (0 = far right of the forehead, 1 = far
        left). Used for the 'phew, wiping my brow' gesture in relieved.

        Pre-rendered as a handful of keyframes at init (see self.wipe_arms) -
        building a limb at 4x every frame would be far too slow.
        NOTE: no sweat drops are drawn anywhere (Chloe's spec) - it's the
        GESTURE alone that says relief."""
        img = _new()
        # Paw travels across the BROW. CY-80 is brow height (just above the
        # eyes, which sit at HY-4 = CY-68).
        px = HX + 17 - s * 34
        py = CY - 74 + math.sin(s * math.pi) * 1.5
        # The arm goes OUT and UP around the SIDE of the head (the trick
        # _build_scratch_arm uses), so the forearm never lies across his
        # face - only the paw and a little wrist reach in over the brow.
        # Two earlier passes ran the limb straight from shoulder to paw and
        # it cut a thin diagonal stick right across his cheek.
        # Kept THICK (the outer and inner edges well separated) - a narrow
        # polygon here reads as a tube/pipe, not a furry arm.
        arm = [
            (CX + 30, CY + 8),      # shoulder, outer
            (CX + 64, CY - 18),     # elbow, swung wide
            (CX + 65, CY - 56),     # forearm rising beside the head
            (px + 12, py - 12),     # outer wrist, arriving at the brow
            (px - 10, py - 6),      # over the paw
            (px + 3, py + 11),      # inner wrist
            (CX + 43, CY - 46),     # forearm, inner edge
            (CX + 40, CY - 14),     # elbow, inner
            (CX + 16, CY + 8),      # shoulder, inner
        ]
        self._draw_limb_cuff(img, arm, (px, py), cuff_r=11.5)
        return img

    def _build_shush_arm(self):
        """RIGHT arm raised so the paw comes up in front of the muzzle and
        a single finger stands vertically over the lips - the 'shhh'
        gesture. Uses Buddy's real furred-limb silhouette (not a stick),
        ending in a compact fist; the lone extended finger is stamped on
        top. Composited LAST in frame() so it sits IN FRONT of the face and
        the finger occludes the mouth. The left arm keeps its resting pose
        (baked into self.base), so only this right arm is raised."""
        img = _new()
        # forearm sweeps up from the right shoulder, inward, to a fist just
        # below the mouth (paw = high end -> mitten_side='above').
        arm = [(CX + 34, CY - 2), (CX + 30, CY - 16), (CX + 22, CY - 28),
               (CX + 12, CY - 36), (CX + 2, CY - 40), (CX - 6, CY - 38),
               (CX - 7, CY - 30), (CX + 1, CY - 26), (CX + 9, CY - 18),
               (CX + 16, CY - 8), (CX + 24, CY - 2)]
        self._draw_limb(img, arm, mitten_y=CY - 30, mitten_side="above")
        # compact fist just below the mouth + the single vertical finger
        # laid over the lips (mouth is at HY+19).
        self._paw_shush(img, HX, HY + 25, flen=10.0, fw=2.8)
        return img

    def _draw_limb_cuff(self, img, pts, cuff, cuff_r=15.0, sleeve_only=False,
                        mitten_only=False):
        """Like _draw_limb, but the brown mitten is a MITTEN BLOB drawn at
        the paw, not a horizontal Y-band and not clipped to the limb.

        Two things go wrong with the stock approach on a HORIZONTAL arm:
        (1) _draw_limb's mitten is 'everything above/below line Y', which on
            a sideways arm smears fur across the whole forearm; and
        (2) clipping the fur to the limb polygon carves it into a crescent
            wherever the arm's tip is thinner than the hand, so the pad ends
            up sitting off to one side of its own mitten.
        So: draw the suit sleeve (clipped, as normal), then paint the mitten
        as a free-standing rounded blob centered on the hand. The blob
        overlaps the sleeve tip, so the hand stays visibly attached to the
        arm, and it fully backs the pad stamped on top of it.

        Split into sleeve/mitten passes because with two crossing arms every
        SLEEVE must be laid down before any MITTEN, or the second sleeve
        paints over the first hand."""
        if not mitten_only:
            _grad_fill(img, pts, SUIT_TOP, SUIT_BOT, outline=SUIT_EDGE,
                       ow=1.4)
        if sleeve_only:
            return
        cx0, cy0 = cuff
        r = cuff_r
        blob = [(cx0, cy0 - r), (cx0 + r * 0.72, cy0 - r * 0.72),
                (cx0 + r, cy0), (cx0 + r * 0.72, cy0 + r * 0.72),
                (cx0, cy0 + r), (cx0 - r * 0.72, cy0 + r * 0.72),
                (cx0 - r, cy0), (cx0 - r * 0.72, cy0 - r * 0.72)]
        _grad_fill(img, blob, PAW_TOP, PAW_BOT, outline=SUIT_EDGE, ow=1.2)

    def _build_hug_arms(self):
        """BOTH arms wrapped AROUND a big heart, squeezing it into his
        chest. Buddy is drawn flat/front-on with no foreshortening, so a
        hug that "wraps toward the viewer" collapses into paws-on-the-belly
        (tried; reads as holding his tummy). A visible heart gives the arms
        something to close around. Crucially the arms must go OVER the
        heart's face - forearms crossing its lower half, each paw reaching
        PAST the opposite edge - so the heart is enveloped and compressed,
        not merely held up between two paws (which reads as presenting it).
        The heart is drawn slightly squashed (wider than tall) to sell the
        squeeze, and its top lobes peek out above the arms.
        Returns (heart_layer, arms_layer) - frame() lays the heart down
        FIRST, then the arms OVER it. Composited over base_adoring."""
        heart = _new()
        arms = _new()
        # heart sits high on the chest; squashed horizontally (sq) so it
        # looks compressed by the squeeze
        hx, hy, hr, sq = CX, CY + 10, 27.0, 1.12
        _soft(heart, (hx - hr * sq, hy - hr * 0.8, hx + hr * sq,
                      hy + hr * 1.1), (70, 30, 40), 70, 14)
        d = ImageDraw.Draw(heart)
        d.ellipse([_x(hx - hr * sq), _x(hy - hr * 0.85),
                   _x(hx + hr * 0.06), _x(hy + hr * 0.25)],
                  fill=RED + (255,))
        d.ellipse([_x(hx - hr * 0.06), _x(hy - hr * 0.85),
                   _x(hx + hr * sq), _x(hy + hr * 0.25)],
                  fill=RED + (255,))
        d.polygon([_x(hx - hr * sq * 0.93), _x(hy + hr * 0.02), _x(hx),
                   _x(hy + hr * 1.05), _x(hx + hr * sq * 0.93),
                   _x(hy + hr * 0.02)], fill=RED + (255,))
        _soft(heart, (hx - hr * 0.66, hy - hr * 0.55, hx - hr * 0.20,
                      hy - hr * 0.12), WHITE, 120, 8)
        # --- arms: each sweeps from its shoulder out, down, then ACROSS
        # the heart's face to the OPPOSITE side. The two are OFFSET in Y
        # (left arm rides higher, right arm lower) so they read as two
        # distinct limbs crossing, not one thick bar/muff across the belly.
        # Single-sided sweeps (never doubling back - that renders as a hook).
        # These arms run HORIZONTALLY, so they use _draw_limb_cuff: the fur
        # is a local circle at the paw, NOT _draw_limb's horizontal Y-band
        # (which would smear brown across the whole forearm).
        # Paw anchors sit ON each arm's own tip (the midpoint of the two
        # far-end spline points), NOT on a heart-relative offset - that
        # mismatch is what left the pads floating slightly off their
        # mittens. The cuff circle is centered on the SAME anchor and kept
        # tight (r=12), so the fur wraps snugly around the pad it belongs
        # to instead of drifting inward along the forearm.
        lpaw = (CX + 21, CY + 9)
        rpaw = (CX - 21, CY + 20)
        # PAD/CUFF ALIGNMENT (measured, not guessed): _paw_detail is not
        # centered on its anchor - with up=True the toes+claws reach above
        # it, so the hand's true visual center is 3px ABOVE the anchor and
        # its covering radius is ~13.5. Center the fur cuff on THAT point
        # (not the anchor) with a little margin, so the mitten fully
        # contains the palm, toe beans and claws instead of sitting low and
        # letting the claws hang off the top edge.
        PR = 6.5
        PAW_DY = -3.0            # hand center is 3px above the anchor
        CUFF_R = 12.5            # mitten blob radius (contains the pad)
        lcuff = (lpaw[0], lpaw[1] + PAW_DY)
        rcuff = (rpaw[0], rpaw[1] + PAW_DY)
        larm = [(CX - 38, CY - 10), (CX - 54, CY + 0), (CX - 56, CY + 14),
                (CX - 44, CY + 24), (CX - 24, CY + 26), (CX - 2, CY + 22),
                (CX + 18, CY + 16), (CX + 24, CY + 4), (CX + 8, CY + 2),
                (CX - 14, CY + 8), (CX - 30, CY + 6)]
        self._draw_limb_cuff(arms, larm, lcuff, cuff_r=CUFF_R,
                             sleeve_only=True)
        rarm = [(CX + 38, CY - 6), (CX + 54, CY + 6), (CX + 56, CY + 22),
                (CX + 44, CY + 34), (CX + 24, CY + 36), (CX + 2, CY + 32),
                (CX - 18, CY + 26), (CX - 24, CY + 14), (CX - 8, CY + 12),
                (CX + 14, CY + 18), (CX + 30, CY + 16)]
        self._draw_limb_cuff(arms, rarm, rcuff, cuff_r=CUFF_R,
                             sleeve_only=True)
        # Both SLEEVES are down; now the mittens, so neither sleeve can
        # paint over the other's hand.
        self._draw_limb_cuff(arms, larm, lcuff, cuff_r=CUFF_R,
                             mitten_only=True)
        self._draw_limb_cuff(arms, rarm, rcuff, cuff_r=CUFF_R,
                             mitten_only=True)
        # Pads last, centered on the SAME point as their mitten blob so the
        # palm, toe beans and claws all sit inside the fur.
        self._paw_detail(arms, lcuff[0], lcuff[1] + 2.5, r=5.8, up=True)
        self._paw_detail(arms, rcuff[0], rcuff[1] + 2.5, r=5.8, up=True)
        return heart, arms

    def _build_giggle_arm(self):
        """RIGHT paw clapped FLAT over the mouth - stifling a laugh (the
        hand-over-mouth of the giggle emoji).

        Deliberately NOT the shush pose, which is the same basic gesture and
        must not be confused with it:
          - shush  = ONE sharp claw-tip held vertically, hand compact, and
                     the body is STILL (quiet, deliberate).
          - giggle = the WHOLE flat paw covering the mouth (pads facing the
                     face, so the furred mitten back shows), and the body
                     HITCHES with suppressed laughter (buddy.py).
        Uses _draw_limb_cuff (mitten as a free-standing blob, not a Y-band),
        the approach proven on hug - a Y-band mitten smears fur down a
        near-horizontal forearm. Composited over base_adoring."""
        img = _new()
        # forearm comes up from the right shoulder to the muzzle; the hand
        # is the high end, and it's WIDE (a flat covering paw, not a fist)
        paw = (HX + 5, HY + 23)
        arm = [(CX + 36, CY - 2), (CX + 40, CY - 16), (CX + 36, CY - 30),
               (CX + 26, CY - 38), (CX + 13, CY - 43), (CX + 2, CY - 42),
               (CX - 4, CY - 35), (CX + 3, CY - 30), (CX + 13, CY - 22),
               (CX + 22, CY - 12), (CX + 30, CY - 2)]
        self._draw_limb_cuff(img, arm, paw, cuff_r=13.0)
        # the flat covering hand: a wide rounded mitten laid over the mouth.
        # Palm faces the FACE, so only the furred back shows - no pads, no
        # claws (that's the shush/hug look). Soft finger grooves keep it
        # from being a featureless blob.
        for gx in (-4.2, 0.0, 4.2):
            _soft(img, (paw[0] + gx - 1.0, paw[1] - 7, paw[0] + gx + 1.0,
                        paw[1] + 5), (70, 40, 30), 40, 8)
        return img

    def _build_cheek_paws(self):
        """BOTH paws raised and clasped together beside the lower
        cheek/chin - the classic 'aww' gesture. Returns just the
        raised-arms layer; adoring composites it over base_adoring
        (the clean no-left-arm base), so no erase/patch is needed."""
        layer = _new()
        # both arms travel a SHORT path toward a shared meeting point
        # near the lower-left cheek (not a long cross-body reach).
        # Tips extend a few px PAST the paw-stamp position (below) so
        # the mitten color always fully overlaps the pad graphic, with
        # margin against spline rounding at the very tip.
        larm = [(CX - 38, CY - 2), (CX - 43, CY - 17), (CX - 43, CY - 30),
                (CX - 36, CY - 40), (CX - 26, CY - 45), (CX - 14, CY - 45),
                (CX - 14, CY - 31), (CX - 24, CY - 17)]
        self._draw_limb(layer, larm, mitten_y=CY - 33, mitten_side="above")
        rarm = [(CX + 38, CY - 2), (CX + 30, CY - 15), (CX + 19, CY - 27),
                (CX + 8, CY - 37), (CX - 3, CY - 44), (CX - 11, CY - 43),
                (CX - 2, CY - 29), (CX + 13, CY - 15)]
        self._draw_limb(layer, rarm, mitten_y=CY - 33, mitten_side="above")
        # clasped paws, comfortably INSIDE the tip (not at the exact
        # apex), so they sit visibly on top of the mitten color
        self._paw_detail(layer, CX - 12, CY - 40, r=7.5, up=True)
        self._paw_detail(layer, CX + 0, CY - 40, r=7.0, up=True)
        return layer

    def _build_plead_paws(self, t):
        """BOTH paws cupped together in front of his chest, palms UP, PRESSING
        toward you in a rhythmic imploring motion. `t` 0..1 cyclic.

        *** THE MOTION IS THE POINT. *** First pass held them apart and STATIC
        and Chloe called it: apart doesn't read as begging, it reads as a
        shrug. Hands that beg MOVE. So the arms swing between -35 and -51
        degrees: the paws come TOGETHER and LIFT toward you, then part and
        drop. ~10px of horizontal travel and ~7px of lift, against an idle
        noise floor of ~2px.

        *** HOW THIS STAYS CLEAR OF ADORING (confirmed). ***
        _build_cheek_paws is "both paws raised and clasped together beside the
        lower cheek" - the 'aww' gesture. This is deliberately close to it now,
        so the separation has to be carried elsewhere:
            adoring  = HIGH (at the cheek), STATIC, backs of the paws (no pads).
            pleading = LOW  (at the chest),  MOVING, OPEN PALMS with pads up.
        The imploring press is the thing adoring does not and cannot do.

        *** DO NOT HAND-ROLL THE ARM POLYGON. *** The first attempt invented an
        8-point outline and rendered as two triangular FINS with the paw pads
        floating loose on his belly. We ROTATE HIS REAL ARM about the shoulder.
        And the swung arm is near-horizontal, so it must use _draw_limb_cuff,
        not _draw_limb: _draw_limb's mitten is "everything below line Y", which
        on a sideways arm smears brown fur down the whole forearm."""
        layer = _new()
        piv = (CX - 38, CY - 2)                     # the shoulder
        th = math.radians(-43.0 + 8.0 * math.sin(t * 2 * math.pi))
        # ARM LENGTH: left at full length (F = 1.0) ON PURPOSE. His arm is 43px
        # and the shoulder sits at CY-2, so a rotated straight arm can only put
        # the paw 43px from the shoulder - at chest height that is either dead
        # centre (arms crossing) or way out past his side. Tried FORESHORTENING
        # it to 0.80 to lift the paws off the belly: it made the arms vanish
        # behind his body and the paws read as two blobs stuck to his tummy.
        # A visible arm matters more than the height. The paws cup low, and the
        # PRESS is what sells the begging.
        F = 1.0

        def rot(pts, pivot, ang):
            px, py = pivot
            c, s = math.cos(ang), math.sin(ang)
            out = []
            for (x, y) in pts:
                dx, dy = (x - px) * F, (y - py) * F
                out.append((px + dx * c - dy * s, py + dx * s + dy * c))
            return out

        larm = rot(self._left_arm_pts(), piv, th)
        rarm = [(2 * CX - x, y) for (x, y) in larm]
        lpaw = rot([(CX - 45, CY + 40.5)], piv, th)[0]
        rpaw = (2 * CX - lpaw[0], lpaw[1])

        # sleeves first, then mittens (the _draw_limb_cuff two-pass rule)
        self._draw_limb_cuff(layer, larm, lpaw, cuff_r=13.0, sleeve_only=True)
        self._draw_limb_cuff(layer, rarm, rpaw, cuff_r=13.0, sleeve_only=True)
        self._draw_limb_cuff(layer, larm, lpaw, cuff_r=13.0, mitten_only=True)
        self._draw_limb_cuff(layer, rarm, rpaw, cuff_r=13.0, mitten_only=True)

        # OPEN PALMS with the CLAWS POINTING DOWN (up=False flips the toes and
        # claws BELOW the palm). This is the difference between a paw held UP
        # and a palm held OUT: claws-down reads as a hand extended toward you,
        # asking for something. Claws-up read as a raised paw.
        # Pads still on, so you see the palm - adoring's clasped paws show the
        # furred BACKS instead.
        self._paw_detail(layer, lpaw[0], lpaw[1], r=8.0, up=False, pads=True)
        self._paw_detail(layer, rpaw[0], rpaw[1], r=8.0, up=False, pads=True)
        return layer

    def _build_bashful_paws(self):
        """Both paws raised to the face - a shy peek-a-boo. Uses Buddy's
        OWN arm silhouette (the same shape as his resting/right arm),
        stretched along its length and swung up so each paw covers its
        own eye. Palms face the face, so only the furred mitten BACK
        shows (no pads). The paw is part of the arm polygon, so it stays
        attached at the wrist - no floating cap, no gap. Composited over
        base_adoring, so there is no resting arm to erase and no seam."""
        layer = _new()

        def stretch_arm(pts, pivot, paw, target, wfac=1.05):
            # Map Buddy's real arm so its paw lands on `target`: stretch
            # along the arm's own axis (keep width ~constant) and rotate
            # up. Preserves the arm's shape - just reaches farther.
            ax, ay = paw[0] - pivot[0], paw[1] - pivot[1]
            aL = math.hypot(ax, ay) or 1.0
            ux, uy = ax / aL, ay / aL            # arm axis unit
            pxu, pyu = -uy, ux                    # arm perp unit
            tx, ty = target[0] - pivot[0], target[1] - pivot[1]
            tL = math.hypot(tx, ty) or 1.0
            vx, vy = tx / tL, ty / tL             # target axis unit
            qx, qy = -vy, vx                       # target perp unit
            s = tL / aL
            out = []
            for (x, y) in pts:
                rx, ry = x - pivot[0], y - pivot[1]
                al = (rx * ux + ry * uy) * s       # along, stretched
                pe = (rx * pxu + ry * pyu) * wfac  # perp, width kept
                out.append((pivot[0] + al * vx + pe * qx,
                            pivot[1] + al * vy + pe * qy))
            return out

        # Buddy's canonical arm silhouette (his right arm), paw integral.
        rarm = [(CX + 38, CY - 2), (CX + 50, CY + 6), (CX + 57, CY + 20),
                (CX + 56, CY + 33), (CX + 49, CY + 41), (CX + 41, CY + 40),
                (CX + 37, CY + 30), (CX + 38, CY + 14)]
        larm = [(2 * CX - x, y) for (x, y) in rarm]   # mirror for the left
        r_pivot, r_paw = (CX + 38, CY - 2), (CX + 47, CY + 36)
        l_pivot, l_paw = (CX - 38, CY - 2), (CX - 47, CY + 36)
        # Draw both raised arms. The screen-RIGHT hand is nudged OUTWARD
        # (dx) so that eye bead peeks out from behind it - like he's trying
        # to sneak a look; the LEFT hand stays fully over its eye. Each paw
        # is a compact rounded BACK (no pads -> palms face in) overlapping
        # its wrist, so it's attached with no gap.
        for sx, base, dx in ((-1, larm, 0), (1, rarm, 13)):
            pivot = (CX + sx * 38, CY - 2)
            paw_pt = (CX + sx * 47, CY + 36)
            wrist = (HX + sx * (19 + dx), HY - 8)
            arm = stretch_arm(base, pivot, paw_pt, wrist)
            self._draw_limb(layer, arm, mitten_y=HY - 60,
                            mitten_side="above")
            ex = HX + sx * (16 + dx)
            paw = [(ex, HY - 30), (ex + 10, HY - 26), (ex + 12, HY - 17),
                   (ex + 9, HY - 9), (ex, HY - 7), (ex - 9, HY - 9),
                   (ex - 12, HY - 17), (ex - 10, HY - 26)]
            _grad_fill(layer, paw, PAW_TOP, PAW_BOT, outline=SUIT_EDGE, ow=1)
            # cream claws poking up over the top edge of the mitten back
            for cfx in (-6.5, 0.0, 6.5):
                cxp = ex + cfx
                by = HY - 27 if abs(cfx) > 3 else HY - 31
                _grad_fill(layer, [(cxp, by - 5), (cxp + 2.4, by),
                                   (cxp, by - 1), (cxp - 2.4, by)],
                           (250, 240, 226), (224, 206, 187))
        return layer

    def _build_mischief_paws(self, t):
        """*** BOTH PAWS RUBBING TOGETHER. *** The scheming gesture. `t` 0..1.

        THE MOTION IS THE WHOLE EMOTE. Two paws held together and STILL is just
        a clasp; two paws SLIDING PAST EACH OTHER is plotting. So the arms
        COUNTER-rotate: as one paw slides up, the other slides down, ~10px of
        relative travel against a ~2px idle noise floor.

        *** HOW THIS STAYS CLEAR OF THE TWO CONFIRMED PAW EMOTES: ***
          adoring  = paws HIGH at the cheek, STATIC, backs out ('aww').
          pleading = paws LOW at the chest, PRESSING TOWARD YOU, OPEN PALMS
                     with the pads up (imploring).
          mischievous = paws at the chest but RUBBING ACROSS EACH OTHER, backs
                     out, no pads. Nobody else rubs.

        *** DO NOT HAND-ROLL THE ARM POLYGON. *** (Pleading shipped triangular
        FINS with the paws floating loose that way.) ROTATE HIS REAL ARM about
        the shoulder. The swung arm is diagonal, so it needs _draw_limb_cuff -
        _draw_limb's mitten is 'everything below line Y' and would smear brown
        fur down the whole forearm."""
        layer = _new()
        piv_l = (CX - 38, CY - 2)
        piv_r = (CX + 38, CY - 2)
        base = math.radians(-55.0)                     # paws meet at the chest
        rub = math.radians(7.0) * math.sin(t * 2 * math.pi)

        def rot(pts, pivot, ang):
            px, py = pivot
            c, s = math.cos(ang), math.sin(ang)
            return [(px + (x - px) * c - (y - py) * s,
                     py + (x - px) * s + (y - py) * c) for (x, y) in pts]

        lpts = self._left_arm_pts()
        rpts = [(2 * CX - x, y) for (x, y) in lpts]
        # COUNTER-ROTATE. The right arm is mirrored, so its rotation is negated;
        # feeding it (base - rub) while the left gets (base + rub) makes the two
        # paws slide across each other instead of moving together.
        larm = rot(lpts, piv_l, base + rub)
        rarm = rot(rpts, piv_r, -(base - rub))
        lpaw = rot([(CX - 45, CY + 40.5)], piv_l, base + rub)[0]
        rpaw = rot([(CX + 45, CY + 40.5)], piv_r, -(base - rub))[0]
        self._draw_limb_cuff(layer, larm, lpaw)
        self._draw_limb_cuff(layer, rarm, rpaw)
        # *** NO _paw_detail HERE. ON PURPOSE. ***
        # First pass stamped the claw/pad detail on both paws, and side by side
        # on his cream belly the two of them formed a MASK-shaped blob - it read
        # as a skull stuck to his tummy, not as two hands. _draw_limb_cuff
        # already paints a clean mitten blob at each hand, and two plain mittens
        # sliding across each other is exactly the gesture. Less is the fix.
        return layer

    def _eye_scheming(self, img):
        """A SLY SIDEWAYS GLANCE under heavy lids. He is not looking AT you -
        he is looking OFF, at whatever he is about to do.

        *** THE COLLISION IS SHUSH, NOT ANY ANGER EMOTE. *** The baseline gave
        mischievous _eye_half_lid(0.3) + _mouth_smirk - and SHUSH (CONFIRMED)
        is _eye_half_lid(0.4) + _mouth_smirk. THE SAME TWO HELPERS. They were
        going to ship as twins with a droop value between them.
        So: shush keeps the stock half-lid, looking straight ahead. This one
        gets its own eye with the PUPILS SHOVED HARD TO ONE SIDE - the glance
        is the tell, and it is what a half-lid alone can never say.

        Also NOT _eye_half_lid because that paints a skin-coloured lid OVER a
        finished eye (the double-eyebrow bug). The lid here is the eye's own
        outline."""
        d = ImageDraw.Draw(img)
        ey = HY - 1
        r = 8.2
        for ex in (HX - 16, HX + 16):
            # the eye: flattened from above by a heavy, lazy lid
            _grad_fill(img, [(ex - r, ey - 1.6), (ex - r * 0.5, ey - 4.2),
                             (ex, ey - 4.8), (ex + r * 0.5, ey - 4.2),
                             (ex + r, ey - 1.6),
                             (ex + r * 0.9, ey + 2.6), (ex, ey + 4.4),
                             (ex - r * 0.9, ey + 2.6)],
                       (250, 246, 240), (226, 220, 212), outline=INK, ow=1.5)
            # THE PUPIL, shoved hard to one side. THE GLANCE.
            px = ex + 3.4
            d.ellipse([_x(px - 3.0), _x(ey - 3.2), _x(px + 3.0), _x(ey + 3.0)],
                      fill=(30, 24, 22, 255))
            _soft(img, (px - 1.8, ey - 2.6, px + 0.2, ey - 0.6), WHITE, 190, 2)
            # the heavy lid, drawn as INK across the top
            d.line([_x(ex - r - 0.6), _x(ey - 3.4), _x(ex), _x(ey - 5.2),
                    _x(ex + r + 0.6), _x(ey - 3.4)],
                   fill=INK + (255,), width=int(_x(2.4)), joint="curve")

    def _mouth_sly(self, img):
        """*** A DEVIOUS GRIN. *** Wide, curling UP at BOTH ends, higher on one
        side, with a fang hooked over it.

        *** FIRST PASS WAS TOO SMALL. Chloe: "there should be, like, a devious
        smile instead." *** What I had was a narrow SMIRK - a nearly flat line
        with one end lifted. A smirk is a small private amusement. A devious
        GRIN is somebody enjoying what they are about to do to you, and that is
        a much bigger, wider shape that turns up at BOTH corners.
        MEASURED: 24px wide (was 20), and the corners now sit 6.5px / 3.2px
        ABOVE the middle instead of one corner 4px up and the other 1.6px DOWN.
        Both ends now go UP. That is the difference between a smirk and a grin.

        >>> Y IS DOWN. Corners at SMALLER y than the middle = curling UP.
            The RIGHT corner (-6.5) is higher than the LEFT (-3.2): the
            asymmetry is what keeps it DEVIOUS rather than just cheerful."""
        d = ImageDraw.Draw(img)
        my = HY + 21
        d.line([_x(HX - 12.0), _x(my - 3.2),     # left corner: UP
                _x(HX - 6.5), _x(my + 1.4),
                _x(HX), _x(my + 2.4),            # the middle, low: the CURL
                _x(HX + 6.5), _x(my + 0.6),
                _x(HX + 12.0), _x(my - 6.5)],    # right corner: UP HIGHER
               fill=INK + (255,), width=int(_x(2.7)), joint="curve")
        # THE FANG, hooked down over the raised side of the grin
        _grad_fill(img, [(HX + 4.6, my + 0.4), (HX + 8.4, my - 1.6),
                         (HX + 6.6, my + 4.6)],
                   (255, 252, 246), (224, 216, 204), outline=INK, ow=0.9)

    def _eye_furious(self, img):
        """*** THE ONLY ANGER EMOTE WHERE YOU CAN SEE THE WHITES OF HIS EYES. ***
        Blown wide, sclera showing all round, pupils shrunk to hard little dots.
        He has LOST IT.

        The block's eyes, in order of how far gone he is:
            huffing    = narrow slits (contempt - fully in control).
            mad        = wide + a white CATCHLIGHT (a person, holding it in).
            angry      = wide + NO catchlight (the light has gone out).
            frustrated = screwed SHUT (effort, aimed at nothing).
            furious    = WHITES SHOWING, pupils shrunk to pinpricks. GONE.
        Shrinking the pupil inside a blown-open eye is the classic "snapped"
        cue - it is the one thing none of the other four do."""
        d = ImageDraw.Draw(img)
        ey = HY - 1
        r = 9.2
        for ex in (HX - 16, HX + 16):
            # THE SCLERA - blown wide open
            _grad_fill(img, [(ex - r, ey - 3.0), (ex - r * 0.55, ey - 7.2),
                             (ex, ey - 8.0), (ex + r * 0.55, ey - 7.2),
                             (ex + r, ey - 3.0),
                             (ex + r * 0.9, ey + 3.4), (ex, ey + 5.6),
                             (ex - r * 0.9, ey + 3.4)],
                       (255, 253, 249), (232, 226, 220), outline=INK, ow=1.6)
            # THE PUPIL - shrunk to a hard little dot. The tell.
            d.ellipse([_x(ex - 2.7), _x(ey - 3.0), _x(ex + 2.7), _x(ey + 2.6)],
                      fill=(26, 20, 18, 255))

    def _brow_furious(self, img):
        """The STEEPEST slash in the block - a near-vertical plunge at the nose.

        Inner-end depth across the whole block (how far the brow is driven DOWN
        toward the nose - the single number that ranks anger):
            huffing    ey -  8.5   composed
            mad        ey -  7.5   a scowl
            frustrated ey -  6.0   crushed
            angry      ey -  4.5   seething
            furious    ey -  3.5   GONE, and the steepest fall of any of them
        >>> OUTER = ex + sx*N (away from nose). INNER = ex - sx*N.
            ANGRY = OUTER HIGH (small y), INNER LOW (large y). CHECK THE SIGNS -
            this is the bug that shipped SAD BROWS on three anger emotes."""
        d = ImageDraw.Draw(img)
        ey = HY - 4
        for sx, ex in ((-1, HX - 16), (1, HX + 16)):
            d.line([_x(ex + sx * 12.5), _x(ey - 19.0),   # OUTER: HIGHEST
                    _x(ex + sx * 3.5), _x(ey - 13.5),
                    _x(ex - sx * 10.5), _x(ey - 3.5)],   # INNER: DRIVEN LOWEST
                   fill=INK + (255,), width=int(_x(3.6)), joint="curve")

    def _mouth_furious(self, img):
        """A WIDE OPEN ROAR. The curse symbols get drawn OVER this in buddy.py,
        so what it needs to be is a big, dark, shouting hole - the band of
        symbols reads against it.

        Deliberately NOT _mouth_scribble (the baseline). A scribble is a STATIC
        squiggle - furniture. The real 🤬 has SYMBOLS THAT CHURN, and those have
        to be animated, so they live in the PIL chain instead."""
        my = HY + 21
        w = 12.5
        _grad_fill(img, [(HX - w, my - 1.0), (HX - w * 0.5, my - 5.0),
                         (HX, my - 5.6), (HX + w * 0.5, my - 5.0),
                         (HX + w, my - 1.0),
                         (HX + w * 0.72, my + 5.4), (HX, my + 7.2),
                         (HX - w * 0.72, my + 5.4)],
                   (70, 24, 28), (30, 10, 14), outline=INK, ow=1.6)

    def _eye_angry(self, img):
        """BURNING. Wide open, and *** NO CATCHLIGHT AT ALL. ***

        That absence is the split from mad, and it is deliberate. Mad has a
        white highlight - there is still a person in there, holding it together.
        Angry's eyes have NO light in them. Dead, hot, fixed on you. It reads as
        a step further gone even though the shapes are close cousins.

        The upper lid also cuts DOWN across the eye harder than mad's, so more
        of the eye is buried under the brow - the look of someone glaring
        THROUGH you."""
        d = ImageDraw.Draw(img)
        ey = HY - 1
        r = 8.6
        for ex in (HX - 16, HX + 16):
            _grad_fill(img, [(ex - r, ey - 3.4), (ex - r * 0.55, ey - 6.6),
                             (ex, ey - 7.2), (ex + r * 0.55, ey - 6.6),
                             (ex + r, ey - 3.4),
                             (ex + r * 0.94, ey + 1.8), (ex, ey + 4.6),
                             (ex - r * 0.94, ey + 1.8)],
                       (48, 32, 26), INK)
            # the UPPER lid cutting down hard across the eye
            d.line([_x(ex - r - 0.8), _x(ey - 5.8), _x(ex), _x(ey - 7.4),
                    _x(ex + r + 0.8), _x(ey - 5.8)],
                   fill=INK + (255,), width=int(_x(2.4)), joint="curve")
            # the LOWER lid, pushed up hard
            d.line([_x(ex - r * 0.95), _x(ey + 3.4), _x(ex), _x(ey + 4.8),
                    _x(ex + r * 0.95), _x(ey + 3.4)],
                   fill=INK + (255,), width=int(_x(2.0)), joint="curve")
            # *** NO _soft() HIGHLIGHT HERE. ON PURPOSE. ***

    def _brow_seething(self, img):
        """LOWER, THICKER and HARDER than mad's - driven right down at the nose.

        The block's brows, in order of how far the inner end is driven DOWN:
            huffing    inner y = ey -  8.5   (composed, held)
            mad        inner y = ey -  7.5   (a scowl)
            frustrated inner y = ey -  6.0   (crushed, + pinch lines)
            angry      inner y = ey -  4.5   (LOWEST - the hardest furrow)
        >>> OUTER = ex + sx*N (away from nose). INNER = ex - sx*N.
            ANGRY = OUTER HIGH (small y), INNER LOW (large y).
            *** THIS IS THE BUG THAT SHIPPED SAD BROWS ON THREE ANGER EMOTES.
                Chloe caught it: "I see sad eyebrows." CHECK THE SIGNS. ***"""
        d = ImageDraw.Draw(img)
        ey = HY - 4
        for sx, ex in ((-1, HX - 16), (1, HX + 16)):
            d.line([_x(ex + sx * 12.0), _x(ey - 16.5),   # OUTER: HIGH
                    _x(ex + sx * 3.0), _x(ey - 12.5),
                    _x(ex - sx * 10.0), _x(ey - 4.5)],   # INNER: DRIVEN DOWN
                   fill=INK + (255,), width=int(_x(3.4)), joint="curve")

    def _mouth_snarl(self, img):
        """A SNARL - the mouth pulled OPEN and back off the teeth, at an angle.

        The split from _mouth_frustrated: frustrated's teeth are CLENCHED SHUT
        in a flat bar (straining, holding it in - the mouth of someone stuck).
        This one is OPEN. He is not holding anything in; he is baring his teeth
        AT you. Corners hauled back and DOWN, a dark cavity behind the teeth.
        >>> Y IS DOWN. Corners (+4.0) at LARGER y than the middle (-3.2)."""
        d = ImageDraw.Draw(img)
        my = HY + 20
        w, h = 11.0, 5.0
        # the open cavity, corners dragged DOWN
        _grad_fill(img, [(HX - w, my + 4.0),                 # corner: DOWN
                         (HX - w * 0.5, my - 2.6),
                         (HX, my - 3.2),                     # top lip: UP
                         (HX + w * 0.5, my - 2.6),
                         (HX + w, my + 4.0),                 # corner: DOWN
                         (HX + w * 0.6, my + h * 1.15),
                         (HX, my + h * 1.45),
                         (HX - w * 0.6, my + h * 1.15)],
                   (78, 30, 34), (40, 15, 19), outline=INK, ow=1.5)
        # THE BARED TEETH - an upper row only, hanging into the cavity
        d.polygon([_x(HX - w * 0.74), _x(my - 1.2), _x(HX), _x(my - 2.4),
                   _x(HX + w * 0.74), _x(my - 1.2),
                   _x(HX + w * 0.68), _x(my + 1.8), _x(HX), _x(my + 2.4),
                   _x(HX - w * 0.68), _x(my + 1.8)],
                  fill=(252, 248, 240, 255))
        for tx in (-5.4, -2.7, 0.0, 2.7, 5.4):
            d.line([_x(HX + tx), _x(my - 1.9), _x(HX + tx), _x(my + 2.2)],
                   fill=INK + (140,), width=int(_x(0.9)))

    def _eye_mad(self, img):
        """A HARD, DIRECT STARE. Eyes fully open and locked on you, with the
        LOWER lid pushed UP - the squint of someone holding a glare.

        The anger block splits its eyes three ways:
            frustrated = screwed SHUT (effort, aimed at nothing).
            huffing    = NARROW, flattened from ABOVE (contempt, withering).
            mad        = WIDE OPEN and staring, tensed from BELOW.
        That last one is the difference: a raised lower lid reads as CONTAINED
        anger - he is holding your gaze on purpose.

        *** FIRST PASS FAILED THE NUMBERS. *** I built mad at 8.8px tall and
        huffing at 8.6px - functionally IDENTICAL - so the "wide vs narrow"
        split existed only in the comments, not in the pixels. Mad is now
        12.4px tall (ratio 0.74, a ROUND stare) against huffing's 8.6px
        (ratio 0.54, clearly SQUASHED). The difference has to be MEASURABLE or
        it isn't there."""
        d = ImageDraw.Draw(img)
        ey = HY - 1
        r = 8.4
        for ex in (HX - 16, HX + 16):
            _grad_fill(img, [(ex - r, ey - 4.6), (ex - r * 0.55, ey - 7.6),
                             (ex, ey - 8.2), (ex + r * 0.55, ey - 7.6),
                             (ex + r, ey - 4.6),
                             (ex + r * 0.92, ey + 1.4), (ex, ey + 4.2),
                             (ex - r * 0.92, ey + 1.4)],
                       (58, 42, 34), INK)
            # THE LOWER LID, pushed UP into the eye - the tell.
            d.line([_x(ex - r * 0.95), _x(ey + 3.2), _x(ex), _x(ey + 4.4),
                    _x(ex + r * 0.95), _x(ey + 3.2)],
                   fill=INK + (255,), width=int(_x(2.0)), joint="curve")
            _soft(img, (ex - 3.4, ey - 5.6, ex - 0.8, ey - 2.8), WHITE, 155, 3)

    def _brow_mad(self, img):
        """A hard, THICK V - the classic scowl. Inner ends driven DOWN.

        Distinct on POSITION and SHAPE from the rest of the block:
            frustrated = LOWEST, jammed onto the lids, PLUS pinch lines.
            huffing    = a clean straight slant, riding HIGH (composed).
            mad        = a heavy V at MID height, with a real BEND in it.
        The bend is what makes it a scowl rather than a slant."""
        d = ImageDraw.Draw(img)
        ey = HY - 4
        for sx, ex in ((-1, HX - 16), (1, HX + 16)):
            # *** OUTER = ex + sx*N.  INNER = ex - sx*N. *** (left eye: sx=-1,
            # so ex + sx*11.5 == ex - 11.5 == away from the nose == OUTER.)
            # ANGRY = OUTER HIGH, INNER LOW (driven DOWN toward the nose).
            d.line([_x(ex + sx * 11.5), _x(ey - 15.0),   # OUTER: HIGH
                    _x(ex + sx * 2.0), _x(ey - 12.5),
                    _x(ex - sx * 9.5), _x(ey - 7.5)],    # INNER: DOWN at nose
                   fill=INK + (255,), width=int(_x(3.2)), joint="curve")

    def _mouth_mad(self, img):
        """A DEEP, HARD SCOWL. An unmistakable downturned arc.

        The measurable split from _mouth_huffing: huffing's mouth is a nearly
        STRAIGHT clamp (corners drop ~2px below the middle - he is holding it
        shut). Mad's corners drop ~5px - a proper frown you can read at a
        glance. Same family, different amount, and the amount IS the emote.
        >>> Y IS DOWN. Corners at LARGER y (+4.4) than the middle (-0.8)."""
        d = ImageDraw.Draw(img)
        my = HY + 21
        d.line([_x(HX - 8.8), _x(my + 4.4),      # corner: DOWN
                _x(HX - 4.4), _x(my + 0.4),
                _x(HX), _x(my - 0.8),            # middle: UP
                _x(HX + 4.4), _x(my + 0.4),
                _x(HX + 8.8), _x(my + 4.4)],     # corner: DOWN
               fill=INK + (255,), width=int(_x(3.0)), joint="curve")

    def _eye_huffing(self, img):
        """A HARD, NARROWED GLARE - eyes OPEN, unimpressed, looking straight at
        you. He is not raging; he is OFFENDED, and he wants you to know.

        This is the one anger emote whose eyes are open AND narrow:
            frustrated = screwed SHUT (effort).
            mad/angry/furious = will keep round, wide, staring rage.
            huffing = a flat, half-lidded, WITHERING look. Contempt, not fury.
        The eye is squashed from ABOVE (the lid pressing down), which is what
        makes a glare read as a glare rather than a small eye."""
        d = ImageDraw.Draw(img)
        ey = HY - 1
        r = 8.0
        for ex in (HX - 16, HX + 16):
            _grad_fill(img, [(ex - r, ey - 1.8), (ex - r * 0.5, ey - 3.4),
                             (ex, ey - 3.8), (ex + r * 0.5, ey - 3.4),
                             (ex + r, ey - 1.8),
                             (ex + r * 0.9, ey + 3.2), (ex, ey + 4.8),
                             (ex - r * 0.9, ey + 3.2)],
                       (58, 42, 34), INK)
            # the LID pressing down from above - a hard flat bar, not a brow
            d.line([_x(ex - r - 0.6), _x(ey - 3.0), _x(ex), _x(ey - 4.4),
                    _x(ex + r + 0.6), _x(ey - 3.0)],
                   fill=INK + (255,), width=int(_x(2.2)), joint="curve")
            _soft(img, (ex - 3.0, ey - 1.2, ex - 0.6, ey + 1.0), WHITE, 130, 3)

    def _brow_huffing(self, img):
        """A hard straight SLANT down toward the nose - set, controlled, held.

        Distinct on POSITION from frustrated's (which is jammed right onto the
        lids and carries PINCH LINES between the brows). This one rides HIGHER
        and is a clean straight line: he is composed. That composure - anger
        held IN - is exactly what huffing is."""
        d = ImageDraw.Draw(img)
        ey = HY - 4
        for sx, ex in ((-1, HX - 16), (1, HX + 16)):
            # OUTER = ex + sx*N (away from nose). INNER = ex - sx*N.
            # ANGRY = OUTER HIGH, INNER LOW.
            d.line([_x(ex + sx * 11), _x(ey - 16.0),   # OUTER: HIGH
                    _x(ex - sx * 9), _x(ey - 8.5)],    # INNER: DOWN at nose
                   fill=INK + (255,), width=int(_x(3.0)))

    def _mouth_huffing(self, img):
        """PRESSED FLAT AND TIGHT. A hard set line, corners just turned down.
        Closed - the steam is coming out of his NOSE, not his mouth, and a mouth
        clamped shut is what forces it there.

        Not _mouth_flat (the baseline, shared with mad): this is THICKER and
        wider, with a compressed upper lip line above it - a mouth being held
        shut by force.
        >>> Y IS DOWN. Corners (+1.5) sit at LARGER y than the middle (-0.5)."""
        d = ImageDraw.Draw(img)
        my = HY + 21
        d.line([_x(HX - 8.5), _x(my + 1.5),      # corner: DOWN
                _x(HX - 3.0), _x(my - 0.4),
                _x(HX + 3.0), _x(my - 0.5),      # middle
                _x(HX + 8.5), _x(my + 1.5)],     # corner: DOWN
               fill=INK + (255,), width=int(_x(2.9)), joint="curve")

    def _eye_frustrated(self, img):
        """Eyes SCREWED SHUT in exasperation - "aaargh".

        *** THE COLLISION TO AVOID IS SOBBING, NOT ANGER. *** _eye_sobbing is
        also clenched shut, so these must not be the same picture:
            sobbing    = clenched in ANGUISH. Squeeze-CREASES fan out from the
                         outer corners. Grief - the face crumpling.
            frustrated = clenched in EFFORT. NO creases. Instead the lids are
                         drawn as hard flat WEDGES angled DOWN toward the nose,
                         with the brow crushed onto them. Tension, not sorrow.
        >>> Y IS DOWN. The INNER end of each lid sits at LARGER y than the outer
            end - i.e. angled down toward the nose. That downward-inward slant
            is what makes it read as anger rather than sadness (a sad clench
            slants the other way)."""
        d = ImageDraw.Draw(img)
        ey = HY - 2
        for sx, ex in ((-1, HX - 16), (1, HX + 16)):
            # outer end HIGH, inner end LOW -> an angry, effortful squeeze
            d.line([_x(ex - sx * 8.5), _x(ey - 3.4),   # OUTER: up
                    _x(ex - sx * 2.0), _x(ey + 0.6),
                    _x(ex + sx * 8.0), _x(ey + 2.6)],  # INNER: down (toward nose)
                   fill=INK + (255,), width=int(_x(2.8)), joint="curve")

    def _brow_frustrated(self, img):
        """CRUSHED DOWN onto the eyes and driven together - the hardest furrow
        in the set, plus the vertical PINCH LINES between them. Frustration is
        pressure with nowhere to go, and that shows in the middle of the face.

        Distinct on POSITION from the anger block's other brows: this one is
        LOWEST (jammed right onto the lids) and has the pinch lines. mad /
        angry / furious will keep their brows higher and more slanted."""
        d = ImageDraw.Draw(img)
        ey = HY - 4
        for sx, ex in ((-1, HX - 16), (1, HX + 16)):
            # OUTER = ex + sx*N (away from nose). INNER = ex - sx*N.
            # ANGRY = OUTER HIGH, INNER DRIVEN DOWN toward the nose.
            d.line([_x(ex + sx * 11), _x(ey - 13.5),   # OUTER: HIGH
                    _x(ex + sx * 2), _x(ey - 10.5),
                    _x(ex - sx * 9), _x(ey - 6.0)],    # INNER: DOWN at nose
                   fill=INK + (255,), width=int(_x(2.9)), joint="curve")
        # THE PINCH LINES between the brows - the pressure made visible
        for ox in (-2.6, 2.6):
            d.line([_x(HX + ox), _x(HY - 16.5), _x(HX + ox * 1.35), _x(HY - 9.5)],
                   fill=INK + (215,), width=int(_x(1.5)))

    def _mouth_frustrated(self, img):
        """TEETH BARED AND CLENCHED. A wide flat grimace with the teeth showing
        through it - the mouth of someone straining against something.

        Wider and flatter than _mouth_grit (which frustrated shared with angry
        in the baseline). No open cavity: this is a mouth PRESSED SHUT hard,
        not one that has fallen open like exhausted's."""
        d = ImageDraw.Draw(img)
        my = HY + 20
        w, h = 10.0, 3.6
        # the dark mouth line, corners pulled back and slightly down
        _grad_fill(img, [(HX - w, my - 0.6), (HX, my - h * 0.75),
                         (HX + w, my - 0.6), (HX + w * 0.86, my + h * 0.9),
                         (HX, my + h * 1.15), (HX - w * 0.86, my + h * 0.9)],
                   (74, 32, 34), (44, 18, 22), outline=INK, ow=1.4)
        # THE TEETH: one hard bar, with the clench lines cut through it
        d.rectangle([_x(HX - w * 0.78), _x(my - h * 0.42),
                     _x(HX + w * 0.78), _x(my + h * 0.30)],
                    fill=(252, 248, 240, 255))
        for tx in (-5.2, -2.6, 0.0, 2.6, 5.2):
            d.line([_x(HX + tx), _x(my - h * 0.42),
                    _x(HX + tx), _x(my + h * 0.30)],
                   fill=INK + (150,), width=int(_x(0.9)))

    def _build_exh_arms(self, k):
        """BOTH arms gone LIMP - swinging loose and away from his sides instead
        of held neatly against them. `k` 0..1.

        Composited over a no-left-arm base, so there is no baked arm underneath
        to double up with.
        *** ROTATE THE REAL ARM, never hand-roll a limb polygon *** (that ships
        triangular fins with the paws floating loose - learned on pleading).
        These stay near-VERTICAL, so _draw_limb is correct here; _draw_limb_cuff
        is only for the near-horizontal case."""
        layer = _new()
        piv = (CX - 38, CY - 2)                    # the shoulder
        th = math.radians(13.0 * k)                # swing OUT, hanging loose

        def rot(pts, ang):
            px, py = piv
            c, s = math.cos(ang), math.sin(ang)
            return [(px + (x - px) * c - (y - py) * s,
                     py + (x - px) * s + (y - py) * c) for (x, y) in pts]

        larm = rot(self._left_arm_pts(), th)
        rarm = [(2 * CX - x, y) for (x, y) in larm]
        lpaw = rot([(CX - 47, CY + 36)], th)[0]
        rpaw = (2 * CX - lpaw[0], lpaw[1])
        my = CY + 26 - 3.0 * k                     # mitten line follows the paw
        self._draw_limb(layer, larm, mitten_y=my)
        self._draw_limb(layer, rarm, mitten_y=my)
        self._paw_detail(layer, lpaw[0], lpaw[1], r=6.5, up=False)
        self._paw_detail(layer, rpaw[0], rpaw[1], r=6.5, up=False)
        return layer

    def _eye_exhausted(self, img):
        """HALF-SHUT AND HEAVY. A wide, LOW-LIDDED eye with a thick dark lid
        line dragged across the top of it, and dark BAGS underneath.

        *** FIRST PASS FAILED: Chloe said "the eyes don't look exhausted." ***
        They were small dark slits - which just read as small eyes, not tired
        ones. The fix isn't subtlety, it's CONTRAST:
          - the eye is WIDE (r 8.6) but squashed FLAT, so it reads as an eye
            that is OPEN and being HELD half-shut, not a tiny eye.
          - a THICK LID LINE across the top: the weight you can see him fighting.
          - real UNDER-EYE BAGS. Nothing else in the 65 has them.

        *** NOT _eye_half_lid *** - that paints a SKIN-coloured lid over a
        finished eye, which reads as a second eyebrow once brows sit above it.
        Here the lid is INK, sitting ON the eye, and it is unmistakably a lid.
        """
        d = ImageDraw.Draw(img)
        ey = HY - 1
        r = 8.6
        for ex in (HX - 16, HX + 16):
            # the visible part of the eye: wide, squashed flat from above
            _grad_fill(img, [(ex - r, ey - 1.2), (ex - r * 0.5, ey - 2.6),
                             (ex, ey - 3.0), (ex + r * 0.5, ey - 2.6),
                             (ex + r, ey - 1.2),
                             (ex + r * 0.88, ey + 3.0), (ex, ey + 4.6),
                             (ex - r * 0.88, ey + 3.0)],
                       (60, 44, 36), INK)
            # THE HEAVY LID, dragged across the top of the eye
            d.line([_x(ex - r - 0.8), _x(ey - 2.4), _x(ex), _x(ey - 4.0),
                    _x(ex + r + 0.8), _x(ey - 2.4)],
                   fill=INK + (255,), width=int(_x(2.6)), joint="curve")
            # a dull, low highlight - no life in it
            _soft(img, (ex - 3.4, ey - 1.0, ex - 1.0, ey + 1.2), WHITE, 120, 3)
            # *** THE BAGS. *** The tell nothing else in the 65 has.
            _soft(img, (ex - r * 0.95, ey + 4.2, ex + r * 0.95, ey + 8.2),
                  (172, 124, 122), 105, 5)
            d.arc([_x(ex - r * 0.9), _x(ey + 1.6),
                   _x(ex + r * 0.9), _x(ey + 9.4)],
                  start=20, end=160, fill=(150, 106, 104, 165),
                  width=int(_x(1.3)))

    def _brow_exhausted(self, img):
        """Sagging OUTWARD and down - collapsed, not tensed. Too tired to hold
        any shape at all. Distinct on POSITION from disappointed's flat
        lifeless line (which sits low and level) - these fall away at the
        outer ends, like the face is sliding off."""
        d = ImageDraw.Draw(img)
        ey = HY - 4
        for sx, ex in ((-1, HX - 16), (1, HX + 16)):
            d.line([_x(ex + sx * 11), _x(ey - 6.5),      # outer end: LOW
                    _x(ex + sx * 2), _x(ey - 11.5),
                    _x(ex - sx * 8), _x(ey - 12.5)],     # inner end: higher
                   fill=INK + (255,), width=int(_x(2.4)), joint="curve")

    def _mouth_exhausted(self, img):
        """MOUTH-BREATHING. A WIDE, LOW, slack open mouth - hanging open
        because closing it is more effort than he has left.

        *** FIRST PASS FAILED: Chloe said "the mouth doesn't look exhausted." ***
        It was a small tidy oval, which just reads as a small mouth. A tired
        mouth is WIDE and LOW and LOOSE, with the corners dragged down and no
        tension anywhere in it. Made it nearly twice as wide and sat it lower.

        Not terrified's rigid gape, not sobbing's fat crescent wail.
        >>> Y IS DOWN. The corners (+2.4) sit at LARGER y than the top lip
            (-1.6), so it hangs DOWNWARD. Not a smile."""
        my = HY + 22
        w = 8.8
        _grad_fill(img, [(HX - w, my + 2.4),                 # corner: DOWN
                         (HX - w * 0.55, my - 1.2),
                         (HX, my - 1.6),                     # top lip
                         (HX + w * 0.55, my - 1.2),
                         (HX + w, my + 2.4),                 # corner: DOWN
                         (HX + w * 0.68, my + 5.6),
                         (HX, my + 6.8),                     # slack bottom lip
                         (HX - w * 0.68, my + 5.6)],
                   (98, 46, 50), (50, 21, 25), outline=INK, ow=1.5)

    def _eye_disappointed(self, img):
        """Eyes cast DOWN - at the floor, not away from you. He can't look at
        the thing that let him down.

        *** NOT _eye_half_lid. *** That helper draws _glossy_eyes and then
        paints a SKIN-COLOURED LID on top of the finished eye - which produces
        the double-eyebrow bug the moment brows sit above it. The heavy lid
        here is part of the EYE SHAPE: the top is flattened and the whole eye
        is pushed DOWN in its socket.

        Distinct from embarrassed, which AVERTS (down AND hard to one side, to
        avoid YOU). This one looks straight DOWN. He's not hiding from you -
        he's just stopped looking up."""
        ey = HY + 1                     # sitting LOW in the socket
        r = 7.2
        for ex in (HX - 16, HX + 16):
            _grad_fill(img, [(ex - r * 0.88, ey - r * 0.20),
                             (ex, ey - r * 0.38), (ex + r * 0.88, ey - r * 0.20),
                             (ex + r, ey + r * 0.28),
                             (ex + r * 0.74, ey + r * 0.86),
                             (ex, ey + r), (ex - r * 0.74, ey + r * 0.86),
                             (ex - r, ey + r * 0.28)],
                       (58, 42, 34), INK)
            # highlight low and dull - no sparkle. He isn't hoping any more.
            _soft(img, (ex - 3.2, ey + 0.4, ex - 0.6, ey + 2.8), WHITE, 150, 4)

    def _brow_disappointed(self, img):
        """Flat, LOW and lifeless - laid down close over the eyes with barely
        any tilt. Not tension (scared's steep diagonal), not grief (crying's
        dragged-down outer ends), not worry (anxious's pinched knot).
        The absence of shape IS the read: he has stopped reacting."""
        d = ImageDraw.Draw(img)
        ey = HY - 4
        for sx, ex in ((-1, HX - 16), (1, HX + 16)):
            d.line([_x(ex + sx * 10), _x(ey - 8.5), _x(ex - sx * 8), _x(ey - 10.5)],
                   fill=INK + (255,), width=int(_x(2.4)))

    def _mouth_disappointed(self, img):
        """A short, flat, downturned line. Small and closed - resignation, not
        grief. crying gets the trembling frown, sobbing gets the open crescent.
        This one has gone quiet.

        >>> Y IS DOWN. Corners at LARGER y (+1.8) than the middle (-0.6) =
            a frown. (crying shipped an actual SMILE by getting this backwards.)
        """
        d = ImageDraw.Draw(img)
        my = HY + 21
        d.line([_x(HX - 6.5), _x(my + 1.8),      # corner: DOWN
                _x(HX - 2.2), _x(my - 0.4),
                _x(HX + 2.2), _x(my - 0.6),      # middle: UP (slightly)
                _x(HX + 6.5), _x(my + 1.8)],     # corner: DOWN
               fill=INK + (255,), width=int(_x(2.3)), joint="curve")

    def _eye_sobbing(self, img):
        """Eyes SQUEEZED SHUT in anguish - not merely closed, CLENCHED.

        The tell is TENSION: squeeze-creases radiating from the outer corners,
        which nothing else has. That's what keeps it off laughing_crying
        (CONFIRMED), whose _eye_closed_cup is a HAPPY closed squint - relaxed,
        no creases, and it's grinning underneath.
        >>> Y IS DOWN. These arcs bow DOWNWARD in the middle (larger y at the
            centre) = screwed shut in pain, not a contented crescent."""
        d = ImageDraw.Draw(img)
        ey = HY - 3
        for sx, ex in ((-1, HX - 16), (1, HX + 16)):
            # the clenched lid: bows DOWN at the centre
            d.line([_x(ex - 8.0), _x(ey - 2.6), _x(ex - 3.0), _x(ey + 1.8),
                    _x(ex + 3.0), _x(ey + 1.8), _x(ex + 8.0), _x(ey - 2.6)],
                   fill=INK + (255,), width=int(_x(2.6)), joint="curve")
            # SQUEEZE CREASES at the outer corner - the tension marks
            ox = ex + sx * 9.5
            for dy2, ln in ((-3.4, 4.2), (0.2, 4.8), (3.6, 4.0)):
                d.line([_x(ox), _x(ey + dy2),
                        _x(ox + sx * ln), _x(ey + dy2 * 1.35)],
                       fill=INK + (200,), width=int(_x(1.4)))

    def _brow_sobbing(self, img):
        """Grief at maximum: inner ends CRUSHED up and together, steeply.
        laughing_crying has NO brows at all, so the brow alone separates them.
        Steeper and higher than _brow_crying, whose outer ends drag down."""
        d = ImageDraw.Draw(img)
        ey = HY - 4
        for sx, ex in ((-1, HX - 16), (1, HX + 16)):
            d.line([_x(ex + sx * 11), _x(ey - 8), _x(ex + sx * 2), _x(ey - 19),
                    _x(ex - sx * 7), _x(ey - 22)],
                   fill=INK + (255,), width=int(_x(2.7)), joint="curve")

    def _mouth_sobbing(self, img):
        """THE OPEN FROWN. A fat CRESCENT: tips turned DOWN, belly humped UP.
        Chloe's words: "an upside down Cheeto."

        *** TWO THINGS I GOT WRONG HERE, BOTH BY OVERBUILDING. ***
        1. A TONGUE. She cut it: a visible tongue is a SILLY-FACE cue (blegh /
           raspberry) and it fought every other thing on the face.
        2. Then a rounded cavity that PULSED with the heave. She cut that too:
           "that's just an open mouth that looks like it's puckering. Don't try
           to do anything fancy as far as animating the mouth."
           She was right, and the numbers say so: the old shape had ~7px of arch
           across a 21px-wide mouth. That is not a frown, that is a BLOB.
        >>> RULE: when a shape isn't reading, fix THE SHAPE. Do not animate it
            and hope the motion sells it. A static shape that reads beats a
            moving shape that doesn't.
        >>> RULE: a tongue reads as PLAYFUL. Keep it out of any distress emote.

        >>> Y IS DOWN. The TIPS sit at LARGER y (+4.0) than the peak of the
            hump (-5.2). Tips low, middle high = a FROWN. (crying shipped an
            actual SMILE by getting exactly this backwards.)
        """
        w = 11.5
        my = HY + 21
        # top edge, left tip -> hump -> right tip
        cav = [(HX - w, my + 4.0),                    # left tip: DOWN
               (HX - w * 0.62, my - 2.4),
               (HX, my - 5.2),                        # the hump: UP
               (HX + w * 0.62, my - 2.4),
               (HX + w, my + 4.0),                    # right tip: DOWN
               # bottom edge, back along the belly of the crescent
               (HX + w * 0.55, my + 2.6),
               (HX, my + 4.8),                        # belly
               (HX - w * 0.55, my + 2.6)]
        _grad_fill(img, cav, (104, 48, 52), (48, 20, 24), outline=INK, ow=1.6)

    def _build_tear_sprite(self):
        """ONE tear, drawn ONCE, reused forever.

        *** PERF: THIS IS THE CHEAP ARCHITECTURE, AND IT MATTERS NOW. ***
        anxious's running sweat cost 40 FULL-CANVAS keyframes and took skin init
        from 4.4s to 7.1s. A tear is a RIGID OBJECT THAT MOVES - it does not
        need a whole-canvas keyframe per position. So: render one small sprite
        here, then move / scale / fade it per frame in buddy.py. Costs ~nothing
        at startup, and SOBBING can reuse the very same sprite.

        CRISP, not soft - a droplet is a hard-edged object (the sparkle rule
        from pleading), never a soft tint (the blush rule from embarrassed).
        """
        w, h = 13, 19
        big = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
        d = ImageDraw.Draw(big)
        cx = w * S / 2.0
        # teardrop: pointed at the TOP, heavy round belly at the BOTTOM
        d.polygon([(cx, 1 * S),
                   (cx + 3.4 * S, 8.0 * S), (cx + 4.6 * S, 12.5 * S),
                   (cx + 2.8 * S, 17.0 * S), (cx, 18.2 * S),
                   (cx - 2.8 * S, 17.0 * S), (cx - 4.6 * S, 12.5 * S),
                   (cx - 3.4 * S, 8.0 * S)],
                  fill=(150, 206, 242, 245), outline=(84, 146, 196, 255))
        # a hard little catchlight so it reads as WET and GLASSY
        d.ellipse([(cx - 2.6 * S, 10.4 * S), (cx - 0.6 * S, 14.0 * S)],
                  fill=(255, 255, 255, 225))
        return big.resize((w, h), Image.LANCZOS)

    def _eye_crying(self, img):
        """Grief eyes: heavy upper lid, wet, with water standing ON the rim.
        The lid is part of the EYE SHAPE - never a skin-coloured lid painted
        over a finished eye (that's the double-eyebrow bug _eye_half_lid causes
        when brows are present).

        *** NOT PLEADING'S EYES. *** Pleading is r 11.8, enormous, sparkling,
        with a star glint and water that WELLS AND NEVER SPILLS - that welling
        is the whole performance. Crying's eyes are NORMAL SIZED and TIRED, and
        the water DOES spill. Pleading is asking you for something; crying has
        stopped asking."""
        ey = HY - 2
        r = 7.6
        for ex in (HX - 16, HX + 16):
            # heavy lid: the top of the eye is FLATTENED, not covered over
            _grad_fill(img, [(ex - r * 0.86, ey - r * 0.34),
                             (ex, ey - r * 0.50), (ex + r * 0.86, ey - r * 0.34),
                             (ex + r, ey + r * 0.10),
                             (ex + r * 0.80, ey + r * 0.78),
                             (ex, ey + r), (ex - r * 0.80, ey + r * 0.78),
                             (ex - r, ey + r * 0.10)],
                       (58, 42, 34), INK)
            _soft(img, (ex - 3.8, ey - 2.4, ex - 1.0, ey + 0.4), WHITE, 200, 4)
            # WATER STANDING ON THE LOWER RIM - it has already broken.
            _soft(img, (ex - r * 0.8, ey + r * 0.55,
                        ex + r * 0.8, ey + r * 1.22),
                  (198, 232, 248), 190, 4)

    def _brow_crying(self, img):
        """Grief brow: inner ends hoisted, outer ends DRAGGED DOWN hard - the
        face collapsing rather than tensing. Distinct on POSITION from
        anxious's tight KNOT and pleading's high round arch (all three brow
        SHAPES were spoken for long ago)."""
        d = ImageDraw.Draw(img)
        ey = HY - 4
        for sx, ex in ((-1, HX - 16), (1, HX + 16)):
            d.line([_x(ex + sx * 11), _x(ey - 6), _x(ex + sx * 2), _x(ey - 15),
                    _x(ex - sx * 8), _x(ey - 16)],
                   fill=INK + (255,), width=int(_x(2.5)), joint="curve")

    def _mouth_crying(self, img):
        """The mouth of someone LOSING a fight not to cry: corners hauled DOWN
        hard, pressed shut, with the chin-quiver wobble in the line.
        Shut, because sobbing is the one that gets the open wail.

        *** SIGN ERROR - CHLOE CAUGHT THIS: "he shouldn't be smiling". ***
        The first version put the CORNERS at (my - 2.6) and the MIDDLE at
        (my + 0.4). Y GROWS DOWNWARD, so that is corners UP and middle DOWN -
        A SMILE. The docstring said "corners hauled down" and the code did the
        exact opposite.
        >>> RULE: Y IS DOWN. A FROWN has its CORNERS at LARGER y than its
            middle. Same class of bug as the _brow_sad sign flip. When drawing
            any mouth or brow, state the intended shape and then CHECK THE
            SIGNS against it before rendering.
        """
        d = ImageDraw.Draw(img)
        my = HY + 20
        d.line([_x(HX - 8.5), _x(my + 2.8),      # corner: DOWN
                _x(HX - 4.8), _x(my - 1.4),
                _x(HX - 1.6), _x(my - 2.1),      # arch: UP
                _x(HX + 1.6), _x(my - 1.5),
                _x(HX + 4.8), _x(my - 0.9),      # slight lopsided quiver
                _x(HX + 8.5), _x(my + 2.8)],     # corner: DOWN
               fill=INK + (255,), width=int(_x(2.4)), joint="curve")

    def _build_anx_sweat(self, t):
        """THE SWEAT THAT RUNS. `t` 0..1, cyclic. THIS IS THE WHOLE EMOTE.

        *** WORRIED (CONFIRMED) ALREADY HAS A SWEAT DROP. *** It is not called
        "sweat" anywhere - it's an unnamed blue teardrop _grad_fill parked at
        (HX+34, HY-30), which is why a keyword grep for "sweat" came back empty
        and nearly let me ship a duplicate. And worried is otherwise glossy eyes
        + inner-raised brows + a frown, which is ANXIOUS'S BASELINE FACE. So
        "worried but with sweat" IS worried. The face cannot carry this emote.

        WHAT SEPARATES THEM IS THE LIFECYCLE:
            worried = ONE bead, drawn identically every single frame. It is
                      never born and it never dies. FURNITURE.
            anxious = beads FORM on his brow, SWELL, RUN DOWN his face, and
                      VANISH. Then new ones form. Born -> ages -> dies.
        Worried is a state he is HOLDING. Anxious is a state that is ESCALATING
        and he cannot stop it.

        *** THE DROPS NEVER POOL AND NEVER REACH THE GROUND (Chloe's call). ***
        Each one fades to nothing as it passes his jaw. That is also the SAFE
        choice technically: the drop never leaves his silhouette, so it never
        meets buddy.py's binary alpha threshold in open space.
        """
        layer = _new()
        d = ImageDraw.Draw(layer)
        # three beads, staggered around the cycle, so one is always running
        for x0, y0, drift, off in ((HX - 23, HY - 19, -3.0, 0.00),
                                   (HX + 24, HY - 23, 3.5, 0.34),
                                   (HX + 10, HY - 28, 1.5, 0.67)):
            u = (t + off) % 1.0
            if u < 0.30:                       # BORN: swells in place
                s = u / 0.30
                x, y = x0, y0
                sc = 0.35 + 0.65 * s
                a = s
            else:                              # AGES: runs down, accelerating
                s = (u - 0.30) / 0.70
                x = x0 + drift * s
                y = y0 + 64.0 * (s * s * 0.72 + s * 0.28)
                sc = 1.0
                a = 1.0
            # DIES: gone by the time it clears his jaw. No pooling, ever.
            if y > HY + 18:
                a *= max(0.0, 1.0 - (y - (HY + 18)) / 26.0)
            if a <= 0.02:
                continue
            w, h = 3.3 * sc, 6.2 * sc
            al = int(255 * a)
            # a teardrop: pointed at the top, round at the bottom. CRISP -
            # a droplet is a hard-edged object (the sparkle rule from
            # pleading), NOT a soft tint (the blush rule from embarrassed).
            d.polygon([(_x(x), _x(y - h)),
                       (_x(x + w * 0.72), _x(y - h * 0.42)),
                       (_x(x + w), _x(y + h * 0.12)),
                       (_x(x), _x(y + h * 0.55)),
                       (_x(x - w), _x(y + h * 0.12)),
                       (_x(x - w * 0.72), _x(y - h * 0.42))],
                      fill=(150, 206, 242, al), outline=(88, 150, 198, al))
            d.ellipse([_x(x - w * 0.5), _x(y - h * 0.32),
                       _x(x - w * 0.05), _x(y + h * 0.14)],
                      fill=(255, 255, 255, int(200 * a)))
        return layer

    def _eye_anxious(self, img):
        """Glossy eyes, but WIDER and STARING - strained, fixed, not blinking
        it away. Worried uses plain _glossy_eyes; these are bigger and tenser so
        the two faces don't land on the same picture."""
        ey = HY - 3
        r = 8.6
        for ex in (HX - 16, HX + 16):
            _grad_fill(img, [(ex, ey - r * 0.92), (ex + r * 0.84, ey - r * 0.6),
                             (ex + r, ey), (ex + r * 0.84, ey + r * 0.62),
                             (ex, ey + r), (ex - r * 0.84, ey + r * 0.62),
                             (ex - r, ey), (ex - r * 0.84, ey - r * 0.6)],
                       (60, 44, 35), INK)
            _soft(img, (ex - 4.2, ey - 5.0, ex - 1.0, ey - 1.8), WHITE, 215, 4)

    def _brow_anxious(self, img):
        """Inner ends raised AND squeezed together into a KNOT above the nose.
        All three brow SHAPES are long gone (inner-up = worried/sad/pleading,
        outer-up = angry, high-and-level = surprised), so this one separates on
        POSITION: the inner ends nearly TOUCH. A knot of worry."""
        d = ImageDraw.Draw(img)
        ey = HY - 4
        for sx, ex in ((-1, HX - 16), (1, HX + 16)):
            d.line([_x(ex + sx * 11), _x(ey - 9), _x(ex - sx * 11), _x(ey - 18)],
                   fill=INK + (255,), width=int(_x(2.6)))

    def _build_embarrassed_flush(self, t):
        """The MORTIFIED flush at spread-level `t` (0 = just starting, 1 =
        fully climbed). A layer that sits over the face, clipped to the face
        window so it can never bleed onto the suit.

        *** MUST DIFFER IN KIND FROM TWO CONFIRMED EMOTES, NOT JUST DEGREE: ***
          bashful  = (234, 92, 116) - a PINK, EVEN, FLAT wash over the whole
                     face window. Static. Pleasant. He's ENJOYING it.
          hot      = _heat_sheen, a physical heat flush, with steam + panting.
          embarrassed = a DEEPER SCARLET that STARTS AT THE CHEEKS AND CLIMBS.
                     It is not a state he's in, it's a thing HAPPENING to him.
        The climb is the whole point: it has a LIFECYCLE (blooms -> spreads ->
        holds), where bashful's is furniture that's simply always there.
        """
        layer = _new()
        hot = (214, 46, 52)          # scarlet, NOT bashful's (234, 92, 116)

        # *** BUILD IT SOLID, THEN BLUR THE WHOLE THING, THEN CLIP TO HIM. ***
        # This took three passes to get right, so here is the full trap:
        #   1st: soft shapes, weak alpha -> the climb was invisible. Too faint.
        #   2nd: a hard rounded_rectangle at alpha 142 to make it strong -> a
        #        crisp red BOX with a visible border sitting on his face.
        #        Chloe: "the box ... does not match where his face is at."
        #   3rd: all-soft shapes -> no box, but weak and washed out again.
        # The fix is to have BOTH: draw SOLID shapes (which gives real
        # density), then Gaussian-blur the ENTIRE layer (which destroys every
        # border it has), and only then clip it to his face. The single edge
        # that survives is the edge of his own skin, which is exactly where a
        # blush is supposed to stop.
        # >>> RULE: a tint is not a shape. If you can see where it stops -
        #     other than at his face - it is furniture. Density comes from the
        #     fill; softness comes from blurring the whole layer afterwards.
        top = HY + 8 - 32.0 * t
        shape = _new()
        d = ImageDraw.Draw(shape)
        d.rounded_rectangle(
            [_x(HX - 26), _x(top), _x(HX + 26), _x(HY + 28)],
            radius=int(_x(18)), fill=hot + (int(60 + 105 * t),))
        # the cheeks are the SOURCE - hottest, and hot from the very start
        for sx in (-1, 1):
            bx = HX + sx * 20
            d.ellipse([_x(bx - 12), _x(HY + 3), _x(bx + 12), _x(HY + 21)],
                      fill=hot + (int(150 + 85 * t),))

        # *** BLUR THE ALPHA ONLY - NEVER THE WHOLE RGBA LAYER. ***
        # Blurring the RGBA image blurs the COLOUR channels too, and outside
        # the shapes the colour is transparent BLACK - so the blur drags black
        # into the scarlet and his face comes out GREY AND MUDDY, like a
        # bruise. Blur the alpha, keep the RGB a flat scarlet everywhere.
        a = shape.getchannel("A").filter(ImageFilter.GaussianBlur(_x(7)))

        # the ONLY edge it is allowed: his face. Clips the cheeks too, so the
        # blush can never bleed onto the orange suit hood.
        m = Image.new("L", a.size, 0)
        ImageDraw.Draw(m).rounded_rectangle(
            [_x(HX - 30), _x(HY - 26), _x(HX + 30), _x(HY + 30)],
            radius=int(_x(21)), fill=255)
        a = Image.composite(a, Image.new("L", a.size, 0), m)

        layer = Image.new("RGBA", shape.size, hot + (0,))
        layer.putalpha(a)
        return layer

    def _build_bashful_blush(self):
        """Strong bashful flush - clearly going pink in the face: an EVEN
        flat wash across the whole exposed face window (clipped to the
        squircle so it can't touch the suit) plus punchy rosy cheek
        circles. Sits over the face plate, under the raised paws."""
        layer = _new()
        rosy = (234, 92, 116)
        flush = _new()
        ImageDraw.Draw(flush).rounded_rectangle(
            [_x(HX - 28), _x(HY - 24), _x(HX + 28), _x(HY + 28)],
            radius=int(_x(20)), fill=rosy + (74,))
        _soft(flush, (HX - 24, HY - 12, HX + 24, HY + 26), rosy, 66, 22)
        m = Image.new("L", layer.size, 0)
        ImageDraw.Draw(m).rounded_rectangle(
            [_x(HX - 30), _x(HY - 26), _x(HX + 30), _x(HY + 30)],
            radius=int(_x(21)), fill=255)
        flush.putalpha(Image.composite(
            flush.getchannel("A"), Image.new("L", layer.size, 0), m))
        layer.alpha_composite(flush)
        for sx in (-1, 1):
            bx = HX + sx * 21
            _soft(layer, (bx - 12, HY + 3, bx + 12, HY + 22), rosy, 205, 15)
            _soft(layer, (bx - 8, HY + 6, bx + 8, HY + 18), rosy, 220, 10)
        return layer

    def _build_innocent_hands(self):
        """His arms taken behind his back (hands clasped out of view):
        each arm bends at the shoulder with the ELBOW poking out at the
        side, then the forearm tucks back behind him. Drawn as a layer
        that sits BEHIND the body, so the body hides the forearms and you
        read 'shoulders -> elbows out -> hands behind the back' - not
        armless, not cut-off stubs."""
        img = _new()
        for sx in (-1, 1):
            arm = [(CX + sx * 33, CY - 5), (CX + sx * 52, CY - 3),
                   (CX + sx * 64, CY + 10), (CX + sx * 67, CY + 24),
                   (CX + sx * 62, CY + 37), (CX + sx * 49, CY + 45),
                   (CX + sx * 33, CY + 46), (CX + sx * 30, CY + 18)]
            _grad_fill(img, arm, SUIT_TOP, SUIT_BOT,
                       outline=SUIT_EDGE, ow=1.3)
        return img

    def _build_innocent_halo(self):
        """A holy gold halo baked above his head so it tilts WITH him on
        the head-tilt (a soft glow ring + a brighter gold ring)."""
        img = _new()
        d = ImageDraw.Draw(img)
        cxh, cyh, rw, rh = HX, HY - 62, 24, 7
        d.ellipse([_x(cxh - rw - 3), _x(cyh - rh - 3),
                   _x(cxh + rw + 3), _x(cyh + rh + 3)],
                  outline=(255, 246, 200, 170), width=int(_x(2)))
        d.ellipse([_x(cxh - rw), _x(cyh - rh), _x(cxh + rw), _x(cyh + rh)],
                  outline=(242, 217, 138, 255), width=int(_x(3)))
        return img

    def _build_innocent_head_mask(self):
        """1x mask selecting the HEAD region (ears, face, antennae, halo)
        so the innocent head-tilt can rotate just the head around the
        neck, leaving the body + arms planted. Solid above the neck, then
        feathered through the neck band so there's no hard seam. The head
        is narrower than the body here and the same coral colour, so the
        small rotation blends invisibly."""
        w, h = self.base_adoring.size
        m = Image.new("L", (w, h), 0)
        d = ImageDraw.Draw(m)
        d.rectangle([0, 0, w, 204], fill=255)
        for yy in range(204, 224):
            a = max(0, int(round(255 * (1 - (yy - 204) / 20.0))))
            d.line([(0, yy), (w, yy)], fill=a)
        return m

    def _build_alert_ring(self):
        img = _new()
        ImageDraw.Draw(img).line(
            _smooth(self._head_pts()) + [_smooth(self._head_pts())[0]],
            fill=RED + (255,), width=int(_x(2)), joint="curve")
        return img

    def _build_wave_patch(self):
        """Sculpted raised arm pointing straight up in a local patch;
        frame() rotates it around the shoulder pivot. Paw shows cream
        palm pad + toe beans like the portrait."""
        pw, ph = 170, 130          # local 1x patch size
        img = Image.new("RGBA", (pw * S, ph * S), (0, 0, 0, 0))
        ax, ay = 85, 118           # shoulder pivot in patch (1x)
        arm = [(ax - 8, ay), (ax - 9, ay - 30), (ax - 10, ay - 55),
               (ax - 12, ay - 72), (ax - 4, ay - 82), (ax + 8, ay - 81),
               (ax + 14, ay - 70), (ax + 11, ay - 52), (ax + 9, ay - 28),
               (ax + 8, ay)]
        old_x = globals()["_x"]

        def lx(v):
            return v * S
        globals()["_x"] = lx
        _grad_fill(img, arm, SUIT_TOP, SUIT_BOT, outline=SUIT_EDGE, ow=1.4)
        # brown mitten over the top third, clipped to the limb
        limb_mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(limb_mask).polygon(_smooth(arm), fill=255)
        paw = Image.new("RGBA", img.size, (0, 0, 0, 0))
        _grad_fill(paw, arm, PAW_TOP, PAW_BOT)
        band = Image.new("L", img.size, 0)
        bd = ImageDraw.Draw(band)
        bd.rectangle([0, 0, img.size[0], lx(ay - 62)], fill=255)
        bd.ellipse([lx(ax - 20), lx(ay - 68), lx(ax + 20), lx(ay - 56)],
                   fill=255)
        paw.putalpha(Image.composite(
            paw.getchannel("A"), Image.new("L", img.size, 0),
            Image.composite(band, Image.new("L", img.size, 0), limb_mask)))
        img.alpha_composite(paw)
        globals()["_x"] = old_x
        # detailed paw face: palm pad + four toe beans + soft claws,
        # drawn in patch-local coords (lx). Toes point up (raised paw).
        lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        pcx, pcy, r = ax, ay - 66, 8.5
        # palm pad
        d.ellipse([lx(pcx - r * 0.7), lx(pcy - r * 0.5),
                   lx(pcx + r * 0.7), lx(pcy + r * 0.55)],
                  fill=PAD + (255,))
        # four toe beans arced above the palm, each capped with a claw
        for fx in (-0.62, -0.21, 0.21, 0.62):
            tx = pcx + fx * r * 1.15
            ty = pcy - r * 0.95 - (r * 0.14) * (1 - abs(fx) * 0.7)
            tr = r * (0.26 if abs(fx) > 0.5 else 0.30)
            d.ellipse([lx(tx - tr), lx(ty - tr), lx(tx + tr), lx(ty + tr)],
                      fill=PAD + (255,))
            cy2 = ty - tr * 1.3
            d.polygon([(lx(tx), lx(cy2 - tr * 0.55)),
                       (lx(tx + tr * 0.42), lx(cy2)),
                       (lx(tx), lx(cy2 + tr * 0.3)),
                       (lx(tx - tr * 0.42), lx(cy2))],
                      fill=(250, 240, 226, 255))
        img.alpha_composite(lay)
        return img, (ax, ay)

    def _antennae(self, pha, phb, alert=False, droop=0.0, startle=0.0,
                  quiver=0.0):
        """Twin cute sprouts from the crown CENTER, tiny V, ball tips.
        Independent sway phases, decoupled from the bob.

        `droop` 0..1 WILTS them (sad_simple): the stalks bend outward, the
        ball tips flop down toward his head, and the perky sway DIES AWAY as
        they go - a wilted antenna that still waggles cheerfully would kill
        the whole read.

        `startle` 0..1 is the exact INVERSE (surprised): they SNAP BOLT
        UPRIGHT - pulled in toward vertical and shot taller - and the lazy
        sway is replaced by `quiver`, a fast shake driven from buddy.py (the
        pet owns the timing; this just draws it).

        droop=0 / startle=0 is the original, untouched.
        """
        img = _new()
        d = ImageDraw.Draw(img)
        tip = RED if alert else SUIT_BOT
        for sx, ph in ((-1, pha), (1, phb)):
            bx = HX + sx * 2.5
            by = HY - 38
            # the idle sway dies off under EITHER a wilt or a startle
            sway = math.sin(ph) * 2.2 * (1.0 - 0.8 * droop) * (1.0 - startle)
            # *** DON'T DROOP THEM INTO HIS SKULL. *** First pass dropped the
            # tips 17px, which buried them in the hood - a dark stalk on a
            # same-coloured head, so they simply VANISHED instead of wilting.
            # A wilt has to stay READABLE: the stalk arcs UP (the mid actually
            # RISES) and then flops OVER and OUTWARD, so the tips hang clear
            # of the head silhouette against open background.
            tx = HX + sx * 8 + sway + sx * 8.0 * droop
            ty = HY - 52 + 9.0 * droop
            mx = HX + sx * 4 + sway * 0.5 + sx * 1.0 * droop
            my = HY - 46 - 2.0 * droop
            # STARTLE: pull them in toward vertical, shoot them taller, and
            # shake the tips. The quiver is on the TIPS only - shaking the
            # roots would just look like his head was vibrating.
            tx += (-sx * 4.0) * startle + quiver * 2.6 * startle
            ty += -9.0 * startle
            mx += (-sx * 1.2) * startle + quiver * 1.0 * startle
            my += -4.0 * startle
            d.line([(_x(bx), _x(by)), (_x(mx), _x(my)), (_x(tx), _x(ty))],
                   fill=SUIT_EDGE + (255,), width=int(_x(2)),
                   joint="curve")
            r = _x(3.1)
            d.ellipse([_x(tx) - r, _x(ty - 1.5) - r, _x(tx) + r,
                       _x(ty - 1.5) + r], fill=tip + (255,),
                      outline=SUIT_EDGE + (255,), width=int(_x(0.8)))
        return _down(img)

    def frame(self, emote, blinking, wave_angle, pha, phb, turn=0.0,
              wipe=None, yawn=None, nausea=None, pant=None, spin=None,
              push=None, sad=None, surprise=None, plead=None, scare=None,
              droop=None, scheme=None):
        if emote == "mischievous" and scheme is not None:
            # *** HE RUBS HIS PAWS TOGETHER. *** The scheming gesture.
            # base_adoring is the NO-LEFT-ARM base, because mischief_paws draws
            # BOTH arms itself - compositing over the normal base would leave
            # the baked left arm underneath and give him three.
            # Note we do NOT composite self.right_arm here for the same reason.
            img = self.base_adoring.copy()
            img.alpha_composite(self.mischief_paws[int(scheme * 10) % 10])
            img.alpha_composite(self._antennae(pha, phb, False))
            img.alpha_composite(self.plates[_plate_key(emote, blinking)])
            return img
        if emote == "exhausted" and droop is not None:
            # *** A REAL DROOP. *** `droop` 0..1.
            # Chloe on the first pass: "the thing you're calling a droop is
            # just this whole entire body uniformly sinking lower on the
            # screen. It's not head and arm droop." Dead right - buddy.py's
            # `bob` TRANSLATES THE WHOLE SPRITE. A sprite sliding down the
            # screen is not a character sagging. So now, all at once:
            #   HEAD  sinks into his shoulders   (head_dy, baked per base)
            #   EARS  wilt                       (ear_droop, baked per base)
            #   ARMS  go limp and swing loose    (exh_arms)
            #   ANTENNAE droop                   (the layer's own droop param)
            # ...while his BODY and FEET stay exactly where they are. That is
            # the difference between sagging and descending.
            # The face plate and antennae are shifted DOWN BY THE SAME head_dy,
            # or his face would stay behind while his head left without it.
            d = max(0.0, min(1.0, droop))
            k = int(round(d * 7))
            dy = int(round(7.0 * d))
            img = self.exh_bases[k].copy()
            img.alpha_composite(self.exh_arms[k])
            img.alpha_composite(self._antennae(pha, phb, False, droop=d),
                                (0, dy))
            img.alpha_composite(self.plates[_plate_key(emote, blinking)],
                                (0, dy))
            return img
        if emote == "scared" and scare is not None:
            # HE CANNOT HOLD STILL. `scare` is the jitter STEP (an int), driven
            # from buddy.py so the pet owns the tremble rate.
            # TERRIFIED (confirmed) is the opposite emote: it has NO body motion
            # at all - a frozen mask of horror. Scared MOVES. That is the split.
            # No _plate_key: scared isn't in _BLINKABLE, and a blink would hide
            # the jittering eyes, which ARE the emote.
            img = self.base.copy()
            img.alpha_composite(self.right_arm)
            img.alpha_composite(self._antennae(pha, phb, False))
            img.alpha_composite(self.scared_plates[int(scare) % 12])
            return img
        if emote == "pleading" and plead is not None:
            # HE'S ASKING YOU FOR SOMETHING. `plead` is the shimmer phase
            # (0..1, cyclic) driving the wet eyes and the quivering pout.
            # Uses base_adoring (the clean no-left-arm base) because BOTH arms
            # are replaced - so there's no resting arm to erase and no seam.
            # No _plate_key: pleading isn't in _BLINKABLE, and a blink would
            # cover up the eyes, which ARE the emote.
            img = self.base_adoring.copy()
            img.alpha_composite(self._antennae(pha, phb, False))
            i = int(plead * 10) % 10
            img.alpha_composite(self.plead_plates[i])
            img.alpha_composite(self.plead_paws[i])
            return img
        if emote == "surprised" and surprise is not None:
            # THE STARTLE. `surprise` is (k, quiver): k 0..1 is how startled
            # he is right now, quiver is the antenna shake (-1..1), both driven
            # from buddy.py so the pet owns the timing.
            # Does NOT use _plate_key: surprised is not in _BLINKABLE, and he
            # shouldn't blink mid-startle anyway. Blink flag stays False.
            k, qv = surprise
            k = max(0.0, min(1.0, k))
            img = self.base.copy()
            img.alpha_composite(self.right_arm)
            img.alpha_composite(self._antennae(pha, phb, False,
                                               startle=k, quiver=qv))
            img.alpha_composite(self.surprised_plates[int(round(k * 8))])
            return img
        if emote == "sad_simple" and sad is not None:
            # His EARS AND ANTENNAE WILT. `sad` is 0..1.
            # The ears are baked into the base, so we swap in a pre-built base
            # whose ear polygons are drooped (self.sad_bases). The antennae
            # are a live layer, so the droop just gets passed straight in.
            # Uses the NORMAL plate lookup, so he STILL BLINKS while he's sad
            # - which is why sad_simple's blink flag has to be True.
            s = max(0.0, min(1.0, sad))
            img = self.sad_bases[int(round(s * 9))].copy()
            img.alpha_composite(self.right_arm)
            img.alpha_composite(self._antennae(pha, phb, False, droop=s))
            img.alpha_composite(self.plates[_plate_key(emote, blinking)])
            return img
        if emote == "nerdy" and push is not None:
            # Mid-push: the right arm brings a paw up to the bridge of his
            # nose. `push` is 0..1. At rest (k == 0) use his REAL arm layer so
            # the idle pose is pixel-identical to normal. The GLASSES
            # themselves are drawn in buddy.py (they slide, so they can't be
            # baked into a plate).
            img = self.base.copy()
            k = int(round(max(0.0, min(1.0, push)) * 8))
            img.alpha_composite(self.right_arm if k == 0
                                else self.push_arms[k])
            img.alpha_composite(self._antennae(pha, phb, False))
            img.alpha_composite(self.plates[_plate_key(emote, blinking)])
            return img
        if emote == "dizzy" and spin is not None:
            # The eye spirals SPIN. `spin` is 0..1 around one full turn.
            img = self.base.copy()
            img.alpha_composite(self.right_arm)
            img.alpha_composite(self._antennae(pha, phb, False))
            k = int(round((spin % 1.0) * 18)) % 18
            img.alpha_composite(self.dizzy_plates[k])
            return img
        if emote == "hot" and pant is not None:
            # Overheated: the pant keyframe is picked by phase so his mouth
            # and tongue actually move. Sweat + heat shimmer are drawn in
            # buddy.py on top of this.
            img = self.base.copy()
            img.alpha_composite(self.right_arm)
            img.alpha_composite(self._antennae(pha, phb, False))
            k = int(round(max(0.0, min(1.0, pant)) * 6))
            img.alpha_composite(self.hot_plates[k])
            return img
        if emote == "nauseated" and nausea is not None:
            green, open_mouth = nausea
            img = self.base.copy()
            img.alpha_composite(self.right_arm)
            # *** GREEN THE SKIN ONLY. *** The tint goes on HERE - over the
            # fur/suit, but BEFORE the face plate. Tinting the finished frame
            # (as the first version did) also greened his EYES, NOSE, BROWS
            # and MOUTH, which read as wrong. Features are composited on top
            # of the tint and keep their own colour.
            if green > 0.01:
                tint = Image.new("RGBA", img.size, (110, 176, 98, 0))
                m = self._nausea_mask.point(
                    lambda v, g=green: int(v * g))
                tint.putalpha(ImageChops.multiply(img.getchannel("A"), m))
                img.alpha_composite(tint)
            img.alpha_composite(self._antennae(pha, phb, False))
            img.alpha_composite(self.nauseated_plates[1 if open_mouth else 0])
            return img
        if emote == "yawn" and yawn is not None:
            # The yawn face is a pre-rendered keyframe (mouth grows/closes),
            # picked by intensity. Outside the yawn it falls through to the
            # normal path - the gesture plays ONCE, it isn't a loop.
            #
            # *** The right arm MUST be composited here. *** The normal path
            # does img.alpha_composite(self.right_arm); this branch bypasses
            # that, and omitting an arm entirely is what made one of them
            # VANISH on the first pass. Here it's replaced by the yawn arm,
            # which rises toward the mouth to cover the yawn - composited
            # LAST so the paw partially obscures the open mouth.
            img = self.base.copy()
            k = int(round(max(0.0, min(1.0, yawn)) * 10))
            img.alpha_composite(self._antennae(pha, phb, False))
            img.alpha_composite(self.yawn_plates[k])
            ka = int(round(max(0.0, min(1.0, yawn)) * 8))
            # At rest use his REAL arm layer (correct hanging pose, palm pads
            # showing). Only swap in the raised yawn arm once it's actually
            # lifting - that way the rest pose is pixel-identical to normal.
            img.alpha_composite(self.right_arm if ka == 0
                                else self.yawn_arms[ka])
            return img
        if emote == "relieved" and wipe is not None:
            # Mid-wipe: the right arm is up at the forehead. `wipe` is 0..1
            # across the brow; pick the nearest pre-rendered keyframe.
            # Outside the wipe, relieved falls through to the normal path and
            # he just stands in the idle arm pose - the gesture happens ONCE
            # (Chloe's spec), it isn't a loop.
            img = self.base.copy()
            img.alpha_composite(self._antennae(pha, phb, False))
            img.alpha_composite(self.plates[_plate_key(emote, blinking)])
            k = int(round(max(0.0, min(1.0, wipe)) * 8))
            img.alpha_composite(self.wipe_arms[k])
            return img
        if emote == "adoring":
            # Clean no-left-arm base (both paws are raised instead of the
            # resting arm). Face plate FIRST, paws LAST - the hands are
            # held up IN FRONT of the face and must occlude the mouth.
            img = self.base_adoring.copy()
            img.alpha_composite(self._antennae(pha, phb, False))
            img.alpha_composite(self.plates[_plate_key(emote, blinking)])
            img.alpha_composite(self.cheek_paws)
            return img
        if emote == "cold":
            # clean no-left-arm base + both forearms crossed over the
            # chest (self-hug). Arms go on BEFORE the face plate - they
            # sit over the chest, well below the head.
            img = self.base_adoring.copy()
            img.alpha_composite(self.cold_arms)
            img.alpha_composite(self._antennae(pha, phb, False))
            img.alpha_composite(self.plates[_plate_key(emote, blinking)])
            return img
        if emote == "awkward":
            # LEFT arm raised to scratch the BACK of the head: drawn
            # FIRST (behind), then the body over it so the head occludes
            # everything passing behind it - only the elbow and the paw
            # peeking over the crown show. Right arm rests normally. Eyeless
            # plate - shifty eyes + head tilt are applied in buddy.py.
            img = Image.new("RGBA", self.base.size, (0, 0, 0, 0))
            img.alpha_composite(self.scratch_arm)
            img.alpha_composite(self.base_adoring)
            img.alpha_composite(self.right_arm)
            img.alpha_composite(self._antennae(pha, phb, False))
            img.alpha_composite(self.plates[_plate_key(emote, blinking)])
            return img
        if emote == "bashful":
            # Clean no-left-arm base (no resting arms -> no side gaps).
            # Face plate first (shy closed-cup eyes + smile), then the
            # flush on the skin, then both paws raised HIGH over the eyes
            # (palms in, mitten backs only) so the eyes peek out below.
            img = self.base_adoring.copy()
            img.alpha_composite(self._antennae(pha, phb, False))
            img.alpha_composite(self.plates[_plate_key(emote, blinking)])
            img.alpha_composite(self.bashful_blush)
            img.alpha_composite(self.bashful_paws)
            return img
        if emote == "innocent":
            # Hands clasped behind his back: the arm layer sits BEHIND the
            # body (elbows poke out, forearms hidden), then the full body
            # + face on top, then the holy halo.
            img = Image.new("RGBA", self.base_adoring.size, (0, 0, 0, 0))
            img.alpha_composite(self.innocent_hands)
            img.alpha_composite(self.base_adoring)
            img.alpha_composite(self._antennae(pha, phb, False))
            img.alpha_composite(self.plates[_plate_key(emote, blinking)])
            img.alpha_composite(self.innocent_halo)
            if turn:
                # cute PUPPY head-tilt: rotate ONLY the head (ears, face,
                # antennae, halo) about the neck; body + arms stay planted.
                # `turn` carries the tilt angle in degrees. This is layered
                # UNDER the gentle whole-body rock added in buddy.py.
                head = img.rotate(turn, center=(CX, 214),
                                  resample=Image.BICUBIC)
                img.paste(head, (0, 0), self._innocent_head_mask)
            return img
        if emote == "shush":
            # Right hand raised to the muzzle with ONE finger held
            # vertically over the lips (the 'shhh') - not a whole paw over
            # the mouth. Left arm keeps its resting pose (baked in base);
            # the raised hand is composited LAST so the finger occludes the
            # lips. Face plate carries the soft half-lidded 'quiet' eyes.
            img = self.base.copy()
            img.alpha_composite(self._antennae(pha, phb, False))
            img.alpha_composite(self.plates[_plate_key(emote, blinking)])
            img.alpha_composite(self.shush_arm)
            return img
        if emote == "giggle":
            # Right paw clapped FLAT over the mouth, stifling a laugh. Hand
            # composited LAST so it actually covers the mouth. Left arm keeps
            # its resting pose (baked into self.base). The crinkled
            # closed-cup eyes come from the plate; the body's giggle HITCH is
            # applied per-frame in buddy.py.
            img = self.base.copy()
            img.alpha_composite(self._antennae(pha, phb, False))
            img.alpha_composite(self.plates[_plate_key(emote, blinking)])
            img.alpha_composite(self.giggle_arm)
            return img
        if emote == "hug":
            # Clean no-left-arm base + a big heart SQUEEZED into the chest.
            # Order is the whole trick: heart DOWN FIRST, then the arms
            # OVER its face - forearms crossing its lower half with each
            # paw past the far edge - so the heart is enveloped by the
            # embrace rather than presented between two paws. Only its top
            # lobes peek out above the arms.
            img = self.base_adoring.copy()
            img.alpha_composite(self._antennae(pha, phb, False))
            img.alpha_composite(self.plates[_plate_key(emote, blinking)])
            img.alpha_composite(self.hug_heart)
            img.alpha_composite(self.hug_arms)
            return img
        img = self.base.copy()
        if emote == "wave" and wave_angle is not None:
            deg = -(math.degrees(wave_angle) + 90)
            ax, ay = self._wave_pivot
            patch = self._wave_patch.rotate(
                deg, center=(ax * S, ay * S), resample=Image.BICUBIC)
            pw = self._wave_patch.width // S
            ph2 = self._wave_patch.height // S
            patch = patch.resize((pw, ph2), Image.LANCZOS)
            tmp = Image.new("RGBA", img.size, (0, 0, 0, 0))
            tmp.paste(patch, (CX + 40 - ax, CY + 2 - ay))
            img.alpha_composite(tmp)
        elif emote in ("laughing_crying", "rofl"):
            img.alpha_composite(self.belly_paw_arm)
        else:
            img.alpha_composite(self.right_arm)
        img.alpha_composite(self._antennae(pha, phb, emote == "alert"))
        img.alpha_composite(self.plates[_plate_key(emote, blinking)])
        if emote == "alert":
            img.alpha_composite(self.alert_ring)
        return img

    # ----- face plates -----
    def _glossy_eyes(self, img, ey=HY - 4, r=8.5):
        for ex in (HX - 16, HX + 16):
            _grad_fill(img, [(ex, ey - r), (ex + r * 0.8, ey - r * 0.55),
                             (ex + r, ey), (ex + r * 0.8, ey + r * 0.6),
                             (ex, ey + r), (ex - r * 0.8, ey + r * 0.6),
                             (ex - r, ey), (ex - r * 0.8, ey - r * 0.55)],
                       (58, 42, 34), INK)
            _soft(img, (ex - 5.5, ey - 6.5, ex - 0.5, ey - 1.5),
                  WHITE, 245, 8)
            _soft(img, (ex + 2, ey + 2, ex + 5.5, ey + 5.5), WHITE, 118, 6)

    def _blink_eyes(self, img):
        d = ImageDraw.Draw(img)
        for ex in (HX - 16, HX + 16):
            d.line([_x(ex - 8), _x(HY - 4), _x(ex + 8), _x(HY - 4)],
                   fill=INK + (255,), width=int(_x(2.6)))

    def _happy_eyes(self, img):
        """Delighted caret eyes (^ ^): two upward-peaked strokes, more
        energetic than a soft closed curve."""
        d = ImageDraw.Draw(img)
        for ex in (HX - 16, HX + 16):
            d.line([(_x(ex - 8), _x(HY + 1)), (_x(ex), _x(HY - 7)),
                    (_x(ex + 8), _x(HY + 1))],
                   fill=INK + (255,), width=int(_x(2.8)), joint="curve")

    def _mouth_open(self, img, w=11.0, h=6.0, lower=True, drop=0.0,
                    corner_lift=0.0):
        """Portrait mouth: smile-shaped opening (corners tucked up),
        ONE wide upper tooth band + ONE wide lower band, both clipped
        inside the opening so they can never escape it. Sits clearly
        below the nose. corner_lift>0 pulls the outer mouth corners
        higher for a bigger cheek-to-cheek grin (e.g. 'grinning')."""
        mcx, mcy = HX, HY + 19 + drop
        cl = corner_lift
        pts = [(mcx - w, mcy - h * (0.55 + cl)),
               (mcx - w * 0.5, mcy - h * 0.95),
               (mcx, mcy - h), (mcx + w * 0.5, mcy - h * 0.95),
               (mcx + w, mcy - h * (0.55 + cl)),
               (mcx + w * 0.62, mcy + h * 0.5),
               (mcx, mcy + h), (mcx - w * 0.62, mcy + h * 0.5)]
        open_mask = _mask_of(pts)
        _grad_fill(img, pts, MOUTH_IN, (86, 46, 34))
        teeth = Image.new("RGBA", img.size, (0, 0, 0, 0))
        td = ImageDraw.Draw(teeth)
        td.rounded_rectangle(
            [_x(mcx - 6.5), _x(mcy - h - 2), _x(mcx + 6.5),
             _x(mcy - h * 0.05)], radius=int(_x(2)),
            fill=TOOTH + (255,), outline=(226, 214, 198, 255),
            width=int(_x(0.7)))
        if lower:
            td.rounded_rectangle(
                [_x(mcx - 5), _x(mcy + h * 0.2), _x(mcx + 5),
                 _x(mcy + h + 2)], radius=int(_x(2)),
                fill=TOOTH + (255,), outline=(226, 214, 198, 255),
                width=int(_x(0.7)))
        teeth.putalpha(Image.composite(
            teeth.getchannel("A"), Image.new("L", img.size, 0), open_mask))
        img.alpha_composite(teeth)
        poly = _smooth(pts)
        ImageDraw.Draw(img).line(poly + [poly[0]], fill=INK + (255,),
                                 width=int(_x(1.4)), joint="curve")

    def _mouth_awkward(self, img):
        """Awkward mouth: EXACTLY the idle mouth's teeth (same size, same
        place) but the opening is pulled WIDER and flattened to an
        expressionless shape - corners sit level with the mid-line (no
        smile-lift, no frown), just loosely agape and stretched wider
        cheek-to-cheek. The 'yikes' look."""
        mcx, mcy = HX, HY + 19
        w, h = 14.0, 6.0   # wider than idle (11); same vertical opening
        # expressionless: corners level at mcy, top/bottom symmetric
        pts = [(mcx - w, mcy), (mcx - w * 0.5, mcy - h * 0.92),
               (mcx, mcy - h), (mcx + w * 0.5, mcy - h * 0.92),
               (mcx + w, mcy), (mcx + w * 0.5, mcy + h * 0.92),
               (mcx, mcy + h), (mcx - w * 0.5, mcy + h * 0.92)]
        open_mask = _mask_of(pts)
        _grad_fill(img, pts, MOUTH_IN, (86, 46, 34))
        # SAME teeth as idle (identical rects, h=6 geometry), clipped
        teeth = Image.new("RGBA", img.size, (0, 0, 0, 0))
        td = ImageDraw.Draw(teeth)
        td.rounded_rectangle(
            [_x(mcx - 6.5), _x(mcy - h - 2), _x(mcx + 6.5),
             _x(mcy - h * 0.05)], radius=int(_x(2)),
            fill=TOOTH + (255,), outline=(226, 214, 198, 255),
            width=int(_x(0.7)))
        td.rounded_rectangle(
            [_x(mcx - 5), _x(mcy + h * 0.2), _x(mcx + 5),
             _x(mcy + h + 2)], radius=int(_x(2)),
            fill=TOOTH + (255,), outline=(226, 214, 198, 255),
            width=int(_x(0.7)))
        teeth.putalpha(Image.composite(
            teeth.getchannel("A"), Image.new("L", img.size, 0), open_mask))
        img.alpha_composite(teeth)
        poly = _smooth(pts)
        ImageDraw.Draw(img).line(poly + [poly[0]], fill=INK + (255,),
                                 width=int(_x(1.4)), joint="curve")

    # ===================================================================
    # Reusable face-part toolkit (eyes / brows / mouths / accessories).
    # Every new emoji-driven face below is built by COMBINING these, the
    # same way a real character sheet differentiates expressions - not
    # by inventing one-off primitives per emote.
    # ===================================================================

    def _brow_confused(self, img):
        """MISMATCHED brows, pushed hard: one driven UP and arched high, the
        other shoved DOWN and angled in. Stronger than _brow_cocked (which is
        just one arch + one flat line) - confusion needs the two halves of his
        face to disagree with each other."""
        d = ImageDraw.Draw(img)
        # RIGHT brow: hoisted high and arched
        d.arc([_x(HX + 5), _x(HY - 24), _x(HX + 27), _x(HY - 13)],
              start=195, end=345, fill=INK + (255,), width=int(_x(2.3)))
        # LEFT brow: pushed down, inner end lower = a baffled scowl
        d.line([_x(HX - 26), _x(HY - 15), _x(HX - 8), _x(HY - 10)],
               fill=INK + (255,), width=int(_x(2.3)))

    def _eye_uneven(self, img):
        """One eye a touch NARROWED, the other normal. A subtle asymmetry that
        pairs with the mismatched brows - his face can't agree on a reaction.
        Kept subtle: overdo it and it becomes a wink or a squint."""
        ey = HY - 3
        # left: slightly squeezed
        ex = HX - 16
        _grad_fill(img, [(ex, ey - 5.6), (ex + 5.6, ey - 4.2),
                         (ex + 7.8, ey), (ex + 5.6, ey + 5.2),
                         (ex, ey + 6.6), (ex - 5.6, ey + 5.2),
                         (ex - 7.8, ey), (ex - 5.6, ey - 4.2)],
                   (58, 42, 34), INK)
        _soft(img, (ex - 4.6, ey - 3.4, ex - 1.0, ey - 0.2), WHITE, 185, 5)
        # right: open, normal
        ex = HX + 16
        _grad_fill(img, [(ex, ey - 7.8), (ex + 6.0, ey - 5.8),
                         (ex + 8.2, ey), (ex + 6.0, ey + 5.8),
                         (ex, ey + 7.8), (ex - 6.0, ey + 5.8),
                         (ex - 8.2, ey), (ex - 6.0, ey - 5.8)],
                   (58, 42, 34), INK)
        _soft(img, (ex - 5.0, ey - 4.6, ex - 1.0, ey - 0.6), WHITE, 195, 6)

    def _mouth_uncertain(self, img, y=20):
        """A small, unhappy, UNCERTAIN mouth - a shallow wobble pulled off to
        one side. Not the big queasy wobble of nauseated, not pensive's
        downturn: this one is SMALL and LOPSIDED, the mouth of someone who
        started to answer and stopped."""
        d = ImageDraw.Draw(img)
        my = HY + y
        pts = []
        for i in range(13):
            f = i / 12.0
            xx = HX - 7.5 + f * 14.0
            yy = my + math.sin(f * 5.4) * 1.5 + f * 1.4   # sags to one side
            pts.append((_x(xx), _x(yy)))
        d.line(pts, fill=INK + (255,), width=int(_x(2.2)), joint="curve")

    def _eye_scrutiny(self, img):
        """The APPRAISING face: one eye NARROWED to a shrewd slit, the other
        held WIDE and magnified behind the monocle.

        The asymmetry is the entire read. Two matching eyes look like plain
        curiosity; squeezing one shut while the other bulges through a lens is
        unmistakably 'I am examining you and have not decided yet'.
        (nerdy magnifies BOTH eyes - it's about knowing. This one aims a lens
        AT you - it's about examining.)"""
        # LEFT eye: narrowed to a shrewd slit
        ex, ey = HX - 16, HY - 3
        _grad_fill(img, [(ex - 8.2, ey + 0.6), (ex - 4.0, ey - 3.0),
                         (ex + 1.0, ey - 3.8), (ex + 6.0, ey - 2.4),
                         (ex + 8.2, ey + 0.6), (ex + 5.4, ey + 3.0),
                         (ex, ey + 3.6), (ex - 5.4, ey + 2.8)],
                   (58, 42, 34), INK)
        _soft(img, (ex - 4.6, ey - 2.4, ex - 1.4, ey - 0.2), WHITE, 150, 5)

        # RIGHT eye: WIDE, magnified by the monocle lens
        ex = HX + 16
        _grad_fill(img, [(ex, ey - 9.4), (ex + 6.8, ey - 6.9),
                         (ex + 9.6, ey), (ex + 6.8, ey + 6.9),
                         (ex, ey + 9.4), (ex - 6.8, ey + 6.9),
                         (ex - 9.6, ey), (ex - 6.8, ey - 6.9)],
                   (58, 42, 34), INK)
        _soft(img, (ex - 5.8, ey - 5.6, ex - 1.2, ey - 1.0), WHITE, 210, 6)
        _soft(img, (ex + 2.6, ey + 2.8, ex + 5.2, ey + 5.2), WHITE, 85, 5)

    def _mouth_pursed(self, img, y=20):
        """A small, tight, PURSED mouth - lips pressed while he weighs you up.
        Deliberately NOT a frown (that would be judgement already delivered)
        and NOT a wobble. He hasn't made his mind up yet; the mouth is just
        held. Pulled slightly off-centre so it doesn't read as neutral/flat."""
        d = ImageDraw.Draw(img)
        my = HY + y
        pts = []
        for i in range(11):
            f = i / 10.0
            xx = HX - 5.4 + f * 11.0
            yy = my - math.sin(f * math.pi) * 0.8
            pts.append((_x(xx), _x(yy)))
        d.line(pts, fill=INK + (255,), width=int(_x(2.4)), joint="curve")
        # a small crease at the tight corner
        d.line([_x(HX + 6.0), _x(my - 0.6), _x(HX + 7.8), _x(my + 1.6)],
               fill=INK + (190,), width=int(_x(1.1)))

    def _eye_magnified(self, img):
        """Eyes seen THROUGH thick lenses - noticeably bigger than his normal
        bead eyes, with a big wet catchlight. The magnification is the point:
        it's what tells you the lenses are strong, and it's the opposite of
        cool's shades (which HIDE the eyes entirely). Between the two, nerdy
        shows MORE eye than usual and cool shows none."""
        for ex in (HX - 16, HX + 16):
            ey = HY - 3
            _grad_fill(img, [(ex, ey - 8.6), (ex + 6.2, ey - 6.3),
                             (ex + 8.8, ey), (ex + 6.2, ey + 6.3),
                             (ex, ey + 8.6), (ex - 6.2, ey + 6.3),
                             (ex - 8.8, ey), (ex - 6.2, ey - 6.3)],
                       (58, 42, 34), INK)
            _soft(img, (ex - 5.2, ey - 5.0, ex - 1.0, ey - 0.8),
                  WHITE, 205, 6)
            _soft(img, (ex + 2.2, ey + 2.4, ex + 4.6, ey + 4.6),
                  WHITE, 80, 5)

    def _mouth_buck(self, img, y=20):
        """A pleased little know-it-all smile with two BUCK TEETH showing.
        The teeth do most of the work - they're the single most legible
        'nerdy' cue at pet scale, more so than any mouth shape."""
        d = ImageDraw.Draw(img)
        my = HY + y
        # the smile: a modest upward arc
        pts = []
        for i in range(13):
            f = i / 12.0
            xx = HX - 9 + f * 18
            yy = my + math.sin(f * math.pi) * 2.0
            pts.append((_x(xx), _x(yy)))
        d.line(pts, fill=INK + (255,), width=int(_x(2.0)), joint="curve")
        # TWO front teeth hanging from the upper lip
        for tx in (HX - 3.4, HX + 0.6):
            _grad_fill(img, [(tx, my - 0.6), (tx + 3.0, my - 0.6),
                             (tx + 3.0, my + 4.6), (tx + 2.4, my + 5.4),
                             (tx + 0.6, my + 5.4), (tx, my + 4.6)],
                       (255, 253, 248), (226, 218, 206), outline=INK, ow=0.9)

    def _build_push_arm(self, s):
        """RIGHT arm coming up to shove his glasses back up. `s` is 0..1
        (0 = arm at rest by his side, 1 = paw pressed against the frame).

        *** THE ARM GOES OUT AND UP AROUND THE SIDE OF THE HEAD, and the paw
        arrives at the OUTER EDGE of the right lens - NOT at the bridge. ***
        A first pass ran the paw to the centre of his face and the forearm
        cut a thick orange sausage diagonally across his cheek. Same failure
        _build_wipe_arm was written to avoid. Pushing the specs up from the
        side of the frame is also what people actually do.
        The limb is kept THICK (outer and inner edges well separated) - a
        narrow polygon here reads as a tube/pipe, not a furry arm."""
        img = _new()
        # paw: rest by his side  ->  outer edge of the right lens
        px = (CX + 50) + s * ((CX + 24) - (CX + 50))
        py = (CY + 6) + s * ((CY - 66) - (CY + 6))
        # the arm rises up the SIDE as s grows
        elbow_y = (CY + 10) + s * ((CY - 18) - (CY + 10))
        fore_y = (CY + 6) + s * ((CY - 56) - (CY + 6))
        arm = [
            (CX + 30, CY + 8),       # shoulder, outer
            (CX + 64, elbow_y),      # elbow, swung wide
            (CX + 65, fore_y),       # forearm rising BESIDE the head
            (px + 12, py - 12),      # outer wrist
            (px - 10, py - 6),       # over the paw
            (px + 3, py + 11),       # inner wrist
            (CX + 43, fore_y + 10),  # forearm, inner edge
            (CX + 40, elbow_y + 4),  # elbow, inner
            (CX + 16, CY + 8),       # shoulder, inner
        ]
        self._draw_limb_cuff(img, arm, (px, py), cuff_r=11.5)
        return img

    def _eye_swirl(self, img, rot=0.0):
        """SPIRAL / SWIRL eyes - the classic dizzy eye, and the one thing
        nothing else in the set has.

        *** NAMED _eye_swirl, NOT _eye_spiral, ON PURPOSE. ***
        There is ALREADY an older `_eye_spiral(self, img, fx=0, which=...)`
        further down this file. Python takes the LAST definition in a class,
        so my new `_eye_spiral(img, rot)` was silently SHADOWED by it, and
        every call went to the old one - which treats its second argument as
        `fx`, a HORIZONTAL PIXEL OFFSET (HX - 16 + fx).
        So the rot value (0..6.28) was sliding the spirals SIDEWAYS by up to
        6px instead of rotating them. Chloe, exactly right: "they do not spin
        ... they go from being centered to drifting left."
        LESSON: before adding a helper, GREP FOR THE NAME. A duplicate method
        name in a class fails silently - no error, just the wrong function.

        A pale sclera disc with a dark spiral wound on top. `rot` spins it;
        keyframed in self.dizzy_plates so the swirl actually TURNS - a frozen
        spiral just looks like a weird pattern.

        *** THE EYE IS ONLY ~17 PIXELS WIDE. THE SPIRAL MUST BE READABLE AT
        THAT SIZE. *** Two failed passes taught this:
          - 2.5-3 TURNS packs the arms ~1px apart at pet scale: they blur into
            a dense squiggle, and rotating a uniform blur produces NO visible
            change. Chloe: "they do not spin... they are fixed along their
            circumference."
          - Tapering the outer end INTO the rim removed the one feature that
            shows angular position, making it even less readable.
        FIX: FEW turns (1.6) + a THICK stroke + a clear, blunt OUTER HOOK that
        ends in open space. The hook is an unambiguous angular marker, so when
        it sweeps around the eye the rotation is obvious. A spiral reads as
        spinning only if it has a feature you can TRACK."""
        d = ImageDraw.Draw(img)
        for i, ex in enumerate((HX - 16, HX + 16)):
            ey = HY - 3
            # pale disc behind the swirl so the dark spiral has contrast
            _grad_fill(img, [(ex, ey - 8.0), (ex + 6.4, ey - 5.8),
                             (ex + 8.4, ey), (ex + 6.4, ey + 5.8),
                             (ex, ey + 8.0), (ex - 6.4, ey + 5.8),
                             (ex - 8.4, ey), (ex - 6.4, ey - 5.8)],
                       (252, 246, 238), (222, 210, 198), outline=INK, ow=1.2)
            # the spiral - each eye winds the OPPOSITE way, which is far more
            # disorienting than two matching swirls
            turns = 1.6                  # FEW turns: arms stay far apart
            sgn = 1.0 if i == 0 else -1.0
            N = 70
            prev = None
            for s in range(N):
                f = s / (N - 1.0)
                ang = sgn * (rot + f * turns * 2 * math.pi)
                rad = 1.2 + f * 6.0
                pt = (ex + math.cos(ang) * rad,
                      ey + math.sin(ang) * rad * 0.93)
                if prev is not None:
                    d.line([_x(prev[0]), _x(prev[1]), _x(pt[0]), _x(pt[1])],
                           fill=INK + (255,), width=int(_x(2.1)))
                prev = pt
            # blunt cap on the OUTER HOOK - the feature the eye tracks, and
            # the whole reason the rotation is visible at all
            if prev is not None:
                d.ellipse([_x(prev[0] - 1.05), _x(prev[1] - 1.05),
                           _x(prev[0] + 1.05), _x(prev[1] + 1.05)],
                          fill=INK + (255,))
            # solid dark core so the centre doesn't look hollow
            d.ellipse([_x(ex - 1.5), _x(ey - 1.5),
                       _x(ex + 1.5), _x(ey + 1.5)], fill=INK + (255,))

    def _mouth_dazed(self, img, y=21):
        """A loose, lopsided, dazed mouth - hanging slightly open and pulled
        off-centre, like he can't quite find his face. Not the queasy wobble
        of nauseated and not drooling's slack want: this one is just
        SCRAMBLED."""
        my = HY + y
        _grad_fill(img, [(HX - 6.5, my - 2.6), (HX - 1.0, my - 3.8),
                         (HX + 5.5, my - 2.2), (HX + 7.5, my + 0.6),
                         (HX + 5.0, my + 4.0), (HX - 1.5, my + 4.8),
                         (HX - 6.0, my + 3.2), (HX - 7.8, my + 0.4)],
                   (116, 52, 56), (70, 26, 32), outline=INK, ow=1.3)

    def _eye_hot(self, img):
        """OVERHEATED eyes: heavy, drooping, WILTING. The outer corners sag
        downward - the eye itself is melting, not just half-closed.

        Distinct from sick's dull glaze (ill) and drooling's vacant stare
        (dopey): this one is DRAINED. The shine is kept but blown out and
        wet-looking, because his whole face is slick with sweat."""
        for i, ex in enumerate((HX - 16, HX + 16)):
            ey = HY - 1
            out = -1 if i == 0 else 1     # which side is the OUTER corner
            # squashed bead with the OUTER corner dragged down = a wilting eye
            _grad_fill(img, [(ex, ey - 3.8),
                             (ex + 6.6, ey - 2.6 + out * 0.9),
                             (ex + 8.2, ey + 0.4 + out * 1.9),
                             (ex + 6.4, ey + 4.0),
                             (ex, ey + 4.8),
                             (ex - 6.4, ey + 4.0),
                             (ex - 8.2, ey + 0.4 - out * 1.9),
                             (ex - 6.6, ey - 2.6 - out * 0.9)],
                       (58, 42, 34), INK)
            # big WET shine - he's slick, not merely glossy
            _soft(img, (ex - 4.8, ey - 2.4, ex - 0.8, ey + 1.4),
                  WHITE, 210, 6)

    def _mouth_pant(self, img, t=0.5):
        """PANTING mouth: hanging open with the TONGUE LOLLING OUT. `t`
        (0..1) drives how far it gapes and how far the tongue hangs, so the
        pant can actually breathe rather than sitting frozen.

        The lolling tongue is the single clearest 'overheated' signal - it's
        what an animal does to dump heat, and no other emote in the set has
        it (yummy's tongue LICKS, it doesn't hang)."""
        my = HY + 20
        mw = 7.0 + t * 1.8
        mh = 4.4 + t * 3.2
        # the open mouth
        _grad_fill(img, [(HX, my - mh), (HX + mw * 0.8, my - mh * 0.55),
                         (HX + mw, my + mh * 0.1),
                         (HX + mw * 0.72, my + mh * 0.8),
                         (HX, my + mh), (HX - mw * 0.72, my + mh * 0.8),
                         (HX - mw, my + mh * 0.1),
                         (HX - mw * 0.8, my - mh * 0.55)],
                   (118, 52, 56), (70, 26, 32), outline=INK, ow=1.4)
        # TONGUE hanging out and down, slightly off to one side, longer as
        # he pants harder
        tl = 6.0 + t * 5.0                 # how far it hangs below the lip
        tx = HX + 1.5                      # lolls a touch to one side
        ty = my + mh * 0.45
        _grad_fill(img, [(tx - 4.2, ty - 1.0), (tx + 4.2, ty - 1.0),
                         (tx + 4.6, ty + tl * 0.55),
                         (tx + 2.4, ty + tl),
                         (tx - 2.4, ty + tl),
                         (tx - 4.6, ty + tl * 0.55)],
                   (228, 130, 142), (188, 84, 104), outline=INK, ow=1.1)
        # centre crease + a wet highlight so the tongue reads as slick
        d = ImageDraw.Draw(img)
        d.line([_x(tx), _x(ty + 1.2), _x(tx), _x(ty + tl * 0.75)],
               fill=(176, 74, 96, 170), width=int(_x(0.9)))
        _soft(img, (tx - 3.0, ty + 0.6, tx - 0.6, ty + tl * 0.45),
              WHITE, 120, 5)

    def _heat_sheen(self, img):
        """Overheated flush: a broad, EVEN, deeply RED wash with small wet
        GLINTS on top.

        Deliberately UNLIKE sick's _fever_flush, which is BLOTCHY and
        unwell-looking. Hot is uniform and SLICK - he's flushed and shining
        with sweat, not mottled with illness. That's what keeps the two from
        colliding.
        Pushed HARD: his cheeks already carry a baked pink blush, so a soft
        red vanishes into it (the fever-flush lesson). An earlier pass here
        also used a big soft WHITE sheen, which washed the red back out and
        left him looking PALE - so the highlights are now small, tight glints
        rather than a broad white veil."""
        # broad, even, hot wash across the whole muzzle
        _soft(img, (HX - 30, HY + 0, HX + 30, HY + 17), (214, 66, 56), 150, 12)
        for sx in (HX - 25, HX + 25):
            _soft(img, (sx - 10, HY + 1, sx + 10, HY + 14),
                  (204, 44, 42), 185, 9)
            _soft(img, (sx - 6.5, HY + 3, sx + 5.0, HY + 11),
                  (198, 36, 38), 160, 6)
            # small TIGHT glint - a wet shine, not a white veil
            _soft(img, (sx - 5.0, HY + 2.0, sx - 1.6, HY + 5.0),
                  WHITE, 120, 3)
        # hot colour up onto the brow too, with one small glint
        _soft(img, (HX - 17, HY - 17, HX + 17, HY - 8), (206, 60, 54), 100, 8)
        _soft(img, (HX - 8, HY - 16, HX - 3, HY - 12), WHITE, 110, 3)

    def _eye_queasy(self, img):
        """Queasy, uncomfortable eyes - squinted against a rolling stomach.

        Not the DULL glazed eye of `sick` (a fever) - these are actively
        SCRUNCHED, like he's bracing. Uneven, and the lower lids push up,
        which is what a face does when it's trying not to be sick.
        Shape only - no stacked lid lines."""
        d = ImageDraw.Draw(img)
        for i, ex in enumerate((HX - 16, HX + 16)):
            ey = HY - 2
            hh = 3.4 if i == 0 else 3.0
            _grad_fill(img, [(ex, ey - hh), (ex + 6.4, ey - hh * 0.7),
                             (ex + 8.0, ey), (ex + 6.4, ey + hh * 0.8),
                             (ex, ey + hh), (ex - 6.4, ey + hh * 0.8),
                             (ex - 8.0, ey), (ex - 6.4, ey - hh * 0.7)],
                       (58, 42, 34), INK)
            _soft(img, (ex - 3.6, ey - hh * 0.4, ex - 1.4, ey + hh * 0.15),
                  WHITE, 120, 5)
            # lower lid pushing UP - the bracing squint
            d.arc([_x(ex - 8.4), _x(ey - 1), _x(ex + 8.4), _x(ey + 8)],
                  start=200, end=340, fill=INK + (255,), width=int(_x(1.7)))

    def _mouth_queasy(self, img, y=21):
        """A simple wavering, downturned queasy mouth. Nothing fancy - an
        earlier version bolted a weird pushed-out lower lip onto it and it
        just read as a mistake."""
        d = ImageDraw.Draw(img)
        my = HY + y
        pts = []
        for i in range(15):
            f = i / 14.0
            xx = HX - 9 + f * 18
            yy = my + math.sin(f * 6.6) * 1.9 - math.sin(f * math.pi) * 1.6
            pts.append((_x(xx), _x(yy)))
        d.line(pts, fill=INK + (255,), width=int(_x(2.2)), joint="curve")

    def _mouth_puke(self, img, y=23):
        """Mouth wide OPEN, jaw dropped - mid-heave. The vomit stream itself
        is drawn per-frame in buddy.py so it can animate."""
        my = HY + y
        mw, mh = 8.5, 9.0
        _grad_fill(img, [(HX, my - mh), (HX + mw * 0.75, my - mh * 0.6),
                         (HX + mw, my + mh * 0.05),
                         (HX + mw * 0.7, my + mh * 0.75),
                         (HX, my + mh), (HX - mw * 0.7, my + mh * 0.75),
                         (HX - mw, my + mh * 0.05),
                         (HX - mw * 0.75, my - mh * 0.6)],
                   (120, 54, 58), (68, 26, 32), outline=INK, ow=1.4)

    def _cheeks_puffed(self, img):
        """Cheeks bulging - he's holding something back. A pale, taut
        highlight on each cheek plus a swollen edge, which reads as puffed
        without changing the sprite's silhouette."""
        for sx in (HX - 26, HX + 26):
            _soft(img, (sx - 8.0, HY + 2, sx + 8.0, HY + 14),
                  (146, 168, 96), 120, 10)
            _soft(img, (sx - 5.0, HY + 3, sx + 3.0, HY + 9),
                  (206, 218, 176), 90, 7)

    def _eye_sick(self, img):
        """Miserable, feverish eyes: heavy squashed lids, dull and glazed.

        The shine is DIMMER and smaller than a healthy eye - a bright glossy
        catchlight reads as alert and well. Taking the sparkle out is most of
        what makes him look ill.
        Heavy lids by RESHAPING the eye, never a stacked lid line."""
        for ex in (HX - 16, HX + 16):
            ey = HY - 2
            hh = 4.2
            _grad_fill(img, [(ex, ey - hh), (ex + 6.6, ey - hh * 0.7),
                             (ex + 8.2, ey), (ex + 6.6, ey + hh * 0.8),
                             (ex, ey + hh * 1.05), (ex - 6.6, ey + hh * 0.8),
                             (ex - 8.2, ey), (ex - 6.6, ey - hh * 0.7)],
                       (58, 42, 34), INK)
            # dull, small, low-alpha shine - a glazed eye, not a glossy one
            _soft(img, (ex - 4.0, ey - hh * 0.35, ex - 1.6, ey + hh * 0.2),
                  WHITE, 110, 5)

    def _mouth_thermometer(self, img, y=20):
        """A thermometer clamped in the side of his mouth - the single
        clearest 'I am ILL' signal, and what separates sick (a fevered body)
        from nauseated (a queasy stomach).

        *** Drawn BIG with real detail. *** A small plain stick just reads as
        a MATCH in his mouth (Chloe). To say 'thermometer' it needs: a thick
        glass barrel, a RED MERCURY COLUMN running down its centre, tick
        marks along the scale, a highlight on the glass, and the fat red bulb
        on the end.
        Angled down-and-out from the mouth corner so it never crosses his
        nose."""
        d = ImageDraw.Draw(img)
        my = HY + y
        # small downturned mouth, gripping the stick
        d.arc([_x(HX - 9), _x(my - 2), _x(HX + 4), _x(my + 7)],
              start=200, end=340, fill=INK + (255,), width=int(_x(2.0)))

        # ---- the thermometer -----------------------------------------
        bx, by = HX + 3.0, my + 1.5        # end held in the mouth corner
        tx, ty = HX + 27.0, my + 13.0      # bulb end, out past the cheek
        dxn, dyn = tx - bx, ty - by
        ln = math.hypot(dxn, dyn)
        ux, uy = dxn / ln, dyn / ln        # along the barrel
        nx, ny = -uy, ux                   # across the barrel

        # glass barrel (thick), with a darker outline underneath it
        d.line([_x(bx), _x(by), _x(tx), _x(ty)],
               fill=(180, 178, 176, 255), width=int(_x(6.2)))
        d.line([_x(bx), _x(by), _x(tx), _x(ty)],
               fill=(248, 247, 244, 255), width=int(_x(4.6)))

        # RED MERCURY COLUMN down the centre of the barrel, running from the
        # bulb most of the way up (this is the thing that says 'thermometer')
        mx0 = bx + ux * ln * 0.30
        my0 = by + uy * ln * 0.30
        d.line([_x(mx0), _x(my0), _x(tx), _x(ty)],
               fill=(216, 54, 50, 255), width=int(_x(1.6)))

        # tick marks along the scale, on one side of the barrel
        for f in (0.34, 0.46, 0.58, 0.70):
            px0 = bx + ux * ln * f
            py0 = by + uy * ln * f
            d.line([_x(px0 + nx * 0.6), _x(py0 + ny * 0.6),
                    _x(px0 + nx * 2.1), _x(py0 + ny * 2.1)],
                   fill=(120, 122, 124, 255), width=int(_x(0.9)))

        # highlight streak along the top of the glass so it reads as GLASS
        d.line([_x(bx - nx * 1.3), _x(by - ny * 1.3),
                _x(tx - nx * 1.3 - ux * 4), _x(ty - ny * 1.3 - uy * 4)],
               fill=(255, 255, 255, 190), width=int(_x(1.1)))

        # the fat red mercury bulb on the end
        r = 4.2
        d.ellipse([_x(tx - r), _x(ty - r), _x(tx + r), _x(ty + r)],
                  fill=(214, 56, 52, 255), outline=(146, 30, 30, 255),
                  width=int(_x(1.0)))
        # tiny gloss on the bulb
        d.ellipse([_x(tx - r * 0.55), _x(ty - r * 0.62),
                   _x(tx - r * 0.05), _x(ty - r * 0.14)],
                  fill=(255, 190, 186, 220))

    def _fever_flush(self, img):
        """Hot, blotchy FEVER colour on the cheeks.

        Has to be pushed hard: Buddy already has a soft pink blush baked into
        his cheeks, so a gentle red just blends into it and reads as nothing
        (Chloe couldn't see the first version at all). This sits DEEPER, more
        SATURATED and slightly LARGER than the base blush, with a couple of
        hot blotches on top, so he clearly looks like he's burning up.
        Sits a little higher than the base blush so it isn't perfectly
        hidden behind it."""
        for sx in (HX - 25, HX + 25):
            # broad hot wash
            _soft(img, (sx - 10.0, HY + 1, sx + 10.0, HY + 13),
                  (206, 58, 54), 165, 11)
            # denser core
            _soft(img, (sx - 6.5, HY + 2, sx + 6.5, HY + 10),
                  (198, 44, 44), 150, 8)
            # a couple of hot blotches so it isn't a flat disc
            _soft(img, (sx - 7.0, HY + 0, sx - 2.0, HY + 4),
                  (208, 62, 58), 130, 5)
            _soft(img, (sx + 2.5, HY + 5, sx + 8.0, HY + 10),
                  (208, 62, 58), 120, 5)

    def _eye_vacant(self, img):
        """Blissed-out, VACANT eyes - heavy-lidded and not focused on
        anything. The lights are on but nobody's home.

        Two things make it read as vacant rather than merely sleepy:
        (1) the eyes are squashed but NOT equally - the lids sit at slightly
            different heights, which reads as slack/dopey rather than tired;
        (2) the shines are SMALL and pushed to different spots, so the eyes
            don't converge on a point - an unfocused stare.
        Heavy lids come from RESHAPING the eye, never from stacking a lid
        line on it (that reads as a second eyebrow)."""
        for i, ex in enumerate((HX - 16, HX + 16)):
            ey = HY - 2
            hh = 4.4 if i == 0 else 3.8      # deliberately uneven
            _grad_fill(img, [(ex, ey - hh), (ex + 6.8, ey - hh * 0.7),
                             (ex + 8.4, ey), (ex + 6.8, ey + hh * 0.8),
                             (ex, ey + hh * 1.05), (ex - 6.8, ey + hh * 0.8),
                             (ex - 8.4, ey), (ex - 6.8, ey - hh * 0.7)],
                       (58, 42, 34), INK)
            # small shines, offset differently per eye -> not converging
            sx = ex - 4.4 if i == 0 else ex - 1.4
            _soft(img, (sx, ey - hh * 0.5, sx + 3.0, ey + hh * 0.25),
                  WHITE, 180, 5)

    def _mouth_slack(self, img, y=21):
        """Mouth hanging open and SLACK - not a smile, not an 'o'. A soft
        lopsided opening with the jaw loose, sagging a little to one side.
        This is the 'wanting' mouth (drooling), as opposed to yummy's active
        tasting mouth."""
        d = ImageDraw.Draw(img)
        my = HY + y
        pts = [(HX - 7.5, my - 3.2), (HX - 2.5, my - 4.4),
               (HX + 4.0, my - 3.8), (HX + 8.5, my - 1.6),
               (HX + 8.0, my + 3.6), (HX + 2.0, my + 6.0),
               (HX - 4.5, my + 5.2), (HX - 8.0, my + 1.4)]
        _grad_fill(img, pts, (108, 48, 54), (68, 26, 32),
                   outline=INK, ow=1.4)
        # slack lower lip catching the light
        d.arc([_x(HX - 7), _x(my + 1), _x(HX + 7), _x(my + 7)],
              start=20, end=160, fill=(196, 132, 128, 190),
              width=int(_x(1.2)))

    def _eye_downcast(self, img):
        """Heavy-lidded eyes CAST DOWNWARD - looking down and inward, not
        meeting your gaze. The signature of pensive/thoughtful melancholy.

        Built as a SHAPE, not a paint-over: the eye is a squashed bead sunk
        LOW in its socket with its shine pushed to the bottom. (Never fake a
        lid with a skin-coloured fill over the muzzle - see the zany and
        skeptical notes.)

        NO LID LINE is drawn on the eye. An earlier pass added a heavy INK
        line across the top of each eye AND kept the brows above it - the two
        together read as DOUBLE EYEBROWS (the same bug Chloe caught on
        smirk). The squashed shape alone carries the heavy-lidded look; the
        real brows sit above and do the rest.

        Distinct from `sleepy` (eyes nearly shut, drifting off) and from the
        unamused/deadpan set (lazily half-open but looking SIDEWAYS). Here he
        is awake and thinking, but looking DOWN."""
        for ex in (HX - 16, HX + 16):
            ey = HY - 1
            # squashed eye, sitting low
            _grad_fill(img, [(ex, ey - 4.2), (ex + 6.6, ey - 2.8),
                             (ex + 8.2, ey + 0.6), (ex + 6.4, ey + 4.0),
                             (ex, ey + 5.2), (ex - 6.4, ey + 4.0),
                             (ex - 8.2, ey + 0.6), (ex - 6.6, ey - 2.8)],
                       (58, 42, 34), INK)
            # the shine sits LOW too - a highlight up top would read as
            # looking up, which kills the downcast feel
            _soft(img, (ex - 4.6, ey + 0.6, ex - 1.0, ey + 3.4),
                  WHITE, 190, 6)

    def _eye_closed_line(self, img):
        """Eyes closed as simple straight HORIZONTAL LINES. No curve, no
        lashes - just shut. (Chloe's spec for relieved: the curved lids and
        lash flicks were fussy; plain lines read cleaner and calmer.)"""
        d = ImageDraw.Draw(img)
        for ex in (HX - 16, HX + 16):
            d.line([_x(ex - 8), _x(HY - 2), _x(ex + 8), _x(HY - 2)],
                   fill=INK + (255,), width=int(_x(2.4)))

    def _eye_closed_cup(self, img):
        """Gentle content squint (opens upward, relaxed) - softer than
        the delighted caret."""
        d = ImageDraw.Draw(img)
        for ex in (HX - 16, HX + 16):
            d.arc([_x(ex - 7.5), _x(HY - 8), _x(ex + 7.5), _x(HY + 3)],
                  start=20, end=160, fill=INK + (255,), width=int(_x(2.4)))

    def _eye_wink(self, img, big_shine=False):
        """Right eye (screen) winks shut, left stays glossy open."""
        r = 9.5 if big_shine else 8.5
        self._glossy_eyes_one(img, HX - 16, r)
        d = ImageDraw.Draw(img)
        d.line([_x(HX + 8), _x(HY - 4), _x(HX + 24), _x(HY - 4)],
               fill=INK + (255,), width=int(_x(2.6)))

    def _eye_wink_chevron(self, img):
        """Playful wink: the open (screen-left) eye stays a bright glossy
        bead; the winking (screen-right) eye is a chevron '<' with its
        POINT toward the INSIDE of the face (the nose) and the wider OPEN
        side toward the OUTSIDE (the ear) - so it reads cheeky like the
        playful emoji, not a flat sleepy line."""
        self._glossy_eyes_one(img, HX - 16, 9.0)      # bright round eye
        d = ImageDraw.Draw(img)
        d.line([_x(HX + 22), _x(HY - 9), _x(HX + 8), _x(HY - 4),
                _x(HX + 22), _x(HY + 1)], fill=INK + (255,),
               width=int(_x(2.6)), joint="curve")

    def _eye_soft_closed(self, img):
        """BOTH eyes gently shut - a soft, shallow relaxed curve (a
        content eye-shut), gentler and more horizontal than the delighted
        cup and NOT the flat hard 'press' of the blink line. Used for
        kiss (blowing a kiss with eyes softly closed)."""
        d = ImageDraw.Draw(img)
        for ex in (HX - 16, HX + 16):
            d.arc([_x(ex - 8), _x(HY - 6), _x(ex + 8), _x(HY + 2)],
                  start=18, end=162, fill=INK + (255,), width=int(_x(2.5)))

    def _eye_zany_drunk(self, img):
        """Goofy-drunk asymmetry: the LEFT eye is blown wide and bulging,
        riding high in its socket; the RIGHT is squinted almost shut under
        a heavy droopy lid, sitting low. Mismatch is the whole point - it
        sells 'zany' far better than a literal spiral, and it stays clearly
        distinct from `silly` (crossed googly beads) and `dizzy` (spirals).
        The squint is a stroked arc, not a painted lid (see note below)."""
        # LEFT: big bulging eye, pushed UP and OUT of alignment. Drawn on a
        # cream eye-white so it genuinely bulges instead of just being a
        # bigger bead.
        lx, ly = HX - 16, HY - 7
        _grad_fill(img, [(lx, ly - 12), (lx + 10, ly - 8), (lx + 12, ly),
                         (lx + 10, ly + 8), (lx, ly + 12), (lx - 10, ly + 8),
                         (lx - 12, ly), (lx - 10, ly - 8)],
                   (255, 252, 246), (226, 214, 202), outline=INK, ow=1.2)
        # pupil sits off-center (up and inward) - the "not tracking" look
        self._glossy_eyes_one(img, lx + 2, r=6.2, ey=ly - 2)
        # RIGHT: squeezed shut into a squinty arc, sitting LOW and small.
        # NOTE: an earlier pass painted a skin-toned lid POLYGON over an
        # open eye - it rendered as a flat pale rectangle floating on the
        # muzzle (its gradient doesn't match the face's shading), reading as
        # a pasted sticker. Drawing the squint as a stroked ARC instead
        # keeps it inside the face with no patch. General rule: don't fake
        # a lid with a skin-colored fill over the muzzle.
        rx, ry = HX + 16, HY - 2
        d = ImageDraw.Draw(img)
        d.arc([_x(rx - 8), _x(ry - 5), _x(rx + 8), _x(ry + 6)],
              start=200, end=340, fill=INK + (255,), width=int(_x(2.6)))
        # a soft under-eye bag below the squint (adds the woozy read)
        _soft(img, (rx - 7, ry + 5, rx + 7, ry + 9), (214, 150, 120), 80, 8)

    def _glossy_eyes_one(self, img, ex, r=8.5, ey=None):
        ey = HY - 4 if ey is None else ey
        _grad_fill(img, [(ex, ey - r), (ex + r * 0.8, ey - r * 0.55),
                         (ex + r, ey), (ex + r * 0.8, ey + r * 0.6),
                         (ex, ey + r), (ex - r * 0.8, ey + r * 0.6),
                         (ex - r, ey), (ex - r * 0.8, ey - r * 0.55)],
                   (58, 42, 34), INK)
        _soft(img, (ex - 5.5, ey - 6.5, ex - 0.5, ey - 1.5), WHITE, 245, 8)
        _soft(img, (ex + 2, ey + 2, ex + 5.5, ey + 5.5), WHITE, 118, 6)

    def _eye_half_lid(self, img, droop=0.4, offset_y=0.0):
        """Heavy-lidded eyes: a skin-toned lid covers the top portion."""
        self._glossy_eyes(img, ey=HY - 4 + offset_y)
        for ex in (HX - 16, HX + 16):
            top = HY - 12 + offset_y
            bot = HY - 12 + offset_y + 18 * droop
            _grad_fill(img, [(ex - 9, top), (ex, top - 1), (ex + 9, top),
                             (ex + 9, bot), (ex, bot + 1), (ex - 9, bot)],
                       SKIN_TOP, SKIN_BOT)

    def _eye_sad(self, img):
        """Sad eyes that are STILL LOOKING AT YOU (pensive's are cast down).

        *** The heaviness is built INTO THE EYE SHAPE - the upper contour is
        pressed down and the lower lid pushed up - and NOT by painting a lid
        on top of a finished eye the way _eye_half_lid does. *** Painting a
        lid while a brow sits above it IS the double-eyebrow bug (smirk,
        pensive). We are not doing it a third time.
        """
        for ex in (HX - 16, HX + 16):
            ey = HY - 4
            _grad_fill(img, [(ex, ey - 5.4),
                             (ex + 5.6, ey - 4.2), (ex + 7.2, ey - 0.6),
                             (ex + 5.8, ey + 4.2), (ex, ey + 5.6),
                             (ex - 5.8, ey + 4.2), (ex - 7.2, ey - 0.6),
                             (ex - 5.6, ey - 4.2)],
                       (58, 42, 34), INK)
            # a big wet catchlight sitting HIGH: it's what keeps him looking
            # UP at you even though the lid is heavy
            _soft(img, (ex - 5.0, ey - 4.6, ex - 0.4, ey - 0.2), WHITE, 240, 8)
            _soft(img, (ex + 2.2, ey + 1.8, ex + 5.2, ey + 4.6), WHITE, 110, 6)

    def _brow_sad(self, img):
        """Grief brows: inner ends hoisted HIGH and pulled TOGETHER, outer
        ends dropping away. _brow_worried is the same basic idea but STRAIGHT,
        shallower and further apart - that reads as apprehension. This one is
        CURVED, steeper and pinched, which reads as hurt."""
        d = ImageDraw.Draw(img)
        exl, exr, ey = HX - 16, HX + 16, HY - 4
        for sx, ex in ((-1, exl), (1, exr)):
            # *** SIGNS MATTER. *** sx = -1 is his LEFT eye, so "outer" is
            # ex + sx*9 (AWAY from centre) and "inner" is ex - sx*6 (TOWARD
            # centre). Getting these backwards puts the HIGH end on the
            # outside, which is the ANGRY brow - and that is exactly what it
            # rendered as on the first pass. Compare _brow_worried, which
            # gets it right: left brow runs (exl-9, low) -> (exl+8, high).
            ox, oy = ex + sx * 9, ey - 9        # outer end, LOW
            mx, my = ex + sx * 2, ey - 15       # the bend
            ix, iy = ex - sx * 6, ey - 17       # inner end, HIGH + pulled in
            d.line([_x(ox), _x(oy), _x(mx), _x(my), _x(ix), _x(iy)],
                   fill=INK + (255,), width=int(_x(2.6)), joint="curve")

    def _mouth_sad(self, img):
        """Small, CLOSED, pressed frown - corners pulled down AND IN, so the
        whole mouth is narrower than pensive's soft wide downturn
        (_mouth_flat(curve=-1, y=20)). Very slightly off-centre on purpose: a
        perfectly symmetric frown reads as a cartoon mask, not a feeling."""
        d = ImageDraw.Draw(img)
        my = HY + 19
        d.line([_x(HX - 6.5), _x(my + 1.6), _x(HX - 3.0), _x(my - 1.4),
                _x(HX + 0.4), _x(my - 2.2), _x(HX + 3.8), _x(my - 1.2),
                _x(HX + 6.8), _x(my + 2.0)],
               fill=INK + (255,), width=int(_x(2.2)), joint="curve")

    def _eye_heart(self, img):
        d = ImageDraw.Draw(img)
        for ex in (HX - 16, HX + 16):
            ey = HY - 4
            d.ellipse([_x(ex - 9), _x(ey - 8), _x(ex + 1), _x(ey + 2)],
                      fill=RED + (255,))
            d.ellipse([_x(ex - 1), _x(ey - 8), _x(ex + 9), _x(ey + 2)],
                      fill=RED + (255,))
            d.polygon([_x(ex - 8.4), _x(ey - 1), _x(ex), _x(ey + 10),
                       _x(ex + 8.4), _x(ey - 1)], fill=RED + (255,))

    def _eye_spiral(self, img, fx=0, which=("L", "R")):
        d = ImageDraw.Draw(img)
        sides = []
        if "L" in which:
            sides.append(HX - 16 + fx)
        if "R" in which:
            sides.append(HX + 16 + fx)
        for ex in sides:
            pts = []
            for i in range(26):
                t = i / 25.0
                ang = t * 3.4 * math.pi
                rr = 1.2 + t * 6.2
                pts.append((_x(ex + math.cos(ang) * rr),
                           _x(HY - 4 + math.sin(ang) * rr)))
            d.line(pts, fill=INK + (255,), width=int(_x(1.6)),
                  joint="curve")

    def _eye_wide_shock(self, img):
        for ex in (HX - 16, HX + 16):
            _soft(img, (ex - 8.5, HY - 12, ex + 8.5, HY + 5), WHITE,
                 235, 10)
            self._glossy_eyes_one(img, ex, r=6.0)

    def _eye_startled_tall(self, img):
        """Terrified eyes: the beads are STRETCHED tall ('stretched in
        terror'). Width is kept at the idle eye width (rx = idle r, never
        skinnier than idle); height is ~2x idle so they read as bug-eyed
        with fright. A faint white glow behind adds a little pop."""
        ey = HY - 4
        rx, ry = 8.5, 16.0
        for ex in (HX - 16, HX + 16):
            _soft(img, (ex - rx, ey - ry, ex + rx, ey + ry * 0.5),
                  WHITE, 150, 12)
            _grad_fill(img, [(ex, ey - ry), (ex + rx * 0.82, ey - ry * 0.6),
                             (ex + rx, ey), (ex + rx * 0.82, ey + ry * 0.55),
                             (ex, ey + ry), (ex - rx * 0.82, ey + ry * 0.55),
                             (ex - rx, ey), (ex - rx * 0.82, ey - ry * 0.6)],
                       (58, 42, 34), INK)
            _soft(img, (ex - 5, ey - 10, ex - 0.5, ey - 3), WHITE, 245, 8)

    def _eye_averted(self, img):
        """MORTIFIED eyes: cast DOWN and hard to ONE SIDE. He is avoiding YOU
        specifically - a single committed avert, not awkward's shifty
        back-and-forth flicking, and not pensive's straight-down rumination.
        Narrowed by RESHAPING the eye (never by painting a lid over a finished
        eye - that's the double-eyebrow bug)."""
        fx = -5.0                 # pushed to HIS left, away from the viewer
        for ex in (HX - 16, HX + 16):
            cx, ey = ex + fx, HY - 1.5
            _grad_fill(img, [(cx, ey - 4.6), (cx + 5.2, ey - 3.6),
                             (cx + 6.6, ey - 0.4), (cx + 5.4, ey + 3.8),
                             (cx, ey + 4.8), (cx - 5.4, ey + 3.8),
                             (cx - 6.6, ey - 0.4), (cx - 5.2, ey - 3.6)],
                       (58, 42, 34), INK)
            _soft(img, (cx - 4.4, ey - 3.8, cx - 0.6, ey - 0.4), WHITE, 210, 6)

    def _brow_embarrassed(self, img):
        """Brows squeezed DOWN CLOSE to the eyes and PINCHED TOGETHER - a
        tight little cringe. All three brow SHAPES are already spoken for:
        inner-up = worried/sad, outer-up = angry, high-and-level = surprised.
        So this one separates on POSITION instead: same inner-up tilt, but
        LOW, SHORT and squeezed inward. 'Please stop looking at me.'"""
        d = ImageDraw.Draw(img)
        exl, exr, ey = HX - 16, HX + 16, HY - 4
        d.line([_x(exl - 6), _x(ey - 8), _x(exl + 7), _x(ey - 12)],
               fill=INK + (255,), width=int(_x(2.5)))
        d.line([_x(exr - 7), _x(ey - 12), _x(exr + 6), _x(ey - 8)],
               fill=INK + (255,), width=int(_x(2.5)))

    def _mouth_embarrassed(self, img):
        """A tiny, tight, pained line, pulled OFF-CENTRE toward the side he's
        turning away from, with one corner tucked. Not sad_simple's pressed
        frown (that's sorrow, and it's symmetric-ish) and not awkward's wide
        flat expressionless mouth."""
        d = ImageDraw.Draw(img)
        my = HY + 19
        d.line([_x(HX - 7.5), _x(my + 0.6), _x(HX - 3.5), _x(my - 1.0),
                _x(HX + 0.5), _x(my - 0.6), _x(HX + 4.5), _x(my + 1.8)],
               fill=INK + (255,), width=int(_x(2.1)), joint="curve")

    def _eye_plead(self, img, k=0.0):
        """THE PUPPY EYES. The biggest in the whole set (r 11.8 vs a normal
        ~7.5), and the single most identifying cue for this emote.

        *** SPARKLE MUST BE CRISP. *** First pass built the catchlights out of
        _soft (blurred) blobs and Chloe said the sparkle "doesn't land" - she
        was right. A blurred highlight reads as HAZE or a smudge on the eye.
        Sparkle is a HARD-EDGED bright shape with a soft glow BEHIND it. So:
        solid white ellipses, plus a four-point STAR glint that twinkles.

        `k` 0..1 (cyclic) drives the twinkle: the star swells and shrinks and
        the wet rim brightens.
        *** THE WELL NEVER SPILLS. *** All falling water is reserved for
        crying / sobbing - welling-but-never-falling is what makes this a
        PERFORMANCE rather than grief.
        """
        d = ImageDraw.Draw(img)
        ey = HY - 3
        r = 11.8
        tw = 0.55 + 0.45 * math.sin(k * 2 * math.pi)      # the twinkle
        for ex in (HX - 16, HX + 16):
            _grad_fill(img, [(ex, ey - r), (ex + r * 0.82, ey - r * 0.6),
                             (ex + r, ey), (ex + r * 0.82, ey + r * 0.62),
                             (ex, ey + r), (ex - r * 0.82, ey + r * 0.62),
                             (ex - r, ey), (ex - r * 0.82, ey - r * 0.6)],
                       (62, 45, 36), INK)
            # THE WET RIM: a bright meniscus banked along the lower lid. It
            # WELLS and never falls.
            _soft(img, (ex - r * 0.78, ey + r * 0.34,
                        ex + r * 0.78, ey + r * 0.99),
                  (206, 236, 250), 150 + int(70 * tw), 4)

            # PRIMARY CATCHLIGHT - big, SOLID, hard-edged. The sparkle.
            _soft(img, (ex - 8.4, ey - 9.4, ex - 1.0, ey - 2.0),
                  WHITE, 90, 7)                     # glow BEHIND it
            d.ellipse([_x(ex - 7.6), _x(ey - 8.6), _x(ex - 1.8), _x(ey - 2.8)],
                      fill=WHITE + (255,))
            # SECONDARY - smaller, opposite side, also solid
            d.ellipse([_x(ex + 2.6), _x(ey + 1.6), _x(ex + 6.4), _x(ey + 5.4)],
                      fill=WHITE + (235,))

            # THE TWINKLE: a four-point star glint that swells and shrinks.
            # This is the bit that actually reads as "sparkling".
            sx0, sy0 = ex + 5.4, ey - 6.4
            L = 2.2 + 3.4 * tw                      # long axis
            Wd = 0.75 + 0.95 * tw                   # waist
            d.polygon([(_x(sx0), _x(sy0 - L)), (_x(sx0 + Wd), _x(sy0 - Wd)),
                       (_x(sx0 + L), _x(sy0)), (_x(sx0 + Wd), _x(sy0 + Wd)),
                       (_x(sx0), _x(sy0 + L)), (_x(sx0 - Wd), _x(sy0 + Wd)),
                       (_x(sx0 - L), _x(sy0)), (_x(sx0 - Wd), _x(sy0 - Wd))],
                      fill=WHITE + (int(160 + 95 * tw),))

    def _brow_plead(self, img):
        """Inner ends hoisted VERY high and strongly arched. This IS an
        inner-raise, like worried and sad; the brow is NOT the separator for
        pleading - the enormous sparkling eyes under it are. Pushed up out of
        their way."""
        d = ImageDraw.Draw(img)
        ey = HY - 4
        for sx, ex in ((-1, HX - 16), (1, HX + 16)):
            ox, oy = ex + sx * 10, ey - 14
            mx, my = ex + sx * 3, ey - 20
            ix, iy = ex - sx * 7, ey - 21
            d.line([_x(ox), _x(oy), _x(mx), _x(my), _x(ix), _x(iy)],
                   fill=INK + (255,), width=int(_x(2.4)), joint="curve")

    def _mouth_plead(self, img, k=0.0):
        """A small HOPEFUL SMILE with a hopeful wobble in it.

        *** A SMILE, NOT A FROWN. *** The first pass gave him a quivering POUT
        and Chloe called it: a frown just reads as SAD. Pleading is not sadness
        - he is ASKING, and he is trying to CHARM you into a yes. That's a
        hopeful little upturned mouth. This one correction is what turns the
        emote from 'miserable' into 'please please please'.
        Deliberately not _mouth_wavy either - that squiggle is reserved for
        scared / anxious."""
        d = ImageDraw.Draw(img)
        my = HY + 19
        q = math.sin(k * 2 * math.pi) * 0.7        # the hopeful wobble
        d.line([_x(HX - 6.5), _x(my - 1.0 + q), _x(HX - 2.6), _x(my + 1.9),
                _x(HX + 2.6), _x(my + 1.9), _x(HX + 6.5), _x(my - 1.0 - q)],
               fill=INK + (255,), width=int(_x(2.2)), joint="curve")

    def _eye_scared(self, img, jx=0.0, jy=0.0):
        """SCARED eyes: wide dark beads that JITTER. `jx`,`jy` shove the whole
        eye a couple of px, and buddy.py cycles them fast, so the eyes visibly
        VIBRATE with fear. Nothing else in the 65 has shaking eyes.

        *** THE EYE SHAPE HAD NOWHERE ELSE TO GO. *** Everything nearby is
        already claimed by a CONFIRMED emote:
            _eye_wide_shock    = mind_blown (dark bead + a big white GLOW).
            _eye_startled_tall = terrified  (bead STRETCHED tall).
            visible SCLERA     = surprised  (the ONLY emote showing eye-white).
        So scared separates on MOTION instead of shape: same round bead, but it
        will not hold still. Fear you can see him failing to suppress.
        """
        ey = HY - 4
        r = 9.2
        for ex in (HX - 16, HX + 16):
            cx, cy = ex + jx, ey + jy
            _grad_fill(img, [(cx, cy - r), (cx + r * 0.84, cy - r * 0.6),
                             (cx + r, cy), (cx + r * 0.84, cy + r * 0.6),
                             (cx, cy + r), (cx - r * 0.84, cy + r * 0.6),
                             (cx - r, cy), (cx - r * 0.84, cy - r * 0.6)],
                       (58, 42, 34), INK)
            # a small hard highlight - it shakes WITH the eye, which is what
            # makes the vibration legible instead of just a blur
            _soft(img, (cx - 4.6, cy - 5.4, cx - 1.2, cy - 2.0), WHITE, 225, 4)

    def _brow_scared(self, img):
        """A hard, STEEP, straight inner-raise - strained rather than sad.
        The brow is not the separator here (the jittering eyes are), but it
        still has to stay off its neighbours:
            pleading    = a very HIGH, ROUNDED arch.
            embarrassed = LOW, short, PINCHED.
            terrified   = _brow_worried lifted 9.
        This one is a steep straight DIAGONAL, tight over the eye - tension,
        not sorrow."""
        d = ImageDraw.Draw(img)
        ey = HY - 4
        for sx, ex in ((-1, HX - 16), (1, HX + 16)):
            d.line([_x(ex + sx * 10), _x(ey - 11), _x(ex - sx * 8), _x(ey - 19)],
                   fill=INK + (255,), width=int(_x(2.6)))

    def _mouth_scared(self, img, k=0.0):
        """A tense open fear-GRIMACE: a wide downturned open mouth with the
        corners dragged back and down. Not _mouth_gape (sobbing / mind_blown -
        a slack dropped jaw) and deliberately NOT _mouth_wavy: that wobbling
        squiggle is a WORRY shape and it is reserved for anxious, which is the
        very next emote."""
        d = ImageDraw.Draw(img)
        my = HY + 20
        w, h = 8.0, 5.4 + 0.8 * math.sin(k * 2 * math.pi)
        cav = [(HX - w, my - 2.0), (HX - w * 0.5, my - 3.4),
               (HX + w * 0.5, my - 3.4), (HX + w, my - 2.0),
               (HX + w * 0.72, my + h), (HX, my + h * 1.25),
               (HX - w * 0.72, my + h)]
        _grad_fill(img, cav, (108, 52, 56), (58, 26, 30),
                   outline=INK, ow=1.4)

    def _eye_startled_round(self, img, k=1.0):
        """SURPRISED eyes. `k` 0..1 = how startled (0 = residual 'oh', 1 = the
        peak of the jump).

        *** THE WHITE IS THE WHOLE POINT. *** Every neighbouring emote's eyes
        are SOLID DARK BEADS:
            _eye_wide_shock   (mind_blown, and the baseline surprised) = a dark
                              bead with a soft white GLOW behind it.
            _eye_startled_tall(terrified) = a dark bead STRETCHED tall.
        This is the only one in the 65 where you actually see SCLERA - a big
        white ring with the pupil shrunk to a pinprick inside it. That
        pinprick-in-white is the universal cartoon startle, and it is what
        makes surprised unmistakable next to the other two at pet scale.
        """
        ey = HY - 4
        r = 7.6 + 3.4 * k               # the eye OPENS as he startles
        pr = 4.4 - 2.0 * k              # ...and the PUPIL shrinks
        for ex in (HX - 16, HX + 16):
            _soft(img, (ex - r - 2, ey - r - 2, ex + r + 2, ey + r + 2),
                  WHITE, 120, 10)
            # white of the eye
            _grad_fill(img, [(ex, ey - r), (ex + r * 0.78, ey - r * 0.72),
                             (ex + r, ey), (ex + r * 0.78, ey + r * 0.72),
                             (ex, ey + r), (ex - r * 0.78, ey + r * 0.72),
                             (ex - r, ey), (ex - r * 0.78, ey - r * 0.72)],
                       (255, 253, 250), (232, 226, 220), outline=INK, ow=1.3)
            # the pinprick pupil, riding slightly high
            d = ImageDraw.Draw(img)
            py = ey - 0.8 * k
            d.ellipse([_x(ex - pr), _x(py - pr), _x(ex + pr), _x(py + pr)],
                      fill=(46, 33, 25, 255))
            _soft(img, (ex - pr, py - pr, ex - pr * 0.15, py - pr * 0.15),
                  WHITE, 230, 5)

    def _brow_shot_up(self, img, k=1.0):
        """SURPRISED brows: both shot STRAIGHT UP, LEVEL and evenly arched.

        *** SURPRISE RAISES BOTH BROWS EQUALLY. *** That is what separates it
        from the entire inner-raised family - _brow_worried (scared, anxious,
        pleading, terrified) and _brow_sad (sad_simple) both hoist the INNER
        ends only, which reads as fear or hurt. A level, symmetric, high arch
        reads as pure "!".
        """
        d = ImageDraw.Draw(img)
        ey = HY - 4 - 6.0 * k           # they RIDE UP as he startles
        for sx, ex in ((-1, HX - 16), (1, HX + 16)):
            d.arc([_x(ex - 9), _x(ey - 20), _x(ex + 9), _x(ey - 6)],
                  start=200, end=340, fill=INK + (255,),
                  width=int(_x(2.6)))

    def _mouth_gasp(self, img, k=1.0):
        """The round O. It POPS OPEN and then shrinks back to a small 'oh'.
        A circle, not mind_blown's slack dropped-jaw _mouth_gape - a gape is
        overwhelm, an O is a clean gasp."""
        d = ImageDraw.Draw(img)
        r = 2.8 + 4.6 * k
        my = HY + 18 + 1.5 * k
        d.ellipse([_x(HX - r * 0.86), _x(my - r), _x(HX + r * 0.86),
                   _x(my + r)],
                  fill=MOUTH_IN + (255,), outline=INK + (255,),
                  width=int(_x(2.0)))

    def _brow_worried(self, img, lift=0):
        """Worried '/ \\' brows (inner ends raised). `lift` slides BOTH
        brows straight up by that many px - used by terrified, whose
        eyes are stretched so tall the default brows would sit on them
        (riding up over the helmet rim is fine / intentionally cartoony).
        Default lift=0 leaves every other emote's brows untouched."""
        d = ImageDraw.Draw(img)
        exl, exr, ey = HX - 16, HX + 16, HY - 4 - lift
        d.line([_x(exl - 9), _x(ey - 10), _x(exl + 8), _x(ey - 16)],
              fill=INK + (255,), width=int(_x(2.6)))
        d.line([_x(exr - 8), _x(ey - 16), _x(exr + 9), _x(ey - 10)],
              fill=INK + (255,), width=int(_x(2.6)))

    def _brow_awkward(self, img):
        """Asymmetric 'huh?' brows for awkward: screen-left raised high
        and gently arched, screen-right low and flat - the quizzical,
        uncertain look."""
        d = ImageDraw.Draw(img)
        exl, exr, ey = HX - 16, HX + 16, HY - 4
        d.arc([_x(exl - 8), _x(ey - 21), _x(exl + 8), _x(ey - 11)],
              start=200, end=340, fill=INK + (255,), width=int(_x(2.6)))
        d.line([_x(exr - 8), _x(ey - 11), _x(exr + 9), _x(ey - 12)],
               fill=INK + (255,), width=int(_x(2.6)))

    def _brow_skeptical(self, img):
        """Hard skeptical asymmetry: RIGHT brow arched HIGH, LEFT brow pushed
        DOWN and angled inward. _brow_cocked raises one brow but leaves the
        other flat/neutral, which reads as mild curiosity. Doubt comes from
        the OPPOSITION - one brow up, one brow down - so the two disagree
        with each other. That contrast is the whole expression."""
        d = ImageDraw.Draw(img)
        # RIGHT: high, strongly arched
        d.arc([_x(HX + 5), _x(HY - 23), _x(HX + 27), _x(HY - 11)],
              start=195, end=345, fill=INK + (255,), width=int(_x(2.4)))
        # LEFT: low, tilted down toward the nose (inner end drops)
        d.line([_x(HX - 26), _x(HY - 15), _x(HX - 8), _x(HY - 10)],
               fill=INK + (255,), width=int(_x(2.6)))

    def _eye_skeptical(self, img):
        """One eye open and appraising, the other NARROWED - you scrutinize
        with one eye. The narrowed eye sits under the lowered brow.

        HOW THE SQUINT IS BUILT (this is the third attempt; the first two are
        instructive):
          (a) An INK arc drawn ABOVE the bead just floated there like a
              second eyebrow - the eye still read wide open.
          (b) A SKIN-COLORED CHORD to clip the bead's top left a visible pale
              WEDGE on the muzzle and broke the eye's outline - the same
              'pasted sticker' failure as zany's first lid.
        So: never clip or cover the eye with a face-colored fill. Instead
        draw the narrowed eye SMALL AND SQUASHED from the outset (a flatter
        ellipse), and put a heavy INK lid line directly on top of it. The eye
        is genuinely a different shape, rather than a round eye with
        something painted over it."""
        # RIGHT eye (under the raised brow): open, glossy, appraising
        self._glossy_eyes_one(img, HX + 16, r=8.5)
        # LEFT eye (under the lowered brow): a SQUASHED bead - full width but
        # only ~half height, so it is intrinsically a narrowed eye
        ex, ey = HX - 16, HY - 2
        _grad_fill(img, [(ex, ey - 4.6), (ex + 6.6, ey - 3.0),
                         (ex + 8.2, ey), (ex + 6.6, ey + 3.4),
                         (ex, ey + 4.6), (ex - 6.6, ey + 3.4),
                         (ex - 8.2, ey), (ex - 6.6, ey - 3.0)],
                   (58, 42, 34), INK)
        _soft(img, (ex - 5.0, ey - 3.4, ex - 1.0, ey - 0.6), WHITE, 210, 6)
        # heavy lid line pressing down on top of it
        d = ImageDraw.Draw(img)
        d.line([_x(ex - 9), _x(ey - 5.4), _x(ex + 8), _x(ey - 4.2)],
               fill=INK + (255,), width=int(_x(2.2)))

    def _brow_cocked(self, img):
        d = ImageDraw.Draw(img)
        d.arc([_x(HX + 6), _x(HY - 19), _x(HX + 26), _x(HY - 10)],
             start=200, end=340, fill=INK + (255,), width=int(_x(2.2)))
        d.line([_x(HX - 24), _x(HY - 13), _x(HX - 8), _x(HY - 13)],
              fill=INK + (255,), width=int(_x(2.2)))

    def _mouth_closed_smile(self, img, y=19):
        d = ImageDraw.Draw(img)
        d.arc([_x(HX - 9), _x(HY + y - 6), _x(HX + 9), _x(HY + y + 5)],
             start=15, end=165, fill=INK + (255,), width=int(_x(2.2)))

    def _mouth_neutral_oval(self, img, y=19):
        """A thin flat OVAL outline - a mouth with no emotion in it at all.
        Not a smile, not a frown, not a straight line: a closed oval that
        reads as 'nothing to say'. Shared by unamused / deadpan / speechless.
        """
        d = ImageDraw.Draw(img)
        my = HY + y
        d.ellipse([_x(HX - 8), _x(my - 2.4), _x(HX + 8), _x(my + 2.4)],
                  outline=INK + (255,), width=int(_x(1.9)))

    def _mouth_flat(self, img, y=19, w=8, curve=0):
        d = ImageDraw.Draw(img)
        if curve == 0:
            d.line([_x(HX - w), _x(HY + y), _x(HX + w), _x(HY + y)],
                  fill=INK + (255,), width=int(_x(2.4)))
        else:
            e0, e1 = (15, 165) if curve > 0 else (200, 340)
            d.arc([_x(HX - w), _x(HY + y - 5), _x(HX + w), _x(HY + y + 5)],
                 start=e0, end=e1, fill=INK + (255,), width=int(_x(2.2)))

    def _mouth_small_o(self, img, y=20, r=4.5, drool=False):
        d = ImageDraw.Draw(img)
        d.ellipse([_x(HX - r), _x(HY + y - r), _x(HX + r), _x(HY + y + r)],
                 fill=MOUTH_IN + (255,), outline=INK + (255,),
                 width=int(_x(1.3)))
        if drool:
            d.line([_x(HX + r * 0.5), _x(HY + y + r),
                   _x(HX + r * 0.5), _x(HY + y + r + 7)],
                  fill=TEAR + (220,), width=int(_x(1.8)))

    def _mouth_tongue(self, img, y=17):
        d = ImageDraw.Draw(img)
        d.ellipse([_x(HX - 10), _x(HY + y - 5), _x(HX + 10), _x(HY + y + 6)],
                 fill=MOUTH_IN + (255,), outline=INK + (255,),
                 width=int(_x(1.4)))
        d.pieslice([_x(HX - 6), _x(HY + y - 1), _x(HX + 6),
                   _x(HY + y + 10)], start=0, end=180,
                  fill=(214, 90, 100, 255), outline=INK + (255,),
                  width=int(_x(1.0)))

    def _mouth_grin_open(self, img, y=18):
        """A wide open playful grin (dark interior). The tongue is NOT
        baked here - it's drawn as an animated overlay in buddy.py so it
        can waggle (raspberry), rooted inside this opening."""
        my = HY + y
        smile = [(HX - 10, my - 3), (HX - 5, my - 1), (HX, my),
                 (HX + 5, my - 1), (HX + 10, my - 3), (HX + 7, my + 5),
                 (HX, my + 7), (HX - 7, my + 5)]
        _grad_fill(img, smile, MOUTH_IN, (86, 46, 34))
        d = ImageDraw.Draw(img)
        mpoly = _smooth(smile)
        d.line(mpoly + [mpoly[0]], fill=INK + (255,),
               width=int(_x(1.6)), joint="curve")

    def _mouth_tongue_side(self, img, y=19, side=1):
        """Goofy 'blep': an open SMILING mouth with the tongue lolling
        OUT on a real DIAGONAL, rooted INSIDE the mouth opening so it
        reads as attached (not a pasted-on tongue). side=+1 flops to
        screen-right, -1 to screen-left."""
        my = HY + y
        s = side
        # open smiling mouth (dark interior) - corners lifted, bottom
        # bulges down; wide enough to actually emit a tongue
        smile = [(HX - 10, my - 3), (HX - 5, my - 1), (HX, my),
                 (HX + 5, my - 1), (HX + 10, my - 3), (HX + 7, my + 5),
                 (HX, my + 7), (HX - 7, my + 5)]
        _grad_fill(img, smile, MOUTH_IN, (86, 46, 34))
        d = ImageDraw.Draw(img)
        mpoly = _smooth(smile)
        d.line(mpoly + [mpoly[0]], fill=INK + (255,),
               width=int(_x(1.6)), joint="curve")
        # tongue: a rounded lobe whose ROOT sits inside the mouth and
        # whose body leans out-and-down on a diagonal to one side
        tongue = [(HX - 2 * s, my + 0), (HX + 5 * s, my - 1),
                  (HX + 12 * s, my + 5), (HX + 14 * s, my + 12),
                  (HX + 9 * s, my + 15), (HX + 3 * s, my + 12),
                  (HX - 1 * s, my + 6)]
        _grad_fill(img, tongue, (236, 124, 136), (198, 78, 92))
        tp = _smooth(tongue)
        d.line(tp + [tp[0]], fill=INK + (255,),
               width=int(_x(1.2)), joint="curve")
        # crease running along the tongue's diagonal axis
        d.line([_x(HX + 4 * s), _x(my + 3), _x(HX + 10 * s), _x(my + 11)],
               fill=(176, 64, 78, 255), width=int(_x(1.1)))

    def _mouth_wavy(self, img, y=20, w=9):
        d = ImageDraw.Draw(img)
        pts = []
        for i in range(9):
            t = i / 8.0
            yy = HY + y + (2.6 if i % 2 else -2.6) * (0.4 + 0.6 * t)
            pts.append((_x(HX - w + t * w * 2), _x(yy)))
        d.line(pts, fill=INK + (255,), width=int(_x(2.2)), joint="curve")

    def _mouth_grit(self, img, y=18, w=9):
        d = ImageDraw.Draw(img)
        d.rounded_rectangle(
            [_x(HX - w), _x(HY + y - 3), _x(HX + w), _x(HY + y + 3)],
            radius=int(_x(1.2)), fill=TOOTH + (255,),
            outline=INK + (255,), width=int(_x(1.6)))
        for i in range(1, 4):
            xx = HX - w + (2 * w) * (i / 4.0)
            d.line([_x(xx), _x(HY + y - 3), _x(xx), _x(HY + y + 3)],
                  fill=(210, 198, 182, 255), width=int(_x(0.8)))

    def _mouth_gape(self, img, y=19, w=8, h=9):
        _grad_fill(img, [(HX - w, HY + y - h * 0.3),
                         (HX, HY + y - h * 0.55),
                         (HX + w, HY + y - h * 0.3),
                         (HX + w * 0.8, HY + y + h * 0.7),
                         (HX, HY + y + h), (HX - w * 0.8, HY + y + h * 0.7)],
                  MOUTH_IN, (86, 46, 34))

    def _mouth_smug(self, img, y=19):
        """A deeper, cockier one-sided smile than _mouth_smirk: one corner
        pulled up HARD and slightly out, with a small dimple crease at that
        corner. Mirrored relative to skeptical's smirk (which raises the
        other side), so the two never read as the same mouth."""
        d = ImageDraw.Draw(img)
        my = HY + y
        # A single confident curve sweeping UP to the right, drawn thick so
        # it actually reads at pet scale (a thin arc disappears into the
        # muzzle). Left end low and flat, right end hooked up high.
        d.line([_x(HX - 11), _x(my + 1.5), _x(HX - 4), _x(my + 3.0)],
               fill=INK + (255,), width=int(_x(2.6)))
        d.arc([_x(HX - 6), _x(my - 9), _x(HX + 14), _x(my + 5)],
              start=40, end=155, fill=INK + (255,), width=int(_x(2.8)))
        # dimple crease at the raised corner - the "I know something" tell
        d.arc([_x(HX + 10), _x(my - 7), _x(HX + 17), _x(my + 1)],
              start=250, end=20, fill=(190, 122, 100, 255),
              width=int(_x(1.5)))

    def _mouth_smirk(self, img, y=19, flip=False):
        """Asymmetric single-corner-raised smirk."""
        d = ImageDraw.Draw(img)
        if not flip:
            e0, e1 = 10, 150
        else:
            e0, e1 = 30, 170
        d.arc([_x(HX - 10), _x(HY + y - 6), _x(HX + 10), _x(HY + y + 5)],
             start=e0, end=e1, fill=INK + (255,), width=int(_x(2.2)))

    def _mouth_pucker(self, img, y=19):
        d = ImageDraw.Draw(img)
        d.ellipse([_x(HX - 4), _x(HY + y - 3), _x(HX + 4), _x(HY + y + 4)],
                 fill=(196, 92, 96, 255), outline=INK + (255,),
                 width=int(_x(1.1)))

    def _mouth_scribble(self, img, y=19, w=9):
        d = ImageDraw.Draw(img)
        pts = []
        for i in range(13):
            t = i / 12.0
            yy = HY + y + math.sin(t * 9) * 3.4
            pts.append((_x(HX - w + t * w * 2), _x(yy)))
        d.line(pts, fill=INK + (255,), width=int(_x(2.0)), joint="curve")

    def _build_dizzy_plate(self, rot):
        """A dizzy face with the spirals wound to rotation `rot`. Keyframed
        so the swirls actually TURN - a frozen spiral reads as a pattern, not
        as vertigo."""
        p = _new()
        self._eye_swirl(p, rot)
        self._mouth_dazed(p)
        return p

    def _build_scared_plate(self, i, n):
        """The scared face at jitter-step `i` of `n`. The eyes are SHOVED a
        couple of px on a deliberately IRREGULAR path - not a clean circle. A
        smooth orbit reads as a wobble; a ragged one reads as a TREMBLE."""
        p = _new()
        a = i / float(n) * 2 * math.pi
        # two detuned drivers so the path never repeats into a tidy circle
        jx = math.sin(a * 3.0) * 1.5 + math.sin(a * 5.0 + 1.1) * 0.7
        jy = math.cos(a * 2.0 + 0.4) * 1.2 + math.sin(a * 7.0) * 0.5
        self._eye_scared(p, jx, jy)
        self._brow_scared(p)
        self._mouth_scared(p, i / float(n))
        return p

    def _build_plead_plate(self, k):
        """The pleading face at shimmer-phase `k` (0..1, cyclic). Keyframed so
        the wet eyes actually SHIMMER and the pout QUIVERS - a frozen puppy-eye
        face is a sticker, not a plea."""
        p = _new()
        self._eye_plead(p, k)
        self._brow_plead(p)
        self._mouth_plead(p, k)
        return p

    def _build_surprised_plate(self, k):
        """A startled face at startle-level `k` (0 = the residual 'oh' he
        settles into, 1 = the peak of the jump). Keyframed because the whole
        emote is an EVENT: the eyes pop, the pupils shrink, the brows shoot up
        and the mouth opens - and then all of it RELAXES back. A frozen
        startle face is a mask, not a reaction."""
        p = _new()
        self._eye_startled_round(p, k)
        self._brow_shot_up(p, k)
        self._mouth_gasp(p, k)
        return p

    def _build_hot_plate(self, t):
        """An overheated face at pant-phase `t` (0 = mouth barely open,
        1 = gaping, tongue out furthest). Pre-rendered as keyframes so the
        pant can actually BREATHE - a frozen open mouth reads as surprise,
        not panting."""
        p = _new()
        self._heat_sheen(p)        # flush UNDER the features
        self._eye_hot(p)
        self._brow_worried(p)
        self._mouth_pant(p, t)
        return p

    def _build_nauseated_plate(self, open_mouth):
        """Two nauseated faces: mouth closed (queasy) and mouth wide open
        (mid-puke). Pre-rendered; buddy.py picks one per frame."""
        p = _new()
        self._eye_queasy(p)
        self._cheeks_puffed(p)
        self._brow_worried(p)
        if open_mouth:
            self._mouth_puke(p)
        else:
            self._mouth_queasy(p)
        return p

    def _build_nausea_mask(self):
        """GREEN-SKIN mask (1x, L). Strong over the face, a faint cast
        elsewhere.

        *** This mask is applied to the BODY/FUR ONLY - before the face plate
        is composited. *** Tinting the finished frame greened his EYES, BROWS
        and MOUTH too, which read as wrong (Chloe: the green should not cover
        them; only the skin should turn green). Those features are drawn in
        the PLATE, which goes on TOP of the tint, so they stay clean.

        The NOSE is the exception: it is baked into the BASE (see _build), so
        it sits UNDER the tint and went green along with the fur. There's no
        plate to protect it - so the mask has a HOLE punched over the nose.
        Punched AFTER the blur, so the hole isn't smeared away, then given a
        light blur of its own so the edge stays soft."""
        m = Image.new("L", (W, H), 0)
        d = ImageDraw.Draw(m)
        d.rectangle([0, 0, W, H], fill=22)          # faint all-over cast
        d.ellipse([HX - 32, HY - 28, HX + 32, HY + 32], fill=150)
        d.ellipse([HX - 26, HY - 22, HX + 26, HY + 28], fill=190)
        m = m.filter(ImageFilter.GaussianBlur(7.0))
        # knock the NOSE out of the tint (nose spans HX+/-6, HY+1..HY+10)
        hole = Image.new("L", (W, H), 255)
        ImageDraw.Draw(hole).ellipse(
            [HX - 7.5, HY - 0.5, HX + 7.5, HY + 11.5], fill=0)
        hole = hole.filter(ImageFilter.GaussianBlur(1.6))
        return ImageChops.multiply(m, hole)

    def _build_yawn_arm(self, r):
        """RIGHT arm rising to cover the yawn. `r` = 0 (resting at his side)
        to 1 (paw up near the mouth).

        *** Built by ROTATING HIS REAL ARM about the shoulder, not by
        hand-rolling a new polygon. *** An earlier pass drew a generic
        two-edge shape and it came out as a TUBE - Buddy's arms have a
        specific tapered silhouette, and a made-up polygon throws the whole
        character off. Rotating the actual _build_right_arm point list keeps
        the exact shape, and the paw lands wherever the rotation puts it.

        His arms are SHORT and can't reach his muzzle, so the paw doesn't
        arrive - it just comes UP toward the mouth and partially obscures it,
        which reads as covering the yawn (Chloe's call).

        The palm faces his mouth, so we draw the BACK of the paw: pads=False
        (no palm pad, no toe beans) but the CLAWS still show past the
        fingertips.

        NOTE: the normal frame() path composites self.right_arm. This branch
        composites THIS instead - omitting it entirely is what made one of his
        arms VANISH on an earlier pass."""
        img = _new()
        # his real resting right arm + its real paw centre
        arm0 = [(CX + 38, CY - 2), (CX + 50, CY + 6), (CX + 57, CY + 20),
                (CX + 56, CY + 33), (CX + 49, CY + 41), (CX + 41, CY + 40),
                (CX + 37, CY + 30), (CX + 38, CY + 14)]
        paw0 = (CX + 47, CY + 36)
        piv = (CX + 38, CY - 2)          # the shoulder
        # angle that swings the paw from its resting spot up toward the mouth
        a0 = math.atan2(paw0[1] - piv[1], paw0[0] - piv[0])
        tgt = (CX + 12, CY - 30)         # just right of the muzzle
        a1 = math.atan2(tgt[1] - piv[1], tgt[0] - piv[0])
        d = (a1 - a0) % (2 * math.pi)    # swing OUT and up, not through him
        th = d * r

        def rot(p):
            dx0, dy0 = p[0] - piv[0], p[1] - piv[1]
            return (piv[0] + dx0 * math.cos(th) - dy0 * math.sin(th),
                    piv[1] + dx0 * math.sin(th) + dy0 * math.cos(th))

        pts = [rot(p) for p in arm0]
        paw = rot(paw0)
        # _draw_limb's mitten is a horizontal Y-BAND - fine for a hanging
        # arm, but once this one rotates up it smears fur along the forearm.
        # Use the free-standing mitten blob instead (the hug/giggle fix).
        self._draw_limb_cuff(img, pts, paw, cuff_r=12.5)
        # BACK of the paw: claws only, no palm pad (his palm faces his mouth).
        # The claws must be drawn BIG and seated INSIDE the fur: an earlier
        # pass used r=6.5, which put the claw arc right on the mitten's RIM,
        # where the little cream nubs were half lost against the edge and
        # read as MISSING at pet scale. Nudging the paw centre down and
        # enlarging it lands the whole claw arc on the brown, where it shows.
        self._paw_detail(img, paw[0], paw[1] + 2.4, r=9.0, up=True,
                         pads=False)
        return img

    def _build_yawn_plate(self, t):
        """A yawn FACE at intensity `t` (0 = drowsy/closed, 1 = peak yawn).

        Pre-rendered as keyframes (see self.yawn_plates) because the mouth
        has to GROW and CLOSE across the yawn, and a baked plate can't
        animate. Rebuilding a 4x face every frame would be far too slow.

        NO WATERY EYES / TEARS (Chloe's call) - a yawn doesn't need them and
        they'd read as crying, which belongs to the crying/sobbing cluster.
        """
        p = _new()
        d = ImageDraw.Draw(p)
        # ---- EYES ----------------------------------------------------
        if t < 0.62:
            # heavy, drowsy - a squashed bead whose height collapses as the
            # yawn builds. (Heavy lids come from RESHAPING the eye, never
            # from stacking a lid line on it - that reads as a second brow.)
            hh = 4.6 * (1.0 - t / 0.62) + 0.9
            for ex in (HX - 16, HX + 16):
                ey = HY - 2
                _grad_fill(p, [(ex, ey - hh), (ex + 6.6, ey - hh * 0.7),
                               (ex + 8.2, ey), (ex + 6.6, ey + hh * 0.78),
                               (ex, ey + hh * 1.05), (ex - 6.6, ey + hh * 0.78),
                               (ex - 8.2, ey), (ex - 6.6, ey - hh * 0.7)],
                         (58, 42, 34), INK)
                if hh > 2.2:
                    _soft(p, (ex - 5.0, ey - hh * 0.6, ex - 1.2,
                              ey - hh * 0.05), WHITE, 200, 6)
        else:
            # SQUEEZED SHUT at the peak of the yawn - scrunched arcs
            sq = (t - 0.62) / 0.38
            for ex in (HX - 16, HX + 16):
                d.arc([_x(ex - 7.6), _x(HY - 7 - sq * 1.5),
                       _x(ex + 7.6), _x(HY + 3)],
                      start=20, end=160, fill=INK + (255,),
                      width=int(_x(2.4)))
        # ---- BROWS: lift with the yawn (the whole face stretches) -----
        for i, ex in enumerate((HX - 16, HX + 16)):
            by = HY - 13 - t * 3.0
            d.arc([_x(ex - 8), _x(by - 3), _x(ex + 8), _x(by + 6)],
                  start=200, end=340, fill=INK + (255,), width=int(_x(2.0)))
        # ---- MOUTH: the big stretch ----------------------------------
        # A yawn opens by DROPPING THE JAW - the mouth grows DOWNWARD only.
        # Growing it symmetrically around a fixed centre made the top lip
        # climb up over his NOSE at the peak.
        # Kept MODEST: an earlier pass opened it so far he looked like he was
        # unhinging his jaw like a snake. A yawn is a big-ish oval, not a
        # cavern.
        mw = 4.5 + t * 4.5
        mh = 3.0 + t * 7.5
        top = HY + 16.5                # fixed: just below the nose
        my = top + mh                  # centre slides DOWN as it opens
        _grad_fill(p, [(HX, my - mh), (HX + mw * 0.75, my - mh * 0.62),
                       (HX + mw, my), (HX + mw * 0.8, my + mh * 0.72),
                       (HX, my + mh), (HX - mw * 0.8, my + mh * 0.72),
                       (HX - mw, my), (HX - mw * 0.75, my - mh * 0.62)],
                   (128, 58, 62), (74, 28, 34), outline=INK, ow=1.4)
        if t > 0.35:
            # tongue sitting in the back of the open mouth
            tw, th = mw * 0.55, mh * 0.30
            ty = my + mh * 0.42
            _grad_fill(p, [(HX, ty - th), (HX + tw, ty),
                           (HX, ty + th), (HX - tw, ty)],
                       (214, 118, 128), (176, 82, 96))
        return p

    def _build_plates(self):
        plates = {}
        # idle: calm neutral resting face (open glossy eyes, gentle grin)
        p = _new()
        self._glossy_eyes(p)
        self._mouth_open(p)
        plates["idle"] = p

        p = _new()
        self._blink_eyes(p)
        self._mouth_open(p)
        plates["idle_blink"] = p

        p = _new()
        self._happy_eyes(p)
        self._mouth_open(p, w=13.0, h=7.5)
        plates["happy"] = p

        p = _new()
        self._happy_eyes(p)
        self._mouth_open(p, w=13.0, h=7.5)
        plates["happy_blink"] = p

        p = _new()
        d = ImageDraw.Draw(p)
        for ex in (HX - 16, HX + 16):
            ey = HY - 4
            d.ellipse([_x(ex - 9), _x(ey - 8), _x(ex + 1), _x(ey + 2)],
                      fill=RED + (255,))
            d.ellipse([_x(ex - 1), _x(ey - 8), _x(ex + 9), _x(ey + 2)],
                      fill=RED + (255,))
            d.polygon([_x(ex - 8.4), _x(ey - 1), _x(ex), _x(ey + 10),
                       _x(ex + 8.4), _x(ey - 1)], fill=RED + (255,))
        self._mouth_open(p)
        plates["love"] = p

        p = _new()
        self._glossy_eyes(p, r=9.5)
        self._mouth_open(p, w=13.0, h=7.5)
        plates["excited"] = p

        p = _new()
        self._glossy_eyes(p, r=9.5)
        self._mouth_open(p, w=8.5, h=7.0, lower=False, drop=1.0)
        plates["alert"] = p

        p = _new()
        d = ImageDraw.Draw(p)
        for ex in (HX - 16, HX + 16):
            d.arc([_x(ex - 8), _x(HY - 8), _x(ex + 8), _x(HY + 4)],
                  start=200, end=340, fill=INK + (255,), width=int(_x(2.6)))
        d.ellipse([_x(HX - 4), _x(HY + 16), _x(HX + 4), _x(HY + 24)],
                  fill=MOUTH_IN + (255,), outline=INK + (255,),
                  width=int(_x(1.2)))
        plates["sleepy"] = p

        p = _new()
        for ex in (HX - 12, HX + 20):
            _grad_fill(p, [(ex, HY - 10), (ex + 5.5, HY - 7), (ex + 6, HY - 4),
                           (ex + 5.5, HY - 1), (ex, HY + 1), (ex - 5.5, HY - 1),
                           (ex - 6, HY - 4), (ex - 5.5, HY - 7)],
                       (58, 42, 34), INK)
            _soft(p, (ex - 4, HY - 9, ex - 1, HY - 6), WHITE, 220, 6)
        d = ImageDraw.Draw(p)
        d.line([_x(HX - 7), _x(HY + 19), _x(HX + 7), _x(HY + 19)],
               fill=INK + (255,), width=int(_x(2.6)))
        plates["thinking"] = p

        p = _new()
        self._blink_eyes(p)
        d = ImageDraw.Draw(p)
        d.line([_x(HX - 7), _x(HY + 19), _x(HX + 7), _x(HY + 19)],
               fill=INK + (255,), width=int(_x(2.6)))
        plates["thinking_blink"] = p

        def worried(p2, eyes_open):
            d2 = ImageDraw.Draw(p2)
            if eyes_open:
                self._glossy_eyes(p2)
            else:
                self._blink_eyes(p2)
            exl, exr, ey = HX - 16, HX + 16, HY - 4
            # worried brows: raised at the INNER ends (/ \), the classic
            # pleading/anxious shape - outer low, inner high
            d2.line([_x(exl - 9), _x(ey - 10), _x(exl + 8), _x(ey - 16)],
                    fill=INK + (255,), width=int(_x(2.6)))
            d2.line([_x(exr - 8), _x(ey - 16), _x(exr + 9), _x(ey - 10)],
                    fill=INK + (255,), width=int(_x(2.6)))
            # frown: small downturned mouth (∩), NOT a smile arc
            d2.arc([_x(HX - 9), _x(HY + 20), _x(HX + 9), _x(HY + 32)],
                   start=200, end=340, fill=INK + (255,),
                   width=int(_x(2.6)))
            # tiny open quiver of worry under the frown
            d2.ellipse([_x(HX - 3), _x(HY + 17), _x(HX + 3), _x(HY + 22)],
                       fill=MOUTH_IN + (255,), outline=INK + (255,),
                       width=int(_x(1.0)))
            _grad_fill(p2, [(HX + 34, HY - 30), (HX + 37, HY - 26),
                            (HX + 37.5, HY - 21), (HX + 34, HY - 18),
                            (HX + 30.5, HY - 21), (HX + 31, HY - 26)],
                       (176, 224, 250), (110, 176, 220))

        p = _new()
        worried(p, True)
        plates["worried"] = p
        p = _new()
        worried(p, False)
        plates["worried_blink"] = p

        # ================================================================
        # Emoji-driven expression set (~44 new faces). Each is built by
        # combining the toolkit above: (eyes, brow, mouth, blinkable).
        # ================================================================
        E = self
        SPECS = [
            ("grinning", lambda p: E._glossy_eyes(p, r=9.0), None,
             lambda p: E._mouth_open(p, w=11.5, h=6.2, corner_lift=0.35),
             True),
            ("laughing", lambda p: E._eye_closed_cup(p), None,
             None, False),
            ("laughing_crying", lambda p: E._eye_closed_cup(p), None,
             None, False),
            ("rofl", lambda p: E._eye_closed_cup(p), None,
             None, False),
            ("adoring", lambda p: E._eye_heart(p), None,
             lambda p: E._mouth_closed_smile(p), False),
            ("kiss", lambda p: E._eye_soft_closed(p), None,
             lambda p: E._mouth_pucker(p), False),
            ("wink", lambda p: E._eye_wink(p), None,
             lambda p: E._mouth_closed_smile(p), False),
            ("bashful", lambda p: E._glossy_eyes(p), None,
             lambda p: E._mouth_closed_smile(p), False),
            ("innocent", lambda p: E._eye_closed_cup(p), None,
             lambda p: E._mouth_closed_smile(p), False),
            ("hug", lambda p: E._eye_closed_cup(p), None,
             lambda p: E._mouth_grin_open(p), False),
            # silly: eyeless plate (crossed, precessing beads are drawn
            # per-frame in buddy.py) + goofy tongue lolling out to the side
            ("silly", lambda p: None, None,
             lambda p: E._mouth_tongue_side(p), False),
            ("playful_tongue", lambda p: E._eye_wink_chevron(p), None,
             lambda p: E._mouth_grin_open(p), False),
            ("zany", lambda p: E._eye_zany_drunk(p), None,
             lambda p: E._mouth_tongue_side(p, side=-1), False),
            # yummy: contented closed-cup eyes + a closed smiling mouth.
            # The tongue is deliberately NOT baked here - the whole point of
            # yummy is the tongue SWEEPING across the lips (a lick), which
            # has to be animated per-frame in buddy.py. A baked static
            # tongue would just duplicate silly / playful_tongue.
            ("yummy", lambda p: E._eye_closed_cup(p), None,
             lambda p: E._mouth_closed_smile(p), False),
            # money_eyes: EYELESS plate - the $ eyes are drawn per-frame in
            # buddy.py so they can PULSE and ka-ching (a baked plate can't
            # scale). Mouth is a wide greedy open grin; the cash bill
            # clenched in the teeth is also a per-frame canvas accent.
            ("money_eyes", lambda p: None, None,
             lambda p: E._mouth_grin_open(p), False),
            ("giggle", lambda p: E._eye_closed_cup(p), None,
             lambda p: E._mouth_small_o(p, r=3.5), False),
            ("shush", lambda p: E._eye_half_lid(p, droop=0.4), None,
             lambda p: E._mouth_small_o(p, r=3.5), True),
            # skeptical: hard brow OPPOSITION (one up, one down) + a squint
            # under the lowered brow + a mouth pulled to one side ("hmm").
            # A slow held head-cock is added in buddy.py.
            ("skeptical", lambda p: E._eye_skeptical(p), E._brow_skeptical,
             lambda p: E._mouth_smirk(p), False),
            # smirk: EYELESS plate - the lazy half-lids are drawn per-frame in
            # buddy.py so they can do the slow brow-raise beat (a baked plate
            # can't animate). Mouth is the deeper _mouth_smug, whose raised
            # corner is MIRRORED vs skeptical's _mouth_smirk so the two don't
            # read as the same face.
            ("smirk", lambda p: None, None,
             lambda p: E._mouth_smug(p), False),
            # unamused / eye_roll / deadpan / speechless SHARE one animation
            # (Chloe's call): they're the same emotional beat, and four
            # near-identical "annoyed half-lidded bear" faces would only blur
            # together. All four get an EYELESS plate + the neutral oval
            # mouth; the lazily half-open eyes and the eye-roll are drawn
            # per-frame in buddy.py.
            ("unamused", lambda p: None, None,
             lambda p: E._mouth_neutral_oval(p), False),
            ("eye_roll", lambda p: None, None,
             lambda p: E._mouth_neutral_oval(p), False),
            ("deadpan", lambda p: None, None,
             lambda p: E._mouth_neutral_oval(p), False),
            ("speechless", lambda p: None, None,
             lambda p: E._mouth_neutral_oval(p), False),
            # awkward: eyeless plate (shifty eyes drawn per-frame in
            # buddy.py) + asymmetric 'huh?' brows + wide expressionless
            # idle-teeth mouth. Right arm scratches head; slight tilt.
            ("awkward", lambda p: None,
             E._brow_awkward, lambda p: E._mouth_awkward(p), False),
            # relieved: eyes shut as simple horizontal LINES, and the mouth
            # PURSED into a small open circle - he's blowing the breath out.
            # (A closed smile can't blow air.) The sigh + the breath streaks
            # leaving that mouth are animated in buddy.py.
            ("relieved", lambda p: E._eye_closed_line(p), None,
             lambda p: E._mouth_small_o(p, r=4.0), False),
            # pensive: thoughtful melancholy. Eyes cast DOWN (not shut like
            # sleepy, not sideways like unamused) + sad inner-raised brows +
            # a soft downturned mouth. The head SINKS and holds, in buddy.py.
            ("pensive", lambda p: E._eye_downcast(p), E._brow_worried,
             lambda p: E._mouth_flat(p, curve=-1, y=20), False),
            ("yawn", lambda p: E._eye_closed_cup(p), None,
             lambda p: E._mouth_small_o(p, r=6), False),
            # drooling: vacant blissed-out stare + a slack hanging mouth.
            # NO baked drool - the old drool=True flag drew a static straight
            # LINE under the mouth, which is just a mark on his chin. The
            # whole emote is the DRIP CYCLE (bead forms, swells, stretches,
            # falls), which is animated in buddy.py.
            ("drooling", lambda p: E._eye_vacant(p), None,
             lambda p: E._mouth_slack(p), False),
            # sick: a FEVERED BODY. Thermometer in the mouth + hot blotchy
            # fever flush + dull glazed eyes. Deliberately NOT the same as
            # nauseated (a queasy STOMACH) - the baseline had both as
            # half-lid + wavy mouth, which made them twins.
            ("sick", lambda p: (E._eye_sick(p), E._fever_flush(p)),
             E._brow_worried, lambda p: E._mouth_thermometer(p), False),
            # nauseated: a QUEASY STOMACH (vs sick = a fevered body).
            # Bracing squint + puffed cheeks + a wobbling sick mouth. The
            # GREEN TINT and the stomach HEAVE are applied in buddy.py.
            ("nauseated", lambda p: (E._eye_queasy(p), E._cheeks_puffed(p)),
             E._brow_worried, lambda p: E._mouth_queasy(p), False),
            # hot: OVERHEATED AND WILTING. Panting tongue + an even glossy
            # sweat-sheen flush (vs sick's blotchy unwell fever) + drooping
            # melted eyes. The pant keyframes, the sweat that rolls off, the
            # slow WILT and the heat shimmer all live in buddy.py.
            # (This row is the fallback face if pant is ever None.)
            ("hot", lambda p: (E._heat_sheen(p), E._eye_hot(p)),
             E._brow_worried, lambda p: E._mouth_pant(p, 0.5), False),
            ("cold", lambda p: E._glossy_eyes(p), None,
             lambda p: E._mouth_grit(p, w=6), True),
            # dizzy: SPIRAL eyes (counter-winding) + a scrambled lopsided
            # mouth. The spirals SPIN, the body describes a true circular
            # ORBIT, and stars circle overhead - all in buddy.py.
            # (This row is the fallback if spin is ever None.)
            ("dizzy", lambda p: E._eye_swirl(p, 0.0), None,
             lambda p: E._mouth_dazed(p), False),
            ("mind_blown", lambda p: E._eye_wide_shock(p), None,
             lambda p: E._mouth_gape(p, w=9, h=10), False),
            ("cool", lambda p: E._glossy_eyes(p), None,
             lambda p: E._mouth_closed_smile(p), False),
            # nerdy: MAGNIFIED eyes (thick lenses) + buck teeth. The round
            # glasses themselves are drawn per-frame in buddy.py, because they
            # SLIDE DOWN his nose and get PUSHED back up - a baked plate
            # couldn't move them. Deliberately the inverse of cool: nerdy
            # shows MORE eye than normal, cool hides the eyes completely.
            ("nerdy", lambda p: E._eye_magnified(p), None,
             lambda p: E._mouth_buck(p), True),
            # scrutinizing: one eye SQUINTS, the other bulges WIDE through the
            # monocle. The monocle itself (gold ring + chain + a glint that
            # SWEEPS) is drawn per-frame in buddy.py, along with the lean-in
            # and the slow up-and-down look-over.
            # vs nerdy: nerdy magnifies BOTH eyes and the prop is passive
            # (worn, then pushed). Here the lens is an INSTRUMENT being AIMED.
            # *** LAST FIELD MUST STAY True. *** It controls whether a
            # "<emote>_blink" plate is BUILT. scrutinizing renders through the
            # NORMAL frame() path, which looks that plate up whenever he
            # blinks - setting it False raised KeyError: 'scrutinizing_blink'
            # and dumped him back to idle. (Emotes set False elsewhere are
            # safe only because they have CUSTOM frame() branches that never
            # call _plate_key.)
            ("scrutinizing", lambda p: E._eye_scrutiny(p), E._brow_cocked,
             lambda p: E._mouth_pursed(p), True),
            # confused: his face DISAGREES WITH ITSELF (mismatched brows +
            # uneven eyes + a lopsided uncertain mouth). The head TILTS ONE
            # WAY, HOLDS, THEN REVERSES - that reversal is the signature, and
            # it's what separates it from skeptical (which tilts ONCE and
            # settles) and from thinking (which is productive). A "?" with a
            # real lifecycle fades in overhead. Both in buddy.py.
            # Blink flag True: this uses the NORMAL frame() path.
            ("confused", lambda p: E._eye_uneven(p), E._brow_confused,
             lambda p: E._mouth_uncertain(p), True),
            # sad_simple: plain, undramatic sadness. THE SIGH THAT NEVER
            # LANDS - he keeps deflating and never settles. That is what
            # separates him from `pensive` (who sinks ONCE and then HOLDS a
            # settled posture) and from `worried` (tension about what's
            # COMING, not weight from what already happened). His EARS AND
            # ANTENNAE WILT - nothing else in the 65 does that, and it is the
            # cue doing most of the work. Eyes stay ON YOU; pensive's are cast
            # down. NO TEARS - all water is reserved for crying/sobbing.
            # Blink flag TRUE so a "sad_simple_blink" plate gets built.
            # NOTE (corrected): this was NOT fixing a latent crash. A KeyError
            # only happens if an emote is in _BLINKABLE *and* its flag is
            # False - and sad_simple is NOT in _BLINKABLE. So the plate is
            # built but never looked up: HE DOES NOT BLINK WHILE SAD. That is
            # what Chloe reviewed and approved. Adding him to _BLINKABLE would
            # be safe (the plate exists) but changes a CONFIRMED emote - her
            # call, not ours.
            ("sad_simple", lambda p: E._eye_sad(p), E._brow_sad,
             lambda p: E._mouth_sad(p), True),
            # surprised: a clean STARTLE, and above all an EVENT, not a state -
            # he jumps, hangs, comes down, and holds a residual "oh". That is
            # what separates it from the sustained conditions all around it:
            # mind_blown (his head POPS OFF - overwhelm), terrified (a held
            # frozen tremble - fear), alert (a sideways body vibrate that never
            # resolves), speechless (a held blank).
            # NEW FACE - the baseline borrowed mind_blown's eyes wholesale:
            #   _eye_startled_round = the ONLY eyes in the 65 that show SCLERA,
            #     a big white with the pupil shrunk to a pinprick. mind_blown's
            #     and terrified's are both solid dark beads.
            #   _brow_shot_up = BOTH brows up, LEVEL. The baseline used
            #     _brow_worried (inner-raised), which is the fear/sadness brow
            #     shared by scared/anxious/pleading/terrified - wrong for "!".
            #   _mouth_gasp = a round O, not mind_blown's slack dropped jaw.
            # This row is only the FALLBACK if `surprise` is ever None; the
            # live emote runs on the keyframed surprised_plates.
            # Blink flag False is SAFE here: surprised is not in _BLINKABLE,
            # so no "surprised_blink" plate is ever looked up.
            ("surprised", lambda p: E._eye_startled_round(p, 1.0),
             lambda p: E._brow_shot_up(p, 1.0),
             lambda p: E._mouth_gasp(p, 1.0), False),
            # embarrassed: HE WANTS TO DISAPPEAR. That is the read, and it is
            # the one thing none of his three neighbours do - bashful is
            # ENJOYING it (paws over the eyes, smiling, pleasant pink wash),
            # hot is a physical state (heat sheen + steam + panting), and
            # awkward is just fidgeting (head-scratch + shifty eyes).
            # He SHRINKS (scale down about the feet - the inverse of
            # scrutinizing's lean-in), LEANS AWAY, and his flush CLIMBS from
            # the cheeks up. All three in buddy.py.
            # The baseline row was a blank: plain glossy eyes, NO brows at all,
            # and a tiny 3.5px o. Replaced entirely.
            # Blink flag True, and embarrassed IS in _BLINKABLE - so the plate
            # is genuinely used and he really does blink here.
            ("embarrassed", lambda p: E._eye_averted(p), E._brow_embarrassed,
             lambda p: E._mouth_embarrassed(p), True),
            # pleading: HE IS ASKING YOU FOR SOMETHING. Not admiring you
            # (adoring), not merely sad (sad_simple), not denying wrongdoing
            # (innocent) - this is a PERFORMANCE aimed at getting a yes.
            #   _eye_plead  = THE PUPPY EYES. r 11.8, the biggest in the 65
            #     (normal is ~7.5). Wet highlights that SHIMMER, a meniscus
            #     WELLING on the lower lid, and he's LOOKING UP AT YOU.
            #     *** IT NEVER SPILLS. *** All falling water is reserved for
            #     crying/sobbing. Welling-but-never-falling IS the performance.
            #   _brow_plead = a very high, strongly arched inner-raise. This is
            #     an inner-raise like worried/sad - the brow is NOT the
            #     separator here, the enormous eyes under it are.
            #   _mouth_plead= a tiny QUIVERING pout. Deliberately not
            #     _mouth_wavy: that squiggle is reserved for scared/anxious.
            # Paws held OUT, APART, PALMS UP (supplication) - kept clear of
            # adoring's clasped-at-the-cheek 'aww' paws. Both in buddy.py /
            # _build_plead_paws.
            # This row is only the FALLBACK if `plead` is ever None; the live
            # emote runs on the keyframed plead_plates.
            # Blink flag False is SAFE: pleading is not in _BLINKABLE.
            ("pleading", lambda p: E._eye_plead(p, 0.0), E._brow_plead,
             lambda p: E._mouth_plead(p, 0.0), False),
            # scared: HE CANNOT HOLD STILL. Terrified (CONFIRMED) is the exact
            # opposite emote - it has NO body motion at all, a FROZEN mask of
            # horror. Scared is fear he is still reacting to: he COWERS, and he
            # FLINCHES at irregular intervals.
            #   _eye_scared  = wide round beads that JITTER. The eye SHAPE had
            #     nowhere left to go - _eye_wide_shock is mind_blown's, the tall
            #     stretched bead is terrified's, and visible SCLERA is
            #     surprised's exclusive. So scared separates on MOTION.
            #   _brow_scared = a steep straight tense diagonal (not pleading's
            #     high round arch, not embarrassed's low pinch).
            #   _mouth_scared= a tense open fear-GRIMACE. Deliberately NOT
            #     _mouth_wavy - that squiggle is a WORRY shape, reserved for
            #     anxious, the very next emote.
            # This row is only the FALLBACK if `scare` is ever None; the live
            # emote runs on the keyframed scared_plates.
            # Blink flag False is SAFE: scared is not in _BLINKABLE.
            ("scared", lambda p: E._eye_scared(p), E._brow_scared,
             lambda p: E._mouth_scared(p, 0.0), False),
            # anxious: WORRIED IS A STATE HE IS HOLDING; ANXIOUS IS A STATE THAT
            # IS ESCALATING AND HE CANNOT STOP IT.
            # *** WORRIED (CONFIRMED) ALREADY OWNS THE SWEAT DROP *** - an
            # unnamed blue teardrop parked at (HX+34, HY-30) that never moves,
            # on a face that is otherwise glossy eyes + inner-raised brows +
            # a frown. That is anxious's baseline face almost exactly. So the
            # FACE cannot carry this emote; the LIFECYCLE does:
            #     worried = ONE static bead. Never born, never dies. FURNITURE.
            #     anxious = beads FORM, SWELL, RUN DOWN his face, and VANISH.
            # The running sweat lives in self.anx_sweat and is composited in
            # buddy.py's PIL chain, NOT in a frame() branch - which is what
            # keeps his BLINK working (see the blink flag below).
            #   _eye_anxious  = glossy but WIDER and staring (worried uses the
            #     plain _glossy_eyes; these are bigger and tenser).
            #   _brow_anxious = inner ends raised AND squeezed into a KNOT that
            #     nearly touches above the nose. All three brow SHAPES are long
            #     gone, so this separates on POSITION.
            #   _mouth_wavy   = THE WOBBLING SQUIGGLE. Reserved for exactly this
            #     emote back when scared was built - scared got a hard grimace
            #     instead, precisely so anxious could have the worry shape.
            # *** BLINK FLAG MUST STAY True. *** anxious IS in _BLINKABLE, and
            # a False flag on a _BLINKABLE emote is a guaranteed KeyError.
            ("anxious", lambda p: E._eye_anxious(p), E._brow_anxious,
             lambda p: E._mouth_wavy(p, w=6), True),
            # crying: HE IS TRYING NOT TO CRY, AND FAILING.
            # *** THE BASELINE TEARS WERE FURNITURE AND ARE NOW DELETED. ***
            # crying, sobbing AND laughing_crying (CONFIRMED) all drew the SAME
            # thing: a tkinter canvas LINE that scrolls down and wraps -
            #     drip = (ph * 30) % 26   ->   cv.create_line(...)
            # It never forms and it never falls. It TELEPORTS. The stale
            # `elif em == "crying"` accent has been removed from buddy.py, or it
            # would have double-drawn over this (the mind_blown / cool /
            # confused trap, for the fourth time).
            # Now: ONE tear at a time. It WELLS on the lid, SWELLS, BREAKS,
            # rolls down his cheek, falls away and dies. *** THEN A PAUSE. ***
            # THE PAUSE IS THE EMOTION - he holds it together, then loses it
            # again. sobbing (next) is the opposite: a continuous flood from
            # both eyes with no restraint at all.
            #   _eye_crying  = NORMAL SIZED and tired, heavy lid, water standing
            #     on the rim. Deliberately NOT pleading's r-11.8 sparkling
            #     puppy eyes whose water WELLS AND NEVER SPILLS. Pleading is
            #     asking you for something; crying has stopped asking.
            #   _brow_crying = inner ends up, outer ends DRAGGED DOWN - the face
            #     collapsing rather than tensing.
            #   _mouth_crying= pressed shut, corners hauled down, chin-quiver in
            #     the line. Shut, because sobbing gets the open wail.
            # The tear itself is drawn in buddy.py's PIL chain from ONE reusable
            # sprite (self.tear) - not a keyframe ladder. See _build_tear_sprite.
            # *** BLINK FLAG MUST STAY True. *** crying IS in _BLINKABLE, and a
            # False flag on a _BLINKABLE emote is a guaranteed KeyError.
            ("crying", lambda p: E._eye_crying(p), E._brow_crying,
             lambda p: E._mouth_crying(p), True),
            # sobbing: CRYING IS RESTRAINT THAT KEEPS LOSING; SOBBING IS
            # RESTRAINT GONE. Crying's whole identity is the PAUSE between
            # tears - the silence where he holds it together. Sobbing never
            # gets one: the flood from BOTH eyes is CONTINUOUS.
            # *** THE STALE CANVAS ACCENT HAS BEEN DELETED *** - sobbing drew
            # the same scrolling tkinter LINES as crying and laughing_crying
            # ((ph*40) % 30), pure furniture, and it would have double-drawn.
            # *** ALSO SPLIT OUT OF ITS SHARED MOTION BRANCH *** - sobbing,
            # frustrated and furious were all running one bob line. It now
            # HEAVES (11px convulsions) where crying only HITCHES (5.5px).
            #   _eye_sobbing  = eyes CLENCHED shut with squeeze-CREASES at the
            #     outer corners. The creases are the tell: laughing_crying
            #     (CONFIRMED) also has closed eyes + tears from both eyes, but
            #     its _eye_closed_cup is a HAPPY relaxed squint with a grin
            #     under it. Tension is what makes these anguish.
            #   _brow_sobbing = inner ends CRUSHED up and together.
            #     laughing_crying has NO brows at all.
            #   _mouth_sobbing= AN OPEN FROWN. A fat static CRESCENT - tips
            #     turned DOWN, belly humped UP. Chloe: "an upside down Cheeto."
            #     It does NOT animate. Two earlier versions failed: one had a
            #     TONGUE (reads as blegh/silly) and one PULSED with the heave
            #     but was too round - "an open mouth that looks like it's
            #     puckering". Fix the SHAPE, don't animate a bad one.
            # Runs on the ORDINARY static plate path - no frame() branch and no
            # keyframe ladder. The tears and the heave carry all the motion.
            # Blink flag False is SAFE: sobbing is not in _BLINKABLE (and his
            # eyes are screwed shut anyway).
            ("sobbing", lambda p: E._eye_sobbing(p), E._brow_sobbing,
             lambda p: E._mouth_sobbing(p), False),
            ("terrified", lambda p: E._eye_startled_tall(p),
             lambda p: E._brow_worried(p, lift=9),
             lambda p: E._mouth_gape(p, w=8, h=9), False),
            # disappointed: THE LETDOWN. Not sadness - EXPECTATION THAT FAILED.
            # He was hoping, and it didn't happen.
            # The sad-cluster is the tightest real estate in the project, so
            # every obvious move was already gone:
            #   sleepy (CONFIRMED) = a slow drowsy bob. disappointed and
            #     exhausted were BOTH sharing that one line; split out.
            #   pensive (CONFIRMED) = sink-and-HOLD. He's awake and thinking.
            #   sad_simple (CONFIRMED) = THE SIGH THAT NEVER LANDS - periodic,
            #     and its whole identity is that it never arrives.
            # So disappointed gets THE DEFLATE: a one-shot VERTICAL SQUASH
            # (scale Y only - embarrassed owns the UNIFORM shrink, scrutinizing
            # owns the scale-up; nobody squashes). Air going out of him. It
            # LANDS in ~1.5s and then he STAYS deflated - the deliberate
            # inverse of sad_simple's sigh that never arrives.
            # *** THE STILLNESS AFTER THE DROP IS THE EMOTION. *** He's stopped
            # hoping. Both the squash and the slump are in buddy.py.
            #   _eye_disappointed = cast straight DOWN at the floor, sitting low
            #     in the socket, dull highlight. NOT _eye_half_lid (that paints
            #     a skin lid OVER a finished eye = the double-eyebrow bug), and
            #     NOT embarrassed's avert (down AND to one side, avoiding YOU).
            #     He isn't hiding from you; he's just stopped looking up.
            #   _brow_disappointed = flat, low, lifeless. The ABSENCE of shape
            #     is the read - he has stopped reacting.
            #   _mouth_disappointed = a short flat downturned line. Gone quiet.
            # Blink flag False is SAFE: disappointed is not in _BLINKABLE.
            ("disappointed", lambda p: E._eye_disappointed(p),
             E._brow_disappointed, lambda p: E._mouth_disappointed(p), False),
            # exhausted: HE HAS NOTHING LEFT. Not drowsy - SPENT.
            # *** SLEEPY (CONFIRMED) OWNS DROWSINESS OUTRIGHT *** - it has
            # floating "z z z" rising off his head in the canvas accent chain.
            # So exhausted must not be sleepy, and that KILLED my own reserved
            # idea: HEAVY BLINKING IS A SLEEPY CUE, NOT AN EXHAUSTED ONE. Cut.
            # The whole baseline face was wrong and all of it is replaced:
            #   _blink_eyes (fully CLOSED) = sleepy's picture. He isn't asleep.
            #   _mouth_wavy = that squiggle is ANXIOUS's now (reserved for it
            #     back when scared was built).
            # And exhausted was STILL sharing sleepy's bob branch. Split out.
            # THE MOTION IS "THE RALLY THAT FAILS" (see buddy.py): he sags,
            # hauls himself part-way upright, and slumps straight back down.
            # Over and over. A struggle to stay up that keeps losing.
            #   sleepy       = drifting off peacefully, with Zs. He's FINE.
            #   disappointed = ONE deflate that lands and goes STILL. He STOPPED.
            #   sad_simple   = a BREATH cycle that never arrives (emotional).
            #   exhausted    = a POSTURE cycle. PHYSICAL EFFORT, and it fails.
            #   _eye_exhausted = thin tired SLITS held open by effort, plus an
            #     UNDER-EYE SHADOW that nothing else in the 65 has.
            #   _brow_exhausted= sagging OUTWARD, collapsed - too tired to hold
            #     a shape. (disappointed's are flat and LEVEL; these fall away.)
            #   _mouth_exhausted= hanging SLACK and open. Not terrified's rigid
            #     gape, not sobbing's wail - it has simply stopped being held
            #     shut.
            # Blink flag False is SAFE: exhausted is not in _BLINKABLE.
            ("exhausted", lambda p: E._eye_exhausted(p), E._brow_exhausted,
             lambda p: E._mouth_exhausted(p), False),
            # frustrated: HE IS STUCK, AND IT IS BUILDING.
            # *** FRUSTRATION IS NOT AIMED AT YOU. *** It is effort that goes
            # NOWHERE. That is what separates it from the rest of the anger
            # block, which is all aimed outward:
            #   mad     = a SCOWL, HELD. Contained. (the low end)
            #   angry   = SEETHING. A steady burn.
            #   furious = an ERUPTION.
            #   frustrated = WIND-UP AND RELEASE. He tenses, trembles harder and
            #     harder as it builds, bursts... and immediately starts winding
            #     up again. It never discharges. THAT CYCLE IS THE EMOTE.
            # *** SPLIT OUT of the shared motion line with FURIOUS *** - they
            # were both running bob=sin(ph*1.2)*2, dx=sin(ph*13)*3.
            #   _eye_frustrated = SCREWED SHUT in effort. *** The collision to
            #     avoid here is SOBBING, not anger *** - _eye_sobbing is also
            #     clenched shut, but it has squeeze-CREASES (anguish, the face
            #     crumpling). These have NO creases; the lids are hard wedges
            #     angled DOWN toward the nose. Tension, not sorrow.
            #   _brow_frustrated= the LOWEST, hardest furrow in the set, jammed
            #     onto the lids, plus vertical PINCH LINES between the brows -
            #     pressure with nowhere to go, made visible.
            #   _mouth_frustrated= teeth BARED and clenched. Wider and flatter
            #     than _mouth_grit (which the baseline shared with angry).
            # NO canvas accent - deliberately. huffing gets steam, angry gets
            # the flush + vein, furious gets the flames. Frustration is INTERNAL.
            # Blink flag False is SAFE: frustrated is not in _BLINKABLE (and his
            # eyes are screwed shut anyway).
            ("frustrated", lambda p: E._eye_frustrated(p), E._brow_frustrated,
             lambda p: E._mouth_frustrated(p), False),
            # huffing: THE INDIGNANT SNORT. He is not raging - he is OFFENDED,
            # and he is letting you know about it.
            # *** STEAM FROM THE NOSE. *** That is literally what the emoji is
            # (face with steam from NOSE). The old accent puffed from beside his
            # EARS, and it was FURNITURE - a `% 40` scroller that teleported and
            # never formed or dissipated. DELETED. The new steam is in buddy.py's
            # PIL chain, with a real lifecycle: born at the nostril, billows,
            # drifts out, dies.
            # *** IT MUST GO IN THE PIL CHAIN, NOT A frame() BRANCH: huffing is
            # in _BLINKABLE with its flag True, so a frame() branch would take
            # his blink away (or KeyError). Same pattern as anxious's sweat.
            # THE BODY SNORTS: a SLOW SWELL as he draws breath in, then a SHARP
            # DROP as he blasts it out. That is the deliberate MIRROR of
            # exhausted (sharp UP, slow down) - same machinery, opposite shape,
            # so the two can never be confused.
            #   _eye_huffing  = a hard NARROWED glare, eyes OPEN. The only anger
            #     emote with open-and-narrow eyes: frustrated is screwed shut,
            #     and mad/angry/furious keep wide staring rage. Contempt, not fury.
            #   _brow_huffing = a clean straight slant, riding HIGHER than
            #     frustrated's (which is jammed on the lids with pinch lines).
            #     He is COMPOSED - anger held IN. That is what huffing is.
            #   _mouth_huffing= pressed FLAT and TIGHT, clamped shut. A mouth
            #     held shut by force is what drives the steam out of his nose.
            # *** BLINK FLAG STAYS True *** - huffing IS in _BLINKABLE, and
            # setting this False would be a KeyError the moment he blinked.
            ("huffing", lambda p: E._eye_huffing(p), E._brow_huffing,
             lambda p: E._mouth_huffing(p), True),
            # mad: A SCOWL, HELD. The LOW END of the anger ladder, and its whole
            # identity is RESTRAINT.
            # *** MAD IS THE ONE THAT DOESN'T SHAKE. *** Everything else in this
            # block vibrates - frustrated ESCALATES, huffing SNORTS, angry will
            # SEETHE, furious will ERUPT. Mad holds perfectly STILL and stares at
            # you, breathing slow and controlled... and every ~3.2s the anger
            # breaks through as ONE sharp shudder that he instantly suppresses.
            # *** THE STILLNESS IS THE EMOTION. *** (see buddy.py)
            # DELIBERATELY NO ACCENT. huffing has steam, angry will have the
            # flush + vein, furious the flames. Mad has NOTHING - the restraint
            # is exactly what makes it read as the low end.
            #   _eye_mad   = WIDE OPEN and staring, tensed from BELOW (the lower
            #     lid pushed up). The block splits eyes three ways: frustrated
            #     screwed SHUT, huffing NARROW (flattened from above, contempt),
            #     mad WIDE (tensed from below, holding your gaze on purpose).
            #   _brow_mad  = a heavy V at MID height with a real BEND - a scowl,
            #     not a slant. frustrated's is lowest + pinch lines; huffing's is
            #     a straight line riding high.
            #   _mouth_mad = a DEEP scowl. Corners drop ~5px below the middle,
            #     where huffing's clamp drops only ~2px. The amount IS the emote.
            # *** BLINK FLAG STAYS True *** - mad IS in _BLINKABLE, and False
            # here would be a KeyError the moment he blinked.
            ("mad", lambda p: E._eye_mad(p), E._brow_mad,
             lambda p: E._mouth_mad(p), True),
            # angry: SEETHING. The burn between mad's restraint and furious's
            # eruption. He is VIBRATING with it.
            # *** ANGRY GAVE UP THE FLAMES. *** angry and furious used to draw
            # the IDENTICAL flame accent, differing only in the count (2 vs 3).
            # They would have shipped as TWINS. The flames are now furious's
            # alone, and angry takes THE ANGER VEIN instead - which nothing else
            # in the 65 has.
            # *** AND ANGRY DOES *NOT* GET A RED FLUSH. *** THREE confirmed
            # emotes already own face-reddening and a fourth would be a twin:
            #     bashful     = a flat PINK wash (static, pleasant).
            #     embarrassed = SCARLET, CLIMBING from the cheeks (a lifecycle).
            #     hot         = _heat_sheen, a physical heat flush + steam.
            # The vein + the tremble + the snarl carry it instead. THE LADDER
            # STILL READS: mad HOLDS STILL -> angry VIBRATES -> furious ERUPTS.
            #   _eye_angry     = burning, and *** NO CATCHLIGHT AT ALL ***. That
            #     absence is the split from mad, which HAS a highlight (there is
            #     still a person in there). Angry's eyes have no light in them.
            #   _brow_seething = the LOWEST, hardest furrow in the whole block
            #     (inner end driven to ey-4.5; mad's stops at -7.5).
            #   _mouth_snarl   = OPEN, teeth bared AT you. frustrated's teeth are
            #     CLENCHED SHUT in a flat bar (holding it in). This one isn't
            #     holding anything in.
            # Blink flag False is SAFE: angry is not in _BLINKABLE.
            ("angry", lambda p: E._eye_angry(p), E._brow_seething,
             lambda p: E._mouth_snarl(p), False),
            # furious: THE ERUPTION. The top of the ladder, and the last rung.
            #   mad     HOLDS STILL (restraint).
            #   angry   VIBRATES (a steady burn that never stops).
            #   furious ERUPTS. He is not containing anything at all.
            # *** THE FLAMES ARE NOW HIS ALONE. *** angry and furious used to
            # draw the IDENTICAL flame accent (2 vs 3 flames) and would have
            # shipped as twins. Angry gave them up. Furious's flames are now
            # bigger, there are more of them, and they are drawn in the PIL
            # chain with a real gradient instead of flat tkinter polygons.
            # *** PLUS THE CURSE SYMBOLS *** - the churning band over his mouth,
            # which is what 🤬 actually IS. They CYCLE (each slot swaps symbol),
            # so they are not furniture.
            #   _eye_furious  = *** THE ONLY ANGER EMOTE SHOWING THE WHITES OF
            #     HIS EYES ***, pupils shrunk to pinpricks. The "snapped" cue.
            #     (mad = wide + catchlight; angry = wide + NO catchlight;
            #      furious = whites + pinprick pupils. Each is one step further.)
            #   _brow_furious = the STEEPEST slash in the block, driven lowest.
            #   _mouth_furious= a wide open ROAR for the symbols to read against.
            #     NOT _mouth_scribble (the baseline) - a static squiggle is
            #     furniture, and the real thing CHURNS.
            # Blink flag False is SAFE: furious is not in _BLINKABLE.
            ("furious", lambda p: E._eye_furious(p), E._brow_furious,
             lambda p: E._mouth_furious(p), False),
            # mischievous: HE IS PLOTTING. Up to something, and pleased about it.
            # *** THE BASELINE WAS A TWIN OF SHUSH. *** It was
            #   mischievous = _eye_half_lid(0.3) + _mouth_smirk
            #   shush       = _eye_half_lid(0.4) + _mouth_smirk   (CONFIRMED)
            # THE SAME TWO HELPERS, separated only by a droop value. Both are
            # replaced here; shush keeps the stock pair.
            #   _eye_scheming = a SLY SIDEWAYS GLANCE - pupils shoved hard to one
            #     side. He isn't looking AT you, he's looking OFF at whatever he
            #     is about to do. A half-lid alone can never say that.
            #   _mouth_sly    = a lopsided grin *** WITH A FANG ***. A smirk is
            #     amused; a smirk with a tooth showing is UP TO SOMETHING.
            # THE GESTURE IS THE EMOTE: *** HE RUBS HIS PAWS TOGETHER. *** The
            # arms COUNTER-rotate so the paws SLIDE ACROSS each other. Two paws
            # held still is a clasp; two paws sliding is PLOTTING.
            #   adoring  = paws HIGH at the cheek, STATIC ('aww').
            #   pleading = paws at the chest, PRESSING AT YOU, open palms.
            #   mischievous = paws at the chest, RUBBING, backs out. Nobody rubs.
            # Blink flag False is SAFE: mischievous is not in _BLINKABLE.
            ("mischievous", lambda p: E._eye_scheming(p), None,
             lambda p: E._mouth_sly(p), False),
        ]

        for key, eyes_fn, brow_fn, mouth_fn, blinkable in SPECS:
            pl = _new()
            eyes_fn(pl)
            if brow_fn:
                brow_fn(pl)
            if mouth_fn:
                mouth_fn(pl)
            plates[key] = pl
            if blinkable:
                pl2 = _new()
                E._blink_eyes(pl2)
                if brow_fn:
                    brow_fn(pl2)
                if mouth_fn:
                    mouth_fn(pl2)
                plates[key + "_blink"] = pl2

        return plates



_BLINKABLE = {"idle", "happy", "thinking", "worried", "grinning",
              "shush",
              "cold", "embarrassed", "anxious", "huffing",
              "mad", "nerdy", "scrutinizing", "confused", "crying"}


def _plate_key(emote, blinking):
    base = {"wave": "happy", "celebrate": "excited"}.get(emote, emote)
    if blinking and base in _BLINKABLE:
        return base + "_blink"
    return base
