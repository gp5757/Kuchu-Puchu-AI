"""
core/video_summary/renderer.py
Renders whiteboard animation frames matching Kuchu Puchu AI's paper/notebook aesthetic.
Generates progressive scene reveals (header -> doodle -> key point -> bullet points).
"""

import os
import math
from PIL import Image, ImageDraw, ImageFont

CANVAS_WIDTH = 1280
CANVAS_HEIGHT = 720

# Palette matching Kuchu Puchu AI notebook design
BG_COLOR = "#FAF8F2"
PAPER_LINE_COLOR = "#EFEAE1"
TEXT_COLOR = "#2D2823"
TEXT_MUTED = "#6B645B"
CARD_BG = "#FFFFFF"
BORDER_COLOR = "#DED5C7"
HIGHLIGHT_BG = "#FEF9C3"  # Butter yellow marker tint
HIGHLIGHT_BORDER = "#EAB308"

# Available font paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FONT_DIR = os.path.join(BASE_DIR, "app", "static", "fonts")
FONT_BOLD_PATH = os.path.join(FONT_DIR, "Kalam-Bold.ttf")
FONT_REG_PATH = os.path.join(FONT_DIR, "Kalam-Regular.ttf")


def _get_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    """Loads Kalam font or falls back gracefully to system TrueType or Pillow default."""
    target_path = FONT_BOLD_PATH if bold else FONT_REG_PATH
    if os.path.exists(target_path):
        try:
            return ImageFont.truetype(target_path, size)
        except Exception:
            pass

    # Windows fallbacks
    for name in ["comicbd.ttf" if bold else "comic.ttf", "segoeuib.ttf" if bold else "segoeui.ttf", "arialbd.ttf" if bold else "arial.ttf"]:
        win_path = os.path.join("C:\\Windows\\Fonts", name)
        if os.path.exists(win_path):
            try:
                return ImageFont.truetype(win_path, size)
            except Exception:
                pass

    # Linux / Docker fallbacks
    for name in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        if os.path.exists(name):
            try:
                return ImageFont.truetype(name, size)
            except Exception:
                pass

    return ImageFont.load_default()


def _draw_washi_tape(draw: ImageDraw.ImageDraw, x: int, y: int, width: int, height: int, color: str = "#E9D5FF"):
    """Draws a cute hand-torn washi tape strip at (x, y)."""
    # Jagged left edge and right edge
    draw.rectangle([x, y, x + width, y + height], fill=color)
    # Subtle dashed texture
    for offset_x in range(x + 10, x + width - 10, 16):
        draw.line([(offset_x, y + 2), (offset_x + 4, y + height - 2)], fill="#FFFFFF", width=1)


def _draw_doodle(draw: ImageDraw.ImageDraw, doodle_type: str, x: int, y: int, size: int, color: str):
    """Draws hand-drawn vector doodle inside bounding box (x, y, x+size, y+size)."""
    cx = x + size // 2
    cy = y + size // 2
    radius = size // 2 - 10

    if doodle_type == "lightbulb":
        # Bulb outline
        draw.ellipse([cx - 28, cy - 36, cx + 28, cy + 12], outline=color, width=3)
        # Bulb base
        draw.rectangle([cx - 14, cy + 12, cx + 14, cy + 26], outline=color, width=2)
        draw.line([(cx - 10, cy + 18), (cx + 10, cy + 18)], fill=color, width=2)
        draw.arc([cx - 8, cy + 24, cx + 8, cy + 32], 0, 180, fill=color, width=2)
        # Filament
        draw.line([(cx - 10, cy - 8), (cx, cy - 18), (cx + 10, cy - 8)], fill=color, width=2)
        # Glow rays
        draw.line([(cx, cy - 48), (cx, cy - 42)], fill=color, width=3)
        draw.line([(cx - 40, cy - 36), (cx - 32, cy - 30)], fill=color, width=3)
        draw.line([(cx + 40, cy - 36), (cx + 32, cy - 30)], fill=color, width=3)
        draw.line([(cx - 44, cy - 10), (cx - 36, cy - 10)], fill=color, width=3)
        draw.line([(cx + 44, cy - 10), (cx + 36, cy - 10)], fill=color, width=3)

    elif doodle_type == "brain":
        # Brain dual lobes
        draw.ellipse([cx - 36, cy - 30, cx, cy + 24], outline=color, width=3)
        draw.ellipse([cx, cy - 30, cx + 36, cy + 24], outline=color, width=3)
        # Brain wrinkles / convolutions
        draw.arc([cx - 26, cy - 18, cx - 6, cy + 6], 30, 210, fill=color, width=2)
        draw.arc([cx + 6, cy - 18, cx + 26, cy + 6], 150, 330, fill=color, width=2)
        draw.line([(cx, cy - 24), (cx, cy + 18)], fill=color, width=2)
        # Sparkles
        draw.text((cx - 48, cy - 42), "✦", fill=color, font=_get_font(18, True))
        draw.text((cx + 38, cy - 42), "✦", fill=color, font=_get_font(18, True))

    elif doodle_type == "flowchart":
        # Box 1 -> Box 2 -> Box 3
        draw.rounded_rectangle([cx - 44, cy - 38, cx + 44, cy - 16], radius=6, outline=color, width=2)
        draw.line([(cx, cy - 16), (cx, cy - 2)], fill=color, width=2)
        # Arrowhead 1
        draw.line([(cx - 4, cy - 7), (cx, cy - 2), (cx + 4, cy - 7)], fill=color, width=2)
        
        draw.rounded_rectangle([cx - 48, cy - 2, cx + 48, cy + 20], radius=6, outline=color, width=2)
        draw.line([(cx, cy + 20), (cx, cy + 34)], fill=color, width=2)
        # Arrowhead 2
        draw.line([(cx - 4, cy + 29), (cx, cy + 34), (cx + 4, cy + 29)], fill=color, width=2)
        
        draw.rounded_rectangle([cx - 40, cy + 34, cx + 40, cy + 50], radius=6, outline=color, width=2)

    elif doodle_type == "target":
        # Concentric rings
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], outline=color, width=3)
        draw.ellipse([cx - radius + 14, cy - radius + 14, cx + radius - 14, cy + radius - 14], outline=color, width=2)
        draw.ellipse([cx - 10, cy - 10, cx + 10, cy + 10], fill=color)
        # Arrow hitting bullseye
        draw.line([(cx + 36, cy - 36), (cx + 6, cy - 6)], fill=TEXT_COLOR, width=3)
        draw.polygon([(cx + 34, cy - 44), (cx + 44, cy - 34), (cx + 38, cy - 38)], fill=TEXT_COLOR)

    elif doodle_type == "gears":
        # Primary gear
        draw.ellipse([cx - 28, cy - 28, cx + 20, cy + 20], outline=color, width=3)
        draw.ellipse([cx - 12, cy - 12, cx + 4, cy + 4], outline=color, width=2)
        # Teeth
        for angle in range(0, 360, 45):
            rad = math.radians(angle)
            gx = cx - 4 + int(28 * math.cos(rad))
            gy = cy - 4 + int(28 * math.sin(rad))
            draw.rectangle([gx - 3, gy - 3, gx + 3, gy + 3], fill=color)
        # Secondary small gear
        draw.ellipse([cx + 12, cy + 12, cx + 38, cy + 38], outline=color, width=2)
        draw.ellipse([cx + 20, cy + 20, cx + 30, cy + 30], outline=color, width=1)

    else:  # checklist or default
        draw.rounded_rectangle([cx - 36, cy - 42, cx + 36, cy + 42], radius=8, outline=color, width=3)
        # Clip top
        draw.rounded_rectangle([cx - 16, cy - 48, cx + 16, cy - 36], radius=4, fill=color)
        # Check rows
        for row_y in [cy - 20, cy, cy + 20]:
            draw.rectangle([cx - 24, row_y - 6, cx - 14, row_y + 4], outline=color, width=2)
            draw.line([(cx - 23, row_y), (cx - 18, row_y + 3), (cx - 12, row_y - 4)], fill=color, width=2)
            draw.line([(cx - 8, row_y), (cx + 24, row_y)], fill=TEXT_COLOR, width=2)


def _wrap_text(text: str, font: ImageFont.ImageFont, max_width: int, draw: ImageDraw.ImageDraw) -> list:
    """Wraps text cleanly into multiple lines that fit max_width."""
    words = text.split()
    if not words:
        return []
    lines = []
    current_line = []

    for word in words:
        test_line = " ".join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]

    if current_line:
        lines.append(" ".join(current_line))
    return lines


def render_scene_frame(
    scene_data: dict,
    video_title: str,
    total_scenes: int,
    stage: int = 3
) -> Image.Image:
    """
    Renders a single frame for a scene at a given progressive reveal stage (0, 1, 2, or 3).
    Stage 0: Canvas background + Header & Scene Tracker
    Stage 1: Stage 0 + Category Badge & Vector Doodle
    Stage 2: Stage 1 + Key Point Callout Card
    Stage 3: Stage 2 + Bullet Points & Footer Stamp (Complete)
    """
    img = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # 1. Background Grid / Paper Lines
    for y in range(50, CANVAS_HEIGHT, 36):
        draw.line([(0, y), (CANVAS_WIDTH, y)], fill=PAPER_LINE_COLOR, width=1)
    # Left margin guide line
    draw.line([(70, 0), (70, CANVAS_HEIGHT)], fill="#E5DCCE", width=1)

    # 2. Top Banner / Header Row
    # Washi Tape Top-Center
    _draw_washi_tape(draw, CANVAS_WIDTH // 2 - 120, 16, 240, 24, color="#DDD6FE")
    tape_font = _get_font(14, bold=True)
    draw.text((CANVAS_WIDTH // 2, 28), "★ KUCHU PUCHU AI • STUDY FOLIO ★", fill="#6D28D9", font=tape_font, anchor="mm")

    # Main Video Title (Left Top)
    title_font = _get_font(20, bold=True)
    truncated_title = video_title[:38] + ("..." if len(video_title) > 38 else "")
    draw.text((90, 32), f"📓 {truncated_title}", fill=TEXT_COLOR, font=title_font)

    # Scene Progress Tracker (Right Top)
    scene_id = scene_data.get("scene_id", 1)
    tracker_text = f"Scene {scene_id} / {total_scenes}"
    tracker_font = _get_font(18, bold=True)
    draw.text((CANVAS_WIDTH - 90, 32), tracker_text, fill=TEXT_MUTED, font=tracker_font, anchor="ra")

    # Progress Dots
    dot_start_x = CANVAS_WIDTH - 90 - (total_scenes * 14)
    for i in range(1, total_scenes + 1):
        dot_color = "#2A9D8F" if i <= scene_id else "#D5CCBF"
        draw.ellipse([dot_start_x + (i * 14), 48, dot_start_x + (i * 14) + 8, 56], fill=dot_color)

    # Stage 0 completes the canvas header frame
    if stage < 1:
        return img

    accent_color = scene_data.get("accent_color", "#2A9D8F")
    badge_text = scene_data.get("badge", f"CONCEPT {scene_id}")
    header_text = scene_data.get("header", f"Concept {scene_id}")

    # 3. Left Card: Concept Taxonomy & Vector Doodle
    left_card_x = 90
    left_card_y = 80
    left_card_w = 400
    left_card_h = 570

    # Card Shadow & Card Body
    draw.rounded_rectangle([left_card_x + 4, left_card_y + 4, left_card_x + left_card_w + 4, left_card_y + left_card_h + 4], radius=14, fill="#EFE8DC")
    draw.rounded_rectangle([left_card_x, left_card_y, left_card_x + left_card_w, left_card_y + left_card_h], radius=14, fill=CARD_BG, outline=BORDER_COLOR, width=2)

    # Category Badge Pill
    badge_font = _get_font(15, bold=True)
    draw.rounded_rectangle([left_card_x + 24, left_card_y + 24, left_card_x + 160, left_card_y + 54], radius=15, fill=accent_color)
    draw.text((left_card_x + 92, left_card_y + 39), f"✦ {badge_text}", fill="#FFFFFF", font=badge_font, anchor="mm")

    # Scene Header (Title of Scene)
    scene_header_font = _get_font(28, bold=True)
    header_lines = _wrap_text(header_text, scene_header_font, left_card_w - 48, draw)
    hy = left_card_y + 76
    for hline in header_lines[:2]:
        draw.text((left_card_x + 24, hy), hline, fill=TEXT_COLOR, font=scene_header_font)
        hy += 34

    # Doodle Box
    doodle_box_y = hy + 18
    doodle_box_size = 230
    doodle_box_x = left_card_x + (left_card_w - doodle_box_size) // 2
    draw.rounded_rectangle([doodle_box_x, doodle_box_y, doodle_box_x + doodle_box_size, doodle_box_y + doodle_box_size], radius=12, fill="#FBF9F4", outline=BORDER_COLOR, width=1)
    
    # Vector Doodle
    doodle_type = scene_data.get("doodle_type", "lightbulb")
    _draw_doodle(draw, doodle_type, doodle_box_x + 20, doodle_box_y + 20, doodle_box_size - 40, accent_color)

    # Hand-drawn script caption below doodle
    caption_font = _get_font(16, bold=False)
    draw.text((left_card_x + left_card_w // 2, doodle_box_y + doodle_box_size + 24), f"Visual concept diagram ↑", fill=TEXT_MUTED, font=caption_font, anchor="mm")

    # If stage == 1, return now (Header + Doodle revealed)
    if stage < 2:
        return img

    # 4. Right Card: Core Insight Callout & Bullet Takeaways
    right_card_x = 515
    right_card_y = 80
    right_card_w = 675
    right_card_h = 570

    draw.rounded_rectangle([right_card_x + 4, right_card_y + 4, right_card_x + right_card_w + 4, right_card_y + right_card_h + 4], radius=14, fill="#EFE8DC")
    draw.rounded_rectangle([right_card_x, right_card_y, right_card_x + right_card_w, right_card_y + right_card_h], radius=14, fill=CARD_BG, outline=BORDER_COLOR, width=2)

    # Core Insight Marker Box
    kp_box_x = right_card_x + 28
    kp_box_y = right_card_y + 28
    kp_box_w = right_card_w - 56
    kp_box_h = 160

    draw.rounded_rectangle([kp_box_x, kp_box_y, kp_box_x + kp_box_w, kp_box_y + kp_box_h], radius=10, fill=HIGHLIGHT_BG, outline=HIGHLIGHT_BORDER, width=2)

    # Insight Kicker
    kicker_font = _get_font(15, bold=True)
    draw.text((kp_box_x + 20, kp_box_y + 20), "💡 CORE TAKEAWAY & INTUITION", fill="#B45309", font=kicker_font)

    # Key Point Text
    key_point = scene_data.get("key_point", "Crucial takeaway explained clearly.")
    kp_font = _get_font(22, bold=True)
    kp_lines = _wrap_text(key_point, kp_font, kp_box_w - 40, draw)
    kpy = kp_box_y + 48
    for line in kp_lines[:3]:
        draw.text((kp_box_x + 20, kpy), line, fill="#78350F", font=kp_font)
        kpy += 32

    # If stage == 2, return now (Key Point revealed)
    if stage < 3:
        return img

    # 5. Bullet Points (Stage 3 Complete Scene)
    bullets_header_font = _get_font(18, bold=True)
    draw.text((right_card_x + 28, right_card_y + 214), "Key Explanations & Practical Context:", fill=TEXT_COLOR, font=bullets_header_font)

    bullets = scene_data.get("bullet_points", [])
    bullet_font = _get_font(20, bold=False)
    by = right_card_y + 252

    for bullet in bullets[:3]:
        # Hand-drawn checkmark badge
        draw.rounded_rectangle([right_card_x + 28, by - 2, right_card_x + 58, by + 28], radius=6, fill="#ECFDF5", outline="#10B981", width=1)
        draw.text((right_card_x + 43, by + 13), "✓", fill="#059669", font=_get_font(18, True), anchor="mm")

        # Bullet text wrapped
        b_lines = _wrap_text(bullet, bullet_font, right_card_w - 110, draw)
        b_text_y = by
        for bline in b_lines[:2]:
            draw.text((right_card_x + 72, b_text_y), bline, fill=TEXT_COLOR, font=bullet_font)
            b_text_y += 28

        by = max(by + 44, b_text_y + 12)

    # Bottom Archival Folio Stamp
    footer_font = _get_font(15, bold=False)
    draw.line([(right_card_x + 28, right_card_h + 30), (right_card_x + right_card_w - 28, right_card_h + 30)], fill=BORDER_COLOR, width=1)
    draw.text((right_card_x + 28, right_card_h + 40), "✏️ Kuchu Puchu AI • Archival Whiteboard Summary Folio", fill=TEXT_MUTED, font=footer_font)
    draw.text((right_card_x + right_card_w - 28, right_card_h + 40), "Obsidian & Video Ready ↗", fill=accent_color, font=footer_font, anchor="ra")

    return img
