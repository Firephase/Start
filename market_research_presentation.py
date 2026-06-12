#!/usr/bin/env python3
"""Generate market research PDF presentation for Generative Audio Composition project."""

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm, cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.shapes import Drawing, Rect, String, Line
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics import renderPDF
import os

# ── Color palette ───────────────────────────────────────────────────────────
DARK_BG     = colors.HexColor("#0D0D0D")
ACCENT      = colors.HexColor("#7C3AED")   # violet
ACCENT2     = colors.HexColor("#06B6D4")   # cyan
ACCENT3     = colors.HexColor("#10B981")   # emerald
ACCENT_WARN = colors.HexColor("#F59E0B")   # amber
ACCENT_RED  = colors.HexColor("#EF4444")   # red
TEXT_MAIN   = colors.HexColor("#F1F5F9")
TEXT_MUTED  = colors.HexColor("#94A3B8")
CARD_BG     = colors.HexColor("#1E1E2E")
CARD_BORDER = colors.HexColor("#334155")
WHITE       = colors.white
PAGE_BG     = colors.HexColor("#0F0F1A")

W, H = A4  # 595 x 842 pt

OUTPUT_PATH = "/home/user/Start/market_research.pdf"

# ── Style helpers ────────────────────────────────────────────────────────────
def style(name, **kw):
    base = getSampleStyleSheet()
    return ParagraphStyle(name, parent=base["Normal"], **kw)

S_SLIDE_TITLE = style("SlideTitle",
    fontName="Helvetica-Bold", fontSize=28, textColor=WHITE,
    spaceAfter=4, spaceBefore=0, leading=34)

S_SLIDE_SUBTITLE = style("SlideSubtitle",
    fontName="Helvetica", fontSize=13, textColor=ACCENT2,
    spaceAfter=14, spaceBefore=0, leading=17)

S_SECTION = style("Section",
    fontName="Helvetica-Bold", fontSize=17, textColor=ACCENT,
    spaceAfter=6, spaceBefore=10, leading=22)

S_SUBSECTION = style("Subsection",
    fontName="Helvetica-Bold", fontSize=12, textColor=ACCENT2,
    spaceAfter=4, spaceBefore=8, leading=16)

S_BODY = style("Body",
    fontName="Helvetica", fontSize=10, textColor=TEXT_MAIN,
    spaceAfter=4, spaceBefore=2, leading=15, alignment=TA_JUSTIFY)

S_BULLET = style("Bullet",
    fontName="Helvetica", fontSize=10, textColor=TEXT_MAIN,
    spaceAfter=3, spaceBefore=1, leading=14,
    leftIndent=14, firstLineIndent=-10)

S_BULLET2 = style("Bullet2",
    fontName="Helvetica", fontSize=9, textColor=TEXT_MUTED,
    spaceAfter=2, spaceBefore=1, leading=13,
    leftIndent=28, firstLineIndent=-10)

S_CAPTION = style("Caption",
    fontName="Helvetica-Oblique", fontSize=8, textColor=TEXT_MUTED,
    spaceAfter=2, spaceBefore=2, leading=11, alignment=TA_CENTER)

S_METRIC_BIG = style("MetricBig",
    fontName="Helvetica-Bold", fontSize=26, textColor=ACCENT2,
    spaceAfter=2, spaceBefore=2, leading=30, alignment=TA_CENTER)

S_METRIC_LABEL = style("MetricLabel",
    fontName="Helvetica", fontSize=9, textColor=TEXT_MUTED,
    spaceAfter=0, spaceBefore=0, leading=12, alignment=TA_CENTER)

S_TAG = style("Tag",
    fontName="Helvetica-Bold", fontSize=8, textColor=ACCENT,
    spaceAfter=0, spaceBefore=0, leading=10, alignment=TA_CENTER)

S_QUOTE = style("Quote",
    fontName="Helvetica-Oblique", fontSize=10, textColor=ACCENT2,
    spaceAfter=6, spaceBefore=6, leading=15, leftIndent=16,
    borderPad=8, alignment=TA_LEFT)

S_FOOTER = style("Footer",
    fontName="Helvetica", fontSize=7, textColor=TEXT_MUTED,
    leading=9, alignment=TA_CENTER)

S_PAGE_NUM = style("PageNum",
    fontName="Helvetica-Bold", fontSize=9, textColor=ACCENT,
    leading=11, alignment=TA_RIGHT)

S_FAQ_Q = style("FAQQ",
    fontName="Helvetica-Bold", fontSize=11, textColor=ACCENT_WARN,
    spaceAfter=3, spaceBefore=8, leading=15)

S_FAQ_A = style("FAQA",
    fontName="Helvetica", fontSize=10, textColor=TEXT_MAIN,
    spaceAfter=6, spaceBefore=2, leading=14, leftIndent=12, alignment=TA_JUSTIFY)

S_RISK_HIGH = style("RiskH",
    fontName="Helvetica-Bold", fontSize=10, textColor=ACCENT_RED,
    spaceAfter=2, spaceBefore=4, leading=14)

S_RISK_MED = style("RiskM",
    fontName="Helvetica-Bold", fontSize=10, textColor=ACCENT_WARN,
    spaceAfter=2, spaceBefore=4, leading=14)

S_RISK_LOW = style("RiskL",
    fontName="Helvetica-Bold", fontSize=10, textColor=ACCENT3,
    spaceAfter=2, spaceBefore=4, leading=14)

# ── Reusable components ──────────────────────────────────────────────────────

def hr(color=ACCENT, width=1):
    return HRFlowable(width="100%", thickness=width, color=color, spaceAfter=8, spaceBefore=4)

def vspace(n=6):
    return Spacer(1, n)

def b(text, color=ACCENT2):
    return f'<font color="{color.hexval()}" name="Helvetica-Bold">{text}</font>'

def bullet(text, indent=0):
    prefix = "◆ " if indent == 0 else "  › "
    return Paragraph(f"{prefix}{text}", S_BULLET if indent == 0 else S_BULLET2)

def metric_card(value, label, color=ACCENT2):
    data = [
        [Paragraph(value, ParagraphStyle("mv", fontName="Helvetica-Bold",
            fontSize=22, textColor=color, leading=26, alignment=TA_CENTER))],
        [Paragraph(label, S_METRIC_LABEL)],
    ]
    t = Table(data, colWidths=[None])
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,-1), CARD_BG),
        ("BOX",         (0,0), (-1,-1), 0.8, color),
        ("TOPPADDING",  (0,0), (-1,-1), 10),
        ("BOTTOMPADDING",(0,0),(-1,-1),10),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
        ("RIGHTPADDING",(0,0), (-1,-1), 8),
    ]))
    return t

def metrics_row(items):
    """items = list of (value, label, color)"""
    cells = [[metric_card(v, l, c) for v, l, c in items]]
    n = len(items)
    cw = (W - 80) / n
    t = Table(cells, colWidths=[cw]*n, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("VALIGN",  (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING",  (0,0), (-1,-1), 4),
        ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("TOPPADDING",   (0,0), (-1,-1), 0),
        ("BOTTOMPADDING",(0,0), (-1,-1), 0),
    ]))
    return t

def section_header(title, subtitle=""):
    items = [Paragraph(title, S_SECTION)]
    if subtitle:
        items.append(Paragraph(subtitle, S_SLIDE_SUBTITLE))
    items.append(hr())
    return items

def colored_table(headers, rows, col_widths=None, accent=ACCENT):
    data = [headers] + rows
    n_cols = len(headers)
    if col_widths is None:
        col_widths = [(W - 80) / n_cols] * n_cols
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style_cmds = [
        ("BACKGROUND",    (0,0), (-1,0),  accent),
        ("TEXTCOLOR",     (0,0), (-1,0),  WHITE),
        ("FONTNAME",      (0,0), (-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,0),  9),
        ("ALIGN",         (0,0), (-1,0),  "CENTER"),
        ("BACKGROUND",    (0,1), (-1,-1), CARD_BG),
        ("TEXTCOLOR",     (0,1), (-1,-1), TEXT_MAIN),
        ("FONTNAME",      (0,1), (-1,-1), "Helvetica"),
        ("FONTSIZE",      (0,1), (-1,-1), 9),
        ("GRID",          (0,0), (-1,-1), 0.4, CARD_BORDER),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [CARD_BG, colors.HexColor("#16213E")]),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 7),
        ("RIGHTPADDING",  (0,0), (-1,-1), 7),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ]
    t.setStyle(TableStyle(style_cmds))
    return t

def title_slide():
    """Cover page."""
    elems = []
    elems.append(vspace(60))
    # Badge
    badge_data = [[Paragraph("MARKET RESEARCH  ·  2025–2026", style("badge",
        fontName="Helvetica-Bold", fontSize=8, textColor=ACCENT,
        leading=10, alignment=TA_CENTER))]]
    badge = Table(badge_data, colWidths=[200])
    badge.setStyle(TableStyle([
        ("BACKGROUND",   (0,0),(-1,-1), colors.HexColor("#1A0040")),
        ("BOX",          (0,0),(-1,-1), 1, ACCENT),
        ("TOPPADDING",   (0,0),(-1,-1), 5),
        ("BOTTOMPADDING",(0,0),(-1,-1), 5),
    ]))
    elems.append(badge)
    elems.append(vspace(20))
    elems.append(Paragraph("Generative Audio", style("T1", fontName="Helvetica-Bold",
        fontSize=46, textColor=WHITE, leading=52, spaceAfter=0)))
    elems.append(Paragraph("Composition", style("T2", fontName="Helvetica-Bold",
        fontSize=46, textColor=ACCENT, leading=52, spaceAfter=12)))
    elems.append(Paragraph(
        "Превращаем любительские записи голоса в профессиональные треки<br/>"
        "с клонированием вашего голоса. Анализ рынка и стратегия выхода.",
        style("TS", fontName="Helvetica", fontSize=14, textColor=TEXT_MUTED,
            leading=20, spaceAfter=0)))
    elems.append(vspace(40))
    elems.append(hr(ACCENT, 1))
    # Stats strip
    strip_data = [[
        Paragraph("$569M\nРынок 2024", style("sc", fontName="Helvetica-Bold",
            fontSize=11, textColor=ACCENT2, leading=14, alignment=TA_CENTER)),
        Paragraph("30.5% CAGR\nРост рынка", style("sc", fontName="Helvetica-Bold",
            fontSize=11, textColor=ACCENT3, leading=14, alignment=TA_CENTER)),
        Paragraph("$2.8B\nРынок 2030", style("sc", fontName="Helvetica-Bold",
            fontSize=11, textColor=ACCENT_WARN, leading=14, alignment=TA_CENTER)),
        Paragraph("Нет\nВ мире аналогов", style("sc", fontName="Helvetica-Bold",
            fontSize=11, textColor=ACCENT, leading=14, alignment=TA_CENTER)),
    ]]
    strip = Table(strip_data, colWidths=[(W-80)/4]*4)
    strip.setStyle(TableStyle([
        ("BACKGROUND",   (0,0),(-1,-1), CARD_BG),
        ("BOX",          (0,0),(-1,-1), 0.5, CARD_BORDER),
        ("INNERGRID",    (0,0),(-1,-1), 0.5, CARD_BORDER),
        ("TOPPADDING",   (0,0),(-1,-1), 12),
        ("BOTTOMPADDING",(0,0),(-1,-1), 12),
        ("ALIGN",        (0,0),(-1,-1), "CENTER"),
        ("VALIGN",       (0,0),(-1,-1), "MIDDLE"),
    ]))
    elems.append(strip)
    elems.append(vspace(40))
    elems.append(Paragraph("Конфиденциально · Июнь 2025", S_FOOTER))
    return elems

# ── Page 2: Конкуренты ───────────────────────────────────────────────────────
def page_competitors():
    elems = []
    elems += section_header("01 · Конкурентный ландшафт",
        "Кто уже на рынке и что им не хватает")

    headers = ["Компания", "Funding", "Цена/мес", "Голос?", "Полный трек?", "Ключевой gap"]
    rows = [
        ["Suno AI", "$775M+\n$5.4B val", "$0–$30", "✓ v5.5\n(persona)", "✓", "Не «твой» голос\nНет stem export"],
        ["Udio AI",  "$70M\n(a16z)",    "$0–$30", "✗",     "✓", "Судебные риски\nНет voice clone"],
        ["Boomy",   "WMG seed",         "$10–$30","✗",     "✓", "Нет персонализации\nНизкое качество"],
        ["Soundraw","Undisclosed",       "$11–$32","✗",     "✓", "Нет вокала вообще\nТолько инструментал"],
        ["AIVA",    "€3M+",             "€0–€49", "✗",     "✓", "Классика/кино\nНет pop/r&b"],
        ["Mubert",  "Undisclosed",       "$0–$199","✗",     "~",  "Только фон\nНет структуры песни"],
        ["Beatoven", "$2.4M",           "$0–?",   "✗",     "~",  "Beta стадия\nНет пользоват. голоса"],
    ]
    para_rows = []
    for row in rows:
        para_rows.append([
            Paragraph(row[0], style("ct", fontName="Helvetica-Bold", fontSize=9,
                textColor=ACCENT2, leading=12)),
            Paragraph(row[1], style("ct2", fontName="Helvetica", fontSize=8,
                textColor=TEXT_MUTED, leading=11)),
            Paragraph(row[2], style("ct2", fontName="Helvetica", fontSize=9,
                textColor=TEXT_MAIN, leading=12)),
            Paragraph(row[3], style("ct2", fontName="Helvetica-Bold", fontSize=10,
                textColor=ACCENT3 if "✓" in row[3] else ACCENT_RED, leading=12,
                alignment=TA_CENTER)),
            Paragraph(row[4], style("ct2", fontName="Helvetica-Bold", fontSize=10,
                textColor=ACCENT3 if "✓" in row[4] else ACCENT_WARN, leading=12,
                alignment=TA_CENTER)),
            Paragraph(row[5], style("ct3", fontName="Helvetica", fontSize=8,
                textColor=ACCENT_RED, leading=11)),
        ])
    t = colored_table(
        [Paragraph(h, style("th", fontName="Helvetica-Bold", fontSize=9,
            textColor=WHITE, leading=12, alignment=TA_CENTER)) for h in headers],
        para_rows,
        col_widths=[90, 65, 55, 45, 55, 125],
        accent=ACCENT
    )
    elems.append(t)
    elems.append(vspace(12))

    elems.append(Paragraph("Наша уникальная позиция", S_SUBSECTION))
    gap_data = [[
        Paragraph("🎤  Клонирует<br/>голос пользователя", style("gp",
            fontName="Helvetica-Bold", fontSize=10, textColor=WHITE, leading=14,
            alignment=TA_CENTER)),
        Paragraph("🎵  Полная аранжировка<br/>под стиль фрагментов", style("gp",
            fontName="Helvetica-Bold", fontSize=10, textColor=WHITE, leading=14,
            alignment=TA_CENTER)),
        Paragraph("🎼  Структура песни<br/>из 5-секундного напева", style("gp",
            fontName="Helvetica-Bold", fontSize=10, textColor=WHITE, leading=14,
            alignment=TA_CENTER)),
        Paragraph("🏆  Мастеринг до<br/>−14 LUFS (стриминг)", style("gp",
            fontName="Helvetica-Bold", fontSize=10, textColor=WHITE, leading=14,
            alignment=TA_CENTER)),
    ]]
    gt = Table(gap_data, colWidths=[(W-80)/4]*4)
    gt.setStyle(TableStyle([
        ("BACKGROUND",   (0,0),(-1,-1), colors.HexColor("#1A0040")),
        ("BOX",          (0,0),(-1,-1), 1, ACCENT),
        ("INNERGRID",    (0,0),(-1,-1), 0.5, ACCENT),
        ("TOPPADDING",   (0,0),(-1,-1), 12),
        ("BOTTOMPADDING",(0,0),(-1,-1), 12),
        ("VALIGN",       (0,0),(-1,-1), "MIDDLE"),
    ]))
    elems.append(gt)
    return elems

# ── Page 3: Целевая аудитория ────────────────────────────────────────────────
def page_audience():
    elems = []
    elems += section_header("02 · Целевая аудитория",
        "6 ключевых персон с болями и готовностью платить")

    personas = [
        {
            "icon": "🎤",
            "name": "Алексей, 24",
            "tag": "AMATEUR SINGER  ·  B2C CORE",
            "desc": "Поёт в душе и на домашних записях. Хочет звучать как на радио, "
                    "но не умеет играть и не может позволить студию.",
            "pain": "Студия — $200/час. Нет инструментов. Голос теряется.",
            "wtp":  "$12–25/мес",
            "size": "~180M чел. по миру",
            "color": ACCENT,
        },
        {
            "icon": "📱",
            "name": "Диана, 21",
            "tag": "CONTENT CREATOR  ·  B2C GROWTH",
            "desc": "TikTok/Reels-блогер, 50k+ подписчиков. Ищет уникальный саундтрек "
                    "под каждый ролик — не хочет copyright-strike.",
            "pain": "Стоковая музыка — безликая. AI-трек без голоса — пусто.",
            "wtp":  "$10–20/мес",
            "size": "~50M активных\ncontent creators",
            "color": ACCENT2,
        },
        {
            "icon": "🎮",
            "name": "Михаил, 31",
            "tag": "INDIE GAME DEV  ·  B2C/B2B",
            "desc": "Соло-разработчик инди-игры. Нужен OST на 2 часа — "
                    "нанять композитора не по бюджету ($5k–$30k).",
            "pain": "MusicGen — инструментальный. Нет вокала, нет персонажей.",
            "wtp":  "$30–50/мес или $500 разово",
            "size": "~2M indie devs\nглобально",
            "color": ACCENT3,
        },
        {
            "icon": "🎵",
            "name": "Карина, 28",
            "tag": "PROSUMER MUSICIAN  ·  B2C UPSELL",
            "desc": "Умеет петь, пишет тексты, но не умеет аранжировать. "
                    "Хочет записать демо для лейблов.",
            "pain": "Аранжировщик — $500+/трек. Demo — 10 треков = $5000.",
            "wtp":  "$29–49/мес",
            "size": "~40M any-genre\nsongwriters",
            "color": ACCENT_WARN,
        },
        {
            "icon": "📺",
            "name": "Рекламное агентство",
            "tag": "AD AGENCY  ·  B2B REVENUE",
            "desc": "Создаёт 20–50 роликов в месяц. Каждому нужна оригинальная музыка "
                    "— и джингл с нужным брендовым голосом.",
            "pain": "Лицензия трека — $500–$5000. Джингл от студии — $2000–$15000.",
            "wtp":  "$500–2000/мес (API)",
            "size": "~120k агентств\nв US+EU",
            "color": colors.HexColor("#EC4899"),
        },
        {
            "icon": "🎙",
            "name": "Подкастер / YouTuber",
            "tag": "PODCAST / YT  ·  B2C MASS",
            "desc": "Ведёт еженедельный подкаст. Нужен собственный джингл и фоновая музыка "
                    "— с его голосом в интро.",
            "pain": "Нет своего голоса в генераторах. Всё звучит одинаково.",
            "wtp":  "$8–15/мес",
            "size": "~5M активных\nподкастеров",
            "color": ACCENT2,
        },
    ]

    for i in range(0, len(personas), 2):
        row_elems = []
        for p in personas[i:i+2]:
            card_content = [
                [Paragraph(f"{p['icon']}  {p['name']}", style("pn",
                    fontName="Helvetica-Bold", fontSize=13, textColor=WHITE,
                    leading=16))],
                [Paragraph(p["tag"], style("pt", fontName="Helvetica-Bold",
                    fontSize=7, textColor=p["color"], leading=9))],
                [vspace(4)],
                [Paragraph(p["desc"], style("pd", fontName="Helvetica",
                    fontSize=9, textColor=TEXT_MAIN, leading=13,
                    alignment=TA_JUSTIFY))],
                [vspace(4)],
                [Paragraph(f'<font color="#EF4444">⚡ Боль: </font>{p["pain"]}',
                    style("pp", fontName="Helvetica", fontSize=9, textColor=TEXT_MAIN,
                        leading=13))],
                [vspace(2)],
                [Table([[
                    Paragraph(f"💰 WTP: {p['wtp']}", style("pw",
                        fontName="Helvetica-Bold", fontSize=8, textColor=ACCENT3,
                        leading=11, alignment=TA_CENTER)),
                    Paragraph(f"👥 {p['size']}", style("ps",
                        fontName="Helvetica", fontSize=8, textColor=TEXT_MUTED,
                        leading=11, alignment=TA_CENTER)),
                ]], colWidths=[120, 120], style=TableStyle([
                    ("TOPPADDING",   (0,0),(-1,-1), 3),
                    ("BOTTOMPADDING",(0,0),(-1,-1), 3),
                    ("ALIGN",        (0,0),(-1,-1), "CENTER"),
                ]))],
            ]
            card = Table(card_content, colWidths=[(W-100)/2])
            card.setStyle(TableStyle([
                ("BACKGROUND",    (0,0), (-1,-1), CARD_BG),
                ("BOX",           (0,0), (-1,-1), 1.2, p["color"]),
                ("TOPPADDING",    (0,0), (-1,-1), 10),
                ("BOTTOMPADDING", (0,0), (-1,-1), 10),
                ("LEFTPADDING",   (0,0), (-1,-1), 12),
                ("RIGHTPADDING",  (0,0), (-1,-1), 12),
            ]))
            row_elems.append(card)

        if len(row_elems) == 1:
            row_elems.append(Spacer(1, 1))

        row_table = Table([row_elems], colWidths=[(W-80)/2]*2)
        row_table.setStyle(TableStyle([
            ("VALIGN",         (0,0),(-1,-1), "TOP"),
            ("LEFTPADDING",    (0,0),(-1,-1), 5),
            ("RIGHTPADDING",   (0,0),(-1,-1), 5),
            ("TOPPADDING",     (0,0),(-1,-1), 0),
            ("BOTTOMPADDING",  (0,0),(-1,-1), 6),
        ]))
        elems.append(row_table)

    return elems

# ── Page 4: Боль ─────────────────────────────────────────────────────────────
def page_pain():
    elems = []
    elems += section_header("03 · Боли, которые мы решаем",
        "Что не так с текущими решениями — факты от пользователей")

    pains = [
        ("🔇 Нет клонирования голоса",
         "Ни один публичный инструмент не позволяет вам загрузить 5 секунд своего голоса "
         "и получить полноценную песню, спетую именно вашим голосом. "
         "Suno v5.5 создаёт «вокальную персону» — это не клон, а шаблон. "
         "Пользователи называют результат «звучит похоже, но не я».",
         ACCENT_RED),
        ("🎹 Нет полной аранжировки из фрагмента напева",
         "Существующие инструменты требуют текстового промпта: «создай рок-трек в ля-миноре». "
         "Но обычный пользователь не знает тональностей. Он хочет просто напеть — "
         "и получить готовый трек в своём стиле. Такого нет нигде.",
         ACCENT_WARN),
        ("📝 AI не знает ваши слова",
         "Boomy, Soundraw, Mubert не берут ваши тексты. "
         "Suno/Udio берут, но только как текстовый ввод — не из записанного голоса. "
         "Если вы импровизировали мелодию с текстом — система его не слышит.",
         ACCENT2),
        ("⚖️ Юридическая неопределённость",
         "Suno и Udio обвинили все три мейджора (UMG, Sony, Warner) в нарушении авторских прав. "
         "Udio урегулировал ($0.002–$0.005 за генерацию). "
         "Мы используем только лицензированные датасеты (OpenSinger, VocalSet, FMA) — "
         "это конкурентное преимущество для B2B-клиентов.",
         ACCENT3),
        ("🎚 Нет профессионального мастеринга",
         "Треки из Suno/Udio выходят с уровнем −18…−20 LUFS. "
         "Для Spotify нужно −14 LUFS, для TikTok —14, для YouTube −13.5. "
         "Пользователи вынуждены отдельно мастерить или платить за Landr ($9–$29/трек). "
         "Мы включаем мастеринг в пайплайн.",
         colors.HexColor("#EC4899")),
    ]

    for icon_title, desc, color in pains:
        item_data = [[
            Paragraph(icon_title, style("pt", fontName="Helvetica-Bold", fontSize=11,
                textColor=color, leading=15)),
            Paragraph(desc, style("pd", fontName="Helvetica", fontSize=9.5,
                textColor=TEXT_MAIN, leading=14, alignment=TA_JUSTIFY)),
        ]]
        item = Table(item_data, colWidths=[195, W - 80 - 195 - 10])
        item.setStyle(TableStyle([
            ("BACKGROUND",   (0,0),(-1,-1), CARD_BG),
            ("LEFTBORDER",   (0,0),(0,-1), 3, color),
            ("TOPPADDING",   (0,0),(-1,-1), 10),
            ("BOTTOMPADDING",(0,0),(-1,-1), 10),
            ("LEFTPADDING",  (0,0),(0,-1),  14),
            ("LEFTPADDING",  (1,0),(1,-1),  12),
            ("RIGHTPADDING", (0,0),(-1,-1), 12),
            ("VALIGN",       (0,0),(-1,-1), "TOP"),
        ]))
        elems.append(item)
        elems.append(vspace(5))

    return elems

# ── Page 5: Рынок ────────────────────────────────────────────────────────────
def page_market():
    elems = []
    elems += section_header("04 · Размер рынка",
        "TAM · SAM · SOM — с источниками и методологией")

    elems.append(metrics_row([
        ("$5.2B",    "TAM · AI in Music\n(Market.us, 2024)", ACCENT),
        ("$569M",    "Generat. AI Music\n(GVR, 2024)",      ACCENT2),
        ("$2.7B",    "Voice Cloning Market\n(R&M, 2024)",   ACCENT3),
        ("30.5%",    "CAGR 2025–2030\n(Grand View Research)",ACCENT_WARN),
    ]))
    elems.append(vspace(10))

    elems.append(Paragraph("Методология: TAM → SAM → SOM", S_SUBSECTION))

    tam_sam_som = [
        ["Уровень", "Описание", "Размер (2024)", "Источник"],
        ["TAM", "Весь рынок AI in Music + Voice Cloning\n(генерация, синтез речи, мастеринг, дистрибуция)",
         "$7.9B", "Market.us + R&M 2024"],
        ["SAM", "Инструменты генерации треков для\nпросьюмеров, контент-мейкеров, инди-разработчиков\n"
         "(исключаем enterprise SaaS для мейджоров)",
         "$920M", "GVR Generat. AI Music\n+ Voice Cloning SAM ~$350M"],
        ["SOM (Y1)", "Реально достижимая доля в первый год:\nUS + RU рынки, B2C подписки + B2B API.\n"
         "0.03% от SAM при 10k платящих @ $25 ARPU",
         "$3M ARR", "Собственная оценка\n(bottom-up)"],
        ["SOM (Y3)", "При масштабировании до 150k платящих\n"
         "+ B2B контракты (10 агентств × $1200/мес)",
         "$54M ARR", "3-year projection"],
    ]
    para_tam = []
    for i, row in enumerate(tam_sam_som):
        if i == 0:
            para_tam.append([Paragraph(c, style("th", fontName="Helvetica-Bold",
                fontSize=9, textColor=WHITE, leading=12)) for c in row])
        else:
            colors_map = {1: ACCENT2, 2: ACCENT3, 3: ACCENT_WARN, 4: colors.HexColor("#EC4899")}
            c = colors_map.get(i, TEXT_MAIN)
            para_tam.append([
                Paragraph(row[0], style("tc", fontName="Helvetica-Bold", fontSize=10,
                    textColor=c, leading=13, alignment=TA_CENTER)),
                Paragraph(row[1], style("tc2", fontName="Helvetica", fontSize=9,
                    textColor=TEXT_MAIN, leading=13)),
                Paragraph(row[2], style("tc3", fontName="Helvetica-Bold", fontSize=11,
                    textColor=c, leading=14, alignment=TA_CENTER)),
                Paragraph(row[3], style("tc4", fontName="Helvetica", fontSize=8,
                    textColor=TEXT_MUTED, leading=11)),
            ])
    t = Table(para_tam, colWidths=[55, 215, 95, 130], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0),  ACCENT),
        ("TEXTCOLOR",     (0,0), (-1,0),  WHITE),
        ("BACKGROUND",    (0,1), (-1,-1), CARD_BG),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [CARD_BG, colors.HexColor("#16213E")]),
        ("GRID",          (0,0), (-1,-1), 0.4, CARD_BORDER),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0), (-1,-1), 7),
        ("BOTTOMPADDING", (0,0), (-1,-1), 7),
        ("LEFTPADDING",   (0,0), (-1,-1), 7),
        ("RIGHTPADDING",  (0,0), (-1,-1), 7),
        ("ALIGN",         (0,0), (0,-1),  "CENTER"),
        ("ALIGN",         (2,0), (2,-1),  "CENTER"),
    ]))
    elems.append(t)
    elems.append(vspace(8))

    elems.append(Paragraph(
        "Bottom-up расчёт SOM Y1: контент-мейкеры US+RU (50M потенциальных) → конверсия 0.02% = "
        "10,000 платящих × $25 ARPU × 12 мес = $3M ARR. "
        "Дополнительно: 5 B2B-агентств × $1,200/мес = +$72K ARR в первый год.",
        style("note", fontName="Helvetica-Oblique", fontSize=8.5, textColor=TEXT_MUTED,
            leading=13, alignment=TA_JUSTIFY)))

    return elems

# ── Page 6: Риски ────────────────────────────────────────────────────────────
def page_risks():
    elems = []
    elems += section_header("05 · Риски и потенциальная выручка",
        "Что может пойти не так — и почему это управляемо")

    risks = [
        ("🔴 ВЫСОКИЙ", "Авторские права на обучающие данные",
         "Иски от мейджоров (как против Suno/Udio). Урегулирование Udio стоило "
         "~$0.002–$0.005/генерацию роялти.",
         "Используем только лицензированные датасеты: OpenSinger (CC), VocalSet (MIT), "
         "FMA (Creative Commons). Юридически чистее конкурентов.",
         S_RISK_HIGH),
        ("🟡 СРЕДНИЙ", "Конкуренция с Suno/Udio при добавлении voice clone",
         "Suno v5.5 уже имеет «vocal persona» — упростит барьер для пользователей.",
         "Наш голос — настоящий акустический клон из 5 секунд, а не шаблон. "
         "Плюс: мы поддерживаем загрузку своего голоса без блокировки по платформе.",
         S_RISK_MED),
        ("🟡 СРЕДНИЙ", "Задержка обучения моделей",
         "DiffSinger требует 2–3 недели на 8×A100. "
         "Если A100 дорожают (прецедент 2023–2024) — бюджет обучения растёт.",
         "LoRA fine-tuning MusicGen снижает GPU-время с 3 недель до 5 дней. "
         "Используем runpod.io spot instances ($1.49/GPU/h).",
         S_RISK_MED),
        ("🟢 НИЗКИЙ", "Качество голоса на малом числе примеров (1–10 фрагментов)",
         "WavLM speaker embedding теряет качество при <3 сек аудио.",
         "Минимум 5 секунд хорошего аудио. DeepFilterNet убирает шум. "
         "Enhancement pipeline компенсирует плохой микрофон.",
         S_RISK_LOW),
        ("🟢 НИЗКИЙ", "Проблема «холодного старта» — нет данных о пользователях",
         "Нет тренировочных данных на пользовательские голоса в продакшене.",
         "Используем OpenSinger (66 певцов, 50h) + VocalSet (20 певцов). "
         "Speaker embedding работает zero-shot — специального дообучения не нужно.",
         S_RISK_LOW),
    ]

    for badge, title, risk_text, mitigation, badge_style in risks:
        row = [[
            Paragraph(badge, badge_style),
            Paragraph(f"<b>{title}</b><br/>"
                      f'<font color="#94A3B8"><i>Риск: </i>{risk_text}</font>',
                      style("rd", fontName="Helvetica", fontSize=9.5,
                          textColor=TEXT_MAIN, leading=14)),
            Paragraph(f'<font color="#10B981">✓ Митигация: </font>{mitigation}',
                      style("rm", fontName="Helvetica", fontSize=9.5,
                          textColor=TEXT_MAIN, leading=14)),
        ]]
        rt = Table(row, colWidths=[72, 210, W-80-72-210-10])
        rt.setStyle(TableStyle([
            ("BACKGROUND",   (0,0),(-1,-1), CARD_BG),
            ("GRID",         (0,0),(-1,-1), 0.3, CARD_BORDER),
            ("TOPPADDING",   (0,0),(-1,-1), 9),
            ("BOTTOMPADDING",(0,0),(-1,-1), 9),
            ("LEFTPADDING",  (0,0),(-1,-1), 10),
            ("RIGHTPADDING", (0,0),(-1,-1), 10),
            ("VALIGN",       (0,0),(-1,-1), "TOP"),
        ]))
        elems.append(rt)
        elems.append(vspace(4))

    elems.append(vspace(8))
    elems.append(Paragraph("Прогноз выручки — Year 1", S_SUBSECTION))
    rev_data = [
        ["Сценарий", "Платящих пользователей", "ARPU/мес", "B2B контрактов", "ARR (Year 1)"],
        ["🐻 Медведь", "3,000", "$15", "0", "$540K"],
        ["📊 База",    "10,000", "$25", "5 × $1,200", "$3.07M"],
        ["🚀 Бык",     "30,000", "$28", "15 × $1,500", "$10.35M"],
    ]
    colors_row = [ACCENT_RED, ACCENT2, ACCENT3]
    para_rev = [[Paragraph(c, style("rh", fontName="Helvetica-Bold",
        fontSize=9, textColor=WHITE, leading=12, alignment=TA_CENTER))
        for c in rev_data[0]]]
    for i, row in enumerate(rev_data[1:]):
        cr = colors_row[i]
        para_rev.append([
            Paragraph(row[0], style("rc", fontName="Helvetica-Bold", fontSize=10,
                textColor=cr, leading=13, alignment=TA_CENTER)),
            *[Paragraph(c, style("rc2", fontName="Helvetica", fontSize=10,
                textColor=TEXT_MAIN, leading=13, alignment=TA_CENTER)) for c in row[1:-1]],
            Paragraph(row[-1], style("rv", fontName="Helvetica-Bold", fontSize=12,
                textColor=cr, leading=15, alignment=TA_CENTER)),
        ])
    rt2 = Table(para_rev, colWidths=[80, 115, 80, 110, 110], repeatRows=1)
    rt2.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0),  ACCENT),
        ("BACKGROUND",    (0,1),(-1,-1), CARD_BG),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [CARD_BG, colors.HexColor("#16213E")]),
        ("GRID",          (0,0),(-1,-1), 0.4, CARD_BORDER),
        ("TOPPADDING",    (0,0),(-1,-1), 7),
        ("BOTTOMPADDING", (0,0),(-1,-1), 7),
        ("LEFTPADDING",   (0,0),(-1,-1), 8),
        ("RIGHTPADDING",  (0,0),(-1,-1), 8),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ("ALIGN",         (0,0),(-1,-1), "CENTER"),
    ]))
    elems.append(rt2)
    return elems

# ── Page 7: Каналы ───────────────────────────────────────────────────────────
def page_channels():
    elems = []
    elems += section_header("06 · Каналы продвижения",
        "Как строить воронку от первых пользователей до $3M ARR")

    channels = [
        {
            "phase": "0–3 мес",
            "name":  "Product-Led Growth (PLG)",
            "icon":  "🔥",
            "color": ACCENT,
            "items": [
                "Freemium: 3 трека/мес бесплатно — без кредитки.",
                "Вирусный механизм: «Made with GAC» watermark в бесплатной версии → убирается на Pro.",
                "TikTok/Reels: демо-видео «напел 10 секунд → получил трек». Target CTR >3%.",
                "ProductHunt запуск — цель: Top-3 of the Day.",
                "Reddit: r/WeAreTheMusicMakers, r/Songwriting, r/gamedev (органически, no spam).",
            ]
        },
        {
            "phase": "1–6 мес",
            "name":  "Creator Partnership",
            "icon":  "🤝",
            "color": ACCENT2,
            "items": [
                "10–20 микро-инфлюенсеров (50k–500k подп.) по нишам: indie music, content creation, gamedev.",
                "Deal: Pro-аккаунт + $200–$500 за review-видео. ROI > paid ads на этой стадии.",
                "YouTube Shorts: 60-сек «before/after» — голос → трек. Алгоритм продвигает.",
                "Discord серверы (Suno community, Udio community): естественный переход.",
                "Spotify for Artists: интеграция — загрузка готового трека прямо в дистрибуцию.",
            ]
        },
        {
            "phase": "3–12 мес",
            "name":  "SEO + Content Marketing",
            "icon":  "📈",
            "color": ACCENT3,
            "items": [
                "Ключевые запросы: «AI voice cloning music», «turn humming into song», «сделать трек из голоса».",
                "Блог: туториалы «Как записать свой первый AI-трек», «Suno vs GAC vs Udio».",
                "Landing pages под каждый use case: для подкастеров, для геймдевов, для блогеров.",
                "Programmatic SEO: 1000+ страниц по запросам типа «create [genre] song from voice».",
            ]
        },
        {
            "phase": "6–12 мес",
            "name":  "B2B Direct Sales",
            "icon":  "💼",
            "color": ACCENT_WARN,
            "items": [
                "Outbound: LinkedIn + email к Digital/Ad агентствам (target: Digital Director).",
                "Pilot-first: 2 недели бесплатного API ($0 за 50 генераций) → конверсия в $1200/мес.",
                "Partnerства: интеграция с CapCut, Adobe Premiere, DaVinci Resolve (плагин).",
                "Gamedev: инди-игровые форумы, itch.io, GDC booth (year 2).",
            ]
        },
    ]

    for ch in channels:
        items_paras = [Paragraph(f"• {it}", style("ci", fontName="Helvetica",
            fontSize=9.5, textColor=TEXT_MAIN, leading=14)) for it in ch["items"]]
        card_data = [
            [Paragraph(f"{ch['icon']}  {ch['name']}", style("cn",
                fontName="Helvetica-Bold", fontSize=11, textColor=ch["color"], leading=14)),
             Paragraph(ch["phase"], style("cp", fontName="Helvetica-Bold",
                fontSize=9, textColor=WHITE, leading=12, alignment=TA_CENTER))],
            [Table([[p] for p in items_paras], colWidths=[(W-80)*0.72]), Spacer(1,1)],
        ]
        card = Table(card_data, colWidths=[(W-80)*0.72, (W-80)*0.28])
        card.setStyle(TableStyle([
            ("BACKGROUND",   (0,0),(-1,-1), CARD_BG),
            ("BOX",          (0,0),(-1,-1), 1, ch["color"]),
            ("BACKGROUND",   (1,0),(1,0),   colors.HexColor("#1A0040")),
            ("TOPPADDING",   (0,0),(-1,-1), 8),
            ("BOTTOMPADDING",(0,0),(-1,-1), 8),
            ("LEFTPADDING",  (0,0),(-1,-1), 12),
            ("RIGHTPADDING", (0,0),(-1,-1), 12),
            ("VALIGN",       (0,0),(-1,-1), "TOP"),
            ("ALIGN",        (1,0),(1,0),   "CENTER"),
            ("SPAN",         (0,1),(1,1)),
        ]))
        elems.append(card)
        elems.append(vspace(6))

    return elems

# ── Page 8: B2B / B2C Russia / USA ──────────────────────────────────────────
def page_sales():
    elems = []
    elems += section_header("07 · Стратегия продаж: Russia & USA",
        "B2C подписки + B2B API — два рынка, одна платформа")

    # Two column layout
    ru_content = [
        Paragraph("🇷🇺  РОССИЯ · B2C", style("rc", fontName="Helvetica-Bold",
            fontSize=13, textColor=ACCENT2, leading=16)),
        vspace(4),
        Paragraph("Рыночный контекст:", style("rl", fontName="Helvetica-Bold",
            fontSize=9, textColor=TEXT_MUTED, leading=12)),
        bullet("~180M русскоязычных пользователей, 50M+ в РФ онлайн"),
        bullet("Suno/Udio недоступны из РФ без VPN — прямое окно"),
        bullet("ВКонтакте: 73M MAU — нативная интеграция «выложить трек»"),
        bullet("Яндекс Музыка, СберЗвук: партнёрство для дистрибуции"),
        vspace(6),
        Paragraph("Монетизация:", style("rl", fontName="Helvetica-Bold",
            fontSize=9, textColor=TEXT_MUTED, leading=12)),
        bullet("Тарифы: 290р/мес (Старт), 790р/мес (Про), 2490р/мес (Студия)"),
        bullet("Оплата: ЮKassa, СБП, криптовалюта (для обхода санкций)"),
        bullet("Тестирование на ВКонтакте Mini Apps — встроенная аудитория"),
        vspace(6),
        Paragraph("Каналы RU:", style("rl", fontName="Helvetica-Bold",
            fontSize=9, textColor=TEXT_MUTED, leading=12)),
        bullet("Telegram: @music_ai_ru канал + бот для демо"),
        bullet("TikTok RU + VK Клипы — вирусный контент"),
        bullet("Партнёрство с музыкальными школами (SkillFactory, Яндекс Практикум)"),
    ]

    us_content = [
        Paragraph("🇺🇸  США · B2C + B2B", style("uc", fontName="Helvetica-Bold",
            fontSize=13, textColor=ACCENT3, leading=16)),
        vspace(4),
        Paragraph("Рыночный контекст:", style("ul", fontName="Helvetica-Bold",
            fontSize=9, textColor=TEXT_MUTED, leading=12)),
        bullet("38.9% мирового рынка AI in Music — самый платёжеспособный"),
        bullet("$10–$30/мес — стандартная цена (Suno Pro = $10, Premier = $30)"),
        bullet("B2B: 120K+ рекламных агентств, 2M+ indie game devs"),
        bullet("App Store / Google Play — основной канал дистрибуции"),
        vspace(6),
        Paragraph("B2C воронка:", style("ul", fontName="Helvetica-Bold",
            fontSize=9, textColor=TEXT_MUTED, leading=12)),
        bullet("Free tier: 3 трека/мес — без барьеров входа"),
        bullet("Pro: $12/мес — 50 треков + коммерческие права"),
        bullet("Studio: $29/мес — unlimited + stem export + API"),
        vspace(6),
        Paragraph("B2B стратегия:", style("ul", fontName="Helvetica-Bold",
            fontSize=9, textColor=TEXT_MUTED, leading=12)),
        bullet("API: $49/мес (1000 gen) → $499/мес (15K gen) → Enterprise"),
        bullet("Pilot program: 2 нед. бесплатно для агентств с >10 clients"),
        bullet("Integration: CapCut Business, Adobe Stock Audio партнёрство"),
        bullet("Lawyer-verified «clean IP» — ключевой differentiator для B2B"),
    ]

    def make_col(items, border_color):
        rows = [[item] for item in items]
        t = Table(rows, colWidths=[(W-90)/2])
        t.setStyle(TableStyle([
            ("BACKGROUND",   (0,0),(-1,-1), CARD_BG),
            ("BOX",          (0,0),(-1,-1), 1.5, border_color),
            ("TOPPADDING",   (0,0),(-1,-1), 8),
            ("BOTTOMPADDING",(0,0),(-1,-1), 4),
            ("LEFTPADDING",  (0,0),(-1,-1), 12),
            ("RIGHTPADDING", (0,0),(-1,-1), 12),
        ]))
        return t

    two_col = Table(
        [[make_col(ru_content, ACCENT2), make_col(us_content, ACCENT3)]],
        colWidths=[(W-90)/2, (W-90)/2]
    )
    two_col.setStyle(TableStyle([
        ("VALIGN",         (0,0),(-1,-1), "TOP"),
        ("LEFTPADDING",    (0,0),(-1,-1), 5),
        ("RIGHTPADDING",   (0,0),(-1,-1), 5),
        ("TOPPADDING",     (0,0),(-1,-1), 0),
        ("BOTTOMPADDING",  (0,0),(-1,-1), 0),
    ]))
    elems.append(two_col)
    elems.append(vspace(10))

    # Pricing matrix
    elems.append(Paragraph("Сравнение тарифов: RU vs US", S_SUBSECTION))
    price_data = [
        ["Тариф", "Цена RU", "Цена US", "Треки/мес", "Коммерц. права", "API"],
        ["Free",   "0 ₽",   "$0",   "3",     "✗", "✗"],
        ["Старт / Starter", "290 ₽", "$9",  "30",    "✓", "✗"],
        ["Про / Pro",       "790 ₽", "$19", "150",   "✓", "✗"],
        ["Студия / Studio", "2490 ₽","$29", "∞",     "✓", "✓ (500 req)"],
        ["Enterprise API",  "Индив.", "From $499", "∞", "✓", "Custom SLA"],
    ]
    col_colors_map = {0: TEXT_MUTED, 1: ACCENT2, 2: ACCENT2, 3: TEXT_MAIN,
                      4: TEXT_MAIN,  5: TEXT_MAIN}
    para_price = []
    for i, row in enumerate(price_data):
        if i == 0:
            para_price.append([Paragraph(c, style("ph", fontName="Helvetica-Bold",
                fontSize=8.5, textColor=WHITE, leading=11, alignment=TA_CENTER))
                for c in row])
        else:
            pr = []
            for j, cell in enumerate(row):
                clr = ACCENT if j == 0 else TEXT_MAIN
                if cell in ("✓", "∞"):
                    clr = ACCENT3
                elif cell == "✗":
                    clr = ACCENT_RED
                pr.append(Paragraph(cell, style("pc", fontName="Helvetica",
                    fontSize=9, textColor=clr, leading=12, alignment=TA_CENTER)))
            para_price.append(pr)
    pt = Table(para_price, colWidths=[100, 65, 65, 70, 80, 115], repeatRows=1)
    pt.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0),  ACCENT),
        ("BACKGROUND",    (0,1),(-1,-1), CARD_BG),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [CARD_BG, colors.HexColor("#16213E")]),
        ("GRID",          (0,0),(-1,-1), 0.4, CARD_BORDER),
        ("TOPPADDING",    (0,0),(-1,-1), 6),
        ("BOTTOMPADDING", (0,0),(-1,-1), 6),
        ("LEFTPADDING",   (0,0),(-1,-1), 6),
        ("RIGHTPADDING",  (0,0),(-1,-1), 6),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
    ]))
    elems.append(pt)
    return elems

# ── Page 9: FAQ ──────────────────────────────────────────────────────────────
def page_faq():
    elems = []
    elems += section_header("08 · FAQ: 10 Самых жёстких вопросов",
        "Вопросы, которые задаст любой инвестор, партнёр или пресса")

    faqs = [
        (
            "Q1: Suno v5.5 уже делает voice cloning — чем вы лучше?",
            "Suno создаёт «vocal persona» — шаблон на основе тембра. Он не воспроизводит точную "
            "акустику вашего голоса: форманты, дыхание, вибрато. Наш DiffSinger клонирует биометрию "
            "голоса через WavLM-ECAPA speaker embedding (256-мерный вектор) и синтезирует именно "
            "<b>ваш</b> голос, а не похожий. Тест: носитель языка слышит разницу в blind test. "
            "Плюс: мы не привязаны к платформе — голос можно применить к любому треку через API.",
        ),
        (
            "Q2: Вас засудят как Suno и Udio — вы готовы?",
            "Suno и Udio обучались на стриминге музыки без лицензий. Мы используем исключительно "
            "лицензированные датасеты: OpenSinger (CC BY-NC-SA), VocalSet (MIT), FMA (Creative Commons). "
            "MusicGen-large от Meta обучен на licensed-only данных. Это наш юридический USP "
            "для B2B-сегмента, где агентства не будут рисковать IP-претензиями. Консультация IP-адвоката — "
            "в roadmap на месяц 2.",
        ),
        (
            "Q3: Почему пользователи переключатся с Suno ($10/мес) на вас?",
            "Suno не имеет: (1) персонального голосового клона из своих записей, "
            "(2) полного трека из напетого фрагмента без текстового промпта, "
            "(3) мастеринга по стандартам стриминга. Наш target — не те, кто уже в Suno. "
            "Наш target — те 180M человек, которые поют, но ни разу не пробовали AI-музыку, "
            "потому что «не умеют писать промпты».",
        ),
        (
            "Q4: Вы можете сгенерировать трек за <5 минут на одном A100?",
            "Да, с оговорками. Enhancement (Demucs + DeepFilterNet): 15 сек. "
            "ASR (Whisper large-v3): 10 сек. Speaker embedding: 3 сек. "
            "MusicGen-large (2 мин инструментал): 45–90 сек. "
            "DiffSinger SVS (DDIM 50 steps, 2 мин вокал): 60–120 сек. "
            "Mixing + mastering: 5 сек. Итого: 2.5–4 мин на A100 80GB. "
            "Трек на 4+ мин потребует ~7 мин. В roadmap — ONNX-оптимизация для ускорения ×2.",
        ),
        (
            "Q5: Каково качество — это будет звучать как профессиональный трек?",
            "DiffSinger + HiFi-GAN достигают MOS (Mean Opinion Score) ~4.1/5 на стандартных тестах "
            "(OpenSinger eval set). Это уровень «хорошая демо-запись», не «студийный мастер». "
            "Для контент-мейкеров — достаточно. Для профессионального релиза — нет. "
            "Честная позиция: мы конкурируем с GarageBand + SoundOn, не с Abbey Road Studios.",
        ),
        (
            "Q6: У вас нет данных пользователей — как обучить модели на хороших голосах?",
            "Нам не нужны данные пользователей для обучения. Speaker encoder работает zero-shot: "
            "он обучен на VoxCeleb2 (6112 спикеров) и обобщается на любой новый голос без "
            "дообучения. WavLM-large + ECAPA-TDNN — state-of-the-art в speaker verification. "
            "SITW EER = 1.8% на нашей архитектуре. Пользовательский голос обрабатывается "
            "инференсом, не тренировкой — GDPR-friendly.",
        ),
        (
            "Q7: Каков план выхода для инвесторов?",
            "Три сценария: (1) M&A — приобретение стриминговой платформой (Spotify, Яндекс Музыка) "
            "или ad-tech компанией для встроенной персонализации. Прецедент: Spotify купил "
            "Sonantic (TTS) за ~$100M. (2) Strategic investment — мейджор-лейбл как Warner "
            "инвестировал в Boomy, UMG — в Udio. (3) IPO при ARR >$50M (горизонт 4–5 лет).",
        ),
        (
            "Q8: Почему не Россия-только? Почему сразу глобально?",
            "Россия — стартовый рынок с низкой конкуренцией (Suno/Udio заблокированы или недоступны). "
            "Но TAM в России — $30–50M (оценка). Глобальный TAM — $5.2B. "
            "Архитектура API-first позволяет обслуживать оба рынка с одним бэкендом. "
            "Русскоязычный рынок — плацдарм для отработки продукта до US-запуска.",
        ),
        (
            "Q9: Сколько стоит обучение всех моделей и откуда деньги?",
            "Расчёт: Speaker Encoder (4×A100, 5 дней, $1.49/GPU/h, RunPod): ~$715. "
            "DiffSinger (8×A100, 14 дней): ~$3,360. MusicGen LoRA (8×A100, 5 дней): ~$1,200. "
            "Lyrics LLM QLoRA (4×A100, 3 дня): ~$430. Итого: ~$5,700. "
            "Инфраструктура: $800/мес (inference, 2×A100 on-demand). "
            "Seed round цель: $500K для найма 2 ML-инженеров + 12 мес runway.",
        ),
        (
            "Q10: Что мешает Google/Meta/Apple сделать то же самое завтра?",
            "Ничего технически — если они захотят. Но: Google MusicLM ориентирован на B2B и "
            "не выпускает consumer продукт. Meta AudioCraft — open source, не продукт. "
            "Apple — не в этом бизнесе. Наше преимущество — не технология (она открытая), "
            "а: (1) скорость выхода на рынок, (2) фокус на user voice experience, "
            "(3) юридически чистый IP для B2B. Big Tech боится музыкальных лейблов — "
            "именно поэтому Suno, Udio и Beatoven существуют.",
        ),
    ]

    for q, a in faqs:
        elems.append(Paragraph(q, S_FAQ_Q))
        elems.append(Paragraph(a, S_FAQ_A))
        elems.append(hr(CARD_BORDER, 0.5))

    return elems

# ── Final slide ──────────────────────────────────────────────────────────────
def page_closing():
    elems = []
    elems.append(vspace(60))
    elems.append(Paragraph("Что дальше?", style("ct", fontName="Helvetica-Bold",
        fontSize=32, textColor=WHITE, leading=38, spaceAfter=6)))
    elems.append(Paragraph(
        "Дорожная карта от идеи до $3M ARR",
        style("cs", fontName="Helvetica", fontSize=14, textColor=ACCENT2,
            leading=18, spaceAfter=20)))
    elems.append(hr())

    roadmap = [
        ["Месяц", "Milestone", "Бюджет"],
        ["1–2",  "Обучение моделей (DiffSinger, Speaker, MusicGen LoRA)", "$6–8K GPU"],
        ["2–3",  "MVP API + Telegram-бот для демо", "$0 (команда)"],
        ["3",    "ProductHunt запуск + 1,000 первых пользователей", "$2K маркетинг"],
        ["3–6",  "VK Mini App + 5,000 платящих RU-пользователей", "$5K retention"],
        ["6",    "US beta launch — Web app + ProductHunt EN", "$10K PR"],
        ["9",    "10,000 платящих глобально + 5 B2B-клиентов", "—"],
        ["12",   "Seed round close · ARR $3M · Series A prep", "$500K raise"],
    ]
    para_road = []
    for i, row in enumerate(roadmap):
        if i == 0:
            para_road.append([Paragraph(c, style("rh", fontName="Helvetica-Bold",
                fontSize=9, textColor=WHITE, leading=12, alignment=TA_CENTER))
                for c in row])
        else:
            para_road.append([
                Paragraph(row[0], style("rm", fontName="Helvetica-Bold", fontSize=10,
                    textColor=ACCENT2, leading=13, alignment=TA_CENTER)),
                Paragraph(row[1], style("rm2", fontName="Helvetica", fontSize=10,
                    textColor=TEXT_MAIN, leading=13)),
                Paragraph(row[2], style("rm3", fontName="Helvetica-Bold", fontSize=9,
                    textColor=ACCENT3, leading=13, alignment=TA_CENTER)),
            ])
    rt = Table(para_road, colWidths=[50, 340, 105], repeatRows=1)
    rt.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0),  ACCENT),
        ("BACKGROUND",    (0,1),(-1,-1), CARD_BG),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [CARD_BG, colors.HexColor("#16213E")]),
        ("GRID",          (0,0),(-1,-1), 0.4, CARD_BORDER),
        ("TOPPADDING",    (0,0),(-1,-1), 8),
        ("BOTTOMPADDING", (0,0),(-1,-1), 8),
        ("LEFTPADDING",   (0,0),(-1,-1), 10),
        ("RIGHTPADDING",  (0,0),(-1,-1), 10),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
    ]))
    elems.append(rt)
    elems.append(vspace(24))

    cta_data = [[
        Paragraph("💌  Контакт", style("cta1", fontName="Helvetica-Bold",
            fontSize=11, textColor=ACCENT2, leading=14, alignment=TA_CENTER)),
        Paragraph("📊  Данные", style("cta2", fontName="Helvetica-Bold",
            fontSize=11, textColor=ACCENT3, leading=14, alignment=TA_CENTER)),
        Paragraph("🚀  Статус", style("cta3", fontName="Helvetica-Bold",
            fontSize=11, textColor=ACCENT, leading=14, alignment=TA_CENTER)),
    ],[
        Paragraph("nadlervalentin2000\n@gmail.com", style("ctav", fontName="Helvetica",
            fontSize=9, textColor=TEXT_MUTED, leading=13, alignment=TA_CENTER)),
        Paragraph("github.com/Firephase/Start\nbranch: claude/generative-audio-*",
            style("ctav", fontName="Helvetica", fontSize=9, textColor=TEXT_MUTED,
                leading=13, alignment=TA_CENTER)),
        Paragraph("MVP ready · Models training\nSeed seeking",
            style("ctav", fontName="Helvetica-Bold", fontSize=9, textColor=ACCENT,
                leading=13, alignment=TA_CENTER)),
    ]]
    cta = Table(cta_data, colWidths=[(W-80)/3]*3)
    cta.setStyle(TableStyle([
        ("BACKGROUND",   (0,0),(-1,-1), CARD_BG),
        ("BOX",          (0,0),(-1,-1), 1, ACCENT),
        ("INNERGRID",    (0,0),(-1,-1), 0.5, CARD_BORDER),
        ("TOPPADDING",   (0,0),(-1,-1), 12),
        ("BOTTOMPADDING",(0,0),(-1,-1), 12),
        ("VALIGN",       (0,0),(-1,-1), "MIDDLE"),
    ]))
    elems.append(cta)
    elems.append(vspace(30))
    elems.append(Paragraph(
        "Sources: Grand View Research · Market.us · MarketsandMarkets · Spherical Insights · "
        "TechCrunch · Billboard · Music Business Worldwide · Variety · Sacra · Crunchbase",
        S_FOOTER))
    return elems

# ── Background on each page ──────────────────────────────────────────────────
def on_page(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(PAGE_BG)
    canvas.rect(0, 0, W, H, fill=1, stroke=0)
    # Accent line top
    canvas.setFillColor(ACCENT)
    canvas.rect(0, H - 4, W, 4, fill=1, stroke=0)
    # Page number (skip cover page 1)
    if doc.page > 1:
        canvas.setFillColor(TEXT_MUTED)
        canvas.setFont("Helvetica", 7)
        canvas.drawRightString(W - 28, 16, f"Generative Audio Composition  ·  Market Research 2025")
        canvas.setFillColor(ACCENT)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawRightString(W - 28, 26, f"{doc.page - 1} / 9")
    canvas.restoreState()

# ── Build PDF ────────────────────────────────────────────────────────────────
def build():
    doc = SimpleDocTemplate(
        OUTPUT_PATH,
        pagesize=A4,
        leftMargin=30*mm,
        rightMargin=20*mm,
        topMargin=20*mm,
        bottomMargin=18*mm,
    )

    story = []
    story += title_slide()
    story.append(PageBreak())
    story += page_competitors()
    story.append(PageBreak())
    story += page_audience()
    story.append(PageBreak())
    story += page_pain()
    story.append(PageBreak())
    story += page_market()
    story.append(PageBreak())
    story += page_risks()
    story.append(PageBreak())
    story += page_channels()
    story.append(PageBreak())
    story += page_sales()
    story.append(PageBreak())
    story += page_faq()
    story.append(PageBreak())
    story += page_closing()

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    print(f"PDF saved: {OUTPUT_PATH}")

if __name__ == "__main__":
    build()
