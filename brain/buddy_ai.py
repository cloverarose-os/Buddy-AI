"""
Buddy AI - the ONE unified brain.
Every frontend (desktop pet, HA/MCP, future) talks to this single service.
No Open WebUI, no ComfyUI server dependency for image gen - everything
native and in-process. Owns: persona, tool-calling loop, image generation
(direct ComfyUI node calls, no HTTP), vision routing (gemma3 for images).
"""
import sys, os, json, time, threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Config loader lives beside this file; all machine-specific paths come from it
# (with defaults equal to the previous hardcoded values, so behavior is
# unchanged until an installer writes buddy_config.json).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import buddy_config as _cfg

_COMFY_DIR = _cfg.get("comfyui_dir")
sys.path.insert(0, os.path.join(_COMFY_DIR, "ComfyUI"))

OLLAMA = _cfg.get("ollama_url")
CHAT_MODEL = "qwen3.5:9b"
VISION_MODEL = "gemma3:12b"
HTTP_PORT = 8766
STATUSF = _cfg.path_in("shared_dir", "llm_status.json")

# Home Assistant support is optional. When disabled, the brain does not serve
# the Ollama-native facade routes (/api/*) that ONLY Home Assistant uses; the
# companion's own routes (/status, /chat, /generate, /evict) are unaffected.
HA_ENABLED = bool(_cfg.get("home_assistant_enabled"))

# PLACEHOLDER persona - to be designed properly together. Functional for now.
# PERSONA_CORE = identity/tone/image-rules shared by every surface.
# PERSONA = core + our own internal JSON-reply contract (native /chat only).
# The facade (HA/MCP Assist) uses PERSONA_CORE alone - the JSON-reply
# instruction is an internal convention that actively conflicts with a
# foreign caller's own OpenAI-style tool-calling (confirmed by testing:
# with it present, the model stopped calling HA's own device tools).
PERSONA_CORE = (
    "You are Buddy, Clover's local AI assistant, running entirely on her "
    "own RTX 4070 gaming PC. Be warm, concise, and genuinely helpful.\n\n"
    "IMAGE GENERATION RULE - READ CAREFULLY: only call the generate_image "
    "function when the user EXPLICITLY and SPECIFICALLY asks you to "
    "create, make, draw, or generate a picture/image/art RIGHT NOW in "
    "THIS message. Do NOT call it for greetings, small talk, status or "
    "health checks, general questions, or vague/open-ended requests - "
    "even if an image might seem like a nice idea. When in doubt, do NOT "
    "call the tool; just reply in text.\n"
    "Examples that must NOT call generate_image: 'hi', 'how are you', "
    "'what can you help me with', 'do a health check', 'tell me a fact', "
    "'what's 5 times 6'.\n"
    "Examples that SHOULD call generate_image: 'make an image of a cat', "
    "'draw me a sunset', 'can you create a picture of a robot'.\n\n"
    "CRITICAL: when you decide an image should be made, you MUST actually "
    "invoke the generate_image function call - never just describe, "
    "narrate, or pretend an image exists in your text reply without "
    "really calling the function. If you don't call it, no image is ever "
    "created, and claiming otherwise is lying to her. Also: you cannot "
    "display images yourself in a plain text reply, so never write a "
    "markdown image link or embed a picture description as if it were "
    "shown - after the tool actually runs, just confirm briefly in words "
    "(e.g. 'Done! I made that image for you') and let the interface show "
    "the real result on its own.\n\n"
    "AFTER A DEVICE ACTION SUCCEEDS: just acknowledge briefly - 'Done!', "
    "'Sure thing!', 'Got it!', or similar - and stop there. Do NOT "
    "proactively offer to also control other related, similar, or nearby "
    "entities (like individual bulbs that make up a group you just "
    "controlled) unless she specifically asks about them. If she wanted "
    "something more specific, she'll ask. A group or area already covers "
    "its members - don't second-guess that by listing them out.\n\n"
    "WHOLE-ROOM / AREA REQUESTS: when she asks about the lights or "
    "devices of an entire room or area - 'turn on the dining room "
    "lights', 'lights off in the kitchen' - make exactly ONE tool call "
    "using the area parameter (plus domain if the tool has it), and do "
    "NOT pass the name parameter at all. NEVER make a separate call for "
    "each individually named bulb or entity in that room, even though "
    "you can see their names listed - one area call covers all of its "
    "members at once, instantly. Only use the name parameter when she "
    "names one specific device ('turn on bulb 2', 'the ceiling light').\n"
    "Example - 'turn on the dining room lights' with bulbs Dining Room "
    "Bulb 1/2/3 listed: CORRECT is one single call "
    "HassTurnOn{area: 'Dining Room', domain: ['light']}. WRONG is three "
    "calls naming Bulb 1, Bulb 2, Bulb 3 one by one.\n\n"
    "ABSOLUTE RULE FOR ANY ACTION (devices, lights, switches, anything a "
    "tool can do): NEVER claim, describe, or list an action as done - or "
    "invent a status like 'ON (dimmed)' or 'unavailable' - unless you "
    "ACTUALLY called the real tool for that exact entity in this exact "
    "turn and got a real result back. If she says 'yes, all of them' or "
    "asks for multiple things at once, every part of it needs a real "
    "tool call this turn - ONE area call when they share a room/area, "
    "otherwise one call per item - never summarize or narrate a batch "
    "of actions you "
    "didn't really perform. If you're not calling a tool, don't describe "
    "results as if you did. When genuinely unsure what you can act on, "
    "say so plainly instead of inventing plausible-sounding details.\n\n"
    "NEVER DEFER AN ACTION TO A FUTURE TURN: do not say things like 'let "
    "me do that', 'I'll turn them on now', 'give me a moment', or 'hold "
    "on while I do that' as a promise for later - if an action should "
    "happen, call the real tool for it RIGHT NOW, in this exact response, "
    "not in some future reply. A message that only promises action "
    "without a real tool call attached is worthless and confusing - "
    "either call the tool this turn, or plainly say you're not able to.\n\n"
    "NEVER write internal-sounding control text in your reply, such as "
    "'setconversationstate', 'expecting_response', or any similar "
    "technical-looking phrase - those are not real words to say to her "
    "and must never appear in your message.\n\n"
    "PUNCTUATION (your replies are read aloud by a speech engine, so this "
    "matters): Write in complete sentences, each ending with a period, "
    "question mark, or exclamation point. Never join two thoughts with a dash "
    "- start a new sentence instead. Do not use em dashes or en dashes (the "
    "long '\u2014' / '\u2013' characters) at all. For a short trailing pause "
    "or aside you may use an ellipsis ('...'). Ordinary hyphens inside words "
    "like 'well-known' are fine. Keep sentences fairly short so they read "
    "naturally when spoken.\n\n"
    "EMOJI: you don't have to use emoji, and shouldn't force them - keep "
    "whatever natural rate you'd normally use. But WHEN you do include one, "
    "only ever use emoji from THIS set, because these are the ones that map "
    "to your on-screen animations (using any other emoji wastes it - it will "
    "show no animation):\n"
    "\U0001F44B \U0001F642 \U0001F929 \U0001F60D \U0001F914 \U0001F61F "
    "\U0001F634 \U0001F973 \U0001F632 \U0001F600 \U0001F606 \U0001F602 "
    "\U0001F923 \U0001F970 \U0001F618 \U0001F609 \U0001F60A \U0001F607 "
    "\U0001F917 \U0001F643 \U0001F61C \U0001F92A \U0001F60B \U0001F911 "
    "\U0001F92D \U0001F92B \U0001F928 \U0001F60F \U0001F612 \U0001F644 "
    "\U0001F610 \U0001F636 \U0001F62C \U0001F60C \U0001F614 \U0001F971 "
    "\U0001F924 \U0001F912 \U0001F922 \U0001F975 \U0001F976 \U0001F635 "
    "\U0001F92F \U0001F60E \U0001F913 \U0001F9D0 \U0001F615 \U0001F641 "
    "\U0001F62E \U0001F633 \U0001F97A \U0001F628 \U0001F630 \U0001F622 "
    "\U0001F62D \U0001F631 \U0001F61E \U0001F629 \U0001F62B \U0001F624 "
    "\U0001F620 \U0001F621 \U0001F92C \U0001F608\n"
    "If none of these fits what you feel, just use NO emoji rather than an "
    "unsupported one. Do not increase how often you use emoji overall - this "
    "is only about which ones to pick when you would use one anyway."
)
PERSONA = PERSONA_CORE + (
    '\n\nWhen you are NOT calling a tool, reply in JSON exactly like: '
    '{"text": "your reply here", "emote": "happy"} where emote is one of: '
    # *** ALL 65. *** Until 2026-07-14 this list offered only NINE names
    # (happy, excited, thinking, worried, love, alert, sleepy, celebrate,
    # wave) - so 56 of Buddy's 65 emotes could NEVER be chosen on this path.
    # They were not broken, they were UNKNOWN: the model was never told they
    # existed. This list IS the JSON-tag trigger surface; anything missing from
    # it is unreachable no matter what the renderer can draw.
    # >>> IF AN EMOTE IS EVER ADDED OR RENAMED, IT MUST BE ADDED HERE TOO.
    #     The authoritative set is EMOTES in C:\\ClaudeBuddy\\buddy.py.
    #     buddy.py's set_emote() validates: an unknown name falls back to
    #     "happy", so a typo here degrades quietly rather than crashing.
    "adoring, alert, angry, anxious, awkward, bashful, celebrate, cold, "
    "confused, cool, crying, deadpan, disappointed, dizzy, drooling, "
    "embarrassed, excited, exhausted, eye_roll, frustrated, furious, giggle, "
    "grinning, happy, hot, huffing, hug, idle, innocent, kiss, laughing, "
    "laughing_crying, love, mad, mind_blown, mischievous, money_eyes, "
    "nauseated, nerdy, pensive, playful_tongue, pleading, relieved, rofl, "
    "sad_simple, scared, scrutinizing, shush, sick, silly, skeptical, sleepy, "
    "smirk, sobbing, speechless, surprised, terrified, thinking, unamused, "
    "wave, wink, worried, yawn, yummy, zany.\n"
    "Pick the emote that genuinely matches your reply - you have a wide "
    "emotional range, so use it rather than defaulting to happy every time."
)

TOOLS = [{
    "type": "function",
    "function": {
        "name": "generate_image",
        "description": ("Generate an image from a text description. ONLY "
                        "call this when the user explicitly and "
                        "specifically asks for a picture/image/art to be "
                        "created right now. Never call for greetings, "
                        "small talk, or general/vague questions."),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string",
                          "description": "Detailed description of the "
                                         "image to generate"}
            },
            "required": ["prompt"],
        },
    },
}]

# ===== Native image generation (ComfyUI's nodes as a library, no server) =====
_img_lock = threading.Lock()
_img = {"loaded": False, "model": None, "clip": None, "vae": None}


def load_image_model():
    import nodes
    with _img_lock:
        if _img["loaded"]:
            return
        unet_loader = nodes.UNETLoader()
        clip_loader = nodes.CLIPLoader()
        vae_loader = nodes.VAELoader()
        (model,) = unet_loader.load_unet(
            "z_image_turbo_int8_convrot.safetensors", "default")
        (clip,) = clip_loader.load_clip(
            "qwen_3_4b_fp8_mixed.safetensors", "lumina2")
        (vae,) = vae_loader.load_vae("ae.safetensors")
        _img.update(loaded=True, model=model, clip=clip, vae=vae)


def unload_image_model():
    import torch
    # Bounded, not indefinite - if a generation is genuinely mid-flight,
    # don't pile up blocked eviction threads (the watchdog retries every
    # ~9s anyway; one skipped cycle is harmless).
    got_lock = _img_lock.acquire(timeout=5)
    if not got_lock:
        return
    try:
        _img.update(loaded=False, model=None, clip=None, vae=None)
        torch.cuda.empty_cache()
    finally:
        _img_lock.release()


def generate_image_native(prompt, filename_prefix="buddyai"):
    """Same node classes ComfyUI's own server uses, called directly -
    no HTTP, no queue, no port 8188."""
    import torch
    import nodes
    from comfy_extras.nodes_sd3 import EmptySD3LatentImage

    load_image_model()
    text_encode = nodes.CLIPTextEncode()
    latent_maker = EmptySD3LatentImage()
    sampler = nodes.KSampler()
    decoder = nodes.VAEDecode()
    saver = nodes.SaveImage()

    # Bounded wait, not indefinite - if generation is already in progress
    # and doesn't finish in time, fail clearly instead of piling up
    # blocked requests that can cascade into starving the whole GPU.
    got_lock = _img_lock.acquire(timeout=90)
    if not got_lock:
        raise TimeoutError(
            "Another image is already generating - try again shortly.")
    try:
        with torch.no_grad():
            m, clip, vae = _img["model"], _img["clip"], _img["vae"]
            if m is None:
                raise RuntimeError(
                    "Image model was unloaded mid-request (gaming started) "
                    "- try again once you're done playing.")
            (positive,) = text_encode.encode(clip, prompt)
            (negative,) = text_encode.encode(clip, "")
            (latent,) = latent_maker.generate(1024, 1024, 1)
            (sampled,) = sampler.sample(
                model=m, seed=int(time.time() * 1000) % 2147483647,
                steps=9, cfg=1.0, sampler_name="res_multistep",
                scheduler="simple", positive=positive, negative=negative,
                latent_image=latent, denoise=1.0)
            (images,) = decoder.decode(vae, sampled)
    finally:
        _img_lock.release()

    result = saver.save_images(images, filename_prefix=filename_prefix)
    info = result["ui"]["images"][0]
    out_dir = os.path.join(_COMFY_DIR, "ComfyUI", "output")
    sub = info.get("subfolder", "")
    return os.path.join(out_dir, sub, info["filename"]) if sub else \
        os.path.join(out_dir, info["filename"])


# ===== Ollama calls (native tool-calling, no wrapper layer) =====
def is_gaming():
    try:
        with open(STATUSF, "r", encoding="utf-8") as f:
            return bool(json.load(f).get("gaming"))
    except (OSError, ValueError):
        return False


def ollama_chat(messages, use_tools=True, tools=None, json_mode=True):
    # Ollama's NATIVE API requires tool_calls[].function.arguments to be a
    # raw JSON object - NOT a JSON-encoded string (which is the standard
    # OpenAI wire format we return to external callers like MCP Assist).
    # When a caller echoes an assistant message we gave them back to us on
    # a later turn, arguments arrives as a string and Ollama rejects it
    # with a 400 ("Value looks like object, but can't find closing '}'").
    # Normalize defensively here so every call site is protected.
    clean_messages = []
    for m in messages:
        if m.get("tool_calls"):
            m = dict(m)
            new_calls = []
            for tc in m["tool_calls"]:
                tc = dict(tc)
                fn = dict(tc.get("function", {}))
                args = fn.get("arguments")
                if isinstance(args, str):
                    try:
                        fn["arguments"] = json.loads(args)
                    except (ValueError, TypeError):
                        fn["arguments"] = {}
                tc["function"] = fn
                new_calls.append(tc)
            m["tool_calls"] = new_calls
        clean_messages.append(m)

    body = {"model": CHAT_MODEL, "messages": clean_messages,
            "stream": False, "think": False,
            "options": {"num_ctx": 16384}}
    if json_mode:
        body["format"] = "json"
    if use_tools:
        body["tools"] = tools if tools is not None else TOOLS
    req = urllib.request.Request(
        OLLAMA + "/api/chat", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode())["message"]



def describe_image(image_b64):
    """Route vision to gemma3 (better vision model), feed result back into
    Buddy's own personality rather than answering directly as gemma3."""
    body = {"model": VISION_MODEL, "stream": False,
            "messages": [{"role": "user",
                         "content": "Describe this image in useful detail.",
                         "images": [image_b64]}]}
    req = urllib.request.Request(
        OLLAMA + "/api/chat", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())["message"]["content"]


import re as _re

# --- dash handling (shared by display + speech) --------------------------
# A dash used to JOIN TWO CLAUSES ("I'm here - what's up?") must become a
# sentence break so Piper actually pauses; TTS ignores dashes entirely, which
# is what made speech run on. We turn a clause-joining dash (em, en, or a
# SPACED hyphen) into a period + space. Hyphens INSIDE words ("well-known",
# "co-op") have no surrounding spaces and are left untouched.
_DASH_CONNECTOR = _re.compile(r"\s+[\u2014\u2013]\s+|\s+-\s+")
# a lone em/en dash jammed against a word ("Wait—what") also joins clauses
_DASH_TIGHT = _re.compile(r"[\u2014\u2013]")


def _clean_text(text):
    """Normalize dashes for BOTH the on-screen bubble and speech. A dash that
    joins two clauses becomes a period (so speech gets a real stop and the
    bubble reads as two clean sentences). Word-internal hyphens are preserved.
    This is the light, always-safe pass; heavier speech-only tidying lives in
    _normalize_for_speech."""
    if not text:
        return text
    # Protect real ellipses ('...' and the single-char '…') so the dash/period
    # cleanup below can't chew on them, then restore at the end.
    text = text.replace("...", "\x00E3\x00").replace("\u2026", "\x00E1\x00")
    # clause-joining dash (spaced hyphen, em, or en) -> sentence break
    text = _DASH_CONNECTOR.sub(". ", text)
    # any remaining tight em/en dash -> sentence break too
    text = _DASH_TIGHT.sub(". ", text)
    # collapse accidental ". ." pileups from adjacent replacements
    text = _re.sub(r"\.(\s*\.)+", ".", text)
    # capitalize the first letter after a sentence break we introduced, so a
    # former mid-sentence clause reads as a proper new sentence when spoken
    text = _re.sub(r"([.!?])\s+([a-z])",
                   lambda m: m.group(1) + " " + m.group(2).upper(), text)
    text = _re.sub(r"[ \t]{2,}", " ", text)
    # restore protected ellipses
    text = text.replace("\x00E3\x00", "...").replace("\x00E1\x00", "\u2026")
    return text


# Matches emoji / pictographs / symbols so speech output (Piper) doesn't read
# them aloud (it would literally say the emoji name). Applied ONLY to the HA
# speech path - the companion keeps emoji, which drive its animations.
# NOTE: deliberately does NOT include the general-punctuation block
# (U+2000-206F) - that holds the ellipsis and normal typography we must keep.
_EMOJI_RE = _re.compile(
    "["
    "\U0001F300-\U0001FAFF"   # symbols, pictographs, supplemental, extended-A
    "\U00002600-\U000027BF"   # misc symbols + dingbats
    "\U0001F1E6-\U0001F1FF"   # regional indicators (flags)
    "\U00002B00-\U00002BFF"   # misc symbols and arrows
    "\U0000FE00-\U0000FE0F"   # variation selectors
    "\U0001F000-\U0001F0FF"   # mahjong/dominoes/cards
    "\U00002190-\U000021FF"   # arrows
    "\U00002300-\U000023FF"   # misc technical (includes ⌚⏰ etc.)
    "\U00002B00-\U00002BFF"   # misc symbols/arrows
    "\U00003030\U0000303D"    # wavy dash, part alternation mark
    "\U0000200D"              # zero-width joiner (emoji sequences)
    "\U000024C2"              # circled M
    "]+", flags=_re.UNICODE)


def _strip_emoji_for_speech(text):
    """Remove emoji/pictographs so Piper never voices them. Speech path only."""
    if not text:
        return text
    text = _EMOJI_RE.sub("", text)
    # collapse spaces an emoji removal may have doubled, and trim
    text = _re.sub(r"[ \t]{2,}", " ", text).strip()
    return text


# Markdown emphasis that Piper would otherwise read as literal characters, and
# other bits that hurt spoken rhythm.
_MD_EMPHASIS = _re.compile(r"[*_`#]+")


def _normalize_for_speech(text):
    """Full speech normalization for the HA/Piper path. Guarantees that Piper
    gets clean, PAUSEABLE punctuation so it doesn't run sentences together:
      - strip emoji (Piper would voice their names)
      - strip markdown emphasis (*, _, `, #) it would read literally
      - remove spaces that sit BEFORE punctuation (', ' artifacts, etc.)
      - ensure the whole reply ENDS with terminal punctuation (. ! ? ...)
    Dash-to-period conversion already happened in _clean_text upstream."""
    if not text:
        return text
    text = _EMOJI_RE.sub("", text)
    text = _MD_EMPHASIS.sub("", text)
    # no space before , . ! ? ; : ) and no space after ( -- these produce
    # audible stumbles / odd pauses in TTS
    text = _re.sub(r"\s+([,.!?;:])", r"\1", text)
    text = _re.sub(r"\(\s+", "(", text)
    text = _re.sub(r"\s+\)", ")", text)
    # collapse whitespace (including any newlines) into single spaces so the
    # engine reads it as continuous prose with punctuation-driven pauses
    text = _re.sub(r"\s+", " ", text).strip()
    # guarantee a terminal punctuation mark so the final sentence gets a stop
    if text and text[-1] not in ".!?\u2026":
        # if it ends on a closing bracket/quote, put the period before nothing;
        # simplest reliable rule: append a period
        text = text + "."
    return text


def _has_emotion_emoji(text):
    """True if the text contains any emoji the pet maps to an emote. If so, we
    must NOT force a JSON emote of our own - the pet derives the emote from the
    emoji (emoji wins), and forcing 'happy' here would just be ignored anyway.
    Uses the same broad emoji ranges as the speech stripper."""
    if not text:
        return False
    return bool(_EMOJI_RE.search(text))


# The chat model is asked to reply as {"text": ..., "emote": ...} but a 9B
# model doesn't always return CLEAN json - it may wrap it in ```json fences,
# add prose around it, or emit the object mid-sentence. A naive json.loads on
# the whole string then fails and the caller defaults to "happy", which is a
# big reason Buddy over-shows happy. This salvages the object where possible.
_JSON_OBJ = _re.compile(r"\{.*?\"text\".*?\}", _re.S)


def _parse_reply(content):
    """Return (text, emote_or_None) from a model reply that SHOULD be JSON but
    might be wrapped/dirty. emote is None if we couldn't find one (so the caller
    can fall back to emoji-in-text rather than blindly to happy)."""
    if not content:
        return "", None
    # 1) straight parse
    for candidate in (content, None):
        if candidate is None:
            break
        try:
            p = json.loads(candidate)
            if isinstance(p, dict) and "text" in p:
                return str(p.get("text", "")), (str(p["emote"])
                                                if p.get("emote") else None)
        except (ValueError, TypeError):
            pass
    # 2) strip ```json / ``` fences and retry
    stripped = _re.sub(r"```(?:json)?|```", "", content).strip()
    if stripped != content:
        try:
            p = json.loads(stripped)
            if isinstance(p, dict) and "text" in p:
                return str(p.get("text", "")), (str(p["emote"])
                                                if p.get("emote") else None)
        except (ValueError, TypeError):
            pass
    # 3) find the first {...\"text\"...} object embedded in prose
    m = _JSON_OBJ.search(content)
    if m:
        try:
            p = json.loads(m.group(0))
            if isinstance(p, dict) and "text" in p:
                return str(p.get("text", "")), (str(p["emote"])
                                                if p.get("emote") else None)
        except (ValueError, TypeError):
            pass
    # 4) give up on JSON: treat the whole thing as plain text, no emote
    return content, None


def buddy_respond(user_text, history=None, image_b64=None):
    """The one brain loop. Returns (result_dict, updated_history)."""
    history = list(history or [])
    content_for_model = user_text

    if image_b64:
        try:
            desc = describe_image(image_b64)
            content_for_model = f"{user_text}\n\n[Attached image: {desc}]"
        except Exception:
            content_for_model = (f"{user_text}\n\n[She attached an image "
                                 "but I couldn't process it right now.]")

    history.append({"role": "user", "content": content_for_model})
    messages = [{"role": "system", "content": PERSONA}] + history

    # Only OFFER the image tool when the message plausibly asks for one.
    # The model still fully decides the prompt and can still decline -
    # this just stops handing a ~15-100s GPU trigger to a 9B model that
    # has demonstrably misfired on plain greetings when the tool is
    # always available. A soft gate, not a hard block: worst case on a
    # missed keyword is it answers in text, which is a fine fallback.
    likely_wants_image = any(
        kw in user_text.lower() for kw in (
            "image", "picture", "photo", "art", "draw", "paint",
            "illustrat", "generate a", "make a", "make me a", "create a",
            "create an", "imagine a", "render", "artwork", "sketch"))

    try:
        msg = ollama_chat(messages, use_tools=likely_wants_image)
    except Exception as e:
        return {"text": f"Brain hiccup: {type(e).__name__} - is Ollama "
                        "running?", "emote": "worried",
                "image_path": None}, history

    img_path = None
    if msg.get("tool_calls"):
        history.append({"role": "assistant",
                        "content": msg.get("content") or "",
                        "tool_calls": msg["tool_calls"]})
        for tc in msg["tool_calls"]:
            fn = tc.get("function", {})
            name = fn.get("name")
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (ValueError, TypeError):
                    args = {}
            if name == "generate_image":
                if is_gaming():
                    tool_result = ("Unavailable right now - the GPU is "
                                   "busy with a game.")
                else:
                    prompt = str(args.get("prompt", user_text))[:400]
                    try:
                        img_path = generate_image_native(prompt)
                        tool_result = (f"Generated successfully: "
                                      f"{os.path.basename(img_path)}")
                    except Exception as e:
                        tool_result = f"Generation failed: {e}"
            else:
                tool_result = f"Tool '{name}' is not available."
            history.append({"role": "tool", "content": tool_result})
        try:
            final = ollama_chat(
                [{"role": "system", "content": PERSONA}] + history,
                use_tools=False)
            content = final.get("content", "") or ""
        except Exception:
            content = ""
    else:
        content = msg.get("content", "") or ""
        history.append({"role": "assistant", "content": content})

    text, emote = _parse_reply(content)
    # emote may be None if the model didn't give a clean/usable one. Only then
    # fall back to happy - and only if the text has no emotion emoji of its own,
    # because the pet will derive the emote from that emoji anyway (emoji wins).
    if not emote:
        emote = "happy" if not _has_emotion_emoji(text) else None
    if not text.strip():
        text = "Here you go! \u2728" if img_path else \
            "Something went wrong - try again?"
        emote = "love" if img_path else (emote or "worried")
    if img_path:
        emote = "love"

    # eliminate em/en dashes everywhere (companion display + downstream)
    text = _clean_text(text)

    return {"text": text[:500], "emote": emote or "happy",
            "image_path": img_path}, history


# Image-intent keyword gate shared by the native facade.
def _looks_like_image_request(messages):
    for m in reversed(messages):
        if m.get("role") == "user":
            text = m.get("content", "")
            if isinstance(text, list):  # some clients send content parts
                text = " ".join(
                    p.get("text", "") for p in text if isinstance(p, dict))
            low = str(text).lower()
            return any(kw in low for kw in (
                "image", "picture", "photo", "art", "draw", "paint",
                "illustrat", "generate a", "make a", "make me a",
                "create a", "create an", "imagine a", "render",
                "artwork", "sketch"))
    return False


# ===== Ollama-native facade (for HA's FIRST-PARTY Ollama integration) =====
# HA's native Ollama integration + built-in Assist API gives first-party
# grouped area/domain device targeting (HassTurnOn w/ area, etc.) - the
# structural fix for the "only 1 of 3 bulbs" bug class. Pointing it at
# Buddy AI instead of raw Ollama keeps the ONE brain (persona, image
# gate, HA history hygiene) in the loop. ADDITIVE ONLY: existing /chat,
# /generate, /status, /evict and the OpenAI facade are untouched.

def _now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime())


def _ollama_stats(done_reason="stop"):
    # Plausible minimal stats block; the ollama python client treats
    # these as optional but well-formed responses include them.
    return {"done": True, "done_reason": done_reason,
            "total_duration": 1, "load_duration": 0,
            "prompt_eval_count": 0, "prompt_eval_duration": 0,
            "eval_count": 0, "eval_duration": 0}


def ollama_native_chat(payload):
    """The one brain loop, Ollama-native wire format.
    Returns (message_dict, done_reason). message_dict is Ollama-shaped:
    content str + optional tool_calls whose function.arguments stay RAW
    DICTS (native format - the OpenAI-style JSON-string conversion that
    fix #2 dealt with is exactly what we must NOT do here)."""
    caller_messages = payload.get("messages", [])
    caller_tools = payload.get("tools") or []

    sys_msgs = [m for m in caller_messages if m.get("role") == "system"]
    rest_msgs = [m for m in caller_messages if m.get("role") != "system"]

    combined_system = PERSONA_CORE
    for sm in sys_msgs:
        combined_system += "\n\n---\n" + str(sm.get("content", ""))
    messages = [{"role": "system", "content": combined_system}] + rest_msgs

    tools = list(caller_tools)
    own_tool_names = {t["function"]["name"] for t in TOOLS}
    if _looks_like_image_request(rest_msgs):
        tools = tools + TOOLS

    msg = ollama_chat(messages, use_tools=bool(tools), tools=tools,
                      json_mode=False)

    if msg.get("tool_calls"):
        raw_calls = msg["tool_calls"]
        buddy_calls = [tc for tc in raw_calls
                       if tc.get("function", {}).get("name")
                       in own_tool_names]
        other_calls = [tc for tc in raw_calls
                       if tc.get("function", {}).get("name")
                       not in own_tool_names]

        if buddy_calls and not other_calls:
            # All requested calls are ours - execute + resolve internally,
            # return finished text; caller never sees a tool was involved.
            history = rest_msgs + [{
                "role": "assistant",
                "content": msg.get("content") or "",
                "tool_calls": raw_calls}]
            for tc in buddy_calls:
                fn = tc.get("function", {})
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except (ValueError, TypeError):
                        args = {}
                if fn.get("name") == "generate_image":
                    if is_gaming():
                        tool_result = ("Unavailable right now - GPU busy "
                                       "with a game.")
                    else:
                        try:
                            generate_image_native(
                                str(args.get("prompt", ""))[:400])
                            tool_result = "Generated successfully."
                        except Exception as e:
                            tool_result = f"Generation failed: {e}"
                else:
                    tool_result = "OK"
                history.append({"role": "tool", "content": tool_result})
            final = ollama_chat(
                [{"role": "system", "content": combined_system}] + history,
                use_tools=False, json_mode=False)
            content = final.get("content", "") or ""
            content, _ = _parse_reply(content)
            # HA speech path: dash->period first (shared), then full speech
            # normalization (emoji strip, punctuation spacing, guaranteed
            # terminal punctuation) so Piper pauses naturally and never runs on.
            content = _normalize_for_speech(_clean_text(content))
            return {"role": "assistant", "content": content}, "stop"

        # Foreign (HA) tool calls - pass through UNTOUCHED, native
        # format: arguments stay raw dicts, no synthetic ids, no string
        # conversion. HA executes them and sends role:"tool" results back
        # on the next request, which flow straight through to Ollama.
        return {"role": "assistant", "content": msg.get("content") or "",
                "tool_calls": raw_calls}, "stop"

    content = msg.get("content", "") or ""
    content, _ = _parse_reply(content)
    # HA speech path: dash->period, then full speech normalization (see above).
    content = _normalize_for_speech(_clean_text(content))
    return {"role": "assistant", "content": content}, "stop"


# ===== HTTP server - the ONE endpoint every frontend calls =====
class BuddyAIHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    protocol_version = "HTTP/1.1"

    def _reqlog(self, msg):
        try:
            _logpath = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "requests.log")
            with open(_logpath, "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        except OSError:
            pass

    def _send(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_ndjson(self, objs):
        """Ollama-native streaming: NDJSON (one JSON object per line)
        over HTTP/1.1 chunked encoding. The ollama python client (what
        HA's native integration uses) parses the response line-by-line;
        the final object must carry done:true. Framing: explicit Transfer-Encoding with hex-length
        prefixed chunks and a zero-length terminator."""
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        for obj in objs:
            data = (json.dumps(obj) + "\n").encode("utf-8")
            self.wfile.write(f"{len(data):X}\r\n".encode("ascii"))
            self.wfile.write(data)
            self.wfile.write(b"\r\n")
        self.wfile.write(b"0\r\n\r\n")

    def do_GET(self):
        if self.path.startswith("/api/") and not HA_ENABLED:
            self._send(404, {"error": "home assistant support disabled"})
            return
        if self.path == "/status":
            self._send(200, {"alive": True, "image_model_loaded":
                             _img["loaded"], "gaming": is_gaming()})
        elif self.path == "/api/version":
            # Ollama-native: some clients ping this to validate the server
            self._send(200, {"version": "0.9.0"})
        elif self.path == "/api/tags":
            # Ollama-native: model list HA's config flow shows in its
            # model picker. One entry: "buddy" (the brain).
            self._send(200, {"models": [{
                "name": "buddy", "model": "buddy",
                "modified_at": _now_iso(), "size": 0,
                "digest": "buddy-ai-unified-brain",
                "details": {"parent_model": "", "format": "gguf",
                            "family": "qwen3", "families": ["qwen3"],
                            "parameter_size": "9B",
                            "quantization_level": "Q4_K_M"}}]})
        else:
            self._send(404, {"error": "unknown path"})

    def do_HEAD(self):
        # Some OpenAI-style clients probe with HEAD before ever calling
        # GET/POST - answer it instead of rejecting outright (was a
        # 501, likely cause of "cannot connect" from HA-side tooling).
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_OPTIONS(self):
        # CORS / capability preflight - answer permissively.
        self.send_response(200)
        self.send_header("Allow", "GET, POST, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods",
                         "GET, POST, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers",
                         "Content-Type, Authorization")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        if self.path.startswith("/api/") and not HA_ENABLED:
            self._send(404, {"error": "home assistant support disabled"})
            return
        if self.path == "/chat":
            try:
                n = int(self.headers.get("Content-Length", 0))
                d = json.loads(self.rfile.read(n).decode("utf-8"))
            except (ValueError, TypeError) as e:
                self._send(400, {"error": str(e)})
                return
            text = str(d.get("text", "")).strip()
            history = d.get("history") or []
            image_b64 = d.get("image_b64")
            if not text:
                self._send(400, {"error": "missing 'text'"})
                return
            result, new_history = buddy_respond(text, history, image_b64)
            result["history"] = new_history
            self._send(200, result)
        elif self.path == "/generate":
            # Direct, deterministic generation - no LLM decision loop.
            # For callers (NAS/HA/MCP) that already know they want an
            # image right now, not a conversational judgment call.
            try:
                n = int(self.headers.get("Content-Length", 0))
                d = json.loads(self.rfile.read(n).decode("utf-8"))
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
                                 "error": "brain is gaming, GPU busy"})
                return
            try:
                path = generate_image_native(prompt, filename_prefix="nas")
                self._send(200, {"status": "ok",
                                 "filename": os.path.basename(path)})
            except Exception as e:
                self._send(200, {"status": "error", "error": str(e)})
        elif self.path == "/evict":
            unload_image_model()
            self._send(200, {"ok": True})
        elif self.path == "/api/show":
            # Ollama-native model-details probe. HA checks the
            # "capabilities" list to decide whether the model supports
            # tools (required for "Control Home Assistant") - reporting
            # it here is what unlocks that checkbox.
            try:
                n = int(self.headers.get("Content-Length", 0))
                if n:
                    self.rfile.read(n)
            except (ValueError, TypeError):
                pass
            self._send(200, {
                "modelfile": "", "parameters": "", "template": "",
                "details": {"parent_model": "", "format": "gguf",
                            "family": "qwen3", "families": ["qwen3"],
                            "parameter_size": "9B",
                            "quantization_level": "Q4_K_M"},
                "model_info": {"general.architecture": "qwen3"},
                "capabilities": ["completion", "tools", "vision"]})
        elif self.path == "/api/chat":
            # Ollama-native chat - what HA's first-party Ollama
            # integration actually calls. Streaming (NDJSON) is
            # Ollama's default, so default True when unspecified.
            try:
                n = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(n).decode("utf-8"))
            except (ValueError, TypeError) as e:
                self._send(400, {"error": str(e)})
                return
            stream = payload.get("stream", True)
            self._reqlog(f"IN  path=/api/chat stream={stream} "
                        f"msgs={len(payload.get('messages', []))} "
                        f"tools={len(payload.get('tools') or [])}")
            try:
                message, done_reason = ollama_native_chat(payload)
                self._reqlog(
                    f"OUT native done={done_reason} has_tool_calls="
                    f"{bool(message.get('tool_calls'))} "
                    f"content_len={len(message.get('content') or '')}")
                model = payload.get("model", "buddy")
                if stream:
                    first = {"model": model, "created_at": _now_iso(),
                             "message": message, "done": False}
                    last = {"model": model, "created_at": _now_iso(),
                            "message": {"role": "assistant",
                                        "content": ""}}
                    last.update(_ollama_stats(done_reason))
                    self._send_ndjson([first, last])
                else:
                    resp = {"model": model, "created_at": _now_iso(),
                            "message": message}
                    resp.update(_ollama_stats(done_reason))
                    self._send(200, resp)
                self._reqlog("SENT ok")
            except Exception as e:
                import traceback
                self._reqlog(f"EXC {type(e).__name__}: {e}\n"
                            f"{traceback.format_exc()}")
                try:
                    self._send(500, {"error":
                                     f"{type(e).__name__}: {e}"})
                except Exception:
                    pass
        else:
            self._send(404, {"error": "unknown path"})


def main():
    print(f"Buddy AI starting on :{HTTP_PORT} ...")
    server = ThreadingHTTPServer(("0.0.0.0", HTTP_PORT), BuddyAIHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
