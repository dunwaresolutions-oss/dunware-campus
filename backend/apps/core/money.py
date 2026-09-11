"""Currency formatting for server-rendered documents.

The browser does the heavy lifting via ``Intl.NumberFormat`` (see
``frontend/lib/format.ts``); this is only for HTML/PDF Campus renders itself
(invoices, receipts). The v1 currency set matches the payments plan.
"""
from __future__ import annotations

# code -> (symbol, human name). Order is the companion dropdown order.
CURRENCIES: dict[str, tuple[str, str]] = {
    "CAD": ("$", "Canadian dollar"),
    "USD": ("$", "US dollar"),
    "ZAR": ("R", "South African rand"),
    "NAD": ("N$", "Namibian dollar"),
    "BWP": ("P", "Botswana pula"),
    "ZMW": ("K", "Zambian kwacha"),
    "ZWL": ("Z$", "Zimbabwean dollar"),
    "MWK": ("MK", "Malawian kwacha"),
    "MZN": ("MT", "Mozambican metical"),
    "BSD": ("$", "Bahamian dollar"),
}

# country (ISO-3166 alpha-2) -> currencies offered, first is the default
COUNTRY_CURRENCIES: dict[str, list[str]] = {
    "CA": ["CAD"],
    "BS": ["BSD", "USD"],
    "ZA": ["ZAR"],
    "NA": ["NAD", "ZAR"],
    "BW": ["BWP"],
    "ZM": ["ZMW"],
    "ZW": ["USD", "ZWL"],
    "MW": ["MWK"],
    "MZ": ["MZN"],
}


def currency_symbol(code: str) -> str:
    return CURRENCIES.get((code or "").upper(), ("", ""))[0] or (code or "").upper()


def format_money(cents: int | None, code: str = "CAD") -> str:
    if cents is None:
        return "—"
    sym = currency_symbol(code)
    return f"{sym}{cents / 100:,.2f}"
