"""Blender background script: rig the Meshy cat and render every pet
animation side-on (cat facing right) with a transparent background.

The model is the user's Meshy AI export ("Midnight Whiskers", OBJ + PNG
texture), kept outside the repo (~14MB). Static mesh, no rig: this script
builds a quadruped skeleton by hand (joint positions measured from the
mesh), skins it with automatic weights and poses every animation
procedurally (FK, plus IK on the legs where the body drops/tilts).

Usage (then run tools/cat3d/crop_frames.py on <out_dir>):
  python tools/cat3d/close_eyes.py <texture.png> <eyes_closed.png>
  blender -b --factory-startup -P render_cat_3d.py -- <model.obj> <out_dir> \
      [--eyes-closed=<eyes_closed.png>] [state ...]

The closed-eye texture is used for the sleep frames (the model has no
eyelids); without it sleep is rendered with open eyes.

Coordinates (after OBJ import): the cat faces -Y, Z is up, paws on z=-0.69.
Every bone's local X axis is world X, so pose rotation_euler.x is always
"swing in the side-view plane"; for a downward leg bone +x moves the paw
backward (+Y).
"""
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
OBJ, OUT = args[0], Path(args[1])
EYES_CLOSED = next((a.split("=", 1)[1] for a in args[2:] if a.startswith("--eyes-closed=")), None)
ONLY = {a for a in args[2:] if not a.startswith("--")}
GROUND = -0.69
V = Vector
rad = math.radians


# ---- model ------------------------------------------------------------------
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.obj_import(filepath=OBJ)
cat = bpy.context.selected_objects[0]
bpy.context.view_layer.objects.active = cat
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
dec = cat.modifiers.new("dec", "DECIMATE")
dec.ratio = 0.35
bpy.ops.object.modifier_apply(modifier=dec.name)
for mat in cat.data.materials:
    bsdf = mat.node_tree.nodes.get("Principled BSDF") if mat and mat.use_nodes else None
    if bsdf:
        # Fully matte fur and eyes (chosen look: no gloss, no rim glow).
        bsdf.inputs["Roughness"].default_value = 1.0
        bsdf.inputs["Specular IOR Level"].default_value = 0.0

# ---- skeleton ---------------------------------------------------------------
BONES = {
    "spine": (V((0, 0.28, -0.20)), V((0, -0.10, -0.20)), None),
    "chest": (V((0, -0.10, -0.20)), V((0, -0.42, -0.14)), "spine"),
    "neck": (V((0, -0.42, -0.14)), V((0, -0.55, 0.08)), "chest"),
    "head": (V((0, -0.55, 0.08)), V((0, -0.60, 0.55)), "neck"),
    "tail1": (V((0, 0.30, -0.17)), V((0, 0.40, 0.00)), "spine"),
    "tail2": (V((0, 0.40, 0.00)), V((0, 0.47, 0.18)), "tail1"),
    "tail3": (V((0, 0.47, 0.18)), V((0, 0.58, 0.30)), "tail2"),
    "tail4": (V((0, 0.58, 0.30)), V((0, 0.75, 0.29)), "tail3"),
    "tail5": (V((0, 0.75, 0.29)), V((0, 0.93, 0.15)), "tail4"),
}
for side, sx in (("L", -1), ("R", 1)):
    BONES[f"fleg_up.{side}"] = (V((sx * 0.12, -0.50, -0.15)), V((sx * 0.12, -0.50, -0.42)), "chest")
    BONES[f"fleg_lo.{side}"] = (V((sx * 0.12, -0.50, -0.42)), V((sx * 0.13, -0.53, -0.63)), f"fleg_up.{side}")
    BONES[f"fpaw.{side}"] = (V((sx * 0.13, -0.53, -0.63)), V((sx * 0.13, -0.62, -0.69)), f"fleg_lo.{side}")
    BONES[f"hleg_up.{side}"] = (V((sx * 0.15, 0.16, -0.20)), V((sx * 0.17, 0.24, -0.45)), "spine")
    BONES[f"hleg_lo.{side}"] = (V((sx * 0.17, 0.24, -0.45)), V((sx * 0.18, 0.20, -0.63)), f"hleg_up.{side}")
    BONES[f"hpaw.{side}"] = (V((sx * 0.18, 0.20, -0.63)), V((sx * 0.18, 0.11, -0.69)), f"hleg_lo.{side}")

arm = bpy.data.armatures.new("rig")
rig = bpy.data.objects.new("rig", arm)
bpy.context.scene.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="EDIT")
for name, (h, t, _) in BONES.items():
    eb = arm.edit_bones.new(name)
    eb.head, eb.tail = h, t
    eb.align_roll(V((1, 0, 0)).cross((t - h).normalized()))
for name, (_, _, parent) in BONES.items():
    if parent:
        eb = arm.edit_bones[name]
        eb.parent = arm.edit_bones[parent]
        eb.use_connect = (eb.head - eb.parent.tail).length < 1e-4
bpy.ops.object.mode_set(mode="OBJECT")

bpy.ops.object.select_all(action="DESELECT")
cat.select_set(True)
rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.parent_set(type="ARMATURE_AUTO")

PB = rig.pose.bones
for pb in PB:
    pb.rotation_mode = "XYZ"

# IK on the legs (2-bone chains up+lo), off by default: poses where the body
# drops or tilts (crouch, sit, lie down) set ground targets for the paws and
# let Blender bend the legs to reach them.
IK = {}
for leg in ("fleg", "hleg"):
    for side in ("L", "R"):
        key = f"{leg}.{side}"
        target = bpy.data.objects.new(f"ik_{key}", None)
        bpy.context.scene.collection.objects.link(target)
        pole = bpy.data.objects.new(f"pole_{key}", None)
        bpy.context.scene.collection.objects.link(pole)
        lo = PB[f"{leg}_lo.{side}"]
        c = lo.constraints.new("IK")
        c.target = target
        c.pole_target = pole
        c.pole_angle = rad(-90)
        c.chain_count = 2
        c.influence = 0.0
        IK[key] = (c, target, pole)


def rest_paw(key):
    """Rest-pose wrist/ankle position (bottom of the lower leg bone)."""
    leg, side = key.split(".")
    return BONES[f"{leg}_lo.{side}"][1].copy()


def reset_pose():
    rig.location = (0, 0, 0)
    rig.rotation_euler = (0, 0, 0)
    for pb in PB:
        pb.location = (0, 0, 0)
        pb.rotation_euler = (0, 0, 0)
        pb.scale = (1, 1, 1)
    for c, _, _ in IK.values():
        c.influence = 0.0


def ik(key, paw_pos, pole_dir_y=1.0):
    """Pins `key`'s wrist/ankle at paw_pos (world). The pole sits behind
    (+Y) the joint so the elbow/hock bends the cat way."""
    c, target, pole = IK[key]
    c.influence = 1.0
    target.location = paw_pos
    leg, side = key.split(".")
    joint = BONES[f"{leg}_up.{side}"][1]
    pole.location = V((joint.x, joint.y + pole_dir_y, joint.z))


def rot(name, x=0.0, y=0.0, z=0.0):
    PB[name].rotation_euler = (x, y, z)


def tail(curl=0.0, lift=0.0, sway=0.0, t=0.0, wave=0.0):
    """curl: extra bend per segment; lift: base raise; sway: side wiggle
    amplitude; wave: travelling up-down wave amplitude (phase t)."""
    for i in range(1, 6):
        x = (lift if i == 1 else curl) + wave * math.sin(2 * math.pi * t - i * 0.6)
        z = sway * math.sin(2 * math.pi * t - i * 0.5)
        rot(f"tail{i}", x, 0, z)


def smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def lerp(a, b, t):
    return a + (b - a) * t


# ---- animations -------------------------------------------------------------
# Each returns a list of callables, one per frame, that pose the rig.

def anim_idle():
    n = 16
    frames = []
    for f in range(n):
        t = f / n
        breath = math.sin(2 * math.pi * t)

        def pose(t=t, breath=breath):
            rot("chest", rad(1.5) * breath)
            rot("neck", rad(-1.0) * breath)
            rot("head", rad(2.5) * math.sin(2 * math.pi * t + 1.0), 0, rad(3) * math.sin(2 * math.pi * t))
            tail(sway=rad(5), t=t, wave=rad(3))
        frames.append(pose)
    return frames


def _leg_cycle(s, swing, bend, stance=0.6):
    if s < stance:
        return -swing + 2 * swing * (s / stance), 0.0
    u = (s - stance) / (1 - stance)
    return swing - 2 * swing * smooth(u), bend * math.sin(math.pi * u)


def anim_walk():
    n = 16
    phases = {"hleg.L": 0.0, "fleg.L": 0.25, "hleg.R": 0.5, "fleg.R": 0.75}
    frames = []
    for f in range(n):
        t = f / n

        def pose(t=t):
            for key, ph in phases.items():
                leg, side = key.split(".")
                up, bend = _leg_cycle((t + ph) % 1.0, rad(24), rad(50))
                if leg == "fleg":
                    rot(f"fleg_up.{side}", up)
                    rot(f"fleg_lo.{side}", bend)
                    rot(f"fpaw.{side}", -up * 0.6)
                else:
                    rot(f"hleg_up.{side}", up)
                    rot(f"hleg_lo.{side}", -bend * 0.7)
                    rot(f"hpaw.{side}", bend * 0.5 - up * 0.5)
            bob = math.sin(4 * math.pi * t)
            rig.location.z = 0.008 * bob
            rot("chest", rad(2) * bob)
            rot("head", rad(-3) * bob)
            tail(sway=rad(3), t=t, wave=rad(4))
        frames.append(pose)
    return frames


def anim_run():
    """Rotary gallop: front pair and hind pair half a cycle apart, spine
    flexing (gathered when the legs are under the body, stretched when
    they reach out), tail streaming back."""
    n = 12
    phases = {"fleg.L": 0.0, "fleg.R": 0.08, "hleg.L": 0.5, "hleg.R": 0.58}
    frames = []
    for f in range(n):
        t = f / n

        def pose(t=t):
            for key, ph in phases.items():
                leg, side = key.split(".")
                up, bend = _leg_cycle((t + ph) % 1.0, rad(42), rad(75), stance=0.45)
                if leg == "fleg":
                    rot(f"fleg_up.{side}", up)
                    rot(f"fleg_lo.{side}", bend)
                    rot(f"fpaw.{side}", -up * 0.5)
                else:
                    rot(f"hleg_up.{side}", up)
                    rot(f"hleg_lo.{side}", -bend * 0.6)
                    rot(f"hpaw.{side}", bend * 0.4 - up * 0.5)
            flex = math.sin(2 * math.pi * t)
            rig.location.z = 0.04 * max(0.0, math.sin(2 * math.pi * t + 0.8))
            rig.rotation_euler.x = rad(4) * math.sin(2 * math.pi * t + 1.6)
            rot("spine", rad(6) * flex)
            rot("chest", rad(-6) * flex)
            rot("head", rad(5) * flex)
            # tail lowered to stream out behind (for the up-and-back tail
            # base, negative x tips it back/down)
            rot("tail1", rad(-50))
            for i in range(2, 6):
                rot(f"tail{i}", rad(-4) + rad(7) * math.sin(2 * math.pi * t - i * 0.7))
        frames.append(pose)
    return frames


def _side_angle(v):
    """Angle of a vector in the side-view (Y,Z) plane: 0 = straight down,
    positive = tip toward +Y (the cat's back). A +x pose rotation of any
    bone (or of the whole rig) adds exactly this much to it."""
    return math.atan2(v.y, -v.z)


def _rest_angle(bone):
    h, t, _ = BONES[bone]
    return _side_angle(t - h)


def _solve_leg(leg, side, pitch, drop, shift_y=0.0, target=None):
    """Analytic 2-bone solve in the side plane (instead of Blender's IK,
    whose pole flipped the front elbows forward — legs looked broken):
    put the wrist/ankle at `target` (default: where it stands at rest)
    while the body drops by `drop`, moves by `shift_y` and pitches by
    `pitch`, always taking the solution with the joint pointing BACK, the
    way both a cat's elbow and hock bend."""
    up, lo, paw = f"{leg}_up.{side}", f"{leg}_lo.{side}", f"{'f' if leg == 'fleg' else 'h'}paw.{side}"
    root_rest = BONES[up][0]
    if target is None:
        target = BONES[lo][1]
    c, s_ = math.cos(pitch), math.sin(pitch)
    # rig rotation about X around the origin, then the translation
    root = V((root_rest.x,
              root_rest.y * c - root_rest.z * s_ + shift_y,
              root_rest.y * s_ + root_rest.z * c - drop))
    l1 = (BONES[up][1] - BONES[up][0]).length
    l2 = (BONES[lo][1] - BONES[lo][0]).length
    d_vec = V((0, target.y - root.y, target.z - root.z))
    dist = min(d_vec.length, l1 + l2 - 1e-4)
    a = math.acos(max(-1.0, min(1.0, (l1 * l1 + dist * dist - l2 * l2) / (2 * l1 * dist))))
    base = _side_angle(d_vec)
    # two candidate knee angles; joint "back" = larger Y = larger side angle
    up_abs = base + a
    joint = V((0, root.y + l1 * math.sin(up_abs), root.z - l1 * math.cos(up_abs)))
    lo_abs = _side_angle(V((0, target.y - joint.y, target.z - joint.z)))
    parents = PB["spine"].rotation_euler.x + (PB["chest"].rotation_euler.x if leg == "fleg" else 0.0)
    up_rot = up_abs - _rest_angle(up) - pitch - parents
    lo_rot = lo_abs - _rest_angle(lo) - pitch - parents - up_rot
    rot(up, up_rot)
    rot(lo, lo_rot)
    rot(paw, -(pitch + parents + up_rot + lo_rot))  # paw stays flat on the floor


def _tail_abs(angles_deg, pitch):
    """Poses the tail so each segment points at the given absolute
    side-view angle (0 = down, 90 = straight back, 180 = up)."""
    acc = pitch + PB["spine"].rotation_euler.x
    for i, a in enumerate(angles_deg, start=1):
        own = rad(a) - _rest_angle(f"tail{i}") - acc
        PB[f"tail{i}"].rotation_euler.x = own
        acc += own


def _crouch(depth, tilt=0.0):
    """Body lowered by `depth` (and pitched by `tilt`, + = nose down) with
    all four paws staying where they stand on the ground."""
    rig.location.z = -depth
    rig.rotation_euler.x = tilt
    for leg in ("fleg", "hleg"):
        for side in ("L", "R"):
            _solve_leg(leg, side, tilt, depth)


def anim_jump():
    """One-shot: crouch, push off (hind legs extend, nose up), stretch out
    in the air, tuck the legs. The app moves the window along the arc."""
    keys = [
        # (crouch depth, body pitch, front up, front lo, hind up, hind lo, tail lift)
        (0.00, 0, 0, 0, 0, 0, 0),
        (0.05, rad(3), 0, 0, 0, 0, rad(10)),
        (0.08, rad(4), 0, 0, 0, 0, rad(15)),
        (0.0, rad(-18), rad(-35), rad(30), rad(35), rad(-10), rad(30)),
        (0.0, rad(-24), rad(-55), rad(20), rad(50), rad(-5), rad(40)),
        (0.0, rad(-12), rad(-60), rad(40), rad(40), rad(-30), rad(35)),
        (0.0, rad(-2), rad(-45), rad(60), rad(10), rad(-50), rad(25)),
        (0.0, rad(6), rad(-30), rad(45), rad(-10), rad(-40), rad(15)),
        (0.0, rad(8), rad(-20), rad(30), rad(-15), rad(-30), rad(10)),
    ]
    frames = []
    for depth, pitch, fu, fl, hu, hl, tl in keys:
        def pose(depth=depth, pitch=pitch, fu=fu, fl=fl, hu=hu, hl=hl, tl=tl):
            if depth > 0:
                _crouch(depth, pitch)
            else:
                rig.rotation_euler.x = pitch
                rig.location.z = 0.07  # airborne: keep dangling paws above the ground line
                for side in ("L", "R"):
                    rot(f"fleg_up.{side}", fu)
                    rot(f"fleg_lo.{side}", fl)
                    rot(f"hleg_up.{side}", hu)
                    rot(f"hleg_lo.{side}", hl)
            tail(lift=tl, curl=rad(-4))
        frames.append(pose)
    return frames


def anim_fall():
    """Loop while falling: legs reaching down and forward, slight flail."""
    n = 6
    frames = []
    for f in range(n):
        t = f / n

        def pose(t=t):
            w = math.sin(2 * math.pi * t)
            rig.rotation_euler.x = rad(5)
            for side, ph in (("L", 0.0), ("R", math.pi)):
                sw = rad(5) * math.sin(2 * math.pi * t + ph)
                # front: reaching down-forward, elbow slightly back, paw bent down
                rot(f"fleg_up.{side}", rad(-14) + sw)
                rot(f"fleg_lo.{side}", rad(-8))
                rot(f"fpaw.{side}", rad(25))
                # hind: hanging, hock gently bent back (joint goes back)
                rot(f"hleg_up.{side}", rad(8) - sw)
                rot(f"hleg_lo.{side}", rad(-14))
                rot(f"hpaw.{side}", rad(12))
            rot("head", rad(-8))
            tail(lift=rad(-20), curl=rad(-8), wave=rad(8), t=t)
        frames.append(pose)
    return frames


def anim_land():
    """One-shot: paws touch down, absorb the impact in a crouch, stand up."""
    depths = [0.0, 0.05, 0.09, 0.08, 0.055, 0.03, 0.01, 0.0]
    frames = []
    for i, d in enumerate(depths):
        def pose(d=d, i=i):
            if d > 0:
                _crouch(d, rad(3) * (d / 0.09))
            rot("head", rad(6) * (d / 0.09))
            tail(lift=rad(15) * (1 - i / len(depths)), curl=rad(-5))
        frames.append(pose)
    return frames


def anim_play():
    """One-shot playful pounce/swipe: crouch with a rear wiggle, then the
    right front paw swipes forward-up and comes back down."""
    seq = []
    for i in range(4):  # crouch + wiggle
        seq.append((0.07, rad(5) * math.sin(i * 2.2), 0.0, 0.0))
    seq += [(0.04, 0, rad(-50), rad(-20)), (0.0, 0, rad(-95), rad(-40)),
            (0.0, 0, rad(-110), rad(-60)), (0.0, 0, rad(-80), rad(20)),
            (0.03, 0, rad(-30), rad(30)), (0.0, 0, 0.0, 0.0)]
    frames = []
    for depth, wiggle, swipe_up, swipe_lo in seq:
        def pose(depth=depth, wiggle=wiggle, swipe_up=swipe_up, swipe_lo=swipe_lo):
            if depth > 0:
                _crouch(depth, rad(4))
            rot("spine", 0, 0, wiggle)
            if swipe_up:
                IK["fleg.R"][0].influence = 0.0
                rot("fleg_up.R", swipe_up)
                rot("fleg_lo.R", swipe_lo)
                rot("head", rad(-6))
            tail(lift=rad(10), sway=rad(10), t=wiggle)
        frames.append(pose)
    return frames


def _sit_pose(breath=0.0, t=0.0):
    """Seated: hindquarters down on the ground, chest up, front legs
    straight. Rig pitched nose-up around the hips; IK keeps all paws on
    the ground (hind paws tucked forward under the body)."""
    # The front legs (~0.48 shoulder->wrist) are short for the body: with
    # the hindquarters resting on the ground the chest can only rise ~20deg
    # before the front paws leave the floor.
    pitch, drop = rad(-20), 0.20
    rig.rotation_euler.x = pitch
    rig.location = (0, 0.0, -drop)
    rot("chest", rad(1.2) * breath)
    for side, sx in (("L", -1), ("R", 1)):
        # front legs straight, paws right under the shoulders
        _solve_leg("fleg", side, pitch, drop, target=V((sx * 0.13, -0.54, GROUND + 0.06)))
        # hind legs folded: ankle on the floor under the belly, hock back
        _solve_leg("hleg", side, pitch, drop, target=V((sx * 0.18, 0.02, GROUND + 0.05)))
    rot("neck", rad(6))
    rot("head", rad(9) + rad(2) * breath)
    # tail down to the floor and out behind, tip hooking up (keeps the
    # silhouette inside the shared crop box)
    _tail_abs([78 + 2 * breath, 100, 125, 155, 180], pitch)


def anim_sit():
    n = 8
    return [lambda f=f: _sit_pose(math.sin(2 * math.pi * f / n), f / n) for f in range(n)]


def _lie_pose(breath=0.0):
    """Lying down curled up: body on the ground, legs folded under, head
    resting low, tail wrapped around."""
    # "Loaf": belly on the floor (it sits ~0.45 below the origin at rest),
    # legs folded under, head lowered to rest on the front paws. Eyes are
    # closed by swapping in the closed-eye texture for these frames (the
    # model has no eyelids).
    drop = 0.22
    rig.location = (0, 0.0, -drop)
    rot("chest", rad(1.5) * breath)
    for side, sx in (("L", -1), ("R", 1)):
        _solve_leg("fleg", side, 0.0, drop, target=V((sx * 0.13, -0.60, GROUND + 0.05)))
        _solve_leg("hleg", side, 0.0, drop, target=V((sx * 0.18, 0.10, GROUND + 0.05)))
    rot("neck", rad(30) + rad(1) * breath)
    rot("head", rad(12))
    # tail resting on the floor and wrapped sideways around the body
    # (side-on it reads shorter, and keeps inside the shared crop box)
    _tail_abs([84, 92, 94, 96, 98], 0.0)
    for i in range(2, 6):
        PB[f"tail{i}"].rotation_euler.z = rad(-32)


def anim_sleep():
    n = 8
    return [lambda f=f: _lie_pose(math.sin(2 * math.pi * f / n)) for f in range(n)]


def _leg_abs(leg, side, up_deg, lo_deg, paw_deg, parents):
    """Poses a leg by absolute side-view angles (0 = down, -90 = forward,
    +90 = back); `parents` = rig pitch + spine (+ chest for front legs)."""
    up, lo = f"{leg}_up.{side}", f"{leg}_lo.{side}"
    paw = f"{'f' if leg == 'fleg' else 'h'}paw.{side}"
    up_rot = rad(up_deg) - _rest_angle(up) - parents
    lo_rot = rad(lo_deg) - _rest_angle(lo) - parents - up_rot
    paw_rot = rad(paw_deg) - _rest_angle(paw) - parents - up_rot - lo_rot
    rot(up, up_rot)
    rot(lo, lo_rot)
    rot(paw, paw_rot)


# Scruff hold: hanging nearly vertical from the neck, nose up.
SCRUFF_PITCH = rad(-50)
SCRUFF_LIFT = -0.05


def anim_dragged():
    """Held by the scruff like a kitten: the body hangs below the neck and
    curls up — front legs hanging limp by the chest, hind legs pulled up
    to the belly, tail tucked forward between them, head a bit sheepish —
    with a gentle pendulum swing."""
    n = 8
    frames = []
    for f in range(n):
        t = f / n

        def pose(t=t):
            sw = math.sin(2 * math.pi * t)
            pitch = SCRUFF_PITCH + rad(3) * sw
            rig.rotation_euler.x = pitch
            rig.rotation_euler.y = rad(3) * sw
            rig.location.z = SCRUFF_LIFT
            rot("spine", rad(-14))          # back rounded (C shape)
            rot("chest", rad(-8))
            front = pitch + rad(-14) + rad(-8)
            hind = pitch + rad(-14)
            for side in ("L", "R"):
                _leg_abs("fleg", side, 10, -20, -45, front)    # limp, paws curled in
                _leg_abs("hleg", side, -100, -45, -80, hind)   # pulled up to the belly
            rot("neck", rad(30))
            rot("head", rad(32) + rad(2) * sw)               # head bowed, sheepish
            # tail curled tight forward under the belly, between the hind legs
            _tail_abs([-15, -70, -120, -165, -200], pitch + rad(3) * math.sin(2 * math.pi * t))
        frames.append(pose)
    return frames


def anim_react():
    """Happy little hop in place: quick crouch, small lift, back down."""
    seq = [0.0, 0.06, 0.09, -0.06, -0.10, -0.06, 0.04, 0.0]
    frames = []
    for d in seq:
        def pose(d=d):
            if d > 0:
                _crouch(d)
            else:
                rig.location.z = -d  # lift (legs stay straight, paws off ground)
                for side in ("L", "R"):
                    rot(f"fleg_up.{side}", rad(-10) * (-d / 0.1))
                    rot(f"hleg_up.{side}", rad(15) * (-d / 0.1))
            rot("head", rad(-5) * (-d / 0.1) if d < 0 else 0)
            tail(lift=rad(25) * (-d / 0.1) if d < 0 else 0, curl=rad(-5))
        frames.append(pose)
    return frames


# Facing the viewer: the whole rig turns -90deg about Z (forward -Y -> -X,
# toward the camera). The head leads the turn, the body follows. The app
# plays turn_front forwards to face the user and reversed to turn back.
FRONT_TURN = rad(-90)


def anim_turn_front():
    n = 7
    frames = []
    for f in range(n):
        u = f / (n - 1)

        def pose(u=u):
            body = smooth(u)
            head_lead = smooth(min(1.0, u * 1.6)) - body  # head ahead of the body
            rig.rotation_euler.z = FRONT_TURN * body
            rot("neck", 0, FRONT_TURN * 0.35 * head_lead)
            rot("head", 0, FRONT_TURN * 0.45 * head_lead)
            tail(sway=rad(6), t=u * 0.5)
        frames.append(pose)
    return frames


def anim_front():
    """Facing the viewer: breathing, a slow curious head tilt, tail sway."""
    n = 16
    frames = []
    for f in range(n):
        t = f / n

        def pose(t=t):
            rig.rotation_euler.z = FRONT_TURN
            breath = math.sin(2 * math.pi * t)
            rot("chest", rad(1.5) * breath)
            # head roll (local Z is the bone's forward axis): curious tilt
            rot("head", rad(2) * math.sin(2 * math.pi * t + 1.0), 0, rad(9) * math.sin(2 * math.pi * t))
            tail(sway=rad(9), t=t, wave=rad(3))
        frames.append(pose)
    return frames


ANIMS = {
    "idle": anim_idle, "walk_right": anim_walk, "run_right": anim_run,
    "jump": anim_jump, "fall": anim_fall, "land": anim_land, "play": anim_play,
    "sit": anim_sit, "sleep": anim_sleep, "dragged": anim_dragged, "react": anim_react,
    "turn_front": anim_turn_front, "front": anim_front,
}

# ---- scene ------------------------------------------------------------------
scene = bpy.context.scene
for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
    try:
        scene.render.engine = engine
        break
    except TypeError:
        continue
scene.render.resolution_x = scene.render.resolution_y = 640
scene.render.film_transparent = True
scene.render.image_settings.color_mode = "RGBA"
scene.view_settings.view_transform = "Standard"
world = bpy.data.worlds.new("W")
scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[1].default_value = 0.9
key = bpy.data.objects.new("key", bpy.data.lights.new("key", "SUN"))
key.data.energy = 3.5
key.rotation_euler = (rad(55), 0, rad(-60))
scene.collection.objects.link(key)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type = "ORTHO"
cam.data.ortho_scale = 2.6
cam.location = (-4, 0.0, 0.15)
cam.rotation_euler = (rad(90), 0, rad(-90))
scene.collection.objects.link(cam)
scene.camera = cam

# ---- render -----------------------------------------------------------------
_tex_node = next(n for n in cat.data.materials[0].node_tree.nodes if n.type == "TEX_IMAGE")
_open_eyes = _tex_node.image
_closed_eyes = bpy.data.images.load(EYES_CLOSED) if EYES_CLOSED else None

for state, make in ANIMS.items():
    if ONLY and state not in ONLY:
        continue
    _tex_node.image = _closed_eyes if (state == "sleep" and _closed_eyes) else _open_eyes
    d = OUT / state
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob("*.png"):
        old.unlink()
    for i, pose in enumerate(make()):
        reset_pose()
        pose()
        bpy.context.view_layer.update()
        scene.render.filepath = str(d / f"{state}_{i}.png")
        bpy.ops.render.render(write_still=True)
    print("RENDERED", state)
print("DONE")
