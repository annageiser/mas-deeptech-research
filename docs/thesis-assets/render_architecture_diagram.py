"""Render the System A vs System B architecture diagram as a high-DPI PNG.

Run:
    python3 docs/thesis-assets/render_architecture_diagram.py

Output: docs/thesis-assets/architecture_diagram.png

The same script is the editable source for the figure that appears in thesis
§3.3. Re-render after any architectural change and re-embed the PNG into the
.docx (the embedded image filename is fixed at word/media/architecture.png so
a re-run keeps the existing relationship).

Implementation note: relies only on Pillow (already a project dep). No
matplotlib, no graphviz, no mermaid-cli — chosen because Pillow is the only
graphics library guaranteed present on the build/development machines.
"""
from __future__ import annotations
import pathlib
from PIL import Image, ImageDraw, ImageFont


OUT_PATH = pathlib.Path(__file__).resolve().parent / "architecture_diagram.png"

# --------------------------------------------------------------------------
# Canvas + typography
# --------------------------------------------------------------------------
W, H = 2400, 1500
BG = (255, 255, 255)
FG = (32, 32, 32)
ACCENT_A = (33, 99, 168)       # System A blue
ACCENT_B = (160, 76, 32)       # System B orange-brown
ACCENT_SHARED = (60, 130, 70)  # Shared infrastructure green
DASH_GREY = (140, 140, 140)
BOX_FILL_A = (235, 244, 255)
BOX_FILL_B = (255, 244, 232)
BOX_FILL_SHARED = (240, 250, 240)

FONT_DIR = pathlib.Path("/System/Library/Fonts/Supplemental")
FONT_REGULAR = ImageFont.truetype(str(FONT_DIR / "Arial.ttf"), 28)
FONT_SMALL = ImageFont.truetype(str(FONT_DIR / "Arial.ttf"), 22)
FONT_BOLD = ImageFont.truetype(str(FONT_DIR / "Arial Bold.ttf"), 32)
FONT_TITLE = ImageFont.truetype(str(FONT_DIR / "Arial Bold.ttf"), 40)
FONT_LABEL = ImageFont.truetype(str(FONT_DIR / "Arial.ttf"), 20)


# --------------------------------------------------------------------------
# Primitives
# --------------------------------------------------------------------------
def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def centered_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    cx: int,
    cy: int,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int] = FG,
) -> None:
    w, h = text_size(draw, text, font)
    draw.text((cx - w // 2, cy - h // 2), text, font=font, fill=fill)


def box(
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    w: int,
    h: int,
    text: str,
    *,
    outline: tuple[int, int, int],
    fill: tuple[int, int, int],
    bold: bool = False,
    font: ImageFont.FreeTypeFont | None = None,
) -> tuple[int, int, int, int]:
    left, top = cx - w // 2, cy - h // 2
    right, bottom = cx + w // 2, cy + h // 2
    draw.rounded_rectangle((left, top, right, bottom), radius=14, outline=outline, fill=fill, width=3)
    f = font or (FONT_BOLD if bold else FONT_REGULAR)
    centered_text(draw, text, cx, cy, f)
    return left, top, right, bottom


def arrow(
    draw: ImageDraw.ImageDraw,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    *,
    width: int = 3,
    color: tuple[int, int, int] = FG,
) -> None:
    draw.line((x1, y1, x2, y2), fill=color, width=width)
    # Arrowhead — small triangle pointing toward (x2, y2)
    head = 14
    # vertical arrow assumption (y2 > y1)
    if x1 == x2:
        if y2 > y1:
            pts = [(x2, y2), (x2 - head, y2 - head), (x2 + head, y2 - head)]
        else:
            pts = [(x2, y2), (x2 - head, y2 + head), (x2 + head, y2 + head)]
    else:
        # Horizontal-ish
        if x2 > x1:
            pts = [(x2, y2), (x2 - head, y2 - head), (x2 - head, y2 + head)]
        else:
            pts = [(x2, y2), (x2 + head, y2 - head), (x2 + head, y2 + head)]
    draw.polygon(pts, fill=color)


def dashed_rect(
    draw: ImageDraw.ImageDraw,
    left: int,
    top: int,
    right: int,
    bottom: int,
    color: tuple[int, int, int] = DASH_GREY,
    dash: int = 12,
    gap: int = 8,
    width: int = 2,
) -> None:
    # Top
    x = left
    while x < right:
        draw.line((x, top, min(x + dash, right), top), fill=color, width=width)
        x += dash + gap
    # Bottom
    x = left
    while x < right:
        draw.line((x, bottom, min(x + dash, right), bottom), fill=color, width=width)
        x += dash + gap
    # Left
    y = top
    while y < bottom:
        draw.line((left, y, left, min(y + dash, bottom)), fill=color, width=width)
        y += dash + gap
    # Right
    y = top
    while y < bottom:
        draw.line((right, y, right, min(y + dash, bottom)), fill=color, width=width)
        y += dash + gap


# --------------------------------------------------------------------------
# Compose the diagram
# --------------------------------------------------------------------------
def main() -> None:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # ---- Title ----
    centered_text(
        draw,
        "System A (graph-orchestrated)   vs.   System B (single-loop agent)",
        W // 2, 50, FONT_TITLE,
    )
    centered_text(
        draw,
        "Both systems write to the same Supabase schema; comparison-validity invariant: no shared Python imports.",
        W // 2, 95, FONT_SMALL, fill=(90, 90, 90),
    )

    # ---- Column boundaries ----
    col_a_cx, col_b_cx = 540, 1860
    box_w = 460
    box_h_small = 80
    box_h_medium = 110
    top_y = 170

    # ---- System A header ----
    centered_text(draw, "System A — masfactory", col_a_cx, top_y, FONT_BOLD, fill=ACCENT_A)
    centered_text(draw, "Liu et al. 2026 MASFactory framework", col_a_cx, top_y + 38, FONT_SMALL, fill=(90, 90, 90))

    # ---- System B header ----
    centered_text(draw, "System B — hermes", col_b_cx, top_y, FONT_BOLD, fill=ACCENT_B)
    centered_text(draw, "NousResearch Hermes Agent v2026.6.5", col_b_cx, top_y + 38, FONT_SMALL, fill=(90, 90, 90))

    # ---- System A boxes ----
    y = top_y + 100
    spacing = 100
    box(draw, col_a_cx, y, box_w, box_h_small, "Planner",
        outline=ACCENT_A, fill=BOX_FILL_A)
    arrow(draw, col_a_cx, y + box_h_small // 2, col_a_cx, y + spacing - 8)

    y += spacing
    box(draw, col_a_cx, y, box_w, box_h_small, "Retriever  (arXiv · website · news · EPO · press)",
        outline=ACCENT_A, fill=BOX_FILL_A)
    arrow(draw, col_a_cx, y + box_h_small // 2, col_a_cx, y + spacing - 8)

    # Actor-loop wrapper
    loop_top = y + spacing - 30
    y += spacing
    actor_loop_y_start = y
    box(draw, col_a_cx, y, box_w, box_h_small, "Extractor",
        outline=ACCENT_A, fill=BOX_FILL_A)
    arrow(draw, col_a_cx, y + box_h_small // 2, col_a_cx, y + spacing - 8)
    y += spacing
    box(draw, col_a_cx, y, box_w, box_h_small, "Classifier  (instructor-typed JSON)",
        outline=ACCENT_A, fill=BOX_FILL_A)
    arrow(draw, col_a_cx, y + box_h_small // 2, col_a_cx, y + spacing - 8)
    y += spacing
    box(draw, col_a_cx, y, box_w, box_h_small, "Reranker pre-filter  (off by default)",
        outline=ACCENT_A, fill=BOX_FILL_A)
    arrow(draw, col_a_cx, y + box_h_small // 2, col_a_cx, y + spacing - 8)
    y += spacing
    box(draw, col_a_cx, y, box_w, box_h_small, "Critic  (single · consensus×3 · debate)",
        outline=ACCENT_A, fill=BOX_FILL_A)
    arrow(draw, col_a_cx, y + box_h_small // 2, col_a_cx, y + spacing - 8)
    y += spacing
    box(draw, col_a_cx, y, box_w, box_h_small, "Accumulate per-actor",
        outline=ACCENT_A, fill=BOX_FILL_A)
    actor_loop_y_end = y + box_h_small // 2 + 20
    # Wrapper
    dashed_rect(
        draw,
        col_a_cx - box_w // 2 - 24,
        actor_loop_y_start - box_h_small // 2 - 24,
        col_a_cx + box_w // 2 + 24,
        actor_loop_y_end,
        color=ACCENT_A,
        width=2,
    )
    draw.text(
        (col_a_cx + box_w // 2 + 32, actor_loop_y_start - box_h_small // 2 - 16),
        "per-actor loop",
        font=FONT_LABEL,
        fill=ACCENT_A,
    )
    arrow(draw, col_a_cx, actor_loop_y_end, col_a_cx, actor_loop_y_end + 50)

    y = actor_loop_y_end + 50
    box(draw, col_a_cx, y + 40, box_w, box_h_small, "Analyst  (per-actor brief)",
        outline=ACCENT_A, fill=BOX_FILL_A)
    arrow(draw, col_a_cx, y + 40 + box_h_small // 2, col_a_cx, y + 40 + spacing - 8)
    y += spacing + 40
    box(draw, col_a_cx, y, box_w, box_h_small,
        "Persistence  (attribution gate · dedup · embed · VADER)",
        outline=ACCENT_A, fill=BOX_FILL_A)
    a_bottom = y + box_h_small // 2

    # ---- System B box ----
    bx_top = top_y + 100
    bx_h = 720
    bx_w = 700
    bx_left = col_b_cx - bx_w // 2
    bx_right = col_b_cx + bx_w // 2
    bx_bottom = bx_top + bx_h
    draw.rounded_rectangle(
        (bx_left, bx_top, bx_right, bx_bottom),
        radius=20, outline=ACCENT_B, fill=BOX_FILL_B, width=3,
    )
    centered_text(draw, "Hermes Agent  (single autonomous loop)", col_b_cx, bx_top + 50, FONT_BOLD, fill=ACCENT_B)
    centered_text(draw, "invoked once per actor", col_b_cx, bx_top + 92, FONT_SMALL, fill=(110, 110, 110))

    # Inner skills/tools block
    draw.text((bx_left + 40, bx_top + 160), "Skills (custom + bundled):", font=FONT_REGULAR, fill=FG)
    skills = [
        "• collect-swiss-quantum-signals  (Ehrenthal four-signal taxonomy)",
        "• arxiv",
        "• blogwatcher",
    ]
    for i, s in enumerate(skills):
        draw.text((bx_left + 70, bx_top + 200 + i * 38), s, font=FONT_SMALL, fill=FG)

    draw.text((bx_left + 40, bx_top + 340), "Toolsets:", font=FONT_REGULAR, fill=FG)
    tools = [
        "• web  (ddgs DuckDuckGo)",
        "• skills",
    ]
    for i, s in enumerate(tools):
        draw.text((bx_left + 70, bx_top + 380 + i * 38), s, font=FONT_SMALL, fill=FG)

    draw.text((bx_left + 40, bx_top + 470), "Agent decides per actor:", font=FONT_REGULAR, fill=FG)
    decisions = [
        "• which sources to query",
        "• how many search / extract iterations",
        "• when to stop and emit JSON",
    ]
    for i, s in enumerate(decisions):
        draw.text((bx_left + 70, bx_top + 510 + i * 38), s, font=FONT_SMALL, fill=FG)

    arrow(draw, col_b_cx, bx_bottom + 10, col_b_cx, bx_bottom + 70)

    # Persister
    persister_y = bx_bottom + 130
    box(draw, col_b_cx, persister_y, bx_w, 100,
        "persist_signals.py  (attribution gate · dedup · embed · VADER)",
        outline=ACCENT_B, fill=BOX_FILL_B)
    b_bottom = persister_y + 50

    # ---- Shared infrastructure band ----
    bottom_y = max(a_bottom, b_bottom) + 110
    band_top = bottom_y - 50
    band_bottom = bottom_y + 130
    draw.rectangle((100, band_top, W - 100, band_bottom), outline=ACCENT_SHARED, fill=BOX_FILL_SHARED, width=3)
    centered_text(draw, "Shared infrastructure", W // 2, band_top + 30, FONT_BOLD, fill=ACCENT_SHARED)
    centered_text(
        draw,
        "Supabase public.signals  (Postgres + pgvector, 768d BAAI/bge-base-en-v1.5)",
        W // 2, band_top + 80, FONT_REGULAR,
    )
    centered_text(
        draw,
        "OpenRouter  →  nvidia/nemotron-3-ultra-550b-a55b:free  (fallback: qwen/qwen3-next-80b-a3b-instruct:free)",
        W // 2, band_top + 124, FONT_REGULAR,
    )
    centered_text(
        draw,
        "40 actors  ·  daily cron (02:00 / 05:00 Europe/Zurich)  ·  Caddy basic-auth at mas-deeptech-research.cloud",
        W // 2, band_top + 168, FONT_SMALL, fill=(80, 80, 80),
    )

    # Arrows from each system into the shared band
    arrow(draw, col_a_cx, a_bottom + 5, col_a_cx, band_top - 5)
    arrow(draw, col_b_cx, b_bottom + 5, col_b_cx, band_top - 5)

    # ---- Footer caption ----
    caption_y = band_bottom + 30
    centered_text(
        draw,
        "Figure: Operational topology of the two compared systems. Each agent box in System A is a separately auditable graph node;",
        W // 2, caption_y, FONT_SMALL, fill=(80, 80, 80),
    )
    centered_text(
        draw,
        "System B's autonomous loop performs the same functions internally but produces no per-node artefact (§3.3, §3.6).",
        W // 2, caption_y + 30, FONT_SMALL, fill=(80, 80, 80),
    )

    img.save(OUT_PATH, "PNG", dpi=(300, 300), optimize=True)
    print(f"wrote {OUT_PATH}  ({OUT_PATH.stat().st_size:,} bytes, {W}x{H} px @ 300 dpi)")


if __name__ == "__main__":
    main()
