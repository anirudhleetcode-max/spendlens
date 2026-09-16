"""Synthetic, India-first dataset for the expense category classifier.

Each sample is the text we have at prediction time: merchant name plus (optionally) a few line-item
names, the way they come out of a receipt. Merchants are split into train/test *by merchant*, so the
test score measures generalisation to shops the model has never seen, not memorisation.

    python -m ml.dataset          # prints a few rows and the split sizes
"""
from __future__ import annotations

import random

# (merchants, item vocabulary) per category. Merchant names are what appears on the bill header.
DATA: dict[str, tuple[list[str], list[str]]] = {
    "Groceries": (
        ["DMart", "Avenue Supermarts Ltd", "Reliance Fresh", "Reliance Smart", "BigBasket", "Blinkit",
         "Zepto", "More Supermarket", "Spencer's Retail", "Star Bazaar", "Nature's Basket", "Ratnadeep Supermarket",
         "Heritage Fresh", "Nilgiris", "Easyday", "Vishal Mega Mart", "Kirana King General Store",
         "Sri Balaji Provision Stores", "Metro Cash & Carry", "Swiggy Instamart", "JioMart", "Big Bazaar",
         "Lulu Hypermarket", "Foodhall", "Namdhari's Fresh", "Country Delight", "Mother Dairy Booth",
         "Sai Ram Kirana", "Apna Bazaar", "Village Supermarket", "Daily Needs Mart", "Fresh To Home"],
        ["toor dal", "basmati rice", "aashirvaad atta", "amul butter", "amul taaza milk", "curd", "paneer",
         "onion", "tomato", "potato", "coriander", "green chilli", "fortune sunflower oil", "tata salt",
         "sugar", "maggi noodles", "parle g", "good day biscuit", "surf excel", "vim bar", "colgate",
         "bread", "eggs", "banana", "apple", "moong dal", "chana dal", "poha", "rava", "haldi powder",
         "mdh garam masala", "tata tea gold", "bru coffee", "ghee", "lays chips", "kurkure", "dettol soap",
         "harpic", "atta 10kg", "sona masoori rice", "cabbage", "cauliflower", "lemon", "ginger garlic paste"],
    ),
    "Food & Dining": (
        ["Swiggy", "Zomato", "Domino's Pizza", "McDonald's", "KFC", "Burger King", "Haldiram's", "Barbeque Nation",
         "Starbucks", "Cafe Coffee Day", "Chaayos", "Saravana Bhavan", "Paradise Biryani", "Behrouz Biryani",
         "Theobroma", "Subway", "Pizza Hut", "Wow! Momo", "Bikanervala", "Sagar Ratna", "A2B Adyar Ananda Bhavan",
         "Mainland China", "Social", "Truffles", "MTR", "Meghana Foods", "Bademiya", "Karim's", "Udupi Grand",
         "Third Wave Coffee", "Blue Tokai", "Faasos", "Rameshwaram Cafe", "Punjabi Dhaba", "Hotel Annapoorna",
         "Taj Mahal Hotel Restaurant", "Cream Centre", "Irani Cafe", "Biryani By Kilo", "Keventers"],
        ["paneer butter masala", "butter naan", "veg biryani", "chicken biryani", "masala dosa", "idli vada",
         "filter coffee", "cappuccino", "cold coffee", "french fries", "mc aloo tikki", "zinger burger",
         "margherita pizza", "garlic bread", "dal makhani", "jeera rice", "tandoori roti", "gulab jamun",
         "veg thali", "chole bhature", "pav bhaji", "masala chai", "momos", "hakka noodles", "manchurian",
         "lassi", "brownie", "delivery charge", "packaging charge", "service charge", "mineral water",
         "fish curry", "mutton rogan josh", "rasmalai", "vada pav", "sandwich", "paratha", "cheesecake"],
    ),
    "Transport & Fuel": (
        ["Indian Oil", "IOCL Fuel Station", "HP Petrol Pump", "Hindustan Petroleum", "Bharat Petroleum",
         "BPCL", "Shell", "Nayara Energy", "Reliance Jio-bp", "Uber", "Ola", "Rapido", "Namma Yatri",
         "Delhi Metro", "Mumbai Metro One", "BMTC", "BEST", "FASTag Recharge", "Park+", "Sri Sai Service Station",
         "Maruti Suzuki Service", "Honda Service Centre", "Blu Smart", "Meru Cabs", "Chalo", "Yulu",
         "Metro Parking", "Go Mechanic", "Bounce", "Quick Ride", "Essar Petrol Pump", "CNG Station IGL"],
        ["petrol", "diesel", "speed petrol", "xtra premium", "power petrol", "cng", "fuel", "litres",
         "trip fare", "ride fare", "auto ride", "bike taxi", "metro card recharge", "smart card top up",
         "bus pass", "parking fee", "toll", "fastag", "engine oil", "general service", "tyre puncture",
         "air check", "wheel alignment", "coolant", "car wash", "base fare", "surge", "rate/ltr", "nozzle",
         "pump no", "vehicle no", "density"],
    ),
    "Shopping": (
        ["Amazon", "Flipkart", "Myntra", "Ajio", "Nykaa", "Meesho", "Croma", "Reliance Digital", "Vijay Sales",
         "Decathlon", "Westside", "Pantaloons", "Lifestyle", "Max Fashion", "Shoppers Stop", "Zudio", "H&M",
         "Uniqlo", "IKEA", "Pepperfry", "Bata", "Titan", "Tanishq", "FabIndia", "Lenskart", "Tata CLiQ",
         "Mr DIY", "Home Centre", "Poorvika Mobiles", "Sangeetha Mobiles", "Raymond", "Manyavar",
         "Chumbak", "Miniso", "Sapna Book House Stationery", "Hamleys"],
        ["t shirt", "jeans", "kurta", "saree", "running shoes", "sneakers", "backpack", "earphones",
         "bluetooth speaker", "phone case", "charger", "usb cable", "lipstick", "moisturiser", "sunscreen",
         "shampoo", "perfume", "watch", "sunglasses", "bedsheet", "cushion cover", "storage box", "kitchen set",
         "pressure cooker", "mixer grinder", "power bank", "keyboard", "mouse", "smartphone", "hoodie",
         "dress", "wallet", "toys", "lamp", "curtains", "water bottle", "yoga mat", "sports shorts"],
    ),
    "Health": (
        ["Apollo Pharmacy", "MedPlus", "Netmeds", "PharmEasy", "1mg", "Tata 1mg", "Wellness Forever",
         "Guardian Pharmacy", "Frank Ross Pharmacy", "Dr Lal PathLabs", "Thyrocare", "Metropolis Healthcare",
         "Apollo Clinic", "Fortis Hospital", "Manipal Hospitals", "Max Healthcare", "Cult.fit", "Gold's Gym",
         "Practo", "Sri Venkateshwara Medicals", "Jan Aushadhi Kendra", "Clove Dental", "Vasan Eye Care",
         "Narayana Health", "Aster Pharmacy", "Healthians", "Anytime Fitness", "Care Hospitals",
         "Shree Ganesh Medical Store", "Sanjeevani Chemist"],
        ["paracetamol 650", "dolo 650", "crocin", "azithromycin", "cetirizine", "pantoprazole", "vitamin d3",
         "b complex", "cough syrup", "strip", "tablet", "capsule", "ointment", "bandage", "thermometer",
         "consultation fee", "blood test", "cbc", "thyroid profile", "lipid profile", "hba1c", "x ray",
         "dental cleaning", "eye test", "physiotherapy", "gym membership", "protein powder", "ors",
         "hand sanitizer", "face mask", "insulin", "bp monitor", "glucometer strips", "mrp", "batch no", "exp"],
    ),
    "Bills & Utilities": (
        ["BESCOM", "Tata Power", "Adani Electricity", "MSEDCL", "TNEB", "BSES Rajdhani", "Airtel", "Jio",
         "Vodafone Idea", "BSNL", "ACT Fibernet", "Hathway", "Tata Play", "Dish TV", "Indane Gas",
         "HP Gas", "Bharat Gas", "Mahanagar Gas", "BWSSB", "Delhi Jal Board", "Society Maintenance",
         "NoBroker Rent", "LIC", "HDFC Ergo", "Paytm Bill Payment", "CRED", "Excitel", "Torrent Power",
         "KSEB", "CESC", "Airtel Xstream", "Jio Fiber"],
        ["electricity bill", "units consumed", "fixed charges", "energy charges", "postpaid bill",
         "prepaid recharge", "data pack", "broadband", "fiber plan", "dth recharge", "lpg cylinder",
         "refill booking", "piped gas", "water bill", "sewerage charges", "maintenance charges", "rent",
         "insurance premium", "policy renewal", "late payment fee", "consumer no", "account no",
         "billing period", "due date", "meter reading", "unlimited calls", "mbps plan", "arrears"],
    ),
    "Entertainment": (
        ["PVR INOX", "PVR Cinemas", "INOX", "Cinepolis", "BookMyShow", "Netflix", "Spotify",
         "Amazon Prime", "Disney+ Hotstar", "JioCinema", "SonyLIV", "Zee5", "Wonderla", "Imagica",
         "Smaaash", "Timezone", "District by Zomato", "Paytm Insider", "Steam", "PlayStation Store",
         "Hard Rock Cafe Events", "Mystery Rooms", "Snow World", "Bowling Co", "Kingdom of Dreams",
         "Carnival Cinemas", "Miraj Cinemas", "YouTube Premium", "Apple Music", "Gaana Plus"],
        ["movie ticket", "recliner seat", "popcorn combo", "nachos", "pepsi", "3d glasses",
         "subscription", "monthly plan", "annual plan", "premium plan", "concert ticket", "standup show",
         "entry ticket", "gaming credits", "bowling lane", "escape room", "amusement park", "water park",
         "convenience fee", "game purchase", "screen 4", "row f", "show time", "audi 2", "family pack"],
    ),
    "Travel": (
        ["IRCTC", "Indian Railways", "IndiGo", "Air India", "Akasa Air", "SpiceJet", "Vistara", "MakeMyTrip",
         "Goibibo", "Cleartrip", "Yatra", "EaseMyTrip", "redBus", "KSRTC", "MSRTC", "Abhibus", "OYO",
         "Treebo", "FabHotels", "Taj Hotels", "ITC Hotels", "Lemon Tree Hotels", "Zostel", "Airbnb",
         "Booking.com", "Agoda", "Thomas Cook", "Zoomcar", "Club Mahindra", "Ginger Hotels", "Ixigo",
         "VRL Travels"],
        ["pnr", "train ticket", "3a berth", "sleeper class", "tatkal", "flight ticket", "boarding pass",
         "seat selection", "excess baggage", "bus ticket", "volvo ac sleeper", "hotel stay", "room night",
         "check in", "check out", "room charges", "city tax", "tour package", "visa fee", "travel insurance",
         "self drive car", "airport transfer", "breakfast included", "deluxe room", "dorm bed", "itinerary",
         "departure", "arrival", "guest name", "nights"],
    ),
    "Education": (
        ["BYJU'S", "Unacademy", "Physics Wallah", "Coursera", "Udemy", "upGrad", "Great Learning",
         "Scaler Academy", "Vedantu", "Sapna Book House", "Crossword Bookstore", "Higginbothams",
         "Oxford Book Store", "Kindle Store", "Allen Career Institute", "Aakash Institute", "FIITJEE",
         "Delhi Public School", "Kendriya Vidyalaya", "VIT University", "Anna University", "NPTEL",
         "British Council", "IELTS IDP", "Classmate Stationery", "Navneet", "Bookswagon", "Pearson VUE",
         "Coding Ninjas", "LeetCode", "Simplilearn", "Khan Stationery Mart"],
        ["tuition fee", "semester fee", "exam fee", "admission fee", "course enrolment", "certificate",
         "textbook", "notebook", "long notebook", "geometry box", "pen", "pencil", "scientific calculator",
         "reference book", "ncert", "rd sharma", "hc verma", "test series", "coaching fee", "lab fee",
         "library fine", "online course", "subscription", "registration", "hostel fee", "uniform",
         "school bag", "chart paper", "exam registration", "a4 sheets", "stapler", "highlighter"],
    ),
    "Other": (
        ["India Post", "Blue Dart", "DTDC", "Delhivery", "Urban Company", "Naturals Salon", "Lakme Salon",
         "Green Trends", "Jawed Habib", "Sri Krishna Dry Cleaners", "UClean Laundry", "Ganesh Temple Trust",
         "GiveIndia", "Paytm Transfer", "Municipal Corporation", "Passport Seva", "RTO Office",
         "Notary Services", "Pet Planet", "Heads Up For Tails", "Supertails", "Ferns N Petals",
         "Archies Gallery", "Xerox Point", "Key Maker", "Locksmith Services", "Tailor Shop",
         "Plumber Services", "Pest Control India", "Housejoy", "Cash Withdrawal", "Gift Shop"],
        ["courier charges", "speed post", "parcel", "haircut", "hair spa", "facial", "beard trim",
         "dry cleaning", "wash and iron", "laundry per kg", "donation", "offering", "property tax",
         "passport fee", "driving licence fee", "notary charges", "pet food", "dog shampoo", "vet visit",
         "flowers bouquet", "greeting card", "photocopy", "print out", "key duplicate", "stitching charges",
         "alteration", "plumbing work", "pest control", "cleaning service", "gift wrap", "misc", "service"],
    ),
}


def _ocr_noise(text: str, rng: random.Random, p: float) -> str:
    """Imitate Tesseract slips: dropped / swapped characters and case changes."""
    swaps = {"o": "0", "l": "1", "i": "l", "s": "5", "e": "c", "a": "o", "b": "h", "m": "rn"}
    out = []
    for ch in text:
        r = rng.random()
        if r < p / 3:
            continue
        if r < 2 * p / 3 and ch.lower() in swaps:
            out.append(swaps[ch.lower()])
            continue
        out.append(ch)
    s = "".join(out)
    if rng.random() < 0.3:
        s = s.upper()
    return s


def make_sample(merchant: str, vocab: list[str], rng: random.Random) -> str:
    mode = rng.random()
    if mode < 0.25:  # manual entry: merchant only
        text = merchant
    elif mode < 0.35:  # items only (merchant header unreadable)
        text = " ".join(rng.sample(vocab, k=rng.randint(2, 5)))
    else:
        text = merchant + " " + " ".join(rng.sample(vocab, k=rng.randint(1, 6)))
    if rng.random() < 0.35:
        text = _ocr_noise(text, rng, p=0.08)
    return text


def split_merchants(seed: int = 7, test_frac: float = 0.25) -> tuple[dict, dict]:
    rng = random.Random(seed)
    train, test = {}, {}
    for cat, (merchants, _) in DATA.items():
        ms = merchants[:]
        rng.shuffle(ms)
        k = max(3, round(len(ms) * test_frac))
        test[cat], train[cat] = ms[:k], ms[k:]
    return train, test


def build(seed: int = 7, per_merchant: int = 30) -> tuple[list[str], list[str], list[str], list[str]]:
    """Returns X_train, y_train, X_test, y_test with merchants disjoint between the two."""
    rng = random.Random(seed)
    train_m, test_m = split_merchants(seed)
    X_tr, y_tr, X_te, y_te = [], [], [], []
    for cat, (_, vocab) in DATA.items():
        # items vocabulary is shared (items are generic); the merchant names are what is held out
        for m in train_m[cat]:
            for _ in range(per_merchant):
                X_tr.append(make_sample(m, vocab, rng)); y_tr.append(cat)
        for m in test_m[cat]:
            for _ in range(per_merchant // 2):
                X_te.append(make_sample(m, vocab, rng)); y_te.append(cat)
    return X_tr, y_tr, X_te, y_te


def build_full(seed: int = 7, per_merchant: int = 30) -> tuple[list[str], list[str]]:
    """All merchants, used for the final model after evaluation."""
    rng = random.Random(seed + 1)
    X, y = [], []
    for cat, (merchants, vocab) in DATA.items():
        for m in merchants:
            for _ in range(per_merchant):
                X.append(make_sample(m, vocab, rng)); y.append(cat)
    return X, y


def known_merchants() -> dict[str, str]:
    """Canonical merchant name -> category, used by the receipt parser for fuzzy header matching."""
    return {m: cat for cat, (ms, _) in DATA.items() for m in ms}


if __name__ == "__main__":
    Xtr, ytr, Xte, yte = build()
    print(len(Xtr), "train /", len(Xte), "test")
    for x, y in list(zip(Xtr, ytr))[::400]:
        print(f"{y:18} | {x}")
