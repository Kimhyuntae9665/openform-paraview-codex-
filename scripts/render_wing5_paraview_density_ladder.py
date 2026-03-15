#!/usr/bin/env pvpython
from __future__ import annotations

import sys
from pathlib import Path

sys.path.append("/usr/lib/python3/dist-packages")

from paraview import simple
from paraview.simple import *  # noqa: F401,F403

simple._DisableFirstRenderCameraReset()

ROOT = Path("/home/astrohome")
VTK_DIR = ROOT / "OpenFOAM-runs/wing5_uav_rerun_v2_signfix/runs/U30_AoA4_streamviz/VTK/U30_AoA4_streamviz_35"
STL_FILE = ROOT / "Downloads/wing5_1_1_m.stl"
OUT_DIR = ROOT / "paraview_density_ladder"
OUT_DIR.mkdir(exist_ok=True)


def plane(name: str, origin, point1, point2, xres: int, yres: int):
    src = Plane(registrationName=name)
    src.Origin = origin
    src.Point1 = point1
    src.Point2 = point2
    src.XResolution = xres
    src.YResolution = yres
    return src


def point_cloud(name: str, center, radius: float, count: int):
    src = PointSource(registrationName=name)
    src.Center = center
    src.Radius = radius
    src.NumberOfPoints = count
    return src


def tracer(name: str, internal, seed, direction="FORWARD", max_len=3.8, step=0.010):
    t = StreamTracerWithCustomSource(registrationName=name, Input=internal, SeedSource=seed)
    t.Vectors = ["POINTS", "U"]
    t.IntegrationDirection = direction
    t.MaximumStreamlineLength = max_len
    t.InitialStepLength = step
    t.MinimumStepLength = step / 4.0
    t.MaximumSteps = 4500
    t.MaximumError = 1.0e-06
    return t


def style_body(view, body_sampled):
    disp = Show(body_sampled, view, "GeometryRepresentation")
    disp.Representation = "Surface"
    disp.Specular = 0.22
    disp.SpecularPower = 24.0
    ColorBy(disp, ("POINTS", "p"))
    lut = GetColorTransferFunction("p")
    pwf = GetOpacityTransferFunction("p")
    lut.RescaleTransferFunction(-14.0, 7.5)
    pwf.RescaleTransferFunction(-14.0, 7.5)
    lut.ApplyPreset("Jet", True)
    disp.SetScalarBarVisibility(view, 0)
    return disp


def style_lines(view, source, line_width: float, opacity: float):
    disp = Show(source, view, "GeometryRepresentation")
    disp.Representation = "Surface"
    disp.LineWidth = line_width
    disp.Opacity = opacity
    disp.RenderLinesAsTubes = 0
    ColorBy(disp, ("POINTS", "U", "Magnitude"))
    lut = GetColorTransferFunction("U")
    pwf = GetOpacityTransferFunction("U")
    lut.RescaleTransferFunction(7.1, 8.35)
    pwf.RescaleTransferFunction(7.1, 8.35)
    lut.ApplyPreset("Turbo", True)
    disp.SetScalarBarVisibility(view, 0)
    return disp


def setup_view():
    view = CreateView("RenderView")
    view.ViewSize = [2600, 1600]
    view.OrientationAxesVisibility = 0
    view.UseColorPaletteForBackground = 0
    view.BackgroundColorMode = "Single Color"
    view.Background = [1.0, 1.0, 1.0]
    view.CameraPosition = [1.55, -2.25, 1.22]
    view.CameraFocalPoint = [-0.28, -0.02, 0.10]
    view.CameraViewUp = [0.0, 0.0, 1.0]
    view.CameraParallelProjection = 0
    return view


def add_density_set(view, internal, prefix: str, cfg: dict):
    seeds = [
        plane(
            prefix + "_far",
            [-1.23, -1.00, -0.06],
            [-1.23, 1.00, -0.06],
            [-1.23, -1.00, 0.34],
            cfg["far_xres"],
            cfg["far_yres"],
        ),
        plane(
            prefix + "_mid_top",
            [-1.00, -0.95, 0.06],
            [-1.00, 0.95, 0.06],
            [-1.00, -0.95, 0.28],
            cfg["mid_xres"],
            cfg["mid_yres"],
        ),
        plane(
            prefix + "_mid_low",
            [-1.00, -0.95, -0.02],
            [-1.00, 0.95, -0.02],
            [-1.00, -0.95, 0.15],
            cfg["low_xres"],
            cfg["low_yres"],
        ),
        point_cloud(prefix + "_root", [-0.52, 0.00, 0.16], 0.14, cfg["root_pts"]),
        point_cloud(prefix + "_root_r", [-0.44, 0.42, 0.15], 0.10, cfg["midwing_pts"]),
        point_cloud(prefix + "_root_l", [-0.44, -0.42, 0.15], 0.10, cfg["midwing_pts"]),
        point_cloud(prefix + "_tip_r", [-0.34, 0.80, 0.13], 0.09, cfg["tip_pts"]),
        point_cloud(prefix + "_tip_l", [-0.34, -0.80, 0.13], 0.09, cfg["tip_pts"]),
        point_cloud(prefix + "_body_top", [-0.18, 0.00, 0.13], 0.12, cfg["body_top_pts"]),
        point_cloud(prefix + "_body_mid", [-0.16, 0.00, 0.06], 0.11, cfg["body_mid_pts"]),
    ]

    stream_objects = []
    for i, seed in enumerate(seeds[:3]):
        stream_objects.append(
            tracer(
                f"{prefix}_plane_{i}",
                internal,
                seed,
                direction="FORWARD",
                max_len=cfg["plane_len"],
                step=cfg["plane_step"],
            )
        )
    for i, seed in enumerate(seeds[3:]):
        stream_objects.append(
            tracer(
                f"{prefix}_point_{i}",
                internal,
                seed,
                direction="BOTH",
                max_len=cfg["point_len"],
                step=cfg["point_step"],
            )
        )

    for obj in stream_objects:
        style_lines(view, obj, cfg["line_width"], cfg["line_opacity"])


def render_one(name: str, cfg: dict, body_sampled, internal):
    view = setup_view()
    style_body(view, body_sampled)
    add_density_set(view, internal, name, cfg)
    Render(view)
    SaveScreenshot(str(OUT_DIR / f"{name}.png"), view, ImageResolution=[2600, 1600], TransparentBackground=0)
    Delete(view)


def build_contact_sheet():
    from PIL import Image, ImageDraw, ImageFont

    names = ["01_light", "02_normal", "03_heavy", "04_very_heavy"]
    images = [Image.open(OUT_DIR / f"{name}.png").convert("RGB") for name in names]
    thumb_w, thumb_h = 1100, 676
    margin = 30
    header_h = 56
    canvas = Image.new("RGB", (2 * thumb_w + 3 * margin, 2 * (thumb_h + header_h) + 3 * margin), (247, 247, 247))
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    for i, (name, img) in enumerate(zip(names, images)):
        row, col = divmod(i, 2)
        x = margin + col * (thumb_w + margin)
        y = margin + row * (thumb_h + header_h + margin)
        canvas.paste(img.resize((thumb_w, thumb_h)), (x, y + header_h))
        draw.rectangle([x, y, x + thumb_w, y + header_h], fill=(230, 230, 230))
        draw.text((x + 18, y + 20), name, fill=(25, 25, 25), font=font)
    canvas.save(OUT_DIR / "density_ladder_contact_sheet.jpg", quality=95)


body = STLReader(registrationName="body_smooth_ladder", FileNames=[str(STL_FILE)])
internal = XMLUnstructuredGridReader(registrationName="internal_ladder", FileName=[str(VTK_DIR / "internal.vtu")])
internal.PointArrayStatus = ["p", "U"]
body_sampled = ResampleWithDataset(
    registrationName="body_sampled_ladder",
    SourceDataArrays=internal,
    DestinationMesh=body,
)

levels = {
    "01_light": {
        "far_xres": 58, "far_yres": 12,
        "mid_xres": 54, "mid_yres": 10,
        "low_xres": 52, "low_yres": 8,
        "root_pts": 90, "midwing_pts": 50, "tip_pts": 34, "body_top_pts": 46, "body_mid_pts": 38,
        "plane_len": 3.8, "point_len": 1.7, "plane_step": 0.013, "point_step": 0.009,
        "line_width": 0.70, "line_opacity": 0.36,
    },
    "02_normal": {
        "far_xres": 78, "far_yres": 16,
        "mid_xres": 74, "mid_yres": 14,
        "low_xres": 70, "low_yres": 12,
        "root_pts": 140, "midwing_pts": 82, "tip_pts": 58, "body_top_pts": 72, "body_mid_pts": 60,
        "plane_len": 3.9, "point_len": 1.8, "plane_step": 0.012, "point_step": 0.008,
        "line_width": 0.64, "line_opacity": 0.40,
    },
    "03_heavy": {
        "far_xres": 102, "far_yres": 22,
        "mid_xres": 96, "mid_yres": 18,
        "low_xres": 90, "low_yres": 16,
        "root_pts": 220, "midwing_pts": 120, "tip_pts": 84, "body_top_pts": 104, "body_mid_pts": 92,
        "plane_len": 4.0, "point_len": 1.9, "plane_step": 0.011, "point_step": 0.007,
        "line_width": 0.58, "line_opacity": 0.44,
    },
    "04_very_heavy": {
        "far_xres": 128, "far_yres": 28,
        "mid_xres": 118, "mid_yres": 22,
        "low_xres": 112, "low_yres": 18,
        "root_pts": 300, "midwing_pts": 170, "tip_pts": 120, "body_top_pts": 140, "body_mid_pts": 120,
        "plane_len": 4.0, "point_len": 2.0, "plane_step": 0.010, "point_step": 0.006,
        "line_width": 0.54, "line_opacity": 0.47,
    },
}

for name, cfg in levels.items():
    render_one(name, cfg, body_sampled, internal)

build_contact_sheet()
