#!/usr/bin/env python3
"""Generate examples/donut_engine.num: a finite-frames orbit-lit torus
streaming the per-frame vertex protocol consumed by host/donut_host.c, which
is a faithful embed of the canonical renderer in doughnut.c (800x600,
U_STEPS=50, V_STEPS=30, R_MAJOR=2.0, R_MINOR=0.8, fov=500, camera_dist=5.0).

The engine's stream is byte-identical to the canonical sigi engine's for the
same frame indices: the arithmetic, constants, angles and print format below
mirror sigi's engine exactly, so bit-parity holds through the %g output.

Frame n (0-indexed), exactly as doughnut.c and the sigi engine do:
  angleX = angleY = 0.5 (fixed)
  angleZ = 0.003 * n                (advanced AFTER each frame)
  light_angle = 0.025 * (n + 1)      (advanced BEFORE each frame)
  light_pos = (cos(la)*4.5, sin(la)*4.5, sin(la*0.7)*2.5)

Per vertex (i in 0..49, j in 0..29, emitted in i*30+j order) the program
prints px, py, z, intensity, each with numlangc's numeric print ("|",
"%g\\n"), one value per line:

  rot_pos, rot_norm = rotate_vector(pos/norm, angleX, angleY, angleZ) (X, then Y, then Z)
  light_dir = light_pos - rot_pos, normalized; dist = |light_dir|
  intensity = max(dot(rot_norm, light_dir), 0.08) / (1 + 0.04*dist)
  z = rot_pos.z + 5.0
  px = (rot_pos.x / z) * 500 + 400 ; py = (rot_pos.y / z) * 500 + 300

Mirroring notes (deviations break byte-parity with the canonical):
- The rotation around BOTH the X and the Y axes uses cos(0.5)/sin(0.5)
  rounded to 12 decimals, because the sigi engine stores one rounded pair
  (CAXY/SAXY) in variables shared by the X and Y stages. Only the Z-stage
  trig is evaluated from the live angleZ.
- U/V angles are index-based, not accumulated: cu = cos(i*U_STEP) with
  U_STEP = round(2*pi/50, 12); likewise V_STEP = round(2*pi/30, 12).
- angleZ and light_angle accumulate by repeated += 0.003 / += 0.025 with
  double drift included (light advanced before the frame, angleZ after).
- intensity is ((((rnx*dx + rny*dy) + rnz*dz)), floored at 0.08) divided by
  (1.0 + dist*0.04); numlang has no negative literals, so negative values
  are printed via the NEG opcode (25).
- 800x600 rasterization, Lambert shading and the purple-pink palette live in
  the host, matching doughnut.c exactly.

The C++ numlang compiler implements no control-flow opcodes yet (20/28/30/50
are deferred), so 1500 vertices per frame must be emitted unrolled. The
preferred in-language computation route (per-vertex FFI sin/cos/sqrt calls
plus unrolled arithmetic) is impractical here on measured compile times:
numlangc emits Jacobian stack pushes per operation, and Apple clang compiles
these giant single-main programs superlinearly - a Phase-1 constants program
of 58k statements took 21 s, and one with 14k FFI calls took 32 s. A
computing engine needs ~100+ stack statements and a sqrt call per vertex,
i.e. ~200k statements plus 1500 FFI calls per frame - minutes per frame.
Per the harmonization guidance this generator therefore falls back to a
small finite-frames constants stream (FRAMES=3 default): every value is
computed in Python floats (IEEE double, same arithmetic order and libm as
the sigi engine) and printed at runtime through "|" (printf "%g\\n"), which
bit-round-trips exactly. The host replays the finite stream forever, giving
the animation.

tests/fixtures/donut_canonical_v2_2f.txt vendors the canonical capture's
first 2 frames; regenerate it from a fresh canonical capture after any
change.
"""

import argparse
import math
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

U_STEPS, V_STEPS = 50, 30
R_MAJOR, R_MINOR = 2.0, 0.8
CAM_DIST, FOV = 5.0, 500.0
ANGLE_XY = 0.5
Z_STEP, LIGHT_STEP = 0.003, 0.025
FRAMES_DEFAULT = 3
# The canonical sigi engine stores these rounded-to-12 constants and shares
# them across the X and Y rotation stages.
CAXY = float(repr(round(math.cos(ANGLE_XY), 12)))
SAXY = float(repr(round(math.sin(ANGLE_XY), 12)))
U_STEP = float(repr(round(2 * math.pi / U_STEPS, 12)))
V_STEP = float(repr(round(2 * math.pi / V_STEPS, 12)))
VERTS_PER_FRAME = U_STEPS * V_STEPS
VALUES_PER_FRAME = 4 * VERTS_PER_FRAME
LINES_PER_FRAME = 2 + VALUES_PER_FRAME


def rotate(x, y, z, caz, saz):
    """doughnut.c rotate_vector (X, then Y, then Z); the X/Y stages use the
    engine's rounded CAXY/SAXY pair, exactly as the canonical engine does."""
    y1 = y * CAXY - z * SAXY
    z1 = y * SAXY + z * CAXY
    x1 = x
    x2 = x1 * CAXY + z1 * SAXY
    z2 = -x1 * SAXY + z1 * CAXY
    y2 = y1
    x3 = x2 * caz - y2 * saz
    y3 = x2 * saz + y2 * caz
    z3 = z2
    return x3, y3, z3


def frame_values(az, la):
    """All 1500 (px, py, z, intensity) tuples for one frame."""
    caz, saz = math.cos(az), math.sin(az)
    lx = math.cos(la) * 4.5
    ly = math.sin(la) * 4.5
    lz = math.sin(la * 0.7) * 2.5
    out = []
    for i in range(U_STEPS):
        cu = math.cos(i * U_STEP)
        su = math.sin(i * U_STEP)
        for j in range(V_STEPS):
            cv = math.cos(j * V_STEP)
            sv = math.sin(j * V_STEP)
            rad = R_MAJOR + R_MINOR * cv
            rx, ry, rz = rotate(rad * cu, rad * su, R_MINOR * sv, caz, saz)
            rnx, rny, rnz = rotate(cv * cu, cv * su, sv, caz, saz)
            dx, dy, dz = lx - rx, ly - ry, lz - rz
            dist = math.sqrt(dx * dx + dy * dy + dz * dz)
            dx /= dist
            dy /= dist
            dz /= dist
            intensity = (rnx * dx + rny * dy) + rnz * dz
            if intensity < 0.08:
                intensity = 0.08
            intensity = intensity / (1.0 + dist * 0.04)
            w = rz + CAM_DIST
            px = (rx / w) * FOV + 400.0
            py = (ry / w) * FOV + 300.0
            out.append((px, py, w, intensity))
    return out


def fmt(v: float) -> str:
    """Literal for value v; numlang has no negative literals, so append the
    NEG opcode (25) for values < 0."""
    if v < 0.0:
        return "%s 25" % repr(-v)
    return repr(v)


def generate(frames: int) -> str:
    lines = [
        "# donut_engine.num - finite-frames orbit-lit torus (doughnut.c port)",
        "#",
        "# Byte-identical prefix of the canonical sigi engine's vertex stream",
        "# (same frames, angles, formulas and %g number format).",
        "# Generated by scripts/gen_donut_engine.py --frames %d; do not edit." % frames,
        "# %d vertices per frame (i*30+j order): px, py, z, intensity lines."
        % VERTS_PER_FRAME,
        "#",
        "# numlangc has no loop opcodes yet, so every frame is unrolled; the host",
        "# replays the finite stream forever, which is the animation.",
        "#",
        "# Run:",
        "#   ./build/numlangc examples/donut_engine.num --run --cc cc \\",
        "#       | ./host/donut_host",
    ]
    push = lines.append
    az = 0.0
    la = 0.0
    for _ in range(frames):
        la += LIGHT_STEP  # light advanced before the frame
        push('"F\\n"')
        for px, py, z, intensity in frame_values(az, la):
            for v in (px, py, z, intensity):
                push("%s |" % fmt(v))
        push('"S\\n"')
        az += Z_STEP  # angleZ advanced after the frame
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--frames", type=int, default=FRAMES_DEFAULT, help="frame count"
    )
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=ROOT / "examples" / "donut_engine.num",
        help="output .num path",
    )
    args = parser.parse_args()
    if args.frames < 1:
        parser.error("--frames must be >= 1")
    text = generate(args.frames)
    args.output.write_text(text, encoding="utf-8")
    print(
        "wrote {}: {} lines, {} frames, {} vertices/frame ({} lines/frame)".format(
            args.output,
            len(text.splitlines()),
            args.frames,
            VERTS_PER_FRAME,
            LINES_PER_FRAME,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
