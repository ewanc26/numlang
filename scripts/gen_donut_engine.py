#!/usr/bin/env python3
"""Generate examples/donut_engine.num: a finite-frames orbit-lit torus
streaming the per-frame vertex protocol consumed by host/donut_host.c, which
is a faithful embed of the canonical renderer in doughnut.c (800x600,
U_STEPS=50, V_STEPS=30, R_MAJOR=2.0, R_MINOR=0.8, fov=500, camera_dist=5.0).

The canonical stream is doughnut.c's own float32 pipeline: every arithmetic
operation, assignment and constant folds to IEEE single precision exactly as
the C float expressions do on a flat-evaluation platform (FLT_EVAL_METHOD 0,
no FMA contraction), and sin/cos/sqrt are correctly rounded to float32 like
libm's sinf/cosf/sqrtf (doughnut.c uses cosf/sinf/sqrtf).  This generator
simulates that pipeline op-for-op:

  float u = (float)i / U_STEPS * 2.0f * M_PI;        (per-operation folding)
  float v = (float)j / V_STEPS * 2.0f * M_PI;
  torus base vertices/normals as in generate_torus();
  rotate_vector(pos/norm, angleX, angleY, angleZ)    (X, then Y, then Z)
  light_dir = light_pos - rot_pos, normalized; dist = sqrtf(|light_dir|^2)
  intensity = max(dot(rot_norm, light_dir), 0.08f) / (1.0f + 0.04f*dist)
  w = rot_pos.z + 5.0f
  px = (rot_pos.x / w) * 500.0f + 400.0f ; py = (rot_pos.y / w) * 500.0f + 300.0f

Frame n (0-indexed), exactly as doughnut.c does:
  angleX = angleY = 0.5 (fixed)
  angleZ += 0.003f                  (advanced AFTER each frame)
  light_angle += 0.025f            (advanced BEFORE each frame)
  light_pos = (cosf(la)*4.5f, sinf(la)*4.5f, sinf(la*0.7f)*2.5f)

Values print through numlangc's numeric print ("|", printf "%g\\n") of the
exact float32 value (held as its round-trip double literal), so the token
text is byte-identical to the canonical capture.

The C++ numlang compiler implements no control-flow opcodes yet (20/28/30/50
are deferred), so 1500 vertices per frame must be emitted unrolled. The
preferred in-language computation route (per-vertex FFI sin/cos/sqrt calls
plus unrolled arithmetic) is impractical on measured compile times: numlangc
emits Jacobian stack pushes per operation, and Apple clang compiles these
giant single-main programs superlinearly - a Phase-1 constants program of
58k statements took 21 s, and one with 14k FFI calls took 32 s. A computing
engine needs ~100+ stack statements and a sqrt call per vertex, i.e. ~200k
statements plus 1500 FFI calls per frame - minutes per frame. This
generator therefore emits a small finite-frames constants stream
(FRAMES_DEFAULT=3): every value is computed in Python by the float32
simulation above and printed at runtime through "|" ("%g\\n"), which
round-trips exactly. The host replays the finite stream forever, which is
the animation.

tests/fixtures/donut_canonical_v2_2f.txt vendors the canonical capture's
first 2 frames; regenerate it from a fresh canonical capture (built from
doughnut_logged.c with -ffp-contract=off) after any change.
"""

import argparse
import math
import pathlib
import struct
from decimal import Decimal, getcontext
from fractions import Fraction

ROOT = pathlib.Path(__file__).resolve().parent.parent

U_STEPS, V_STEPS = 50, 30
CAM_DIST, FOV = 5.0, 500.0
ANGLE_XY = 0.5
Z_STEP, LIGHT_STEP = 0.003, 0.025
FRAMES_DEFAULT = 3
VERTS_PER_FRAME = U_STEPS * V_STEPS
VALUES_PER_FRAME = 4 * VERTS_PER_FRAME
LINES_PER_FRAME = 2 + VALUES_PER_FRAME

PI = math.pi
getcontext().prec = 80


def f32(x):
    """Fold to IEEE single precision (round to nearest, ties to even)."""
    return struct.unpack("f", struct.pack("f", x))[0]


# float32-folded constants: C computes with 0.8f, 0.04f, ... exactly these
# folded values, not with the raw doubles.
K025 = f32(0.025)
K003 = f32(0.003)
K07 = f32(0.7)
K45 = f32(4.5)
K25 = f32(2.5)
K08 = f32(0.08)
K04 = f32(0.04)
K1E5 = f32(1e-5)
K08D = f32(0.8)
K2 = f32(2.0)


def _dec(x):
    if isinstance(x, Decimal):
        return x
    if isinstance(x, Fraction):
        return Decimal(x.numerator) / Decimal(x.denominator)
    return Decimal(x)


def _dec_sin(x):
    """Exact sin for |x| <= 7 (every angle this pipeline reaches)."""
    d = _dec(x)
    neg = d < 0
    if neg:
        d = -d
    assert d <= 7
    term = d
    total = d
    k = 1
    while True:
        term = -term * d * d / ((2 * k) * (2 * k + 1))
        total += term
        if term == 0 or abs(term) < Decimal(10) ** (-75):
            break
        k += 1
    return -total if neg else total


def _dec_cos(x):
    d = _dec(x)
    neg = d < 0
    if neg:
        d = -d
    assert d <= 7
    term = Decimal(1)
    total = Decimal(1)
    k = 1
    while True:
        term = -term * d * d / ((2 * k - 1) * (2 * k))
        total += term
        if term == 0 or abs(term) < Decimal(10) ** (-75):
            break
        k += 1
    return total


def _round32_exact(t):
    """Round the exact Decimal t to the nearest float32 (ties to even)."""
    t = _dec(t)
    c0 = f32(float(t))
    bits = struct.unpack("I", struct.pack("f", c0))[0]
    best = None
    for db in (-1, 0, 1):
        b = bits + db
        if b < 0 or b > 0xFFFFFFFF:
            continue
        c = struct.unpack("f", struct.pack("I", b))[0]
        err = abs(Fraction(t) - Fraction(c))
        if best is None or err < best[0] or (err == best[0] and (b & 1) == 0):
            best = (err, c)
    return best[1]


def cosf(x):
    """Correctly rounded float32 cos, matching libm cosf on the pipeline."""
    return _round32_exact(_dec_cos(Fraction(x)))


def sinf(x):
    """Correctly rounded float32 sin, matching libm sinf on the pipeline."""
    return _round32_exact(_dec_sin(Fraction(x)))


def sqrtf(x):
    """Correctly rounded float32 sqrt: the float whose square is closest to
    x (exact rational comparison), as hardware/libm sqrtf rounds."""
    if x <= 0.0:
        return f32(0.0 if x == 0.0 else x)
    approx = f32(math.sqrt(x))
    cands = set()
    bits = struct.unpack("I", struct.pack("f", approx))[0]
    for db in (-2, -1, 0, 1, 2):
        cands.add(struct.unpack("f", struct.pack("I", bits + db))[0])
    tgt = Fraction(x)
    best = None
    for c in cands:
        err = abs(tgt - Fraction(c) * Fraction(c))
        if best is None or err < best[0]:
            best = (err, c)
    return best[1]


def frame_values(az, la):
    """All 1500 (px, py, z, intensity) float32 tuples for one frame,
    mirroring doughnut.c's per-vertex pipeline op-for-op, folding after
    every operation and assignment as the C float expressions do."""
    caz, saz = cosf(az), sinf(az)
    lx = f32(cosf(la) * K45)
    ly = f32(sinf(la) * K45)
    lz = f32(sinf(f32(la * K07)) * K25)
    cax, sax = f32(math.cos(0.5)), f32(math.sin(0.5))
    cay, say = cax, sax
    out = []
    for i in range(U_STEPS):
        u = f32(f32(f32(f32(i) / 50.0) * K2) * PI)
        cu, su = cosf(u), sinf(u)
        for j in range(V_STEPS):
            v = f32(f32(f32(f32(j) / 30.0) * K2) * PI)
            cv, sv = cosf(v), sinf(v)
            rad = f32(K2 + f32(K08D * cv))
            bx = f32(rad * cu)
            by = f32(rad * su)
            bz = f32(K08D * sv)
            nx, ny, nz = f32(cv * cu), f32(cv * su), sv
            y1 = f32(f32(by * cax) - f32(bz * sax))
            z1 = f32(f32(by * sax) + f32(bz * cax))
            x2 = f32(f32(bx * cay) + f32(z1 * say))
            z2 = f32(f32(-bx * say) + f32(z1 * cay))
            rx = f32(f32(x2 * caz) - f32(y1 * saz))
            ry = f32(f32(x2 * saz) + f32(y1 * caz))
            ny1 = f32(f32(ny * cax) - f32(nz * sax))
            nz1 = f32(f32(ny * sax) + f32(nz * cax))
            nx2 = f32(f32(nx * cay) + f32(nz1 * say))
            nz2 = f32(f32(-nx * say) + f32(nz1 * cay))
            rnx = f32(f32(nx2 * caz) - f32(ny1 * saz))
            rny = f32(f32(nx2 * saz) + f32(ny1 * caz))
            dx, dy, dz = f32(lx - rx), f32(ly - ry), f32(lz - z2)
            dist = sqrtf(f32(f32(f32(dx * dx) + f32(dy * dy)) + f32(dz * dz)))
            if dist > K1E5:
                dx = f32(dx / dist)
                dy = f32(dy / dist)
                dz = f32(dz / dist)
            intensity = f32(f32(f32(rnx * dx) + f32(rny * dy)) + f32(nz2 * dz))
            if intensity < K08:
                intensity = K08
            intensity = f32(intensity / f32(1.0 + f32(K04 * dist)))
            w = f32(z2 + CAM_DIST)
            px = f32(f32(f32(rx / w) * FOV) + 400.0)
            py = f32(f32(f32(ry / w) * FOV) + 300.0)
            out.append((px, py, w, intensity))
    return out


def fmt(v: float) -> str:
    """Literal for float32 value v (held exactly as a double); numlang has
    no negative literals, so append the NEG opcode (25) for values < 0."""
    if v < 0.0:
        return "%s 25" % repr(-v)
    return repr(v)


def generate(frames: int) -> str:
    lines = [
        "# donut_engine.num - finite-frames orbit-lit torus (doughnut.c port)",
        "#",
        "# Byte-identical prefix of doughnut.c's canonical float32 vertex",
        "# stream (same frames, angles, formulas and %g number format).",
        "# Generated by scripts/gen_donut_engine.py --frames %d; do not edit." % frames,
        "# %d vertices per frame (i*30+j order): px, py, z, intensity lines."
        % VERTS_PER_FRAME,
        "#",
        "# Every value is the exact float32 result of doughnut.c's pipeline",
        "# (per-operation single-precision folding, folded constants and",
        "# correctly-rounded float32 sin/cos/sqrt); the host replays the",
        "# finite stream forever, which is the animation.",
        "#",
        "# Run:",
        "#   ./build/numlangc examples/donut_engine.num --run --cc cc \\",
        "#       | ./host/donut_host",
    ]
    push = lines.append
    az = 0.0
    la = 0.0
    for _ in range(frames):
        la = f32(la + K025)  # light advanced before the frame
        push('"F\\n"')
        for px, py, z, intensity in frame_values(az, la):
            for v in (px, py, z, intensity):
                push("%s |" % fmt(v))
        push('"S\\n"')
        az = f32(az + K003)  # angleZ advanced after the frame
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
