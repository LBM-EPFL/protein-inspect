"""View-battery montage: compose individual PyMOL views into a single
labeled grid image.

Motivation
----------
The Claude Code CLI silently caps `@path` image attachments at 3 per
non-trivial prompt (see `evals/experiments/cli_image_dropout_findings.md`).
The full view battery is typically 5–9 PNGs per protein, so attaching
them all causes views past the third to be dropped server-side, with the
model explicitly reporting "image N was not rendered to me." The eval
becomes effectively "YAML + 3 images" instead of "YAML + full battery."

The montage workaround composes the views into a *single* PNG with each
panel's view name burned in over it. A single attachment never trips the
cap, and the model can still recover which view is which via the burned-in
title.

Trade-off: each panel gets downscaled, so the per-view label sizes that
read cleanly at 1200×900 get smaller in the montage. View-battery labels
were already bumped to size 28–30 in anticipation of this; in practice the
montage panels stay readable at typical LLM image-viewer sizes (~600px
wide panels in a 2×3 montage).

Future alternative
------------------
The clean architectural fix is to bypass the CLI entirely and call the
Anthropic SDK directly with explicit `content` blocks per image. That
requires an `ANTHROPIC_API_KEY` (the Max-subscription auth used by
`claude -p` doesn't carry over) and a small replumb of `run_eval.py` to
use `anthropic.Anthropic().messages.create(...)`. Worth doing if the eval
needs to scale to many-image conditions or if you want per-image cost
attribution.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Title bar height per panel (px). Holds the view name + parameters.
TITLE_HEIGHT = 64

# Background color for the whole montage (white matches the rendered views).
BG_COLOR = (255, 255, 255)

# Title bar fill + text color.
TITLE_BG = (32, 32, 32)
TITLE_FG = (240, 240, 240)


def _resolve_font(size: int) -> ImageFont.ImageFont:
    """Try a few system font paths; fall back to PIL's default."""
    candidates = [
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size)
            except (OSError, IOError):
                continue
    return ImageFont.load_default()


def _grid_dimensions(n: int) -> tuple[int, int]:
    """Pick (rows, cols) for n panels, biasing toward wider-than-tall.

    Examples: 1→(1,1), 2→(1,2), 3→(1,3), 4→(2,2), 5–6→(2,3), 7–9→(3,3),
    10–12→(3,4), 13–16→(4,4).
    """
    if n <= 0:
        return (0, 0)
    if n == 1:
        return (1, 1)
    if n == 2:
        return (1, 2)
    if n == 3:
        return (1, 3)
    if n == 4:
        return (2, 2)
    if n <= 6:
        return (2, 3)
    if n <= 9:
        return (3, 3)
    if n <= 12:
        return (3, 4)
    # General: square-ish, slightly wider
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    return (rows, cols)


_FILENAME_RE = re.compile(r"^\d+_?(.*?)\.png$", re.IGNORECASE)


def _title_for(path: Path) -> str:
    """Strip leading 'NN_' prefix and the .png extension for the title bar."""
    m = _FILENAME_RE.match(path.name)
    if m and m.group(1):
        # Replace underscores with spaces for readability, preserve identifiers.
        return m.group(1).replace("_", " ")
    return path.stem


def build_montage(views_dir: Path, out_path: Path,
                  max_panels: int | None = None,
                  panel_size: tuple[int, int] | None = None) -> dict:
    """Compose all PNGs in views_dir into a single grid PNG at out_path.

    Each panel carries a dark title bar with the view name (e.g.,
    "metal ZN A101", "pocket SRO A202") burned in so the model can
    identify which view is which without external metadata.

    Parameters
    ----------
    views_dir:
        Directory containing the per-view PNGs from PyMOL.
    out_path:
        Where to write the composite PNG.
    max_panels:
        If set, only the first `max_panels` views (sorted by filename) are
        included. Useful when more views exist than the grid can comfortably
        hold.
    panel_size:
        Force each panel to (width, height). Defaults to the size of the
        first source PNG.

    Returns
    -------
    A dict with: `path` (the output path), `n_panels` (how many made it in),
    `grid` ([rows, cols]), `panel_size`, `total_size`. Useful for logging
    and for populating `summary.visual.montage`.
    """
    paths = sorted(views_dir.glob("*.png"))
    if max_panels is not None:
        paths = paths[:max_panels]
    if not paths:
        raise FileNotFoundError(f"No PNGs found in {views_dir}")

    # Load first image to derive panel size if not specified.
    first = Image.open(paths[0]).convert("RGB")
    if panel_size is None:
        panel_size = first.size  # (width, height)
    panel_w, panel_h = panel_size

    n = len(paths)
    rows, cols = _grid_dimensions(n)

    # Total montage dimensions: panels stacked with title bars on top of each.
    cell_h = panel_h + TITLE_HEIGHT
    total_w = cols * panel_w
    total_h = rows * cell_h

    montage = Image.new("RGB", (total_w, total_h), BG_COLOR)
    draw = ImageDraw.Draw(montage)
    font = _resolve_font(size=max(20, TITLE_HEIGHT // 2))

    for idx, p in enumerate(paths):
        r = idx // cols
        c = idx % cols
        x = c * panel_w
        y = r * cell_h

        # Title bar
        draw.rectangle([(x, y), (x + panel_w, y + TITLE_HEIGHT)], fill=TITLE_BG)
        title = _title_for(p)
        # Center text in the title bar
        try:
            tb = draw.textbbox((0, 0), title, font=font)
            text_w = tb[2] - tb[0]
            text_h = tb[3] - tb[1]
        except AttributeError:
            text_w, text_h = font.getsize(title)
        tx = x + max(8, (panel_w - text_w) // 2)
        ty = y + max(4, (TITLE_HEIGHT - text_h) // 2)
        draw.text((tx, ty), title, font=font, fill=TITLE_FG)

        # Image panel
        img = Image.open(p).convert("RGB")
        if img.size != (panel_w, panel_h):
            img = img.resize((panel_w, panel_h), Image.LANCZOS)
        montage.paste(img, (x, y + TITLE_HEIGHT))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    montage.save(out_path, format="PNG", optimize=True)

    return {
        "path": str(out_path),
        "n_panels": n,
        "grid": [rows, cols],
        "panel_size": [panel_w, panel_h],
        "total_size": [total_w, total_h],
    }
