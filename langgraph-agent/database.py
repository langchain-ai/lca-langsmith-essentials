"""In-memory data store for LangSlice Pizzeria.

Holds everything the agent can look up:

* ``COMPANY_INFO``      - searchable knowledge base (hours, address, policies, ...)
* ``INGREDIENTS``       - topping catalog with per-topping stock levels
* ``CRUSTS`` / ``SIZES`` / ``SPECIALTY_PIZZAS`` - the menu
* ``ORDERS``            - live orders, keyed by conversation thread id

There is no real database here on purpose: the whole point of the demo is that
every lookup is fast, deterministic, and easy to eyeball next to a trace.
"""

from __future__ import annotations

import copy
import itertools
from typing import Any

from langsmith import traceable

# ---------------------------------------------------------------------------
# Company knowledge base
# ---------------------------------------------------------------------------

COMPANY_INFO: list[dict[str, Any]] = [
    {
        "id": "location",
        "title": "Location & directions",
        "tags": ["address", "location", "directions", "where", "parking", "find"],
        "content": (
            "LangSlice is at 412 Chainlink Ave, Suite 100, Brooklyn, NY 11211. "
            "We're two blocks from the Bedford Ave L stop. Street parking is "
            "usually available on Chainlink Ave after 6pm, and there is a paid "
            "lot next door at 418 Chainlink Ave."
        ),
    },
    {
        "id": "hours",
        "title": "Store hours",
        "tags": ["hours", "open", "close", "closing", "time", "today", "schedule"],
        "content": (
            "Hours: Monday-Thursday 11:00am-10:00pm, Friday-Saturday "
            "11:00am-12:00am, Sunday 12:00pm-9:00pm. The kitchen stops taking "
            "new orders 30 minutes before closing. We are closed on "
            "Thanksgiving and Christmas Day."
        ),
    },
    {
        "id": "contact",
        "title": "Contact information",
        "tags": ["phone", "call", "email", "contact", "number", "reach", "support"],
        "content": (
            "Phone: (718) 555-0142. Email: hello@langslice.example. "
            "For catering inquiries email catering@langslice.example. "
            "We answer DMs on social under @langslicebk during store hours."
        ),
    },
    {
        "id": "delivery",
        "title": "Delivery policy",
        "tags": ["delivery", "deliver", "radius", "fee", "minimum", "time", "eta"],
        "content": (
            "We deliver within a 3 mile radius of the shop. Delivery fee is "
            "$3.99, waived on orders over $35. Order minimum for delivery is "
            "$25. Typical delivery time is 35-50 minutes; during Friday and "
            "Saturday dinner rush it can reach 70 minutes. Pickup orders are "
            "usually ready in 15-20 minutes."
        ),
    },
    {
        "id": "payment",
        "title": "Payment options",
        "tags": ["payment", "pay", "card", "cash", "tip", "credit", "apple pay"],
        "content": (
            "We accept cash, all major credit cards, Apple Pay, and Google Pay. "
            "Tips can be added at checkout or in cash to the driver. We do not "
            "split a single order across more than two cards."
        ),
    },
    {
        "id": "gluten-free-crust",
        "title": "Gluten-free crust",
        "tags": [
            "gluten",
            "gluten-free",
            "glutenfree",
            "celiac",
            "wheat",
            "crust",
            "crusts",
            "size",
            "sizes",
        ],
        "content": (
            "Gluten-free crust is available in all three sizes - small, medium, "
            "and large - for $3.00 extra. It is a rice and tapioca flour blend, "
            "par-baked before it is topped. The dough is prepped in the same "
            "kitchen as our regular dough, so we cannot promise a celiac-safe "
            "pizza."
        ),
    },
    {
        "id": "allergens",
        "title": "Allergens & dietary options",
        "tags": [
            "allergen",
            "allergy",
            "vegan",
            "vegetarian",
            "dairy",
            "nut",
            "celiac",
        ],
        "content": (
            "Gluten-free crust is available for $3.00 extra. Vegan cheese is "
            "available for $2.00 extra. Our kitchen handles wheat, dairy, and "
            "soy, so we cannot guarantee an allergen-free environment for "
            "guests with celiac disease or severe allergies. Full allergen "
            "sheets are posted in store."
        ),
    },
    {
        "id": "loyalty",
        "title": "Loyalty program",
        "tags": ["loyalty", "rewards", "points", "coupon", "discount", "deal"],
        "content": (
            "The Slice Stack rewards program gives 1 point per dollar spent. "
            "100 points earns a free large one-topping pizza. Points expire 12 "
            "months after they are earned, and catering and party-tray orders "
            "do not earn points. Students get 10% off with a valid ID on "
            "weekdays before 4pm."
        ),
    },
    {
        "id": "catering",
        "title": "Catering & large orders",
        "tags": ["catering", "party", "large", "event", "bulk", "office"],
        "content": (
            "Catering starts at 5 pizzas and requires 24 hours notice. Party "
            "trays (32 squares) are $42 each. For orders over 15 pizzas, email "
            "catering@langslice.example so the kitchen can schedule the bake."
        ),
    },
]

# ---------------------------------------------------------------------------
# Ingredient catalog
#
# ``stock_units`` is the number of pizzas' worth of the topping left in the
# walk-in today. A value of 0 means the kitchen is out of it.
#
# ``price`` is the per-pizza upcharge on top of the size's base price. Tomato
# sauce and mozzarella are included in the base price, so mozzarella is 0.00 and
# a customer who wants more cheese than standard gets ``extra cheese``.
# ---------------------------------------------------------------------------

INGREDIENTS: dict[str, dict[str, Any]] = {
    "mozzarella": {"category": "cheese", "price": 0.00, "stock_units": 180, "vegetarian": True},
    "extra cheese": {"category": "cheese", "price": 1.50, "stock_units": 180, "vegetarian": True},
    "vegan cheese": {"category": "cheese", "price": 2.00, "stock_units": 24, "vegetarian": True},
    "feta": {"category": "cheese", "price": 2.00, "stock_units": 9, "vegetarian": True},
    "ricotta": {"category": "cheese", "price": 2.00, "stock_units": 0, "vegetarian": True},
    "parmesan": {"category": "cheese", "price": 1.25, "stock_units": 60, "vegetarian": True},
    "pepperoni": {"category": "meat", "price": 2.50, "stock_units": 74, "vegetarian": False},
    "sausage": {"category": "meat", "price": 2.50, "stock_units": 38, "vegetarian": False},
    "bacon": {"category": "meat", "price": 2.75, "stock_units": 16, "vegetarian": False},
    "ham": {"category": "meat", "price": 2.50, "stock_units": 11, "vegetarian": False},
    "grilled chicken": {"category": "meat", "price": 3.00, "stock_units": 27, "vegetarian": False},
    "anchovies": {"category": "meat", "price": 2.25, "stock_units": 0, "vegetarian": False},
    "mushrooms": {"category": "vegetable", "price": 1.75, "stock_units": 42, "vegetarian": True},
    "black olives": {"category": "vegetable", "price": 1.50, "stock_units": 33, "vegetarian": True},
    "green olives": {"category": "vegetable", "price": 1.50, "stock_units": 12, "vegetarian": True},
    "red onion": {"category": "vegetable", "price": 1.00, "stock_units": 55, "vegetarian": True},
    "bell pepper": {"category": "vegetable", "price": 1.25, "stock_units": 29, "vegetarian": True},
    "jalapeno": {"category": "vegetable", "price": 1.25, "stock_units": 21, "vegetarian": True},
    "spinach": {"category": "vegetable", "price": 1.50, "stock_units": 0, "vegetarian": True},
    "roasted garlic": {"category": "vegetable", "price": 1.00, "stock_units": 48, "vegetarian": True},
    "sun dried tomato": {"category": "vegetable", "price": 2.00, "stock_units": 7, "vegetarian": True},
    "pineapple": {"category": "fruit", "price": 1.75, "stock_units": 0, "vegetarian": True},
    "fresh basil": {"category": "herb", "price": 0.75, "stock_units": 36, "vegetarian": True},
    "oregano": {"category": "herb", "price": 0.50, "stock_units": 90, "vegetarian": True},
    "hot honey": {"category": "finish", "price": 1.00, "stock_units": 19, "vegetarian": True},
}

#: Common ways customers say a topping, mapped to the catalog key.
INGREDIENT_ALIASES: dict[str, str] = {
    "cheese": "mozzarella",
    "mozz": "mozzarella",
    "fresh mozzarella": "mozzarella",
    "feta cheese": "feta",
    "extra mozzarella": "extra cheese",
    "double cheese": "extra cheese",
    "olives": "black olives",
    "olive": "black olives",
    "black olive": "black olives",
    "green olive": "green olives",
    "kalamata": "black olives",
    "onion": "red onion",
    "onions": "red onion",
    "red onions": "red onion",
    "peppers": "bell pepper",
    "pepper": "bell pepper",
    "bell peppers": "bell pepper",
    "green pepper": "bell pepper",
    "green peppers": "bell pepper",
    "mushroom": "mushrooms",
    "shrooms": "mushrooms",
    "jalapenos": "jalapeno",
    "jalapeno peppers": "jalapeno",
    "jalapeños": "jalapeno",
    "jalapeño": "jalapeno",
    "chicken": "grilled chicken",
    "basil": "fresh basil",
    "garlic": "roasted garlic",
    "sun dried tomatoes": "sun dried tomato",
    "sundried tomato": "sun dried tomato",
    "sundried tomatoes": "sun dried tomato",
    "pineapples": "pineapple",
    "ananas": "pineapple",
    "sausages": "sausage",
    "italian sausage": "sausage",
    "pepperonis": "pepperoni",
    "anchovy": "anchovies",
    "prosciutto": "ham",
    "vegan mozzarella": "vegan cheese",
    "dairy free cheese": "vegan cheese",
    "parmigiano": "parmesan",
    "parm": "parmesan",
}

# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------

SIZES: dict[str, dict[str, Any]] = {
    "small": {"inches": 10, "base_price": 11.00, "slices": 6},
    "medium": {"inches": 14, "base_price": 15.00, "slices": 8},
    "large": {"inches": 18, "base_price": 19.00, "slices": 10},
}

CRUSTS: dict[str, dict[str, Any]] = {
    "hand tossed": {"upcharge": 0.00, "sizes": ["small", "medium", "large"]},
    "thin": {"upcharge": 0.00, "sizes": ["small", "medium", "large"]},
    "deep dish": {"upcharge": 2.50, "sizes": ["medium", "large"]},
    "gluten free": {"upcharge": 3.00, "sizes": ["small", "medium"]},
}

CRUST_ALIASES: dict[str, str] = {
    "hand-tossed": "hand tossed",
    "handtossed": "hand tossed",
    "regular": "hand tossed",
    "classic": "hand tossed",
    "original": "hand tossed",
    "thin crust": "thin",
    "new york": "thin",
    "ny": "thin",
    "deep-dish": "deep dish",
    "pan": "deep dish",
    "chicago": "deep dish",
    "gluten-free": "gluten free",
    "glutenfree": "gluten free",
    "gf": "gluten free",
}

SPECIALTY_PIZZAS: dict[str, dict[str, Any]] = {
    "adlc supreme": {
        "description": "Pepperoni, sausage, bacon, and hot honey.",
        "toppings": ["mozzarella", "pepperoni", "sausage", "bacon", "hot honey"],
        "prices": {"small": 19.75, "medium": 23.75, "large": 27.75},
    },
    "the monitoring margherita": {
        "description": "Crushed tomato, mozzarella, fresh basil, olive oil.",
        "toppings": ["mozzarella", "fresh basil", "oregano"],
        "prices": {"small": 12.25, "medium": 16.25, "large": 20.25},
    },
    "the golden dataset": {
        "description": "Mushrooms, bell pepper, red onion, black olives, spinach.",
        "toppings": [
            "mozzarella",
            "mushrooms",
            "bell pepper",
            "red onion",
            "black olives",
            "spinach",
        ],
        "prices": {"small": 18.00, "medium": 22.00, "large": 26.00},
    },
    "the spicy evaluator": {
        "description": "Grilled chicken, jalapeno, red onion, hot honey.",
        "toppings": ["mozzarella", "grilled chicken", "jalapeno", "red onion", "hot honey"],
        "prices": {"small": 17.25, "medium": 21.25, "large": 25.25},
    },
    "production pesto": {
        "description": "Pesto base, feta, sun dried tomato, roasted garlic.",
        "toppings": ["mozzarella", "feta", "sun dried tomato", "roasted garlic"],
        "prices": {"small": 16.00, "medium": 20.00, "large": 24.00},
    },
}

SIDES: dict[str, float] = {
    "garlic knots (6)": 6.50,
    "caesar salad": 8.00,
    "mozzarella sticks (6)": 7.50,
    "cannoli": 4.50,
    "fountain drink": 2.75,
}

# ---------------------------------------------------------------------------
# Delivery policy
#
# These mirror the ``delivery`` article in ``COMPANY_INFO``: change one and
# change the other, or the agent will quote a policy the code does not enforce.
# ---------------------------------------------------------------------------

#: Smallest order subtotal we will send out for delivery.
DELIVERY_MINIMUM = 25.00

#: Flat delivery fee, waived once the subtotal clears ``FREE_DELIVERY_OVER``.
DELIVERY_FEE = 3.99
FREE_DELIVERY_OVER = 35.00

# ---------------------------------------------------------------------------
# Live orders
# ---------------------------------------------------------------------------

#: Open and confirmed orders, keyed by conversation thread id.
ORDERS: dict[str, dict[str, Any]] = {}

_ORDER_SEQUENCE = itertools.count(1041)


def _normalize(text: str) -> str:
    return " ".join(str(text).strip().lower().replace("_", " ").split())


# ---------------------------------------------------------------------------
# Knowledge base lookups
# ---------------------------------------------------------------------------


def search_company_info(query: str, limit: int = 3) -> list[dict[str, Any]]:
    """Keyword search across the company knowledge base.

    Scores each article by how many query words hit its tags, title, or body,
    and returns the best ``limit`` matches.
    """
    words = [w for w in _normalize(query).split() if len(w) > 2]
    scored: list[tuple[int, dict[str, Any]]] = []

    for article in COMPANY_INFO:
        haystack = _normalize(f"{article['title']} {article['content']}")
        score = 0
        for word in words:
            if any(word in tag for tag in article["tags"]):
                score += 3
            elif word in haystack:
                score += 1
        if score:
            scored.append((score, article))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [
        {"id": a["id"], "title": a["title"], "content": a["content"]}
        for _, a in scored[:limit]
    ]


# ---------------------------------------------------------------------------
# Menu lookups
# ---------------------------------------------------------------------------


@traceable
def get_ingredient(name: str) -> dict[str, Any] | None:
    """Look a topping up in the catalog, tolerating plurals and nicknames.

    Returns the catalog record (with ``name`` folded in) or ``None`` when the
    kitchen has never heard of the topping.

    Traced, so each lookup lands in LangSmith as a child run of whichever order
    tool made it, showing the full catalog record - ``stock_units`` included.
    That is a trace-only side effect: callers still receive the same dict they
    always did, and the order tools pass only topping *names* into their return
    values, so nothing here reaches the model's context.
    """
    key = _normalize(name)
    key = INGREDIENT_ALIASES.get(key, key)

    if key not in INGREDIENTS and key.endswith("s"):
        singular = key[:-1]
        key = INGREDIENT_ALIASES.get(singular, singular)

    record = INGREDIENTS.get(key)
    if record is None:
        return None
    return {"name": key, **record}


def get_crust(name: str) -> dict[str, Any] | None:
    """Look a crust up in the menu, tolerating hyphenation and nicknames."""
    key = _normalize(name)
    key = CRUST_ALIASES.get(key, key)
    record = CRUSTS.get(key)
    if record is None:
        return None
    return {"name": key, **record}


def get_specialty_pizza(name: str) -> dict[str, Any] | None:
    """Look up a specialty pizza by its menu name."""
    key = _normalize(name)
    record = SPECIALTY_PIZZAS.get(key)
    if record is None:
        return None
    return {"name": key, **record}


def list_toppings(in_stock_only: bool = True) -> list[dict[str, Any]]:
    """Return the topping catalog, optionally hiding anything out of stock."""
    toppings = []
    for name, record in sorted(INGREDIENTS.items()):
        if in_stock_only and record["stock_units"] <= 0:
            continue
        toppings.append({"name": name, **record})
    return toppings


def format_menu_markdown() -> str:
    """Build a compact menu that renders cleanly in a browser and a terminal."""
    lines = [
        "## 🍕 LangSlice Menu",
        "",
        "### Specialty Pizzas",
        "",
        "| Pizza | Toppings | Small | Medium | Large |",
        "|:--|:--|--:|--:|--:|",
    ]

    for name, spec in SPECIALTY_PIZZAS.items():
        prices = spec["prices"]
        lines.append(
            f"| **{name.title()}** | {spec['description']} | "
            f"${prices['small']:.2f} | ${prices['medium']:.2f} | "
            f"${prices['large']:.2f} |"
        )

    lines.extend(
        [
            "",
            "### Build Your Pizza",
            "",
            "| Size | Diameter | Slices | Base price |",
            "|:--|--:|--:|--:|",
        ]
    )
    for name, spec in SIZES.items():
        lines.append(
            f"| **{name.title()}** | {spec['inches']}\" | {spec['slices']} | "
            f"${spec['base_price']:.2f} |"
        )

    lines.extend(
        [
            "",
            "### Choose a Crust",
            "",
            "| Crust | Upcharge | Available sizes |",
            "|:--|--:|:--|",
        ]
    )
    for name, spec in CRUSTS.items():
        price = "Included" if spec["upcharge"] == 0 else f"+${spec['upcharge']:.2f}"
        sizes = ", ".join(size.title() for size in spec["sizes"])
        lines.append(f"| **{name.title()}** | {price} | {sizes} |")

    lines.extend(
        [
            "",
            "### Add Toppings",
            "",
            "*Prices are per pizza.*",
        ]
    )
    toppings_by_category: dict[str, list[dict[str, Any]]] = {}
    for topping in list_toppings(in_stock_only=False):
        toppings_by_category.setdefault(topping["category"], []).append(topping)

    category_order = ("cheese", "meat", "vegetable", "fruit", "herb", "finish")
    for category in category_order:
        toppings = toppings_by_category.get(category, [])
        if not toppings:
            continue
        lines.extend(
            [
                "",
                f"#### {category.title()}",
                "",
                "| Topping | Price |",
                "|:--|--:|",
            ]
        )
        for topping in toppings:
            price = (
                "Included" if topping["price"] == 0 else f"${topping['price']:.2f}"
            )
            lines.append(f"| **{topping['name'].title()}** | {price} |")

    lines.extend(
        [
            "",
            "### Sides & Drinks",
            "",
            "| Item | Price |",
            "|:--|--:|",
        ]
    )
    for name, price in SIDES.items():
        lines.append(f"| **{name.title()}** | ${price:.2f} |")

    lines.extend(
        [
            "",
            "*Pizza prices include tomato sauce and mozzarella. Crust and topping "
            "upcharges are added to the base price.*",
        ]
    )
    return "\n".join(lines)


def format_menu_terminal() -> str:
    """Build a line-oriented menu for terminals that do not render Markdown."""
    lines = ["LANGSLICE MENU", "==============", "", "SPECIALTY PIZZAS"]
    for name, spec in SPECIALTY_PIZZAS.items():
        prices = spec["prices"]
        price_text = " · ".join(
            f"{size.title()} ${prices[size]:.2f}" for size in SIZES
        )
        lines.extend(
            [f"  {name.title()}", f"    {spec['description']}", f"    {price_text}"]
        )

    lines.extend(["", "BUILD YOUR PIZZA"])
    for name, spec in SIZES.items():
        details = f'{spec["inches"]}" · {spec["slices"]} slices'
        lines.append(f"  {name.title():<8} {details:<18} ${spec['base_price']:.2f}")

    lines.extend(["", "CRUSTS"])
    for name, spec in CRUSTS.items():
        price = "included" if spec["upcharge"] == 0 else f"+${spec['upcharge']:.2f}"
        sizes = ", ".join(spec["sizes"])
        lines.append(f"  {name.title():<14} {price:<9} ({sizes})")

    lines.extend(["", "ADD TOPPINGS (price per pizza)"])
    toppings_by_category: dict[str, list[dict[str, Any]]] = {}
    for topping in list_toppings(in_stock_only=False):
        toppings_by_category.setdefault(topping["category"], []).append(topping)
    category_order = ("cheese", "meat", "vegetable", "fruit", "herb", "finish")
    for category in category_order:
        toppings = toppings_by_category.get(category, [])
        if not toppings:
            continue
        lines.append(f"  {category.title()}")
        for topping in toppings:
            price = "included" if topping["price"] == 0 else f"${topping['price']:.2f}"
            lines.append(f"    {topping['name'].title():<22} {price}")

    lines.extend(["", "SIDES & DRINKS"])
    for name, price in SIDES.items():
        lines.append(f"  {name.title():<25} ${price:.2f}")

    lines.extend(
        [
            "",
            "Pizza prices include tomato sauce and mozzarella.",
            "Crust and topping upcharges are added to the base price.",
        ]
    )
    return "\n".join(lines)


def get_menu() -> dict[str, Any]:
    """Return the full menu: sizes, crusts, specialty pizzas, toppings, sides."""
    return {
        "display_markdown": format_menu_markdown(),
        "base_price_includes": (
            "Every pizza's base price includes tomato sauce and mozzarella. "
            "Topping prices below are per-pizza upcharges on top of the base "
            "price and the crust upcharge; mozzarella is listed at 0.00 because "
            "it is already included."
        ),
        "sizes": {
            name: {
                "diameter_inches": spec["inches"],
                "slices": spec["slices"],
                "base_price": spec["base_price"],
            }
            for name, spec in SIZES.items()
        },
        "crusts": {
            name: {"upcharge": spec["upcharge"], "available_sizes": spec["sizes"]}
            for name, spec in CRUSTS.items()
        },
        "specialty_pizzas": {
            name: {
                "description": spec["description"],
                "toppings": spec["toppings"],
                "prices": spec["prices"],
            }
            for name, spec in SPECIALTY_PIZZAS.items()
        },
        "toppings": [
            {"name": t["name"], "category": t["category"], "price": t["price"]}
            for t in list_toppings(in_stock_only=False)
        ],
        "sides": SIDES,
    }


def _price_line(label: str, amount: float) -> dict[str, Any]:
    """One component of a pizza's price. Free components say so out loud.

    Mozzarella and the standard crusts cost nothing, but they are still on the
    pizza the customer sees, so they get a line rather than being dropped - a
    breakdown that silently omits them reads as an incomplete accounting.
    """
    return {
        "label": label if amount else f"{label} (included)",
        "amount": round(amount, 2),
    }


def price_breakdown(size: str, crust: str, toppings: list[str]) -> dict[str, Any]:
    """Itemize a pizza's price: size base, crust upcharge, then each topping.

    This is the single source of truth for what a pizza costs - ``price_pizza``
    sums these very lines, so an itemized breakdown cannot drift away from the
    ``unit_price`` the customer was quoted.
    """
    lines = [
        _price_line(f"{size} base", SIZES[size]["base_price"]),
        _price_line(f"{crust} crust", CRUSTS[crust]["upcharge"]),
    ]
    for topping in toppings:
        record = INGREDIENTS.get(topping)
        if record is not None:
            lines.append(_price_line(topping, record["price"]))
    return {
        "lines": lines,
        "unit_price": round(sum(line["amount"] for line in lines), 2),
    }


def price_pizza(size: str, crust: str, toppings: list[str]) -> float:
    """Price a single pizza from its size, crust, and resolved toppings."""
    return price_breakdown(size, crust, toppings)["unit_price"]


# ---------------------------------------------------------------------------
# Order lifecycle
# ---------------------------------------------------------------------------


def new_order(thread_id: str, customer_name: str, order_type: str, address: str | None) -> dict[str, Any]:
    """Create (and register) a fresh open order for this conversation."""
    order = {
        "order_id": f"LS-{next(_ORDER_SEQUENCE)}",
        "customer_name": customer_name,
        "order_type": order_type,
        "address": address,
        "pizzas": [],
        "sides": [],
        "status": "open",
    }
    ORDERS[thread_id] = order
    return order


def get_order(thread_id: str) -> dict[str, Any] | None:
    """Return this conversation's order, or ``None`` if none has been started."""
    return ORDERS.get(thread_id)


def clear_order(thread_id: str) -> None:
    """Forget this conversation's order (used by the chat UI's reset button)."""
    ORDERS.pop(thread_id, None)


def renumber_pizzas(order: dict[str, Any]) -> None:
    """Keep ``pizza_number`` in sync with position in the order."""
    for index, pizza in enumerate(order["pizzas"], start=1):
        pizza["pizza_number"] = index


def build_pizza(size: str, crust: str, toppings: list[str], quantity: int, notes: str | None) -> dict[str, Any]:
    """Assemble a pizza line item (not yet attached to an order)."""
    pricing = price_breakdown(size, crust, toppings)
    return {
        "pizza_number": 0,
        "size": size,
        "crust": crust,
        "toppings": list(toppings),
        "quantity": quantity,
        "notes": notes,
        "unit_price": pricing["unit_price"],
        "price_lines": pricing["lines"],
    }


def copy_pizza(pizza: dict[str, Any]) -> dict[str, Any]:
    """Deep copy a pizza line item."""
    return copy.deepcopy(pizza)


def order_summary(order: dict[str, Any]) -> dict[str, Any]:
    """Customer-facing view of an order, with line items and totals."""
    renumber_pizzas(order)

    lines = []
    subtotal = 0.0
    for pizza in order["pizzas"]:
        line_total = round(pizza["unit_price"] * pizza["quantity"], 2)
        subtotal += line_total
        # Named for the figure it adds up to, not for the line item, so nothing
        # downstream reads a per-pizza itemization against a multiplied total.
        # Recomputed only for a pizza built before the field existed.
        price_lines = pizza.get("price_lines") or price_breakdown(
            pizza["size"], pizza["crust"], pizza["toppings"]
        )["lines"]
        lines.append(
            {
                "pizza_number": pizza["pizza_number"],
                "quantity": pizza["quantity"],
                "size": pizza["size"],
                "crust": pizza["crust"],
                "specialty_pizza": pizza.get("specialty_pizza"),
                "toppings": pizza["toppings"],
                "notes": pizza["notes"],
                "unit_price": pizza["unit_price"],
                "unit_price_lines": price_lines,
                "line_total": line_total,
            }
        )

    side_lines = []
    for side in order["sides"]:
        line_total = round(side["price"] * side["quantity"], 2)
        subtotal += line_total
        side_lines.append({**side, "line_total": line_total})

    delivery_fee = 0.0
    if order["order_type"] == "delivery" and subtotal < FREE_DELIVERY_OVER:
        delivery_fee = DELIVERY_FEE

    subtotal = round(subtotal, 2)
    tax = round(subtotal * 0.08875, 2)
    total = round(subtotal + tax + delivery_fee, 2)

    return {
        "order_id": order["order_id"],
        "status": order["status"],
        "customer_name": order["customer_name"],
        "order_type": order["order_type"],
        "address": order["address"],
        "pizzas": lines,
        "sides": side_lines,
        "subtotal": subtotal,
        "delivery_fee": delivery_fee,
        "tax": tax,
        "total": total,
    }
