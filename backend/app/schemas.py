from datetime import date as Date

from pydantic import BaseModel, Field, field_validator

from .categories import CATEGORIES, PAYMENT_MODES


def check_category(v: str | None) -> str | None:
    if v is not None and v not in CATEGORIES:
        raise ValueError(f"category must be one of: {', '.join(CATEGORIES)}")
    return v


def check_payment(v: str | None) -> str | None:
    if v is not None and v not in PAYMENT_MODES:
        raise ValueError(f"payment_mode must be one of: {', '.join(PAYMENT_MODES)}")
    return v


class LineItem(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    qty: float = Field(default=1, ge=0, le=100000)
    price: float = Field(default=0, ge=0, le=10_000_000)


class ExpenseIn(BaseModel):
    merchant: str = Field(min_length=1, max_length=80)
    amount: float = Field(gt=0, le=10_000_000)
    date: Date
    category: str | None = None
    tax: float = Field(default=0, ge=0, le=10_000_000)
    payment_mode: str = "Unknown"
    items: list[LineItem] = Field(default_factory=list, max_length=60)
    notes: str = Field(default="", max_length=300)
    receipt_id: str | None = None
    suggested_category: str | None = None

    _cat = field_validator("category", "suggested_category")(lambda v: check_category(v))
    _pm = field_validator("payment_mode")(lambda v: check_payment(v))

    @field_validator("merchant", "notes")
    @classmethod
    def _strip(cls, v: str):
        return v.strip()


class ExpensePatch(BaseModel):
    merchant: str | None = Field(default=None, min_length=1, max_length=80)
    amount: float | None = Field(default=None, gt=0, le=10_000_000)
    date: Date | None = None
    category: str | None = None
    tax: float | None = Field(default=None, ge=0, le=10_000_000)
    payment_mode: str | None = None
    items: list[LineItem] | None = Field(default=None, max_length=60)
    notes: str | None = Field(default=None, max_length=300)

    _cat = field_validator("category")(lambda v: check_category(v))
    _pm = field_validator("payment_mode")(lambda v: check_payment(v))


class BudgetIn(BaseModel):
    category: str
    amount: float = Field(gt=0, le=10_000_000)

    @field_validator("category")
    @classmethod
    def _cat(cls, v):
        if v not in CATEGORIES:
            raise ValueError("unknown category")
        return v


class SuggestIn(BaseModel):
    merchant: str = Field(default="", max_length=80)
    items: list[str] = Field(default_factory=list, max_length=60)
