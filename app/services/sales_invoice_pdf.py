# =============================================================================
# app/services/sales_invoice_pdf.py
# -----------------------------------------------------------------------------
# Renders a SalesInvoice as the bilingual (English / Arabic) "Invoice" PDF that
# Kytos issues: company letterhead + footer image on every page, the header
# reference table, Seller / Buyer blocks, the line-items table, the totals with
# amounts in words, bank details and notes. Geometry (page size, margins,
# column widths, gray bands, 0.5pt black grid) was measured from a real issued
# invoice so the output matches it.
#
# ReportLab cannot shape or reorder Arabic by itself, so all text goes through
# ``BiText``: it wraps logically, then shapes (arabic-reshaper) and reorders
# (python-bidi) each *line*, and draws Arabic runs in Noto Sans Arabic and
# Latin runs in Lato. Fonts and the letterhead/footer images are bundled in
# app/assets.
# =============================================================================

from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from pathlib import Path

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import BaseDocTemplate, Flowable, Frame, Image, PageTemplate, Spacer, Table, TableStyle

from app.config import settings
from app.models.enums import SalesInvoiceStatus
from app.models.sales_invoice import SalesInvoice
from app.services.amount_words import amount_in_words
from app.services.zatca import build_zatca_qr_image

ASSETS = Path(__file__).resolve().parent.parent / "assets"

# ── Page geometry (points; measured from the reference invoice) ──────────────
PAGE_W, PAGE_H = 680.0, 842.0
MARGIN_X = 28.0
CONTENT_W = 624.0
FRAME_TOP = 113.2          # first content row, measured from the top edge
FRAME_BOTTOM = 740.0       # last usable y, measured from the top edge
LETTERHEAD = (28.02, 14.07, 624.0, 62.87)     # x, y-from-top, w, h
FOOTER_IMG = (28.02, 754.83, 624.0, 73.35)
PAGE_NO_BASELINE = 750.5   # from the top edge

GRAY = colors.Color(0.66273, 0.66273, 0.66273)
BLACK = colors.black
GRID = 0.52
PAD_X, PAD_Y = 1.2, 0.25
BASE_SIZE = 8.0
LEADING = 12.6            # measured: each extra text line adds 12.6pt, one-line rows are 13.1pt
ARABIC_SCALE = 1.08        # Noto Arabic runs a little small next to Lato at the same size

F_LATIN, F_LATIN_BOLD, F_ARABIC = "InvLato", "InvLatoBold", "InvNotoArabic"
_fonts_ready = False


def _register_fonts() -> None:
    global _fonts_ready
    if _fonts_ready:
        return
    pdfmetrics.registerFont(TTFont(F_LATIN, str(ASSETS / "fonts" / "Lato-Regular.ttf")))
    pdfmetrics.registerFont(TTFont(F_LATIN_BOLD, str(ASSETS / "fonts" / "Lato-Bold.ttf")))
    pdfmetrics.registerFont(TTFont(F_ARABIC, str(ASSETS / "fonts" / "NotoSansArabic-Regular.ttf")))
    _fonts_ready = True


# ── Bilingual text ────────────────────────────────────────────────────────────

def _is_arabic(ch: str) -> bool:
    o = ord(ch)
    return 0x0600 <= o <= 0x06FF or 0x0750 <= o <= 0x077F or 0xFB50 <= o <= 0xFDFF or 0xFE70 <= o <= 0xFEFF


def _has_arabic(text: str) -> bool:
    return any(_is_arabic(c) for c in text)


def _shape(line: str) -> str:
    """Logical line -> visual line (joined Arabic letters, RTL runs reordered)."""
    if not _has_arabic(line):
        return line
    return get_display(arabic_reshaper.reshape(line))


class BiText(Flowable):
    """Left/center/right-aligned text that may mix English and Arabic.

    Wraps on the logical text, then shapes/reorders each wrapped line, so a
    long Arabic sentence breaks in the right places and reads correctly.
    """

    def __init__(self, text, size=BASE_SIZE, align="center", color=BLACK, bold=False, leading=None):
        super().__init__()
        self.text = "" if text is None else str(text)
        self.size = size
        self.align = align
        self.color = color
        self.latin = F_LATIN_BOLD if bold else F_LATIN
        self.leading = leading or LEADING * size / BASE_SIZE
        self._lines: list[str] = []

    # font selection per character; neutrals (space, punctuation) inherit
    def _runs(self, visual: str) -> list[tuple[str, str, float]]:
        runs: list[tuple[str, str, float]] = []
        cur = None
        for ch in visual:
            if _is_arabic(ch):
                font = F_ARABIC
            elif ch.isalnum():
                font = self.latin
            else:
                font = cur or self.latin
            size = self.size * ARABIC_SCALE if font == F_ARABIC else self.size
            if runs and font == cur:
                runs[-1] = (runs[-1][0] + ch, font, size)
            else:
                runs.append((ch, font, size))
                cur = font
        return runs

    def _width(self, visual: str) -> float:
        return sum(pdfmetrics.stringWidth(t, f, s) for t, f, s in self._runs(visual))

    def _break(self, max_w: float) -> list[str]:
        lines: list[str] = []
        for para in self.text.split("\n"):
            cur = ""
            for word in para.split(" "):
                cand = word if not cur else f"{cur} {word}"
                if not cur or self._width(_shape(cand)) <= max_w:
                    cur = cand
                else:
                    lines.append(cur)
                    cur = word
            lines.append(cur)
        return lines

    def wrap(self, avail_w, avail_h):
        self._lines = self._break(avail_w)
        self.width = avail_w
        self.height = self.leading * len(self._lines)
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.setFillColor(self.color)
        for i, line in enumerate(self._lines):
            visual = _shape(line)
            w = self._width(visual)
            x = {"left": 0.0, "right": self.width - w}.get(self.align, (self.width - w) / 2)
            y = self.height - i * self.leading - self.leading / 2 - self.size * 0.33
            for text, font, size in self._runs(visual):
                c.setFont(font, size)
                c.drawString(x, y, text)
                x += pdfmetrics.stringWidth(text, font, size)


# ── Table helpers ─────────────────────────────────────────────────────────────

def _cell(text, align="center", **kw) -> BiText:
    return BiText(text, align=align, **kw)


def _grid_style(extra=None, valign="TOP") -> TableStyle:
    base = [
        ("GRID", (0, 0), (-1, -1), GRID, BLACK),
        ("VALIGN", (0, 0), (-1, -1), valign),
        ("LEFTPADDING", (0, 0), (-1, -1), PAD_X),
        ("RIGHTPADDING", (0, 0), (-1, -1), PAD_X),
        ("TOPPADDING", (0, 0), (-1, -1), PAD_Y),
        ("BOTTOMPADDING", (0, 0), (-1, -1), PAD_Y),
    ]
    return TableStyle(base + (extra or []))


def _band(cells: list[tuple[str, str]], widths: list[float], size=10.0) -> Table:
    """Gray strip with white text and no inner dividers: [(text, align), ...]."""
    t = Table([[_cell(txt, al, size=size, color=colors.white) for txt, al in cells]], colWidths=widths)
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), GRID, BLACK),
        ("BACKGROUND", (0, 0), (-1, -1), GRAY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), PAD_X), ("RIGHTPADDING", (0, 0), (-1, -1), PAD_X),
        ("TOPPADDING", (0, 0), (-1, -1), PAD_Y), ("BOTTOMPADDING", (0, 0), (-1, -1), PAD_Y),
    ]))
    return t


def _money(n) -> str:
    return f"{float(n or 0):,.2f}"


def _d(v) -> str:
    return v.isoformat() if v else ""


# Arabic renderings of the standard payment terms
_TERMS_AR = {
    "immediate payment": "تدفع على الفور",
    "due on receipt": "مستحق عند الاستلام",
    "net 15": "صافي 15 يوماً",
    "net 30": "صافي 30 يوماً",
    "net 45": "صافي 45 يوماً",
    "net 60": "صافي 60 يوماً",
}


def _terms_text(terms: str | None) -> str:
    if not terms:
        return ""
    ar = _TERMS_AR.get(terms.strip().lower())
    return f"{terms} {ar}" if ar else terms


# ── Sections ──────────────────────────────────────────────────────────────────

def _title_box() -> Table:
    t = Table([[_cell("فاتورة", size=14)], [_cell("Invoice", size=14)]], colWidths=[250.0], rowHeights=[24.1, 24.1])
    t.setStyle(_grid_style(valign="MIDDLE"))
    t.hAlign = "CENTER"
    return t


def _meta_table(inv: SalesInvoice) -> Table:
    number = inv.invoice_number or ("Draft" if inv.status == SalesInvoiceStatus.DRAFT else "")
    rows = [
        ("Invoice Number", number, "رقم الفاتورة"),
        ("Invoice Date", _d(inv.invoice_date), "تاريخ الفاتورة"),
        ("Delivery Note No", inv.delivery_note_no, "رقم إيصال التوصيل"),
        ("Delivery Date", _d(inv.delivery_date), "تاريخ التوصيل"),
        ("Term of Payment", _terms_text(inv.payment_terms), "طريقة الدفع"),
        ("Due Date", _d(inv.due_date), "تاريخ الاستحقاق"),
        ("Customer's PO Ref", inv.your_ref, "رقم أمر الشراء"),
        ("Vendor Number for Al Sinan", inv.vendor_number, "رقم المورد للشركة السنان"),
        ("Internal Reference Number For Al Sinan", inv.internal_reference, "الرقم الإشاري للشركة"),
        ("Invoice Currency", inv.currency, "عملة الفاتورة"),
        ("GR/SES", inv.gr_ses, "إشعار استلام البضائع/ورقة دخول الخدمة"),
    ]
    data = [
        [_cell(en, "left"), _cell(val, "center", size=11.0 if i == 0 else BASE_SIZE), _cell(ar, "right")]
        for i, (en, val, ar) in enumerate(rows)
    ]
    t = Table(data, colWidths=[125.2, 249.4, 124.2])
    t.setStyle(_grid_style())
    t.hAlign = "LEFT"
    return t


def _party_table(rows) -> Table:
    """One side (Seller or Buyer): label | value | Arabic-label rows."""
    data = [[_cell(en, "left"), _cell(val, "center"), _cell(ar, "right")] for en, val, ar in rows]
    t = Table(data, colWidths=[62.9, 187.0, 61.9])
    t.setStyle(_grid_style())
    return t


_ADDR_LABELS = [
    ("Name", "الاسم"), ("Building No.", "رقم المبنى"), ("Street Name", "اسم الشارع"),
    ("District", "الحي"), ("City", "المدينة"), ("Country", "البلد"),
    ("Postal Code", "الرمز البريدي"), ("Vat Number", "رقم تسجيل ضريبة القيمة المضافة"),
    ("CR No.", "السجل التجاري"),
]


def _parties(inv: SalesInvoice) -> Table:
    s = settings
    seller_vals = [s.SELLER_NAME, s.SELLER_BUILDING, s.SELLER_STREET, s.SELLER_DISTRICT, s.SELLER_CITY,
                   s.SELLER_COUNTRY, s.SELLER_POSTAL_CODE, s.SELLER_VAT_NUMBER, s.SELLER_CR_NO]
    buyer_vals = [inv.customer_name, inv.customer_building_no, inv.customer_street, inv.customer_district,
                  inv.customer_city, inv.customer_country, inv.customer_postal_code, inv.customer_tax_id,
                  inv.customer_cr_no]
    seller = _party_table([(en, v, ar) for (en, ar), v in zip(_ADDR_LABELS, seller_vals)])
    buyer = _party_table([(en, v, ar) for (en, ar), v in zip(_ADDR_LABELS, buyer_vals)])
    outer = Table([[seller, buyer]], colWidths=[311.8, 312.2])
    outer.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return outer


_ITEM_COLS = [40.9, 35.1, 190.2, 42.4, 42.5, 55.5, 42.5, 41.9, 42.4, 90.1]


def _items_table(inv: SalesInvoice) -> Table:
    heads = [
        "Serial\nNumber\nالرقم\nالتسلسلي", "Material\nNumber\nرقم\nالمواد", "Item Description\nوصف الصنف",
        "Unit Price\nسعر\nالوحدة", "Quantity\nالكمية", "Unit of\nMeasurement\n(UOM)\nوحدة القياس",
        "Taxable\nAmount\nالمبلغ\nالخاضع\nللضريبة", "Tax Rate\nنسبة\nالضريبة", "Tax\nAmount\nمبلغ\nالضريبة",
        "Item Subtotal(Including\nVat)\nالمجموع(شامل ضريبة)\nالقيمة المضافة",
    ]
    data = [[_cell(h, color=colors.white) for h in heads]]
    rate = f"{float(inv.vat_rate):g}"
    for it in inv.items:
        tax = round(float(it.total) * float(inv.vat_rate) / 100, 2)
        name = it.item_name + (f"\n{it.description}" if it.description else "")
        data.append([
            _cell(str(it.line_no)), _cell(it.catalog_no or ""), _cell(name),
            _cell(_money(it.unit_price)), _cell(_money(it.qty)), _cell(it.unit),
            _cell(_money(it.total)), _cell(f"VAT {rate}%\nضريبة القيمة المضافة"),
            _cell(_money(tax)), _cell(_money(float(it.total) + tax)),
        ])
    t = Table(data, colWidths=_ITEM_COLS, repeatRows=1)
    t.setStyle(_grid_style([("BACKGROUND", (0, 0), (-1, 0), GRAY)]))
    return t


_TOTAL_COLS = [188.0, 155.8, 155.8, 124.4]


def _totals_table(inv: SalesInvoice) -> Table:
    cur = inv.currency
    rate = f"{float(inv.vat_rate):g}"
    foreign = cur != "SAR"

    def amt(n, c=cur):
        return f"{_money(n)} {c}"

    def words_cell(n, c):
        en, ar = amount_in_words(n, c)
        return [BiText(en, align="left"), BiText(ar, align="left")]

    rows = [
        ("", "Total (Excluding Vat)", "الإجمالي (غير شامل ضريبة القيمة المضافة)", amt(inv.subtotal)),
        ("", "Discount", "مجموع الخصومات", amt(inv.discount)),
        ("", "Total Taxable Amount (Excluding Vat)", "الإجمالي الخاضع للضريبة (غير شامل ضريبة القيمة المضافة)",
         amt(inv.taxable_amount)),
        (words_cell(inv.vat, cur), f"Total Vat {rate}%", f"مجموع ضريبة القيمة المضافة {rate}%", amt(inv.vat)),
    ]
    if foreign:
        rows.append((words_cell(inv.vat_sar, "SAR"), f"Total Vat {rate}% in SAR",
                     f"مجموع ضريبة القيمة المضافة بالريال السعودي {rate}%", amt(inv.vat_sar, "SAR")))
    rows.append((words_cell(inv.total, cur), "Total Amount Due", "إجمالي المبلغ المستحق", amt(inv.total)))
    if foreign:
        rows.append((words_cell(inv.total_sar, "SAR"), "Total Amount Due in SAR",
                     "إجمالي المبلغ المستحق بالريال السعودي", amt(inv.total_sar, "SAR")))

    data = []
    for first, en, ar, value in rows:
        data.append([first if first else "", _cell(en, "left"), _cell(ar, "right"), _cell(value, "right")])
    t = Table(data, colWidths=_TOTAL_COLS)
    t.setStyle(_grid_style())
    return t


def _bank_table(inv: SalesInvoice) -> Table | None:
    acct = next((a for a in settings.COMPANY_BANK_ACCOUNTS if a.get("currency") == inv.currency), None)
    if acct is None:
        return None
    data = [[_cell("Bank Details تفاصيل البنك", "center"), ""]]
    for label, key in (("Name", "account_name"), ("A/C No", "account_no"), ("SWIFT CODE", "swift"),
                       ("BANK", "bank"), ("BRANCH", "branch"), ("IBAN No", "iban")):
        data.append([_cell(label, "left"), _cell(acct.get(key, ""), "left")])
    t = Table(data, colWidths=[187.1, 436.9])
    t.setStyle(_grid_style([("SPAN", (0, 0), (1, 0)), ("LEFTPADDING", (0, 1), (-1, -1), 5.5)]))
    return t


def _notes_table(inv: SalesInvoice) -> Table:
    t = Table([[_cell("ملاحظات", "center")], [_cell(inv.remarks or "", "center")]], colWidths=[CONTENT_W],
              rowHeights=[None, 21.5])
    t.setStyle(_grid_style())
    return t


def _empty_box() -> Table:
    """Blank light-gray field under the notes (present on the original invoice)."""
    t = Table([["", ""]], colWidths=[15.9, 592.5], rowHeights=[24.3])
    t.setStyle(TableStyle([("BOX", (1, 0), (1, 0), GRID, colors.Color(0.85, 0.85, 0.85))]))
    t.hAlign = "LEFT"
    return t


def _zatca_qr_block(inv: SalesInvoice):
    """ZATCA Phase 1 simplified-tax-invoice QR code (posted invoices only —
    a draft has no invoice number/timestamp yet, so it isn't a real tax
    invoice). Amounts go in SAR, since that's what ZATCA's fields expect."""
    if inv.status == SalesInvoiceStatus.DRAFT or not inv.invoice_number:
        return None
    ts = inv.posted_at or datetime.combine(inv.invoice_date or date.today(), datetime.min.time())
    png = build_zatca_qr_image(
        seller_name=settings.SELLER_NAME, vat_number=settings.SELLER_VAT_NUMBER,
        timestamp=ts, invoice_total=float(inv.total_sar), vat_total=float(inv.vat_sar),
    )
    qr = Image(png, width=60, height=60)
    caption = BiText("ZATCA QR — Simplified Tax Invoice\nرمز الاستجابة السريعة — فاتورة ضريبية مبسطة", size=6.5, align="left")
    t = Table([[qr, caption]], colWidths=[70.0, CONTENT_W - 70.0], rowHeights=[62.0])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (0, 0), 4)]))
    return t


# ── Page furniture (letterhead, footer, "Page X of Y") ────────────────────────

class _InvoiceCanvas(rl_canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._states: list[dict] = []

    def showPage(self):
        self._states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._states)
        for state in self._states:
            self.__dict__.update(state)
            self._decorate(self._pageNumber, total)
            super().showPage()
        super().save()

    def _decorate(self, page: int, total: int) -> None:
        x, y, w, h = LETTERHEAD
        self.drawImage(str(ASSETS / "invoice" / "letterhead.jpg"), x, PAGE_H - y - h, w, h)
        x, y, w, h = FOOTER_IMG
        self.drawImage(str(ASSETS / "invoice" / "footer.jpg"), x, PAGE_H - y - h, w, h)
        self.setFillColor(BLACK)
        self.setFont(F_LATIN_BOLD, 7.5)
        self.drawCentredString(PAGE_W / 2, PAGE_H - PAGE_NO_BASELINE, f"Page {page} of {total}")


# ── Entry point ───────────────────────────────────────────────────────────────

def build_invoice_pdf(inv: SalesInvoice) -> BytesIO:
    _register_fonts()

    story = [
        _title_box(), Spacer(1, 3.2),
        _meta_table(inv), Spacer(1, 3.2),
        _band([("Seller", "left"), ("البائع", "right"), ("Buyer\\ Bill to", "left"), ("المشتري / فاتورة إلى", "right")],
              [155.9, 156.1, 155.6, 156.4]),
        _parties(inv), Spacer(1, 0.5),
        _band([("Line items", "center")], [CONTENT_W]),
        _items_table(inv),
        Spacer(1, 0.5),
        _band([("Total Amounts", "left"), ("إجمالي المبلغ", "right")], [311.8, 312.2]),
        _totals_table(inv),
    ]
    bank = _bank_table(inv)
    if bank is not None:
        story += [Spacer(1, 0.6), bank]
    qr_block = _zatca_qr_block(inv)
    story += [Spacer(1, 13.1), _notes_table(inv), Spacer(1, 10.0),
              qr_block if qr_block is not None else Spacer(1, 19.4)]
    if qr_block is None:
        story += [Spacer(1, 10.0), _empty_box()]

    buf = BytesIO()
    doc = BaseDocTemplate(
        buf, pagesize=(PAGE_W, PAGE_H),
        title=f"Invoice {inv.invoice_number or 'Draft'}", author=settings.COMPANY_NAME,
    )
    frame = Frame(
        MARGIN_X, PAGE_H - FRAME_BOTTOM, CONTENT_W, FRAME_BOTTOM - FRAME_TOP,
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id="body",
    )
    doc.addPageTemplates([PageTemplate(id="invoice", frames=[frame])])
    doc.build(story, canvasmaker=_InvoiceCanvas)
    buf.seek(0)
    return buf
