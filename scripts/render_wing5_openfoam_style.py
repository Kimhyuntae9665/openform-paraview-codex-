#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import numpy as np
import pyvista as pv
from PIL import Image


ROOT = Path("/home/astrohome")
STL_PATH = ROOT / "Downloads/wing5_1_1_m.stl"
CSV_PATH = ROOT / "OpenFOAM-runs/wing5_uav_rerun_v2_signfix/results/coefficients_sweep_smoothed.csv"
OUT_PNG = ROOT / "openfoam_wing5_aero_style.png"
OUT_JPG = ROOT / "openfoam_wing5_aero_style.jpg"
OUT_BOTTOM_PNG = ROOT / "openfoam_wing5_aero_style_bottom.png"
OUT_BOTTOM_JPG = ROOT / "openfoam_wing5_aero_style_bottom.jpg"

# Original STL frame -> current frame:
# old: x-forward, y-right, z-down, absolute CG
# new: x-right, y-forward, z-up, CG-relative
CG_OLD_ABS = np.array([-0.416882, -0.013035, 0.100203], dtype=float)

CAMERA_PRESETS: dict[str, list[tuple[float, float, float]]] = {
    "top": [
        (2.30, -2.10, 1.20),
        (0.00, -0.05, -0.02),
        (0.00, 0.00, 1.00),
    ],
    "bottom": [
        (2.30, -2.10, -1.15),
        (0.00, -0.05, -0.02),
        (0.00, 0.00, 1.00),
    ],
}


def load_case(case_name: str) -> dict[str, float]:
    rows = list(csv.DictReader(CSV_PATH.open()))
    for row in rows:
        if row["case"] == case_name:
            return {
                "speed_kmh": float(row["speed_kmh"]),
                "aoa_deg": float(row["aoa_deg"]),
                "Cd": float(row["Cd"]),
                "Cl": float(row["Cl"]),
                "CmPitch": float(row["CmPitch"]),
            }
    raise SystemExit(f"Missing case in CSV: {case_name}")


def transform_points(points: np.ndarray) -> np.ndarray:
    rel_old = points - CG_OLD_ABS
    x_right = rel_old[:, 1]
    y_forward = rel_old[:, 0]
    # Keep visual top-side orientation consistent with the STL the user expects.
    z_up = rel_old[:, 2]
    return np.column_stack((x_right, y_forward, z_up))


def make_pressure_scalar(mesh: pv.PolyData, aoa_deg: float, cl_raw: float) -> np.ndarray:
    normals = mesh.point_data["Normals"]
    pts = mesh.points

    aoa = math.radians(aoa_deg)
    flow_dir = np.array([0.0, math.cos(aoa), -math.sin(aoa)], dtype=float)
    flow_dir /= np.linalg.norm(flow_dir)

    front_incidence = np.clip(-(normals @ flow_dir), -1.0, 1.0)

    z_norm = pts[:, 2] / max(np.max(np.abs(pts[:, 2])), 1e-6)
    y_norm = pts[:, 1] / max(np.max(np.abs(pts[:, 1])), 1e-6)
    span_norm = pts[:, 0] / max(np.max(np.abs(pts[:, 0])), 1e-6)

    # Use the corrected OpenFOAM lift sign to bias upper-surface suction.
    lift_mag = max(abs(cl_raw), 0.02)
    suction_bias = -(0.7 + 8.0 * lift_mag) * math.sin(aoa) * normals[:, 2]

    nose_bias = 0.30 * np.exp(-((y_norm - 0.55) ** 2) / 0.12)
    center_bias = 0.15 * np.exp(-(span_norm**2) / 0.55)
    body_bias = -0.10 * z_norm

    pressure_like = 0.90 * front_incidence + suction_bias + nose_bias + center_bias + body_bias
    return np.tanh(1.25 * pressure_like)


def add_arrow(plotter: pv.Plotter, start: tuple[float, float, float], direction: tuple[float, float, float], scale: float, color: str, label: str) -> None:
    arrow = pv.Arrow(start=start, direction=direction, scale=scale, shaft_radius=0.025, tip_radius=0.06, tip_length=0.20)
    plotter.add_mesh(arrow, color=color, smooth_shading=True)
    label_pos = np.array(start) + np.array(direction, dtype=float) * (scale * 1.12)
    plotter.add_point_labels(
        [label_pos],
        [label],
        text_color=color,
        font_size=16,
        point_color=color,
        point_size=0,
        shape=None,
        always_visible=True,
    )


def add_reference_line(
    plotter: pv.Plotter,
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    color: str,
    width: float,
) -> None:
    plotter.add_mesh(pv.Line(start, end), color=color, line_width=width)


def render(case_name: str = "U30_AoA4", view: str = "top") -> None:
    case = load_case(case_name)

    mesh = pv.read(str(STL_PATH)).triangulate().clean()
    mesh.points = transform_points(np.asarray(mesh.points))
    mesh = mesh.compute_normals(point_normals=True, cell_normals=False, auto_orient_normals=True, inplace=False)
    mesh["PressureLike"] = make_pressure_scalar(mesh, case["aoa_deg"], case["Cl"])

    pv.start_xvfb()
    plotter = pv.Plotter(off_screen=True, window_size=(1800, 1200))
    plotter.set_background("white")

    plotter.add_mesh(
        mesh,
        scalars="PressureLike",
        cmap="jet",
        smooth_shading=True,
        specular=0.22,
        scalar_bar_args={
                "title": "Pressure-like index",
            "vertical": True,
            "position_x": 0.02,
            "position_y": 0.10,
            "width": 0.05,
            "height": 0.72,
            "fmt": "%.2f",
            "title_font_size": 20,
            "label_font_size": 16,
        },
    )

    aoa = math.radians(case["aoa_deg"])
    flow_start = (-0.95, 0.52, 0.20) if view == "top" else (-0.95, 0.34, -0.26)
    flow_scale = 0.72
    add_reference_line(
        plotter,
        start=flow_start,
        end=(flow_start[0], flow_start[1] + flow_scale, flow_start[2]),
        color="lightgray",
        width=6,
    )
    add_arrow(
        plotter,
        start=flow_start,
        direction=(0.0, math.cos(aoa), -math.sin(aoa)),
        scale=flow_scale,
        color="royalblue",
        label=f"Freestream (+{case['aoa_deg']:.0f} deg)",
    )
    add_arrow(plotter, start=(0.02, -0.02, -0.02), direction=(0.0, 0.0, 1.0), scale=0.26, color="forestgreen", label="Lift")
    add_arrow(plotter, start=(0.02, -0.02, -0.02), direction=(0.0, -1.0, 0.0), scale=0.18, color="crimson", label="Drag")

    title = f"wing5 OpenFOAM-style aerodynamic view ({view})"
    line1 = f"Case {case_name}   V={case['speed_kmh']:.0f} km/h   AoA={case['aoa_deg']:.0f} deg"
    line2 = f"Cd={case['Cd']:.4f}   Cl={case['Cl']:.4f}   Cm={case['CmPitch']:.4f}"
    line3 = "Gray line = body-axis reference, blue arrow = freestream at the actual AoA"
    plotter.add_text(title, position=(270, 1120), font_size=24, color="black")
    plotter.add_text(line1, position=(270, 1080), font_size=17, color="black")
    plotter.add_text(line2, position=(270, 1048), font_size=17, color="black")
    plotter.add_text(line3, position=(270, 1018), font_size=15, color="dimgray")

    plotter.camera_position = CAMERA_PRESETS[view]
    out_png = OUT_PNG if view == "top" else OUT_BOTTOM_PNG
    out_jpg = OUT_JPG if view == "top" else OUT_BOTTOM_JPG
    plotter.show(screenshot=str(out_png))
    plotter.close()

    Image.open(out_png).convert("RGB").save(out_jpg, quality=95)
    print(out_png)
    print(out_jpg)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", default="U30_AoA4")
    parser.add_argument("--view", choices=sorted(CAMERA_PRESETS), default="top")
    args = parser.parse_args()
    render(case_name=args.case, view=args.view)
