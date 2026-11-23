"""Compose gauges into a scene (single dial, panel, before/after pair) and then
'photograph' it: glare, camera tilt (perspective), exposure, blur and sensor noise.

Every geometric/photometric change is applied to the evidence masks as well, so
the validator can check what is *actually visible* in the final picture.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image, ImageDraw

from .render import CANON, GaugeRender, font
from .spec import PhotoSpec

PANEL_RGB = (196, 199, 196)


@dataclass
class Placement:
    x: float          # top-left of the canonical gauge image in canvas px
    y: float
    scale: float      # canvas px per canonical px


@dataclass
class Scene:
    image: np.ndarray                          # final RGB uint8
    renders: list[GaugeRender]
    placements: list[Placement]
    needle_masks: list[np.ndarray]             # final-image needle masks (float 0..1)
    setpoint_masks: list[np.ndarray | None]
    glare_alpha: np.ndarray                    # final-image glare opacity 0..1
    homography: np.ndarray
    tags: list[str] = field(default_factory=list)

    def local_scale(self, i: int) -> float:
        """Smallest linear magnification (final px per canonical px) around gauge i's
        centre, including perspective foreshortening."""
        p = self.placements[i]
        cx = p.x + CANON / 2 * p.scale
        cy = p.y + CANON / 2 * p.scale
        J = _jacobian(self.homography, cx, cy)
        s = np.linalg.svd(J, compute_uv=False)
        return float(p.scale * s.min())


def _jacobian(H: np.ndarray, x: float, y: float, eps: float = 1.0) -> np.ndarray:
    def f(px, py):
        v = H @ np.array([px, py, 1.0])
        return v[:2] / v[2]
    fx = (f(x + eps, y) - f(x - eps, y)) / (2 * eps)
    fy = (f(x, y + eps) - f(x, y - eps)) / (2 * eps)
    return np.stack([fx, fy], axis=1)


def _layout(n: int, kind: str) -> tuple[int, int, list[Placement], int]:
    if kind == "single":
        W = H = 640
        return W, H, [Placement(20, 20, 1.0)], 0
    cols = n if n <= 3 else math.ceil(n / 2)
    rows = math.ceil(n / cols)
    cell, plate = 400, 52
    sc = cell / CANON
    W = cols * cell + 40
    H = rows * (cell + plate) + 40
    places = []
    for i in range(n):
        r, c = divmod(i, cols)
        places.append(Placement(20 + c * cell, 20 + r * (cell + plate), sc))
    return W, H, places, plate


def compose(renders: list[GaugeRender], tags: list[str], kind: str) -> tuple[Image.Image, list[Placement], list[np.ndarray], list[np.ndarray | None]]:
    W, H, places, plate = _layout(len(renders), kind)
    canvas = Image.new("RGBA", (W, H), PANEL_RGB + (255,))
    draw = ImageDraw.Draw(canvas)
    nmasks, smasks = [], []
    for r, p, tag in zip(renders, places, tags):
        size = int(round(CANON * p.scale))
        g = r.rgba.resize((size, size), Image.LANCZOS) if size != CANON else r.rgba
        canvas.alpha_composite(g, (int(p.x), int(p.y)))

        def place_mask(m):
            if m is None:
                return None
            full = np.zeros((H, W), np.float32)
            mm = cv2.resize(m.astype(np.float32) / 255.0, (size, size), interpolation=cv2.INTER_AREA)
            full[int(p.y):int(p.y) + size, int(p.x):int(p.x) + size] = mm
            return full
        nmasks.append(place_mask(r.needle_mask))
        smasks.append(place_mask(r.setpoint_mask))

        if tag and plate:
            cxp = p.x + size / 2
            top = p.y + size - 6
            f = font(26)
            tw = draw.textlength(tag, font=f)
            draw.rounded_rectangle([cxp - tw / 2 - 14, top, cxp + tw / 2 + 14, top + 40], 6,
                                   fill=(25, 25, 28, 255))
            draw.text((cxp, top + 20), tag, font=f, fill=(250, 250, 250, 255), anchor="mm")
    return canvas.convert("RGB"), places, nmasks, smasks


def _glare(rng: np.random.Generator, H: int, W: int, level: int, places: list[Placement]) -> np.ndarray:
    alpha = np.zeros((H, W), np.float32)
    if level <= 0:
        return alpha
    strength = {1: 0.45, 2: 0.85}[min(level, 2)]
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    for p in places:
        size = CANON * p.scale
        cx = p.x + size * rng.uniform(0.3, 0.7)
        cy = p.y + size * rng.uniform(0.3, 0.7)
        rx = size * rng.uniform(0.10, 0.22)
        ry = size * rng.uniform(0.05, 0.12)
        th = rng.uniform(0, math.pi)
        dx, dy = xx - cx, yy - cy
        u = (dx * math.cos(th) + dy * math.sin(th)) / rx
        v = (-dx * math.sin(th) + dy * math.cos(th)) / ry
        alpha = np.maximum(alpha, strength * np.exp(-(u * u + v * v) * 1.2))
    return alpha


def _homography(rng: np.random.Generator, W: int, H: int, tilt: float) -> np.ndarray:
    if tilt <= 0:
        return np.eye(3)
    t = math.radians(tilt)
    shrink = 0.5 * math.tan(t) * 0.45        # how much the far edge shrinks (fraction)
    squash = 1 - (1 - math.cos(t)) * 0.8     # foreshortening across the tilt axis
    src = np.float32([[0, 0], [W, 0], [W, H], [0, H]])
    side = int(rng.integers(0, 4))           # which edge is further from the camera
    dst = src.copy()
    if side in (0, 1):                       # left / right edge far
        far = [0, 3] if side == 0 else [1, 2]
        for i in far:
            dst[i, 1] = H / 2 + (dst[i, 1] - H / 2) * (1 - shrink)
        cx = W / 2
        dst[:, 0] = cx + (dst[:, 0] - cx) * squash
    else:                                    # top / bottom edge far
        far = [0, 1] if side == 2 else [2, 3]
        for i in far:
            dst[i, 0] = W / 2 + (dst[i, 0] - W / 2) * (1 - shrink)
        cy = H / 2
        dst[:, 1] = cy + (dst[:, 1] - cy) * squash
    jitter = rng.uniform(-0.015, 0.015, size=(4, 2)).astype(np.float32) * [W, H]
    return cv2.getPerspectiveTransform(src, (dst + jitter).astype(np.float32))


def photograph(rng: np.random.Generator, canvas: Image.Image, places: list[Placement],
               nmasks: list[np.ndarray], smasks: list[np.ndarray | None], photo: PhotoSpec):
    img = np.asarray(canvas).astype(np.float32)
    H, W = img.shape[:2]

    alpha = _glare(rng, H, W, photo.glare, places)
    img = img * (1 - alpha[..., None]) + 255.0 * alpha[..., None]

    Hm = _homography(rng, W, H, photo.tilt)
    if photo.tilt > 0:
        warp = lambda a, border: cv2.warpPerspective(a, Hm, (W, H), flags=cv2.INTER_LINEAR,
                                                    borderMode=cv2.BORDER_CONSTANT, borderValue=border)
        img = warp(img, (90, 92, 95))
        alpha = warp(alpha, 0)
        nmasks = [warp(m, 0) for m in nmasks]
        smasks = [warp(m, 0) if m is not None else None for m in smasks]

    if photo.lighting != 1.0:
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        vign = 1 - 0.25 * (((xx - W / 2) / W) ** 2 + ((yy - H / 2) / H) ** 2) * 4
        img = img * photo.lighting * vign[..., None]
    if photo.blur > 0:
        img = cv2.GaussianBlur(img, (0, 0), photo.blur)
    if photo.noise > 0:
        img = img + rng.normal(0, photo.noise, img.shape).astype(np.float32)
    img = np.clip(img, 0, 255).astype(np.uint8)
    return img, nmasks, smasks, alpha, Hm


def build_scene(rng: np.random.Generator, renders: list[GaugeRender], tags: list[str],
                kind: str, photo: PhotoSpec) -> Scene:
    canvas, places, nm, sm = compose(renders, tags, kind)
    img, nm, sm, alpha, Hm = photograph(rng, canvas, places, nm, sm, photo)
    return Scene(img, renders, places, nm, sm, alpha, Hm, tags)
