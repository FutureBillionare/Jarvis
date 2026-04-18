"""Standalone text-to-CAD server — Claude + OpenSCAD WASM, no Docker needed."""
import base64
import json
import webbrowser
from pathlib import Path
from typing import Optional

import anthropic
from fastapi import FastAPI, Form, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE = Path(__file__).parent
WASM_DIR = BASE / "cadam" / "src" / "vendor" / "openscad-wasm"
UI_FILE = BASE / "cad_ui.html"
CONFIG = json.loads((BASE / "jarvis_config.json").read_text())

client = anthropic.Anthropic(api_key=CONFIG["api_key"])

app = FastAPI(title="HUBERT CAD")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)
app.mount("/wasm", StaticFiles(directory=str(WASM_DIR)), name="wasm")

SYSTEM = """You are an elite parametric CAD engineer, aerospace structures expert, and computational geometry specialist who writes OpenSCAD code. Before generating any code you MUST research the object, then output your findings.

═══ MANDATORY OUTPUT FORMAT ═══

Your response MUST follow this exact format — no exceptions:

RESEARCH:
[Write 3-6 lines covering: what this object really is, real-world dimensions/standards, key structural/functional constraints, sub-components required, and manufacturing approach. Be specific — cite actual mm sizes, bolt patterns, battery cell dimensions, etc.]
---
[raw OpenSCAD code — no markdown fences, starts immediately after the --- line]

═══ RESEARCH PHASE ═══

Step 0 — RESEARCH the object before anything else:
  • What does this object actually look like in the real world? What are its defining features?
  • What are the standard engineering dimensions / weight classes / configurations?
  • What structural constraints govern its shape? (load paths, stress concentrations, fatigue)
  • What manufacturing method would be used? (FDM, SLA, CNC, injection mold)
  • Are there sub-components? (motor mounts, battery bays, arm joints, fastening patterns)

  DRONE / UAV KNOWLEDGE BASE (apply when relevant):
  • Quadcopter classes: Micro (<100mm), Whoop (75–115mm), 3" (140mm), 5" racing (210–250mm), 7" long-range (310mm), X8 heavy lift
  • Frame styles: X-frame (equal arms, racing), Stretch-X (longer front/back), H-frame (parallel rails), True-X, deadcat, coaxial
  • Motor sizing: 1103–1408 (micros), 2204–2306 (3"), 2306–2407 (5" racing), 2812–4014 (7"+)
  • 3V (single cell) battery: ~40×20×10mm (300mAh); 3S 1000mAh: ~72×35×23mm; 4S 1500mAh: ~95×35×27mm
  • Brushless motor mount: 4 M3 bolts on 16mm cross or 19mm cross pattern; motor OD 22–28mm typical
  • Flight controller stack: 30.5mm×30.5mm M3 pattern (standard), 20mm×20mm (micro)
  • Structural: arm thickness ≥5mm FDM for 5" props; use ribs/gussets at hub-arm junction; wall ≥2.5mm
  • Propeller clearance: arm tip to prop center = prop_radius + 5mm minimum

═══ RESEARCH PHASE (silent, before writing any code) ═══

Step 0 — RESEARCH the object deeply:
  • What does this object actually look like in the real world? What are its defining features?
  • What are the standard engineering dimensions / weight classes / configurations?
  • What structural constraints govern its shape? (load paths, stress concentrations, fatigue)
  • What manufacturing method would be used? (FDM, SLA, CNC, injection mold)
  • Are there sub-components? (motor mounts, battery bays, arm joints, fastening patterns)

  DRONE / UAV KNOWLEDGE BASE (apply when relevant):
  • Quadcopter classes: Micro (<100mm), Whoop (75–115mm), 3" (140mm), 5" racing (210–250mm), 7" long-range (310mm), X8 heavy lift
  • Frame styles: X-frame (equal arms, racing), Stretch-X (longer front/back), H-frame (parallel rails), True-X, deadcat, coaxial
  • Motor sizing: 1103–1408 (micros), 2204–2306 (3"), 2306–2407 (5" racing), 2812–4014 (7"+)
  • 3V (single cell) battery: ~40×20×10mm (300mAh); 3S 1000mAh: ~72×35×23mm; 4S 1500mAh: ~95×35×27mm
  • Brushless motor mount: 4 M3 bolts on 16mm cross or 19mm cross pattern; motor OD 22–28mm typical
  • Flight controller stack: 30.5mm×30.5mm M3 pattern (standard), 20mm×20mm (micro)
  • Structural: arm thickness ≥5mm FDM for 5" props; use ribs/gussets at hub-arm junction; wall ≥2.5mm
  • Propeller clearance: arm tip to prop center = prop_radius + 5mm minimum

  ROBOT / MECHANICAL ARM KNOWLEDGE BASE:
  • Link lengths scale with payload; servo horn radius = torque/force; bearing seats = servo OD + 0.3mm clearance
  • Joint styles: revolute (cylinder + shaft), prismatic (dovetail slide), spherical (ball socket)

Step 1 — CLASSIFY the request:
  • Drone/UAV frame? (quadcopter, hexacopter, racing, freestyle, long-range, FPV)
  • Mechanical part? (gear, bearing, bracket, fastener, shaft, flange, cam, linkage, spring, thread)
  • Architectural element? (arch, vault, column, cornice, truss, facade panel, dome, spire)
  • Organic / sculptural? (leaf, wave, helix, voronoi shell, gyroid, twisted prism)
  • Consumer product? (enclosure, grip, knob, lens mount, phone stand, snap-fit clip)
  • Structural profile? (I-beam, C-channel, T-slot extrusion, angle iron, tube frame)
  • Assembled system? (multiple parts with tolerances, joints, fastening points)

Step 2 — SELECT the best geometry strategy:
  • Simple revolve → rotate_extrude() (rings, knobs, pulleys, bottles, nozzles)
  • Profile sweep → linear_extrude() with optional twist/scale (rails, ramps, screw bodies)
  • Polygon mesh → polyhedron() (prisms, diamonds, irregular solids)
  • CSG assembly → union() / difference() / intersection() (most mechanical parts)
  • Minkowski sum → minkowski() (rounded boxes, inflated shapes, fillets)
  • Hull → hull() (organic transitions, blobby forms, smooth joints)
  • Parametric loops → for() + hull/union (gears, stars, lattices, spirals)
  • Surface deformation → linear_extrude() with $fn polygon approximation

Step 3 — DETERMINE realistic dimensions:
  • M3 screw: ∅3mm. Standard USB port: 12×4.5mm. AA battery: ∅14.5×50.5mm.
  • Human hand grip: ∅35–45mm. Wall thickness: ≥1.5mm for FDM printing.
  • Use real engineering standards when the object is a known part.

Step 4 — PLAN features:
  • Holes, counterbores, chamfers → difference()
  • Ribs, gussets, bosses → union()
  • Threads → use a helical profile via linear_extrude+polygon or note "add thread module"
  • Snap fits → thin cantilever beam geometry with deflection gap
  • Knurling → rotated array of small cuts via for() + difference()

Step 5 — ORTHOGRAPHIC DRAWING INTERPRETATION (if images are attached):
  • Identify which views are present: Front (F), Top (T), Side/Right (S)
  • Extract key dimensions from dimension lines, title block, or scale
  • Front + Top views → use linear_extrude of the front profile, then intersect with
    linear_extrude of the top profile rotated 90° around X
  • Circular features visible in one view → cylinders in difference()
  • Hidden lines (dashed) → internal features, use difference()
  • Reconstruct 3D by computing the intersection of extruded silhouettes from each view

═══ ADVANCED OPENSCAD TECHNIQUES ═══

GEARS:
module gear(teeth, module_m, thickness, bore) {
  pitch_r = teeth * module_m / 2;
  difference() {
    linear_extrude(thickness)
      polygon([for(i=[0:teeth-1], j=[0:1])
        let(a = (i + j*0.5) * 360/teeth,
            r = j==0 ? pitch_r*1.05 : pitch_r*0.85)
        [r*cos(a), r*sin(a)]]);
    cylinder(h=thickness+1, r=bore/2, center=true);
  }
}

HELIX / SPRING:
module helix(r, pitch, turns, wire_r) {
  union() [for(i=[0:$fn-1])
    let(a=i*360*turns/$fn, a2=(i+1)*360*turns/$fn,
        z=i*pitch*turns/$fn, z2=(i+1)*pitch*turns/$fn)
    hull() {
      translate([r*cos(a), r*sin(a), z]) sphere(r=wire_r);
      translate([r*cos(a2), r*sin(a2), z2]) sphere(r=wire_r);
    }];
}

VORONOI-STYLE LATTICE: Use minkowski() with small sphere on thin walls
ROUNDED EVERYTHING: minkowski() { shape(); sphere(r=fillet, $fn=16); }
SNAP FIT: thin beam + undercut geometry via difference()
THREADS: use cylinder with slight taper + comment "add thread library for production"

═══ OUTPUT RULES ═══
- ALWAYS start with "RESEARCH:" section then "---" separator then OpenSCAD code. No exceptions.
- If the prompt contains an [EXACT DIMENSIONS REQUIRED] block, you MUST define w/d/h at the top of the file using exactly those values (in mm) and scale ALL geometry to fit within that bounding box. No approximations.
- After the "---" separator: raw .scad code only — no markdown fences, no prose.
- Define ALL parameters as named variables at the top with inline units comment.
- Use $fn=64 on any curved surface; $fn=6 for hex profiles.
- Comment the top line with: // <shape name> | strategy: <geometry approach>
- NEVER default to a featureless cube or sphere when a more accurate shape exists.
- For MODIFY requests: build on the last SCAD in conversation history — add via union(), subtract via difference(), or rewrite only the affected module.
- For ORTHOGRAPHIC DRAWINGS: always comment which views you identified and how you reconstructed the 3D form.
- For DRONES: always include motor mounts with bolt circle holes, arm taper, battery bay, FC stack mounting pattern, and weight-relief cutouts. NEVER output a flat box for a drone frame.
- Output must be immediately compilable OpenSCAD — no pseudocode, no placeholders."""

# Supported image MIME types for Claude vision
IMAGE_MIMES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


class GenerateRequest(BaseModel):
    prompt: str
    history: list[dict] = []


class GenerateResponse(BaseModel):
    scad_code: str
    rationale: str = ""


def _strip_fences(code: str) -> str:
    if code.startswith("```"):
        lines = code.splitlines()
        code = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return code.strip()


def _parse_response(raw: str) -> tuple[str, str]:
    """Split 'RESEARCH:\\n...\\n---\\nscad_code' into (scad, rationale)."""
    if "---" in raw and raw.lstrip().startswith("RESEARCH:"):
        parts = raw.split("---", 1)
        rationale = parts[0].replace("RESEARCH:", "").strip()
        scad = _strip_fences(parts[1].strip())
        return scad, rationale
    # No structured format — treat whole response as SCAD
    return _strip_fences(raw), ""


_FALLBACK_TEMPLATES = {
    # ── PRIMITIVES ──────────────────────────────────────────────────────────────
    "sphere": "// Sphere | strategy: primitive\nd = 50; // mm\nsphere(d=d, $fn=64);",
    "cylinder": "// Cylinder | strategy: primitive\nh = 60; r = 20; // mm\ncylinder(h=h, r=r, center=true, $fn=64);",
    "cone": "// Cone | strategy: tapered cylinder\nh=60; r1=25; r2=0;\ncylinder(h=h, r1=r1, r2=r2, center=true, $fn=64);",
    "box": "// Box | strategy: cube primitive\nw=80; d=60; h=40;\ncube([w,d,h], center=true);",
    "cube": "// Cube | strategy: cube primitive\nsize=50;\ncube([size,size,size], center=true);",

    # ── RINGS & TOROIDS ─────────────────────────────────────────────────────────
    "torus": "// Torus | strategy: rotate_extrude\nR=35; r=10;\nrotate_extrude(angle=360, $fn=64)\n  translate([R,0]) circle(r=r, $fn=32);",
    "ring": "// Ring | strategy: rotate_extrude\nR=30; wall=5;\nrotate_extrude($fn=64)\n  translate([R,0]) circle(r=wall/2, $fn=24);",
    "washer": "// Washer | strategy: difference of cylinders\nod=30; id=16; h=3;\ndifference(){\n  cylinder(h=h,r=od/2,center=true,$fn=64);\n  cylinder(h=h+1,r=id/2,center=true,$fn=64);\n}",

    # ── TUBES & PIPES ────────────────────────────────────────────────────────────
    "tube": "// Tube | strategy: difference of cylinders\nod=40; id=30; h=80;\ndifference(){\n  cylinder(h=h,r=od/2,center=true,$fn=64);\n  cylinder(h=h+2,r=id/2,center=true,$fn=64);\n}",
    "pipe": "// Pipe | strategy: difference of cylinders\nod=25; wall=2.5; h=120;\ndifference(){\n  cylinder(h=h,r=od/2,center=true,$fn=64);\n  cylinder(h=h+2,r=(od/2-wall),center=true,$fn=64);\n}",

    # ── PYRAMIDS & PRISMS ────────────────────────────────────────────────────────
    "pyramid": "// Pyramid | strategy: linear_extrude with scale=0\ns=50; h=60;\nlinear_extrude(height=h, scale=0)\n  square([s,s], center=true);",
    "prism": "// Triangular Prism | strategy: linear_extrude polygon\nh=60; w=40;\nlinear_extrude(h)\n  polygon([[0,0],[w,0],[w/2,w*0.866]]);",
    "hexprism": "// Hex Prism | strategy: linear_extrude polygon\nflats=30; h=20;\nlinear_extrude(h, center=true)\n  circle(r=flats/cos(30), $fn=6);",
    "octahedron": "// Octahedron | strategy: hull of spheres at face centers\nr=25;\nhull(){\n  for(v=[[r,0,0],[-r,0,0],[0,r,0],[0,-r,0],[0,0,r],[0,0,-r]])\n    translate(v) sphere(2, $fn=8);\n}",

    # ── STARS & POLYGONS ─────────────────────────────────────────────────────────
    "star": "// Star | strategy: linear_extrude of star polygon\nn=5; r1=25; r2=12; h=8;\nlinear_extrude(h)\n  polygon([for(i=[0:2*n-1])\n    let(a=i*180/n, r=i%2==0?r1:r2)\n    [r*cos(a), r*sin(a)]]);",
    "gear": "// Spur Gear | strategy: parametric tooth polygon\nteeth=18; m=2; h=10; bore=6;\npitch_r=teeth*m/2; add_r=pitch_r+m; ded_r=pitch_r-1.25*m;\ndifference(){\n  linear_extrude(h)\n    polygon([for(i=[0:teeth-1], j=[0:3])\n      let(a=(i+j/4)*360/teeth,\n          r=j==0||j==3 ? ded_r : j==1 ? add_r*1.0 : add_r)\n      [r*cos(a), r*sin(a)]]);\n  cylinder(h=h+1, r=bore/2, center=false, $fn=32);\n}",

    # ── SPRINGS & HELICES ────────────────────────────────────────────────────────
    "spring": "// Compression Spring | strategy: hull-chained helix\ncoil_r=15; wire_r=2; pitch=8; turns=6;\n$fn=32;\nunion() [for(i=[0:$fn*turns-1])\n  let(a=i*360/$fn, a2=(i+1)*360/$fn,\n      z=i*pitch*turns/($fn*turns), z2=(i+1)*pitch*turns/($fn*turns))\n  hull(){\n    translate([coil_r*cos(a), coil_r*sin(a), z]) sphere(r=wire_r);\n    translate([coil_r*cos(a2), coil_r*sin(a2), z2]) sphere(r=wire_r);\n  }];",
    "helix": "// Helix | strategy: hull-chained sphere chain\nR=20; wire_r=3; pitch=10; turns=4;\n$fn=48;\nunion() [for(i=[0:$fn*turns-1])\n  let(a=i*360/$fn, a2=(i+1)*360/$fn,\n      z=i*pitch*turns/($fn*turns), z2=(i+1)*pitch*turns/($fn*turns))\n  hull(){\n    translate([R*cos(a), R*sin(a), z]) sphere(r=wire_r);\n    translate([R*cos(a2), R*sin(a2), z2]) sphere(r=wire_r);\n  }];",

    # ── MECHANICAL PARTS ─────────────────────────────────────────────────────────
    "bolt": "// Hex Bolt | strategy: hex prism + cylinder shaft\ndia=8; head_h=5; shaft_l=30;\nunion(){\n  linear_extrude(head_h)\n    circle(r=dia*0.9/cos(30), $fn=6);\n  cylinder(h=shaft_l, r=dia/2, $fn=32);\n}",
    "nut": "// Hex Nut | strategy: difference hex prism - cylinder\ndia=8; h=6;\ndifference(){\n  linear_extrude(h)\n    circle(r=dia*0.9/cos(30), $fn=6);\n  cylinder(h=h+1, r=dia/2, center=false, $fn=32);\n}",
    "bracket": "// L-Bracket | strategy: union of two extruded rectangles\nw=40; d=40; h=5; wall=4;\nunion(){\n  cube([w, wall, h]);\n  cube([wall, d, h]);\n}",
    "flange": "// Flanged Hub | strategy: difference of cylinders with bolt circle\nod=80; id=20; hub_h=25; flange_h=8; bolt_r=30; bolt_d=6; n_bolts=6;\ndifference(){\n  union(){\n    cylinder(h=hub_h, r=od*0.3, $fn=64);\n    cylinder(h=flange_h, r=od/2, $fn=64);\n  }\n  cylinder(h=hub_h+1, r=id/2, $fn=32);\n  for(i=[0:n_bolts-1])\n    rotate([0,0,i*360/n_bolts])\n      translate([bolt_r,0,-1])\n        cylinder(h=flange_h+2, r=bolt_d/2, $fn=24);\n}",
    "shaft": "// Keyed Shaft | strategy: cylinder with keyway difference\ndia=20; l=80; key_w=6; key_d=3;\ndifference(){\n  cylinder(h=l, r=dia/2, $fn=64);\n  translate([dia/2-key_d, -key_w/2, -1])\n    cube([key_d+1, key_w, l+2]);\n}",
    "bearing": "// Ball Bearing (outer ring) | strategy: rotate_extrude + inner cylinder\nOD=52; ID=25; W=15; track_r=4;\ndifference(){\n  cylinder(h=W, r=OD/2, center=true, $fn=64);\n  cylinder(h=W+1, r=ID/2, center=true, $fn=64);\n  rotate_extrude($fn=64)\n    translate([(OD+ID)/4, 0]) circle(r=track_r, $fn=32);\n}",
    "channel": "// C-Channel | strategy: linear_extrude profile polygon\nw=40; h=30; t=3; l=100;\nlinear_extrude(l)\n  polygon([[0,0],[w,0],[w,t],[t,t],[t,h-t],[w,h-t],[w,h],[0,h]]);",
    "ibeam": "// I-Beam | strategy: linear_extrude H-profile\nbf=60; d=80; tf=6; tw=4; l=200;\nlinear_extrude(l, center=true)\n  union(){\n    square([bf, tf], center=true);\n    translate([0, (d-tf)/2]) square([bf, tf], center=true);\n    translate([0, d/2-tf]) square([tw, d-2*tf], center=false)\n      translate([-tw/2, -(d/2-tf)]);\n  }",

    # ── ARCHITECTURAL ────────────────────────────────────────────────────────────
    "arch": "// Arch | strategy: difference of rotate_extrude half-circle\nspan=100; rise=60; thickness=10; depth=20;\ndifference(){\n  translate([0,0,0]) rotate([90,0,0])\n    rotate_extrude(angle=180, $fn=64)\n      translate([span/2,0]) square([thickness, depth]);\n  translate([-span/2-thickness,-depth-1,-1])\n    cube([span+2*thickness, depth+2, rise]);\n}",
    "dome": "// Dome | strategy: intersection of sphere and half-space\nr=50; wall=4;\ndifference(){\n  intersection(){\n    sphere(r=r, $fn=64);\n    translate([0,0,-1]) cylinder(h=r+1, r=r+1);\n  }\n  intersection(){\n    sphere(r=r-wall, $fn=64);\n    translate([0,0,-1]) cylinder(h=r+1, r=r+1);\n  }\n}",
    "column": "// Doric Column | strategy: linear_extrude + taper\nbase_r=25; top_r=20; h=120; flutes=20;\ndifference(){\n  cylinder(h=h, r1=base_r, r2=top_r, $fn=64);\n  for(i=[0:flutes-1])\n    rotate([0,0,i*360/flutes])\n      translate([base_r*0.85,0,0])\n        cylinder(h=h+1, r=3, $fn=16);\n}",

    # ── ORGANIC / SCULPTURAL ─────────────────────────────────────────────────────
    "leaf": "// Leaf | strategy: linear_extrude tapered polygon\nl=80; w=30; h=4;\nlinear_extrude(h, center=true, scale=[0.01, 0.01])\n  scale([l/2, w/2])\n    circle($fn=32);",
    "wave": "// Wave Surface | strategy: polyhedron from height map\nn=20; size=100; amp=15; freq=2;\npolyhedron(\n  points=[for(j=[0:n], i=[0:n])\n    [i*size/n-size/2,\n     j*size/n-size/2,\n     amp*sin(freq*360*i/n)*cos(freq*360*j/n)]],\n  faces=[for(j=[0:n-1], i=[0:n-1])\n    let(b=j*(n+1)+i)\n    each [[b,b+1,b+n+2,b+n+1]]]\n);",
    "spiral": "// Spiral Ramp | strategy: linear_extrude with twist\nouter_r=40; inner_r=20; h=50; twist_deg=720;\nlinear_extrude(h, twist=twist_deg, $fn=64)\n  difference(){\n    circle(r=outer_r);\n    circle(r=inner_r);\n  }",
    "twisted": "// Twisted Prism | strategy: linear_extrude with twist\nsides=6; r=25; h=80; twist=180;\nlinear_extrude(h, twist=twist, $fn=sides)\n  circle(r=r, $fn=sides);",

    # ── ELECTRONICS / PRODUCT ────────────────────────────────────────────────────
    "enclosure": "// Electronics Enclosure | strategy: shell via minkowski + difference\nw=80; d=60; h=30; wall=2.5; fillet=3;\nminkowski(){\n  cube([w-2*fillet, d-2*fillet, h/2], center=true);\n  cylinder(r=fillet, h=h/2, center=true, $fn=24);\n}",
    "standoff": "// PCB Standoff | strategy: cylinder with threaded hole\nod=6; id=3; h=10;\ndifference(){\n  cylinder(h=h, r=od/2, $fn=32);\n  cylinder(h=h+1, r=id/2, $fn=32);\n}",
    "knob": "// Knurled Knob | strategy: cylinder with rotated cuts\ndia=35; h=20; bore=6; n_cuts=24;\ndifference(){\n  cylinder(h=h, r=dia/2, $fn=64);\n  cylinder(h=h+1, r=bore/2, $fn=32);\n  for(i=[0:n_cuts-1])\n    rotate([0,0,i*360/n_cuts])\n      translate([dia/2*0.85,0,h/2])\n        rotate([0,20,0])\n          cylinder(h=h*1.5, r=2, center=true, $fn=12);\n}",

    # ── DRONES / UAV ─────────────────────────────────────────────────────────
    "drone": (
        '// Quadcopter X-Frame 5" 250mm | strategy: CSG assembly — arms, hub, motor mounts, battery bay\n'
        'wb=250; arm_w=14; arm_h=6; hub_r=38; hub_h=10;\n'
        'arm_len=wb*0.707/2-hub_r; motor_od=24; motor_h=9;\n'
        'batt_w=35; batt_d=65; batt_h=20; wall=2.5; fc=30.5; sr=1.5;\n'
        'module mm(){\n'
        '  difference(){\n'
        '    cylinder(h=motor_h,r=motor_od/2,$fn=32);\n'
        '    cylinder(h=motor_h+1,r=(motor_od-5)/2,$fn=32);\n'
        '    for(i=[0:3])rotate([0,0,i*90])translate([motor_od/2*0.62,0,-1])cylinder(h=motor_h+2,r=sr,$fn=16);\n'
        '  }\n'
        '}\n'
        'module arm(){\n'
        '  hull(){\n'
        '    cube([2,arm_w,arm_h],center=true);\n'
        '    translate([arm_len,0,0])cube([2,arm_w*0.65,arm_h],center=true);\n'
        '  }\n'
        '}\n'
        'union(){\n'
        '  difference(){\n'
        '    cylinder(h=hub_h,r=hub_r,center=true,$fn=64);\n'
        '    translate([0,0,wall])cube([batt_w,batt_d,batt_h],center=true);\n'
        '    for(i=[0:3])rotate([0,0,i*90+45])translate([fc/2,fc/2,0])cylinder(h=hub_h+2,r=sr,center=true,$fn=16);\n'
        '    for(i=[0:3])rotate([0,0,i*90])translate([hub_r*0.62,0,0])cylinder(h=hub_h+2,r=8,center=true,$fn=24);\n'
        '  }\n'
        '  for(i=[0:3])rotate([0,0,i*90+45])translate([hub_r,0,0])arm();\n'
        '  for(i=[0:3])rotate([0,0,i*90+45])translate([hub_r+arm_len,0,arm_h/2])mm();\n'
        '}'
    ),
    "quadcopter": (
        '// Quadcopter X-Frame 5" 250mm | strategy: CSG assembly — arms, hub, motor mounts, battery bay\n'
        'wb=250; arm_w=14; arm_h=6; hub_r=38; hub_h=10;\n'
        'arm_len=wb*0.707/2-hub_r; motor_od=24; motor_h=9;\n'
        'batt_w=35; batt_d=65; batt_h=20; wall=2.5; fc=30.5; sr=1.5;\n'
        'module mm(){\n'
        '  difference(){\n'
        '    cylinder(h=motor_h,r=motor_od/2,$fn=32);\n'
        '    cylinder(h=motor_h+1,r=(motor_od-5)/2,$fn=32);\n'
        '    for(i=[0:3])rotate([0,0,i*90])translate([motor_od/2*0.62,0,-1])cylinder(h=motor_h+2,r=sr,$fn=16);\n'
        '  }\n'
        '}\n'
        'module arm(){\n'
        '  hull(){\n'
        '    cube([2,arm_w,arm_h],center=true);\n'
        '    translate([arm_len,0,0])cube([2,arm_w*0.65,arm_h],center=true);\n'
        '  }\n'
        '}\n'
        'union(){\n'
        '  difference(){\n'
        '    cylinder(h=hub_h,r=hub_r,center=true,$fn=64);\n'
        '    translate([0,0,wall])cube([batt_w,batt_d,batt_h],center=true);\n'
        '    for(i=[0:3])rotate([0,0,i*90+45])translate([fc/2,fc/2,0])cylinder(h=hub_h+2,r=sr,center=true,$fn=16);\n'
        '    for(i=[0:3])rotate([0,0,i*90])translate([hub_r*0.62,0,0])cylinder(h=hub_h+2,r=8,center=true,$fn=24);\n'
        '  }\n'
        '  for(i=[0:3])rotate([0,0,i*90+45])translate([hub_r,0,0])arm();\n'
        '  for(i=[0:3])rotate([0,0,i*90+45])translate([hub_r+arm_len,0,arm_h/2])mm();\n'
        '}'
    ),
    "hexacopter": (
        '// Hexacopter flat-hex frame | strategy: CSG 6-arm radial assembly\n'
        'hub_r=45; arm_len=120; arm_w=14; arm_h=7; hub_h=12;\n'
        'motor_od=28; motor_h=10; sr=1.5;\n'
        'module mm(){\n'
        '  difference(){\n'
        '    cylinder(h=motor_h,r=motor_od/2,$fn=32);\n'
        '    cylinder(h=motor_h+1,r=(motor_od-5)/2,$fn=32);\n'
        '    for(i=[0:3])rotate([0,0,i*90])translate([motor_od/2*0.62,0,-1])cylinder(h=motor_h+2,r=sr,$fn=16);\n'
        '  }\n'
        '}\n'
        'module arm(){\n'
        '  hull(){\n'
        '    cube([2,arm_w,arm_h],center=true);\n'
        '    translate([arm_len,0,0])cube([2,arm_w*0.6,arm_h],center=true);\n'
        '  }\n'
        '}\n'
        'union(){\n'
        '  difference(){\n'
        '    cylinder(h=hub_h,r=hub_r,center=true,$fn=64);\n'
        '    for(i=[0:5])rotate([0,0,i*60])translate([hub_r*0.55,0,0])cylinder(h=hub_h+2,r=7,center=true,$fn=24);\n'
        '  }\n'
        '  for(i=[0:5])rotate([0,0,i*60])translate([hub_r,0,0])arm();\n'
        '  for(i=[0:5])rotate([0,0,i*60])translate([hub_r+arm_len,0,arm_h/2])mm();\n'
        '}'
    ),
    "motor_mount": (
        '// Brushless Motor Mount | strategy: cylinder with 4-bolt circle\n'
        'od=30; id=22; h=10; bolt_r=9.5; sr=1.5;\n'
        'difference(){\n'
        '  cylinder(h=h,r=od/2,$fn=32);\n'
        '  cylinder(h=h+1,r=id/2,$fn=32);\n'
        '  for(i=[0:3])rotate([0,0,i*90])translate([bolt_r,0,-1])cylinder(h=h+2,r=sr,$fn=16);\n'
        '}'
    ),
}

_KEYWORD_MAP = {
    # ── drones / UAV
    "drone": "drone",
    "uav": "drone",
    "quadcopter": "quadcopter",
    "quad": "quadcopter",
    "fpv": "quadcopter",
    "racing drone": "quadcopter",
    "freestyle drone": "quadcopter",
    "hexacopter": "hexacopter",
    "hexa": "hexacopter",
    "multirotor": "drone",
    "drone body": "drone",
    "drone frame": "drone",
    "drone chassis": "drone",
    "motor mount": "motor_mount",
    "brushless": "motor_mount",
    # ── mechanical
    "gear": "gear",
    "tooth": "gear",
    "sprocket": "gear",
    "spring": "spring",
    "helix": "helix",
    "spiral": "spiral",
    "bolt": "bolt",
    "screw": "bolt",
    "nut": "nut",
    "hex nut": "nut",
    "washer": "washer",
    "bracket": "bracket",
    "flange": "flange",
    "shaft": "shaft",
    "keyed": "shaft",
    "bearing": "bearing",
    "channel": "channel",
    "c-channel": "channel",
    "i-beam": "ibeam",
    "ibeam": "ibeam",
    # ── pipes / tubes
    "tube": "tube",
    "pipe": "pipe",
    "hollow": "tube",
    "bore": "tube",
    # ── rings / toroids
    "torus": "torus",
    "donut": "torus",
    "ring": "ring",
    "washer": "washer",
    # ── solids
    "sphere": "sphere",
    "ball": "sphere",
    "globe": "sphere",
    "cylinder": "cylinder",
    "rod": "cylinder",
    "pillar": "cylinder",
    "post": "cylinder",
    "column": "column",
    "cone": "cone",
    "pyramid": "pyramid",
    "prism": "prism",
    "hex": "hexprism",
    "hexagon": "hexprism",
    "octahedron": "octahedron",
    "diamond": "octahedron",
    # ── stars
    "star": "star",
    "starfish": "star",
    # ── architectural
    "arch": "arch",
    "dome": "dome",
    "vault": "dome",
    # ── organic
    "leaf": "leaf",
    "wave": "wave",
    "twisted": "twisted",
    "twist": "twisted",
    "knob": "knob",
    "knurl": "knob",
    # ── structural
    "l-bracket": "bracket",
    "angle iron": "bracket",
    # ── electronics
    "enclosure": "enclosure",
    "box enclosure": "enclosure",
    "standoff": "standoff",
    "pcb": "standoff",
    # ── flat/sheet
    "plate": "box",
    "panel": "box",
    "sheet": "box",
    "flat": "box",
    # ── generics
    "box": "box",
    "cube": "cube",
}

import re as _re

def _parse_dims(prompt: str) -> dict:
    """Extract W/D/H overrides injected by the frontend dimension panel."""
    dims = {}
    for axis, key in [("Width", "w"), ("Depth", "d"), ("Height", "h")]:
        m = _re.search(rf"{axis}\s*\(.*?\)\s*=\s*([\d.]+)\s*mm", prompt, _re.IGNORECASE)
        if m:
            dims[key] = float(m.group(1))
    return dims


def _apply_dims(scad: str, dims: dict) -> str:
    """Replace w/d/h variable assignments with user-specified values."""
    for var, val in dims.items():
        # Match `var = <number>;` regardless of position on the line
        scad = _re.sub(
            rf"(?<![a-zA-Z_0-9])({var}\s*=\s*)[0-9.]+(\s*;)",
            lambda m, v=val: f"{m.group(1)}{v}{m.group(2)}",
            scad,
        )
    return scad


def _local_fallback(prompt: str) -> str:
    dims = _parse_dims(prompt)
    p = prompt.lower()
    # Multi-word phrases first (longest match wins)
    for phrase in sorted(_KEYWORD_MAP, key=len, reverse=True):
        if phrase in p:
            key = _KEYWORD_MAP[phrase]
            if key in _FALLBACK_TEMPLATES:
                code = _FALLBACK_TEMPLATES[key]
                if dims:
                    code = _apply_dims(code, dims)
                return code
    # Context inference for descriptive prompts
    if any(w in p for w in ("rounded", "smooth", "organic", "blob", "bulge")):
        dw = dims.get("w", 60); dd = dims.get("d", 40); dh = dims.get("h", 30)
        return (f"// {prompt[:60]} — organic minkowski form\n"
                f"w={dw}; d={dd}; h={dh}; r=5;\n"
                f"minkowski(){{\n  cube([w-2*r,d-2*r,h-2*r], center=true);\n  sphere(r=r, $fn=24);\n}}")
    if any(w in p for w in ("lattice", "mesh", "grid", "pattern", "voronoi")):
        return _FALLBACK_TEMPLATES["wave"]
    # Generic fallback
    dw = dims.get("w", 60); dd = dims.get("d", 40); dh = dims.get("h", 30)
    return (f"// {prompt[:60]} — parametric form\n"
            f"w={dw}; d={dd}; h={dh}; // mm\n"
            f"cube([w, d, h], center=true);")


def _call_claude(messages: list) -> GenerateResponse:
    try:
        resp = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=8192,
            thinking={"type": "enabled", "budget_tokens": 4000},
            system=SYSTEM,
            messages=messages,
        )
        # Extended thinking returns multiple blocks; find the text block
        raw = next((b.text for b in resp.content if hasattr(b, "text")), "")
        scad, rationale = _parse_response(raw)
        return GenerateResponse(scad_code=scad, rationale=rationale)
    except Exception as e:
        err = str(e).lower()
        if "credit" in err or "billing" in err or "balance" in err or "402" in err or "400" in err or "thinking" in err:
            # Retry without extended thinking if billing/feature not available
            try:
                resp = client.messages.create(
                    model="claude-opus-4-7",
                    max_tokens=4096,
                    system=SYSTEM,
                    messages=messages,
                )
                raw = resp.content[0].text
                scad, rationale = _parse_response(raw)
                return GenerateResponse(scad_code=scad, rationale=rationale)
            except Exception as e2:
                err2 = str(e2).lower()
                if "credit" in err2 or "billing" in err2 or "balance" in err2 or "402" in err2 or "400" in err2:
                    last = messages[-1]["content"]
                    prompt_text = last if isinstance(last, str) else next(
                        (b["text"] for b in last if b.get("type") == "text"), "box"
                    )
                    scad = _local_fallback(prompt_text)
                    return GenerateResponse(scad_code=scad, rationale="[Offline mode — API unavailable, using geometry library]")
                raise
        raise


_ORTHO_HINT = (
    "\n\n[ORTHOGRAPHIC DRAWING ATTACHED — interpret as engineering views]\n"
    "Instructions:\n"
    "1. Identify which views are present (Front, Top, Right/Side, Isometric).\n"
    "2. Read visible dimension lines and annotations for real-world measurements.\n"
    "3. Hidden lines (dashed) indicate internal or back-face features — model them with difference().\n"
    "4. Reconstruct 3D by intersecting linear_extrude() of silhouettes from orthogonal views.\n"
    "5. Circular features in one view → cylinder() operations.\n"
    "Output valid OpenSCAD that faithfully reconstructs the drawn part."
)

_DRAWING_EXTS = {".pdf", ".dxf", ".svg", ".dwg", ".iges", ".step", ".stp"}


def _extract_pdf_text(raw: bytes) -> str | None:
    try:
        import io
        import pdfplumber
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            return "\n".join(
                page.extract_text() or "" for page in pdf.pages
            ).strip() or None
    except Exception:
        return None


def _build_user_content(prompt: str, files: list[UploadFile] | None = None, file_bytes: dict | None = None) -> list:
    """Build a Claude message content list, injecting vision blocks and drawing hints."""
    content = []
    has_drawing = False

    if files:
        for f, raw in zip(files, (file_bytes or {}).values()):
            mime = f.content_type or "application/octet-stream"
            ext = Path(f.filename or "").suffix.lower()

            if mime in IMAGE_MIMES:
                # Images sent as vision blocks — may be orthographic drawings
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime,
                        "data": base64.standard_b64encode(raw).decode(),
                    },
                })
                has_drawing = True
            elif ext == ".pdf":
                # Try to extract text (dimensions, annotations) from PDF
                text = _extract_pdf_text(raw)
                if text and len(text.strip()) > 20:
                    content.append({
                        "type": "text",
                        "text": (f"[PDF Engineering Drawing: {f.filename}]\n"
                                 f"Extracted text/annotations:\n{text[:4000]}"),
                    })
                else:
                    content.append({
                        "type": "text",
                        "text": f"[PDF Drawing attached: {f.filename} — no text extractable, interpret from context]",
                    })
                has_drawing = True
            elif ext in _DRAWING_EXTS:
                # For DXF/SVG/STEP try to include raw content if text-based
                try:
                    txt = raw.decode("utf-8", errors="replace")[:6000]
                    content.append({
                        "type": "text",
                        "text": f"[{ext.upper()} Drawing: {f.filename}]\n{txt}",
                    })
                except Exception:
                    content.append({
                        "type": "text",
                        "text": f"[{ext.upper()} Drawing: {f.filename} — binary format, use context]",
                    })
                has_drawing = True
            else:
                content.append({
                    "type": "text",
                    "text": f"[Attached file: {f.filename} ({mime})]",
                })

    full_prompt = prompt + (_ORTHO_HINT if has_drawing else "")
    content.append({"type": "text", "text": full_prompt})
    return content


@app.post("/generate", response_model=GenerateResponse)
async def generate_json(req: GenerateRequest):
    """JSON-only endpoint (no file attachments)."""
    messages = [
        *req.history,
        {"role": "user", "content": req.prompt},
    ]
    return _call_claude(messages)


@app.post("/generate/multipart", response_model=GenerateResponse)
async def generate_multipart(
    prompt: str = Form(...),
    history: str = Form(default="[]"),
    files: list[UploadFile] = File(default=[]),
):
    """Multipart endpoint supporting image/file attachments."""
    parsed_history = json.loads(history)

    # Read all file bytes upfront (UploadFile streams can only be read once)
    file_data = {}
    for f in files:
        file_data[f.filename] = await f.read()

    content = _build_user_content(prompt, files, file_data)

    messages = [
        *parsed_history,
        {"role": "user", "content": content},
    ]
    return _call_claude(messages)


@app.get("/", response_class=HTMLResponse)
async def index():
    return UI_FILE.read_text()


def launch(port: int = 7474, open_browser: bool = True) -> None:
    import threading
    import uvicorn

    if open_browser:
        threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{port}")).start()
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


if __name__ == "__main__":
    launch()
