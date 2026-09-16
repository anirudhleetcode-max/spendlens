"""Synthetic Indian thermal-receipt photos with ground truth.

    python -m ml.receipts_synth --out ../samples --n 3

Layout: 42-column monospace thermal print (merchant header, GSTIN, bill no, date in a random Indian
format, item table, subtotal, CGST/SGST, a total line with a random label, payment mode), then made to
look photographed: paper placed on a darker surface, rotated a few degrees, blurred, sensor noise, JPEG.
"""
from __future__ import annotations

import argparse
import io
import json
import random
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_DIR = Path(__file__).resolve().parent / "fonts"
COLS = 42
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


@dataclass
class Truth:
    merchant: str
    date: str               # ISO yyyy-mm-dd
    total: float
    tax: float
    payment_mode: str
    category: str
    items: list[dict] = field(default_factory=list)
    date_text: str = ""
    total_label: str = ""


# header text on paper, canonical merchant (what the parser should return), kind, category
SHOPS = [
    ("DMART", "DMart", "grocery", "Groceries", "AVENUE SUPERMARTS LTD"),
    ("RELIANCE FRESH", "Reliance Fresh", "grocery", "Groceries", "RELIANCE RETAIL LIMITED"),
    ("BIGBASKET", "BigBasket", "grocery", "Groceries", "SUPERMARKET GROCERY SUPPLIES PVT LTD"),
    ("MORE SUPERMARKET", "More Supermarket", "grocery", "Groceries", "MORE RETAIL PVT LTD"),
    ("APOLLO PHARMACY", "Apollo Pharmacy", "pharmacy", "Health", "APOLLO HEALTHCO LIMITED"),
    ("MEDPLUS", "MedPlus", "pharmacy", "Health", "OPTIVAL HEALTH SOLUTIONS PVT LTD"),
    ("HALDIRAM'S", "Haldiram's", "restaurant", "Food & Dining", "HALDIRAM FOODS INTL"),
    ("SARAVANA BHAVAN", "Saravana Bhavan", "restaurant", "Food & Dining", "HOTEL SARAVANA BHAVAN"),
    ("CAFE MADRAS", "Cafe Madras", "restaurant", "Food & Dining", "CAFE MADRAS KING CIRCLE"),
    ("INDIAN OIL", "Indian Oil", "fuel", "Transport & Fuel", "COCO FUEL STATION"),
    ("HP PETROL PUMP", "HP Petrol Pump", "fuel", "Transport & Fuel", "SRI LAKSHMI FILLING STATION"),
    ("CROMA", "Croma", "retail", "Shopping", "INFINITI RETAIL LIMITED"),
]

ITEMS = {
    "grocery": [("TOOR DAL 1KG", 142), ("AASHIRVAAD ATTA 5KG", 265), ("AMUL BUTTER 500G", 275),
                ("TATA SALT 1KG", 28), ("FORTUNE OIL 1L", 155), ("MAGGI NOODLES 280G", 56),
                ("PARLE G 800G", 90), ("SURF EXCEL 1KG", 138), ("ONION", 38), ("TOMATO", 32),
                ("AMUL TAAZA 1L", 68), ("BASMATI RICE 1KG", 119), ("SUGAR 1KG", 46), ("BRU COFFEE", 185),
                ("COLGATE 200G", 112), ("GOOD DAY BISCUIT", 30), ("PANEER 200G", 92), ("EGGS 6PC", 48)],
    "pharmacy": [("DOLO 650 TAB", 32), ("CROCIN ADV", 28), ("VITAMIN D3 60K", 124), ("BECOSULES CAP", 51),
                 ("AZITHRAL 500", 119), ("CETIRIZINE 10MG", 18), ("PAN 40 TAB", 162), ("ORS SACHET", 21),
                 ("BENADRYL SYRUP", 118), ("BAND AID 10S", 40), ("SAVLON 100ML", 64)],
    "restaurant": [("MASALA DOSA", 110), ("IDLI VADA", 85), ("FILTER COFFEE", 45), ("VEG THALI", 220),
                   ("PANEER BUTTER MASALA", 260), ("BUTTER NAAN", 55), ("CHOLE BHATURE", 170),
                   ("RAS MALAI", 90), ("MANGO LASSI", 95), ("PAV BHAJI", 150), ("JEERA RICE", 140),
                   ("DAL MAKHANI", 230), ("MASALA CHAI", 30), ("GULAB JAMUN", 70)],
    "retail": [("USB C CABLE 1M", 499), ("BOAT EARPHONES", 1299), ("MOUSE WIRELESS", 799),
               ("HDMI CABLE", 649), ("AA BATTERY 4PC", 180), ("PHONE COVER", 399), ("POWER BANK 10K", 1499)],
}


def _money(v: float) -> str:
    return f"{v:,.2f}"


def _date_text(d: date, rng: random.Random) -> str:
    fmts = [
        lambda: d.strftime("%d/%m/%Y"),
        lambda: d.strftime("%d-%m-%Y"),
        lambda: d.strftime("%d.%m.%y"),
        lambda: d.strftime("%Y-%m-%d"),
        lambda: f"{d.day:02d}-{MONTHS[d.month - 1]}-{d.year}",
        lambda: f"{d.day:02d} {MONTHS[d.month - 1]} {d.year}",
        lambda: f"{d.day:02d}/{d.month:02d}/{d.year % 100:02d}",
    ]
    return rng.choice(fmts)()


def _lr(left: str, right: str) -> str:
    return left + " " * max(1, COLS - len(left) - len(right)) + right


BASE_DATE = min(date(2026, 9, 16), date.today())  # fixed for reproducible metrics, never in the future


def make_receipt(rng: random.Random, shop=None, on: date | None = None) -> tuple[list[tuple[str, str]], Truth]:
    """Returns print lines as (style, text) with style in {'big','bold','n','c'} plus ground truth."""
    header, canonical, kind, category, legal = shop or rng.choice(SHOPS)
    offset = rng.randint(0, 120)
    d = on or (BASE_DATE - timedelta(days=offset))
    dtxt = _date_text(d, rng)
    lines: list[tuple[str, str]] = [("big", header), ("c", legal),
                                    ("c", rng.choice(["MG ROAD, BENGALURU 560001", "ANDHERI W, MUMBAI 400053",
                                                      "T NAGAR, CHENNAI 600017", "SECTOR 18, NOIDA 201301",
                                                      "BANJARA HILLS, HYDERABAD 500034"])),
                                    ("c", f"GSTIN: {rng.randint(10, 36)}AAB{'CDEFG'[rng.randint(0, 4)]}"
                                          f"{rng.randint(1000, 9999)}K1Z{rng.randint(1, 9)}"),
                                    ("c", f"Ph: 0{rng.randint(20, 99)}-{rng.randint(20000000, 99999999)}")]
    lines.append(("c", "TAX INVOICE" if kind != "restaurant" else "BILL"))
    lines.append(("n", "-" * COLS))
    date_label = rng.choice(["Date:", "Dt:", "Bill Dt:", "Date :"])
    lines.append(("n", _lr(f"Bill No: {rng.randint(1000, 99999)}", f"{date_label} {dtxt}")))
    lines.append(("n", _lr(f"Time: {rng.randint(8, 22):02d}:{rng.randint(0, 59):02d}",
                           f"Cashier: {rng.choice(['RAVI', 'ANITA', 'SURESH', 'POOJA'])}")))
    if kind == "restaurant":
        lines.append(("n", f"Table: {rng.randint(1, 24)}   Covers: {rng.randint(1, 5)}"))
    lines.append(("n", "-" * COLS))

    items: list[dict] = []
    if kind == "fuel":
        product = rng.choice(["PETROL", "DIESEL", "SPEED PETROL"])
        rate = round(rng.uniform(88, 106), 2)
        amount = float(rng.choice([200, 300, 500, 750, 1000, 1500, 2000]))
        vol = round(amount / rate, 2)
        lines += [("n", _lr("Product:", product)), ("n", _lr("Rate/Ltr:", f"{rate:.2f}")),
                  ("n", _lr("Volume(L):", f"{vol:.2f}")), ("n", _lr("Nozzle No:", str(rng.randint(1, 8)))),
                  ("n", _lr("Vehicle No:", f"KA{rng.randint(1, 60):02d}AB{rng.randint(1000, 9999)}")),
                  ("n", "-" * COLS)]
        items.append({"name": product, "qty": vol, "price": amount})
        subtotal, tax = amount, 0.0
        total = amount
        total_label = rng.choice(["AMOUNT", "SALE AMOUNT", "TOTAL"])
        lines.append(("bold", _lr(f"{total_label}: Rs.", _money(total))))
    else:
        lines.append(("n", _lr("Item            Qty    Rate", "Amount")))
        lines.append(("n", "-" * COLS))
        pool = ITEMS[kind]
        for name, price in rng.sample(pool, k=min(len(pool), rng.randint(2, 6))):
            qty = rng.choice([1, 1, 1, 2, 2, 3])
            price = float(price)
            amt = qty * price
            items.append({"name": name, "qty": qty, "price": amt})
            left = f"{name[:16]:<16}{qty:>3}{price:>9.2f}"
            lines.append(("n", _lr(left, f"{amt:.2f}")))
        lines.append(("n", "-" * COLS))
        subtotal = sum(i["price"] for i in items)
        rate = 2.5 if kind in ("restaurant", "grocery") else (6.0 if kind == "pharmacy" else 9.0)
        half = round(subtotal * rate / 100, 2)
        tax = round(2 * half, 2)
        raw_total = subtotal + tax
        total = float(round(raw_total))
        n_qty = sum(int(i["qty"]) for i in items)
        lines.append(("n", _lr(f"Total Qty: {n_qty}", f"Items: {len(items)}")))
        lines.append(("n", _lr("Sub Total", _money(subtotal))))
        lines.append(("n", _lr(f"CGST @{rate}%", _money(half))))
        lines.append(("n", _lr(f"SGST @{rate}%", _money(half))))
        ro = round(total - raw_total, 2)
        if abs(ro) >= 0.01:
            lines.append(("n", _lr("Round Off", f"{ro:+.2f}")))
        lines.append(("n", "-" * COLS))
        total_label = rng.choice(["GRAND TOTAL", "NET AMOUNT", "TOTAL", "NET PAYABLE", "BILL AMOUNT"])
        lines.append(("bold", _lr(total_label, "Rs." + _money(total))))
        if kind == "grocery" and rng.random() < 0.6:
            lines.append(("n", _lr("You Saved", "Rs." + _money(round(subtotal * 0.07, 2)))))
    lines.append(("n", "-" * COLS))
    pm = rng.choice(["UPI", "Card", "Cash"])
    pm_text = {"UPI": rng.choice(["PAID VIA UPI", "UPI - GPAY", "PHONEPE UPI"]),
               "Card": rng.choice(["CARD: VISA XXXX4821", "PAID BY CARD", "RUPAY DEBIT CARD"]),
               "Cash": rng.choice(["CASH", "PAID CASH"])}[pm]
    lines.append(("n", _lr("Payment Mode:", pm_text)))
    lines += [("n", ""), ("c", "THANK YOU! VISIT AGAIN")]
    truth = Truth(merchant=canonical, date=d.isoformat(), total=total, tax=tax, payment_mode=pm,
                  category=category, items=items, date_text=dtxt, total_label=total_label)
    return lines, truth


def render(lines: list[tuple[str, str]], rng: random.Random, clean: bool = False) -> Image.Image:
    fs = 26
    font = ImageFont.truetype(str(FONT_DIR / "DejaVuSansMono.ttf"), fs)
    bold = ImageFont.truetype(str(FONT_DIR / "DejaVuSansMono-Bold.ttf"), fs)
    big = ImageFont.truetype(str(FONT_DIR / "DejaVuSansMono-Bold.ttf"), int(fs * 1.5))
    cw = font.getbbox("M")[2]
    pad = 36
    width = cw * COLS + 2 * pad
    lh = int(fs * 1.35)
    height = pad * 2 + sum(int(lh * 1.5) if s == "big" else lh for s, _ in lines)
    paper = Image.new("L", (width, height), 250)
    dr = ImageDraw.Draw(paper)
    y = pad
    ink = 30 if clean else rng.randint(20, 70)
    for style, text in lines:
        f = big if style == "big" else bold if style == "bold" else font
        if style in ("big", "c"):
            tw = dr.textlength(text, font=f)
            x = (width - tw) / 2
        else:
            x = pad
        dr.text((x, y), text, fill=ink, font=f)
        y += int(lh * 1.5) if style == "big" else lh
    if clean:
        return paper.convert("RGB")

    # thermal print fading: uneven brightness across the paper
    arr = np.asarray(paper).astype(np.float32)
    grad = np.linspace(rng.uniform(-18, 0), rng.uniform(0, 18), arr.shape[0])[:, None]
    arr = np.clip(arr + (arr < 200) * grad, 0, 255)
    paper = Image.fromarray(arr.astype(np.uint8))

    # place on a darker table surface, then "photograph" it
    margin = int(width * 0.12)
    bg_val = rng.randint(60, 120)
    canvas = Image.new("L", (width + 2 * margin, height + 2 * margin), bg_val)
    canvas.paste(paper, (margin, margin))
    angle = rng.uniform(-4.0, 4.0)
    canvas = canvas.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=bg_val)
    canvas = canvas.filter(ImageFilter.GaussianBlur(rng.uniform(0.4, 1.1)))
    arr = np.asarray(canvas).astype(np.float32)
    arr += np.random.default_rng(rng.randint(0, 10**6)).normal(0, rng.uniform(4, 10), arr.shape)
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    rgb = Image.fromarray(arr).convert("RGB")
    # slight warm tint like indoor light
    r, g, b = rgb.split()
    b = b.point(lambda v: int(v * 0.93))
    return Image.merge("RGB", (r, g, b))


def generate(n: int, seed: int = 42, on: date | None = None) -> list[tuple[bytes, Truth]]:
    rng = random.Random(seed)
    out = []
    for i in range(n):
        shop = SHOPS[i % len(SHOPS)]
        lines, truth = make_receipt(rng, shop, on)
        img = render(lines, rng)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=rng.randint(78, 90))
        out.append((buf.getvalue(), truth))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="../samples")
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--seed", type=int, default=2026)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    picks = [SHOPS[0], SHOPS[4], SHOPS[7], SHOPS[9]][: a.n]
    rng = random.Random(a.seed)
    for shop in picks:
        lines, truth = make_receipt(rng, shop)
        name = f"receipt_{truth.merchant.lower().replace(' ', '_').replace(chr(39), '')}.jpg"
        render(lines, rng).save(out / name, "JPEG", quality=88)
        (out / name.replace(".jpg", ".json")).write_text(json.dumps(asdict(truth), indent=2))
        print("wrote", out / name, truth.total, truth.date)


if __name__ == "__main__":
    main()
