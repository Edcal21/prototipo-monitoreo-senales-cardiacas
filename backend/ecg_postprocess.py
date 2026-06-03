"""
Post-proceso visual para PNG de ECG generado por matplotlib.

Convierte una grafica ECG en una imagen con apariencia mas clinica:
- papel calido con textura sutil
- rejilla ECG mas viva
- trazo ECG mas profundo
- borde y sombra de documento

La funcion principal recibe bytes PNG o BytesIO y devuelve BytesIO.
"""
from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont


PAPER_BG = (255, 253, 245)
PAPER_NOISE = 4

GRID_MINOR_COL = (245, 160, 175)
GRID_MAJOR_COL = (230, 100, 120)

ECG_LINE_COL = (6, 55, 110)
R_PEAK_COL = (210, 25, 25)

BORDER_COL = (180, 170, 160)
SHADOW_COL = (210, 200, 190)
BORDER_W = 6
SHADOW_OFFSET = 8

VIGNETTE_STRENGTH = 0.12
SHARPEN_RADIUS = 0.7
SHARPEN_PCT = 130
SHARPEN_THRESH = 2
PNG_COMPRESS = 6


def _to_pil(source: bytes | io.BytesIO) -> Image.Image:
    if isinstance(source, (bytes, bytearray)):
        source = io.BytesIO(source)
    source.seek(0)
    return Image.open(source).convert("RGBA")


def _add_paper_texture(img: Image.Image, noise_strength: int) -> Image.Image:
    if noise_strength <= 0:
        return img

    arr = np.array(img).astype(np.int16)
    rng = np.random.default_rng(42)
    noise = rng.integers(
        -noise_strength,
        noise_strength + 1,
        size=(arr.shape[0], arr.shape[1]),
        dtype=np.int16,
    )
    arr[:, :, :3] = np.clip(arr[:, :, :3] + noise[:, :, np.newaxis], 0, 255)
    return Image.fromarray(arr.astype(np.uint8), "RGBA")


def _add_vignette(img: Image.Image, strength: float) -> Image.Image:
    if strength <= 0:
        return img

    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    margin_x = int(w * 0.12)
    margin_y = int(h * 0.12)
    draw.ellipse([margin_x, margin_y, w - margin_x, h - margin_y], fill=255)

    blur_r = int(min(w, h) * 0.25)
    mask = mask.filter(ImageFilter.GaussianBlur(blur_r))

    dark = Image.new("RGBA", (w, h), (0, 0, 0, int(255 * strength)))
    dark.putalpha(ImageChops.invert(mask))
    return Image.alpha_composite(img, dark)


def _add_border_and_shadow(img: Image.Image) -> Image.Image:
    w, h = img.size
    pad = BORDER_W + SHADOW_OFFSET + 2
    canvas = Image.new("RGBA", (w + pad * 2, h + pad * 2), (248, 245, 238, 255))

    shadow = Image.new("RGBA", (w + BORDER_W * 2, h + BORDER_W * 2), (*SHADOW_COL, 160))
    shadow = shadow.filter(ImageFilter.GaussianBlur(SHADOW_OFFSET // 2))
    canvas.paste(
        shadow,
        (pad - BORDER_W + SHADOW_OFFSET, pad - BORDER_W + SHADOW_OFFSET),
        shadow,
    )

    paper = Image.new("RGBA", (w + BORDER_W * 2, h + BORDER_W * 2), PAPER_BG + (255,))
    canvas.paste(paper, (pad - BORDER_W, pad - BORDER_W), paper)
    canvas.paste(img, (pad, pad), img)

    draw = ImageDraw.Draw(canvas)
    bx0, by0 = pad - BORDER_W, pad - BORDER_W
    bx1 = bx0 + w + BORDER_W * 2 - 1
    by1 = by0 + h + BORDER_W * 2 - 1
    draw.rectangle([bx0, by0, bx1, by1], outline=BORDER_COL, width=2)
    return canvas


def _enhance_ecg_colors(img: Image.Image) -> Image.Image:
    arr = np.array(img).astype(np.float32)
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]

    is_minor_grid = (r > 220) & (g < 200) & (b < 210) & (r > g + 30)
    is_major_grid = (r > 200) & (g < 160) & (b < 170) & (r > g + 50)

    arr[:, :, 0] = np.where(is_major_grid, GRID_MAJOR_COL[0], arr[:, :, 0])
    arr[:, :, 1] = np.where(is_major_grid, GRID_MAJOR_COL[1], arr[:, :, 1])
    arr[:, :, 2] = np.where(is_major_grid, GRID_MAJOR_COL[2], arr[:, :, 2])

    minor_only = is_minor_grid & ~is_major_grid
    arr[:, :, 0] = np.where(minor_only, GRID_MINOR_COL[0], arr[:, :, 0])
    arr[:, :, 1] = np.where(minor_only, GRID_MINOR_COL[1], arr[:, :, 1])
    arr[:, :, 2] = np.where(minor_only, GRID_MINOR_COL[2], arr[:, :, 2])

    is_ecg_line = (b > 100) & (r < 100) & (g < 130) & (b > r + 40)
    arr[:, :, 0] = np.where(is_ecg_line, ECG_LINE_COL[0], arr[:, :, 0])
    arr[:, :, 1] = np.where(is_ecg_line, ECG_LINE_COL[1], arr[:, :, 1])
    arr[:, :, 2] = np.where(is_ecg_line, ECG_LINE_COL[2], arr[:, :, 2])

    is_r_peak = (r > 180) & (g < 80) & (b < 80) & (r > g * 2)
    arr[:, :, 0] = np.where(is_r_peak, R_PEAK_COL[0], arr[:, :, 0])
    arr[:, :, 1] = np.where(is_r_peak, R_PEAK_COL[1], arr[:, :, 1])
    arr[:, :, 2] = np.where(is_r_peak, R_PEAK_COL[2], arr[:, :, 2])

    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")


def _thermal_tone(img: Image.Image) -> Image.Image:
    rgb = img.convert("RGB")
    rgb = ImageEnhance.Contrast(rgb).enhance(1.05)
    rgb = ImageEnhance.Color(rgb).enhance(1.08)

    alpha = img.split()[3]
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    return out


def _sharpen(img: Image.Image) -> Image.Image:
    rgb = img.convert("RGB").filter(
        ImageFilter.UnsharpMask(
            radius=SHARPEN_RADIUS,
            percent=SHARPEN_PCT,
            threshold=SHARPEN_THRESH,
        )
    )
    alpha = img.split()[3]
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    return out


def _stamp_badge(img: Image.Image, text: str) -> Image.Image:
    if not text:
        return img

    draw = ImageDraw.Draw(img)
    w, h = img.size
    margin = 14
    font_size = max(11, w // 90)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = w - tw - margin
    y = h - th - margin

    draw.rectangle(
        [x - 6, y - 4, x + tw + 6, y + th + 4],
        fill=(240, 235, 225, 180),
        outline=(160, 150, 140, 200),
    )
    draw.text((x, y), text, fill=(90, 80, 70, 200), font=font)
    return img


def ecg_clinical_render(
    png_source: bytes | io.BytesIO,
    *,
    badge_text: str = "",
    add_border: bool = True,
    vignette: float = VIGNETTE_STRENGTH,
    paper_noise: int = PAPER_NOISE,
) -> io.BytesIO:
    img = _to_pil(png_source)
    img = _enhance_ecg_colors(img)
    img = _thermal_tone(img)

    if paper_noise > 0:
        img = _add_paper_texture(img, paper_noise)
    if vignette > 0:
        img = _add_vignette(img, vignette)

    img = _sharpen(img)

    if badge_text:
        img = _stamp_badge(img, badge_text)
    if add_border:
        img = _add_border_and_shadow(img)

    out = io.BytesIO()
    img.convert("RGB").save(out, format="PNG", optimize=True, compress_level=PNG_COMPRESS)
    out.seek(0)
    return out


def patch_build_clinical_png_bytes(original_fn):
    def wrapper(*args, **kwargs):
        raw_bytesio = original_fn(*args, **kwargs)
        return ecg_clinical_render(raw_bytesio)

    return wrapper
