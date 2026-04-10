"""Generate SeatScout deployment architecture diagram as PNG using Pillow."""
from PIL import Image, ImageDraw, ImageFont
import math

W, H = 1400, 900
img = Image.new("RGB", (W, H), "#ffffff")
draw = ImageDraw.Draw(img)

# Try to load a system font, fall back to default
def get_font(size, bold=False):
    paths = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except:
            pass
    return ImageFont.load_default()

F_SM = get_font(13)
F_MD = get_font(15)
F_LG = get_font(17, bold=True)
F_TITLE = get_font(13)

def rr(x, y, w, h, fill, outline, radius=12, lw=2):
    draw.rounded_rectangle([x, y, x+w, y+h], radius=radius, fill=fill, outline=outline, width=lw)

def label(x, y, w, text, font, color="#1e1e1e", align="center"):
    bbox = font.getbbox(text)
    tw = bbox[2] - bbox[0]
    if align == "center":
        tx = x + (w - tw) // 2
    else:
        tx = x + 6
    draw.text((tx, y), text, fill=color, font=font)

def zone(x, y, w, h, fill, outline, title, title_color):
    draw.rounded_rectangle([x, y, x+w, y+h], radius=16, fill=fill, outline=outline, width=2)
    label(x+8, y+8, w, title, F_TITLE, title_color, align="left")

def box(x, y, w, h, fill, outline, line1, line2=None):
    rr(x, y, w, h, fill, outline)
    if line2:
        label(x, y+10, w, line1, F_MD, "#1e1e1e")
        label(x, y+30, w, line2, F_SM, "#555555")
    else:
        label(x, y+14, w, line1, F_MD, "#1e1e1e")

def arrow(x1, y1, x2, y2, color="#555555", dashed=False):
    if dashed:
        # draw dashed line
        dx, dy = x2-x1, y2-y1
        dist = math.sqrt(dx*dx + dy*dy)
        steps = int(dist / 10)
        for i in range(0, steps, 2):
            sx = x1 + dx * i / steps
            sy = y1 + dy * i / steps
            ex = x1 + dx * min(i+1, steps) / steps
            ey = y1 + dy * min(i+1, steps) / steps
            draw.line([(sx, sy), (ex, ey)], fill=color, width=2)
    else:
        draw.line([(x1, y1), (x2, y2)], fill=color, width=2)
    # arrowhead
    dx, dy = x2-x1, y2-y1
    dist = math.sqrt(dx*dx + dy*dy)
    if dist == 0: return
    ux, uy = dx/dist, dy/dist
    lx = x2 - ux*12 - uy*6
    ly = y2 - uy*12 + ux*6
    rx = x2 - ux*12 + uy*6
    ry = y2 - uy*12 - ux*6
    draw.polygon([(x2,y2),(lx,ly),(rx,ry)], fill=color)

# ── Title ──────────────────────────────────────────────────────────────────────
F_BIG = get_font(22, bold=True)
label(0, 18, W, "SeatScout — Deployment Architecture", F_BIG, "#1e1e1e")

# ── User ──────────────────────────────────────────────────────────────────────
box(580, 58, 220, 52, "#a5d8ff", "#4a9eed", "User Browser (Chat UI)")

# ── Google Cloud zone (left column) ──────────────────────────────────────────
zone(30, 130, 240, 320, "#f0fdf4", "#22c55e", "Google Cloud Platform", "#15803d")

# Firebase
box(48, 165, 205, 62, "#bbf7d0", "#22c55e", "Firebase Hosting", "web/index.html · CDN · Free tier")

# Firestore
box(48, 300, 205, 62, "#bbf7d0", "#22c55e", "Firestore (NoSQL)", "Usage logs · movieseats-app project")

# ── Railway zone (center column) ──────────────────────────────────────────────
zone(300, 130, 240, 320, "#fffbeb", "#f59e0b", "Railway (PaaS)", "#b45309")

# FastAPI
box(315, 168, 210, 62, "#fde68a", "#f59e0b", "FastAPI Server", "Python 3.12 · Docker · SSE streams")

# Playwright
box(315, 248, 210, 58, "#fde68a", "#f59e0b", "Playwright", "Headless Chromium · Seat maps")

# Scorer
box(315, 320, 210, 58, "#fde68a", "#f59e0b", "Seat Scorer", "Center 40% · Row 35% · Adj 25%")

# ── AWS zone (right column) ───────────────────────────────────────────────────
zone(570, 130, 290, 190, "#fff7ed", "#f97316", "AWS Bedrock (us-east-1)", "#c2410c")

# Haiku
box(585, 165, 260, 58, "#fed7aa", "#f97316", "Claude Haiku 4.5", "Intent · Ranking · Chat replies")

# Sonnet
box(585, 242, 260, 58, "#fed7aa", "#f97316", "Claude Sonnet 4.6", "Movie search · Complex reasoning")

# ── Brave Search (external) ───────────────────────────────────────────────────
zone(570, 340, 290, 115, "#eef2ff", "#6366f1", "External APIs", "#3730a3")

box(585, 368, 260, 58, "#e0e7ff", "#6366f1", "Brave Search API", "Live movie/theater data · 2k/mo free")

# Cinemark
box(900, 190, 265, 58, "#fce7f3", "#ec4899", "Cinemark.com", "DOM scraping · .seatAvailable class")

# ── GitHub ────────────────────────────────────────────────────────────────────
box(440, 530, 300, 62, "#f1f5f9", "#475569", "GitHub: sarathk402/seatscout", "main branch · CI/CD auto-deploy")

# ── Arrows ────────────────────────────────────────────────────────────────────
# User → Firebase
arrow(620, 110, 160, 165, "#4a9eed")
# User → FastAPI
arrow(660, 110, 430, 168, "#4a9eed")
# FastAPI → Haiku
arrow(525, 200, 585, 194, "#f97316")
# FastAPI → Brave
arrow(525, 220, 585, 385, "#6366f1")
# Playwright → Cinemark
arrow(525, 278, 900, 220, "#ec4899")
# FastAPI → Firestore (dashed)
arrow(315, 220, 253, 320, "#22c55e", dashed=True)
# GitHub → Railway (dashed CI/CD)
arrow(530, 530, 430, 452, "#475569", dashed=True)
# GitHub → Firebase (dashed CI/CD)
arrow(470, 530, 160, 227, "#475569", dashed=True)

# ── Legend ────────────────────────────────────────────────────────────────────
lx, ly = 900, 340
rr(lx, ly, 265, 180, "#f9fafb", "#d1d5db", radius=8)
label(lx, ly+8, 265, "Legend", get_font(14, bold=True), "#374151")
items = [
    ("━━", "#4a9eed", "User request / response"),
    ("━━", "#f97316", "Claude AI calls (Bedrock)"),
    ("━━", "#6366f1", "Brave Search (RAG)"),
    ("━━", "#ec4899", "Playwright scraping"),
    ("- -", "#22c55e", "Firestore logging"),
    ("- -", "#475569", "CI/CD deployment"),
]
for i, (sym, clr, desc) in enumerate(items):
    yy = ly + 35 + i * 23
    draw.text((lx+12, yy), sym, fill=clr, font=F_MD)
    draw.text((lx+45, yy), desc, fill="#374151", font=F_SM)

# Save
out = "/Users/kundas/script/movieseats/.claude/worktrees/wonderful-noether/docs/Excalidraw.png"
img.save(out, "PNG", dpi=(144, 144))
print(f"Saved: {out}")
