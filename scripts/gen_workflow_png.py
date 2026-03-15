"""Generate a horizontal workflow PNG diagram for the daily digest pipeline.

Layout: top row has 3 phases (触发 → 数据采集 → AI摘要) horizontally,
then AI摘要 forks downward into RAG入库 and 通知&归档 side by side.
"""

from PIL import Image, ImageDraw, ImageFont

# --- Config ---
WIDTH, HEIGHT = 1600, 1050
BG = "#FFFFFF"
CJK_FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"

font_title = ImageFont.truetype(CJK_FONT, 28)
font_header = ImageFont.truetype(CJK_FONT, 20)
font_body = ImageFont.truetype(CJK_FONT, 16)
font_small = ImageFont.truetype(CJK_FONT, 14)

# Phase definitions
PHASES = [
    {
        "title": "触发",
        "color": "#2196F3",
        "bg": "#e8f4f8",
        "steps": [
            ("定时任务", "UTC 1:20 每日"),
            ("手动触发", "workflow_dispatch"),
        ],
    },
    {
        "title": "数据采集",
        "color": "#FF9800",
        "bg": "#fff3e0",
        "steps": [
            ("加载配置", "config/users.json"),
            ("计算时间范围", "昨日 24h"),
            ("Apify 请求", "Twitter Scraper"),
            ("轮询等待", "每10s/最长600s"),
            ("下载数据", "raw_tweets.json"),
        ],
    },
    {
        "title": "AI 摘要",
        "color": "#9C27B0",
        "bg": "#f3e5f5",
        "steps": [
            ("解析推文", "转推/引用/线程"),
            ("智谱 GLM-4.7", "逐条生成摘要"),
            ("输出文件", "summarized_tweets.json"),
        ],
    },
    {
        "title": "RAG 入库",
        "color": "#4CAF50",
        "bg": "#e8f5e9",
        "steps": [
            ("生成唯一 ID", "合并摘要+原文"),
            ("本地 JSON", "tweets_store.json"),
            ("Embedding", "智谱 embedding-3"),
            ("Pinecone", "向量数据库"),
        ],
    },
    {
        "title": "通知 & 归档",
        "color": "#E91E63",
        "bg": "#fce4ec",
        "steps": [
            ("HTML 邮件", "按作者分组"),
            ("SMTP 发送", "Gmail TLS"),
            ("GitHub Artifacts", "保留 7 天"),
        ],
    },
]

img = Image.new("RGB", (WIDTH, HEIGHT), BG)
draw = ImageDraw.Draw(img)

# Title
draw.text((WIDTH // 2, 28), "AI Builder Daily Digest - 主工作流", fill="#333333", font=font_title, anchor="mt")

# Layout constants
BOX_H = 58
BOX_GAP = 10
HEADER_H = 42
PADDING = 14
CORNER = 12
PHASE_GAP = 20
MARGIN_X = 40
TOP_Y = 75


def draw_rounded_rect(d, xy, fill, outline=None, radius=10, width=2):
    d.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def draw_phase(d, phase, x0, y0, pw):
    """Draw a single phase block. Returns (phase_rect, list_of_box_info)."""
    n_steps = len(phase["steps"])
    content_h = HEADER_H + n_steps * (BOX_H + BOX_GAP) + PADDING
    x1 = x0 + pw
    y1 = y0 + content_h

    # Phase background
    draw_rounded_rect(d, (x0, y0, x1, y1), fill=phase["bg"], outline=phase["color"], radius=CORNER, width=2)

    # Phase header
    d.text(
        ((x0 + x1) // 2, y0 + 6 + HEADER_H // 2),
        phase["title"],
        fill=phase["color"],
        font=font_header,
        anchor="mm",
    )
    d.line([(x0 + 10, y0 + HEADER_H), (x1 - 10, y0 + HEADER_H)], fill=phase["color"], width=1)

    boxes = []
    for j, (label, sub) in enumerate(phase["steps"]):
        bx0 = x0 + PADDING
        by0 = y0 + HEADER_H + BOX_GAP + j * (BOX_H + BOX_GAP)
        bx1 = x1 - PADDING
        by1 = by0 + BOX_H

        draw_rounded_rect(d, (bx0, by0, bx1, by1), fill="#FFFFFF", outline="#CCCCCC", radius=8, width=1)

        cx = (bx0 + bx1) // 2
        d.text((cx, by0 + 15), label, fill="#333333", font=font_body, anchor="mt")
        d.text((cx, by0 + 36), sub, fill="#888888", font=font_small, anchor="mt")

        boxes.append({"rect": (bx0, by0, bx1, by1), "cx": cx, "cy": (by0 + by1) // 2})

    return (x0, y0, x1, y1), boxes


def draw_vertical_arrows(d, boxes, color):
    """Draw arrows between consecutive steps within a phase."""
    for j in range(len(boxes) - 1):
        cx = boxes[j]["cx"]
        by1 = boxes[j]["rect"][3]
        by0_next = boxes[j + 1]["rect"][1]
        d.line([(cx, by1), (cx, by0_next)], fill=color, width=2)
        a = 6
        d.polygon([(cx, by0_next), (cx - a, by0_next - a), (cx + a, by0_next - a)], fill=color)


def draw_h_arrow(d, x1, y1, x2, y2, color="#666666", lw=2):
    """Draw horizontal arrow with arrowhead pointing right."""
    if y1 == y2:
        d.line([(x1, y1), (x2, y2)], fill=color, width=lw)
    else:
        mid_x = (x1 + x2) // 2
        d.line([(x1, y1), (mid_x, y1)], fill=color, width=lw)
        d.line([(mid_x, y1), (mid_x, y2)], fill=color, width=lw)
        d.line([(mid_x, y2), (x2, y2)], fill=color, width=lw)
    a = 7
    d.polygon([(x2, y2), (x2 - a, y2 - a), (x2 - a, y2 + a)], fill=color)


def draw_v_arrow(d, x1, y1, x2, y2, color="#666666", lw=2):
    """Draw vertical arrow with arrowhead pointing down."""
    if x1 == x2:
        d.line([(x1, y1), (x2, y2)], fill=color, width=lw)
    else:
        mid_y = (y1 + y2) // 2
        d.line([(x1, y1), (x1, mid_y)], fill=color, width=lw)
        d.line([(x1, mid_y), (x2, mid_y)], fill=color, width=lw)
        d.line([(x2, mid_y), (x2, y2)], fill=color, width=lw)
    a = 7
    d.polygon([(x2, y2), (x2 - a, y2 - a), (x2 + a, y2 - a)], fill=color)


# ========== ROW 1: 触发 → 数据采集 → AI摘要 (horizontal) ==========
top_phases = PHASES[:3]
top_usable_w = WIDTH - 2 * MARGIN_X - (len(top_phases) - 1) * PHASE_GAP
top_phase_w = top_usable_w // len(top_phases)

top_rects = []
top_boxes = []

for i, phase in enumerate(top_phases):
    x0 = MARGIN_X + i * (top_phase_w + PHASE_GAP)
    rect, boxes = draw_phase(draw, phase, x0, TOP_Y, top_phase_w)
    top_rects.append(rect)
    top_boxes.append(boxes)
    draw_vertical_arrows(draw, boxes, phase["color"])

# Horizontal arrows between top phases
for i in range(len(top_phases) - 1):
    src = top_boxes[i][-1]  # last box of current phase
    dst = top_boxes[i + 1][0]  # first box of next phase
    draw_h_arrow(draw, src["rect"][2], src["cy"], dst["rect"][0], dst["cy"])

# ========== ROW 2: RAG入库 and 通知&归档 (below AI摘要, side by side) ==========
# Position them below AI摘要, centered under it but spanning wider
row2_top = max(r[3] for r in top_rects) + 60  # gap below row 1

# The two bottom phases span the right 2/3 of the canvas, centered under AI摘要
bot_phases = PHASES[3:]
# Place them under the AI摘要 column area, but wider - use the right portion
ai_summary_rect = top_rects[2]
ai_cx = (ai_summary_rect[0] + ai_summary_rect[2]) // 2

bot_phase_w = top_phase_w  # same width as top phases
bot_total_w = 2 * bot_phase_w + PHASE_GAP
bot_start_x = ai_cx - bot_total_w // 2

# Ensure it doesn't go off screen
bot_start_x = max(MARGIN_X, min(bot_start_x, WIDTH - MARGIN_X - bot_total_w))

bot_rects = []
bot_boxes = []

for i, phase in enumerate(bot_phases):
    x0 = bot_start_x + i * (bot_phase_w + PHASE_GAP)
    rect, boxes = draw_phase(draw, phase, x0, row2_top, bot_phase_w)
    bot_rects.append(rect)
    bot_boxes.append(boxes)
    draw_vertical_arrows(draw, boxes, phase["color"])

# ========== FORK ARROWS: AI摘要 last step → down to RAG入库 and 通知&归档 ==========
ai_last = top_boxes[2][-1]  # last box of AI摘要
fork_start_x = ai_last["cx"]
fork_start_y = ai_last["rect"][3]  # bottom of last box

# Fork point (midway between row1 bottom and row2 top)
fork_y = (fork_start_y + row2_top) // 2

# Destination: top of first box in each bottom phase
rag_first = bot_boxes[0][0]
notify_first = bot_boxes[1][0]

rag_dst_x = rag_first["cx"]
rag_dst_y = rag_first["rect"][1]

notify_dst_x = notify_first["cx"]
notify_dst_y = notify_first["rect"][1]

# Draw the fork: vertical line down, then split left and right
draw.line([(fork_start_x, fork_start_y), (fork_start_x, fork_y)], fill="#666666", width=2)

# Left branch → RAG入库
draw.line([(fork_start_x, fork_y), (rag_dst_x, fork_y)], fill="#4CAF50", width=2)
draw.line([(rag_dst_x, fork_y), (rag_dst_x, rag_dst_y)], fill="#4CAF50", width=2)
a = 7
draw.polygon([(rag_dst_x, rag_dst_y), (rag_dst_x - a, rag_dst_y - a), (rag_dst_x + a, rag_dst_y - a)], fill="#4CAF50")

# Right branch → 通知&归档
draw.line([(fork_start_x, fork_y), (notify_dst_x, fork_y)], fill="#E91E63", width=2)
draw.line([(notify_dst_x, fork_y), (notify_dst_x, notify_dst_y)], fill="#E91E63", width=2)
a = 7
draw.polygon([(notify_dst_x, notify_dst_y), (notify_dst_x - a, notify_dst_y - a), (notify_dst_x + a, notify_dst_y - a)], fill="#E91E63")

# Fork dot
draw.ellipse([(fork_start_x - 5, fork_y - 5), (fork_start_x + 5, fork_y + 5)], fill="#666666")

# Legend at bottom
legend_y = HEIGHT - 40
legend_items = [
    ("#666666", "顺序流程"),
    ("#4CAF50", "分叉 → RAG 入库"),
    ("#E91E63", "分叉 → 通知 & 归档"),
]
lx = MARGIN_X + 20
for color, label in legend_items:
    draw.rectangle([(lx, legend_y), (lx + 24, legend_y + 14)], fill=color)
    draw.text((lx + 32, legend_y + 7), label, fill="#333333", font=font_small, anchor="lm")
    lx += 280

# Save
out_path = "/home/user/ai-builder-digest/docs/workflow-main.png"
img.save(out_path, "PNG")
print(f"Saved to {out_path} ({img.size[0]}x{img.size[1]})")
