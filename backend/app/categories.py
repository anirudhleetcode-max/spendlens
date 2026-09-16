# The ten classes the category model predicts (order = column order of model probabilities).
MODEL_CATEGORIES = [
    "Groceries",
    "Food & Dining",
    "Transport & Fuel",
    "Shopping",
    "Health",
    "Bills & Utilities",
    "Entertainment",
    "Travel",
    "Education",
    "Other",
]
# Stored when the model abstains and the user hasn't picked a category yet.
UNCATEGORISED = "Uncategorised"
CATEGORIES = MODEL_CATEGORIES + [UNCATEGORISED]
PAYMENT_MODES = ["UPI", "Card", "Cash", "Wallet", "Net Banking", "Unknown"]
