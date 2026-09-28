#!/usr/bin/env python3
"""
AI chat-robot emotion animations - Lottie JSON generator.

Style references:
  * xAI Grok bot        - circular black-hole mark, monochrome white on
                          near-black, orbital swoosh ring
  * Emotion Ball (情绪球) / grok-ball - ball-bodied AI emotion engine:
                          breathing squash-stretch body, gaze micro-drift,
                          emotionId taxonomy (00 lifecycle / 10 emotions /
                          30 agent states), enter transition sequences
  * Vector / Emo / Jibo - glossy squircle eye language

Every emotion has the SAME FORM:
  * same 160x160 canvas, same ball body, same eye/mouth anchor points
  * same orbiting swoosh ring (speed scales with emotion energy)
  * same playback segments (for elastic switching):
      frames 0..14    ENTER  - uniform squash & pop-in transition
                               (plays automatically when firmware swaps files)
      frames 15..op-1 LOOP   - seamless emotion loop
  * same layer stack: overlay layers (dots/tear/confetti/...) first, then
    the single "face" layer (features first, ball plate last - lottie
    paint order is first-on-top).

Renderer constraints (ThorVG 0.15.3 via LVGL lv_lottie, drawn at 160x160):
  shape layers only, solid/gradient fills, round-cap strokes, keyframed
  transforms. NO expressions, images, text, masks/mattes/trim paths.
"""

import json
import math
import os

W = H = 160
CX = CY = 80.0   # face center
FPS = 30
ENTRY = 15       # enter-transition length in frames (uniform)

# ------------------------------------------------------------------ themes --
# dark:  white ink on a near-black disc (default; matches the chat page)
# light: dark ink on a white disc
THEMES = ("dark", "light")

_THEME_PALETTES = {
    "dark": dict(plate_top="191A21", plate_bot="060608", plate_rim="2C2D34",
                 mono="F5F5F5", dim="C9CBD4", dimmer="9B9DA8",
                 blush="FFFFFF", tear="D8D8DE", gloss_op=6, cheek_op=20),
    "light": dict(plate_top="FFFFFF", plate_bot="E2E5EE", plate_rim="C5CBD9",
                  mono="1C2029", dim="454B59", dimmer="7A8095",
                  blush="1C2029", tear="4E5668", gloss_op=10, cheek_op=14),
}


def set_theme(theme):
    """assign the module palette for the given theme (builders read the
    globals at generation time)."""
    global PLATE_TOP, PLATE_BOT, PLATE_RIM, MONO
    global C_IDLE, C_LISTEN, C_THINK, C_SPEAK, C_ERROR, C_CONN, C_HAPPY
    global C_LOVE, C_SAD, C_ANGRY, C_CONFUSE, C_SLEEP
    global C_BLUSH, C_TEAR, C_GLOSS, GLOSS_OP, CHEEK_OP
    p = _THEME_PALETTES[theme]
    PLATE_TOP = p["plate_top"]
    PLATE_BOT = p["plate_bot"]
    PLATE_RIM = p["plate_rim"]
    MONO = p["mono"]
    C_IDLE = C_LISTEN = C_THINK = C_SPEAK = C_ERROR = C_CONN = MONO
    C_HAPPY = C_LOVE = C_ANGRY = C_CONFUSE = MONO
    C_SAD = p["dim"]        # slightly dimmed
    C_SLEEP = p["dimmer"]   # night-mode feel
    C_BLUSH = p["blush"]
    C_TEAR = p["tear"]
    C_GLOSS = "FFFFFF"
    GLOSS_OP = p["gloss_op"]
    CHEEK_OP = p["cheek_op"]

EYE_L = (-26.0, -6.0)   # relative to face center (80, 80)
EYE_R = (26.0, -6.0)
MOUTH = (0.0, 26.0)


def rgb(h):
    return [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)] + [1.0]


# ------------------------------------------------------------ keyframe util --
E_IO  = ({"x": [0.42], "y": [0.0]},  {"x": [0.58], "y": [1.0]})  # ease-in-out
E_OUT = ({"x": [0.0],  "y": [0.0]},  {"x": [0.33], "y": [1.0]})  # ease-out
E_IN  = ({"x": [0.67], "y": [0.0]},  {"x": [1.0],  "y": [1.0]})  # ease-in
E_LIN = ({"x": [0.33], "y": [0.0]},  {"x": [0.67], "y": [1.0]})  # ~linear


def static(v):
    return {"a": 0, "k": v}


def anim(keys, dim=1, ease=E_IO):
    """keys: sorted list of (frame, value); value scalar -> [v], else list."""
    out = []
    for i, (t, v) in enumerate(keys):
        sv = v if isinstance(v, list) else [v]
        k = {"t": t, "s": sv}
        if i < len(keys) - 1:
            nv = keys[i + 1][1]
            k["e"] = nv if isinstance(nv, list) else [nv]
            ei, eo = ease
            k["i"] = {"x": ei["x"] * dim, "y": ei["y"] * dim}
            k["o"] = {"x": eo["x"] * dim, "y": eo["y"] * dim}
        out.append(k)
    return {"a": 1, "k": out}


def shifted(keys, dt=ENTRY):
    return [(t + dt, v) for (t, v) in keys]


# ------------------------------------------------------- enter transition --
# uniform elastic pop-in, composed with each emotion's loop keys
def face_s(loop=None):
    keys = [(0, [72, 72, 100]), (8, [106, 106, 100]), (12, [97, 97, 100]),
            (14, [100, 100, 100])]
    return anim(keys + shifted(loop or []), 3)


def face_p(loop=None):
    keys = [(0, [80, 86, 0]), (8, [80, 77, 0]), (14, [80, 80, 0])]
    return anim(keys + shifted(loop or []), 3)


def face_r(loop=None):
    return anim(shifted(loop or [(0, 0)]))


def eye_s(loop=None):
    """eyes grow in with overshoot, then run the loop keys."""
    keys = [(0, [60, 60]), (7, [108, 108]), (11, [96, 96]), (14, [100, 100])]
    return anim(keys + shifted(loop or []), 2)


def mouth_s(loop=None):
    """mouth pops in slightly after the eyes (staggered, like reaction
    emoji)."""
    keys = [(0, [20, 20]), (3, [20, 20]), (9, [112, 112]), (13, [98, 98]),
            (14, [100, 100])]
    return anim(keys + shifted(loop or []), 2)


def blinks(op, times):
    """loop-section scale-y blink keys (frames are loop-relative; caller
    shifts). op = full loop length incl. ENTRY."""
    keys = [(0, [100, 100])]
    for t0, t1 in times:
        keys.append((t0, [100, 100]))
        keys.append(((t0 + t1) / 2, [100, 8]))
        keys.append((t1, [100, 100]))
    if keys[-1][0] < op:
        keys.append((op, [100, 100]))
    return keys


# ------------------------------------------------------------------- shapes --
def fill(color, op=100):
    return {"ty": "fl", "c": static(rgb(color)), "o": static(op), "r": 1, "bm": 0}


def gfill(c0, c1, p0, p1, op=100):
    """linear gradient fill c0 (at p0) -> c1 (at p1)."""
    return {"ty": "gf", "s": static(list(p0)), "e": static(list(p1)),
            "g": {"p": 2, "k": static([0] + rgb(c0)[:3] + [1] + rgb(c1)[:3])},
            "t": 1, "o": static(op), "r": 1, "bm": 0}


def stroke(color, w, op=100):
    return {"ty": "st", "c": static(rgb(color)), "o": static(op),
            "w": static(w), "lc": 2, "lj": 2, "ml": 4, "bm": 0}


def ellipse(cx, cy, w, h):
    return {"ty": "el", "d": 1, "p": static([cx, cy]), "s": static([w, h])}


def rrect(cx, cy, w, h, r):
    return {"ty": "rc", "d": 1, "p": static([cx, cy]), "s": static([w, h]),
            "r": static(r)}


def path(verts, v_in, v_out, closed=False):
    return {"ty": "sh", "ks": static(
        {"i": v_in, "o": v_out, "v": verts, "c": closed})}


def arc(x0, y0, x1, y1, bulge):
    """quadratic arc through the midpoint displaced by bulge (+y = downward),
    expressed as a two-vertex cubic."""
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    cx, cy = mx, my + 2 * bulge
    c1 = [x0 + 2.0 / 3 * (cx - x0), y0 + 2.0 / 3 * (cy - y0)]
    c2 = [x1 + 2.0 / 3 * (cx - x1), y1 + 2.0 / 3 * (cy - y1)]
    return path([[x0, y0], [x1, y1]],
                [[0, 0], [c2[0] - x1, c2[1] - y1]],
                [[c1[0] - x0, c1[1] - y0], [0, 0]])


def smooth_path(pts, closed=False, k=0.18):
    """auto-smoothed polyline (Catmull-Rom-ish tangents)."""
    n = len(pts)
    v_in, v_out = [], []
    for i in range(n):
        p0 = pts[max(i - 1, 0)]
        p1 = pts[min(i + 1, n - 1)]
        tx, ty = (p1[0] - p0[0]) * k, (p1[1] - p0[1]) * k
        v_in.append([-tx, -ty])
        v_out.append([tx, ty])
    if not closed:
        v_in[0] = [0, 0]
        v_out[-1] = [0, 0]
    return path([list(p) for p in pts], v_in, v_out, closed)


def group(items, name="grp", p=None, a=None, s=None, r=None, o=None):
    tr = {"ty": "tr",
          "p": p if p is not None else static([0, 0]),
          "a": a if a is not None else static([0, 0]),
          "s": s if s is not None else static([100, 100]),
          "r": r if r is not None else static(0),
          "o": o if o is not None else static(100)}
    it = list(items) + [tr]
    return {"ty": "gr", "nm": name, "np": len(it), "it": it}


def layer(name, shapes, ind, op, p=None, r=None, s=None, o=None, st=0):
    return {"ddd": 0, "ind": ind, "ty": 4, "nm": name, "sr": 1,
            "ks": {"o": o if o is not None else static(100),
                   "r": r if r is not None else static(0),
                   "p": p if p is not None else static([CX, CY, 0]),
                   "a": static([0, 0, 0]),
                   "s": s if s is not None else static([100, 100, 100])},
            "ao": 0, "hasMask": False, "shapes": shapes,
            "ip": 0, "op": op, "st": st, "bm": 0}


# --------------------------------------------------------------- face parts --
def plate():
    """Grok black-hole face: near-black gradient disc + rim + gloss."""
    gloss = group([ellipse(0, 0, 56, 30), fill(C_GLOSS, GLOSS_OP)],
                  name="gloss", p=static([-20, -36]), r=static(-18))
    base = group([ellipse(0, 2, 134, 134),
                  gfill(PLATE_TOP, PLATE_BOT, (0, -65), (0, 69)),
                  stroke(PLATE_RIM, 1.5)],
                 name="base")
    return [gloss, base]   # top-first


def ring_arc(R, a0, a1, cy=2.0, steps=10):
    """circular arc (degrees, y-down screen coords) with exact cubic
    tangents: k = 4/3 * tan(theta/4) per segment."""
    th = math.radians((a1 - a0) / steps)
    k = 4.0 / 3 * math.tan(th / 4)
    verts, v_in, v_out = [], [], []
    for i in range(steps + 1):
        a = math.radians(a0) + th * i
        x, y = R * math.cos(a), cy + R * math.sin(a)
        tx, ty = -math.sin(a) * k * R, math.cos(a) * k * R
        verts.append([x, y])
        v_in.append([-tx, -ty] if i > 0 else [0, 0])
        v_out.append([tx, ty] if i < steps else [0, 0])
    return path(verts, v_in, v_out)


def breathe(loop):
    """Emotion-Ball style body breathing: subtle volume-preserving
    squash & stretch (y up while x down) over one loop."""
    return [(0, [100, 100, 100]), (loop / 2, [101.2, 100.7, 100]),
            (loop, [100, 100, 100])]


def drift(loop, amp=1.5):
    """Emotion-Ball style gaze micro-drift: eyes slowly wander in a small
    diamond path (loop-relative, caller shifts via face-level ENTRY)."""
    return anim(shifted([(0, [0, 0]), (loop * 0.25, [amp, -amp * 0.6]),
                         (loop * 0.5, [0, 0]),
                         (loop * 0.75, [-amp, amp * 0.6]),
                         (loop, [0, 0])]), 2)


def orbit(loop, R=73.0, sweep=300.0, w=4.5, speed=1.0):
    """the orbital swoosh: a white arc ring circling the ball.
    Rotates an integer number of revolutions per loop so the wrap is
    seamless; speed scales with the emotion's energy."""
    revs = max(1, int(round(loop * speed / 60.0)))
    return group([ring_arc(R, -230.0, -230.0 + sweep), stroke(MONO, w, 85)],
                 name="orbit",
                 r=anim(shifted([(0, 0), (loop, 360 * revs)]), ease=E_LIN))


def eye(color, at, w=25, h=32, r=11, s=None, o=100, p=None):
    """glossy squircle eye (anime catchlight, Emo/Vector style)."""
    glint = group([ellipse(0, 0, 7, 7), fill(C_GLOSS, 90)],
                  name="glint", p=static([-w * 0.22, -h * 0.24]))
    ball = group([rrect(0, 0, w, h, r), fill(color, o)], name="ball")
    return group([glint, ball], name="eye",
                 p=p if p is not None else static(list(at)),
                 s=s if s is not None else eye_s())


def arc_eye(color, at, w=24, bulge=-13, sw=6.5, s=None):
    """happy '^^' eye (bulge<0) or closed lid (bulge>0)."""
    return group([arc(-w / 2, 4, w / 2, 4, bulge), stroke(color, sw)],
                 name="eye", p=static(list(at)),
                 s=s if s is not None else eye_s())


def x_eye(color, at, sz=7.5, sw=5, r=None, s=None):
    l1 = path([[-sz, -sz], [sz, sz]], [[0, 0], [0, 0]], [[0, 0], [0, 0]])
    l2 = path([[-sz, sz], [sz, -sz]], [[0, 0], [0, 0]], [[0, 0], [0, 0]])
    return group([l1, l2, stroke(color, sw)], name="eye",
                 p=static(list(at)), r=r,
                 s=s if s is not None else eye_s())


def heart(color, at, size=1.0, s=None, o=None, p=None):
    """heart with glint, built from 2 circles + diamond."""
    r = 6.0 * size
    d = 12.0 * size
    glint = group([ellipse(0, 0, 4.5, 4.5), fill(C_GLOSS, 80)],
                  name="glint", p=static([-r * 0.9, -r * 1.1]))
    body = group([ellipse(-r, -r * 0.6, d, d),
                  ellipse(r, -r * 0.6, d, d),
                  group([rrect(0, 0, d * 1.42, d * 1.42, 2)],
                        name="dia", r=static(45), p=static([0, r * 0.75])),
                  fill(color)],
                 name="body")
    return group([glint, body], name="eye",
                 p=p if p is not None else static(list(at)),
                 s=s if s is not None else eye_s(), o=o)


def mouth_oval(color, w=26, h=14, op=100, at=None, s=None):
    x, y = at if at is not None else MOUTH
    return group([ellipse(0, 0, w, h), fill(color, op)],
                 name="mouth", p=static([x, y]),
                 s=s if s is not None else mouth_s())


def mouth_line(color, w=24, h=7, op=100, at=None, s=None):
    x, y = at if at is not None else MOUTH
    return group([rrect(0, 0, w, h, h / 2), fill(color, op)],
                 name="mouth", p=static([x, y]),
                 s=s if s is not None else mouth_s())


def mouth_smile(color, at=None, w=30, bulge=11, sw=6):
    x, y = at if at is not None else MOUTH
    return group([arc(-w / 2, -2, w / 2, -2, bulge), stroke(color, sw)],
                 name="mouth", p=static([x, y]), s=mouth_s())


def mouth_frown(color, at=None, w=26, bulge=-9, sw=5.5):
    x, y = at if at is not None else MOUTH
    return group([arc(-w / 2, 3, w / 2, 3, bulge), stroke(color, sw)],
                 name="mouth", p=static([x, y]), s=mouth_s())


def cheeks(op=None, spread=38):
    if op is None:
        op = CHEEK_OP
    return group([ellipse(-spread, 15, 12, 12), ellipse(spread, 15, 12, 12),
                  fill(C_BLUSH, op)], name="cheeks")


def face(parts, op, p=None, r=None, s=None, spin=1.0):
    """face layer: features (top-first) + orbit swoosh + plate (bottom).
    Default body motion is the Emotion-Ball breathing squash."""
    loop = op - ENTRY
    return layer("face",
                 list(parts) + [orbit(loop, speed=spin)] + plate(),
                 1, op,
                 p=p if p is not None else face_p(),
                 r=r if r is not None else face_r(),
                 s=s if s is not None else face_s(breathe(loop)))


def doc(name, loop, layers):
    op = ENTRY + loop
    return {"v": "5.7.4", "fr": FPS, "ip": 0, "op": op, "w": W, "h": H,
            "nm": name, "ddd": 0, "assets": [],
            "meta": {"g": "at-desktop robot_emotion 1.0"},
            "layers": layers}


# ----------------------------------------------------------------- emotions --
def em_idle():
    loop = 120
    op = ENTRY + loop
    blink = blinks(loop, [(58, 66), (104, 110)])
    glance = anim(shifted([(0, [0, 0]), (80, [0, 0]), (87, [-5, -1]),
                           (99, [-5, -1]), (106, [0, 0]), (120, [0, 0])]), 2)
    eyes = group([
        eye(C_IDLE, EYE_L, s=eye_s(blink)),
        eye(C_IDLE, EYE_R, s=eye_s(blink)),
    ], name="eyes", p=glance)   # Vector-style idle look-around
    parts = [
        eyes,
        mouth_smile(C_IDLE, w=20, bulge=5, sw=5),
    ]
    return doc("robot-idle", loop,
               [face(parts, op,
                     p=face_p([(0, [80, 80, 0]), (60, [80, 77.5, 0]),
                               (120, [80, 80, 0])]))])


def em_listening():
    loop = 72
    op = ENTRY + loop
    pulse = [(0, [100, 100]), (18, [105, 108]), (36, [100, 100]),
             (54, [104, 106]), (72, [100, 100])]
    bars = []
    for i, (x, d) in enumerate(((-56, 0), (-47, 12), (47, 8), (56, 20))):
        lvl = anim([(0, [100, 30]), (14, [100, 100]), (28, [100, 45]),
                    (42, [100, 85]), (56, [100, 30]), (72, [100, 30])], 2)
        bars.append(group([rrect(0, 0, 5, 22, 2.5), fill(C_LISTEN, 90)],
                          name="bar%d" % i, p=static([x, -2]), s=lvl))
    parts = [
        group([
            eye(C_LISTEN, EYE_L, w=26, h=33, r=12, s=eye_s(pulse)),
            eye(C_LISTEN, EYE_R, w=26, h=33, r=12, s=eye_s(pulse)),
        ], name="eyes", p=drift(loop, 1.2)),
        mouth_line(C_LISTEN, w=20, h=8),
    ] + bars
    return doc("robot-listening", loop,
               [face(parts, op,
                     s=face_s([(0, [100, 100, 100]), (36, [103.5, 103.5, 100]),
                               (72, [100, 100, 100])]))])


def em_thinking():
    loop = 90
    op = ENTRY + loop
    wander = anim(shifted([(0, [0, 0]), (18, [-8, -5]), (40, [-8, -5]),
                           (58, [8, -5]), (78, [8, -5]), (89, [0, 0])]), 2)
    halo = group([ellipse(0, 0, 36, 10), stroke(C_THINK, 2.5, 60)],
                 name="halo", p=static([0, -57]),
                 o=anim(shifted([(0, 25), (45, 65), (90, 25)])))
    eyes = group([
        eye(C_THINK, EYE_L, w=23, h=23, r=10),
        eye(C_THINK, EYE_R, w=23, h=23, r=10),
    ], name="eyes", p=wander)
    parts = [halo, eyes, mouth_line(C_THINK, w=14, h=6, op=80)]
    layers = []
    for i, dx in enumerate((-18, 0, 18)):
        t0 = ENTRY + i * 15
        dot = group([ellipse(0, 0, 8, 8), fill(C_THINK)],
                    name="dot",
                    p=anim([(t0, [dx, -50]), (t0 + 15, [dx, -58]),
                            (t0 + 30, [dx, -50]), (t0 + 44, [dx, -50]),
                            (op, [dx, -50])], 2),
                    o=anim([(0, 0), (t0, 0), (t0 + 15, 100), (t0 + 30, 30),
                            (t0 + 44, 0), (op, 0)]))
        layers.append(layer("dot%d" % i, [dot], len(layers) + 2, op))
    layers.append(face(parts, op))
    return doc("robot-thinking", loop, layers)


def em_speaking():
    loop = 48
    op = ENTRY + loop
    talk = [(0, [100, 18]), (5, [112, 100]), (10, [96, 35]),
            (15, [108, 95]), (20, [100, 25]), (25, [110, 88]),
            (30, [96, 30]), (35, [106, 92]), (40, [100, 22]),
            (47, [100, 18])]
    blink = blinks(loop, [(40, 46)])
    parts = [
        group([
            eye(C_SPEAK, EYE_L, s=eye_s(blink)),
            eye(C_SPEAK, EYE_R, s=eye_s(blink)),
        ], name="eyes", p=drift(loop, 1.0)),
        mouth_oval(C_SPEAK, s=mouth_s(talk)),
    ]
    return doc("robot-speaking", loop, [face(parts, op)])


def em_happy():
    loop = 60
    op = ENTRY + loop
    squish = [(0, [100, 100]), (15, [104, 96]), (30, [100, 100]),
              (45, [103, 97]), (60, [100, 100])]
    parts = [
        arc_eye(C_HAPPY, EYE_L, w=26, s=eye_s(squish)),
        arc_eye(C_HAPPY, EYE_R, w=26, s=eye_s(squish)),
        mouth_smile(C_HAPPY, w=36, bulge=14, sw=7),
        cheeks(),
    ]
    return doc("robot-happy", loop,
               [face(parts, op,
                     p=face_p([(0, [80, 80, 0]), (15, [80, 74.5, 0]),
                               (30, [80, 80, 0]), (45, [80, 76.5, 0]),
                               (60, [80, 80, 0])]))])


def em_love():
    loop = 90
    op = ENTRY + loop
    beat = [(0, [100, 100]), (9, [120, 120]), (18, [100, 100]),
            (27, [113, 113]), (36, [100, 100]), (90, [100, 100])]
    parts = [
        group([
            heart(C_LOVE, EYE_L, 0.95, s=eye_s(beat)),
            heart(C_LOVE, EYE_R, 0.95, s=eye_s(beat)),
        ], name="eyes", p=drift(loop, 1.2)),
        mouth_smile(C_LOVE, w=26, bulge=10, sw=5.5),
        cheeks(),
    ]
    layers = []
    for i, (dx, t0) in enumerate(((14, ENTRY), (-16, ENTRY + 45))):
        fh = heart(C_LOVE, [0, 0], 0.55,
                   p=anim([(t0, [0, -14]), (t0 + 38, [0, -46]),
                           (op, [0, -46])], 2, ease=E_LIN),
                   s=anim([(t0, [60, 60]), (t0 + 18, [100, 100]),
                           (t0 + 38, [100, 100]), (op, [100, 100])], 2),
                   o=anim([(0, 0), (t0, 0), (t0 + 9, 85), (t0 + 26, 85),
                           (t0 + 38, 0), (op, 0)]))
        layers.append(layer("heart%d" % i, [fh], len(layers) + 2, op,
                            p=static([80 + dx, 42, 0])))
    layers.append(face(parts, op))
    return doc("robot-love", loop, layers)


def em_surprised():
    loop = 60
    op = ENTRY + loop
    pop = [(0, [100, 100]), (6, [130, 130]), (11, [121, 121]),
           (44, [121, 121]), (52, [100, 100]), (60, [100, 100])]
    parts = [
        group([
            eye(C_CONN, EYE_L, w=25, h=31, r=12, s=eye_s(pop)),
            eye(C_CONN, EYE_R, w=25, h=31, r=12, s=eye_s(pop)),
        ], name="eyes", p=drift(loop, 1.0)),
        # mouth stays shut during the enter pop, then opens on the jump
        mouth_oval(C_CONN, w=17, h=21, at=MOUTH,
                   s=anim(shifted([(0, [10, 10]), (7, [115, 115]),
                                   (11, [100, 100]), (44, [100, 100]),
                                   (52, [10, 10]), (60, [10, 10])]), 2,
                          ease=E_OUT)),
    ]
    return doc("robot-surprised", loop,
               [face(parts, op,
                     p=face_p([(0, [80, 80, 0]), (6, [80, 73, 0]),
                               (12, [80, 80, 0]), (60, [80, 80, 0])]))])


def em_sad():
    loop = 120
    op = ENTRY + loop
    droop = [(0, [100, 100]), (30, [100, 58]), (90, [100, 58]),
             (119, [100, 100])]
    # anchor at eye bottom so the top sinks
    el = group([rrect(0, -14, 23, 28, 10), fill(C_SAD, 85)], name="eye",
               p=static([EYE_L[0], EYE_L[1] + 14]), s=eye_s(droop))
    er = group([rrect(0, -14, 23, 28, 10), fill(C_SAD, 85)], name="eye",
               p=static([EYE_R[0], EYE_R[1] + 14]), s=eye_s(droop))
    # sad brows: inner ends raised
    brow_l = group([rrect(0, 0, 16, 5, 2.5), fill(C_SAD, 70)],
                   name="brow", p=static([-24, -28]), r=static(-14))
    brow_r = group([rrect(0, 0, 16, 5, 2.5), fill(C_SAD, 70)],
                   name="brow", p=static([24, -28]), r=static(14))
    parts = [brow_l, brow_r,
             group([el, er], name="eyes", p=drift(loop, 0.8)),
             mouth_frown(C_SAD, at=(0, 30))]
    tear = group([ellipse(0, 2, 7, 9),
                  path([[0, -7], [-3.5, 1], [3.5, 1]], [[0, 0]] * 3,
                       [[0, 0]] * 3, True),
                  fill(C_TEAR)], name="tear",
                 p=anim([(20, [EYE_R[0] + 8, 8]), (70, [EYE_R[0] + 8, 34]),
                         (71, [EYE_R[0] + 8, 8]), (119, [EYE_R[0] + 8, 8])],
                        2),
                 o=anim([(20, 0), (28, 90), (62, 90), (70, 0),
                         (71, 0), (119, 0)]))
    layers = [layer("tear", [tear], 2, op),
              face(parts, op,
                   p=face_p([(0, [80, 80, 0]), (60, [80, 84, 0]),
                             (120, [80, 80, 0])]))]
    return doc("robot-sad", loop, layers)


def em_angry():
    loop = 72
    op = ENTRY + loop
    shake = [(8, [80, 80, 0]), (12, [77, 80, 0]), (16, [83, 80, 0]),
             (20, [77.8, 80, 0]), (24, [82.2, 80, 0]), (28, [80, 80, 0]),
             (72, [80, 80, 0])]
    shake_r = [(8, 0), (12, -2.5), (16, 2.5), (20, -1.8), (24, 1.8),
               (28, 0), (72, 0)]
    snap = anim(shifted([(0, 0), (8, 100), (60, 100), (68, 0), (72, 0)]),
                ease=E_OUT)
    brow_l = group([rrect(0, 0, 22, 6.5, 3), fill(C_ANGRY)],
                   name="brow", p=static([-25, -27]), r=static(22), o=snap)
    brow_r = group([rrect(0, 0, 22, 6.5, 3), fill(C_ANGRY)],
                   name="brow", p=static([25, -27]), r=static(-22), o=snap)
    squint = [(0, [100, 100]), (8, [100, 62]), (60, [100, 62]),
              (68, [100, 100])]
    parts = [
        brow_l, brow_r,
        eye(C_ANGRY, EYE_L, h=28, s=eye_s(squint)),
        eye(C_ANGRY, EYE_R, h=28, s=eye_s(squint)),
        mouth_line(C_ANGRY, w=22, h=6, at=(0, 28),
                   s=mouth_s([(0, [100, 100]), (8, [80, 100]),
                              (60, [80, 100]), (68, [100, 100])])),
    ]
    return doc("robot-angry", loop,
               [face(parts, op,
                     p=anim([(0, [80, 80, 0]), (ENTRY, [80, 80, 0])]
                            + shifted(shake), 3, ease=E_LIN),
                     r=anim(shifted(shake_r), ease=E_LIN),
                     s=face_s())])


def em_confused():
    loop = 120
    op = ENTRY + loop
    squint = [(0, [100, 100]), (14, [100, 55]), (92, [100, 55]),
              (108, [100, 100])]
    raise_l = anim(shifted([(0, list(EYE_L)),
                            (14, [EYE_L[0] - 2, EYE_L[1] - 5]),
                            (92, [EYE_L[0] - 2, EYE_L[1] - 5]),
                            (108, list(EYE_L))]), 2)
    parts = [
        group([eye(C_CONFUSE, [0, 0], w=25, h=31, r=11)], name="eye",
              p=raise_l),
        eye(C_CONFUSE, EYE_R, s=eye_s(squint)),
        group([smooth_path([(-15, 1), (-7.5, -2.5), (0, 3.5), (7.5, -2.5),
                            (15, 1)]),
               stroke(C_CONFUSE, 4.5)], name="mouth", p=static(list(MOUTH)),
              s=mouth_s()),
    ]
    q = group([smooth_path([(-5.5, -8), (0, -12.5), (5, -10.5), (5.5, -5),
                            (1, -2), (0, 2)], k=0.3),
               stroke(C_CONFUSE, 4.5),
               ellipse(0, 9, 5.5, 5.5),
               fill(C_CONFUSE)],
              name="qmark",
              p=anim([(0, [0, 0]), (30, [0, -4]), (60, [0, 0]),
                      (90, [0, -4]), (120, [0, 0])], 2))
    layers = [layer("qmark", [q], 2, op, p=static([128, 34, 0]),
                    o=anim([(0, 0), (14, 0), (26, 100), (92, 100),
                            (108, 0), (120, 0)])),
              face(parts, op,
                   r=face_r([(0, 0), (14, 9), (92, 9), (108, 0),
                             (120, 0)]))]
    return doc("robot-confused", loop, layers)


def em_sleepy():
    loop = 150
    op = ENTRY + loop
    breath = [(0, [100, 100, 100]), (75, [100, 102.5, 100]),
              (150, [100, 100, 100])]
    bubble = anim(shifted([(0, [100, 100]), (75, [135, 135]),
                           (150, [100, 100])]), 2)
    parts = [
        arc_eye(C_SLEEP, EYE_L, w=22, bulge=7, sw=5.5),
        arc_eye(C_SLEEP, EYE_R, w=22, bulge=7, sw=5.5),
        group([ellipse(0, 0, 10, 11), fill(C_SLEEP, 55)], name="mouth",
              p=static([MOUTH[0], MOUTH[1] - 2]), s=bubble),
    ]
    layers = []

    def zzz(i, at, size, t0, t1):
        w, h = 7 * size, 6 * size
        z = group([path([[-w, -h], [w, -h], [-w, h], [w, h]],
                        [[0, 0]] * 4, [[0, 0]] * 4),
                   stroke(C_SLEEP, 3.2 * size)], name="z",
                  p=anim([(t0, list(at)), (t1, [at[0] + 10, at[1] - 14]),
                          (t1 + 1, list(at)), (loop, list(at))], 2,
                         ease=E_LIN),
                  o=anim([(t0, 0), (t0 + 12, 90), (t1 - 12, 90), (t1, 0),
                          (t1 + 1, 0), (loop, 0)]))
        return layer("z%d" % i, [z], i + 2, op)

    layers.append(zzz(0, (18, -34), 0.9, 18, 66))
    layers.append(zzz(1, (32, -46), 1.25, 45, 105))
    layers.append(zzz(2, (48, -58), 1.6, 80, 140))
    layers.append(face(parts, op,
                       p=face_p([(0, [80, 80, 0]), (75, [80, 81.5, 0]),
                                 (150, [80, 80, 0])]),
                       s=face_s(breath)))
    return doc("robot-sleepy", loop, layers)


def em_dizzy_error():
    loop = 72
    op = ENTRY + loop
    wob = [(0, 0), (10, -6), (22, 6), (32, -4), (44, 4), (54, -2),
           (64, 0), (72, 0)]
    spin = anim(shifted([(0, 0), (12, 28), (28, -28), (44, 18), (60, -10),
                         (71, 0)]))
    parts = [
        x_eye(C_ERROR, EYE_L, r=spin),
        x_eye(C_ERROR, EYE_R, r=spin),
        group([smooth_path([(-14, 1), (-7, -2), (0, 2.5), (7, -2), (14, 1)]),
               stroke(C_ERROR, 4.5)], name="mouth", p=static(list(MOUTH)),
              s=mouth_s()),
    ]
    return doc("robot-error", loop,
               [face(parts, op, r=face_r(wob), spin=2.0)])


def em_scanning():
    """agent state: searching/retrieving - narrowed eyes, rapid triangle-wave
    left-right scan, ball leans into each sweep."""
    loop = 60
    op = ENTRY + loop
    scan = anim(shifted([(0, [-8, 0]), (15, [8, 0]), (30, [-8, 0]),
                         (45, [8, 0]), (60, [-8, 0])]), 2, ease=E_LIN)
    narrow = [(0, [100, 78]), (60, [100, 78])]   # held narrowed
    eyes = group([
        eye(MONO, EYE_L, w=26, h=30, r=11, s=eye_s(narrow)),
        eye(MONO, EYE_R, w=26, h=30, r=11, s=eye_s(narrow)),
    ], name="eyes", p=scan)
    parts = [eyes, mouth_line(MONO, w=18, h=6, op=85)]
    return doc("robot-scanning", loop,
               [face(parts, op,
                     r=face_r([(0, 0), (15, 2.5), (30, 0), (45, -2.5),
                               (60, 0)]),
                     spin=2.0)])


def em_celebrate():
    """agent state: task done - happy arcs, big bounce, confetti burst."""
    loop = 90
    op = ENTRY + loop
    squish = [(0, [100, 100]), (12, [105, 95]), (24, [100, 100]),
              (90, [100, 100])]
    parts = [
        arc_eye(MONO, EYE_L, w=26, s=eye_s(squish)),
        arc_eye(MONO, EYE_R, w=26, s=eye_s(squish)),
        mouth_smile(MONO, w=38, bulge=15, sw=7),
        cheeks(),
    ]
    layers = []
    conf_x = (-34, -20, -7, 8, 21, 33)
    conf_r = (300, -260, 340, -300, 280, -330)
    for i in range(6):
        t0 = ENTRY + i * 4
        if i % 2:
            shape = [rrect(0, 0, 4.5, 7, 2), fill(MONO, 80)]
        else:
            shape = [ellipse(0, 0, 5, 5), fill(MONO, 70)]
        conf = group(shape, name="conf",
                     p=anim([(t0, [0, -50]), (t0 + 46, [conf_x[i] * 1.6, 44]),
                             (op, [conf_x[i] * 1.6, 44])], 2, ease=E_IN),
                     r=anim([(t0, 0), (t0 + 46, conf_r[i])], ease=E_LIN),
                     o=anim([(0, 0), (t0, 0), (t0 + 4, 90), (t0 + 36, 85),
                             (t0 + 46, 0), (op, 0)]))
        layers.append(layer("conf%d" % i, [conf], i + 2, op))
    layers.append(face(parts, op,
                       p=face_p([(0, [80, 80, 0]), (12, [80, 72, 0]),
                                 (24, [80, 80, 0]), (40, [80, 75, 0]),
                                 (54, [80, 80, 0]), (90, [80, 80, 0])]),
                       spin=1.5))
    return doc("robot-celebrate", loop, layers)


EMOTIONS = {
    # lifecycle group (00-09)
    "00_sleep":     em_sleepy,
    "02_idle":      em_idle,
    # emotion group (10-29)
    "10_happy":     em_happy,
    "11_love":      em_love,
    "12_angry":     em_angry,
    "13_surprised": em_surprised,
    "14_sad":       em_sad,
    "15_confused":  em_confused,
    # agent-state group (30-49)
    "30_thinking":  em_thinking,
    "31_listening": em_listening,
    "32_speaking":  em_speaking,
    "33_scanning":  em_scanning,
    "40_error":     em_dizzy_error,
    "41_celebrate": em_celebrate,
}


def main():
    outdir = os.path.dirname(os.path.abspath(__file__))
    print("segments: enter=0..%d, loop=%d..op-1" % (ENTRY - 1, ENTRY))
    for theme in THEMES:
        set_theme(theme)
        tdir = os.path.join(outdir, theme)
        os.makedirs(tdir, exist_ok=True)
        for name, fn in EMOTIONS.items():
            d = fn()
            d["nm"] = d["nm"] + "-" + theme
            path_out = os.path.join(tdir, name + ".json")
            with open(path_out, "w") as f:
                json.dump(d, f, separators=(",", ":"))
            size = os.path.getsize(path_out)
            print("%-6s %-14s %3d frames (enter %d + loop %d = %.1fs)  "
                  "%5d bytes"
                  % (theme, name, d["op"], ENTRY, d["op"] - ENTRY,
                     d["op"] / FPS, size))


if __name__ == "__main__":
    main()
