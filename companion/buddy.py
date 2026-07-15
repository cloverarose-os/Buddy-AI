# Claude Desktop Buddy v4 - local brain edition
# Chat box -> routes to Buddy AI (:8766), the ONE unified brain. Desktop is
# a PURE thin display/animation client: send text, get back {text, emote,
# image_path}, render it. No persona, no tool logic, no image-gen code here
# at all - Buddy AI owns everything now, so this always matches whatever
# capabilities the brain has, even as they grow.
# Claude/watchdog can still speak via inbox.txt. HTTP API on :8765 for
# HA/local stack (/say, /status, /generate_image - unchanged, NAS depends on it)
import tkinter as tk
import tkinter.font as tkfont
import os, time, random, math, json, re
import threading, urllib.request
import queue as _queue
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from PIL import Image, ImageTk, ImageDraw, ImageFilter, ImageChops
from skin_highres import HighResSkin, HX, HY, CX, CY, \
    PAW_TOP, PAW_BOT, SUIT_EDGE as SKIN_EDGE


def _shift(img, dx, dy):
    """Translate an RGBA layer by (dx, dy) on a transparent canvas of the
    same size. Used by the frame-transform chain (recoil, lid flight)."""
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img, (int(dx), int(dy)))
    return out

BASE = r"C:\ClaudeBuddy"
INBOX = os.path.join(BASE, "inbox.txt")
OUTBOX = os.path.join(BASE, "outbox.txt")
LOG = os.path.join(BASE, "log.txt")
STATUSF = os.path.join(BASE, "llm_status.json")
BUDDY_AI_URL = "http://localhost:8766"
HTTP_PORT = 8765
BUDDY = None
TRANS = "#ff00fe"
TRANS_RGB = (255, 0, 254)
EMOTES = {
    "idle", "happy", "excited", "thinking", "worried", "love",
    "alert", "sleepy", "celebrate", "wave",
    # emoji-driven expression set
    "grinning", "laughing", "laughing_crying", "rofl", "adoring", "kiss",
    "wink", "bashful", "innocent", "hug", "silly", "playful_tongue",
    "zany", "yummy", "money_eyes", "giggle", "shush", "skeptical",
    "smirk", "unamused", "eye_roll", "deadpan", "speechless", "awkward",
    "relieved", "pensive", "yawn", "drooling", "sick", "nauseated",
    "hot", "cold", "dizzy", "mind_blown", "cool", "nerdy", "scrutinizing",
    "confused", "sad_simple", "surprised", "embarrassed", "pleading",
    "scared", "anxious", "crying", "sobbing", "terrified", "disappointed",
    "exhausted", "frustrated", "huffing", "mad", "angry", "furious",
    "mischievous",
}

# --- image-request detection (companion side) ----------------------------
# The brain ultimately decides (via the model's tool call) whether to make an
# image, and that generation is slow (tens of seconds). To avoid Buddy sitting
# silent on "..." the whole time, the companion does a lightweight keyword
# check the instant you hit send: if the message clearly asks for a picture, we
# immediately show an in-personality "give me a sec" line while the thinking
# animation runs. It only needs to catch the common phrasings; a miss just
# means the old silent behavior, and we bias AWAY from false positives so
# ordinary sentences that merely mention a "picture" don't trigger it.
_IMG_VERBS = ("make", "generate", "create", "draw", "paint", "render",
              "design", "sketch", "gimme", "give me", "show me", "whip up",
              "cook up", "conjure", "produce")
_IMG_NOUNS = ("image", "picture", "pic", "art", "artwork", "drawing",
              "painting", "illustration", "wallpaper", "portrait", "sketch",
              "render", "photo")

import re as _re_img
# 'draw' and 'paint' are strong enough to fire on their own (with an optional
# 'me'), except for common idioms ('draw a conclusion/line', etc.).
_re_img_draw = _re_img.compile(
    r"\b(?:draw|paint)(?:\s+me)?\b(?!\s+(?:a\s+|the\s+|your\s+)?"
    r"(?:line|lines|conclusion|conclusions|attention|near|close|blood|"
    r"breath|the\s+curtains|water|straw))")
_re_img_verbnoun = _re_img.compile(
    r"\b(?:make|generate|create|render|design|sketch|conjure|produce|"
    r"whip up|cook up|gimme|give me|show me)\b[\w\s,'-]{0,30}?\b"
    r"(?:image|picture|pic|artwork|drawing|painting|illustration|wallpaper|"
    r"portrait|render|photo)\b")


def looks_like_image_request(text):
    """True if the message plainly asks Buddy to CREATE an image. Requires an
    image-creation verb reasonably close BEFORE an image noun, so 'draw me a
    cat' or 'make an image of a robot' fire, but 'that picture was nice' or
    'I like your art' do not."""
    t = " " + text.lower().strip() + " "
    # 'draw' + almost anything is an image request even without a noun
    if _re_img_draw.search(t):
        return True
    # verb ... noun within a short window
    return bool(_re_img_verbnoun.search(t))


# rotating in-personality "hang on, making it" lines (no em dashes; ellipses
# fit the pause and match the TTS-friendly style)
_IMG_ACK_LINES = [
    "Ooh, fun... let me paint that for you! Give me a sec...",
    "On it! Good art takes a moment... hang tight!",
    "Yesss, let me cook something up for you... one moment!",
    "Ooh I love making these... gimme a few seconds!",
    "Warming up my paintbrush... this'll take a moment!",
    "Let me work my magic... image incoming, just a sec!",
]

# Emoji -> emote. If the model's reply text contains one of these, it
# ALWAYS wins over the JSON "emote" tag (JSON is the fallback only).
EMOJI_TO_EMOTE = {
    # U+1F44B waving hand -> wave. ADDED 2026-07-14: the trigger audit found
    # wave was the ONLY non-idle emote with no emoji at all. It still worked,
    # because "wave" is one of the names the brain's JSON tag list offers - but
    # it was reachable on ONE path instead of two. Now it has both.
    # (idle is deliberately left with NO emoji: it is the default resting state,
    # not something anything should ever trigger.)
    "\U0001F44B": "wave",
    "\U0001F642": "happy", "\U0001F929": "excited", "\U0001F60D": "love",
    "\U0001F914": "thinking", "\U0001F61F": "worried", "\U0001F634":
    "sleepy", "\U0001F973": "celebrate", "\U0001F632": "alert",
    "\U0001F600": "grinning", "\U0001F606": "laughing",
    "\U0001F602": "laughing_crying", "\U0001F923": "rofl",
    "\U0001F970": "adoring", "\U0001F618": "kiss", "\U0001F609": "wink",
    "\U0001F60A": "bashful", "\U0001F607": "innocent",
    "\U0001F917": "hug", "\U0001F643": "silly",
    "\U0001F61C": "playful_tongue", "\U0001F92A": "zany",
    "\U0001F60B": "yummy", "\U0001F911": "money_eyes",
    "\U0001F92D": "giggle", "\U0001F92B": "shush",
    "\U0001F928": "skeptical", "\U0001F60F": "smirk",
    "\U0001F612": "unamused", "\U0001F644": "eye_roll",
    "\U0001F610": "deadpan", "\U0001F636": "speechless",
    "\U0001F62C": "awkward", "\U0001F60C": "relieved",
    "\U0001F614": "pensive", "\U0001F971": "yawn",
    "\U0001F924": "drooling", "\U0001F912": "sick",
    "\U0001F922": "nauseated", "\U0001F975": "hot",
    "\U0001F976": "cold", "\U0001F635": "dizzy",
    "\U0001F92F": "mind_blown", "\U0001F60E": "cool",
    "\U0001F913": "nerdy", "\U0001F9D0": "scrutinizing",
    "\U0001F615": "confused", "\U0001F641": "sad_simple",
    "\U0001F62E": "surprised", "\U0001F633": "embarrassed",
    "\U0001F97A": "pleading", "\U0001F628": "scared",
    "\U0001F630": "anxious", "\U0001F622": "crying",
    "\U0001F62D": "sobbing", "\U0001F631": "terrified",
    "\U0001F61E": "disappointed", "\U0001F629": "exhausted",
    "\U0001F62B": "frustrated", "\U0001F624": "huffing",
    "\U0001F620": "mad", "\U0001F621": "angry",
    "\U0001F92C": "furious", "\U0001F608": "mischievous",
}

# Near-miss emote names the LLM reaches for that are NOT real emotes, mapped to
# the closest real one. Applied in set_emote BEFORE the validity check, so it
# covers BOTH trigger paths (emoji text and the JSON "emote" tag).
# The live brain round-trip on 2026-07-14 showed the model repeatedly emitting
# "guilty"/"guilt" (no such emote) for "you should feel bad" prompts; without
# this it fell back to "happy", i.e. a smile on a guilt cue - clearly wrong.
# embarrassed is the closest existing expression (flushed, sheepish).
# NOTE: this is a deliberately small, targeted map. Broader model-vocabulary
# tuning is a separate future package, per Chloe - do not grow this ad hoc.
EMOTE_ALIASES = {
    "guilty": "embarrassed",
    "guilt": "embarrassed",
}


def emote_from_text(text):
    """First matching emotion emoji in text wins (priority over any
    JSON emote tag). Returns None if no known emoji is present."""
    if not text:
        return None
    for ch in text:
        em = EMOJI_TO_EMOTE.get(ch)
        if em:
            return em
    return None


# High-res "bear in alien jumpsuit" palette (from Buddy's self-portrait)
BODY = "#EF8467"        # suit coral (also themes chat UI)
BODY_EDGE = "#D2664B"
SUIT = BODY
SUIT_EDGE = BODY_EDGE
SUIT_DK = "#E0704F"     # inner ears, hood rim, side pods
SKIN = "#F6C89E"        # face
BLUSH = "#F0997E"
BELLY = "#FBF3E8"
PAW = "#6E4433"         # brown paws/feet
PAD = "#F2A08B"         # pink paw pads
INK = "#2E211B"
RED = "#E0455A"

class Buddy:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Claude Buddy")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=TRANS)
        try:
            self.root.attributes("-transparentcolor", TRANS)
        except tk.TclError:
            pass
        self.w, self.h = 380, 430
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        # keep his on-screen position identical to the old 350px window
        # (top pinned); the extra canvas height extends downward for the
        # hover rings below his feet.
        top_y = sh - 350 - 90
        self.root.geometry(f"{self.w}x{self.h}+{sw-self.w-24}+{top_y}")
        self.cv = tk.Canvas(self.root, width=self.w, height=self.h,
                            bg=TRANS, highlightthickness=0)
        self.cv.pack()
        self.msg = ""
        self.msg_until = 0.0
        self.emote = "idle"
        self.emote_until = 0.0
        self.phase = 0.0
        self._rofl_t0 = 0.0   # phase at which the current rofl cycle began
        self._relieved_t0 = 0.0   # phase at which relieved was triggered
                                  # (the forehead wipe is one-shot, not looped)
        self._yawn_t0 = 0.0       # phase at which yawn was triggered (also
                                  # one-shot: build -> peak -> close -> drowsy)
        self._cool_t0 = 0.0       # phase at which cool was triggered (the
                                  # "deal with it" shades drop in ONCE)
        self._sad_t0 = 0.0        # phase at which sad_simple was triggered
                                  # (the ear/antenna wilt falls ONCE)
        self._sad_ug = 0.0        # current point in the sigh cycle, shared by
                                  # the body sigh and the ear sag
        self._surprised_t0 = 0.0  # phase at which surprised was triggered
                                  # (the startle is a ONE-SHOT event)
        self._surprised_el = 0.0  # elapsed phase since the startle began,
                                  # shared by the jump, the face and the
                                  # antenna quiver so they can't desync
        self._emb_t0 = 0.0        # phase at which embarrassed was triggered
                                  # (the flush BLOOMS once, then pulses)
        self._plead_t0 = 0.0      # phase at which pleading was triggered (he
                                  # LEANS IN once, then keeps bouncing hopefully)
        self._scared_t0 = 0.0     # phase at which scared was triggered (he
                                  # COWERS once, then trembles and FLINCHES)
        self._cry_t0 = 0.0        # phase at which crying was triggered - the
                                  # tear cycle starts fresh, so the first tear
                                  # WELLS just after he arrives
        self._sob_t0 = 0.0        # phase at which sobbing was triggered (he
                                  # SINKS once, then heaves)
        self._disap_t0 = 0.0      # phase at which disappointed was triggered
                                  # (he DEFLATES once, then goes still)
        self._exh_t0 = 0.0        # phase at which exhausted was triggered (he
                                  # SAGS once, then rallies and fails, forever)
        self._exh_droop = 0.0     # 0..1 - drives the REAL droop (head sinking,
                                  # ears wilting, arms limp, antennae down).
                                  # NOT `bob`, which only slides the sprite.
        self._frus_t0 = 0.0       # phase at which frustrated was triggered (the
                                  # wind-up starts fresh, so he BUILDS on arrival)
        self._huff_t0 = 0.0       # phase at which huffing was triggered (he
                                  # starts on an INHALE, not mid-blast)
        self._huff_u = 0.0        # 0..1 point in the SNORT cycle, shared by the
                                  # body and the steam so they cannot desync
        self._mad_t0 = 0.0        # phase at which mad was triggered (he settles
                                  # into the held scowl, then shudders on cue)
        self._angry_t0 = 0.0      # phase at which angry was triggered
        self._angry_throb = 0.0   # 0..1 swell of rage, shared by the body and
                                  # the ANGER VEIN so they cannot desync
        self._fur_t0 = 0.0        # phase at which furious was triggered
        self._fur_erupt = 0.0     # 0..1 the BLOW, shared by the body, the
                                  # flames and the cursing so they peak together
        self._misc_t0 = 0.0       # phase at which mischievous was triggered
        self._misc_rub = 0.0      # 0..1 the PAW-RUB cycle (the scheming gesture)
        self.blink_until = 0.0
        self.next_blink = time.time() + random.uniform(2, 5)
        self.particles = []
        self.skin = HighResSkin()
        self.ant_a = random.uniform(0, 6.28)
        self.ant_b = random.uniform(0, 6.28)
        self._photo = None
        self._lips_base = self._bake_lips()
        self._lips_photo = None
        self.bubble_win = None
        self._bubble_msg = ""
        self.chat_win = None
        self.chat_history = []
        self.results = _queue.Queue()
        global BUDDY
        BUDDY = self
        threading.Thread(target=start_http, daemon=True).start()
        self._dx = self._dy = 0
        self.cv.bind("<Button-1>", self.on_press)
        self.cv.bind("<B1-Motion>", self.on_drag)
        self.cv.bind("<Button-3>", self.on_menu)
        self.cv.bind("<Double-Button-1>", self.toggle_chat)
        self.root.after(300, self.check_queue)
        self.tick()
        self.poll()
        self.root.mainloop()

    def on_press(self, e):
        self._dx, self._dy = e.x, e.y

    def on_drag(self, e):
        x = self.root.winfo_x() + e.x - self._dx
        y = self.root.winfo_y() + e.y - self._dy
        self.root.geometry(f"+{x}+{y}")
        self._place_chat()
        self._place_bubble()

    def on_menu(self, e):
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label="Chat with Buddy", command=self.toggle_chat)
        m.add_command(label="Dismiss message", command=self.clear_msg)
        m.add_command(label="Exit buddy", command=self.root.destroy)
        m.tk_popup(e.x_root, e.y_root)

    def toggle_chat(self, e=None):
        try:
            if self.chat_win and self.chat_win.winfo_exists():
                self.chat_win.destroy()
                self.chat_win = None
                return
        except tk.TclError:
            self.chat_win = None
        w = tk.Toplevel(self.root)
        w.title("Chat with Buddy")
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.attributes("-alpha", 0.95)
        try:
            w.attributes("-transparentcolor", TRANS)
        except tk.TclError:
            pass
        cw, ch = 252, 96
        w.configure(bg=TRANS)
        cvc = tk.Canvas(w, width=cw, height=ch, bg=TRANS,
                        highlightthickness=0)
        cvc.pack()
        px1 = cw - 24                     # panel right edge (arrow zone)
        self._round_rect(cvc, 6, 6, px1, ch - 6, 18,
                         fill="#FBEDE6", outline=BODY, width=2)
        # sound-wave arcs aimed at his ear: this is what he hears
        ay = 44
        for r2 in (5, 9, 13):
            cvc.create_arc(px1 + 2 - r2, ay - r2, px1 + 2 + r2, ay + r2,
                           start=-50, extent=100, style="arc",
                           outline=BODY, width=2)
        cvc.create_text(20, 22, text="Talk to Buddy", anchor="w",
                        font=("Segoe UI", 9, "italic"), fill=BODY_EDGE)
        self.entry = tk.Entry(w, font=("Segoe UI", 11), bd=0,
                              bg="#FFFFFF", fg=INK, insertbackground=BODY,
                              relief="flat", highlightthickness=1,
                              highlightbackground=BODY,
                              highlightcolor=BODY)
        self.entry.place(x=16, y=40, width=px1 - 16 - 54, height=30)
        send = tk.Button(w, text="Send", command=self.send_chat,
                         font=("Segoe UI", 9, "bold"), bd=0,
                         bg=BODY, fg="#FFFFFF", activebackground=BODY_EDGE,
                         activeforeground="#FFFFFF", relief="flat",
                         cursor="hand2")
        send.place(x=px1 - 50, y=40, width=44, height=30)
        self.entry.bind("<Return>", lambda ev: self.send_chat())
        self.entry.bind("<Escape>", lambda ev: self.toggle_chat())
        self.chat_win = w
        self._place_chat()
        self.entry.focus_force()
        w.after(50, lambda: self.entry.focus_force())

    def _place_chat(self):
        """Keep the input box locked screen-left of his head, arrow
        touching his ear."""
        try:
            if not (self.chat_win and self.chat_win.winfo_exists()):
                return
        except tk.TclError:
            return
        cw, ch = 252, 96
        x = self.root.winfo_x() + (HX - 46) - cw + 4
        y = self.root.winfo_y() + HY - 56
        self.chat_win.geometry(f"{cw}x{ch}+{max(0, x)}+{max(0, y)}")

    def _place_bubble(self):
        """Response bubble locked up-right of his head (storyboard).

        Grows UPWARD by self._bubble_grow px (see _bubble_measure): the tail
        stays pinned to his head and the top rises, so the window's y-origin
        moves up by the same amount the canvas got taller."""
        try:
            if not (self.bubble_win and self.bubble_win.winfo_exists()):
                return
        except tk.TclError:
            return
        g = getattr(self, "_bubble_grow", 0)
        x = self.root.winfo_x() + HX - 10
        y = self.root.winfo_y() + HY - 236 - g      # grow UP: raise the origin
        self.bubble_win.geometry(f"310x{212 + g}+{max(0, x)}+{max(0, y)}")

    # --- vertical-stretch bubble ------------------------------------------
    # The shape is a fixed set of control points; its CHARACTER (width, corner
    # rounding, border, tail) must never change - only its HEIGHT. So we split
    # the polygon into a TOP band (rises by `g`) and a BOTTOM band + tail
    # (stay put), and open a gap of `g` px between them. Every x is untouched,
    # so the silhouette is pixel-identical apart from being taller.
    _BUB_W = 310
    _BUB_H0 = 212                    # base canvas height
    _BUB_WAIST = 90                  # points above this y rise; at/below stay
    # base control points (the original hand-tuned comic-skew bubble)
    _BUB_PTS = [30, 16, 150, 8, 286, 14, 298, 30, 302, 92, 294, 150,
                282, 162, 160, 168, 44, 163, 30, 150, 22, 88, 24, 34]
    _BUB_TAIL = [70, 162, 106, 158, 42, 204]
    _BUB_SEAM = [72, 161, 103, 158]
    _BUB_TEXT_W = 252               # text wrap width (never changes)
    _BUB_GROW_MAX = 212             # cap: +212 => bubble can reach 2x its base

    def _bubble_shift(self, g):
        """Return (poly, tail, seam, text_cy) for a bubble grown by `g` px
        upward. Everything below the waist keeps its base y; everything above
        the waist has `g` added to its y in CANVAS space (the canvas is `g`
        taller and anchored so the bottom is fixed, so 'add g to the top band'
        makes the body taller while the floor/tail hold still)."""
        def place(seq):
            out = []
            for i in range(0, len(seq), 2):
                px, py = seq[i], seq[i + 1]
                out.append(px)
                out.append(py if py < self._BUB_WAIST else py + g)
            return out
        poly = place(self._BUB_PTS)
        tail = [self._BUB_TAIL[0], self._BUB_TAIL[1] + g,
                self._BUB_TAIL[2], self._BUB_TAIL[3] + g,
                self._BUB_TAIL[4], self._BUB_TAIL[5] + g]
        seam = [self._BUB_SEAM[0], self._BUB_SEAM[1] + g,
                self._BUB_SEAM[2], self._BUB_SEAM[3] + g]
        # text vertical centre: midway through the interior (top ~30 .. floor)
        text_cy = 30 + (150 + g - 30) // 2
        return poly, tail, seam, text_cy

    def _bubble_measure(self, msg):
        """Measure how tall this message needs the bubble to be. Returns
        (grow_px, scroll_needed). grow is clamped to [0, _BUB_GROW_MAX]; if the
        text is taller than the capped interior, scroll_needed is True."""
        if not getattr(self, "_bub_font", None):
            self._bub_font = tkfont.Font(family="Segoe UI", size=11)
        # Measure on the MAIN canvas (self.cv), which always exists. Measuring
        # on self._bubble_cv is a bug: when a new message arrives we destroy the
        # old bubble first, so _bubble_cv points at a DEAD canvas and create_text
        # throws TclError - which aborted _show_bubble and left an empty bubble
        # for every message after the first.
        cv = self.cv
        tmp = cv.create_text(-9999, -9999, text=msg, width=self._BUB_TEXT_W,
                             font=self._bub_font, anchor="nw")
        x1, y1, x2, y2 = cv.bbox(tmp)
        cv.delete(tmp)
        text_h = y2 - y1
        base_interior = 150 - 30            # interior height at base (~120)
        need = text_h + 24                  # padding top+bottom
        grow = max(0, need - base_interior)
        scroll = grow > self._BUB_GROW_MAX
        return min(grow, self._BUB_GROW_MAX), scroll

    def _show_bubble(self):
        g, scroll = self._bubble_measure(self.msg)
        self._bubble_grow = g
        self._bubble_scroll_on = scroll
        self._bubble_scroll_off = 0         # current scroll offset (px)
        self._bubble_scroll_off_last = -1   # force first scroll to apply
        w = tk.Toplevel(self.root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        try:
            w.attributes("-transparentcolor", TRANS)
        except tk.TclError:
            pass
        w.configure(bg=TRANS)
        cvb = tk.Canvas(w, width=self._BUB_W, height=self._BUB_H0 + g,
                        bg=TRANS, highlightthickness=0)
        cvb.pack()
        self._bubble_cv = cvb
        self._bubble_win = w
        self.bubble_win = w
        self._bubble_render()
        self._bubble_msg = self.msg
        self._place_bubble()
        # wheel scrolling only matters when capped/scrolling
        cvb.bind("<MouseWheel>", self._bubble_wheel)
        w.bind("<MouseWheel>", self._bubble_wheel)

    def _bubble_render(self):
        """(Re)draw the bubble shape, text and (if scrolling) the indicator."""
        cvb = self._bubble_cv
        g = self._bubble_grow
        cvb.delete("all")
        poly, tail, seam, text_cy = self._bubble_shift(g)
        cvb.create_polygon(poly, smooth=True, fill="#FFFFFF",
                           outline=BODY, width=3)
        cvb.create_polygon(tail, fill="#FFFFFF", outline=BODY, width=3)
        cvb.create_line(seam, fill="#FFFFFF", width=5)
        if not getattr(self, "_bubble_scroll_on", False):
            # normal: text centred in the (possibly taller) interior
            self._bubble_text = cvb.create_text(
                162, text_cy, text=self.msg, width=self._BUB_TEXT_W,
                font=("Segoe UI", 11), fill=INK)
        else:
            # capped + scrolling. The text is rendered into a PIL image and
            # HARD-CLIPPED to a rectangle inside the bubble's FLAT middle (never
            # touching the curved top/bottom). *** The expensive work - wrapping
            # the text and building the full-height image - is done ONCE here and
            # CACHED. Scrolling then only re-crops that cached image and moves
            # the indicator (see _bubble_scroll_to), which is cheap enough not to
            # hitch the animation. Previously every wheel notch re-wrapped and
            # rebuilt the whole image, which froze the bubble and Buddy briefly.
            top = 40                        # inside the flat wall, below curve
            floor = 140 + g                 # inside the flat wall, above curve
            view_w = self._BUB_TEXT_W
            view_h = floor - top
            self._bubble_view_h = view_h
            self._bubble_top = top
            # build + cache the full-height text image ONCE
            self._bubble_full_img, full_h = self._bubble_build_full_image(
                self.msg, view_w)
            self._bubble_full_h = full_h
            off = getattr(self, "_bubble_scroll_off", 0)
            off = max(0, min(off, max(0, full_h - view_h)))
            self._bubble_scroll_off = off
            # *** THE REAL FIX FOR THE SCROLL HITCH. *** The window uses
            # -transparentcolor, i.e. a Windows LAYERED window: ANY change to
            # the image pixels forces the OS to recomposite the whole window
            # (~56ms) - which is why both new-PhotoImage AND paste() stuttered
            # identically. So on scroll we now change NO pixels at all: the
            # full-height text image lives inside a small CHILD canvas clipped
            # to the viewing area, and scrolling is inner.yview_moveto() - a
            # window-system blit, no pixel upload, no recomposite.
            # The child canvas bg is white, sitting entirely inside the flat
            # white interior, so it is invisible against the bubble body.
            inner = tk.Canvas(cvb, width=view_w, height=view_h,
                              bg="#FFFFFF", highlightthickness=0, bd=0)
            inner.place(x=162 - view_w // 2, y=top)
            self._bubble_photo = ImageTk.PhotoImage(self._bubble_full_img)
            inner.create_image(0, 0, image=self._bubble_photo, anchor="nw")
            inner.configure(scrollregion=(0, 0, view_w, full_h))
            inner.bind("<MouseWheel>", self._bubble_wheel)
            self._bubble_inner = inner
            if off:
                inner.yview_moveto(off / max(1, full_h))
            track_top, track_bot = top + 4, floor - 4
            track_h = track_bot - track_top
            frac = min(1.0, view_h / max(1, full_h))
            bar_h = max(18, int(track_h * frac))
            max_off = max(1, full_h - view_h)
            pos = min(1.0, off / max_off)
            bar_top = track_top + int((track_h - bar_h) * pos)
            self._bubble_track = (292, track_top, track_h, bar_h, max_off)
            self._bubble_bar_id = cvb.create_rectangle(
                292, bar_top, 296, bar_top + bar_h, fill=BODY, outline="",
                width=0)

    def _bubble_build_full_image(self, msg, width):
        """Wrap `msg` and render it ONCE into a full-height transparent RGBA
        image. Returns (image, full_h). Called a single time when the scrolling
        bubble is created; scrolling reuses this cached image via crop, so the
        wrap+draw cost is never paid again on wheel events."""
        if not getattr(self, "_bub_pilfont", None):
            self._bub_pilfont = self._load_bubble_pilfont()
        font = self._bub_pilfont
        lines = self._wrap_pil(msg, width, font)
        lh = self._bub_line_h
        full_h = len(lines) * lh + 8
        view_h = getattr(self, "_bubble_view_h", full_h)
        full = Image.new("RGBA", (width, max(view_h, full_h)), (0, 0, 0, 0))
        d = ImageDraw.Draw(full)
        ink = (46, 33, 27, 255)             # INK
        y = 4
        for ln in lines:
            w = d.textlength(ln, font=font)
            d.text(((width - w) // 2, y), ln, font=font, fill=ink)
            y += lh
        return full, full_h

    def _bubble_scroll_to(self, off):
        """Scroll with ZERO pixel changes: move the child canvas's viewport
        (yview_moveto is a window-system blit) and slide the indicator bar.
        No image data is touched, so the layered window never recomposites -
        that recomposite was the entire hitch."""
        cvb = self._bubble_cv
        view_h = self._bubble_view_h
        full_h = self._bubble_full_h
        max_off = max(0, full_h - view_h)
        off = max(0, min(off, max_off))
        if off == getattr(self, "_bubble_scroll_off_last", -1):
            return                          # nothing changed; skip the work
        self._bubble_scroll_off = off
        self._bubble_scroll_off_last = off
        self._bubble_inner.yview_moveto(off / max(1, full_h))
        # move the indicator bar
        track_x, track_top, track_h, bar_h, tmax = self._bubble_track
        pos = min(1.0, off / max(1, tmax))
        bar_top = track_top + int((track_h - bar_h) * pos)
        cvb.coords(self._bubble_bar_id, track_x, bar_top,
                   track_x + 4, bar_top + bar_h)

    def _load_bubble_pilfont(self):
        from PIL import ImageFont
        # Must use ABSOLUTE font paths: PIL's truetype() cannot resolve bare
        # names like "segoeui.ttf" on this system (it raises OSError and would
        # silently fall back to the tiny bitmap default, making bubble text
        # render tiny). Segoe UI matches the Tk bubble font used elsewhere.
        import os
        winf = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
        f = None
        for name in ("segoeui.ttf", "arial.ttf"):
            try:
                f = ImageFont.truetype(os.path.join(winf, name), 15)
                break
            except OSError:
                f = None
        if f is None:
            f = ImageFont.load_default()
        # cache a consistent line height
        asc, desc = f.getmetrics()
        self._bub_line_h = asc + desc + 3
        return f

    def _wrap_pil(self, msg, width, font):
        """Word-wrap `msg` to pixel `width` using the PIL font metrics."""
        from PIL import ImageDraw as _ID
        scratch = _ID.Draw(Image.new("RGBA", (1, 1)))
        out = []
        for para in msg.split("\n"):
            words = para.split(" ")
            line = ""
            for wd in words:
                trial = wd if not line else line + " " + wd
                if scratch.textlength(trial, font=font) <= width:
                    line = trial
                else:
                    if line:
                        out.append(line)
                    line = wd
            out.append(line)
        return out

    def _bubble_wheel(self, e):
        if not getattr(self, "_bubble_scroll_on", False):
            return
        step = 24 if e.delta < 0 else -24
        off = getattr(self, "_bubble_scroll_off", 0) + step
        # cheap in-place scroll (paste into existing PhotoImage + move bar)
        self._bubble_scroll_to(off)

    def _round_rect(self, cv, x1, y1, x2, y2, r, **kw):
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r,
               x2, y2, x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r,
               x1, y1 + r, x1, y1]
        return cv.create_polygon(pts, smooth=True, **kw)

    def send_chat(self):
        txt = self.entry.get().strip()
        if not txt:
            return
        self.entry.delete(0, tk.END)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG, "a", encoding="utf-8") as lg:
            lg.write(f"[{stamp}] USER: {txt}\n")
        if is_gaming():
            self.results.put({"text": "Brain is unloaded so your game "
                              "gets all the VRAM - ask me after the "
                              "session!", "emote": "sleepy"})
            return
        # If this plainly looks like an image request, acknowledge it right
        # away in-personality (image gen is slow; otherwise Buddy just sits
        # silent on "..."). The real reply/image still arrives when the brain
        # finishes and overwrites this. A brief excited beat, then the thinking
        # animation runs for the rest of the wait (which you're fine with).
        if looks_like_image_request(txt):
            self.msg = random.choice(_IMG_ACK_LINES)
            # excited for a moment as the acknowledgment lands, then thinking
            # carries the rest of the (long) generation wait
            self.set_emote("excited", 3)
            self.root.after(3000, lambda: self.set_emote("thinking", 182)
                            if self.msg else None)
        else:
            self.msg = "..."
            self.set_emote("thinking", 185)
        # Thinking/ack must stay up at least as long as brain_worker's own
        # network timeout (180s) - otherwise a legitimately-slow request
        # (cold-start image gen, or queued behind another one) makes the
        # animation give up and look "failed" right before the real
        # result arrives. 185s gives a small buffer beyond that timeout.
        self.msg_until = time.time() + 185
        threading.Thread(target=self.brain_worker, args=(txt,),
                         daemon=True).start()

    def brain_worker(self, txt):
        """Pure thin client. Send text (+ running history) to Buddy AI -
        the ONE brain - and display exactly whatever comes back. No
        persona, no tool logic, no image-gen code lives here at all
        anymore; Buddy AI owns everything, so this always matches
        whatever capabilities the brain has, even as they grow."""
        try:
            body = json.dumps({"text": txt,
                               "history": self.chat_history}).encode()
            req = urllib.request.Request(
                BUDDY_AI_URL + "/chat", data=body,
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=180) as r:
                out = json.loads(r.read().decode())
        except Exception as e:
            self.results.put({"text": f"Brain hiccup: {type(e).__name__} - "
                              "is Buddy AI running?", "emote": "worried"})
            return

        self.chat_history = out.get("history", self.chat_history)[-16:]
        result = {"text": out.get("text", "\u2728"),
                  "emote": out.get("emote", "happy")}
        if out.get("image_path"):
            result["image"] = out["image_path"]
        self.results.put(result)

    def show_image_window(self, path):
        """Display a generated image in a coral-framed popup."""
        try:
            from PIL import Image, ImageTk
        except ImportError:
            return
        try:
            win = tk.Toplevel(self.root)
            win.title("Buddy made this")
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            win.configure(bg=BODY)
            img = Image.open(path)
            disp = 460
            img.thumbnail((disp, disp))
            photo = ImageTk.PhotoImage(img)
            frame = tk.Frame(win, bg=BODY, bd=0)
            frame.pack(padx=4, pady=4)
            lbl = tk.Label(frame, image=photo, bg=BODY, bd=0)
            lbl.image = photo  # keep ref
            lbl.pack(padx=6, pady=(6, 2))
            bar = tk.Frame(frame, bg=BODY)
            bar.pack(fill="x", pady=(0, 4))
            tk.Label(bar, text="\u2728 made by Buddy", bg=BODY, fg="#FFFFFF",
                     font=("Segoe UI", 9, "italic")).pack(side="left", padx=8)
            tk.Button(bar, text="Save As...", bd=0, bg="#FBEDE6", fg=INK,
                      font=("Segoe UI", 8, "bold"), cursor="hand2",
                      command=lambda: self._save_image(path)).pack(
                          side="right", padx=4)
            tk.Button(bar, text="Close", bd=0, bg="#FBEDE6", fg=INK,
                      font=("Segoe UI", 8, "bold"), cursor="hand2",
                      command=win.destroy).pack(side="right", padx=4)
            # center on screen
            win.update_idletasks()
            sw = win.winfo_screenwidth()
            sh = win.winfo_screenheight()
            ww = win.winfo_width()
            wh = win.winfo_height()
            win.geometry(f"+{(sw-ww)//2}+{(sh-wh)//2}")
            # drag support
            def press(e):
                win._dx, win._dy = e.x, e.y
            def drag(e):
                win.geometry(f"+{win.winfo_x()+e.x-win._dx}"
                             f"+{win.winfo_y()+e.y-win._dy}")
            lbl.bind("<Button-1>", press)
            lbl.bind("<B1-Motion>", drag)
        except Exception:
            pass

    def _save_image(self, path):
        try:
            from tkinter import filedialog
            import shutil
            dst = filedialog.asksaveasfilename(
                defaultextension=".png",
                filetypes=[("PNG image", "*.png")],
                initialfile=os.path.basename(path))
            if dst:
                shutil.copy(path, dst)
        except Exception:
            pass

    def check_queue(self):
        try:
            while True:
                d = self.results.get_nowait()
                self.msg = str(d.get("text", ""))
                self.msg_until = time.time() + max(
                    14.0, min(60.0, len(self.msg) / 3.0))
                # Emoji in the actual reply text ALWAYS wins; the JSON "emote"
                # tag is only the fallback when the text has no emotion emoji.
                # (This mirrors the inbox path. Previously check_queue used the
                # JSON tag alone and fell straight to "happy", so emoji in the
                # reply were ignored and Buddy over-defaulted to happy.)
                emoji_emote = emote_from_text(self.msg)
                if emoji_emote:
                    chosen = emoji_emote
                else:
                    chosen = d.get("emote") or "happy"
                self.set_emote(chosen, 20)
                stamp = time.strftime("%Y-%m-%d %H:%M:%S")
                with open(LOG, "a", encoding="utf-8") as lg:
                    lg.write(f"[{stamp}] BUDDY: {self.msg}\n")
                if d.get("image"):
                    self.show_image_window(d["image"])
                self.root.deiconify()
                self.root.lift()
        except _queue.Empty:
            pass
        self.root.after(300, self.check_queue)

    def clear_msg(self):
        self.msg = ""
        self.msg_until = 0

    def set_emote(self, name, dur):
        # resolve known near-miss names (e.g. the model's "guilty") first, then
        # fall back to happy for anything still unrecognised. This runs for both
        # the emoji path and the JSON-tag path, since both call set_emote.
        name = EMOTE_ALIASES.get(name, name)
        if name not in EMOTES:
            name = "happy"
        self.emote = name
        self.emote_until = time.time() + dur
        if name == "rofl":
            # anchor the choreographed cycle to NOW so it always starts
            # from the top (rest -> launch -> spin -> land) the moment
            # rofl is triggered, instead of jumping in mid-tumble.
            self._rofl_t0 = self.phase
        if name == "relieved":
            # anchor relieved too: the forehead wipe is a ONE-TIME gesture
            # (Chloe: "he raises his arm one single time, does the wipe, and
            # puts his arms back"). Without an anchor it would loop forever.
            self._relieved_t0 = self.phase
        if name == "yawn":
            # a yawn is a one-shot EVENT (build -> peak -> close -> drowsy),
            # not a looping state - that's what separates it from `sleepy`.
            self._yawn_t0 = self.phase
        if name == "cool":
            # the shades DROP IN ONCE on arrival and then stay on his face.
            # Anchored, or they'd re-drop forever.
            self._cool_t0 = self.phase
        if name == "sad_simple":
            # his ears and antennae WILT ONCE, on arrival. Anchored, or the
            # wilt would already be over before he even got here.
            self._sad_t0 = self.phase
        if name == "surprised":
            # the startle is a ONE-SHOT EVENT (anticipate -> jump -> hang ->
            # come down -> residual "oh"). That it RESOLVES is the whole thing
            # separating it from mind_blown / terrified / alert, which are all
            # sustained states. Anchored, or he'd jump forever.
            self._surprised_t0 = self.phase
        if name == "embarrassed":
            # the flush BLOOMS ONCE on arrival and then keeps pulsing (he
            # keeps re-realising). Anchored, or the bloom would already be
            # over before he got here.
            self._emb_t0 = self.phase
        if name == "pleading":
            # he LEANS IN toward you once on arrival (he's asking YOU), then
            # settles into the hopeful bounce. Anchored, or the lean-in is
            # already over before he gets here.
            self._plead_t0 = self.phase
        if name == "scared":
            # he COWERS ONCE on arrival (drops into a crouch and stays there),
            # then trembles and flinches from that crouch. Anchored, or the
            # cower would already be over before he got here.
            self._scared_t0 = self.phase
        if name == "crying":
            # anchor the tear cycle so the FIRST tear wells right after he
            # arrives, instead of him turning up halfway through a pause.
            self._cry_t0 = self.phase
        if name == "sobbing":
            self._sob_t0 = self.phase
        if name == "disappointed":
            # he DEFLATES ONCE on arrival. Anchored, or the drop would already
            # be over before he got here and he'd just stand there squashed.
            self._disap_t0 = self.phase
        if name == "exhausted":
            # he SAGS once on arrival, then rallies-and-fails from there.
            self._exh_t0 = self.phase
        if name == "frustrated":
            # the wind-up starts fresh, so he BUILDS from the moment he arrives
            # rather than turning up mid-burst.
            self._frus_t0 = self.phase
        if name == "huffing":
            # he arrives on an INHALE and snorts from there, rather than turning
            # up halfway through a blast with steam already in the air.
            self._huff_t0 = self.phase
        if name == "mad":
            # he SETTLES into the held scowl on arrival, then shudders on cue.
            self._mad_t0 = self.phase
        if name == "angry":
            self._angry_t0 = self.phase
        if name == "furious":
            self._fur_t0 = self.phase
        if name == "mischievous":
            self._misc_t0 = self.phase
        if name in ("celebrate", "excited"):
            self.spawn_confetti(26 if name == "celebrate" else 10)

    def spawn_confetti(self, n):
        cols = ["#E0455A", "#F2B84B", "#4BA3F2", "#6BCB77", "#D97757"]
        for _ in range(n):
            self.particles.append({
                "x": random.uniform(20, self.w - 20),
                "y": random.uniform(-40, 40),
                "vy": random.uniform(1.5, 3.5),
                "vx": random.uniform(-0.8, 0.8),
                "c": random.choice(cols),
                "s": random.uniform(3, 6)})

    def poll(self):
        try:
            if os.path.exists(INBOX):
                with open(INBOX, "r", encoding="utf-8-sig") as f:
                    raw = f.read().strip().lstrip("\ufeff")
                os.remove(INBOX)
                text, emote = raw, "idle"
                if raw.startswith("{"):
                    try:
                        d = json.loads(raw)
                        text = str(d.get("text", ""))
                        emote = str(d.get("emote", "idle"))
                    except (ValueError, TypeError):
                        pass
                if emote not in EMOTES:
                    emote = "idle"
                # emoji in the actual reply text ALWAYS wins - the JSON
                # tag is only the fallback when no emotion emoji is sent
                emoji_emote = emote_from_text(text)
                if emoji_emote:
                    emote = emoji_emote
                if text:
                    self.msg = text
                    self.msg_until = time.time() + 30
                self.set_emote(emote, 30 if text else 8)
                with open(LOG, "a", encoding="utf-8") as lg:
                    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
                    lg.write(f"[{stamp}] {emote.upper()}: {text}\n")
                self.root.deiconify()
                self.root.lift()
        except OSError:
            pass
        now = time.time()
        if self.msg and now > self.msg_until:
            self.msg = ""
        if self.emote != "idle" and now > self.emote_until:
            self.emote = "idle"
        self.root.after(400, self.poll)

    def tick(self):
        self.phase += 0.12
        spd = 3.0 if self.emote in ('excited', 'celebrate') else 1.0
        self.ant_a += 0.037 * spd
        self.ant_b += 0.055 * spd
        if self.msg:
            try:
                ok = self.bubble_win and self.bubble_win.winfo_exists()
            except tk.TclError:
                ok = False
            try:
                if not ok:
                    self._show_bubble()
                elif self._bubble_msg != self.msg:
                    # message changed: RE-MEASURE and resize for the new text
                    # (a plain itemconfigure would keep the old height and
                    # clip/overflow). Rebuild from scratch.
                    try:
                        self.bubble_win.destroy()
                    except tk.TclError:
                        pass
                    self.bubble_win = None
                    self._bubble_cv = None
                    self._show_bubble()
                self._place_bubble()
            except tk.TclError:
                # never let a bubble hiccup leave an empty/dead window - drop
                # it and let the next tick rebuild cleanly.
                try:
                    if self.bubble_win:
                        self.bubble_win.destroy()
                except tk.TclError:
                    pass
                self.bubble_win = None
                self._bubble_cv = None
        else:
            try:
                if self.bubble_win and self.bubble_win.winfo_exists():
                    self.bubble_win.destroy()
            except tk.TclError:
                pass
            self.bubble_win = None
        now = time.time()
        if now >= self.next_blink:
            self.blink_until = now + 0.15
            self.next_blink = now + random.uniform(2.5, 6)
        alive = []
        for p in self.particles:
            p["y"] += p["vy"]
            p["x"] += p["vx"]
            if p["y"] < self.h - 10:
                alive.append(p)
        self.particles = alive
        if self.emote == "celebrate" and random.random() < 0.15:
            self.spawn_confetti(3)
        # SAFETY NET: a rendering bug (current or future) must NEVER be
        # able to freeze this loop or leave him invisible again - catch
        # anything, log it, fall back to the known-safe idle state, and
        # the reschedule below always runs regardless.
        try:
            self.draw(now < self.blink_until)
        except Exception as e:
            try:
                import traceback as _tb
                with open(LOG, "a", encoding="utf-8") as lg:
                    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
                    lg.write(f"[{stamp}] DRAW ERROR (falling back to "
                            f"idle): {type(e).__name__}: {e}\n")
                    lg.write(_tb.format_exc() + "\n")
            except OSError:
                pass
            self.emote = "idle"
            try:
                self.draw(False)
            except Exception:
                pass
        self.root.after(40, self.tick)

    def _bake_lips(self):
        """Render the color lips glyph from the OS emoji font ONCE,
        cropped to its own bounds, for the kiss 'blow a kiss' animation
        (scaled per frame). Returns None if the font isn't available, in
        which case the kiss branch falls back to a vector lips."""
        try:
            from PIL import ImageFont
            img = Image.new("RGBA", (220, 220), (0, 0, 0, 0))
            font = ImageFont.truetype(r"C:\Windows\Fonts\seguiemj.ttf", 137)
            ImageDraw.Draw(img).text((24, 18), "\U0001F48B", font=font,
                                     embedded_color=True)
            bbox = img.getbbox()
            return img.crop(bbox) if bbox else None
        except Exception:
            return None

    def _rofl_cycle(self, ph):
        """Choreographed rolling-on-floor cycle. Instead of the rings
        tracking his feet (which clipped/looked broken as he spun), the
        rings stay put in their normal upright spot and he LAUNCHES off
        them: a small hop up shoves the plume down out of frame, he does
        N full ringless rotations, then the rings rise back to meet his
        feet at the very tail and he lands. Loops while rofl is active;
        if the emote times out mid-cycle it just cuts to idle (fine).

        Returns (roll_deg, body_dy, ring_drop):
          roll_deg  - body rotation; 0 until launch, eases to N*360 across
                      the spin, held upright through the return/settle.
          body_dy   - vertical hop (negative = up) off the rings.
          ring_drop - how far the world-space plume is pushed DOWN
                      (positive = off-frame) during launch/spin.
        phase advances ~3.0/sec, so CYCLE=21 -> ~7s per full cycle."""
        CYCLE = 21.0
        u = ((ph - self._rofl_t0) / CYCLE) % 1.0

        def sm(a, b, x):                     # smoothstep ease a->b
            if x <= a:
                return 0.0
            if x >= b:
                return 1.0
            t = (x - a) / (b - a)
            return t * t * (3 - 2 * t)

        # phase boundaries: rest | launch | spin | return | settle
        R0, R1, R2, R3 = 0.08, 0.20, 0.82, 0.94
        HOP, DROP, NROT = 26.0, 210.0, 3
        up = sm(R0, R1, u)                   # 0->1 as he launches
        down = sm(R2, R3, u)                 # 0->1 as he returns
        env = up - down                      # 1 through the spin, 0 at rest
        body_dy = -HOP * env                 # hop up, then back down to land
        ring_drop = DROP * env               # plume dives off-frame, then rises
        roll_deg = NROT * 360.0 * sm(R1, R2, u)   # lands back at upright
        # foot push: one foot extends DOWN during the launch to sell the
        # jump - a smooth pulse peaking mid-launch, gone by the time he
        # leaves the ground and starts to spin.
        if R0 < u < R1:
            p = (u - R0) / (R1 - R0)
            foot_ext = math.sin(math.pi * p)
        else:
            foot_ext = 0.0
        return roll_deg, body_dy, ring_drop, foot_ext

    def draw(self, blinking):
        cv = self.cv
        cv.delete("all")
        ph = self.phase
        em = self.emote
        dx = 0.0
        rofl_ring_drop = 0.0   # set in the rofl branch; ring section reads it
        if em == "excited":
            bob = -abs(math.sin(ph * 2.2)) * 12
        elif em == "celebrate":
            bob = -abs(math.sin(ph * 2.6)) * 16
        elif em == "alert" or em == "mind_blown":
            bob = 0
            dx = math.sin(ph * 9) * 4
        elif em == "sleepy":
            bob = math.sin(ph * 0.5) * 3
        elif em == "exhausted":
            # *** THE RALLY THAT FAILS - EXPRESSED AS AN ACTUAL DROOP. ***
            # First pass drove this entirely off `bob`, and Chloe called it:
            # "the thing you're calling a droop is just this whole entire body
            # uniformly sinking lower on the screen. It's not head and arm
            # droop." Exactly right. `bob` TRANSLATES THE WHOLE SPRITE - a
            # sprite sliding down the screen is not a character sagging.
            #
            # So the droop now lives in self._exh_droop (0..1), and skin's
            # frame() turns it into REAL deformation: head sinking into the
            # shoulders, ears wilting, arms going limp, antennae drooping -
            # while his BODY and FEET stay put.
            #
            # The RALLY is expressed THROUGH the droop: he hauls his head up,
            # his ears half-perk... and it all falls again. bob is now only a
            # small residual sag, not the effect itself.
            el = max(0.0, ph - self._exh_t0)
            settle = 1.0 - math.exp(-el * 1.5)      # the droop falls in ONCE
            # ph rises 3.0/sec, so rate 0.133 = ONE RALLY EVERY ~2.5s.
            u = (ph * 0.133) % 1.0
            if u < 0.22:
                lift = math.sin((u / 0.22) * math.pi)   # sharp heave UP
            else:
                lift = 0.0                              # and back to hanging
            self._exh_droop = settle * (1.0 - 0.62 * lift)
            bob = 3.2 * settle - 2.2 * lift * settle
            dx = 0.0
        elif em == "disappointed":
            # *** THE LETDOWN. *** Split out of the shared sleepy/disappointed/
            # exhausted bob - he is not drowsy, he is DEFLATED.
            # He SLUMPS once, it LANDS, and then he goes STILL.
            # >>> THE STILLNESS AFTER THE DROP IS THE EMOTION. He's stopped
            #     hoping, so there is almost nothing left moving - just a
            #     shallow, flat breath.
            # The deliberate inverse of sad_simple, whose sigh is PERIODIC and
            # NEVER ARRIVES. This one arrives and stays arrived.
            # (The VERTICAL SQUASH that goes with it is in the PIL chain.)
            el = max(0.0, ph - self._disap_t0)
            drop = 1.0 - math.exp(-el * 1.9)
            bob = 9.0 * drop + math.sin(ph * 0.55) * 0.7
            dx = 0.0
        elif em == "pensive":
            # THE WEIGHT OF THE THOUGHT. He sinks - shoulders settling down -
            # and then HOLDS there. Pulled out of the shared slow-bob that
            # sleepy/disappointed/exhausted use, because pensive isn't drowsy
            # or defeated: he's awake, still, and thinking.
            # An exponential ease means he drops quickly at first and then
            # STAYS sunk (a settled posture, like skeptical's held cock),
            # rather than endlessly bobbing.
            sink = 3.4 * (1.0 - math.exp(-ph * 0.55))
            # slow, deep breathing over the top - melancholy is STILL, so
            # this is nearly the only thing moving
            breathe = math.sin(ph * 0.52) * 1.5
            bob = sink + breathe
        elif em == "sad_simple":
            # THE SIGH THAT NEVER LANDS.
            # Deliberately NOT pensive's sink-and-hold. Pensive eases down to
            # a settled posture and STAYS there (an exponential to an
            # asymptote). This one is PERIODIC and never arrives: he draws a
            # breath, holds it, lets it go with a drop of the shoulders, sags,
            # and then has to do the whole thing again. He can't find a
            # resting place. Same relationship as confused (reverses) vs
            # skeptical (settles) - the MOTION SHAPE is the separator.
            # *** MAKE IT BIG ENOUGH TO SEE. *** First pass moved him a total
            # of 6.2px across a 5s cycle - pensive's idle BREATHING is already
            # +-1.5px, so I built a "sigh" barely louder than background noise
            # and Chloe (correctly) saw nothing. Now: 16px of travel, a fast
            # exhale, and a 4s cycle so several land inside one 20s trigger.
            # The SLOW-IN / FAST-COLLAPSE contrast is what makes it read as a
            # sigh rather than a bob.
            SG = 12.0                       # ~4s per sigh (ph = 3.0/sec)
            ug = (ph / SG) % 1.0
            if ug < 0.38:                   # INHALE - slow lift
                k = ug / 0.38
                bob = -5.0 * (k * k * (3 - 2 * k))
            elif ug < 0.48:                 # the held breath
                bob = -5.0
            elif ug < 0.58:                 # EXHALE - fast. The shoulders GO.
                k = (ug - 0.48) / 0.10
                bob = -5.0 + 16.0 * (k * k * (3 - 2 * k))
            else:                           # sagging, creeping slowly back
                k = (ug - 0.58) / 0.42
                bob = 11.0 * (1.0 - k * k * (3 - 2 * k))
            dx = 0.0
            # The ear/antenna wilt rides this SAME cycle - stash ug so the
            # sag and the sigh can never drift apart from a stray retune.
            self._sad_ug = ug
        elif em == "surprised":
            # THE STARTLE. An EVENT, not a state - that is the entire
            # separation from mind_blown / terrified / alert / speechless,
            # which are all sustained conditions he just sits in.
            # Anchored one-shot (self._surprised_t0), like cool / relieved /
            # yawn - or it would re-jump forever.
            # ph advances 3.0/sec, so these are in ph-units:
            el = max(0.0, ph - self._surprised_t0)
            if el < 0.18:              # ~0.06s of ANTICIPATION. He dips.
                bob = 2.0 * (el / 0.18)
            elif el < 0.60:            # THE JUMP. ~0.14s. Fast and sharp.
                k = (el - 0.18) / 0.42
                bob = 2.0 - 20.0 * (k * k * (3 - 2 * k))
            elif el < 1.80:            # HANGS at the top, eyes out on stalks
                bob = -18.0 + 1.2 * math.sin((el - 0.60) * 5.0)
            elif el < 3.30:            # comes down, with a small overshoot
                k = (el - 1.80) / 1.50
                bob = -18.0 + 20.5 * (k * k * (3 - 2 * k))
            else:                      # settled. A soft residual breath.
                bob = 2.5 + math.sin((el - 3.30) * 0.9) * 1.2
            dx = 0.0
            # 18px of travel against an idle bob of ~2px. Deliberately loud:
            # the LAST two emotes both failed review for being too subtle to
            # see, so the amplitude gets checked against the noise floor now.
            self._surprised_el = el
        elif em == "embarrassed":
            # He SINKS as he shrinks - trying to get smaller and lower, to be
            # less of a target. Slight, because the SHRINK (in the PIL chain
            # below) is the loud part; this just stops him standing at full
            # height while he does it.
            el = max(0.0, ph - self._emb_t0)
            bob = 4.5 * (1.0 - math.exp(-el * 1.0)) \
                + math.sin(ph * 0.8) * 0.8
            dx = 0.0
        elif em == "pleading":
            # THE HOPEFUL BOUNCE. He rocks up on his toes, expectant, over and
            # over - the body language of someone waiting for a yes.
            # Kept clear of its neighbours by SPEED and SIZE:
            #   excited  = -abs(sin(ph*2.2)) * 12  -> fast and big (bouncing).
            #   pleading = -abs(sin(ph*1.0)) * 7   -> slow and hopeful (asking).
            #   sad_simple = a 16px sigh over a 4s cycle -> heavy, falling.
            # 7px against an idle bob of ~2px, so it clears the noise floor -
            # the mistake sad_simple failed review for TWICE.
            el = max(0.0, ph - self._plead_t0)
            lean = 1.0 - math.exp(-el * 1.4)          # he leans in, once
            bob = -abs(math.sin(ph * 1.0)) * 7.0 + 2.0 * lean
            dx = math.sin(ph * 0.5) * 1.6             # a small hopeful sway
        elif em == "scared":
            # HE CANNOT HOLD STILL. Three layers, and the FLINCH is the one
            # that makes this emote:
            #   1. THE COWER - he drops into a crouch on arrival and stays low.
            #   2. A fine constant fear TREMBLE.
            #   3. *** THE FLINCHES *** - sudden hard JOLTS at IRREGULAR
            #      intervals, as though something just moved at the edge of his
            #      vision. Two detuned drivers (0.43 and 0.31) beat against
            #      each other so the jolts NEVER settle into a rhythm.
            # That irregularity is the whole separation from `cold`, whose
            # shiver is a fast, tight, perfectly REGULAR metronome. A tremble
            # you can predict is cold. A tremble you can't is fear.
            # And it stays clear of `alert` (a nonstop sideways rattle) and of
            # `embarrassed` (a smooth shrink + lean, with a red face).
            el = max(0.0, ph - self._scared_t0)
            cower = 7.0 * (1.0 - math.exp(-el * 2.2))
            tremble = math.sin(ph * 19.0) * 1.3
            f1 = max(0.0, math.sin(ph * 0.43)) ** 24
            f2 = max(0.0, math.sin(ph * 0.31 + 2.1)) ** 24
            flinch = min(1.0, f1 + f2)
            # the jolt: he JERKS down and sideways. 10px, against a ~2px idle
            # floor, so it cannot be missed.
            bob = cower + tremble + 10.0 * flinch
            dx = math.sin(ph * 17.0) * 0.9 - 5.0 * flinch
        elif em == "anxious":
            # RAPID SHALLOW BREATHING. He is winding himself up and can't stop.
            # It is a BREATH, not a shake - a smooth rise and fall - which is
            # what keeps it off `cold` (a tight, fast, regular VIBRATION) and
            # off `scared` (a cower plus irregular JOLTS).
            # 6px against a ~2px idle floor, so it clears the noise floor - the
            # mistake sad_simple failed review for twice.
            # `worried`, the emote this must not become, has NO body motion at
            # all: a static face on the default idle bob.
            bob = math.sin(ph * 4.4) * 6.0 + math.sin(ph * 13.0) * 0.6
            dx = 0.0
        elif em == "crying":
            # HE IS TRYING NOT TO CRY, AND FAILING.
            # He SAGS, breathes slow and shallow, and every couple of seconds
            # a HITCH catches in his chest - the involuntary catch of someone
            # crying quietly and losing the fight to hide it.
            # Kept off its neighbours:
            #   anxious  = FAST rhythmic breathing (winding himself UP).
            #   scared   = a cower + BIG IRREGULAR jolts (something out there).
            #   sad_simple = one big slow 16px SIGH (resignation, no fight).
            #   crying   = a slow sag + a small, REGULAR, involuntary HITCH.
            # sobbing (next) gets the big heaving version of this. Crying is
            # the one he's still trying to suppress.
            el = max(0.0, ph - self._cry_t0)
            sag = 3.4 * (1.0 - math.exp(-el * 1.4))
            hitch = max(0.0, math.sin(ph * 0.62)) ** 16
            bob = sag + math.sin(ph * 0.85) * 1.2 - 5.5 * hitch
            dx = 0.0
        elif em == "sick":
            # FEVER: a slow, heavy, unwell sway - he can barely hold himself
            # up - punctuated by an occasional CHILL that runs through him.
            # Deliberately different from `cold` (a fast constant tight
            # tremble): here the shivers COME AND GO, which is what a fever
            # feels like, and between them he just sags.
            bob = math.sin(ph * 0.62) * 2.6 + 1.6      # slow, sunk low
            dx = math.sin(ph * 0.44) * 2.2             # listing side to side
            # chill: a burst of shivering every ~5s, fading in and out
            chill = max(0.0, math.sin(ph * 1.25)) ** 6
            dx += math.sin(ph * 26) * 2.4 * chill
            bob += math.sin(ph * 31) * 1.1 * chill
        elif em in ("laughing", "laughing_crying"):
            bob = math.sin(ph * 7) * 3
        elif em == "rofl":
            bob = math.sin(ph * 7) * 3 + 4
        elif em == "sobbing":
            # *** HE HEAVES. *** Crying is restraint that keeps losing;
            # sobbing is restraint GONE. Big shuddering convulsions that rack
            # his whole body, not crying's small suppressed hitch.
            # SPLIT OUT of the old shared branch - sobbing, frustrated and
            # furious were ALL running bob=sin(ph*1.2)*2, dx=sin(ph*13)*3 off
            # one line. frustrated and furious keep that for now; each still
            # needs its own.
            # The sob: a sharp deep LURCH, then a ragged recovery. Cubing a
            # raised sine gives the sharp peak + long trough of a real sob.
            #   crying  = a 5.5px HITCH he is trying to suppress.
            #   sobbing = an 11px HEAVE he has stopped trying to suppress.
            el = max(0.0, ph - self._sob_t0)
            sink = 5.0 * (1.0 - math.exp(-el * 1.8))
            sob = ((math.sin(ph * 2.6) * 0.5) + 0.5) ** 3
            bob = sink + 11.0 * sob + math.sin(ph * 21.0) * 0.9
            dx = math.sin(ph * 2.6 + 0.7) * 1.6
        elif em == "frustrated":
            # *** THE WIND-UP AND RELEASE. *** He is STUCK, and it is BUILDING.
            # SPLIT OUT of the shared line with furious (they were both running
            # bob=sin(ph*1.2)*2, dx=sin(ph*13)*3 - twins).
            #
            # Frustration is EFFORT THAT GOES NOWHERE. So the tremble does not
            # sit at a constant level like a shiver - it WINDS UP. It starts
            # small, gets harder and harder as the pressure builds, peaks in a
            # BURST... and then drops to nothing and starts winding up again.
            # *** IT NEVER DISCHARGES. THAT CYCLE IS THE EMOTE. ***
            #   cold    = a CONSTANT tight shiver (a metronome).
            #   scared  = a cower + IRREGULAR flinches.
            #   angry   = (coming) a STEADY seething burn.
            #   frustrated = a tremble that ESCALATES and resets. ~2.2s a cycle.
            # He also HUNCHES as he winds up - shoulders rising into it - and
            # drops on the burst.
            el = max(0.0, ph - self._frus_t0)
            settle = 1.0 - math.exp(-el * 2.2)
            u = (ph * 0.152) % 1.0                  # one build+burst per ~2.2s
            if u < 0.80:
                build = (u / 0.80) ** 2.2           # pressure RISING
                burst = 0.0
            else:
                build = 1.0
                burst = math.sin(((u - 0.80) / 0.20) * math.pi)   # THE RELEASE
            shake = 0.7 + 5.6 * build               # the tremble ESCALATES
            bob = settle * (-3.2 * build + 7.0 * burst
                            + math.sin(ph * 24.0) * shake * 0.35)
            dx = settle * (math.sin(ph * 19.0) * shake)
        elif em == "huffing":
            # *** THE SNORT. *** A SLOW SWELL as he draws the breath in, then a
            # SHARP DROP as he blasts it out of his nose.
            # >>> That is the deliberate MIRROR of exhausted, which is SHARP UP
            #     and SLOW DOWN (a rally that fails). Same machinery, opposite
            #     shape - so the two can never be mistaken for each other.
            # He is not raging, he is OFFENDED. The body is composed; it just
            # keeps puffing up and blasting off. ~1.6s a cycle.
            el = max(0.0, ph - self._huff_t0)
            settle = 1.0 - math.exp(-el * 2.6)
            # ph rises 3.0/sec, so rate 0.208 -> a snort every ~1.6s.
            u = (ph * 0.208) % 1.0
            if u < 0.62:
                s = u / 0.62
                b = -6.5 * (s ** 1.6)                    # SLOW swell UP
            else:
                s = (u - 0.62) / 0.38
                b = -6.5 + 9.5 * (1.0 - (1.0 - s) ** 3)  # SHARP blast DOWN
            self._huff_u = u
            bob = settle * b
            dx = 0.0
        elif em == "mischievous":
            # *** HE IS PLOTTING. *** The paws do the talking (they RUB - see
            # skin's _build_mischief_paws). The body just has to stay out of
            # their way and look pleased with itself.
            #   a slow, gleeful ROCK... and then a SNICKER: a quick 3-beat
            #   shoulder shake every ~2.6s, like he can't keep it in.
            # The snicker is what stops the rub reading as a NERVOUS FIDGET -
            # a fidget is anxious, but a fidget PLUS a private laugh is scheming.
            el = max(0.0, ph - self._misc_t0)
            settle = 1.0 - math.exp(-el * 2.4)
            self._misc_rub = (ph * 0.42) % 1.0        # ~0.8s per rub stroke
            # ph rises 3.0/sec -> rate 0.128 = a snicker every ~2.6s
            u = (ph * 0.128) % 1.0
            if u < 0.16:
                q = u / 0.16
                snick = math.sin(q * math.pi * 3.0) * math.sin(q * math.pi)
            else:
                snick = 0.0
            bob = settle * (math.sin(ph * 0.9) * 1.6 - 2.4 * abs(snick))
            dx = settle * (math.sin(ph * 0.6) * 1.8 + 2.2 * snick)
        elif em == "furious":
            # *** THE ERUPTION. THE TOP OF THE LADDER. ***
            # Finally split off frustrated's old shared line (bob=sin(ph*1.2)*2,
            # dx=sin(ph*13)*3), which the two of them ran for the whole project.
            #
            # He shakes VIOLENTLY and NEVER stops - and every ~2.2s he BLOWS,
            # launching upward as the flames flare and the cursing peaks.
            # The block, by how violent the shake is and whether it ever rests:
            #   mad        HOLDS STILL. dx exactly 0 for 95% of the time.
            #   angry      a CONSTANT 3.4px shudder. Never builds, never stops.
            #   frustrated ESCALATES 0.7 -> 6.3px, bursts, RESETS TO QUIET.
            #   furious    NEVER DROPS BELOW 4.0px and PEAKS AT 7.5px. He is the
            #              only one who is violent even at his calmest.
            el = max(0.0, ph - self._fur_t0)
            settle = 1.0 - math.exp(-el * 3.0)
            # ph rises 3.0/sec, so rate 0.152 -> he BLOWS every ~2.2s.
            u = (ph * 0.152) % 1.0
            erupt = math.sin((u / 0.12) * math.pi) if u < 0.12 else 0.0
            self._fur_erupt = erupt
            shake = 4.0 + 3.5 * erupt            # violent at rest, worse on the blow
            bob = settle * (-2.0 - 9.0 * erupt
                            + math.sin(ph * 26.0) * shake * 0.55)
            dx = settle * (math.sin(ph * 33.0) * shake)
        elif em == "mad":
            # *** A SCOWL, HELD. THE STILLNESS IS THE EMOTION. ***
            # Mad is the LOW END of the anger ladder, and its whole identity is
            # RESTRAINT. So it gets the one thing nothing else in the block has:
            # *** MAD IS THE ONLY ANGER EMOTE THAT DOESN'T SHAKE. ***
            #   frustrated = a tremble that ESCALATES, then bursts.
            #   huffing    = swells and SNORTS.
            #   angry      = (coming) a steady seething burn.
            #   furious    = (coming) an eruption.
            #   mad        = HOLDS STILL. Slow, controlled breathing - the
            #                breathing of someone counting to ten.
            # He is holding it in... and then every ~3.2s IT GETS OUT: ONE sharp
            # SHUDDER, about a sixth of a second, instantly suppressed. That
            # flash of losing control and clamping straight back down is what
            # sells "contained" - stillness alone would just read as idle.
            el = max(0.0, ph - self._mad_t0)
            settle = 1.0 - math.exp(-el * 2.0)
            breath = math.sin(ph * 0.62) * 2.6        # slow, deliberate, calm
            # ph rises 3.0/sec, so rate 0.104 -> the anger escapes every ~3.2s.
            u = (ph * 0.104) % 1.0
            if u < 0.05:
                q = u / 0.05
                env = math.sin(q * math.pi)           # a short, hard envelope
                jolt = math.sin(q * math.pi * 3.0) * env
                bob = settle * (breath - 3.0 * env)
                dx = settle * (3.4 * jolt)
            else:
                bob = settle * breath
                dx = 0.0                              # PERFECTLY still. No shake.
        elif em == "angry":
            # *** SEETHING. A STEADY, HEAVY BURN. ***
            # The middle rung of the ladder, and the tremble is what places it:
            #   mad        = HOLDS STILL. dx is exactly 0 for 95% of the time.
            #   frustrated = a tremble that ESCALATES 9x, then bursts, then
            #                resets. It never settles.
            #   angry      = a CONSTANT, heavy vibration. It does not build and
            #                it does not stop. He is just BURNING.
            #   furious    = (coming) an eruption.
            # LOWER frequency and BIGGER amplitude than cold/terrified, so it
            # reads as a powerful SHUDDER rather than a thin shiver:
            #   cold      = 27/34 at 1.3/1.7 px  (a shiver)
            #   terrified = 22/28 at 1.2/2.2 px  (a shiver)
            #   angry     = 17/21 at 2.6/3.4 px  (a SHUDDER)
            # Over the top, a slow SWELL of rage that the VEIN throbs in time
            # with - so the accent and the body cannot desync.
            el = max(0.0, ph - self._angry_t0)
            settle = 1.0 - math.exp(-el * 2.2)
            seethe = 0.5 + 0.5 * math.sin(ph * 1.05)   # the slow swell of it
            self._angry_throb = seethe
            bob = settle * (-1.8 - 1.6 * seethe + math.sin(ph * 17.0) * 2.6)
            dx = settle * (math.sin(ph * 21.0) * 3.4)
        elif em == "terrified":
            # frozen-with-fear tremble: a fast, tight shiver (a bit more
            # than cold) so he reads as shaking, not swaying
            bob = math.sin(ph * 22) * 1.2
            dx = math.sin(ph * 28) * 2.2
        elif em == "cold":
            # fast, tiny tremble = shivering (different freqs on each
            # axis so it jitters rather than sliding on a clean diagonal)
            bob = math.sin(ph * 27) * 1.3
            dx = math.sin(ph * 34) * 1.7
        elif em == "dizzy":
            # A TRUE CIRCULAR ORBIT, not a wobble. dx uses cos and bob uses
            # sin at the SAME frequency, so he traces an actual circle - the
            # room is spinning and he's going round with it.
            # *** This is what keeps him distinct from `zany`, *** which is a
            # woozy SWAY built from detuned sines (it never closes a loop).
            OR = 2.1
            bob = math.sin(ph * OR) * 4.2 + 1.5
            dx = math.cos(ph * OR) * 6.0
        elif em == "innocent":
            # cute head-tilt: the tilt (a gentle whole-sprite rotation) is
            # applied below; here just a soft bob, no sideways slide.
            bob = math.sin(ph * 0.9) * 2
            dx = 0
        else:
            bob = math.sin(ph) * 4
        bob = int(bob)
        dx = int(dx)
        cx = self.w // 2 + dx
        hy = HY + bob
        cy = CY + bob
        wave_angle = (-0.9 + math.sin(ph * 3) * 0.55) if em == "wave" \
            else None
        # innocent: `turn` is a FIXED cute head-tilt (deg) LOCKED to the
        # body - the head holds a constant cock relative to the body, and
        # the whole sprite (head + body together) does the gentle rock.
        turn = 8.0 if em == "innocent" else 0.0
        # relieved: a ONE-SHOT forehead wipe shortly after the trigger, then
        # the arm goes back to idle and he just breathes. Anchored to
        # _relieved_t0 so it fires once - not on a loop.
        wipe = None
        if em == "relieved":
            el = ph - self._relieved_t0          # seconds since triggered
            W0, W1 = 0.45, 2.35                  # wipe window
            if W0 <= el < W1:
                w = (el - W0) / (W1 - W0)
                # out-and-back: 0 -> 1 -> 0 across the brow, eased, so the
                # arm lifts, sweeps, and returns rather than snapping home
                wipe = math.sin(w * math.pi) ** 0.8
        # yawn: a ONE-SHOT event - builds, peaks wide, closes, leaves him
        # drowsy. (This is what separates yawn, an EVENT, from sleepy, a
        # STATE.) Anchored to the trigger so it doesn't loop.
        yawn = None
        if em == "yawn":
            ely = ph - self._yawn_t0
            Y0, Y1, Y2, Y3 = 0.35, 1.35, 2.05, 3.30
            if ely < Y0:
                yawn = 0.0
            elif ely < Y1:                       # BUILD - mouth stretches open
                t = (ely - Y0) / (Y1 - Y0)
                yawn = t * t * (3 - 2 * t)
            elif ely < Y2:                       # PEAK - held wide
                yawn = 1.0
            elif ely < Y3:                       # CLOSE - jaw comes back down
                t = (ely - Y2) / (Y3 - Y2)
                yawn = 1.0 - t * t * (3 - 2 * t)
            else:
                yawn = 0.0                       # drowsy, done
        # nauseated: green skin + a HUNCH-AND-PUKE. The green level and the
        # open/closed mouth are decided here and passed into frame(), because
        # the tint has to be applied to the FUR before the face is drawn (so
        # it can't green his eyes/nose/brows/mouth).
        nausea = None
        if em == "nauseated":
            NC = 5.2
            un = (ph / NC) % 1.0
            if un < 0.62:                      # queasy, holding it back
                pk = 0.0
            elif un < 0.72:                    # the hunch - he doubles over
                pk = (un - 0.62) / 0.10 * 0.35
            elif un < 0.90:                    # PUKING
                pk = 1.0
            else:                              # straightening back up
                pk = 1.0 - (un - 0.90) / 0.10
            self._puke = pk                    # motion block reads this
            self._puke_u = un
            green = 0.55 + 0.45 * min(1.0, pk * 1.4)
            nausea = (green, pk > 0.55)
        # hot: FAST SHALLOW PANTING. The mouth/tongue keyframe is chosen here
        # and passed into frame(); a frozen open mouth reads as surprise, not
        # panting - the RHYTHM is the signature.
        pant = None
        if em == "hot":
            # fast, shallow, slightly uneven (a real pant isn't a metronome)
            pant = 0.5 + 0.5 * math.sin(ph * 7.4)
            pant = max(0.0, min(1.0, pant * 0.92 + 0.05 * math.sin(ph * 3.1)))
            self._pant = pant                  # motion block reads this
        # dizzy: the eye SPIRALS spin. A frozen spiral reads as a pattern;
        # the turning is what sells vertigo.
        spin = None
        if em == "dizzy":
            # *** ph IS NOT SECONDS. *** The tick is 40ms and phase += 0.12,
            # so ph advances 3.0 units PER SECOND. Getting this wrong is what
            # broke the spin: ph*0.85 meant ~2.5 REVOLUTIONS PER SECOND, and
            # sampling 18 quantized keyframes at 25fps then advanced the index
            # by 1-2 steps unevenly each frame - textbook wagon-wheel
            # aliasing. Chloe: "they just twitch left and right... no
            # centrifugal spin at all."
            # 0.28 * 3.0 = ~0.84 revolutions/sec, which advances the keyframe
            # index by ~0.6 steps per frame - always forward, never skipping,
            # so it reads as a smooth continuous vortex.
            spin = (ph * 0.28) % 1.0
        # nerdy: the glasses SLIP DOWN his nose, and every few seconds he
        # shoves them back up with a paw. That push is the whole gesture.
        push = None
        if em == "nerdy":
            PC = 12.0                       # ~4s between pushes (ph = 3/sec)
            un = (ph / PC) % 1.0
            if un < 0.72:                   # they creep down the nose
                self._slip = (un / 0.72) * 3.8
                push = 0.0
            elif un < 0.88:                 # THE PUSH
                kp = (un - 0.72) / 0.16
                push = math.sin(kp * math.pi)          # arm up, then back
                # snap them up as the paw arrives (kp ~ 0.5)
                self._slip = 3.8 * max(0.0, 1.0 - kp / 0.5)
            else:                           # settled, freshly seated
                self._slip = 0.0
                push = 0.0
        # sad_simple: his EARS AND ANTENNAE WILT. They fall ONCE, on arrival -
        # anchored on self._sad_t0, or the wilt would already be long over by
        # the time he actually got here (the `cool` shades lesson) - and then
        # STAY down, sagging a touch further on every exhale.
        # Born -> falls -> lives -> stays. A lifecycle, not furniture.
        sad = None
        if em == "sad_simple":
            el = max(0.0, ph - self._sad_t0)
            wilt = 1.0 - math.exp(-el * 0.9)     # falls over ~1.5s, once
            ug = self._sad_ug                    # same cycle as the sigh
            if 0.48 <= ug < 0.58:                # extra sag through the exhale
                sag = (ug - 0.48) / 0.10
            elif ug >= 0.58:
                sag = 1.0 - (ug - 0.58) / 0.42
            else:
                sag = 0.0
            sad = wilt * (0.80 + 0.20 * sag)
        # surprised: the face POPS (eyes/pupils/brows/mouth all keyframed) and
        # the antennae SNAP BOLT UPRIGHT and shake. Both ride the same
        # anchored one-shot as the jump above, so they can never desync.
        surprise = None
        if em == "surprised":
            el = self._surprised_el
            if el < 0.18:                       # anticipation - not yet
                k = 0.0
            elif el < 0.60:                     # the POP, with the jump
                k = (el - 0.18) / 0.42
            elif el < 1.80:                     # held wide at the top
                k = 1.0
            elif el < 3.30:                     # relaxing back down
                k = 1.0 - 0.62 * ((el - 1.80) / 1.50)
            else:                               # residual "...oh."
                k = 0.38
            # the antenna quiver: fast, and it DIES OFF as he recovers, so it
            # is an effect with a lifecycle rather than a permanent vibration
            # (which is also what keeps it clear of `alert`, whose sideways
            # body shake never stops).
            decay = math.exp(-max(0.0, el - 0.60) * 1.1)
            qv = math.sin(ph * 24.0) * decay
            surprise = (k, qv)
        plead = None
        if em == "pleading":
            # the shimmer phase for the wet eyes and the quivering pout.
            # ph advances 3.0 units/sec, so ph * 0.30 gives a full shimmer
            # cycle about every 1.1s - a slow, wet, hopeful glisten rather
            # than a nervous flicker.
            plead = (ph * 0.30) % 1.0
        scare = None
        if em == "scared":
            # the eye-jitter STEP. ph advances 3.0/sec and the tick is 40ms, so
            # ph rises 0.12 per frame; ph * 8 therefore advances the index by
            # ~0.96 per frame - just under one step. That is deliberate: the
            # index must never jump more than 1 step per frame or the jitter
            # ALIASES and reads as a smooth drift instead of a vibration (the
            # wagon-wheel bug that cost dizzy several passes).
            scare = int(ph * 8.0)
        droop = None
        if em == "exhausted":
            # THE REAL DROOP: head sinks, ears wilt, arms go limp, antennae
            # fall - while his body and feet stay put. Computed in the bob
            # section so the rally and the droop cannot desync.
            droop = self._exh_droop
        scheme = None
        if em == "mischievous":
            # THE PAW-RUB. Computed in the bob section so the rub and the
            # snicker cannot desync.
            scheme = self._misc_rub
        frame = self.skin.frame(em, blinking, wave_angle,
                                self.ant_a, self.ant_b, turn, wipe, yawn,
                                nausea, pant, spin, push, sad, surprise,
                                plead, scare, droop, scheme)
        bg = Image.new("RGB", (self.w, self.h), TRANS_RGB)
        if em == "rofl":
            # TRUE tumble: a full continuous rotation of the actual
            # transparent character sprite, so he genuinely passes
            # through lying-on-his-side (horizontal), not just an
            # upright squash. Mouth + tears are baked directly onto
            # this same RGBA frame BEFORE rotating, so they spin with
            # him instead of floating separately. Rotating the RGBA
            # image (not a magenta-keyed RGB one) means the smoothed
            # edges blend to transparent, not magenta.
            fd = ImageDraw.Draw(frame)
            op = 0.35 + 0.65 * abs(math.sin(ph * 6))
            mw, mh = 11.5, 3.0 + 5.0 * op
            mcx, mcy = HX, HY + 19
            mpts = [
                (mcx - mw, mcy - mh * 0.55),
                (mcx - mw * 0.5, mcy - mh * 0.95),
                (mcx, mcy - mh), (mcx + mw * 0.5, mcy - mh * 0.95),
                (mcx + mw, mcy - mh * 0.55),
                (mcx + mw * 0.62, mcy + mh * 0.5),
                (mcx, mcy + mh), (mcx - mw * 0.62, mcy + mh * 0.5)]
            fd.polygon(mpts, fill=(108, 60, 46, 255),
                      outline=(46, 33, 25, 255))
            if op > 0.45:
                fd.rectangle([mcx - 6, mcy - mh, mcx + 6, mcy - mh + 4],
                            fill=(255, 252, 246, 255),
                            outline=(46, 33, 25, 255))
            for sxo in (-16, 16):
                drip = (ph * 44 + (12 if sxo > 0 else 0)) % 26
                fd.line([(HX + sxo, HY + 8 + drip),
                        (HX + sxo, HY + 14 + drip)],
                       fill=(127, 196, 232, 255), width=4)
            # rofl is a CHOREOGRAPHED launch -> spin -> return cycle (see
            # _rofl_cycle). The rings do NOT rotate or track his feet -
            # they stay in the normal upright world-space spot and are
            # drawn at canvas level below. Here we take his rotation and
            # how far his body has HOPPED up off the rings; rofl_ring_drop
            # is handed to the ring section so the plume dives off-frame
            # during the spin and rises back to his feet at the tail.
            roll_deg, rofl_body_dy, rofl_ring_drop, foot_ext = \
                self._rofl_cycle(ph)
            # one foot extends straight DOWN during the launch to sell the
            # push-off (he's still upright here - rotation only starts
            # after the launch). Baked onto the sprite before cropping so
            # it stays put with the body.
            if foot_ext > 0.02:
                e = foot_ext * 16.0
                fx = CX - 22
                fd.polygon([(fx - 11, CY + 66), (fx + 11, CY + 66),
                            (fx + 9, CY + 82 + e), (fx - 9, CY + 82 + e)],
                           fill=PAW_BOT + (255,))
                fd.ellipse([fx - 15, CY + 76 + e, fx + 15, CY + 92 + e],
                           fill=PAW_TOP + (255,),
                           outline=SKIN_EDGE + (255,), width=2)
            # crop to a TIGHT box around him+rings before rotating -
            # rotating the full mostly-empty 380x430 frame ballooned
            # the diagonal bounding box to ~518x518, forcing a ~30%
            # shrink to fit back in the window. That shrink was
            # squashing the already-small outer rings down near
            # invisible, which read as "cut off". A tight crop keeps
            # the worst-case rotated size ~316x315 - fits at full
            # scale (1.0) with zero shrinking at every angle.
            cropped = frame.crop((110, 125, 270, 410))
            rotated = cropped.rotate(roll_deg, expand=True,
                                     resample=Image.BICUBIC)
            max_w, max_h = self.w - 16, self.h - 16
            scale = min(1.0, max_w / rotated.width, max_h / rotated.height)
            rw = max(1, int(rotated.width * scale))
            rh = max(1, int(rotated.height * scale))
            rotated = rotated.resize((rw, rh), Image.LANCZOS)
            mask = rotated.getchannel("A").point(
                lambda a: 255 if a >= 110 else 0)
            bg.paste(rotated,
                     (self.w // 2 - rw // 2,
                      int(235 - rh // 2 + rofl_body_dy)), mask)
        else:
            if em == "awkward":
                # shifty eyes baked onto the RGBA sprite BEFORE the tilt
                # (so they rotate with the face), then a slight head TILT
                # (pivot near the feet so he leans rather than slides).
                fd2 = ImageDraw.Draw(frame)
                # sporadic shifty eyes: a pseudo-random target (-1 left /
                # 0 center / +1 right) per beat, HELD then quick-snapped to
                # the next at a pseudo-random moment - irregular, not a
                # smooth metronome sweep. Both beads share the offset.
                rnd = lambda n: (math.sin(n * 12.9898 + 78.233)
                                 * 43758.5453) % 1.0

                def _tgt(n):
                    v = rnd(n * 1.7 + 3.0)
                    return -1.0 if v < 0.40 else (1.0 if v > 0.63 else 0.0)
                beat = ph * 0.5
                bi = int(beat)
                frac = beat - bi
                prev = _tgt(bi)
                nxt = _tgt(bi + 1)
                snap = 0.55 + 0.40 * rnd(bi + 91.0)
                if frac < snap:
                    pos = prev
                else:
                    k = min(1.0, (frac - snap) / max(1e-3, 1.0 - snap))
                    k = k * k * (3 - 2 * k)
                    pos = prev + (nxt - prev) * k
                dart = pos * 5.4
                for exb in (HX - 16, HX + 16):
                    ex = exb + dart
                    r = 8.5
                    fd2.ellipse([ex - r * 0.86, HY - 4 - r,
                                 ex + r * 0.86, HY - 4 + r],
                                fill=(58, 42, 34, 255))
                    fd2.ellipse([ex - r * 0.5, HY - 4 - r * 0.68,
                                 ex - r * 0.05, HY - 4 - r * 0.12],
                                fill=(240, 233, 225, 255))
                frame = frame.rotate(6.0, center=(CX, CY + 66),
                                     resample=Image.BICUBIC)
            elif em == "innocent":
                # cute head-tilt: a gentle whole-sprite rotation pivoting
                # low (feet planted), so head, ears, helmet, arms and the
                # baked halo all tilt together - not a face-only move.
                ang = math.sin(ph * 1.5) * 6.0
                frame = frame.rotate(ang, center=(CX, CY + 66),
                                     resample=Image.BICUBIC)
            elif em == "giggle":
                # GIGGLE HITCH: an UP-AND-DOWN bounce, not a side-to-side
                # rock - a laugh jerks the shoulders vertically. (First pass
                # used a rotation like awkward/innocent/zany; it read as
                # swaying, which is wrong for laughing.)
                # abs(sin) gives a repeated POP upward with a settle between
                # beats, rather than a smooth symmetric wave - that's the
                # shape of a hitch. The slow term makes bursts swell and
                # subside so he isn't bouncing like a metronome.
                amp = 0.55 + 0.45 * abs(math.sin(ph * 1.05))
                hop = (abs(math.sin(ph * 6.2)) * 3.6
                       + abs(math.sin(ph * 3.1 + 0.6)) * 1.4) * amp
                shifted = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                # negative dy = up. He pops UP off the rest pose and drops
                # back, so his feet stay planted at the bottom of the cycle.
                shifted.paste(frame, (0, -int(round(hop))))
                frame = shifted
            elif em == "smirk":
                # SMUG: lazy half-lidded eyes baked per-frame (so they can
                # animate), plus a single slow BROW-RAISE beat - the eyes
                # crack open a little, hold, and sink back. That one arched
                # beat is the "...I know something you don't" tell.
                #
                # Cycle: mostly resting low; a brow raise every ~4.4s.
                BR = 4.4
                u = (ph / BR) % 1.0
                if u < 0.14:                    # raise
                    lift = u / 0.14
                elif u < 0.42:                  # hold it up
                    lift = 1.0
                elif u < 0.62:                  # sink back
                    lift = 1.0 - (u - 0.42) / 0.20
                else:                           # rest, lids low
                    lift = 0.0
                # Draw the eyes+brows SUPERSAMPLED (4x) onto their own layer
                # and downscale, then paste. Drawing them directly at 1x on
                # the frame (as `awkward` does) leaves hard JAGGED edges -
                # awkward gets away with it because its beads are big, round
                # and simple, but these squashed lids show the stair-stepping
                # badly. Everything else in the renderer is built at 4x for
                # exactly this reason.
                SS = 4
                eye_layer = Image.new("RGBA", (frame.width * SS,
                                               frame.height * SS),
                                      (0, 0, 0, 0))
                fd3 = ImageDraw.Draw(eye_layer)
                for exb in (HX - 16, HX + 16):
                    ey = HY - 2
                    hh = 4.4 + 2.2 * lift       # lid height: low -> opening
                    # squashed eye SHAPE (never a skin-colored fill over the
                    # face - see the zany/skeptical notes)
                    fd3.ellipse([(exb - 8.4) * SS, (ey - hh) * SS,
                                 (exb + 8.4) * SS, (ey + hh) * SS],
                                fill=(58, 42, 34, 255))
                    fd3.ellipse([(exb - 5.2) * SS, (ey - hh * 0.72) * SS,
                                 (exb - 1.2) * SS, (ey - hh * 0.08) * SS],
                                fill=(240, 233, 225, 255))
                    # ONE brow per eye, lifting with the beat.
                    # NOTE: an earlier pass ALSO drew a heavy "lid line"
                    # sitting directly on top of the eye. With the brow above
                    # it, that read as DOUBLE EYEBROWS. The squashed eye shape
                    # already carries the heavy-lidded look on its own - it
                    # does not need a line drawn across it.
                    by = ey - hh - 6.5 - 3.6 * lift
                    fd3.line([(exb - 9) * SS, (by + 1.4) * SS,
                              (exb + 9) * SS, by * SS],
                             fill=(44, 31, 25, 255), width=int(2.2 * SS))
                eye_layer = eye_layer.resize(frame.size, Image.LANCZOS)
                frame.alpha_composite(eye_layer)
                # lazy settle: he eases back and just sits there, smug. Very
                # small - a smirk is about NOT trying hard.
                ang = -1.8 * (1.0 - math.exp(-ph * 1.1))
                frame = frame.rotate(ang, center=(CX, CY + 66),
                                     resample=Image.BICUBIC)
            elif em in ("unamused", "deadpan", "speechless"):
                # *** THREE DISTINCT STATIC FACES. *** Split from eye_roll
                # 2026-07-14: these four used to SHARE the eye-roll animation,
                # so in the parade unamused/deadpan/speechless all just rolled
                # their eyes and were indistinguishable. Now each reads as its
                # own emotion; only eye_roll actually rolls (below).
                #   unamused   = flat half-lidded eyes cut hard to ONE SIDE and
                #                HELD - the 'not amused' side-eye. Still.
                #   deadpan    = eyes dead-ahead, centred, heavy flat lids -
                #                totally blank, nobody home.
                #   speechless = eyes wide-ish with SMALL pupils, frozen -
                #                stunned into silence.
                # All three share the half-open aperture + the flat neutral
                # oval mouth (from the plate); the PUPIL and LID differ.
                if em == "unamused":
                    px, py = 4.2, 0.6          # cut to the side, slightly down
                    ap_ax, ap_ay = 8.6, 4.8    # low, lazy lids
                    pr = 4.2
                    lid_drop = 1.9             # heavy upper lid
                elif em == "deadpan":
                    px, py = 0.0, 0.0          # dead centre, staring through you
                    ap_ax, ap_ay = 8.6, 5.0
                    pr = 4.4
                    lid_drop = 1.4
                else:                          # speechless
                    px, py = 0.0, -0.4         # centred, a touch UP
                    ap_ax, ap_ay = 8.2, 7.0    # WIDER open (not half-lidded)
                    pr = 3.0                   # SMALL pupils = stunned
                    lid_drop = 0.2             # lids barely lowered
                SS = 4
                lay = Image.new("RGBA", (frame.width * SS, frame.height * SS),
                                (0, 0, 0, 0))
                ld = ImageDraw.Draw(lay)
                for exb in (HX - 16, HX + 16):
                    ey = HY - 3
                    # the aperture (squashed cream eye-white)
                    ld.ellipse([(exb - ap_ax) * SS, (ey - ap_ay) * SS,
                                (exb + ap_ax) * SS, (ey + ap_ay) * SS],
                               fill=(252, 248, 242, 255),
                               outline=(44, 31, 25, 255), width=int(1.6 * SS))
                    # the pupil, clipped to the aperture
                    pup = Image.new("RGBA", lay.size, (0, 0, 0, 0))
                    ImageDraw.Draw(pup).ellipse(
                        [(exb + px - pr) * SS, (ey + py - pr) * SS,
                         (exb + px + pr) * SS, (ey + py + pr) * SS],
                        fill=(58, 42, 34, 255))
                    msk = Image.new("L", lay.size, 0)
                    ImageDraw.Draw(msk).ellipse(
                        [(exb - ap_ax + 0.8) * SS, (ey - ap_ay + 0.8) * SS,
                         (exb + ap_ax - 0.8) * SS, (ey + ap_ay - 0.8) * SS],
                        fill=255)
                    lay.paste(pup, (0, 0), Image.composite(
                        pup.getchannel("A"), Image.new("L", lay.size, 0), msk))
                    # catchlight ONLY on speechless (the wide, alert stare);
                    # unamused/deadpan are deliberately dead-eyed, no shine
                    if em == "speechless":
                        ld.ellipse([(exb + px - pr + 0.6) * SS,
                                    (ey + py - pr + 0.6) * SS,
                                    (exb + px - pr + 2.4) * SS,
                                    (ey + py - pr + 2.4) * SS],
                                   fill=(255, 255, 255, 235))
                    # the upper lid pressing down
                    ld.line([(exb - ap_ax - 1) * SS,
                             (ey - ap_ay + lid_drop + 0.9) * SS,
                             (exb + ap_ax + 1) * SS,
                             (ey - ap_ay + lid_drop - 0.3) * SS],
                            fill=(44, 31, 25, 255), width=int(2.6 * SS))
                lay = lay.resize(frame.size, Image.LANCZOS)
                frame.alpha_composite(lay)
            elif em == "eye_roll":
                # THE actual eye-roll (only this one rolls now).
                #
                # The beat: hold a SIDE GLANCE -> roll the eyes UP and around
                # over the top -> land on the OPPOSITE side -> return to
                # centre -> hold. Eyes are lazily HALF-OPEN throughout (that
                # tired aperture is the whole attitude), and the mouth is the
                # flat neutral oval from the plate.
                RC = 5.4                      # seconds per full cycle
                u = (ph / RC) % 1.0
                if u < 0.22:                  # hold the side glance
                    a = math.pi
                    blend = 1.0
                elif u < 0.58:                # ROLL: left -> up -> right
                    t = (u - 0.22) / 0.36
                    # ease in/out so the roll has weight
                    t = t * t * (3 - 2 * t)
                    a = math.pi * (1.0 - t)   # pi -> 0, passing through pi/2
                    blend = 1.0               #   (pi/2 = straight up)
                elif u < 0.72:                # hold on the far side
                    a = 0.0
                    blend = 1.0
                elif u < 0.86:                # drift back to centre
                    t = (u - 0.72) / 0.14
                    t = t * t * (3 - 2 * t)
                    a = 0.0
                    blend = 1.0 - t
                else:                         # hold centre, dead-eyed
                    a = 0.0
                    blend = 0.0
                # pupil offset on an arc: cos -> sideways, -sin -> UP
                px = math.cos(a) * 4.2 * blend
                py = -math.sin(a) * 3.4 * blend

                SS = 4
                lay = Image.new("RGBA", (frame.width * SS, frame.height * SS),
                                (0, 0, 0, 0))
                ld = ImageDraw.Draw(lay)
                for exb in (HX - 16, HX + 16):
                    ey = HY - 3
                    # the APERTURE: a lazily half-open eye - a squashed cream
                    # eye-white. Half-open (not a slit, not wide) is what
                    # reads as bored/deadpan.
                    ax, ay = 8.6, 5.4
                    ld.ellipse([(exb - ax) * SS, (ey - ay) * SS,
                                (exb + ax) * SS, (ey + ay) * SS],
                               fill=(252, 248, 242, 255),
                               outline=(44, 31, 25, 255), width=int(1.6 * SS))
                    # the PUPIL, clipped to the aperture so it can slide
                    # partly UNDER the lid as it rolls up - that occlusion is
                    # what sells an eye-roll rather than a floating dot.
                    pup = Image.new("RGBA", lay.size, (0, 0, 0, 0))
                    pd = ImageDraw.Draw(pup)
                    pr = 4.4
                    pd.ellipse([(exb + px - pr) * SS, (ey + py - pr) * SS,
                                (exb + px + pr) * SS, (ey + py + pr) * SS],
                               fill=(58, 42, 34, 255))
                    msk = Image.new("L", lay.size, 0)
                    ImageDraw.Draw(msk).ellipse(
                        [(exb - ax + 0.8) * SS, (ey - ay + 0.8) * SS,
                         (exb + ax - 0.8) * SS, (ey + ay - 0.8) * SS],
                        fill=255)
                    lay.paste(pup, (0, 0), Image.composite(
                        pup.getchannel("A"), Image.new("L", lay.size, 0), msk))
                    # heavy upper lid: a thick line pressing down on the eye,
                    # keeping it half-open
                    ld.line([(exb - ax - 1) * SS, (ey - ay + 1.6) * SS,
                             (exb + ax + 1) * SS, (ey - ay + 0.4) * SS],
                            fill=(44, 31, 25, 255), width=int(2.6 * SS))
                lay = lay.resize(frame.size, Image.LANCZOS)
                frame.alpha_composite(lay)
            elif em == "relieved":
                # ONE DEEP SIGH OF RELIEF - a single choreographed breath,
                # NOT a repeating cycle. (Looping it made him look like he
                # was standing out in the cold watching his own breath over
                # and over - Chloe's note.) Anchored to the trigger, same as
                # the forehead wipe.
                #
                # Timeline (seconds since triggered):
                #   0.00-0.45  settle
                #   0.45-2.35  the forehead wipe (handled up in frame())
                #   2.40-4.30  INHALE - chest swells, body lifts
                #   4.30-4.70  hold the breath at the top
                #   4.70-9.20  EXHALE - long and slow, chest deflates, the
                #              breath cloud rolls out of his mouth
                #   9.20+      resting, sunk a little lower. Done.
                el = ph - self._relieved_t0
                IN0, IN1 = 2.40, 4.30
                HD1 = 4.70
                EX1 = 9.20
                if el < IN0:
                    swell, rise, ex = 0.0, 0.0, None
                elif el < IN1:                     # drawing the breath IN
                    t = (el - IN0) / (IN1 - IN0)
                    t = t * t * (3 - 2 * t)
                    swell, rise, ex = t, t, None
                elif el < HD1:                     # held at the top
                    swell, rise, ex = 1.0, 1.0, None
                elif el < EX1:                     # the long slow EXHALE
                    t = (el - HD1) / (EX1 - HD1)
                    te = t * t * (3 - 2 * t)
                    swell = 1.0 - te               # chest deflates
                    rise = 1.0 - 1.30 * te         # sinks BELOW rest = slump
                    ex = t                         # 0..1 drives the cloud
                else:                              # settled, spent
                    swell, rise, ex = 0.0, -0.30, None

                # CHEST SWELL: he visibly fills his lungs. Scale the WHOLE
                # sprite about a pivot down at his feet, rather than resizing
                # a torso band - a band crop leaves a hard horizontal SEAM
                # across the shoulders where the widened torso meets the
                # unscaled head, and the head/ears read as detached.
                # Scaling everything keeps him a single solid piece; because
                # the pivot is at the feet, the growth reads as the chest
                # filling out rather than the whole bear inflating.
                if swell > 0.01:
                    sc2 = 1.0 + 0.045 * swell
                    nw = int(round(frame.width * sc2))
                    nh = int(round(frame.height * sc2))
                    big = frame.resize((nw, nh), Image.LANCZOS)
                    grown = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                    # centre horizontally, anchor to the BOTTOM (feet stay put)
                    grown.alpha_composite(big, ((frame.width - nw) // 2,
                                                frame.height - nh))
                    frame = grown

                # body lift on the inhale / slump on the exhale
                dy = -rise * 4.5
                shifted = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                shifted.paste(frame, (0, int(round(dy))))
                frame = shifted

                # THE BREATH CLOUD - soft WHITE SEMI-TRANSPARENT vapour
                # rolling out of the mouth across the whole long exhale.
                # Drawn into the PIL RGBA frame, NOT on the tkinter canvas:
                # the canvas has no real alpha and can only fake translucency
                # with dither/stipple, which is what made the first attempt
                # look PATTERNED. PIL gives true alpha; GaussianBlur turns
                # hard ellipses into actual soft vapour.
                if ex is not None:
                    puff = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                    pdw = ImageDraw.Draw(puff)
                    # The mouth MOVES when the chest swells (the sprite is
                    # scaled about the feet), so the cloud's origin has to be
                    # put through the same transform - otherwise the vapour
                    # detaches and floats off the lips.
                    sc2 = 1.0 + 0.045 * max(0.0, swell)
                    mx0 = CX + 5 * sc2
                    my0 = (frame.height
                           - (frame.height - (HY + 20)) * sc2
                           + int(round(dy)))
                    for i3 in range(9):
                        tt = ex * 1.35 - i3 * 0.11  # blobs leave in sequence
                        if tt <= 0.0 or tt >= 1.0:
                            continue
                        bx0 = mx0 + tt * 60 + i3 * 1.6
                        by0 = my0 - tt * tt * 13.0 - i3 * 1.5
                        rr0 = 4.0 + tt * 15.0 + i3 * 0.7
                        # brighter and denser than before, fading as it
                        # expands and disperses
                        aa0 = int(225 * (1.0 - tt) ** 1.15)
                        if aa0 < 8:
                            continue
                        pdw.ellipse([bx0 - rr0, by0 - rr0 * 0.76,
                                     bx0 + rr0, by0 + rr0 * 0.76],
                                    fill=(255, 255, 255, aa0))
                    puff = puff.filter(ImageFilter.GaussianBlur(3.8))
                    frame.alpha_composite(puff)
            elif em == "yawn":
                # The body STRETCHES with the yawn - he pulls himself up
                # taller as his lungs fill, then settles back down (and a
                # touch lower than he started, because now he's drowsy).
                # Same whole-sprite scale-about-the-feet trick as relieved's
                # inhale: scaling only a band leaves a hard seam across the
                # shoulders and the head reads as detached.
                yv = yawn if yawn is not None else 0.0
                if yv > 0.01:
                    sc3 = 1.0 + 0.05 * yv
                    nw3 = int(round(frame.width * sc3))
                    nh3 = int(round(frame.height * sc3))
                    big3 = frame.resize((nw3, nh3), Image.LANCZOS)
                    grown3 = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                    grown3.alpha_composite(big3,
                                           ((frame.width - nw3) // 2,
                                            frame.height - nh3))
                    frame = grown3
                # lift on the stretch, then sag drowsily afterwards
                ely2 = ph - self._yawn_t0
                sag = 0.0
                if ely2 > 3.30:
                    sag = 2.6 * (1.0 - math.exp(-(ely2 - 3.30) * 1.2))
                dy3 = -yv * 3.0 + sag
                sh3 = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                sh3.paste(frame, (0, int(round(dy3))))
                frame = sh3
            elif em == "drooling":
                # THE DRIP CYCLE - this is the whole emote. A bead forms at
                # the low corner of his slack mouth, swells, stretches into a
                # teardrop on a thin neck, pinches off, falls, and a new one
                # starts. (The old baked version drew a static straight LINE
                # under the mouth - that's just a mark on his chin, not
                # drool.)
                #
                # Drawn into the PIL RGBA frame, not the tkinter canvas: the
                # canvas has no real alpha, so it can't do the translucent
                # glossy look saliva needs (it can only dither, which reads
                # as a pattern).
                DC = 2.9                       # seconds per drip
                u = (ph / DC) % 1.0
                mx = CX + 5.0                  # low corner of the slack mouth
                my = HY + 26.0
                dl = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                dd = ImageDraw.Draw(dl)
                SAL = (168, 224, 236)          # saliva blue-white
                SALE = (120, 186, 206)

                if u < 0.62:
                    # HANGING: bead swells and the neck stretches downward
                    t = u / 0.62
                    t = t * t * (3 - 2 * t)
                    neck = 3.0 + t * 13.0      # how far the drop has sagged
                    rr = 1.6 + t * 2.9         # bead fattens as it fills
                    # thin neck from the lip down to the bead
                    dd.line([mx, my - 1, mx, my + neck - rr * 0.4],
                            fill=SAL + (205,), width=2)
                    # the bead itself (slightly teardrop: narrower on top)
                    by = my + neck
                    dd.polygon([(mx, by - rr * 1.5), (mx + rr, by - rr * 0.1),
                                (mx + rr * 0.85, by + rr * 0.85), (mx, by + rr),
                                (mx - rr * 0.85, by + rr * 0.85),
                                (mx - rr, by - rr * 0.1)],
                               fill=SAL + (230,), outline=SALE + (235,))
                    # gloss highlight so it reads WET
                    dd.ellipse([mx - rr * 0.5, by - rr * 0.75,
                                mx - rr * 0.05, by - rr * 0.15],
                               fill=(255, 255, 255, 210))
                elif u < 0.80:
                    # FALLING: it pinched off - the drop drops away, and a
                    # short stub is left behind on the lip
                    t = (u - 0.62) / 0.18
                    by = my + 16.0 + t * t * 46.0     # accelerating fall
                    rr = 4.2 - t * 0.8
                    dd.polygon([(mx, by - rr * 1.7), (mx + rr, by - rr * 0.1),
                                (mx + rr * 0.85, by + rr * 0.85), (mx, by + rr),
                                (mx - rr * 0.85, by + rr * 0.85),
                                (mx - rr, by - rr * 0.1)],
                               fill=SAL + (int(225 * (1 - t * 0.55)),),
                               outline=SALE + (200,))
                    dd.line([mx, my - 1, mx, my + 3.5],
                            fill=SAL + (190,), width=2)
                else:
                    # RESTING: just a wet glint on the lip before the next one
                    dd.line([mx, my - 1, mx, my + 2.5],
                            fill=SAL + (150,), width=2)
                frame.alpha_composite(dl)
            elif em == "nauseated":
                # HUNCH AND PUKE (Chloe's call). Between heaves he just sways
                # queasily; then he doubles over, opens up, and lets go.
                # The GREEN TINT is NOT applied here - it's done inside
                # frame(), under the face plate, so it greens only his skin
                # and not his eyes/nose/brows/mouth.
                pk = getattr(self, "_puke", 0.0)
                un = getattr(self, "_puke_u", 0.0)

                # THE HUNCH: he folds forward - compresses down, leans, and
                # his head drops. Sold with a squash + a forward tilt.
                #
                # *** THE LEAN AND THE STREAM MUST AGREE. *** He pukes out to
                # SCREEN LEFT, so he must lean LEFT too - an earlier pass
                # rotated him clockwise (leaning RIGHT) while the spray went
                # left, so he was heaving away from his own vomit. PIL's
                # rotate() is COUNTERCLOCKWISE for a positive angle, and a CCW
                # rotation about a pivot at his feet tips his head to the
                # LEFT. Hence +7, not -7.
                LEAN = 7.0
                sqz = 1.0 - 0.075 * pk         # compress vertically
                wid = 1.0 + 0.035 * pk         # and spread a little
                if pk > 0.01:
                    nw5 = max(1, int(round(frame.width * wid)))
                    nh5 = max(1, int(round(frame.height * sqz)))
                    b5 = frame.resize((nw5, nh5), Image.LANCZOS)
                    g5 = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                    g5.alpha_composite(b5, ((frame.width - nw5) // 2,
                                            frame.height - nh5))
                    frame = g5
                    # tip forward over his own feet, TOWARD the stream
                    frame = frame.rotate(LEAN * pk, center=(CX, CY + 66),
                                         resample=Image.BICUBIC)

                # WHERE HIS MOUTH ACTUALLY IS, after the squash and the lean.
                # Put the mouth point through the SAME transforms rather than
                # guessing a fixed offset - otherwise the spray detaches from
                # his face as he tips (the drool/relieved lesson: the source
                # has to follow the mouth).
                mox, moy = HX, HY + 23.0
                # 1) squash about the feet
                mox = CX + (mox - CX) * wid
                moy = frame.height - (frame.height - moy) * sqz
                # 2) rotate CCW about the feet pivot
                th5 = math.radians(LEAN * pk)
                pvx, pvy = CX, CY + 66
                ddx, ddy = mox - pvx, moy - pvy
                mx5 = pvx + ddx * math.cos(th5) + ddy * math.sin(th5)
                my5 = pvy - ddx * math.sin(th5) + ddy * math.cos(th5)

                # THE VOMIT. Drawn into the PIL frame for real alpha, and it
                # originates AT the mouth (the drool lesson).
                #
                # *** IT WIDENS AS IT LEAVES. *** Puke is not laminar flow
                # (Chloe). An earlier pass tapered the stream to a point,
                # which made it read as a smooth TUBE / garden hose. A real
                # heave leaves the mouth narrow and immediately breaks up:
                # the further it travels, the WIDER and more scattered it
                # gets. So the radius GROWS with distance, blobs are jittered
                # off the centre-line by a spread that also grows, and the
                # far end is loose droplets rather than a solid edge.
                if pk > 0.55:
                    t = (un - 0.72) / 0.18 if un < 0.90 else 1.0
                    t = max(0.0, min(1.0, t))
                    vl = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                    vd = ImageDraw.Draw(vl)
                    VG = (126, 178, 74)
                    VGE = (92, 140, 52)
                    N5 = 30
                    for i5 in range(N5):
                        f = i5 / float(N5 - 1)
                        if f > t:
                            continue
                        # centre-line of the spray: out to his side, falling
                        bxs = mx5 - 3 - f * 44
                        bys = my5 + f * 10 + f * f * 56
                        # narrow at the lips, FANNING OUT with distance
                        rr5 = 2.4 + f * 6.0
                        spread = f * f * 15.0      # how far blobs scatter
                        # 3 blobs per step, jittered across the cone; the
                        # deterministic sines keep it stable frame to frame
                        # while still looking irregular
                        for j5 in range(3):
                            jx = math.sin(i5 * 1.7 + j5 * 2.3) * spread
                            jy = math.cos(i5 * 2.1 + j5 * 1.1) * spread * 0.55
                            r6 = rr5 * (0.55 + 0.30 * ((j5 + i5) % 3))
                            if r6 < 0.9:
                                continue
                            a6 = 235 - int(f * 70)   # thins out at the far end
                            vd.ellipse([bxs + jx - r6, bys + jy - r6 * 0.9,
                                        bxs + jx + r6, bys + jy + r6 * 0.9],
                                       fill=VG + (a6,))
                        # a darker core near the mouth gives the spray form
                        if f < 0.5:
                            r7 = rr5 * 0.5
                            vd.ellipse([bxs - r7, bys + r7 * 0.2,
                                        bxs + r7, bys + r7 * 1.2],
                                       fill=VGE + (150,))
                    # loose droplets flung out ahead of the spray
                    for i5, (ox, oy, rr5) in enumerate((
                            (-58, 48, 3.2), (-70, 62, 2.4), (-48, 76, 2.8),
                            (-66, 84, 2.0), (-38, 88, 2.3))):
                        if t < 0.35 + i5 * 0.09:
                            continue
                        cx5 = mx5 + ox - t * 12
                        cy5 = my5 + oy + t * 30
                        vd.ellipse([cx5 - rr5, cy5 - rr5,
                                    cx5 + rr5, cy5 + rr5],
                                   fill=VG + (215,), outline=VGE + (185,))
                    frame.alpha_composite(vl)
                else:
                    # between heaves: a slow queasy sway
                    dxn = math.sin(ph * 0.8) * 2.2
                    sh6 = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                    sh6.paste(frame, (int(round(dxn)), 0))
                    frame = sh6
            elif em == "hot":
                # THE WILT: he slowly sags under the heat like he's melting,
                # then barely recovers and sags again. Being DRAINED is what
                # separates hot from merely warm - and it's the exact opposite
                # of `cold`, which is a fast constant tremble.
                # Whole-sprite squash about the FEET (no shoulder seam).
                WC = 6.4
                uw = (ph / WC) % 1.0
                # long slow melt, then a quick weary straighten
                if uw < 0.78:
                    wilt = uw / 0.78
                    wilt = wilt * wilt * (3 - 2 * wilt)
                else:
                    wilt = 1.0 - (uw - 0.78) / 0.22
                pv = getattr(self, "_pant", 0.5)
                sqz7 = 1.0 - 0.045 * wilt          # sinking
                # fast shallow BREATH on top of the wilt - his chest pumps
                sqz7 -= 0.010 * pv
                wid7 = 1.0 + 0.022 * wilt + 0.008 * pv
                nw7 = max(1, int(round(frame.width * wid7)))
                nh7 = max(1, int(round(frame.height * sqz7)))
                b7 = frame.resize((nw7, nh7), Image.LANCZOS)
                g7 = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                g7.alpha_composite(b7, ((frame.width - nw7) // 2,
                                        frame.height - nh7))
                frame = g7
                # a slow heavy list, like he can't hold himself straight
                dx7 = math.sin(ph * 0.5) * 2.4
                sh7 = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                sh7.paste(frame, (int(round(dx7)), 0))
                frame = sh7

                hl = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                hd = ImageDraw.Draw(hl)

                # SWEAT: heavy beads on his brow that swell and ROLL OFF.
                # Same drip machinery as drooling, moved to the forehead and
                # run faster. Placed at the TEMPLES so they never cross his
                # eyes (a bead over the eye reads as a rendering bug).
                SW = (196, 232, 246)
                SWE = (132, 190, 214)
                for bi, (bx7, per, off) in enumerate((
                        (HX - 27, 1.9, 0.0), (HX + 27, 2.3, 0.9))):
                    ub = ((ph + off) / per) % 1.0
                    by7 = HY - 14
                    if ub < 0.55:              # swelling on the brow
                        tb = ub / 0.55
                        rr7 = 1.4 + tb * 2.6
                        yy7 = by7 + tb * 3.0
                        hd.polygon([(bx7, yy7 - rr7 * 1.5),
                                    (bx7 + rr7, yy7),
                                    (bx7 + rr7 * 0.8, yy7 + rr7 * 0.9),
                                    (bx7, yy7 + rr7),
                                    (bx7 - rr7 * 0.8, yy7 + rr7 * 0.9),
                                    (bx7 - rr7, yy7)],
                                   fill=SW + (225,), outline=SWE + (220,))
                        hd.ellipse([bx7 - rr7 * 0.5, yy7 - rr7 * 0.7,
                                    bx7 - rr7 * 0.05, yy7 - rr7 * 0.1],
                                   fill=(255, 255, 255, 215))
                    elif ub < 0.85:            # rolling DOWN the side of him
                        tb = (ub - 0.55) / 0.30
                        rr7 = 3.6 - tb * 0.9
                        yy7 = by7 + 3.0 + tb * tb * 52.0
                        xx7 = bx7 + (-1 if bi == 0 else 1) * tb * 5.0
                        hd.polygon([(xx7, yy7 - rr7 * 1.6),
                                    (xx7 + rr7, yy7),
                                    (xx7 + rr7 * 0.8, yy7 + rr7 * 0.9),
                                    (xx7, yy7 + rr7),
                                    (xx7 - rr7 * 0.8, yy7 + rr7 * 0.9),
                                    (xx7 - rr7, yy7)],
                                   fill=SW + (int(220 * (1 - tb * 0.4)),),
                                   outline=SWE + (190,))

                # HEAT SHIMMER: wavy rising lines in the SIDE CHANNELS only.
                # Anything crossing his silhouette reads as a rendering bug,
                # so these stay clear of him entirely.
                for sgn in (-1, 1):
                    for k7 in range(3):
                        base_x = CX + sgn * (74 + k7 * 11)
                        rise = ((ph * 26 + k7 * 30) % 90)
                        yb = CY + 26 - rise
                        aa7 = int(120 * math.sin(rise / 90.0 * math.pi))
                        if aa7 < 8:
                            continue
                        pts7 = []
                        for s7 in range(7):
                            fy = s7 / 6.0
                            pts7.append(
                                (base_x + math.sin(fy * 5.4 + ph * 3
                                                   + k7) * 3.4,
                                 yb - fy * 22))
                        hd.line(pts7, fill=(255, 236, 214, aa7), width=2,
                                joint="curve")
                frame.alpha_composite(hl)
            elif em == "dizzy":
                # HEAD LOLL: kept SMALL on purpose. A rotation about a pivot
                # at his FEET swings the HEAD sideways by roughly
                # sin(angle) * 130px - so 6 degrees threw his eyes ~13px
                # left and right, which completely swamped the spiral spin.
                # Chloe read that lateral swing as the eyes "drifting from
                # centre to left", and never saw the swirl turn at all.
                # 2.5 degrees keeps the woozy lean without stealing the show.
                OR = 2.1
                frame = frame.rotate(math.sin(ph * OR - 0.9) * 2.5,
                                     center=(CX, CY + 66),
                                     resample=Image.BICUBIC)

                # STARS CIRCLING OVERHEAD, on an ellipse ABOVE his head.
                # Kept entirely CLEAR of his silhouette - the standing rule
                # (anything crossing the face reads as a rendering bug). The
                # ellipse is wide and flat so it reads as a ring seen edge-on.
                sl = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                sd = ImageDraw.Draw(sl)
                for si in range(4):
                    a8 = ph * 2.6 + si * (math.pi / 2)
                    sx8 = HX + math.cos(a8) * 40
                    sy8 = (HY - 64) + math.sin(a8) * 9
                    # DEPTH: a star on the far side of the ring is smaller
                    # and dimmer, which is what makes the ring read as 3D
                    # rather than as four dots sliding along a line.
                    depth = (math.sin(a8) + 1) * 0.5      # 0 far .. 1 near
                    rr8 = 2.3 + depth * 2.2
                    aa8 = int(120 + depth * 125)
                    # 4-point twinkle star
                    sd.polygon([(sx8, sy8 - rr8 * 1.9),
                                (sx8 + rr8 * 0.52, sy8 - rr8 * 0.52),
                                (sx8 + rr8 * 1.9, sy8),
                                (sx8 + rr8 * 0.52, sy8 + rr8 * 0.52),
                                (sx8, sy8 + rr8 * 1.9),
                                (sx8 - rr8 * 0.52, sy8 + rr8 * 0.52),
                                (sx8 - rr8 * 1.9, sy8),
                                (sx8 - rr8 * 0.52, sy8 - rr8 * 0.52)],
                               fill=(255, 226, 130, aa8),
                               outline=(226, 176, 66, min(255, aa8 + 30)))
                frame.alpha_composite(sl)
            elif em == "mind_blown":
                # HIS HEAD POPS. The lid (crown + antennae) launches off, a
                # cloud erupts from the crater, and the lid arcs back down and
                # lands - so the gag loops cleanly.
                #
                # *** The lid is CUT FROM HIS ACTUAL RENDERED HEAD, *** not
                # hand-drawn. Crop the frame above the cut line and that IS
                # the top of his head - correct hood, shading, ears and
                # antennae, guaranteed to match. (Hand-rolling the shape is
                # exactly the mistake that made the yawn arm read as a tube.)
                #
                # ph advances 3.0 units/sec, so MC=9.0 is a ~3 second cycle.
                MC = 9.0
                um = (ph / MC) % 1.0
                CUT = HY - 36          # above the ears, at the antennae base

                if um < 0.10:
                    a = 0.0            # still building - lid on, tensing
                elif um < 0.75:
                    a = (um - 0.10) / 0.65     # airborne
                else:
                    a = 0.0            # landed

                lid_h = 4.0 * a * (1.0 - a)    # parabola: up, then back down
                blown = 1.0 if 0.10 <= um < 0.75 else 0.0

                # body RECOIL from the blast, plus a tense shudder before it
                if um < 0.10:
                    tense = math.sin(ph * 40) * 0.9 * (um / 0.10)
                    frame = _shift(frame, int(round(tense)), 0)
                elif um < 0.22:
                    k = (um - 0.10) / 0.12
                    jolt = math.sin(k * math.pi) * 5.0
                    frame = _shift(frame, int(round(math.sin(ph * 34) * jolt)),
                                   int(round(jolt * 0.7)))

                if blown > 0.5:
                    W2, H2 = frame.size
                    lid = frame.crop((0, 0, W2, CUT))       # his real crown
                    body = frame.copy()
                    # blow the lid OFF: erase that band from the body
                    body.paste(Image.new("RGBA", (W2, CUT), (0, 0, 0, 0)),
                               (0, 0))

                    # ---- the crater he's now missing a lid from ----------
                    cr = ImageDraw.Draw(body)
                    cr.ellipse([HX - 34, CUT - 7, HX + 34, CUT + 9],
                               fill=(58, 30, 26, 255))
                    cr.ellipse([HX - 34, CUT - 7, HX + 34, CUT + 4],
                               fill=(30, 14, 12, 255))
                    cr.arc([HX - 35, CUT - 8, HX + 35, CUT + 10],
                           start=0, end=180, fill=SKIN_EDGE + (255,), width=3)

                    # ---- the eruption: billowing cloud out of the crater --
                    cl = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                    cd = ImageDraw.Draw(cl)
                    for i9 in range(16):
                        f9 = i9 / 15.0
                        # each puff has its own age - older ones are higher,
                        # bigger and fainter (a cloud BILLOWS, it doesn't
                        # travel as a rigid blob)
                        age = a - f9 * 0.30
                        if age <= 0:
                            continue
                        rise = age * 62.0
                        rr9 = 5.0 + age * 15.0 + f9 * 3.0
                        aa9 = int(215 * max(0.0, 1.0 - age * 0.85))
                        if aa9 < 8:
                            continue
                        wob = math.sin(f9 * 9.0 + ph * 2.2) * (6.0 + age * 12)
                        cx9 = HX + wob
                        cy9 = CUT - 2 - rise
                        col = (250, 238, 226) if i9 % 3 else (232, 214, 202)
                        cd.ellipse([cx9 - rr9, cy9 - rr9 * 0.86,
                                    cx9 + rr9, cy9 + rr9 * 0.86],
                                   fill=col + (aa9,))
                    # hot flash right at the crater on the first instant
                    if a < 0.16:
                        fl = int(230 * (1.0 - a / 0.16))
                        fr9 = 12 + a * 90
                        cd.ellipse([HX - fr9, CUT - fr9 * 0.6,
                                    HX + fr9, CUT + fr9 * 0.5],
                                   fill=(255, 236, 170, fl))
                    # debris chunks flung out of the crater
                    for i9, (dxr, spin) in enumerate(((-1.0, 1.0), (0.5, -1.0),
                                                      (-0.4, 1.0), (1.0, -1.0))):
                        if a < 0.05:
                            continue
                        dt = a
                        px9 = HX + dxr * (16 + dt * 48)
                        py9 = CUT - (dt * 70) + (dt * dt * 46)
                        rr9 = 3.4 - dt * 1.2
                        if rr9 < 0.9:
                            continue
                        cd.ellipse([px9 - rr9, py9 - rr9, px9 + rr9, py9 + rr9],
                                   fill=(228, 106, 74) + (int(230 * (1 - dt * 0.6)),))
                    body.alpha_composite(cl)

                    # ---- put the lid back, mid-flight --------------------
                    lift = int(round(lid_h * 86))
                    drift = int(round(math.sin(a * math.pi) * 7))
                    tilt = math.sin(a * math.pi) * 22.0
                    lidbig = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                    lidbig.paste(lid, (0, 0))
                    lidbig = lidbig.rotate(tilt, center=(HX, CUT),
                                           resample=Image.BICUBIC)
                    body.alpha_composite(_shift(lidbig, drift, -lift))
                    frame = body
            elif em == "cool":
                # *** "DEAL WITH IT" SUNGLASSES *** (Chloe's exact request).
                # Chunky 8-BIT PIXEL shades that drop STRAIGHT DOWN from off
                # the top of frame in a hard LINEAR motion - constant speed,
                # NO easing, NO bounce - land on his face, and stay put.
                # The deadpan linearity IS the joke; easing it would kill it.
                #
                # *** THE SPRITE IS DRAWN SLIGHTLY OFF-AXIS (3/4 view), ***
                # exactly like the real meme sprite: the NEAR lens is WIDER
                # than the far one, and the TEMPLE ARM ("the ear part") is
                # visible running back off the near side. Two head-on
                # rectangles read as a flat bar stuck to his face.
                #
                # *** CELL IS AN INTEGER AND THE ORIGIN IS SNAPPED TO THE
                # PIXEL GRID. *** A fractional cell (2.7) made adjacent blocks
                # round to 2px or 3px unevenly - the "pixels" came out ragged
                # and NOT SQUARE. Integer cell + integer origin = true squares.
                # Also drawn at 1x, never supersampled: everything else about
                # Buddy is smooth and antialiased; these must NOT be.
                el = ph - getattr(self, "_cool_t0", 0.0)
                # ph advances 3.0/sec -> 4.5 units = ~1.5s. Slower than the
                # first pass (0.8s), which arrived too fast to land the gag.
                DROP = 4.5
                CELL = 3                        # INTEGER: square pixels
                land_y = HY - 15
                start_y = -62.0
                if el < DROP:
                    gy = start_y + (land_y - start_y) * (el / DROP)   # LINEAR
                else:
                    gy = land_y
                gx = int(round(HX - 40.5))
                gy = int(round(gy))             # snap to the pixel grid

                # 25x6 sprite, drawn OFF-AXIS (3/4 view).
                #  '1' = FRAME  - fully opaque black plastic
                #  '2' = LENS   - very slightly TRANSPARENT smoked glass, so
                #                 his eyes BARELY read through it. Subtle on
                #                 purpose: enough to tell lens from frame and
                #                 to hint at the eyes, nothing more.
                #  '0' = empty
                # The TEMPLE ARM runs off the LEFT side, so the LEFT lens is
                # the NEAR one and is WIDER (9 cells) than the far right lens
                # (8 cells). That width difference plus the arm is what makes
                # them read as WORN rather than as a flat bar stuck on.
                SPR = (
                    "0111111111111111111111110",
                    "1100122222221000122222210",
                    "1000122222221000122222210",
                    "0000122222221000122222210",
                    "0000122222221000122222210",
                    "0000111111111000111111110",
                )
                FRAME_COL = (18, 18, 22, 255)     # opaque plastic
                LENS_COL = (30, 30, 38, 214)      # smoked glass, barely see-thru
                gl = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                gd = ImageDraw.Draw(gl)
                for ry, row in enumerate(SPR):
                    for rx, ch in enumerate(row):
                        if ch == "0":
                            continue
                        x0 = gx + rx * CELL
                        y0 = gy + ry * CELL
                        # -1 so blocks butt up exactly, no overlap smear
                        gd.rectangle([x0, y0, x0 + CELL - 1, y0 + CELL - 1],
                                     fill=(FRAME_COL if ch == "1"
                                           else LENS_COL))
                frame.alpha_composite(gl)
            elif em == "disappointed":
                # *** THE DEFLATE. *** A VERTICAL SQUASH - scale Y ONLY.
                # Air going out of him. This axis was genuinely free:
                #   embarrassed  = a UNIFORM shrink (he wants to disappear).
                #   scrutinizing = a UNIFORM scale-UP (leaning in at you).
                #   disappointed = Y ONLY. He doesn't get smaller, he DEFLATES:
                #     squashed down and slightly wider, like something with the
                #     air let out. Nobody else does this.
                # Anchored about the FEET so he settles onto the ground rather
                # than sinking through it.
                el = max(0.0, ph - self._disap_t0)
                drop = 1.0 - math.exp(-el * 1.9)
                sy = 1.0 - 0.075 * drop          # squashed DOWN 7.5%
                sx2 = 1.0 + 0.030 * drop         # and a touch WIDER
                if drop > 0.02:
                    nw = max(1, int(round(frame.width * sx2)))
                    nh = max(1, int(round(frame.height * sy)))
                    sq = frame.resize((nw, nh), Image.LANCZOS)
                    # WIDENING makes the image wider than the canvas, which
                    # would hand alpha_composite a NEGATIVE dest - PIL raises
                    # "Destination must be non-negative". Crop back to canvas
                    # width instead. (His body is ~110px wide in a 380px frame,
                    # so trimming a few px off each edge cannot clip him.)
                    if nw > frame.width:
                        left = (nw - frame.width) // 2
                        sq = sq.crop((left, 0, left + frame.width, nh))
                        nw = frame.width
                    g = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                    g.alpha_composite(sq, ((frame.width - nw) // 2,
                                           frame.height - nh))
                    frame = g
            elif em == "mischievous":
                # *** THE HORNS - ROOTED IN THE SKULL AND ANGLED TO ITS CURVE. ***
                #
                # FIRST PASS WAS BROKEN AND CHLOE CALLED IT: "his devil horns are
                # floating in his ear holes and aren't actually attached to his
                # head." Dead right, and the numbers say exactly why:
                #     EARS span HX+/-17 .. HX+/-41 (centred HX+/-29).
                #     I put the horns at HX+/-27. *** DEAD CENTRE OF THE EARS. ***
                # They were also straight VERTICAL triangles with a flat base, so
                # nothing about them followed the head. They sat ON him, not IN him.
                #
                # THE FIX, three parts:
                #  1. ROOT them inboard at HX+/-19, on the head's upper slope
                #     (head top runs (HX,HY-41) -> (HX+/-26,HY-34)), not on the ear.
                #  2. SINK the base BELOW the head surface so the horn EMERGES from
                #     the skull instead of resting on it.
                #  3. *** ANGLE each horn along the SKULL'S OUTWARD NORMAL *** - the
                #     vector from the head centre out through the root. That is what
                #     "fit the curvature of his head" means: a horn growing out of a
                #     curved surface points AWAY FROM THE CENTRE, it does not point
                #     straight up. Each horn is built in local space and ROTATED onto
                #     that normal.
                # Plus a dark contact shadow at the root, which is what actually
                # sells "attached" rather than "stuck on".
                hl = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                hd = ImageDraw.Draw(hl)
                for sx3 in (-1, 1):
                    rx, ry = HX + sx3 * 19.0, HY - 33.0     # the ROOT, sunk in
                    nx, ny = rx - HX, ry - HY               # outward normal...
                    nl = math.hypot(nx, ny)
                    nx, ny = nx / nl, ny / nl               # ...normalised
                    # rotate local (0,-1) [straight up] onto the normal
                    cs, sn = -ny, nx
                    def put(lx, ly):
                        return (rx + lx * cs - ly * sn, ry + lx * sn + ly * cs)
                    # local horn: base at y=0, tip up at y=-17, hooked outward
                    horn = [put(-5.4 * sx3, 1.5), put(-4.2 * sx3, -6.0),
                            put(-2.0 * sx3, -12.0), put(1.4 * sx3, -17.2),
                            put(3.2 * sx3, -11.5), put(4.6 * sx3, -5.0),
                            put(5.6 * sx3, 1.5)]
                    # the contact shadow that seats it into the fur.
                    # *** BUILD THE BOX WITH min/max. *** Once the horn is
                    # rotated onto the skull normal, the "left" corner can end
                    # up to the RIGHT of the "right" corner on one side, and
                    # PIL's ellipse() REFUSES a box with x0 > x1:
                    #     ValueError: x1 must be greater than or equal to x0
                    # That threw on EVERY FRAME and the pet fell back to idle -
                    # Chloe saw no animation at all. Any bbox built from ROTATED
                    # points must be normalised with min/max, never assumed
                    # ordered.
                    sa = put(-6.2 * sx3, 2.6)
                    sb = put(6.4 * sx3, 2.6)
                    hd.ellipse([min(sa[0], sb[0]) - 1, min(sa[1], sb[1]) - 1,
                                max(sa[0], sb[0]) + 1, max(sa[1], sb[1]) + 1],
                               fill=(150, 70, 62, 90))
                    hd.polygon(horn, fill=(198, 58, 58, 255),
                               outline=(118, 24, 28, 255))
                    # the lit face of the horn
                    hd.polygon([put(-3.2 * sx3, 0.0), put(-2.0 * sx3, -6.2),
                                put(0.2 * sx3, -12.6), put(-0.4 * sx3, -5.4)],
                               fill=(230, 112, 104, 255))
                frame.alpha_composite(hl)
            elif em == "furious":
                # *** THE ERUPTION: FLAMES + THE CURSING. ***
                # The flat tkinter flames are DELETED. They were shared with
                # angry (identical code, 2 vs 3 flames) and they were flat
                # single-colour polygons. These are drawn in the PIL chain with
                # a real gradient core, there are FIVE of them, and they are
                # bigger. THE FLAMES ARE NOW FURIOUS'S ALONE.
                #
                # IMAGE coords (HX/HY), never canvas coords (cx/hy) - cx/hy
                # already carry the bob.
                er = self._fur_erupt
                fl = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                fd = ImageDraw.Draw(fl)
                for i2 in range(5):
                    fxo = (i2 - 2) * 13.0
                    # each flame flickers on ITS OWN phase, so they never march
                    # in step (that is what makes fire read as fire)
                    flick = 0.55 + 0.45 * math.sin(ph * 7.0 + i2 * 2.1)
                    fh = (17.0 + 13.0 * er) * flick     # they FLARE on the blow
                    fx4 = HX + fxo
                    fy4 = HY - 43.0
                    fd.polygon([(fx4 - 6.0, fy4), (fx4 - 3.2, fy4 - fh * 0.42),
                                (fx4 - 1.4, fy4 - fh * 0.72),
                                (fx4 + 0.9, fy4 - fh),
                                (fx4 + 2.6, fy4 - fh * 0.55),
                                (fx4 + 6.0, fy4)],
                               fill=(242, 112, 48, 255))
                    fd.polygon([(fx4 - 2.8, fy4 - 1.0),
                                (fx4 - 0.8, fy4 - fh * 0.42),
                                (fx4 + 0.6, fy4 - fh * 0.62),
                                (fx4 + 2.4, fy4 - 1.0)],
                               fill=(251, 214, 92, 255))
                frame.alpha_composite(fl)

                # *** THE CURSE SYMBOLS. *** The churning band over his mouth -
                # this is what the emoji actually IS.
                # THEY CYCLE: each slot SWAPS symbol on a beat, so the band
                # CHURNS rather than sitting there. A static squiggle (the old
                # _mouth_scribble) is furniture; this has a lifecycle.
                sy = HY + 21.0
                step = int(ph * 2.2)          # advances ~0.26/frame -> no alias
                for i2 in range(3):
                    sx4 = HX + (i2 - 1) * 11.0
                    kind = (step + i2) % 4
                    pu = 0.80 + 0.20 * math.sin(ph * 9.0 + i2 * 2.0)
                    s = 4.4 * pu * (1.0 + 0.25 * er)
                    ink = (252, 240, 180, 255)
                    if kind == 0:             # a STAR burst
                        pts = []
                        for k in range(10):
                            rr = s if k % 2 == 0 else s * 0.42
                            aa = math.radians(k * 36.0 - 90.0)
                            pts.append((sx4 + rr * math.cos(aa),
                                        sy + rr * math.sin(aa)))
                        fd2 = ImageDraw.Draw(frame)
                        fd2.polygon(pts, fill=ink, outline=(40, 20, 16, 255))
                    elif kind == 1:           # a HASH
                        fd2 = ImageDraw.Draw(frame)
                        for o in (-s * 0.34, s * 0.34):
                            fd2.line([(sx4 + o - s * 0.16, sy - s),
                                      (sx4 + o + s * 0.16, sy + s)],
                                     fill=ink, width=2)
                            fd2.line([(sx4 - s, sy + o), (sx4 + s, sy + o)],
                                     fill=ink, width=2)
                    elif kind == 2:           # an EXCLAMATION
                        fd2 = ImageDraw.Draw(frame)
                        fd2.polygon([(sx4 - s * 0.34, sy - s),
                                     (sx4 + s * 0.34, sy - s),
                                     (sx4 + s * 0.17, sy + s * 0.22),
                                     (sx4 - s * 0.17, sy + s * 0.22)],
                                    fill=ink)
                        fd2.ellipse([sx4 - s * 0.28, sy + s * 0.48,
                                     sx4 + s * 0.28, sy + s], fill=ink)
                    else:                     # an AT / spiral
                        fd2 = ImageDraw.Draw(frame)
                        fd2.ellipse([sx4 - s, sy - s, sx4 + s, sy + s],
                                    outline=ink, width=2)
                        fd2.ellipse([sx4 - s * 0.38, sy - s * 0.38,
                                     sx4 + s * 0.38, sy + s * 0.38], fill=ink)
            elif em == "angry":
                # *** THE ANGER VEIN. *** The four-lobed cross-pop mark.
                # ANGRY'S ONE ACCENT, and nothing else in the 65 has it.
                #
                # It replaces the FLAMES, which angry used to share with furious
                # (identical accent, 2 vs 3 flames - they'd have been twins).
                # It is ALSO not a red flush, on purpose: bashful, embarrassed
                # and hot ALREADY own face-reddening between them, and a fourth
                # would just be another twin.
                #
                # *** A VEIN IS A CRISP OBJECT, NOT A TINT. *** So it follows the
                # sparkle/droplet rule, NOT the blush rule: hard edges, solid
                # fill, a dark outline. No soft bleed - and the alpha threshold
                # is binary anyway, so a soft edge would just snap into a hard
                # one somewhere unpredictable.
                #
                # It THROBS on the same `seethe` swell that drives his body, so
                # the vein and the shudder can never desync.
                #
                # IMAGE coords (HX/HY), never canvas coords (cx/hy) - cx/hy
                # already carry the bob.
                th = self._angry_throb
                vr = 9.4 * (0.82 + 0.26 * th)        # it swells as he burns
                vx, vy = HX + 28.0, HY - 31.0        # temple, up on the hood
                pts = []
                for k in range(4):
                    ao = math.radians(90.0 * k)
                    # OUTER lobe tip
                    pts.append((vx + vr * math.cos(ao),
                                vy + vr * math.sin(ao)))
                    # INNER notch. *** 0.55, NOT 0.30. *** A first pass pulled
                    # the notch right in to 30%, which made it a thin spiky
                    # STAR - it read as a SPARKLE, not an anger mark. The 💢 is
                    # a FAT CROSS with concave sides. Thicker lobes = a vein.
                    ai = ao + math.radians(45.0)
                    pts.append((vx + vr * 0.55 * math.cos(ai),
                                vy + vr * 0.55 * math.sin(ai)))
                vl = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                ImageDraw.Draw(vl).polygon(
                    pts, fill=(214, 40, 46, int(200 + 55 * th)),
                    outline=(120, 16, 22, 255))
                frame.alpha_composite(vl)
            elif em == "huffing":
                # *** STEAM FROM THE NOSE. *** Two jets, one per nostril.
                # THE OLD ACCENT WAS FURNITURE AND IS DELETED: it was a
                # `(ph * 14 + i * 20) % 40` scroller drawn beside his EARS -
                # puffs that teleported, never formed and never dissipated.
                # This one has a real LIFECYCLE: born at the nostril, billows
                # out, drifts away and DIES. And it comes out of his NOSE,
                # which is what the emoji actually is.
                #
                # IN THE PIL CHAIN, NOT A frame() BRANCH: huffing is in
                # _BLINKABLE with its flag True, so a frame() branch would cost
                # him his blink. Same pattern as anxious's sweat.
                #
                # IMAGE coords (HX/HY) - NOT canvas coords (cx/hy). cx/hy
                # already contain the bob, and using them here would apply the
                # bob TWICE and slide the steam off his face.
                #
                # *** IT DISSIPATES BY SHRINKING, NOT BY FADING. ***
                # The alpha threshold is BINARY (>=110 or gone), so a puff that
                # faded out would POP off at full size. Instead the alpha stays
                # high (230) and the radius follows sin(a*pi): it is born from
                # NOTHING, billows, and shrinks back to NOTHING.
                u = self._huff_u
                if u >= 0.58:                    # steam only on the BLAST
                    st = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                    sd = ImageDraw.Draw(st)
                    s = (u - 0.58) / 0.42
                    for sx in (-1, 1):
                        for i2 in range(3):
                            a = s - i2 * 0.17    # the three puffs are staggered
                            if a <= 0.0 or a >= 1.0:
                                continue
                            r = 8.5 * math.sin(a * math.pi)
                            if r < 0.8:
                                continue
                            # *** THEY MUST TRAVEL CLEAR OF HIS HEAD. ***
                            # The head spans HX +/- 44. A first pass only sent
                            # them 34px, so they never left his face and just
                            # read as white SPLOTCHES ON HIS CHEEKS. They now
                            # run out to ~57px - past the silhouette, into open
                            # air - and DOWNWARD, the way a snort actually goes.
                            px = HX + sx * (5.0 + 52.0 * a)
                            py = HY + 8.0 + 10.0 * a + 10.0 * a * a
                            # OUTLINED, so it reads on ANY wallpaper. A white
                            # blob with no edge vanishes on a light desktop.
                            sd.ellipse([px - r * 1.2, py - r,
                                        px + r * 1.2, py + r],
                                       fill=(240, 240, 244, 232),
                                       outline=(150, 154, 166, 245),
                                       width=2)
                    frame.alpha_composite(st)
            elif em == "sobbing":
                # *** THE FLOOD. NO PAUSE, EVER. ***
                # Crying's whole identity is the ~1.1s of SILENCE between
                # tears - the beat where he holds it together. Sobbing never
                # gets one. Three tears per eye, staggered a third of a cycle
                # apart, so as one dies the next is already welling: the flow
                # NEVER breaks. That absence of a gap IS the emote.
                # Reuses crying's ONE tear sprite - free.
                # IMAGE coords (HX/HY), never canvas coords (cx/hy): the PIL
                # chain runs before the bob is applied, so cx/hy would apply
                # the bob twice and slide the tears off his face.
                el = max(0.0, ph - self._sob_t0)
                spr = self.skin.tear
                for eye_sx in (-1, 1):
                    for i2 in range(3):
                        u = (el * 0.29 + i2 / 3.0
                             + (0.17 if eye_sx > 0 else 0.0)) % 1.0
                        if u < 0.16:
                            s = u / 0.16
                            tx = HX + eye_sx * 16.0
                            ty = HY + 5.0
                            sc = 0.45 + 0.50 * s
                            al = 0.5 + 0.5 * s
                        else:
                            s = (u - 0.16) / 0.84
                            tx = HX + eye_sx * (16.0 + 7.0 * s)
                            ty = HY + 5.0 + 46.0 * (s * s * 0.6 + s * 0.4)
                            sc = 0.95 + 0.15 * s
                            al = 1.0
                        # DIES before it clears him. Chloe's rule: the water
                        # must never pool and never reach the ground.
                        if ty > HY + 20.0:
                            al *= max(0.0, 1.0 - (ty - (HY + 20.0)) / 28.0)
                        if al <= 0.03:
                            continue
                        w2 = max(1, int(round(spr.width * sc)))
                        h2 = max(1, int(round(spr.height * sc)))
                        t2 = spr.resize((w2, h2), Image.LANCZOS)
                        if al < 0.99:
                            t2.putalpha(t2.getchannel("A").point(
                                lambda v, _a=al: int(v * _a)))
                        frame.alpha_composite(
                            t2, (int(round(tx - w2 / 2.0)),
                                 int(round(ty - h2 / 2.0))))
            elif em == "crying":
                # ONE TEAR AT A TIME, AND THEN A PAUSE.
                # *** THE PAUSE IS THE EMOTION. *** He holds it together for a
                # beat, then loses it again. sobbing (next) is the opposite:
                # a continuous flood from both eyes with no restraint at all.
                # The baseline drew a tkinter LINE that scrolled down and
                # wrapped - (ph*30) % 26 - so it never formed and never fell,
                # it TELEPORTED. That accent is now deleted; this replaces it.
                # Born -> swells -> breaks -> rolls -> falls -> DIES.
                # *** IMAGE COORDS (HX/HY), NOT CANVAS COORDS (cx/hy). ***
                # The PIL chain runs on `frame` BEFORE the sprite is placed at
                # (dx, bob) by create_image. cx/hy already contain the bob, so
                # using them here would apply the bob TWICE and the tear would
                # slide off his face as he moves - exactly the class of bug
                # that put a floating red box next to his head on embarrassed.
                el = max(0.0, ph - self._cry_t0)
                u = (el * 0.074) % 1.0          # one full cycle ~4.5s
                spr = self.skin.tear
                tx = ty = None
                sc = al = 1.0
                if u < 0.25:
                    # WELLS on the lower lid. Grows in place, doesn't move.
                    s = u / 0.25
                    tx, ty = HX - 16.0, HY + 6.0
                    sc = 0.30 + 0.55 * s
                    al = 0.35 + 0.65 * s
                elif u < 0.62:
                    # BREAKS and ROLLS down his cheek, picking up speed.
                    s = (u - 0.25) / 0.37
                    tx = HX - 16.0 - 5.0 * s
                    ty = HY + 6.0 + 26.0 * (s * s * 0.55 + s * 0.45)
                    sc = 0.85 + 0.15 * s
                elif u < 0.76:
                    # FALLS AWAY and FADES OUT. Chloe's rule: it must never
                    # pool and never reach the ground. It dies in the air,
                    # still over his body - so it never leaves his silhouette
                    # and never meets the binary alpha threshold in open space.
                    s = (u - 0.62) / 0.14
                    tx = HX - 21.0
                    ty = HY + 32.0 + 30.0 * s * s
                    al = 1.0 - s
                # else: 0.76 -> 1.0 is THE PAUSE. Nothing is drawn. He is
                # holding it together. Then it starts again.
                if tx is not None and al > 0.03:
                    w2 = max(1, int(round(spr.width * sc)))
                    h2 = max(1, int(round(spr.height * sc)))
                    t2 = spr.resize((w2, h2), Image.LANCZOS)
                    if al < 0.99:
                        t2.putalpha(t2.getchannel("A").point(
                            lambda v: int(v * al)))
                    frame.alpha_composite(
                        t2, (int(round(tx - w2 / 2.0)),
                             int(round(ty - h2 / 2.0))))
            elif em == "anxious":
                # THE SWEAT RUNS. This is the emote.
                # `worried` (CONFIRMED) already has a sweat drop - one static
                # bead glued to his temple that never moves. FURNITURE. These
                # ones have a LIFECYCLE: they form on his brow, swell, run down
                # his face, and VANISH before his jaw. Born -> ages -> dies.
                # Chloe's constraint: they must never pool or reach the ground.
                # They don't - they fade out while still on him, which also
                # means they never leave his silhouette and never meet the
                # binary alpha threshold in open space.
                # ph rises 0.12/frame, so ph*6.7 advances the index by ~0.80 -
                # under one step per frame, or the drops would ALIAS and appear
                # to jump or drift backwards (the wagon-wheel trap from dizzy).
                # Composited here rather than in a frame() branch so anxious
                # keeps BLINKING (it's in _BLINKABLE).
                frame.alpha_composite(
                    self.skin.anx_sweat[int(ph * 6.7) % 40])
            elif em == "embarrassed":
                # HE WANTS TO DISAPPEAR.
                # bashful ENJOYS the attention (paws up, smiling, flat pink
                # wash). hot is a physical state (sheen + steam + panting).
                # awkward just fidgets (head-scratch + shifty eyes).
                # This one is MORTIFIED: he shrinks, he leans away, and the
                # flush climbs up his face. None of the three do that.
                el = max(0.0, ph - self._emb_t0)

                # THE FLUSH: blooms up from the cheeks over ~1.5s, then PULSES
                # (he keeps re-realising). Born -> spreads -> lives. bashful's
                # is a static wash that's simply always there - furniture.
                bloom = 1.0 - math.exp(-el * 1.3)
                pulse = 0.86 + 0.14 * math.sin(ph * 1.5)
                t = max(0.0, min(1.0, bloom * pulse))
                # *** DRAWN BEFORE THE LEAN AND THE SHRINK, ON PURPOSE. ***
                # Both of those transform the WHOLE sprite. If the flush went
                # on afterwards it would be painted in un-transformed
                # coordinates and slide straight off his face. If the body
                # transforms, whatever sits on it must transform WITH it.
                frame.alpha_composite(
                    self.skin.embarrassed_flush[int(round(t * 8))])

                # HE LEANS AWAY from you (a small whole-sprite rotation about
                # the FEET) and SHRINKS. The shrink is the exact inverse of
                # scrutinizing's lean-IN (which grows to 1.055 to get closer);
                # this one goes DOWN to ~0.92 - he is trying to be smaller.
                shrink = 1.0 - math.exp(-el * 1.1)
                lean = 5.5 * shrink
                if abs(lean) > 0.05:
                    frame = frame.rotate(lean, center=(CX, CY + 66),
                                         resample=Image.BICUBIC)
                sc = 1.0 - 0.085 * shrink
                if sc < 0.999:
                    nw = max(1, int(round(frame.width * sc)))
                    nh = max(1, int(round(frame.height * sc)))
                    small = frame.resize((nw, nh), Image.LANCZOS)
                    g = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                    g.alpha_composite(small, ((frame.width - nw) // 2,
                                              frame.height - nh))
                    frame = g
            elif em == "nerdy":
                # ROUND THIN-RIMMED GLASSES, drawn in the PIL frame so they
                # can SLIDE. Deliberately the OPPOSITE of cool's shades:
                # those are opaque, chunky, pixelated and HIDE the eyes -
                # these are thin, smooth, and nearly CLEAR, so his (already
                # magnified) eyes read fully through them.
                #
                # They sit `slip` px LOWER as they creep down his nose, and
                # snap back up when the paw pushes them. That slide is the
                # whole gag, and it's why they can't be baked into a plate.
                slip = getattr(self, "_slip", 0.0)
                gl = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                gd = ImageDraw.Draw(gl)
                RIM = (58, 50, 44, 255)
                ey = HY - 3 + slip
                R = 13.8            # roomy enough that GLASS shows around the
                                    # eye - a tight lens just reads as goggles
                for ex in (HX - 16, HX + 16):
                    # lens glass: barely there - a faint cool tint, NOT a
                    # wash. Anything heavier would fight the eye behind it.
                    gd.ellipse([ex - R, ey - R, ex + R, ey + R],
                               fill=(214, 232, 240, 34))
                    # thin rim
                    gd.ellipse([ex - R, ey - R, ex + R, ey + R],
                               outline=RIM, width=2)
                    # a single glass glint - a short diagonal streak. This is
                    # what makes it read as GLASS rather than a drawn circle.
                    gd.line([ex - R * 0.62, ey - R * 0.28,
                             ex - R * 0.16, ey - R * 0.72],
                            fill=(255, 255, 255, 150), width=2)
                # bridge over the nose
                gd.line([HX - 16 + R - 1, ey - 1, HX + 16 - R + 1, ey - 1],
                        fill=RIM, width=2)
                # temple arms running back toward the ears on both sides
                gd.line([HX - 16 - R + 1, ey - 2, HX - 34, ey - 5],
                        fill=RIM, width=2)
                gd.line([HX + 16 + R - 1, ey - 2, HX + 34, ey - 5],
                        fill=RIM, width=2)
                frame.alpha_composite(gl)
            elif em == "scrutinizing":
                # HE LEANS IN AND LOOKS YOU OVER. The prop is an INSTRUMENT
                # here, not an accessory - that's the whole difference from
                # nerdy (worn glasses, passive) and from skeptical (a settled
                # doubting head-cock that just HOLDS).
                # SC = 15.0 ph-units = ~5s (ph advances 3.0/sec).
                SC = 15.0
                us = (ph / SC) % 1.0

                if us < 0.28:                      # LEANS IN toward you
                    lean = (us / 0.28)
                    lean = lean * lean * (3 - 2 * lean)     # smooth
                    scan = 0.0
                elif us < 0.76:                    # THE LOOK-OVER
                    lean = 1.0
                    ks = (us - 0.28) / 0.48
                    # one slow sweep DOWN and back UP - appraising you head
                    # to toe. Slow on purpose: a fast scan reads as a twitch.
                    scan = math.sin(ks * 2 * math.pi)
                else:                              # settles back out
                    lean = 1.0 - (us - 0.76) / 0.24
                    scan = 0.0

                # LEAN IN = he gets BIGGER (closer to you). Whole-sprite scale
                # about the FEET, so there's no seam across the shoulders.
                if lean > 0.01:
                    sc = 1.0 + 0.055 * lean
                    nw = max(1, int(round(frame.width * sc)))
                    nh = max(1, int(round(frame.height * sc)))
                    big = frame.resize((nw, nh), Image.LANCZOS)
                    g = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                    g.alpha_composite(big, ((frame.width - nw) // 2,
                                            frame.height - nh))
                    frame = g
                # the scan itself: a slow vertical drift + a matching head tilt
                if abs(scan) > 0.005:
                    frame = frame.rotate(scan * 2.2, center=(CX, CY + 66),
                                         resample=Image.BICUBIC)
                    frame = _shift(frame, 0, int(round(scan * 3.0)))

                # ---- THE MONOCLE (right eye) --------------------------
                ml = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                md = ImageDraw.Draw(ml)
                GOLD = (188, 150, 74, 255)
                GOLD_D = (140, 106, 46, 255)
                mx, my = HX + 16, HY - 3
                R = 14.2
                # glass
                md.ellipse([mx - R, my - R, mx + R, my + R],
                           fill=(216, 234, 242, 30))
                # gold ring: a dark under-ring then the bright ring on top,
                # so it reads as METAL with thickness rather than a drawn circle
                md.ellipse([mx - R, my - R, mx + R, my + R],
                           outline=GOLD_D, width=4)
                md.ellipse([mx - R + 1, my - R + 1, mx + R - 1, my + R - 1],
                           outline=GOLD, width=2)

                # THE GLINT: a bright streak that SWEEPS across the lens at
                # the moment of judgment (mid look-over). An effect needs a
                # LIFECYCLE - it is born, crosses, and dies. A permanent
                # highlight would just be furniture (the mind_blown lesson).
                if 0.46 < us < 0.60:
                    gk = (us - 0.46) / 0.14
                    ga = int(210 * math.sin(gk * math.pi))    # fades in/out
                    gxs = mx - R + gk * (2 * R)               # sweeps across
                    md.line([gxs - 4, my + 8, gxs + 5, my - 9],
                            fill=(255, 255, 255, ga), width=3)
                    md.line([gxs + 3, my + 7, gxs + 8, my - 5],
                            fill=(255, 255, 255, max(0, ga - 70)), width=2)

                # CHAIN: hangs from the outer edge of the ring, sagging away
                # down to his chest. Drawn with a real droop - a straight line
                # reads as a wire, not a chain.
                cxs, cys = mx + R - 2, my + R - 3
                pts = []
                for i in range(9):
                    f = i / 8.0
                    px = cxs + 8 * f
                    py = cys + 34 * f * f + 6 * f
                    pts.append((px, py))
                md.line(pts, fill=GOLD_D, width=2, joint="curve")
                for i in range(0, 9, 2):        # links catching the light
                    px, py = pts[i]
                    md.ellipse([px - 1.4, py - 1.4, px + 1.4, py + 1.4],
                               fill=GOLD)
                frame.alpha_composite(ml)
            elif em == "confused":
                # *** THE REVERSAL IS THE SIGNATURE. *** He tilts one way,
                # HOLDS ("...wait"), then tilts the OTHER way and holds again
                # ("...no, that's not right either"). He never settles.
                #   skeptical    = tilts ONCE and settles into the doubt.
                #   thinking     = productive; he's working on it.
                #   scrutinizing = leans in and examines you.
                #   confused     = CANNOT RESOLVE. It reverses. That's the gag.
                # CC = 18.0 ph-units = ~6s (ph advances 3.0/sec).
                CC = 18.0
                uc = (ph / CC) % 1.0
                A = 6.0
                if uc < 0.16:                       # tilt one way
                    t = uc / 0.16
                    ang = A * (t * t * (3 - 2 * t))
                elif uc < 0.38:                     # HOLD ("...wait")
                    ang = A
                elif uc < 0.58:                     # REVERSE, through zero
                    t = (uc - 0.38) / 0.20
                    ang = A * (1 - 2 * (t * t * (3 - 2 * t)))
                elif uc < 0.82:                     # HOLD the other way
                    ang = -A
                else:                               # come back to level
                    t = (uc - 0.82) / 0.18
                    ang = -A * (1 - (t * t * (3 - 2 * t)))
                # a tiny drift so a HOLD never looks like a frozen frame
                ang += math.sin(ph * 0.7) * 0.5
                frame = frame.rotate(ang, center=(CX, CY + 66),
                                     resample=Image.BICUBIC)

                # THE QUESTION MARK - and it has a LIFECYCLE: it is born,
                # rises, wobbles, and DIES. A "?" permanently stapled over his
                # head would be furniture, not an effect (the mind_blown
                # yellow-rays lesson). It swells during the holds - the beats
                # where he's most stuck - and fades out through the reversal.
                if uc < 0.38:
                    life = min(1.0, uc / 0.10)
                elif uc < 0.58:
                    life = max(0.0, 1.0 - (uc - 0.38) / 0.12)   # dies
                elif uc < 0.82:
                    life = min(1.0, (uc - 0.58) / 0.10)         # reborn
                else:
                    life = max(0.0, 1.0 - (uc - 0.82) / 0.12)
                if life > 0.02:
                    ql = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                    qd = ImageDraw.Draw(ql)
                    aa = int(235 * life)
                    QC = (96, 84, 74)
                    # sits off to the side, clear of the antennae, and RISES
                    # a little as it lives. On his LEFT (Chloe's call) - the
                    # glyph itself is NOT mirrored, only its position moves,
                    # or it would stop reading as a "?".
                    qx = HX - 40
                    qy = (HY - 52) - life * 7 + math.sin(ph * 1.6) * 1.8
                    sc = 0.75 + 0.25 * life          # swells in
                    # the hook of the "?"
                    qd.arc([qx - 8 * sc, qy - 11 * sc,
                            qx + 8 * sc, qy + 3 * sc],
                           start=170, end=20, fill=QC + (aa,),
                           width=max(1, int(3 * sc)))
                    # the tail curling down to the stem
                    qd.line([qx + 7 * sc, qy - 1 * sc,
                             qx + 1 * sc, qy + 7 * sc],
                            fill=QC + (aa,), width=max(1, int(3 * sc)))
                    # the dot
                    qd.ellipse([qx - 1 * sc, qy + 11 * sc,
                                qx + 3 * sc, qy + 15 * sc],
                               fill=QC + (aa,))
                    frame.alpha_composite(ql)
            elif em == "skeptical":
                # SKEPTICAL HEAD-COCK: he tilts, then HOLDS it - the "go on,
                # I'm listening... sure you are" beat. Deliberately NOT the
                # continuous sway of zany: a doubting look is a settled
                # posture, not a wobble.
                # tanh-style ease: rises quickly to ~5 deg and then flattens
                # out, so most of the cycle is spent holding the tilt rather
                # than passing through it. A slow shallow drift keeps it from
                # looking like a frozen frame.
                hold = 1.0 - math.exp(-ph * 1.4)          # ease in, then hold
                drift = math.sin(ph * 0.5) * 0.8          # tiny life
                ang = -(5.0 * hold + drift)
                frame = frame.rotate(ang, center=(CX, CY + 66),
                                     resample=Image.BICUBIC)
            elif em == "zany":
                # goofy-drunk woozy roll: a wide, SLOW lean that never quite
                # repeats. Two detuned sine terms (1.1 and 0.37 Hz-ish) beat
                # against each other so the sway is lopsided and unsteady
                # instead of a clean metronome - that irregularity is what
                # sells "can't hold himself upright". Pivots low at the feet
                # like innocent's, so he leans as one piece.
                ang = (math.sin(ph * 1.1) * 7.0
                       + math.sin(ph * 0.37 + 1.3) * 3.5)
                frame = frame.rotate(ang, center=(CX, CY + 66),
                                     resample=Image.BICUBIC)
            mask = frame.getchannel("A").point(
                lambda a: 255 if a >= 110 else 0)
            bg.paste(frame, (0, 0), mask)
        self._photo = ImageTk.PhotoImage(bg)
        cv.create_image(dx, bob, anchor="nw", image=self._photo)
        # antigrav hover plume: a downward-tapering STACK of rings (not
        # concentric) - widest just under his feet, each one below it
        # smaller and lower, so nothing reaches the window's side edges.
        # Gentle downward drift + fade animates the "thrust". MUST be
        # drawn AFTER create_image above: canvas items stack in creation
        # order (later = on top), and the character image is a fully
        # opaque rectangle (magenta + character, no per-pixel alpha at
        # the Tkinter level) - drawing rings before it meant the image
        # painted straight over them every frame, invisibly.
        ring_cx = cx
        # World-space hover plume (fixed, upright). For rofl it sits ~33px
        # higher (his sprite pastes shifted up) and carries the launch/
        # return DROP from _rofl_cycle, so the plume dives off-frame as he
        # launches into the spin and rises back to meet his feet at the
        # tail - the rings never rotate or track his feet mid-spin.
        if em == "rofl":
            ring_top = CY + 63 + bob + rofl_ring_drop
        else:
            ring_top = CY + 96 + bob
        try:
            for i in range(4):
                t = ((ph * 0.8) + i / 4.0) % 1.0
                depth = i + t              # 0..4, descending index
                rw = max(2, 30 - depth * 6.5)  # widest top, shrink
                rh = rw * 0.34
                ry = ring_top + depth * 13
                a = 1 - (depth / 4.0)      # fade as they descend
                if a <= 0.08:
                    continue
                g = min(255, 150 + int((1 - a) * 90))
                r = min(255, 90 + int((1 - a) * 90))
                col = f"#{r:02x}{g:02x}ff"
                cv.create_oval(ring_cx - rw, ry - rh,
                               ring_cx + rw, ry + rh,
                               outline=col, width=max(1, int(3 * a)))
        except tk.TclError:
            pass
        # confetti (now in front - reads better over the render)
        for p in self.particles:
            s = p["s"]
            cv.create_rectangle(p["x"], p["y"], p["x"] + s, p["y"] + s,
                                fill=p["c"], outline="")
        # emote accents around the figure
        if em == "happy":
            # delighted sparkles: little twinkling 4-point stars by his cheeks
            for i2, (sxo, syo, spd) in enumerate(
                    ((-54, -10, 1.0), (52, -18, 1.3))):
                tw = 0.5 + 0.5 * math.sin(ph * spd * 2 + i2)
                sz = 3 + tw * 4
                sx2 = cx + sxo
                sy2 = hy + syo
                col = "#FFF3B0" if i2 == 0 else "#FFFFFF"
                cv.create_line(sx2 - sz, sy2, sx2 + sz, sy2,
                               fill=col, width=2)
                cv.create_line(sx2, sy2 - sz, sx2, sy2 + sz,
                               fill=col, width=2)
        elif em == "thinking":
            k = int(ph * 2) % 3
            for i2 in range(3):
                sz = 5 if i2 == k else 3
                bx = cx + 50 + i2 * 13
                by = hy - 46 - i2 * 11
                cv.create_oval(bx - sz, by - sz, bx + sz, by + sz,
                               fill="#FFFFFF", outline=BODY_EDGE)
        elif em == "alert":
            cv.create_line(cx + 52, hy - 60, cx + 52, hy - 40,
                           fill=RED, width=6, capstyle=tk.ROUND)
            cv.create_oval(cx + 49, hy - 32, cx + 55, hy - 26,
                           fill=RED, outline="")
        elif em == "sleepy":
            for i2 in range(3):
                yoff = (ph * 12 + i2 * 22) % 66
                cv.create_text(cx + 50 + i2 * 6, hy - 40 - yoff,
                               text="z",
                               font=("Segoe UI", 9 + i2 * 3, "bold"),
                               fill="#7A6A5F")
        elif em == "love":
            for i2 in range(3):
                yoff = (ph * 10 + i2 * 24) % 70
                cv.create_text(cx - 58 - i2 * 8, cy - 30 - yoff,
                               text="\u2665",
                               font=("Segoe UI", 10 + i2 * 2), fill=RED)
        elif em == "excited":
            for i2 in range(4):
                a = ph * 1.5 + i2 * (math.pi / 2)
                sx2 = cx + math.cos(a) * 78
                sy2 = cy + math.sin(a) * 78
                cv.create_text(sx2, sy2, text="+", fill="#F2B84B",
                               font=("Segoe UI", 13, "bold"))
        elif em == "terrified":
            # NO tears. Chattering teeth (fixed white upper row + a lower
            # row that clacks up-and-down fast) over the dark gape, plus
            # Scooby-Doo fright vibration lines flickering on both sides.
            mmy = hy + 19
            chat = abs(math.sin(ph * 20)) * 2.6
            cv.create_rectangle(cx - 6, mmy - 4, cx + 6, mmy - 1,
                                fill="#FFFCF6", outline="#2E211B")
            cv.create_rectangle(cx - 5, mmy + 2 + chat, cx + 5,
                                mmy + 5 + chat, fill="#FFFCF6",
                                outline="#2E211B")
            for tx in (cx - 3, cx, cx + 3):
                cv.create_line(tx, mmy - 4, tx, mmy - 1, fill="#2E211B")
            for sido in (-1, 1):
                bx = cx + sido * 54
                for i2 in range(3):
                    yy = hy - 8 + i2 * 20
                    ln = 5 + abs(math.sin(ph * 24 + i2 * 1.7)) * 6
                    cv.create_line(bx, yy, bx + sido * ln, yy,
                                   fill="#B8BCC2", width=2)
        elif em in ("laughing", "laughing_crying"):
            # mouth pulses open/closed for the "ha-ha-ha" flutter - a
            # wide SMILE silhouette (corners turned up), not a circle
            op = 0.35 + 0.65 * abs(math.sin(ph * 6))
            mw = 11.5
            mh = 3.0 + 5.0 * op
            my_ = hy + 19
            pts = [
                cx - mw, my_ - mh * 0.55, cx - mw * 0.5, my_ - mh * 0.95,
                cx, my_ - mh, cx + mw * 0.5, my_ - mh * 0.95,
                cx + mw, my_ - mh * 0.55, cx + mw * 0.62, my_ + mh * 0.5,
                cx, my_ + mh, cx - mw * 0.62, my_ + mh * 0.5,
            ]
            cv.create_polygon(pts, smooth=True, fill="#6C3E2E",
                              outline="#2E211B", width=2)
            if op > 0.45:
                cv.create_rectangle(cx - 6, my_ - mh, cx + 6,
                                    my_ - mh + 4, fill="#FFFCF6",
                                    outline="#2E211B")
            if em == "laughing_crying":
                for sx3 in (-16, 16):
                    drip = (ph * 44 + (12 if sx3 > 0 else 0)) % 26
                    cv.create_line(cx + sx3, hy + 6 + drip, cx + sx3,
                                   hy + 14 + drip, fill="#7FC4E8", width=4,
                                   capstyle=tk.ROUND)
        elif em in ("adoring", "hug"):
            for i2 in range(2):
                yoff = (ph * 9 + i2 * 30) % 60
                cv.create_text(cx - 50 - i2 * 6, cy - 24 - yoff,
                               text="\u2665",
                               font=("Segoe UI", 9 + i2), fill=RED)
        elif em == "kiss":
            # floaty hearts on the left (restored - same as adoring/hug)
            for i2 in range(2):
                yoff = (ph * 9 + i2 * 30) % 60
                cv.create_text(cx - 50 - i2 * 6, cy - 24 - yoff,
                               text="\u2665", font=("Segoe UI", 9 + i2),
                               fill=RED)
            # blow a kiss: the real lips emoji forms over his mouth and
            # GROWS toward the camera, holds a beat, pops a touch bigger,
            # then vanishes - looping while the emote is active.
            KC = 7.0
            u = (ph / KC) % 1.0
            lh = None
            rise = 0.0
            if u < 0.20:
                lh = None
            elif u < 0.62:
                t = (u - 0.20) / 0.42
                lh = 12 + t * 34
                rise = t * 6
            elif u < 0.80:
                lh = 46
                rise = 6
            elif u < 0.90:
                t = (u - 0.80) / 0.10
                lh = 46 + t * 14
                rise = 6
            if lh is not None:
                ly = hy + 19 - rise
                if self._lips_base is not None:
                    base = self._lips_base
                    th = max(6, int(lh))
                    tw = max(6, int(th * base.width / base.height))
                    self._lips_photo = ImageTk.PhotoImage(
                        base.resize((tw, th), Image.LANCZOS))
                    cv.create_image(cx, ly, image=self._lips_photo,
                                    anchor="center")
                else:
                    s = lh / 30.0
                    W, H = 11 * s, 9 * s
                    LIP, LIP_DK = "#D9455A", "#A5324A"
                    upper = [cx - W, ly, cx - W * 0.5, ly - H * 0.5,
                             cx - W * 0.15, ly - H * 0.05, cx, ly - H * 0.22,
                             cx + W * 0.15, ly - H * 0.05, cx + W * 0.5,
                             ly - H * 0.5, cx + W, ly]
                    lower = [cx - W, ly, cx + W, ly, cx + W * 0.6,
                             ly + H * 0.75, cx, ly + H, cx - W * 0.6,
                             ly + H * 0.75]
                    cv.create_polygon(lower, fill=LIP, outline=LIP_DK)
                    cv.create_polygon(upper, fill=LIP, outline=LIP_DK)
        elif em == "playful_tongue":
            # raspberry tongue: a wide flat pink tongue rooted inside the
            # open grin and protruding down, wiggling fast side-to-side
            # (the 'blowing a raspberry' vibration). No brow bounce.
            my = hy + 18
            wag = math.sin(ph * 9) * 3.0
            tip = my + 13
            pts = [cx - 8, my + 1, cx + 8, my + 1,
                   cx + 7 + wag, tip - 4, cx + wag, tip,
                   cx - 7 + wag, tip - 4]
            cv.create_polygon(pts, fill="#E87C88", outline="#B84E5C",
                              width=2, smooth=1)
            cv.create_line(cx + wag * 0.4, my + 3, cx + wag, tip - 2,
                           fill="#B84E5C", width=1)
        elif em == "yummy":
            # LIP LICK: the tongue emerges, sweeps ACROSS the lips, then
            # retracts and rests a beat before going again. The sweep (not a
            # static hanging tongue) is what makes this "savoring something
            # delicious" instead of a copy of silly / playful_tongue.
            #
            # Cycle: 0.00-0.15 out | 0.15-0.60 sweep across | 0.60-0.72 in |
            #        0.72-1.00 rest (mouth closed, no tongue drawn).
            LC = 2.6                      # seconds per lick cycle
            u = (ph / LC) % 1.0
            my = hy + 19
            if u < 0.72:
                if u < 0.15:              # extend
                    ext = u / 0.15
                    trav = -1.0
                elif u < 0.60:            # sweep left -> right
                    ext = 1.0
                    trav = -1.0 + 2.0 * ((u - 0.15) / 0.45)
                else:                     # retract
                    ext = 1.0 - (u - 0.60) / 0.12
                    trav = 1.0
                # ease the travel so it slows at the corners (a real lick
                # lingers at the edges rather than sliding at constant speed)
                tx = cx + math.sin(trav * 1.5708) * 8.0
                # ride ON the lip line, not below it - the tongue should
                # overlap the smile, not float under the chin
                ty = my - 1 + 2.5 * ext
                w = 5.0 * ext + 1.2
                h = 3.4 * ext + 0.8
                # tongue: a soft rounded lobe. Drawn as an OVAL (not a
                # polygon) - an angular polygon here reads as a hexagonal
                # blob stuck to his face rather than a tongue.
                cv.create_oval(tx - w, ty - h, tx + w, ty + h,
                               fill="#E87C88", outline="#B84E5C", width=2)
                # a glossy highlight so it reads wet
                cv.create_oval(tx - w * 0.5, ty - h * 0.6,
                               tx - w * 0.05, ty - h * 0.05,
                               fill="#F3A8B0", outline="")
        elif em == "cool":
            # NOTE: the old flat tkinter rectangle "sunglasses" was REMOVED.
            # It was a static bar with no motion at all. The real "deal with
            # it" pixel shades are drawn in the PIL chain (see em == "cool"
            # there) so they can drop in and so the pixels stay crunchy -
            # tkinter can't antialias OR animate them the way this needs.
            pass
        elif em == "nerdy":
            # NOTE: the old flat tkinter oval "glasses" were REMOVED. They
            # were static, couldn't slide, and tkinter has no real alpha so
            # the lenses could never be transparent. The real round glasses
            # are drawn in the PIL chain (see em == "nerdy" there).
            pass
        elif em == "scrutinizing":
            # NOTE: the old flat tkinter monocle (a static oval + a straight
            # line for the chain) was REMOVED. It couldn't glint, the chain
            # didn't hang, and tkinter has no real alpha so the glass could
            # never be transparent. The real monocle is drawn in the PIL chain.
            pass
        elif em == "money_eyes":
            # FULL JACKPOT. Four parts, all per-frame (the plate is eyeless
            # and mouth-only, so everything that MOVES lives here):
            #   1. $ eyes that breathe, with a periodic KA-CHING scale punch
            #   2. a green cash bill clenched in the teeth
            #   3. $ symbols floating up
            #   4. bills fluttering DOWN around him (it's raining money)
            GREEN = "#3E9E52"
            DARKG = "#256B36"
            # --- 1. pulsing $ eyes -------------------------------------
            # slow breathe + a sharp punch on a ~1.9s beat (fast attack,
            # slower settle) so it reads as a cash-register "ka-ching" hit
            # rather than a smooth throb.
            KC = 1.9
            k = (ph / KC) % 1.0
            if k < 0.12:                       # punch: snap out
                punch = k / 0.12
            elif k < 0.42:                     # settle back down
                punch = 1.0 - (k - 0.12) / 0.30
            else:
                punch = 0.0
            sc = 1.0 + 0.10 * math.sin(ph * 2.2) + 0.42 * punch
            # Draw the $ as a real TEXT GLYPH at a scaled font size, not as
            # hand-assembled arcs. Two arcs + a bar is fiddly to get right at
            # this size - the first attempt's bowls curved the same way and
            # read as UP/DOWN ARROWS, not dollar signs. A font glyph is
            # always a correct "$", and scaling the font size gives the
            # pulse/ka-ching for free.
            fsz = max(8, int(round(17 * sc)))
            for sx3 in (-16, 16):
                cv.create_text(cx + sx3, hy - 4, text="$", fill=GREEN,
                               font=("Segoe UI", fsz, "bold"))
            # --- 2. cash bill clenched in the teeth --------------------
            # sits LOW and hangs out of the grin, tilted slightly, so it's
            # clearly a banknote in his mouth rather than a green smudge on
            # the lip line
            my = hy + 22
            bw, bh = 17, 9
            cv.create_rectangle(cx - bw, my - bh / 2, cx + bw, my + bh / 2,
                                fill="#A8DDB4", outline=DARKG, width=1)
            cv.create_rectangle(cx - bw + 3, my - bh / 2 + 2,
                                cx + bw - 3, my + bh / 2 - 2,
                                outline=DARKG)
            cv.create_text(cx, my, text="$", fill=DARKG,
                           font=("Segoe UI", 7, "bold"))
            # --- 3. $ symbols floating UP ------------------------------
            # off to his LEFT, clear of the body (same lane the adoring/kiss
            # hearts use) so they never drift across the face
            for i2 in range(3):
                yoff = (ph * 11 + i2 * 24) % 62
                cv.create_text(cx - 50 - i2 * 7, cy - 22 - yoff,
                               text="$", fill=GREEN,
                               font=("Segoe UI", 10 + (i2 % 2), "bold"))
            # --- 4. bills raining DOWN ---------------------------------
            # Kept OUT of his silhouette: they fall in two side channels
            # (well left and well right of the body) rather than anywhere
            # across the sprite. A bill landing across his eye/face reads as
            # a bug, not as rain - the head must stay clear.
            for i2 in range(6):
                side = -1 if i2 % 2 == 0 else 1
                lane = i2 // 2                       # 0,1,2 per side
                t = (ph * 0.40 + i2 * 0.17) % 1.0
                bx = (cx + side * (52 + lane * 13)
                      + math.sin(ph * 1.3 + i2) * 5)
                by = cy - 86 + t * 170
                # tumble: the bill's width squashes through zero as it flips
                flip = abs(math.cos(ph * 2.4 + i2 * 1.1))
                fw = 8.5 * flip + 1.2
                fh = 5.0
                cv.create_rectangle(bx - fw, by - fh, bx + fw, by + fh,
                                    fill="#8FCF9C", outline=DARKG, width=1)
                # inner frame + a tiny $ so it reads as a BANKNOTE and not
                # a plain green rectangle (only when the flip is wide enough
                # to show any detail)
                if fw > 5.0:
                    cv.create_rectangle(bx - fw + 2, by - fh + 1.5,
                                        bx + fw - 2, by + fh - 1.5,
                                        outline=DARKG)
                    cv.create_text(bx, by, text="$", fill=DARKG,
                                   font=("Segoe UI", 5, "bold"))
        elif em == "confused":
            # NOTE: the old baseline "?" was REMOVED. It was a STATIC tkinter
            # text glyph parked over his head every frame with no lifecycle -
            # and it double-drew alongside the real one, so he had TWO
            # question marks. The real "?" is in the PIL chain, where it is
            # born, rises, wobbles and DIES with the confusion beats.
            pass
        elif em == "cold":
            # drifting snow: small white specks falling slowly with a
            # gentle sideways sway, wrapping around. Anchored to the
            # window center (not cx) so they don't jitter with his shiver.
            scx = self.w // 2
            top = hy - 74
            span = 172
            for i2 in range(12):
                seedx = (i2 * 53) % 150 - 75
                speed = 11 + (i2 % 3) * 3
                yy = top + ((ph * speed + i2 * 27) % span)
                drift = math.sin(ph * 1.3 + i2) * 7
                xx = scx + seedx + drift
                r = 1.6 + (i2 % 3) * 0.7
                cv.create_oval(xx - r, yy - r, xx + r, yy + r,
                               fill="#EAF6FF", outline="")
        elif em == "silly":
            # crossed, precessing eye-beads. He has no pupils, so the
            # whole bead orbits an OFF-CENTER pivot; left & right run in
            # OPPOSITE phase. The crossed pose (pulled inward) carries the
            # goofy read - the roll is now a small, slow wobble (was too
            # busy). The silly plate is eyeless - these ARE his eyes.
            theta = ph * 2.0
            cross = 7
            for side, base_ex, phase in ((-1, cx - 16, 0.0),
                                         (1, cx + 16, math.pi)):
                ecx = base_ex - side * cross
                ecy = hy - 4
                pvx = ecx + side * 1.0
                pvy = ecy + 0.6
                ox = pvx + math.cos(theta + phase) * 1.5
                oy = pvy + math.sin(theta + phase) * 1.2
                r = 6.5
                cv.create_oval(ox - r, oy - r * 1.05, ox + r, oy + r * 1.05,
                               fill="#3A2A22", outline="")
                cv.create_oval(ox - r * 0.5, oy - r * 0.72, ox - r * 0.05,
                               oy - r * 0.25, fill="#EDE6DE", outline="")
        # NOTE: mind_blown's old tkinter-canvas accent was REMOVED here.
        # It drew 5 static yellow (#F2B84B) rays fanning off his head EVERY
        # frame, with no dissipation - so they were still sitting there after
        # the head had landed again (Chloe: "they don't dissipate... it looks
        # weird"). The PIL blast (flash + billowing cloud + debris + the lid
        # itself) does the job; the rays add nothing.


def is_gaming():
    try:
        with open(STATUSF, "r", encoding="utf-8") as f:
            return bool(json.load(f).get("gaming"))
    except (OSError, ValueError):
        return False


COMFY_HOST = "http://localhost:8188"


def _detect_lan_ip():
    """This machine's own LAN IP, derived at runtime - needed when we hand an
    image URL to an EXTERNAL caller (NAS / Home Assistant), because "localhost"
    in that URL would mean THEIR machine, not ours. Opening a UDP socket toward
    a public address doesn't actually send anything; it just makes the OS pick
    the primary outbound interface so we can read its local address. Falls back
    to localhost if detection fails (single-machine setups still work)."""
    import socket
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        if s is not None:
            s.close()


BRAIN_LAN_IP = _detect_lan_ip()


def generate_zimage(prompt, filename_prefix="buddy"):
    """
    The one and only place the Z-Image ComfyUI workflow is built and run.
    Used by both the chat-triggered desktop popup (gen_image) and the
    HTTP /generate_image endpoint (for the NAS MCP server / Home Assistant).
    Returns the output filename (str) on success, or None on failure.
    """
    workflow = {
        "1": {"class_type": "UNETLoader", "inputs": {
            "unet_name": "z_image_turbo_int8_convrot.safetensors",
            "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {
            "clip_name": "qwen_3_4b_fp8_mixed.safetensors",
            "type": "lumina2"}},
        "3": {"class_type": "VAELoader",
              "inputs": {"vae_name": "ae.safetensors"}},
        "4": {"class_type": "CLIPTextEncode",
              "inputs": {"text": prompt, "clip": ["2", 0]}},
        "5": {"class_type": "CLIPTextEncode",
              "inputs": {"text": "", "clip": ["2", 0]}},
        "6": {"class_type": "EmptySD3LatentImage", "inputs": {
            "width": 1024, "height": 1024, "batch_size": 1}},
        "7": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["4", 0], "negative": ["5", 0],
            "latent_image": ["6", 0],
            "seed": int(time.time()) % 2147483647, "steps": 9, "cfg": 1.0,
            "sampler_name": "res_multistep", "scheduler": "simple",
            "denoise": 1.0}},
        "8": {"class_type": "VAEDecode",
              "inputs": {"samples": ["7", 0], "vae": ["3", 0]}},
        "9": {"class_type": "SaveImage",
              "inputs": {"images": ["8", 0], "filename_prefix": filename_prefix}},
    }
    try:
        body = json.dumps({"prompt": workflow}).encode()
        req = urllib.request.Request(
            COMFY_HOST + "/prompt", data=body,
            headers={"Content-Type": "application/json"})
        resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
        pid = resp.get("prompt_id")
        if not pid:
            return None
    except Exception:
        return None

    for _ in range(120):
        time.sleep(1)
        try:
            h = json.loads(urllib.request.urlopen(
                f"{COMFY_HOST}/history/{pid}", timeout=10).read())
        except Exception:
            continue
        if pid in h:
            imgs = h[pid].get("outputs", {}).get("9", {}).get("images", [])
            if imgs:
                return imgs[0]["filename"]
            return None
    return None

class BuddyHTTP(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/status":
            st = {}
            try:
                with open(STATUSF, "r", encoding="utf-8") as f:
                    st = json.load(f)
            except (OSError, ValueError):
                pass
            self._send(200, {"buddy": "alive", "llm": st})
        elif self.path.startswith("/image/"):
            fname = self.path[len("/image/"):]
            # only a bare filename - no path traversal
            if "/" in fname or "\\" in fname or ".." in fname:
                self._send(400, {"error": "invalid filename"})
                return
            fpath = os.path.join(
                r"G:\Buddy AI\ComfyUI_windows_portable\ComfyUI\output", fname)
            if not os.path.isfile(fpath):
                self._send(404, {"error": "not found"})
                return
            with open(fpath, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self._send(404, {"error": "unknown path"})

    def do_POST(self):
        if self.path == "/say" and BUDDY is not None:
            try:
                n = int(self.headers.get("Content-Length", 0))
                d = json.loads(self.rfile.read(n).decode())
                BUDDY.results.put({
                    "text": str(d.get("text", ""))[:400],
                    "emote": str(d.get("emote", "happy"))})
                self._send(200, {"ok": True})
            except (ValueError, TypeError) as e:
                self._send(400, {"error": str(e)})
        elif self.path == "/generate_image":
            try:
                n = int(self.headers.get("Content-Length", 0))
                d = json.loads(self.rfile.read(n).decode())
                prompt = str(d.get("prompt", "")).strip()
            except (ValueError, TypeError) as e:
                self._send(400, {"status": "error", "error": str(e)})
                return
            if not prompt:
                self._send(400, {"status": "error",
                                 "error": "missing 'prompt'"})
                return
            if is_gaming():
                self._send(200, {"status": "busy",
                                 "error": "brain is gaming, GPU unavailable"})
                return
            # Proxy to Buddy AI's direct/deterministic generation endpoint
            # (no LLM decision loop - NAS/HA already knows it wants an
            # image). Buddy AI does the actual generation natively.
            try:
                body = json.dumps({"prompt": prompt}).encode()
                req = urllib.request.Request(
                    BUDDY_AI_URL + "/generate", data=body,
                    headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=120) as r:
                    result = json.loads(r.read().decode())
            except Exception as e:
                self._send(200, {"status": "error", "error": str(e)})
                return
            if result.get("status") == "ok" and result.get("filename"):
                # served by OUR own /image/ route (ComfyUI's server is
                # retired, so its old :8188/view no longer exists)
                url = (f"http://{BRAIN_LAN_IP}:{HTTP_PORT}/image/"
                       f"{result['filename']}")
                self._send(200, {"status": "ok", "url": url,
                                 "image_url": url})
            else:
                self._send(200, {"status": result.get("status", "error"),
                                 "error": result.get("error",
                                                     "generation failed")})
        else:
            self._send(404, {"error": "unknown path"})

def start_http():
    try:
        ThreadingHTTPServer(("0.0.0.0", HTTP_PORT),
                            BuddyHTTP).serve_forever()
    except OSError:
        pass

if __name__ == "__main__":
    Buddy()
