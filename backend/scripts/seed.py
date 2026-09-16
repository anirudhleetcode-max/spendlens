"""Create / reset the demo account with ~75 days of realistic spending.

    python -m scripts.seed
Login: demo@spendlens.app / demo1234
"""
from __future__ import annotations

import io
import random
from datetime import date, datetime, timedelta, timezone

import gridfs
import pymongo

from app.config import get_settings
from app.security import hash_password
from app.services.images import shrink_jpeg
from app.utils import merchant_key
from ml.receipts_synth import SHOPS, make_receipt, render

EMAIL = "demo@spendlens.app"
PASSWORD = "demo1234"

# (merchant, category, amount range, payment modes, typical items, weekly frequency)
PATTERNS = [
    ("DMart", "Groceries", (650, 2400), ["UPI", "Card"], ["Toor Dal 1Kg", "Aashirvaad Atta 5Kg", "Amul Butter"], 1.0),
    ("BigBasket", "Groceries", (400, 1600), ["UPI"], ["Onion", "Tomato", "Amul Taaza 1L", "Eggs 6Pc"], 0.9),
    ("Reliance Fresh", "Groceries", (150, 700), ["UPI", "Cash"], ["Banana", "Curd", "Bread"], 0.6),
    ("Swiggy", "Food & Dining", (180, 650), ["UPI"], ["Chicken Biryani", "Delivery Charge"], 2.0),
    ("Zomato", "Food & Dining", (200, 700), ["UPI", "Card"], ["Paneer Butter Masala", "Butter Naan"], 1.4),
    ("Chaayos", "Food & Dining", (120, 320), ["UPI"], ["Masala Chai", "Vada Pav"], 0.8),
    ("Saravana Bhavan", "Food & Dining", (260, 900), ["Card", "Cash"], ["Masala Dosa", "Filter Coffee"], 0.4),
    ("Indian Oil", "Transport & Fuel", (500, 1500), ["Card", "UPI"], ["Petrol"], 0.8),
    ("Uber", "Transport & Fuel", (140, 480), ["UPI"], ["Trip Fare"], 1.2),
    ("Namma Metro", "Transport & Fuel", (200, 500), ["UPI"], ["Smart Card Top Up"], 0.3),
    ("Apollo Pharmacy", "Health", (120, 650), ["UPI", "Card"], ["Dolo 650 Tab", "Vitamin D3"], 0.4),
    ("Amazon", "Shopping", (300, 2200), ["Card"], ["Usb C Cable", "Phone Cover"], 0.5),
    ("Myntra", "Shopping", (700, 2400), ["Card", "UPI"], ["T Shirt", "Jeans"], 0.2),
    ("PVR INOX", "Entertainment", (450, 1100), ["Card"], ["Movie Ticket", "Popcorn Combo"], 0.3),
    ("Coursera", "Education", (2400, 2400), ["Card"], ["Online Course"], 0.06),
    ("Sapna Book House", "Education", (250, 900), ["UPI"], ["Reference Book", "Long Notebook"], 0.15),
]
MONTHLY = [  # (merchant, category, amount, day-of-month, mode)
    ("BESCOM", "Bills & Utilities", 1860, 5, "UPI"),
    ("Airtel", "Bills & Utilities", 599, 9, "UPI"),
    ("ACT Fibernet", "Bills & Utilities", 1049, 12, "Card"),
    ("Netflix", "Entertainment", 499, 3, "Card"),
    ("Indane Gas", "Bills & Utilities", 905, 18, "UPI"),
]
BUDGETS = {"Groceries": 9000, "Food & Dining": 7000, "Transport & Fuel": 4500, "Shopping": 4000,
           "Bills & Utilities": 5000, "Entertainment": 2000, "Health": 2500}


def main() -> None:
    s = get_settings()
    db = pymongo.MongoClient(s.mongo_uri, tz_aware=True)[s.mongo_db]
    fs = gridfs.GridFSBucket(db, bucket_name="receipts")
    rng = random.Random(11)
    now = datetime.now(timezone.utc)

    user = db.users.find_one({"email": EMAIL})
    if user:
        uid = user["_id"]
        for f in db["receipts.files"].find({"metadata.user_id": uid}, {"_id": 1}):
            fs.delete(f["_id"])
        for coll in ("expenses", "budgets", "merchant_overrides", "category_feedback"):
            db[coll].delete_many({"user_id": uid})
    else:
        uid = db.users.insert_one({"name": "Aditi Rao", "email": EMAIL, "password_hash": hash_password(PASSWORD),
                                   "created_at": now}).inserted_id

    today = now.date()
    start = (today.replace(day=1) - timedelta(days=1)).replace(day=1) - timedelta(days=20)
    docs = []

    def add(d: date, merchant, cat, amount, mode, items, source="manual", receipt_id=None, notes=""):
        dt = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        docs.append({"user_id": uid, "merchant": merchant, "merchant_key": merchant_key(merchant),
                     "amount": round(float(amount), 2), "tax": round(float(amount) * 0.05, 2) if cat in
                     ("Groceries", "Food & Dining") else 0.0, "date": dt, "category": cat,
                     "suggested_category": cat, "payment_mode": mode,
                     "items": [{"name": n, "qty": 1, "price": 0} for n in items], "notes": notes,
                     "receipt_id": receipt_id, "source": source,
                     "created_at": dt + timedelta(hours=rng.randint(9, 21)), "updated_at": now})

    d = start
    while d <= today:
        for merchant, cat, (lo, hi), modes, items, per_week in PATTERNS:
            if rng.random() < per_week / 7:
                amt = rng.uniform(lo, hi)
                amt = round(amt) if rng.random() < 0.6 else round(amt, 2)
                add(d, merchant, cat, amt, rng.choice(modes), rng.sample(items, k=min(2, len(items))))
        for merchant, cat, amt, dom, mode in MONTHLY:
            if d.day == dom:
                add(d, merchant, cat, amt + rng.randint(-40, 60) * (cat == "Bills & Utilities"), mode, [])
        d += timedelta(days=1)

    # a few genuinely unusual ones for the anomaly panel
    add(today - timedelta(days=4), "Barbeque Nation", "Food & Dining", 3480, "Card",
        ["Veg Buffet", "Non Veg Buffet"], notes="Team dinner")
    add(today - timedelta(days=9), "Apollo Pharmacy", "Health", 2890, "Card", ["Thyroid Profile", "Lipid Profile"])
    add(today - timedelta(days=36), "Croma", "Shopping", 8999, "Card", ["Boat Earphones", "Power Bank 10K"])

    # two scanned receipts with real images
    for shop_idx, days_ago in [(0, 2), (4, 6)]:
        lines, truth = make_receipt(rng, SHOPS[shop_idx])
        buf = io.BytesIO()
        render(lines, rng).save(buf, "JPEG", quality=88)
        rid = fs.upload_from_stream("receipt.jpg", shrink_jpeg(buf.getvalue()),
                                    metadata={"user_id": uid, "content_type": "image/jpeg", "uploaded_at": now})
        dd = today - timedelta(days=days_ago)
        add(dd, truth.merchant, truth.category, truth.total, truth.payment_mode,
            [i["name"].title() for i in truth.items], source="scan", receipt_id=rid)
        docs[-1]["items"] = [{"name": i["name"].title(), "qty": float(i["qty"]), "price": i["price"]} for i in truth.items]
        docs[-1]["tax"] = truth.tax

    db.expenses.insert_many(docs)
    for cat, amt in BUDGETS.items():
        db.budgets.update_one({"user_id": uid, "category": cat}, {"$set": {"amount": float(amt), "updated_at": now}},
                              upsert=True)
    db.merchant_overrides.update_one({"user_id": uid, "merchant_key": "namma metro"},
                                     {"$set": {"merchant": "Namma Metro", "category": "Transport & Fuel",
                                               "updated_at": now}}, upsert=True)
    print(f"seeded {len(docs)} expenses for {EMAIL} / {PASSWORD} in db '{s.mongo_db}'")


if __name__ == "__main__":
    main()
