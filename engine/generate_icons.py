"""
Generates custom Micelio Desktop brand icons (`public/icon.svg`, `public/icon.png`, `public/icon.ico`).
Design: Dark obsidian rounded-squircle badge (#0D0D11) with a glowing Santander-red (#EC0000)
mycelium neural network node graph.
"""

import struct
import zlib
from pathlib import Path

PUBLIC_DIR = Path(__file__).resolve().parent.parent / "public"
PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

SVG_CONTENT = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" fill="none">
  <defs>
    <radialGradient id="bgGlow" cx="50%" cy="30%" r="75%">
      <stop offset="0%" stop-color="#1C191E" />
      <stop offset="100%" stop-color="#09090B" />
    </radialGradient>
    <linearGradient id="redAccent" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#FF3B3B" />
      <stop offset="100%" stop-color="#EC0000" />
    </linearGradient>
  </defs>

  <!-- Rounded Squircle Background -->
  <rect x="12" y="12" width="232" height="232" rx="56" fill="url(#bgGlow)" stroke="#27272A" stroke-width="6"/>

  <!-- Mycelium / Agentic Network Connections -->
  <g stroke="url(#redAccent)" stroke-width="10" stroke-linecap="round" stroke-linejoin="round">
    <path d="M128 196 V120" />
    <path d="M128 120 L74 78" />
    <path d="M128 120 L182 78" />
    <path d="M128 148 L70 144" />
    <path d="M128 148 L186 144" />
    <path d="M74 78 L128 56 L182 78" stroke-opacity="0.45" stroke-width="6" />
  </g>

  <!-- Nodes -->
  <circle cx="128" cy="120" r="18" fill="url(#redAccent)" />
  <circle cx="128" cy="120" r="7" fill="#FFFFFF" />

  <circle cx="74" cy="78" r="14" fill="url(#redAccent)" />
  <circle cx="182" cy="78" r="14" fill="url(#redAccent)" />
  <circle cx="128" cy="56" r="11" fill="#FF5555" />

  <circle cx="70" cy="144" r="11" fill="#EC0000" />
  <circle cx="186" cy="144" r="11" fill="#EC0000" />
  <circle cx="128" cy="196" r="13" fill="#FFFFFF" />
</svg>
"""


def make_png_and_ico(width: int = 256, height: int = 256) -> tuple[bytes, bytes]:
    """Render a crisp 256x256 RGBA PNG & Windows .ICO of the Micelio neural-mycelium emblem."""
    import math

    pixels = bytearray(width * height * 4)

    def blend_pixel(x: int, y: int, r: int, g: int, b: int, a: float) -> None:
        if x < 0 or x >= width or y < 0 or y >= height or a <= 0:
            return
        idx = (y * width + x) * 4
        inv = 1.0 - a
        pixels[idx] = min(255, int(r * a + pixels[idx] * inv))
        pixels[idx + 1] = min(255, int(g * a + pixels[idx + 1] * inv))
        pixels[idx + 2] = min(255, int(b * a + pixels[idx + 2] * inv))
        pixels[idx + 3] = min(255, int(255 * a + pixels[idx + 3] * inv))

    # 1. Rounded squircle background (#0B0B0F with subtle red radial aura)
    margin = 14
    radius = 52
    for y in range(margin, height - margin):
        for x in range(margin, width - margin):
            dx = max(0, max(margin + radius - x, x - (width - margin - radius - 1)))
            dy = max(0, max(margin + radius - y, y - (height - margin - radius - 1)))
            dist = math.hypot(dx, dy)
            if dist <= radius + 1.0:
                alpha = max(0.0, min(1.0, radius + 0.5 - dist))
                # Radial glow near center
                cdist = math.hypot(x - 128, y - 115) / 140.0
                r_bg = int(14 + max(0.0, 1.0 - cdist) * 24)
                g_bg = int(14 + max(0.0, 1.0 - cdist) * 4)
                b_bg = int(18 + max(0.0, 1.0 - cdist) * 8)
                # Border highlight
                if abs(dist - radius) < 2.2:
                    r_bg, g_bg, b_bg = 65, 25, 28
                blend_pixel(x, y, r_bg, g_bg, b_bg, alpha)

    def draw_segment(x1: float, y1: float, x2: float, y2: float, thickness: float, color: tuple[int, int, int]) -> None:
        min_x = max(0, int(min(x1, x2) - thickness - 2))
        max_x = min(width - 1, int(max(x1, x2) + thickness + 2))
        min_y = max(0, int(min(y1, y2) - thickness - 2))
        max_y = min(height - 1, int(max(y1, y2) + thickness + 2))
        vx, vy = x2 - x1, y2 - y1
        seg_len_sq = vx * vx + vy * vy
        for py in range(min_y, max_y + 1):
            for px in range(min_x, max_x + 1):
                t = 0.0 if seg_len_sq == 0 else max(0.0, min(1.0, ((px - x1) * vx + (py - y1) * vy) / seg_len_sq))
                proj_x = x1 + t * vx
                proj_y = y1 + t * vy
                d = math.hypot(px - proj_x, py - proj_y)
                if d <= thickness + 1.0:
                    a = max(0.0, min(1.0, thickness + 0.5 - d))
                    blend_pixel(px, py, color[0], color[1], color[2], a)

    def draw_circle(cx: float, cy: float, r: float, color: tuple[int, int, int]) -> None:
        for py in range(max(0, int(cy - r - 2)), min(height, int(cy + r + 3))):
            for px in range(max(0, int(cx - r - 2)), min(width, int(cx + r + 3))):
                d = math.hypot(px - cx, py - cy)
                if d <= r + 1.0:
                    a = max(0.0, min(1.0, r + 0.5 - d))
                    blend_pixel(px, py, color[0], color[1], color[2], a)

    # 2. Draw Mycelium Branches
    red_main = (236, 0, 0)
    red_soft = (255, 65, 65)
    white = (250, 250, 252)

    draw_segment(74, 78, 128, 56, 3.5, (160, 25, 25))
    draw_segment(128, 56, 182, 78, 3.5, (160, 25, 25))
    draw_segment(128, 196, 128, 120, 6.0, red_main)
    draw_segment(128, 120, 74, 78, 5.5, red_soft)
    draw_segment(128, 120, 182, 78, 5.5, red_soft)
    draw_segment(128, 148, 70, 144, 4.5, red_main)
    draw_segment(128, 148, 186, 144, 4.5, red_main)

    # 3. Draw Nodes
    draw_circle(128, 120, 17, red_soft)
    draw_circle(128, 120, 7, white)
    draw_circle(74, 78, 13, red_soft)
    draw_circle(182, 78, 13, red_soft)
    draw_circle(128, 56, 10, red_soft)
    draw_circle(70, 144, 10, red_main)
    draw_circle(186, 144, 10, red_main)
    draw_circle(128, 196, 12, white)

    # Encode as PNG
    raw_rows = bytearray()
    for y in range(height):
        raw_rows.append(0)  # Filter type 0
        row_start = y * width * 4
        raw_rows.extend(pixels[row_start : row_start + width * 4])

    def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    idat = zlib.compress(bytes(raw_rows), 9)
    png_bytes = b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", ihdr) + png_chunk(b"IDAT", idat) + png_chunk(b"IEND", b"")

    # Wrap PNG inside a standard Windows .ICO container
    ico_header = struct.pack("<HHH", 0, 1, 1)
    ico_entry = struct.pack(
        "<BBBBHHII",
        0,  # 256px width
        0,  # 256px height
        0,
        0,
        1,
        32,
        len(png_bytes),
        6 + 16,
    )
    ico_bytes = ico_header + ico_entry + png_bytes
    return png_bytes, ico_bytes


if __name__ == "__main__":
    (PUBLIC_DIR / "icon.svg").write_text(SVG_CONTENT, encoding="utf-8")
    png_data, ico_data = make_png_and_ico()
    (PUBLIC_DIR / "icon.png").write_bytes(png_data)
    (PUBLIC_DIR / "icon.ico").write_bytes(ico_data)
    print("Generated public/icon.svg, public/icon.png, and public/icon.ico successfully.")
