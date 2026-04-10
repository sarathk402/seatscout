"""Generate SeatScout deployment architecture diagram as PNG using Pillow."""
from PIL import Image, ImageDraw, ImageFont
import math

W, H = 1580, 1020
img = Image.new("RGB", (W, H), "#ffffff")
draw = ImageDraw.Draw(img)

def get_font(size, bold=False):
    paths = ["/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/Arial.ttf"]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except:
            pass
    return ImageFont.load_default()

F_XS   = get_font(11)
F_SM   = get_font(13)
F_MD   = get_font(15)
F_BOLD = get_font(15, bold=True)
F_LG   = get_font(22, bold=True)
F_ZONE = get_font(13)

def rr(x, y, w, h, fill, outline, radius=12, lw=2):
    draw.rounded_rectangle([x, y, x+w, y+h], radius=radius, fill=fill, outline=outline, width=lw)

def text_center(x, y, w, text, font, color="#1e1e1e"):
    bbox = font.getbbox(text)
    tw = bbox[2] - bbox[0]
    draw.text((x + (w - tw) // 2, y), text, fill=color, font=font)

def text_left(x, y, text, font, color="#1e1e1e"):
    draw.text((x, y), text, fill=color, font=font)

def zone(x, y, w, h, fill, outline, title, title_color):
    draw.rounded_rectangle([x, y, x+w, y+h], radius=16, fill=fill, outline=outline, width=2)
    text_left(x+10, y+9, title, F_ZONE, title_color)

def box(x, y, w, h, fill, outline, line1, line2=None):
    rr(x, y, w, h, fill, outline)
    if line2:
        text_center(x, y+9, w, line1, F_MD)
        text_center(x, y+30, w, line2, F_XS, "#555")
    else:
        text_center(x, y+13, w, line1, F_MD)

def arrow(x1, y1, x2, y2, color="#555", dashed=False, lw=2):
    if dashed:
        dx, dy = x2-x1, y2-y1
        dist = math.sqrt(dx*dx+dy*dy)
        steps = max(int(dist/10), 1)
        for i in range(0, steps, 2):
            sx = x1 + dx*i/steps; sy = y1 + dy*i/steps
            ex = x1 + dx*min(i+1,steps)/steps; ey = y1 + dy*min(i+1,steps)/steps
            draw.line([(sx,sy),(ex,ey)], fill=color, width=lw)
    else:
        draw.line([(x1,y1),(x2,y2)], fill=color, width=lw)
    dx, dy = x2-x1, y2-y1
    dist = math.sqrt(dx*dx+dy*dy)
    if dist == 0: return
    ux, uy = dx/dist, dy/dist
    draw.polygon([(x2,y2),(x2-ux*12-uy*6, y2-uy*12+ux*6),(x2-ux*12+uy*6, y2-uy*12-ux*6)], fill=color)

def flow_label(x1, y1, x2, y2, step, desc, example, color):
    """Draw a step badge + description near midpoint of arrow."""
    mx, my = (x1+x2)//2, (y1+y2)//2
    # badge circle
    r = 10
    draw.ellipse([mx-r, my-r, mx+r, my+r], fill=color, outline=color)
    bw = get_font(12, bold=True).getbbox(step)
    bww = bw[2]-bw[0]
    draw.text((mx - bww//2, my-8), step, fill="white", font=get_font(12, bold=True))
    # label box
    pad = 5
    lines = [desc, example]
    widths = [F_SM.getbbox(l)[2]-F_SM.getbbox(l)[0] for l in lines]
    bx_w = max(widths) + pad*2
    bx_h = 36
    bx = mx + 14
    by = my - bx_h//2
    rr(bx, by, bx_w, bx_h, "#ffffffee" if True else "#fff", color, radius=6, lw=1)
    draw.text((bx+pad, by+3), desc, fill=color, font=F_SM)
    draw.text((bx+pad, by+20), example, fill="#555", font=F_XS)

# ═══════════════════════════════════════════════════════════════════════════════
# TITLE
# ═══════════════════════════════════════════════════════════════════════════════
text_center(0, 18, W, "SeatScout — Request Flow & Deployment Architecture", F_LG, "#1e1e1e")

# ═══════════════════════════════════════════════════════════════════════════════
# USER
# ═══════════════════════════════════════════════════════════════════════════════
box(670, 58, 240, 52, "#a5d8ff", "#4a9eed", 'User: "Dhurandhar 75035, 2 seats"')

# ═══════════════════════════════════════════════════════════════════════════════
# GOOGLE CLOUD ZONE
# ═══════════════════════════════════════════════════════════════════════════════
zone(30, 135, 235, 370, "#f0fdf4", "#22c55e", "Google Cloud Platform", "#15803d")
box(48, 172, 200, 62, "#bbf7d0", "#22c55e", "Firebase Hosting", "Serves index.html · Free CDN")
box(48, 318, 200, 62, "#bbf7d0", "#22c55e", "Firestore", "Async usage logging")

# ═══════════════════════════════════════════════════════════════════════════════
# RAILWAY ZONE
# ═══════════════════════════════════════════════════════════════════════════════
zone(295, 135, 255, 370, "#fffbeb", "#f59e0b", "Railway (PaaS)", "#b45309")
box(312, 172, 222, 62, "#fde68a", "#f59e0b", "FastAPI Server", "Orchestrates all steps · SSE streaming")
box(312, 268, 222, 58, "#fde68a", "#f59e0b", "Playwright", "Opens 6 showtime tabs in parallel")
box(312, 348, 222, 58, "#fde68a", "#f59e0b", "Seat Scorer", "Math: center 40% · row 35% · adj 25%")

# ═══════════════════════════════════════════════════════════════════════════════
# AWS BEDROCK ZONE
# ═══════════════════════════════════════════════════════════════════════════════
zone(582, 135, 320, 230, "#fff7ed", "#f97316", "AWS Bedrock  (us-east-1)", "#c2410c")

# Haiku — annotated with when it's called
rr(598, 170, 288, 72, "#fed7aa", "#f97316")
text_center(598, 170+8, 288, "Claude Haiku 4.5", F_BOLD, "#9a3412")
text_center(598, 170+28, 288, "Steps ① & ⑤  —  every request", F_XS, "#92400e")
text_center(598, 170+44, 288, "Parse intent · rank results · chat replies", F_XS, "#78350f")

# Sonnet — annotated with when it's called
rr(598, 260, 288, 72, "#fed7aa", "#f97316")
text_center(598, 260+8, 288, "Claude Sonnet 4.6", F_BOLD, "#9a3412")
text_center(598, 260+28, 288, "Step ②  —  only on new movie lookup", F_XS, "#92400e")
text_center(598, 260+44, 288, "Resolve movie name + reason over search results", F_XS, "#78350f")

# ═══════════════════════════════════════════════════════════════════════════════
# BRAVE SEARCH
# ═══════════════════════════════════════════════════════════════════════════════
zone(582, 390, 320, 115, "#eef2ff", "#6366f1", "External APIs", "#3730a3")
box(598, 420, 288, 58, "#e0e7ff", "#6366f1", "Brave Search API", "Step ②  —  fetches 5 live results for Sonnet")

# ═══════════════════════════════════════════════════════════════════════════════
# CINEMARK
# ═══════════════════════════════════════════════════════════════════════════════
box(960, 265, 275, 62, "#fce7f3", "#ec4899", "Cinemark.com", "Step ③  —  DOM: .seatAvailable / .seatUnavailable")

# ═══════════════════════════════════════════════════════════════════════════════
# GITHUB
# ═══════════════════════════════════════════════════════════════════════════════
box(500, 580, 300, 62, "#f1f5f9", "#475569", "GitHub: sarathk402/seatscout", "CI/CD → Railway + Firebase")

# ═══════════════════════════════════════════════════════════════════════════════
# FLOW STEP BOXES (bottom strip)
# ═══════════════════════════════════════════════════════════════════════════════
steps = [
    ("①", "#f97316", "Parse intent",        "Haiku extracts: movie='Dhurandhar',\nzip='75035', seats=2, format=any"),
    ("②", "#f97316", "Resolve movie",       "Sonnet + Brave: 'Dhurandhar' →\ncinemark slug 'dhurandhar'"),
    ("③", "#ec4899", "Scrape seats",        "Playwright opens 6 showtime tabs,\nreturns available seat grids"),
    ("④", "#06b6d4", "Score seats",         "Scorer ranks each seat: e.g.\nRow F center = 1.18/1.25"),
    ("⑤", "#f97316", "Rank & recommend",    "Haiku picks best option,\nwrites recommendation blurb"),
    ("⑥", "#4a9eed", "Stream to user",      "SSE events: status → results\n→ recommendation → done"),
]
sx, sy, sw, sh = 30, 690, 245, 88
for i, (num, clr, title, detail) in enumerate(steps):
    bx = sx + i*(sw+8)
    rr(bx, sy, sw, sh, "#f9fafb", clr, radius=10)
    # step number badge
    draw.ellipse([bx+8, sy+8, bx+32, sy+32], fill=clr)
    nbbox = get_font(14, bold=True).getbbox(num)
    nw = nbbox[2]-nbbox[0]
    draw.text((bx+20-nw//2, sy+10), num, fill="white", font=get_font(14, bold=True))
    draw.text((bx+40, sy+10), title, fill=clr, font=F_BOLD)
    for j, line in enumerate(detail.split("\n")):
        draw.text((bx+8, sy+36+j*18), line, fill="#374151", font=F_XS)

# ═══════════════════════════════════════════════════════════════════════════════
# ARROWS
# ═══════════════════════════════════════════════════════════════════════════════
# User → Firebase (browser loads UI)
arrow(700, 110, 165, 172, "#4a9eed")
draw.text((245, 130), "loads UI", fill="#4a9eed", font=F_XS)

# User → FastAPI (sends chat message)
arrow(750, 110, 438, 172, "#4a9eed")
draw.text((560, 118), "chat message (SSE)", fill="#4a9eed", font=F_XS)

# FastAPI → Haiku  ① Parse intent
arrow(534, 200, 598, 206, "#f97316", lw=2)
draw.text((537, 183), "① parse intent", fill="#f97316", font=F_XS)

# FastAPI → Sonnet  ② Resolve movie (only new lookup)
arrow(534, 215, 598, 296, "#f97316", lw=2)
draw.text((537, 240), "② resolve movie", fill="#f97316", font=F_XS)

# FastAPI → Brave  ② fetch search results
arrow(534, 228, 598, 449, "#6366f1", lw=2)

# Brave → Sonnet (results fed to Sonnet)
arrow(742, 420, 742, 332, "#6366f1", lw=1, dashed=True)
draw.text((748, 370), "search results", fill="#6366f1", font=F_XS)

# FastAPI → Playwright  ③
arrow(423, 268, 423, 268, "#ec4899")   # internal, skip
# FastAPI → Cinemark via Playwright
arrow(534, 280, 960, 290, "#ec4899", lw=2)
draw.text((670, 258), "③ scrape seat maps", fill="#ec4899", font=F_XS)

# Scorer feedback (implicit — same zone)
# FastAPI → Haiku  ⑤ rank
draw.line([(534, 350), (580, 350), (580, 206), (598, 206)], fill="#f97316", width=1)
draw.polygon([(598,206),(586,200),(586,212)], fill="#f97316")
draw.text((537, 338), "⑤ rank results", fill="#f97316", font=F_XS)

# FastAPI → Firestore (dashed)
arrow(312, 228, 248, 318, "#22c55e", dashed=True)
draw.text((248, 262), "log (async)", fill="#22c55e", font=F_XS)

# GitHub CI/CD
arrow(570, 580, 430, 506, "#475569", dashed=True)
arrow(530, 580, 165, 287, "#475569", dashed=True)

# ═══════════════════════════════════════════════════════════════════════════════
# LEGEND
# ═══════════════════════════════════════════════════════════════════════════════
lx, ly = 1260, 690
rr(lx, ly, 295, 148, "#f9fafb", "#d1d5db", radius=8, lw=1)
text_left(lx+10, ly+8, "Legend", get_font(14, bold=True), "#374151")
items = [
    ("━━", "#4a9eed", "User request / SSE response"),
    ("━━", "#f97316", "Claude AI  (Bedrock)"),
    ("━━", "#6366f1", "Brave Search  (RAG context)"),
    ("━━", "#ec4899", "Playwright seat scraping"),
    ("- -", "#22c55e", "Firestore logging  (async)"),
    ("- -", "#475569", "CI/CD deployment"),
]
for i, (sym, clr, desc) in enumerate(items):
    yy = ly + 32 + i*19
    draw.text((lx+10, yy), sym, fill=clr, font=F_MD)
    draw.text((lx+42, yy), desc, fill="#374151", font=F_XS)

# ═══════════════════════════════════════════════════════════════════════════════
# SAVE
# ═══════════════════════════════════════════════════════════════════════════════
out = "/Users/kundas/script/movieseats/.claude/worktrees/wonderful-noether/docs/Excalidraw.png"
img.save(out, "PNG", dpi=(144, 144))
print(f"Saved: {out}")
