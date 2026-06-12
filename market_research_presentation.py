#!/usr/bin/env python3
"""Generate market research PDF presentation — Cyrillic-safe with Liberation Sans."""

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── Register Unicode fonts (Cyrillic-capable) ────────────────────────────────
FONT_DIR = "/usr/share/fonts/truetype/liberation"
pdfmetrics.registerFont(TTFont("Reg",    f"{FONT_DIR}/LiberationSans-Regular.ttf"))
pdfmetrics.registerFont(TTFont("Bold",   f"{FONT_DIR}/LiberationSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont("Italic", f"{FONT_DIR}/LiberationSans-Italic.ttf"))
pdfmetrics.registerFont(TTFont("BoldIt", f"{FONT_DIR}/LiberationSans-BoldItalic.ttf"))
from reportlab.pdfbase.pdfmetrics import registerFontFamily
registerFontFamily("Lib", normal="Reg", bold="Bold", italic="Italic", boldItalic="BoldIt")

# ── Palette ──────────────────────────────────────────────────────────────────
C_BG      = colors.HexColor("#0F0F1A")
C_CARD    = colors.HexColor("#1A1A2E")
C_BORDER  = colors.HexColor("#2D3748")
C_ACCENT  = colors.HexColor("#7C3AED")   # violet
C_CYAN    = colors.HexColor("#06B6D4")
C_GREEN   = colors.HexColor("#10B981")
C_AMBER   = colors.HexColor("#F59E0B")
C_RED     = colors.HexColor("#EF4444")
C_PINK    = colors.HexColor("#EC4899")
C_WHITE   = colors.white
C_TEXT    = colors.HexColor("#E2E8F0")
C_MUTED   = colors.HexColor("#94A3B8")
C_STRIPE  = colors.HexColor("#16213E")

W, H = A4
OUTPUT = "/home/user/Start/market_research.pdf"

# ── Style factory ────────────────────────────────────────────────────────────
def S(name, font="Reg", size=10, color=C_TEXT, align=TA_LEFT,
      leading=None, space_before=0, space_after=4,
      left_indent=0, first_indent=0):
    return ParagraphStyle(
        name,
        fontName=font,
        fontSize=size,
        textColor=color,
        alignment=align,
        leading=leading or size * 1.4,
        spaceBefore=space_before,
        spaceAfter=space_after,
        leftIndent=left_indent,
        firstLineIndent=first_indent,
    )

# Pre-built styles
s_slide_title   = S("st",  "Bold",   30, C_WHITE,   TA_LEFT,  38,  0,  6)
s_slide_sub     = S("ss",  "Reg",    13, C_CYAN,    TA_LEFT,  17,  0, 14)
s_section       = S("sec", "Bold",   18, C_ACCENT,  TA_LEFT,  24, 10,  6)
s_subsection    = S("sub", "Bold",   12, C_CYAN,    TA_LEFT,  16,  8,  4)
s_body          = S("bod", "Reg",    10, C_TEXT,    TA_JUSTIFY,14, 2,  4)
s_bullet        = S("bul", "Reg",    10, C_TEXT,    TA_LEFT,  14,  2,  3, 14, -10)
s_bullet2       = S("bl2", "Reg",     9, C_MUTED,   TA_LEFT,  13,  1,  2, 26, -10)
s_caption       = S("cap", "Italic",  8, C_MUTED,   TA_CENTER,11,  2,  2)
s_footer        = S("ftr", "Reg",     7, C_MUTED,   TA_CENTER,10,  0,  0)
s_faq_q         = S("fqq", "Bold",   11, C_AMBER,   TA_LEFT,  15,  8,  3)
s_faq_a         = S("fqa", "Reg",    10, C_TEXT,    TA_JUSTIFY,14, 2,  6, 12)
s_note          = S("not", "Italic",  8, C_MUTED,   TA_JUSTIFY,12, 4,  2)

def sc(name, **kw): return S(name, **kw)   # shortcut

# ── Helpers ───────────────────────────────────────────────────────────────────
def vs(n=6):   return Spacer(1, n)
def hr(c=C_ACCENT, t=1):
    return HRFlowable(width="100%", thickness=t, color=c, spaceAfter=8, spaceBefore=4)

def p(text, style): return Paragraph(text, style)

def bul(text, sub=False):
    prefix = "◆ " if not sub else "  › "
    return Paragraph(prefix + text, s_bullet if not sub else s_bullet2)

def cell(text, font="Reg", size=9, color=C_TEXT, align=TA_CENTER, leading=None):
    return Paragraph(text, S("_c", font, size, color, align, leading))

def tbl(data, col_widths, style_cmds=None):
    t = Table(data, colWidths=col_widths)
    base = [
        ("BACKGROUND",   (0,0),(-1,-1), C_CARD),
        ("GRID",         (0,0),(-1,-1), 0.4, C_BORDER),
        ("TOPPADDING",   (0,0),(-1,-1), 6),
        ("BOTTOMPADDING",(0,0),(-1,-1), 6),
        ("LEFTPADDING",  (0,0),(-1,-1), 7),
        ("RIGHTPADDING", (0,0),(-1,-1), 7),
        ("VALIGN",       (0,0),(-1,-1), "MIDDLE"),
    ]
    if style_cmds:
        base += style_cmds
    t.setStyle(TableStyle(base))
    return t

def header_tbl(headers, rows, widths, accent=C_ACCENT):
    """Table with colored header row."""
    h_row = [cell(h, "Bold", 9, C_WHITE, TA_CENTER) for h in headers]
    all_rows = [h_row] + rows
    extra = [
        ("BACKGROUND",    (0,0),(-1,0),   accent),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),  [C_CARD, C_STRIPE]),
    ]
    return tbl(all_rows, widths, extra)

def metric_box(value, label, color=C_CYAN):
    inner = [
        [cell(value, "Bold", 20, color, TA_CENTER)],
        [cell(label, "Reg",   8, C_MUTED, TA_CENTER)],
    ]
    t = Table(inner)
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0,0),(-1,-1), C_CARD),
        ("BOX",          (0,0),(-1,-1), 1, color),
        ("TOPPADDING",   (0,0),(-1,-1), 10),
        ("BOTTOMPADDING",(0,0),(-1,-1), 10),
        ("LEFTPADDING",  (0,0),(-1,-1), 8),
        ("RIGHTPADDING", (0,0),(-1,-1), 8),
    ]))
    return t

def metrics_row(items):
    cw = (W - 80) / len(items)
    cells = [[metric_box(v, l, c) for v, l, c in items]]
    t = Table(cells, colWidths=[cw]*len(items))
    t.setStyle(TableStyle([
        ("VALIGN",        (0,0),(-1,-1), "TOP"),
        ("LEFTPADDING",   (0,0),(-1,-1), 3),
        ("RIGHTPADDING",  (0,0),(-1,-1), 3),
        ("TOPPADDING",    (0,0),(-1,-1), 0),
        ("BOTTOMPADDING", (0,0),(-1,-1), 0),
    ]))
    return t

def section_hdr(title, sub=""):
    out = [p(title, s_section)]
    if sub:
        out.append(p(sub, s_slide_sub))
    out.append(hr())
    return out

# ── Page canvas callback (background + stripe) ───────────────────────────────
def on_page(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(C_BG)
    canvas.rect(0, 0, W, H, fill=1, stroke=0)
    canvas.setFillColor(C_ACCENT)
    canvas.rect(0, H - 5, W, 5, fill=1, stroke=0)
    if doc.page > 1:
        canvas.setFont("Reg", 7)
        canvas.setFillColor(C_MUTED)
        canvas.drawString(30, 16, "Generative Audio Composition  ·  Market Research 2025")
        canvas.setFont("Bold", 9)
        canvas.setFillColor(C_ACCENT)
        canvas.drawRightString(W - 28, 16, f"{doc.page - 1} / 9")
    canvas.restoreState()

# ════════════════════════════════════════════════════════════════════════════
# SLIDES
# ════════════════════════════════════════════════════════════════════════════

def slide_cover():
    out = []
    out.append(vs(50))
    # badge
    badge = tbl([[cell("MARKET RESEARCH  ·  2025–2026", "Bold", 8, C_ACCENT, TA_CENTER)]],
                [210], [("BOX",(0,0),(-1,-1),1,C_ACCENT),
                        ("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#12002A"))])
    out.append(badge)
    out.append(vs(18))
    out.append(p("Generative Audio", S("t1","Bold",44,C_WHITE,TA_LEFT,52)))
    out.append(p("Composition", S("t2","Bold",44,C_ACCENT,TA_LEFT,52,0,10)))
    out.append(p(
        "Превращаем любительские записи голоса в профессиональные треки "
        "с клонированием вашего голоса. Анализ рынка и стратегия выхода.",
        S("ts","Reg",13,C_MUTED,TA_LEFT,19,0,0)))
    out.append(vs(30))
    out.append(hr(C_ACCENT, 1))

    strip = tbl([[
        cell("$569M\nРынок генерат. AI music 2024",  "Bold",11,C_CYAN, TA_CENTER),
        cell("30.5% CAGR\nРост 2025–2030",            "Bold",11,C_GREEN,TA_CENTER),
        cell("$2.8B\nПрогноз рынка 2030",             "Bold",11,C_AMBER,TA_CENTER),
        cell("Нет аналогов\nголосовой клон + трек",   "Bold",11,C_ACCENT,TA_CENTER),
    ]], [(W-80)/4]*4, [
        ("INNERGRID",    (0,0),(-1,-1), 0.5, C_BORDER),
        ("TOPPADDING",   (0,0),(-1,-1), 14),
        ("BOTTOMPADDING",(0,0),(-1,-1), 14),
    ])
    out.append(strip)
    out.append(vs(40))
    out.append(p("Конфиденциально · Июнь 2025", s_footer))
    return out


def slide_competitors():
    out = []
    out += section_hdr("01 · Конкурентный ландшафт",
                        "Кто уже на рынке — и что им не хватает")

    widths = [88, 70, 54, 44, 56, 123]
    headers = ["Компания", "Funding", "Цена/мес", "Голос?", "Полный трек?", "Ключевой gap"]

    def row(name, fund, price, voice, track, gap, vc, tc):
        return [
            cell(name,  "Bold", 9, C_CYAN,  TA_LEFT),
            cell(fund,  "Reg",  8, C_MUTED, TA_LEFT),
            cell(price, "Reg",  9, C_TEXT,  TA_CENTER),
            cell(voice, "Bold",10, vc,      TA_CENTER),
            cell(track, "Bold",10, tc,      TA_CENTER),
            cell(gap,   "Reg",  8, C_RED,   TA_LEFT),
        ]

    rows = [
        row("Suno AI",  "$775M+\n$5.4B val", "$0–$30",
            "✓ v5.5\n(persona)", "✓",
            "Не «твой» голос\nНет stem export",    C_GREEN, C_GREEN),
        row("Udio AI",  "$70M (a16z)",        "$0–$30",
            "✗",                 "✓",
            "Судебные риски\nНет voice clone",     C_RED,   C_GREEN),
        row("Boomy",    "WMG seed",            "$10–$30",
            "✗",                 "✓",
            "Нет персонализации\nНизкое качество", C_RED,   C_GREEN),
        row("Soundraw", "Не раскрыто",         "$11–$32",
            "✗",                 "✓",
            "Только инструментал\nНет вокала",     C_RED,   C_GREEN),
        row("AIVA",     "€3M+",                "€0–€49",
            "✗",                 "✓",
            "Только классика/кино\nНет pop/r&b",   C_RED,   C_GREEN),
        row("Mubert",   "Не раскрыто",         "$0–$199",
            "✗",                 "~",
            "Только фоновая музыка\nНет структуры",C_RED,   C_AMBER),
        row("Beatoven", "$2.4M",               "$0–?",
            "✗",                 "~",
            "Beta стадия\nНет пользов. голоса",    C_RED,   C_AMBER),
    ]

    out.append(header_tbl(headers, rows, widths))
    out.append(vs(12))
    out.append(p("Наша уникальная позиция", s_subsection))

    usp = tbl([[
        cell("🎤 Клонирует голос\nпользователя",           "Bold",10,C_WHITE,TA_CENTER),
        cell("🎵 Полная аранжировка\nиз напетого фрагмента","Bold",10,C_WHITE,TA_CENTER),
        cell("🎼 Структура песни\nиз 5 секунд записи",     "Bold",10,C_WHITE,TA_CENTER),
        cell("🏆 Мастеринг\n–14 LUFS (стриминг)",          "Bold",10,C_WHITE,TA_CENTER),
    ]], [(W-80)/4]*4, [
        ("BACKGROUND",   (0,0),(-1,-1), colors.HexColor("#12002A")),
        ("BOX",          (0,0),(-1,-1), 1.5, C_ACCENT),
        ("INNERGRID",    (0,0),(-1,-1), 0.5, C_ACCENT),
        ("TOPPADDING",   (0,0),(-1,-1), 13),
        ("BOTTOMPADDING",(0,0),(-1,-1), 13),
    ])
    out.append(usp)
    return out


def slide_audience():
    out = []
    out += section_hdr("02 · Целевая аудитория",
                        "6 ключевых персон — боли и готовность платить")

    personas = [
        ("🎤 Алексей, 24",  "AMATEUR SINGER · B2C CORE",
         "Поёт в душе и на домашних записях. Хочет звучать как на радио, "
         "но не умеет играть и не может позволить студию.",
         "Студия — $200/час. Нет инструментов.", "$12–25/мес", "~180M певцов по миру", C_ACCENT),
        ("📱 Диана, 21",    "CONTENT CREATOR · B2C GROWTH",
         "TikTok/Reels-блогер, 50k+ подписчиков. Ищет уникальный саундтрек — "
         "не хочет copyright-strike.",
         "Стоковая музыка — безликая. AI без голоса — пусто.", "$10–20/мес", "~50M creators", C_CYAN),
        ("🎮 Михаил, 31",   "INDIE GAME DEV · B2C/B2B",
         "Соло-разработчик инди-игры. Нужен OST на 2 часа — "
         "нанять композитора не по бюджету ($5k–$30k).",
         "MusicGen — только инструментал. Нет вокала персонажей.", "$30–50/мес", "~2M indie devs", C_GREEN),
        ("🎵 Карина, 28",   "PROSUMER MUSICIAN · B2C UPSELL",
         "Умеет петь, пишет тексты, но не умеет аранжировать. "
         "Хочет записать демо для лейблов.",
         "Аранжировщик — $500+/трек. 10 треков = $5000.", "$29–49/мес", "~40M songwriters", C_AMBER),
        ("📺 Рекламное агентство", "AD AGENCY · B2B REVENUE",
         "Создаёт 20–50 роликов в месяц. Каждому нужна оригинальная музыка "
         "и джингл с нужным брендовым голосом.",
         "Лицензия трека — $500–$5000. Джингл от студии — $2k–$15k.", "$500–2000/мес (API)", "~120k агентств", C_PINK),
        ("🎙 Подкастер / YouTuber", "PODCAST / YT · B2C MASS",
         "Ведёт еженедельный подкаст. Нужен собственный джингл "
         "и фоновая музыка с его голосом в интро.",
         "Нет своего голоса в генераторах. Всё звучит одинаково.", "$8–15/мес", "~5M подкастеров", C_CYAN),
    ]

    for i in range(0, len(personas), 2):
        pair = personas[i:i+2]
        cards = []
        for name, tag, desc, pain, wtp, size, color in pair:
            inner = [
                [cell(name, "Bold", 12, C_WHITE, TA_LEFT)],
                [cell(tag,  "Bold",  7, color,   TA_LEFT)],
                [vs(3)],
                [p(desc,  S("pd","Reg",9,C_TEXT,TA_JUSTIFY,13))],
                [vs(3)],
                [p("⚡ Боль: " + pain, S("pp","Reg",9,C_TEXT,TA_LEFT,13))],
                [vs(3)],
                [tbl([[
                    cell("💰 WTP: " + wtp, "Bold", 8, C_GREEN, TA_CENTER),
                    cell("👥 " + size,      "Reg",  8, C_MUTED, TA_CENTER),
                ]], [120, 120])],
            ]
            card = Table([[row_item] for row_item in inner],
                         colWidths=[(W-100)/2])
            card.setStyle(TableStyle([
                ("BACKGROUND",   (0,0),(-1,-1), C_CARD),
                ("BOX",          (0,0),(-1,-1), 1.2, color),
                ("TOPPADDING",   (0,0),(-1,-1), 10),
                ("BOTTOMPADDING",(0,0),(-1,-1), 8),
                ("LEFTPADDING",  (0,0),(-1,-1), 12),
                ("RIGHTPADDING", (0,0),(-1,-1), 12),
            ]))
            cards.append(card)

        if len(cards) == 1:
            cards.append(Spacer(1, 1))

        row_tbl = Table([cards], colWidths=[(W-80)/2]*2)
        row_tbl.setStyle(TableStyle([
            ("VALIGN",        (0,0),(-1,-1), "TOP"),
            ("LEFTPADDING",   (0,0),(-1,-1), 5),
            ("RIGHTPADDING",  (0,0),(-1,-1), 5),
            ("TOPPADDING",    (0,0),(-1,-1), 0),
            ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ]))
        out.append(row_tbl)
    return out


def slide_pain():
    out = []
    out += section_hdr("03 · Боли, которые мы решаем",
                        "Что не так с текущими решениями — реальные факты")

    items = [
        ("🔇 Нет клонирования голоса",
         "Ни один публичный инструмент не позволяет загрузить 5 секунд своего голоса "
         "и получить трек, спетый именно вашим голосом. "
         "Suno v5.5 создаёт «вокальную персону» — шаблон тембра. "
         "Пользователи: «звучит похоже, но не я». Мы клонируем биометрию через WavLM-ECAPA.", C_RED),
        ("🎹 Нет полного трека из напетого фрагмента",
         "Существующие инструменты требуют текстового промпта: «создай рок в ля-миноре». "
         "Обычный пользователь не знает тональностей. Он хочет просто напеть — "
         "и получить готовый трек в своём стиле. Такого нет нигде.", C_AMBER),
        ("📝 AI не слышит ваши слова",
         "Boomy, Soundraw, Mubert не берут тексты. Suno/Udio берут — "
         "но только как текстовый ввод, не из записанного голоса. "
         "Если вы импровизировали мелодию со словами — система их не слышит.", C_CYAN),
        ("⚖️ Юридическая неопределённость",
         "Suno и Udio обвинили все три мейджора (UMG, Sony, Warner). "
         "Udio урегулировал: $0.002–$0.005 за генерацию. "
         "Мы используем только лицензированные датасеты (OpenSinger CC, VocalSet MIT, FMA CC) — "
         "юридический USP для B2B-клиентов.", C_GREEN),
        ("🎚 Нет профессионального мастеринга",
         "Треки из Suno/Udio выходят при –18…–20 LUFS. "
         "Spotify требует –14 LUFS, TikTok –14, YouTube –13.5. "
         "Пользователи вынуждены платить за Landr ($9–$29/трек). "
         "Мы включаем мастеринг в пайплайн автоматически.", C_PINK),
    ]

    for title, body, color in items:
        row = [[
            cell(title, "Bold", 11, color, TA_LEFT),
            p(body, S("pb","Reg",9.5,C_TEXT,TA_JUSTIFY,14)),
        ]]
        t = tbl(row, [195, W-80-195-10], [
            ("LEFTBORDER", (0,0),(0,-1), 3, color),
        ])
        out.append(t)
        out.append(vs(5))
    return out


def slide_market():
    out = []
    out += section_hdr("04 · Размер рынка",
                        "TAM · SAM · SOM — с источниками и методологией расчёта")

    out.append(metrics_row([
        ("$5.2B",  "TAM · AI in Music\n(Market.us, 2024)",        C_ACCENT),
        ("$569M",  "Generat. AI Music\n(Grand View Research, 2024)", C_CYAN),
        ("$2.7B",  "Voice Cloning Market\n(R&M, 2024)",           C_GREEN),
        ("30.5%",  "CAGR 2025–2030\n(Grand View Research)",       C_AMBER),
    ]))
    out.append(vs(10))
    out.append(p("Методология: TAM → SAM → SOM", s_subsection))

    widths = [55, 215, 95, 130]
    headers = ["Уровень", "Описание", "Размер (2024)", "Источник"]
    rows = [
        [cell("TAM",    "Bold",10,C_CYAN,  TA_CENTER),
         cell("Весь рынок AI in Music + Voice Cloning\n(генерация, синтез, мастеринг, дистрибуция)",
              "Reg",9,C_TEXT,TA_LEFT),
         cell("$7.9B",  "Bold",11,C_CYAN, TA_CENTER),
         cell("Market.us + R&M 2024","Reg",8,C_MUTED,TA_LEFT)],

        [cell("SAM",    "Bold",10,C_GREEN, TA_CENTER),
         cell("Инструменты генерации треков для просьюмеров,\n"
              "контент-мейкеров, инди-разработчиков\n(исключаем enterprise SaaS для мейджоров)",
              "Reg",9,C_TEXT,TA_LEFT),
         cell("$920M",  "Bold",11,C_GREEN,TA_CENTER),
         cell("GVR Generat. AI Music\n+ Voice Cloning SAM","Reg",8,C_MUTED,TA_LEFT)],

        [cell("SOM Y1", "Bold",10,C_AMBER, TA_CENTER),
         cell("Реально достижимая доля в первый год:\n"
              "US + RU рынки, B2C подписки + B2B API.\n"
              "0.03% от SAM при 10k платящих @ $25 ARPU",
              "Reg",9,C_TEXT,TA_LEFT),
         cell("$3M ARR","Bold",11,C_AMBER,TA_CENTER),
         cell("Bottom-up расчёт\n(см. ниже)","Reg",8,C_MUTED,TA_LEFT)],

        [cell("SOM Y3", "Bold",10,C_PINK,  TA_CENTER),
         cell("При масштабировании до 150k платящих\n"
              "+ B2B контракты (10 агентств × $1200/мес)",
              "Reg",9,C_TEXT,TA_LEFT),
         cell("$54M ARR","Bold",11,C_PINK, TA_CENTER),
         cell("3-year projection","Reg",8,C_MUTED,TA_LEFT)],
    ]
    out.append(header_tbl(headers, rows, widths))
    out.append(vs(8))
    out.append(p(
        "Bottom-up расчёт SOM Y1: контент-мейкеры US+RU (50M потенциальных) → конверсия 0.02% = "
        "10,000 платящих × $25 ARPU × 12 мес = $3M ARR. "
        "Дополнительно: 5 B2B-агентств × $1,200/мес = +$72K ARR в первый год.",
        s_note))
    return out


def slide_risks():
    out = []
    out += section_hdr("05 · Риски и прогноз выручки",
                        "Что может пойти не так — и почему это управляемо")

    risks = [
        ("🔴 ВЫСОКИЙ", "Авторские права на обучающие данные",
         "Иски от мейджоров (как против Suno/Udio). Udio урегулировал за ~$0.002–0.005/генерацию.",
         "Используем только лицензированные данные: OpenSinger (CC), VocalSet (MIT), FMA (CC). "
         "Юридически чище всех конкурентов.", C_RED),
        ("🟡 СРЕДНИЙ", "Конкуренция с Suno/Udio при добавлении voice clone",
         "Suno v5.5 уже имеет «vocal persona» — упрощает барьер для пользователей.",
         "Наш голос — настоящий акустический клон из 5 секунд, не шаблон. "
         "Поддерживаем загрузку без блокировки по платформе.", C_AMBER),
        ("🟡 СРЕДНИЙ", "Задержка обучения моделей",
         "DiffSinger требует 2–3 недели на 8×A100. "
         "Если A100 дорожают — бюджет обучения растёт.",
         "LoRA fine-tuning снижает GPU-время с 3 недель до 5 дней. "
         "RunPod spot instances: $1.49/GPU/h.", C_AMBER),
        ("🟢 НИЗКИЙ", "Качество голоса при малом числе примеров (1–10 фрагментов)",
         "WavLM speaker embedding теряет качество при <3 сек аудио.",
         "Минимум 5 секунд хорошего аудио. DeepFilterNet убирает шум. "
         "Enhancement pipeline компенсирует плохой микрофон.", C_GREEN),
        ("🟢 НИЗКИЙ", "Проблема холодного старта — нет данных пользователей",
         "Нет тренировочных данных на пользовательские голоса в продакшене.",
         "Speaker encoder работает zero-shot: обучен на VoxCeleb2 (6112 спикеров). "
         "WavLM-ECAPA обобщается на любой голос без дообучения.", C_GREEN),
    ]

    for badge, title, risk_txt, fix_txt, color in risks:
        row = [[
            cell(badge, "Bold", 9, color, TA_CENTER),
            p(f"{title}\n\nРиск: {risk_txt}",
              S("rr","Reg",9.5,C_TEXT,TA_LEFT,14)),
            p(f"✓ Митигация: {fix_txt}",
              S("rf","Reg",9.5,C_GREEN,TA_LEFT,14)),
        ]]
        t = tbl(row, [70, 215, W-80-70-215-10])
        out.append(t)
        out.append(vs(4))

    out.append(vs(8))
    out.append(p("Прогноз выручки — Year 1", s_subsection))

    widths2 = [80, 115, 80, 110, 110]
    headers2 = ["Сценарий", "Платящих пользов.", "ARPU/мес", "B2B контрактов", "ARR (Year 1)"]
    rows2 = [
        [cell("🐻 Медведь","Bold",10,C_RED,  TA_CENTER),
         cell("3,000",     "Reg", 10,C_TEXT, TA_CENTER),
         cell("$15",       "Reg", 10,C_TEXT, TA_CENTER),
         cell("0",         "Reg", 10,C_TEXT, TA_CENTER),
         cell("$540K",     "Bold",12,C_RED,  TA_CENTER)],
        [cell("📊 База",   "Bold",10,C_CYAN, TA_CENTER),
         cell("10,000",    "Reg", 10,C_TEXT, TA_CENTER),
         cell("$25",       "Reg", 10,C_TEXT, TA_CENTER),
         cell("5 × $1,200","Reg", 10,C_TEXT, TA_CENTER),
         cell("$3.07M",    "Bold",12,C_CYAN, TA_CENTER)],
        [cell("🚀 Бык",    "Bold",10,C_GREEN,TA_CENTER),
         cell("30,000",    "Reg", 10,C_TEXT, TA_CENTER),
         cell("$28",       "Reg", 10,C_TEXT, TA_CENTER),
         cell("15 × $1,500","Reg",10,C_TEXT, TA_CENTER),
         cell("$10.35M",   "Bold",12,C_GREEN,TA_CENTER)],
    ]
    out.append(header_tbl(headers2, rows2, widths2))
    return out


def slide_channels():
    out = []
    out += section_hdr("06 · Каналы продвижения",
                        "Воронка от первых пользователей до $3M ARR")

    channels = [
        ("0–3 мес",  "Product-Led Growth (PLG)", C_ACCENT, [
            "Freemium: 3 трека/мес бесплатно — без кредитки",
            'Вирус: «Made with GAC» watermark в бесплатной версии — убирается на Pro',
            "TikTok/Reels: «напел 10 сек → получил трек». Target CTR >3%",
            "ProductHunt запуск — цель: Top-3 of the Day",
            "Reddit: r/WeAreTheMusicMakers, r/Songwriting, r/gamedev — органически",
        ]),
        ("1–6 мес",  "Creator Partnership", C_CYAN, [
            "10–20 микро-инфлюенсеров (50k–500k подп.): indie music, content creation, gamedev",
            "Deal: Pro-аккаунт + $200–$500 за review-видео. ROI > paid ads",
            "YouTube Shorts: «before/after» — голос → трек. Алгоритм продвигает",
            "Discord (Suno/Udio community): естественный переход конкурентной аудитории",
            "Spotify for Artists: прямая загрузка готового трека в дистрибуцию",
        ]),
        ("3–12 мес", "SEO + Content Marketing", C_GREEN, [
            "Ключевые запросы: «AI voice cloning music», «turn humming into song»",
            "Блог: туториалы «Как записать AI-трек», «Suno vs GAC vs Udio»",
            "Landing pages под каждый use case: подкастеры, геймдевы, блогеры",
            "Programmatic SEO: 1000+ страниц «create [genre] song from voice»",
        ]),
        ("6–12 мес", "B2B Direct Sales", C_AMBER, [
            "Outbound: LinkedIn + email к Digital/Ad агентствам (Digital Director)",
            "Pilot-first: 2 нед. бесплатного API (50 генераций) → конверсия в $1,200/мес",
            "Партнёрства: интеграция с CapCut, Adobe Premiere (плагин)",
            "Gamedev: инди-форумы, itch.io, GDC booth (year 2)",
        ]),
    ]

    for phase, name, color, items in channels:
        bullet_rows = [[bul(it)] for it in items]
        inner_content = Table(bullet_rows, colWidths=[(W-80)*0.70])
        inner_content.setStyle(TableStyle([
            ("TOPPADDING",   (0,0),(-1,-1), 1),
            ("BOTTOMPADDING",(0,0),(-1,-1), 1),
            ("LEFTPADDING",  (0,0),(-1,-1), 0),
            ("RIGHTPADDING", (0,0),(-1,-1), 0),
        ]))

        card_data = [
            [cell(name,  "Bold",11,color,  TA_LEFT),
             cell(phase, "Bold", 9,C_WHITE, TA_CENTER)],
            [inner_content, Spacer(1,1)],
        ]
        card = Table(card_data, colWidths=[(W-80)*0.72, (W-80)*0.28])
        card.setStyle(TableStyle([
            ("BACKGROUND",   (0,0),(-1,-1), C_CARD),
            ("BOX",          (0,0),(-1,-1), 1, color),
            ("BACKGROUND",   (1,0),(1,0),   colors.HexColor("#12002A")),
            ("TOPPADDING",   (0,0),(-1,-1), 9),
            ("BOTTOMPADDING",(0,0),(-1,-1), 9),
            ("LEFTPADDING",  (0,0),(-1,-1), 12),
            ("RIGHTPADDING", (0,0),(-1,-1), 12),
            ("VALIGN",       (0,0),(-1,-1), "TOP"),
            ("ALIGN",        (1,0),(1,0),   "CENTER"),
            ("SPAN",         (0,1),(1,1)),
        ]))
        out.append(card)
        out.append(vs(6))
    return out


def slide_sales():
    out = []
    out += section_hdr("07 · Стратегия продаж: Russia & USA",
                        "B2C подписки + B2B API — два рынка, одна платформа")

    def mk_col(items, border):
        rows = [[it] for it in items]
        t = Table(rows, colWidths=[(W-100)/2])
        t.setStyle(TableStyle([
            ("BACKGROUND",   (0,0),(-1,-1), C_CARD),
            ("BOX",          (0,0),(-1,-1), 1.5, border),
            ("TOPPADDING",   (0,0),(-1,-1), 8),
            ("BOTTOMPADDING",(0,0),(-1,-1), 4),
            ("LEFTPADDING",  (0,0),(-1,-1), 12),
            ("RIGHTPADDING", (0,0),(-1,-1), 12),
        ]))
        return t

    ru = mk_col([
        cell("🇷🇺  РОССИЯ · B2C", "Bold",13,C_CYAN, TA_LEFT),
        vs(4),
        cell("Рыночный контекст:", "Bold",9,C_MUTED,TA_LEFT),
        bul("~50M онлайн-пользователей в РФ"),
        bul("Suno/Udio недоступны без VPN — прямое окно"),
        bul("ВКонтакте: 73M MAU — нативная интеграция"),
        bul("Яндекс Музыка, СберЗвук: партнёрство для дистрибуции"),
        vs(4),
        cell("Тарифы:", "Bold",9,C_MUTED,TA_LEFT),
        bul("290 ₽/мес — Старт (30 треков)"),
        bul("790 ₽/мес — Про (150 треков + права)"),
        bul("2490 ₽/мес — Студия (∞ треков + API)"),
        vs(4),
        cell("Каналы:", "Bold",9,C_MUTED,TA_LEFT),
        bul("Telegram-бот для демо + @music_ai_ru канал"),
        bul("TikTok RU + VK Клипы — вирусный контент"),
        bul("Партнёрство с SkillFactory, Яндекс Практикум"),
    ], C_CYAN)

    us = mk_col([
        cell("🇺🇸  США · B2C + B2B", "Bold",13,C_GREEN, TA_LEFT),
        vs(4),
        cell("Рыночный контекст:", "Bold",9,C_MUTED,TA_LEFT),
        bul("38.9% мирового рынка AI in Music"),
        bul("$10–$30/мес — стандартная цена (Suno Pro $10)"),
        bul("B2B: 120K+ рекламных агентств, 2M+ indie devs"),
        bul("App Store / Google Play — основной канал"),
        vs(4),
        cell("B2C тарифы:", "Bold",9,C_MUTED,TA_LEFT),
        bul("$0/мес — Free (3 трека без кредитки)"),
        bul("$12/мес — Pro (50 треков + коммерч. права)"),
        bul("$29/мес — Studio (∞ + stem export + API)"),
        vs(4),
        cell("B2B API:", "Bold",9,C_MUTED,TA_LEFT),
        bul("$49/мес — 1,000 генераций"),
        bul("$499/мес — 15,000 генераций"),
        bul("Enterprise — Custom SLA + «clean IP» гарантия"),
    ], C_GREEN)

    two_col = Table([[ru, us]], colWidths=[(W-100)/2]*2)
    two_col.setStyle(TableStyle([
        ("VALIGN",        (0,0),(-1,-1), "TOP"),
        ("LEFTPADDING",   (0,0),(-1,-1), 5),
        ("RIGHTPADDING",  (0,0),(-1,-1), 5),
        ("TOPPADDING",    (0,0),(-1,-1), 0),
        ("BOTTOMPADDING", (0,0),(-1,-1), 0),
    ]))
    out.append(two_col)
    out.append(vs(10))
    out.append(p("Сравнительная таблица тарифов", s_subsection))

    widths = [105, 70, 68, 72, 84, 96]
    headers = ["Тариф", "Цена RU", "Цена US", "Треков/мес", "Комм. права", "API доступ"]
    rows = [
        [cell("Free",                 "Reg", 9,C_MUTED, TA_LEFT),
         cell("0 ₽",                 "Bold",9,C_MUTED, TA_CENTER),
         cell("$0",                  "Bold",9,C_MUTED, TA_CENTER),
         cell("3",                   "Reg", 9,C_TEXT,  TA_CENTER),
         cell("✗",                   "Bold",10,C_RED,  TA_CENTER),
         cell("✗",                   "Bold",10,C_RED,  TA_CENTER)],
        [cell("Старт / Starter",      "Reg", 9,C_TEXT,  TA_LEFT),
         cell("290 ₽",               "Bold",9,C_CYAN,  TA_CENTER),
         cell("$9",                  "Bold",9,C_CYAN,  TA_CENTER),
         cell("30",                  "Reg", 9,C_TEXT,  TA_CENTER),
         cell("✓",                   "Bold",10,C_GREEN,TA_CENTER),
         cell("✗",                   "Bold",10,C_RED,  TA_CENTER)],
        [cell("Про / Pro",            "Reg", 9,C_TEXT,  TA_LEFT),
         cell("790 ₽",               "Bold",9,C_CYAN,  TA_CENTER),
         cell("$19",                 "Bold",9,C_CYAN,  TA_CENTER),
         cell("150",                 "Reg", 9,C_TEXT,  TA_CENTER),
         cell("✓",                   "Bold",10,C_GREEN,TA_CENTER),
         cell("✗",                   "Bold",10,C_RED,  TA_CENTER)],
        [cell("Студия / Studio",      "Reg", 9,C_TEXT,  TA_LEFT),
         cell("2490 ₽",              "Bold",9,C_AMBER, TA_CENTER),
         cell("$29",                 "Bold",9,C_AMBER, TA_CENTER),
         cell("Без лимита",          "Reg", 9,C_TEXT,  TA_CENTER),
         cell("✓",                   "Bold",10,C_GREEN,TA_CENTER),
         cell("500 req/мес",         "Bold", 9,C_GREEN,TA_CENTER)],
        [cell("Enterprise API",       "Bold",9,C_ACCENT,TA_LEFT),
         cell("Индивид.",            "Reg", 9,C_MUTED, TA_CENTER),
         cell("от $499",             "Bold",9,C_ACCENT,TA_CENTER),
         cell("Без лимита",          "Reg", 9,C_TEXT,  TA_CENTER),
         cell("✓",                   "Bold",10,C_GREEN,TA_CENTER),
         cell("Custom SLA",          "Bold", 9,C_ACCENT,TA_CENTER)],
    ]
    out.append(header_tbl(headers, rows, widths))
    return out


def slide_faq():
    out = []
    out += section_hdr("08 · FAQ: 10 самых жёстких вопросов",
                        "Вопросы, которые задаст любой инвестор, партнёр или пресса")

    faqs = [
        ("Q1: Suno v5.5 уже делает voice cloning — чем вы лучше?",
         "Suno создаёт «vocal persona» — шаблон на основе тембра. Он не воспроизводит точную "
         "акустику: форманты, дыхание, вибрато. Наш DiffSinger клонирует биометрию через "
         "WavLM-ECAPA speaker embedding (256 dim). Тест: носитель языка слышит разницу в blind test. "
         "Плюс: мы не привязаны к платформе — голос применяется к любому треку через API."),
        ("Q2: Вас засудят как Suno и Udio — вы готовы?",
         "Suno и Udio обучались на стриминге без лицензий. Мы используем исключительно "
         "лицензированные датасеты: OpenSinger (CC BY-NC-SA), VocalSet (MIT), FMA (Creative Commons). "
         "MusicGen-large обучен на licensed-only данных. Это наш юридический USP для B2B — "
         "агентства не будут рисковать IP-претензиями. Консультация IP-адвоката в roadmap на месяц 2."),
        ("Q3: Почему пользователи переключатся с Suno ($10/мес) на вас?",
         "Наш target — не те, кто уже в Suno. Наш target — 180M человек, которые поют, "
         "но ни разу не пробовали AI-музыку, потому что «не умеют писать промпты». "
         "Мы не требуем промптов: просто напой — получи трек."),
        ("Q4: Вы можете сгенерировать трек за <5 минут на одном A100?",
         "Да: Enhancement 15 сек + ASR 10 сек + Speaker emb 3 сек + "
         "MusicGen 45–90 сек + DiffSinger DDIM 50 шагов 60–120 сек + Mix 5 сек = "
         "2.5–4 мин на A100 80GB. Трек на 4+ мин ~7 мин. ONNX-оптимизация в roadmap — ускорение ×2."),
        ("Q5: Это будет звучать как профессиональный трек?",
         "DiffSinger + HiFi-GAN достигают MOS ~4.1/5 (OpenSinger eval). "
         "Это уровень «хорошая демо-запись», не «студийный мастер». "
         "Для контент-мейкеров — достаточно. Честная позиция: "
         "мы конкурируем с GarageBand + SoundOn, не с Abbey Road Studios."),
        ("Q6: Нет данных пользователей — как работает speaker encoder?",
         "Нам не нужны данные пользователей для обучения. Speaker encoder работает zero-shot: "
         "обучен на VoxCeleb2 (6112 спикеров) и обобщается на любой голос без дообучения. "
         "WavLM-large + ECAPA-TDNN — state-of-the-art. SITW EER = 1.8%. "
         "Пользовательский голос обрабатывается инференсом, не тренировкой — GDPR-friendly."),
        ("Q7: Каков план выхода для инвесторов?",
         "Три сценария: (1) M&A — приобретение Spotify/Яндекс Музыкой для встроенной "
         "персонализации. Прецедент: Spotify купил Sonantic (TTS) за ~$100M. "
         "(2) Strategic investment — мейджор-лейбл как Warner инвестировал в Boomy. "
         "(3) IPO при ARR >$50M (горизонт 4–5 лет)."),
        ("Q8: Почему не Россия-только? Почему глобально?",
         "Россия — стартовый рынок: Suno/Udio заблокированы, конкуренция низкая, TAM $30–50M. "
         "Глобальный TAM — $5.2B. API-first архитектура позволяет обслуживать оба рынка "
         "с одним бэкендом. Русскоязычный рынок — плацдарм для отработки продукта до US-запуска."),
        ("Q9: Сколько стоит обучение моделей и откуда деньги?",
         "Speaker Encoder (4×A100, 5 дн., RunPod $1.49/h): ~$715. "
         "DiffSinger (8×A100, 14 дн.): ~$3,360. "
         "MusicGen LoRA (8×A100, 5 дн.): ~$1,200. "
         "Lyrics LLM QLoRA (4×A100, 3 дн.): ~$430. Итого: ~$5,700. "
         "Inference: $800/мес (2×A100 on-demand). Seed round цель: $500K на 12 мес runway."),
        ("Q10: Что мешает Google/Meta/Apple сделать то же самое завтра?",
         "Ничего технически — если захотят. Но: Google MusicLM ориентирован на B2B, "
         "не выпускает consumer продукт. Meta AudioCraft — open source, не продукт. "
         "Apple — не в этом бизнесе. Big Tech боится музыкальных лейблов — "
         "именно поэтому Suno, Udio и Beatoven существуют. Наше преимущество — "
         "скорость выхода + user voice experience + юридически чистый IP для B2B."),
    ]

    for q, a in faqs:
        out.append(p(q, s_faq_q))
        out.append(p(a, s_faq_a))
        out.append(hr(C_BORDER, 0.5))

    return out


def slide_closing():
    out = []
    out.append(vs(50))
    out.append(p("Что дальше?", S("ct","Bold",32,C_WHITE,TA_LEFT,38,0,6)))
    out.append(p("Дорожная карта от MVP до $3M ARR",
                 S("cs","Reg",14,C_CYAN,TA_LEFT,18,0,18)))
    out.append(hr())

    widths = [50, 340, 105]
    headers = ["Месяц", "Milestone", "Бюджет"]
    rows = [
        [cell("1–2",  "Bold",10,C_CYAN,  TA_CENTER),
         cell("Обучение моделей (DiffSinger, Speaker Encoder, MusicGen LoRA)","Reg",10,C_TEXT,TA_LEFT),
         cell("$6–8K GPU","Bold",9,C_GREEN,TA_CENTER)],
        [cell("2–3",  "Bold",10,C_CYAN,  TA_CENTER),
         cell("MVP API + Telegram-бот для демо","Reg",10,C_TEXT,TA_LEFT),
         cell("$0 (команда)","Bold",9,C_MUTED,TA_CENTER)],
        [cell("3",    "Bold",10,C_CYAN,  TA_CENTER),
         cell("ProductHunt запуск + 1,000 первых пользователей","Reg",10,C_TEXT,TA_LEFT),
         cell("$2K маркетинг","Bold",9,C_GREEN,TA_CENTER)],
        [cell("3–6",  "Bold",10,C_CYAN,  TA_CENTER),
         cell("VK Mini App + 5,000 платящих RU-пользователей","Reg",10,C_TEXT,TA_LEFT),
         cell("$5K retention","Bold",9,C_GREEN,TA_CENTER)],
        [cell("6",    "Bold",10,C_CYAN,  TA_CENTER),
         cell("US beta launch — Web app + ProductHunt EN","Reg",10,C_TEXT,TA_LEFT),
         cell("$10K PR","Bold",9,C_GREEN,TA_CENTER)],
        [cell("9",    "Bold",10,C_AMBER, TA_CENTER),
         cell("10,000 платящих глобально + 5 B2B-клиентов","Reg",10,C_TEXT,TA_LEFT),
         cell("—","Reg",9,C_MUTED,TA_CENTER)],
        [cell("12",   "Bold",10,C_GREEN, TA_CENTER),
         cell("Seed round close · ARR $3M · Series A prep","Bold",10,C_GREEN,TA_LEFT),
         cell("$500K raise","Bold",9,C_GREEN,TA_CENTER)],
    ]
    out.append(header_tbl(headers, rows, widths))
    out.append(vs(20))

    cta = tbl([[
        cell("💌 Контакт\nnadlervalentin2000@gmail.com",   "Bold",10,C_CYAN, TA_CENTER),
        cell("📊 Код проекта\ngithub.com/Firephase/Start", "Bold",10,C_GREEN,TA_CENTER),
        cell("🚀 Статус\nMVP ready · Models training\nSeed seeking","Bold",10,C_ACCENT,TA_CENTER),
    ]], [(W-80)/3]*3, [
        ("INNERGRID",    (0,0),(-1,-1), 0.5, C_BORDER),
        ("BOX",          (0,0),(-1,-1), 1.5, C_ACCENT),
        ("TOPPADDING",   (0,0),(-1,-1), 14),
        ("BOTTOMPADDING",(0,0),(-1,-1), 14),
    ])
    out.append(cta)
    out.append(vs(24))
    out.append(p(
        "Источники: Grand View Research · Market.us · MarketsandMarkets · Spherical Insights · "
        "TechCrunch · Billboard · Music Business Worldwide · Variety · Sacra · Crunchbase",
        s_footer))
    return out


# ════════════════════════════════════════════════════════════════════════════
def build():
    doc = SimpleDocTemplate(
        OUTPUT,
        pagesize=A4,
        leftMargin=28*mm,
        rightMargin=20*mm,
        topMargin=18*mm,
        bottomMargin=16*mm,
    )

    story = []
    story += slide_cover();       story.append(PageBreak())
    story += slide_competitors(); story.append(PageBreak())
    story += slide_audience();    story.append(PageBreak())
    story += slide_pain();        story.append(PageBreak())
    story += slide_market();      story.append(PageBreak())
    story += slide_risks();       story.append(PageBreak())
    story += slide_channels();    story.append(PageBreak())
    story += slide_sales();       story.append(PageBreak())
    story += slide_faq();         story.append(PageBreak())
    story += slide_closing()

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    print(f"PDF saved: {OUTPUT}")


if __name__ == "__main__":
    build()
