#!/usr/bin/env python3

from __future__ import annotations

import os
import time
import sys
import math
import subprocess
import argparse
from pathlib import Path
from typing import Optional, List, Tuple
import xml.etree.ElementTree as ET

import requests
from PIL import Image, ImageEnhance, ImageOps

from svgpathtools import Document, Path as SvgPath


# ----------------- Config -----------------
PICSART_REMOVE_BG_URL = "https://api.picsart.io/tools/1.0/removebg"
ENV_KEY_NAME = "YOUR_API_KEY_HERE" # Set this to your Picsart API key, e.g. "PICSART_API_KEY"
TIMEOUT_SEC = 120

WHITE_THRESHOLD = 245
WHITE_RATIO_MIN = 0.90

LINE_CONTRAST = 2.2
LINE_THRESHOLD = 165
LINE_INVERT = False

STROKE_COLOR = "#000000"
STROKE_WIDTH_PX = "1.2"
STROKE_LINECAP = "round"
STROKE_LINEJOIN = "round"

POTRACE_EXE = r"POTRACE_EXE"  # Set this to your potrace.exe path, e.g. "C:/potrace/potrace.exe"

POTRACE_TURDSIZE = "10"
POTRACE_ALPHAMAX = "1"
POTRACE_OPTTOL = "0.2"

# Hatching shading settings (balanced for 0.5mm pen)
HATCH_LINE_STEP_PX = 7
HATCH_THICKNESS_PX = 2
HATCH_ANGLE_DEG = 45
HATCH_CONTRAST = 1.7
# ------------------------------------------


class PicsartAPIError(RuntimeError):
    pass


def log(msg: str) -> None:
    print(msg, flush=True)


def get_api_key() -> str:
    key = os.environ.get(ENV_KEY_NAME, "").strip()
    if not key:
        raise RuntimeError(
            f"{ENV_KEY_NAME} env var not set.\n"
            f"Windows PowerShell: setx {ENV_KEY_NAME} \"YOUR_KEY_HERE\"\n"
            f"Then open a NEW terminal and run again."
        )
    return key


def _extract_result_url(json_data: dict) -> Optional[str]:
    url = (json_data.get("data") or {}).get("url")
    if url:
        return url
    url = (json_data.get("response") or {}).get("url")
    if url:
        return url
    url = json_data.get("url")
    if url:
        return url
    return None


def picsart_remove_bg(input_path: Path, output_path: Path) -> Path:
    api_key = get_api_key()

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    with input_path.open("rb") as f:
        resp = requests.post(
            PICSART_REMOVE_BG_URL,
            headers={"X-Picsart-API-Key": api_key},
            files={"image": f},
            timeout=TIMEOUT_SEC,
        )

    if resp.status_code != 200:
        body = resp.text[:800] if resp.text else "<no body>"
        raise PicsartAPIError(f"Picsart API error (HTTP {resp.status_code}): {body}")

    try:
        data = resp.json()
    except ValueError as e:
        raise PicsartAPIError(f"Expected JSON but got: {resp.text[:300]}") from e

    result_url = _extract_result_url(data)
    if not result_url:
        raise PicsartAPIError("Result URL not found in response.")

    img_resp = requests.get(result_url, timeout=TIMEOUT_SEC)
    if img_resp.status_code != 200:
        raise PicsartAPIError(f"Failed to download result (HTTP {img_resp.status_code})")

    output_path.write_bytes(img_resp.content)
    return output_path


def make_white_background(png_with_alpha: Path, output_path: Path) -> Path:
    im = Image.open(png_with_alpha).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.paste(im, (0, 0), im)
    bg.convert("RGB").save(output_path, format="PNG")
    return output_path


def make_line_ready_bw(
    input_image: Path,
    output_path: Path,
    *,
    contrast: float = LINE_CONTRAST,
    threshold: int = LINE_THRESHOLD,
    invert: bool = LINE_INVERT,
) -> Path:
    im = Image.open(input_image).convert("RGB")
    im = ImageOps.grayscale(im)
    im = ImageOps.autocontrast(im, cutoff=1)
    im = ImageEnhance.Contrast(im).enhance(contrast)
    im = im.point(lambda p: 255 if p > threshold else 0, mode="L")
    if invert:
        im = ImageOps.invert(im)
    im.save(output_path, format="PNG")
    return output_path


def make_hatching_shading(
    input_image: Path,
    output_path: Path,
    *,
    line_step: int = HATCH_LINE_STEP_PX,
    thickness: int = HATCH_THICKNESS_PX,
    angle: int = HATCH_ANGLE_DEG,
    contrast: float = HATCH_CONTRAST,
) -> Path:
    im = Image.open(input_image).convert("L")
    im = ImageOps.autocontrast(im, cutoff=1)
    im = ImageEnhance.Contrast(im).enhance(contrast)

    w, h = im.size

    rot = im.rotate(angle, expand=True, fillcolor=255)
    rw, rh = rot.size
    hatch_rot = Image.new("L", (rw, rh), 255)

    rot_px = rot.load()
    hatch_px = hatch_rot.load()

    # density thresholds (tune later if needed)
    T1, T2, T3 = 85, 130, 170

    for y in range(0, rh, line_step):
        for x in range(rw):
            b = rot_px[x, y]

            draw = False
            if b < T1:
                draw = True
            elif b < T2:
                draw = ((x // 6) % 2 == 0)
            elif b < T3:
                draw = ((x // 10) % 3 == 0)

            if draw:
                for t in range(thickness):
                    yy = y + t
                    if 0 <= yy < rh:
                        hatch_px[x, yy] = 0

    hatch_final = hatch_rot.rotate(-angle, expand=True, fillcolor=255)

    cx, cy = hatch_final.size[0] // 2, hatch_final.size[1] // 2
    left = cx - w // 2
    top = cy - h // 2
    hatch_final = hatch_final.crop((left, top, left + w, top + h))

    hatch_final.save(output_path, format="PNG")
    return output_path

def calculate_white_ratio(image_path: Path, threshold: int = WHITE_THRESHOLD) -> float:
    im = Image.open(image_path).convert("L")
    hist = im.histogram()
    total = sum(hist)
    if total <= 0:
        return 0.0
    white_count = sum(hist[threshold:256])
    return white_count / total


def ensure_potrace_available(potrace_exe: str = POTRACE_EXE) -> None:
    p = Path(potrace_exe)
    if not p.exists():
        raise RuntimeError(
            "Potrace not found.\n"
            "Set POTRACE_EXE to your potrace.exe full path.\n"
            f"Current: {potrace_exe}"
        )
    subprocess.run([potrace_exe, "-v"], check=True, capture_output=True, text=True)


def png_to_bmp_for_potrace(input_png: Path, output_bmp: Path) -> Path:
    im = Image.open(input_png).convert("L")
    im = im.point(lambda p: 255 if p > 127 else 0, mode="L")
    im = im.convert("1")
    im.save(output_bmp, format="BMP")
    return output_bmp


def potrace_trace_to_svg(input_bmp: Path, output_svg: Path) -> Path:
    cmd = [
        POTRACE_EXE,
        input_bmp.as_posix(),
        "-s",
        "-o", output_svg.as_posix(),
        "--turdsize", POTRACE_TURDSIZE,
        "--alphamax", POTRACE_ALPHAMAX,
        "--opttolerance", POTRACE_OPTTOL,
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)

    if not output_svg.exists() or output_svg.stat().st_size == 0:
        raise RuntimeError("Potrace said OK but SVG not created / empty.")
    return output_svg


def svg_has_paths(svg_path: Path) -> bool:
    try:
        tree = ET.parse(svg_path)
        root = tree.getroot()
    except Exception:
        text = svg_path.read_text(encoding="utf-8", errors="ignore").lower()
        return ("<path" in text) or ("<polyline" in text) or ("<polygon" in text) or ("<line" in text)

    def local_name(tag: str) -> str:
        if "}" in tag:
            return tag.split("}", 1)[1]
        if ":" in tag:
            return tag.split(":", 1)[1]
        return tag

    drawable = {"path", "polyline", "polygon", "line", "rect", "circle", "ellipse"}
    for el in root.iter():
        if local_name(el.tag) in drawable:
            return True
    return False


def svg_has_images(svg_path: Path) -> bool:
    text = svg_path.read_text(encoding="utf-8", errors="ignore").lower()
    return "<image" in text


def _split_style(style: str) -> dict:
    out: dict = {}
    if not style:
        return out
    for p in style.split(";"):
        p = p.strip()
        if not p or ":" not in p:
            continue
        k, v = p.split(":", 1)
        out[k.strip()] = v.strip()
    return out


def _join_style(d: dict) -> str:
    return ";".join(f"{k}:{v}" for k, v in d.items() if v is not None and v != "")


def clean_svg_for_pen_plotter(
    input_svg: Path,
    output_svg: Path,
    *,
    stroke_color: str = STROKE_COLOR,
    stroke_width_px: str = STROKE_WIDTH_PX,
    stroke_linecap: str = STROKE_LINECAP,
    stroke_linejoin: str = STROKE_LINEJOIN,
) -> Path:
    tree = ET.parse(input_svg)
    root = tree.getroot()

    def local_name(tag: str) -> str:
        return tag.split("}", 1)[1] if "}" in tag else tag

    for parent in list(root.iter()):
        for child in list(parent):
            if local_name(child.tag) == "image":
                parent.remove(child)

    drawable_tags = {"path", "rect", "circle", "ellipse", "line", "polyline", "polygon"}

    for el in root.iter():
        if local_name(el.tag) not in drawable_tags:
            continue

        el.set("fill", "none")
        el.set("stroke", stroke_color)
        el.set("stroke-width", stroke_width_px)
        el.set("stroke-linecap", stroke_linecap)
        el.set("stroke-linejoin", stroke_linejoin)

        style = el.get("style", "")
        d = _split_style(style)
        d["fill"] = "none"
        d["stroke"] = stroke_color
        d["stroke-width"] = stroke_width_px
        d["stroke-linecap"] = stroke_linecap
        d["stroke-linejoin"] = stroke_linejoin
        el.set("style", _join_style(d))

    tree.write(output_svg, encoding="utf-8", xml_declaration=True)

    if not svg_has_paths(output_svg):
        raise RuntimeError("Clean SVG has no vector paths.")
    return output_svg


def trace_png_to_svg_auto(line_png: Path, svg_path: Path, base: Path) -> None:
    ensure_potrace_available()
    bmp_path = base.parent / f"{base.name}_trace.bmp"
    png_to_bmp_for_potrace(line_png, bmp_path)
    potrace_trace_to_svg(bmp_path, svg_path)

    if not svg_has_paths(svg_path):
        raise RuntimeError("Potrace produced no vector paths.")


# ======================================================================
# =====================  GCODE PART (YOUR CODE)  ========================
# ======================================================================

MACHINE_W = 220.0
MACHINE_H = 280.0

MARGIN = 20.0

PEN_UP = "M3 S50"
PEN_DOWN = "M3 S10"
PEN_DELAY = 0.2

FEED_TRAVEL = 15000
FEED_DRAW = 15000

STEP_MM = 0.5

FLIP_X = False
FLIP_Y = True

RETURN_TO_ZERO = True


def fmt(x: float) -> str:
    return f"{x:.3f}".rstrip("0").rstrip(".")


def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def get_paths(svg_file: Path) -> List[SvgPath]:
    doc = Document(str(svg_file))
    paths = doc.paths()
    paths = [p for p in paths if p is not None and len(p) > 0]
    if not paths:
        raise RuntimeError("No vector paths found in SVG.")
    return paths


def bbox_of_paths(paths: List[SvgPath]) -> Tuple[float, float, float, float]:
    minx = float("inf")
    miny = float("inf")
    maxx = float("-inf")
    maxy = float("-inf")

    for p in paths:
        xmin, xmax, ymin, ymax = p.bbox()
        minx = min(minx, xmin)
        maxx = max(maxx, xmax)
        miny = min(miny, ymin)
        maxy = max(maxy, ymax)

    if not math.isfinite(minx):
        raise RuntimeError("Could not compute SVG bounds.")
    return minx, miny, maxx, maxy


def fit_to_machine(paths: List[SvgPath]) -> Tuple[float, float, float]:
    minx, miny, maxx, maxy = bbox_of_paths(paths)
    w = maxx - minx
    h = maxy - miny
    if w <= 0 or h <= 0:
        raise RuntimeError("SVG has invalid size (bbox zero).")

    usable_w = MACHINE_W - 2 * MARGIN
    usable_h = MACHINE_H - 2 * MARGIN
    if usable_w <= 1 or usable_h <= 1:
        raise RuntimeError("Machine usable area too small. Reduce margin.")

    scale = min(usable_w / w, usable_h / h)
    dx = -minx * scale
    dy = -miny * scale
    return scale, dx, dy


def map_point(x_svg: float, y_svg: float, scale: float, dx: float, dy: float) -> Tuple[float, float]:
    x = x_svg * scale + dx
    y = y_svg * scale + dy

    SHIFT_X = 10
    SHIFT_Y = -5
    x = x - SHIFT_X
    y = y - SHIFT_Y

    x += MARGIN
    y += MARGIN

    if FLIP_X:
        x = MACHINE_W - x
    if FLIP_Y:
        y = MACHINE_H - y

    x = clamp(x, 0.0, MACHINE_W)
    y = clamp(y, 0.0, MACHINE_H)
    return (x, y)


def sample_path(p: SvgPath, scale: float, dx: float, dy: float) -> List[Tuple[float, float]]:
    L = p.length(error=1e-3)
    if L <= 1e-6:
        return []

    step_svg = STEP_MM / max(scale, 1e-9)
    n = max(2, int(math.ceil(L / step_svg)) + 1)

    pts: List[Tuple[float, float]] = []
    for i in range(n):
        t = i / (n - 1)
        z = p.point(t)
        pts.append(map_point(z.real, z.imag, scale, dx, dy))

    out: List[Tuple[float, float]] = []
    for pt in pts:
        if not out or dist(pt, out[-1]) > 0.02:
            out.append(pt)
    return out


def build_gcode(paths: List[SvgPath]) -> str:
    scale, dx, dy = fit_to_machine(paths)

    lines: List[str] = []
    lines.append("G90")
    lines.append("G21")
    lines.append(PEN_UP)
    lines.append(f"G4 P{fmt(PEN_DELAY)}")

    pen_down = False
    last: Tuple[float, float] | None = None

    def force_pen_up():
        nonlocal pen_down
        lines.append(PEN_UP)
        lines.append(f"G4 P{fmt(PEN_DELAY)}")
        pen_down = False

    def force_pen_down():
        nonlocal pen_down
        if not pen_down:
            lines.append(PEN_DOWN)
            lines.append(f"G4 P{fmt(PEN_DELAY)}")
            pen_down = True

    for p in paths:
        subpaths = p.continuous_subpaths()
        for sp in subpaths:
            pts = sample_path(sp, scale, dx, dy)
            if len(pts) < 2:
                continue

            start = pts[0]
            force_pen_up()
            if last is None or dist(start, last) > 0.02:
                lines.append(f"G0 X{fmt(start[0])} Y{fmt(start[1])}")
                last = start

            force_pen_down()
            lines.append(f"G1 F{fmt(FEED_DRAW)}")
            for (x, y) in pts[1:]:
                if last and dist((x, y), last) < 0.02:
                    continue
                lines.append(f"G1 X{fmt(x)} Y{fmt(y)}")
                last = (x, y)

            force_pen_up()

    if RETURN_TO_ZERO:
        force_pen_up()
        lines.append("G0 X0 Y0")

    return "\n".join(lines) + "\n"


def open_in_lasergrbl(gcode_path: Path) -> None:
    subprocess.run(
        "taskkill /F /IM LaserGRBL.exe",
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    time.sleep(0.3)
    os.startfile(str(gcode_path))


def process_one(input_path: Path, mode: int) -> dict:
    base = input_path.with_suffix("")
    cutout_path = base.parent / f"{base.name}_cutout.png"
    white_path = base.parent / f"{base.name}_white.png"

    if mode == 1:
        line_path = base.parent / f"{base.name}_line_m1.png"
        svg_path = base.parent / f"{base.name}_m1.svg"
        clean_svg_path = base.parent / f"{base.name}_clean_m1.svg"
        gcode_path = base.parent / f"{base.name}_m1.gcode"
    else:
        line_path = base.parent / f"{base.name}_line_m2.png"
        svg_path = base.parent / f"{base.name}_m2.svg"
        clean_svg_path = base.parent / f"{base.name}_clean_m2.svg"
        gcode_path = base.parent / f"{base.name}_m2.gcode"

    result = {"input": str(input_path), "mode": mode, "gcode": None, "success": False, "error": None}

    try:
        if gcode_path.exists() and gcode_path.stat().st_size > 0:
            result["gcode"] = str(gcode_path)
            log(f"G-code already exists (mode={mode}), opening: {gcode_path}")
            open_in_lasergrbl(gcode_path)
            result["success"] = True
            return result

        log(f"[1/6] RemoveBG: {input_path.name}")
        picsart_remove_bg(input_path, cutout_path)

        log("[2/6] White background")
        make_white_background(cutout_path, white_path)

        if mode == 1:
            log("[3/6] Mode-1 outline")
            make_line_ready_bw(white_path, line_path)
        else:
            log("[3/6] Mode-2 shading")
            make_hatching_shading(white_path, line_path)

        log("[4/6] Potrace -> SVG")
        trace_png_to_svg_auto(line_path, svg_path, base)

        log("[5/6] SVG cleanup")
        clean_svg_for_pen_plotter(svg_path, clean_svg_path)

        log("[6/6] SVG -> G-code")
        paths = get_paths(clean_svg_path)
        gcode = build_gcode(paths)
        gcode_path.write_text(gcode, encoding="utf-8")
        result["gcode"] = str(gcode_path)

        open_in_lasergrbl(gcode_path)

        result["success"] = True
        return result

    except Exception as e:
        result["error"] = str(e)
        return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", type=int, choices=[1, 2], default=1, help="1=outline, 2=shading")
    parser.add_argument("images", nargs="+", help="input image files")

    
    args = parser.parse_args(argv)

    inputs: List[Path] = [Path(p) for p in args.images]
    missing = [p for p in inputs if not p.exists()]
    if missing:
        print("Missing files:")
        for p in missing:
            print(f"  - {p}")
        return 1

    ok = 0
    for p in inputs:
        res = process_one(p, args.mode)
        if res["success"]:
            ok += 1
            print(f"OK: {res['gcode']}")
        else:
            print(f"FAIL: {p} -> {res['error']}")

    return 0 if ok == len(inputs) else 2


if __name__ == "__main__":
    raise SystemExit(main())