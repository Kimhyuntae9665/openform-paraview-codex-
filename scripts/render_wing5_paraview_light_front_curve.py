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
OUT_DIR = ROOT / "paraview_density_ladder_front"
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


def tracer(name: str, internal, seed, direction="FORWARD", max_len=3.8, step=0.011):
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


def setup_view(camera_position, camera_focal, camera_up):
    view = CreateView("RenderView")
    view.ViewSize = [2600, 1600]
    view.OrientationAxesVisibility = 0
    view.UseColorPaletteForBackground = 0
    view.BackgroundColorMode = "Single Color"
    view.Background = [1.0, 1.0, 1.0]
    view.CameraPosition = camera_position
    view.CameraFocalPoint = camera_focal
    view.CameraViewUp = camera_up
    view.CameraParallelProjection = 0
    return view


def add_streams(view, internal, prefix: str, cfg: dict):
    seeds = [
        plane(
            prefix + "_far",
            [-1.22, -0.96, -0.05],
            [-1.22, 0.96, -0.05],
            [-1.22, -0.96, 0.33],
            cfg["far_xres"],
            cfg["far_yres"],
        ),
        plane(
            prefix + "_mid",
            [-0.98, -0.90, 0.03],
            [-0.98, 0.90, 0.03],
            [-0.98, -0.90, 0.24],
            cfg["mid_xres"],
            cfg["mid_yres"],
        ),
        point_cloud(prefix + "_wing_root", [-0.52, 0.00, 0.16], 0.13, cfg["root_pts"]),
        point_cloud(prefix + "_wing_r", [-0.42, 0.36, 0.15], 0.09, cfg["wing_pts"]),
        point_cloud(prefix + "_wing_l", [-0.42, -0.36, 0.15], 0.09, cfg["wing_pts"]),
        point_cloud(prefix + "_body_top", [-0.17, 0.00, 0.12], 0.11, cfg["body_pts"]),
        point_cloud(prefix + "_body_mid", [-0.10, 0.00, 0.07], 0.10, cfg["body_mid_pts"]),
        point_cloud(prefix + "_nose", [-0.80, 0.00, 0.07], 0.09, cfg["nose_pts"]),
        point_cloud(prefix + "_nose_r", [-0.73, 0.10, 0.08], 0.07, cfg["nose_side_pts"]),
        point_cloud(prefix + "_nose_l", [-0.73, -0.10, 0.08], 0.07, cfg["nose_side_pts"]),
    ]

    plane_seeds = seeds[:2]
    point_seeds = seeds[2:]

    for i, seed in enumerate(plane_seeds):
        obj = tracer(
            f"{prefix}_plane_{i}",
            internal,
            seed,
            direction="FORWARD",
            max_len=cfg["plane_len"],
            step=cfg["plane_step"],
        )
        style_lines(view, obj, cfg["line_width"], cfg["line_opacity"])

    for i, seed in enumerate(point_seeds):
        obj = tracer(
            f"{prefix}_point_{i}",
            internal,
            seed,
            direction="BOTH",
            max_len=cfg["point_len"],
            step=cfg["point_step"],
        )
        style_lines(view, obj, cfg["line_width"], cfg["line_opacity"])


def render_one(name: str, cfg: dict, body_sampled, internal):
    view = setup_view(cfg["camera_position"], cfg["camera_focal"], cfg["camera_up"])
    style_body(view, body_sampled)
    add_streams(view, internal, name, cfg)
    Render(view)
    SaveScreenshot(str(OUT_DIR / f"{name}.png"), view, ImageResolution=[2600, 1600], TransparentBackground=0)
    Delete(view)


def build_contact_sheet():
    from PIL import Image, ImageDraw, ImageFont

    names = ["01_light_front_curve", "02_light_front_curve_close"]
    images = [Image.open(OUT_DIR / f"{name}.png").convert("RGB") for name in names]
    thumb_w, thumb_h = 1200, 738
    margin = 30
    header_h = 56
    canvas = Image.new("RGB", (2 * thumb_w + 3 * margin, thumb_h + header_h + 2 * margin), (247, 247, 247))
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    for i, (name, img) in enumerate(zip(names, images)):
        x = margin + i * (thumb_w + margin)
        y = margin
        canvas.paste(img.resize((thumb_w, thumb_h)), (x, y + header_h))
        draw.rectangle([x, y, x + thumb_w, y + header_h], fill=(230, 230, 230))
        draw.text((x + 18, y + 20), name, fill=(25, 25, 25), font=font)
    canvas.save(OUT_DIR / "front_curve_contact_sheet.jpg", quality=95)


body = STLReader(registrationName="body_smooth_front_curve", FileNames=[str(STL_FILE)])
internal = XMLUnstructuredGridReader(registrationName="internal_front_curve", FileName=[str(VTK_DIR / "internal.vtu")])
internal.PointArrayStatus = ["p", "U"]
body_sampled = ResampleWithDataset(
    registrationName="body_sampled_front_curve",
    SourceDataArrays=internal,
    DestinationMesh=body,
)

variants = {
    "01_light_front_curve": {
        "far_xres": 56,
        "far_yres": 11,
        "mid_xres": 42,
        "mid_yres": 10,
        "root_pts": 84,
        "wing_pts": 50,
        "body_pts": 44,
        "body_mid_pts": 36,
        "nose_pts": 56,
        "nose_side_pts": 32,
        "plane_len": 3.7,
        "point_len": 1.55,
        "plane_step": 0.012,
        "point_step": 0.0075,
        "line_width": 0.68,
        "line_opacity": 0.34,
        "camera_position": [-2.10, -0.90, 0.78],
        "camera_focal": [-0.48, -0.01, 0.11],
        "camera_up": [0.0, 0.0, 1.0],
    },
    "02_light_front_curve_close": {
        "far_xres": 52,
        "far_yres": 10,
        "mid_xres": 38,
        "mid_yres": 9,
        "root_pts": 76,
        "wing_pts": 44,
        "body_pts": 38,
        "body_mid_pts": 32,
        "nose_pts": 64,
        "nose_side_pts": 36,
        "plane_len": 3.5,
        "point_len": 1.45,
        "plane_step": 0.0115,
        "point_step": 0.007,
        "line_width": 0.66,
        "line_opacity": 0.33,
        "camera_position": [-1.78, -0.48, 0.62],
        "camera_focal": [-0.58, -0.01, 0.10],
        "camera_up": [0.0, 0.0, 1.0],
    },
}

for name, cfg in variants.items():
    render_one(name, cfg, body_sampled, internal)

build_contact_sheet()
