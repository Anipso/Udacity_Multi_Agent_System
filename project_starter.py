import re
import pandas as pd
import numpy as np
import os
import time
import dotenv
import ast
from sqlalchemy.sql import text
from datetime import datetime, timedelta
from typing import Dict, List, Union
from sqlalchemy import create_engine, Engine
from smolagents import (
    ToolCallingAgent,
    OpenAIServerModel,
    tool,
)

# Create an SQLite database
db_engine = create_engine("sqlite:///munder_difflin.db")

# List containing the different kinds of papers 
paper_supplies = [
    # Paper Types (priced per sheet unless specified)
    {"item_name": "A4 paper",                         "category": "paper",        "unit_price": 0.05},
    {"item_name": "Letter-sized paper",              "category": "paper",        "unit_price": 0.06},
    {"item_name": "Cardstock",                        "category": "paper",        "unit_price": 0.15},
    {"item_name": "Colored paper",                    "category": "paper",        "unit_price": 0.10},
    {"item_name": "Glossy paper",                     "category": "paper",        "unit_price": 0.20},
    {"item_name": "Matte paper",                      "category": "paper",        "unit_price": 0.18},
    {"item_name": "Recycled paper",                   "category": "paper",        "unit_price": 0.08},
    {"item_name": "Eco-friendly paper",               "category": "paper",        "unit_price": 0.12},
    {"item_name": "Poster paper",                     "category": "paper",        "unit_price": 0.25},
    {"item_name": "Banner paper",                     "category": "paper",        "unit_price": 0.30},
    {"item_name": "Kraft paper",                      "category": "paper",        "unit_price": 0.10},
    {"item_name": "Construction paper",               "category": "paper",        "unit_price": 0.07},
    {"item_name": "Wrapping paper",                   "category": "paper",        "unit_price": 0.15},
    {"item_name": "Glitter paper",                    "category": "paper",        "unit_price": 0.22},
    {"item_name": "Decorative paper",                 "category": "paper",        "unit_price": 0.18},
    {"item_name": "Letterhead paper",                 "category": "paper",        "unit_price": 0.12},
    {"item_name": "Legal-size paper",                 "category": "paper",        "unit_price": 0.08},
    {"item_name": "Crepe paper",                      "category": "paper",        "unit_price": 0.05},
    {"item_name": "Photo paper",                      "category": "paper",        "unit_price": 0.25},
    {"item_name": "Uncoated paper",                   "category": "paper",        "unit_price": 0.06},
    {"item_name": "Butcher paper",                    "category": "paper",        "unit_price": 0.10},
    {"item_name": "Heavyweight paper",                "category": "paper",        "unit_price": 0.20},
    {"item_name": "Standard copy paper",              "category": "paper",        "unit_price": 0.04},
    {"item_name": "Bright-colored paper",             "category": "paper",        "unit_price": 0.12},
    {"item_name": "Patterned paper",                  "category": "paper",        "unit_price": 0.15},

    # Product Types (priced per unit)
    {"item_name": "Paper plates",                     "category": "product",      "unit_price": 0.10},  # per plate
    {"item_name": "Paper cups",                       "category": "product",      "unit_price": 0.08},  # per cup
    {"item_name": "Paper napkins",                    "category": "product",      "unit_price": 0.02},  # per napkin
    {"item_name": "Disposable cups",                  "category": "product",      "unit_price": 0.10},  # per cup
    {"item_name": "Table covers",                     "category": "product",      "unit_price": 1.50},  # per cover
    {"item_name": "Envelopes",                        "category": "product",      "unit_price": 0.05},  # per envelope
    {"item_name": "Sticky notes",                     "category": "product",      "unit_price": 0.03},  # per sheet
    {"item_name": "Notepads",                         "category": "product",      "unit_price": 2.00},  # per pad
    {"item_name": "Invitation cards",                 "category": "product",      "unit_price": 0.50},  # per card
    {"item_name": "Flyers",                           "category": "product",      "unit_price": 0.15},  # per flyer
    {"item_name": "Party streamers",                  "category": "product",      "unit_price": 0.05},  # per roll
    {"item_name": "Decorative adhesive tape (washi tape)", "category": "product", "unit_price": 0.20},  # per roll
    {"item_name": "Paper party bags",                 "category": "product",      "unit_price": 0.25},  # per bag
    {"item_name": "Name tags with lanyards",          "category": "product",      "unit_price": 0.75},  # per tag
    {"item_name": "Presentation folders",             "category": "product",      "unit_price": 0.50},  # per folder

    # Large-format items (priced per unit)
    {"item_name": "Large poster paper (24x36 inches)", "category": "large_format", "unit_price": 1.00},
    {"item_name": "Rolls of banner paper (36-inch width)", "category": "large_format", "unit_price": 2.50},

    # Specialty papers
    {"item_name": "100 lb cover stock",               "category": "specialty",    "unit_price": 0.50},
    {"item_name": "80 lb text paper",                 "category": "specialty",    "unit_price": 0.40},
    {"item_name": "250 gsm cardstock",                "category": "specialty",    "unit_price": 0.30},
    {"item_name": "220 gsm poster paper",             "category": "specialty",    "unit_price": 0.35},
]

# Given below are some utility functions you can use to implement your multi-agent system

def generate_sample_inventory(paper_supplies: list, coverage: float = 0.4, seed: int = 137) -> pd.DataFrame:
    """
    Generate inventory for exactly a specified percentage of items from the full paper supply list.

    This function randomly selects exactly `coverage` × N items from the `paper_supplies` list,
    and assigns each selected item:
    - a random stock quantity between 200 and 800,
    - a minimum stock level between 50 and 150.

    The random seed ensures reproducibility of selection and stock levels.

    Args:
        paper_supplies (list): A list of dictionaries, each representing a paper item with
                               keys 'item_name', 'category', and 'unit_price'.
        coverage (float, optional): Fraction of items to include in the inventory (default is 0.4, or 40%).
        seed (int, optional): Random seed for reproducibility (default is 137).

    Returns:
        pd.DataFrame: A DataFrame with the selected items and assigned inventory values, including:
                      - item_name
                      - category
                      - unit_price
                      - current_stock
                      - min_stock_level
    """
    # Ensure reproducible random output
    np.random.seed(seed)

    # Calculate number of items to include based on coverage
    num_items = int(len(paper_supplies) * coverage)

    # Randomly select item indices without replacement
    selected_indices = np.random.choice(
        range(len(paper_supplies)),
        size=num_items,
        replace=False
    )

    # Extract selected items from paper_supplies list
    selected_items = [paper_supplies[i] for i in selected_indices]

    # Construct inventory records
    inventory = []
    for item in selected_items:
        inventory.append({
            "item_name": item["item_name"],
            "category": item["category"],
            "unit_price": item["unit_price"],
            "current_stock": np.random.randint(200, 800),  # Realistic stock range
            "min_stock_level": np.random.randint(50, 150)  # Reasonable threshold for reordering
        })

    # Return inventory as a pandas DataFrame
    return pd.DataFrame(inventory)

def init_database(db_engine: Engine, seed: int = 137) -> Engine:    
    """
    Set up the Munder Difflin database with all required tables and initial records.

    This function performs the following tasks:
    - Creates the 'transactions' table for logging stock orders and sales
    - Loads customer inquiries from 'quote_requests.csv' into a 'quote_requests' table
    - Loads previous quotes from 'quotes.csv' into a 'quotes' table, extracting useful metadata
    - Generates a random subset of paper inventory using `generate_sample_inventory`
    - Inserts initial financial records including available cash and starting stock levels

    Args:
        db_engine (Engine): A SQLAlchemy engine connected to the SQLite database.
        seed (int, optional): A random seed used to control reproducibility of inventory stock levels.
                              Default is 137.

    Returns:
        Engine: The same SQLAlchemy engine, after initializing all necessary tables and records.

    Raises:
        Exception: If an error occurs during setup, the exception is printed and raised.
    """
    try:
        # ----------------------------
        # 1. Create an empty 'transactions' table schema
        # ----------------------------
        transactions_schema = pd.DataFrame({
            "id": [],
            "item_name": [],
            "transaction_type": [],  # 'stock_orders' or 'sales'
            "units": [],             # Quantity involved
            "price": [],             # Total price for the transaction
            "transaction_date": [],  # ISO-formatted date
        })
        transactions_schema.to_sql("transactions", db_engine, if_exists="replace", index=False)

        # Set a consistent starting date
        initial_date = datetime(2025, 1, 1).isoformat()

        # ----------------------------
        # 2. Load and initialize 'quote_requests' table
        # ----------------------------
        quote_requests_df = pd.read_csv("quote_requests.csv")
        quote_requests_df["id"] = range(1, len(quote_requests_df) + 1)
        quote_requests_df.to_sql("quote_requests", db_engine, if_exists="replace", index=False)

        # ----------------------------
        # 3. Load and transform 'quotes' table
        # ----------------------------
        quotes_df = pd.read_csv("quotes.csv")
        quotes_df["request_id"] = range(1, len(quotes_df) + 1)
        quotes_df["order_date"] = initial_date

        # Unpack metadata fields (job_type, order_size, event_type) if present
        if "request_metadata" in quotes_df.columns:
            quotes_df["request_metadata"] = quotes_df["request_metadata"].apply(
                lambda x: ast.literal_eval(x) if isinstance(x, str) else x
            )
            quotes_df["job_type"] = quotes_df["request_metadata"].apply(lambda x: x.get("job_type", ""))
            quotes_df["order_size"] = quotes_df["request_metadata"].apply(lambda x: x.get("order_size", ""))
            quotes_df["event_type"] = quotes_df["request_metadata"].apply(lambda x: x.get("event_type", ""))

        # Retain only relevant columns
        quotes_df = quotes_df[[
            "request_id",
            "total_amount",
            "quote_explanation",
            "order_date",
            "job_type",
            "order_size",
            "event_type"
        ]]
        quotes_df.to_sql("quotes", db_engine, if_exists="replace", index=False)

        # ----------------------------
        # 4. Generate inventory and seed stock
        # ----------------------------
        inventory_df = generate_sample_inventory(paper_supplies, seed=seed)

        # Seed initial transactions
        initial_transactions = []

        # Add a starting cash balance via a dummy sales transaction
        initial_transactions.append({
            "item_name": None,
            "transaction_type": "sales",
            "units": None,
            "price": 50000.0,
            "transaction_date": initial_date,
        })

        # Add one stock order transaction per inventory item
        for _, item in inventory_df.iterrows():
            initial_transactions.append({
                "item_name": item["item_name"],
                "transaction_type": "stock_orders",
                "units": item["current_stock"],
                "price": item["current_stock"] * item["unit_price"],
                "transaction_date": initial_date,
            })

        # Commit transactions to database
        pd.DataFrame(initial_transactions).to_sql("transactions", db_engine, if_exists="append", index=False)

        # Save the inventory reference table
        inventory_df.to_sql("inventory", db_engine, if_exists="replace", index=False)

        return db_engine

    except Exception as e:
        print(f"Error initializing database: {e}")
        raise

def create_transaction(
    item_name: str,
    transaction_type: str,
    quantity: int,
    price: float,
    date: Union[str, datetime],
) -> int:
    """
    This function records a transaction of type 'stock_orders' or 'sales' with a specified
    item name, quantity, total price, and transaction date into the 'transactions' table of the database.

    Args:
        item_name (str): The name of the item involved in the transaction.
        transaction_type (str): Either 'stock_orders' or 'sales'.
        quantity (int): Number of units involved in the transaction.
        price (float): Total price of the transaction.
        date (str or datetime): Date of the transaction in ISO 8601 format.

    Returns:
        int: The ID of the newly inserted transaction.

    Raises:
        ValueError: If `transaction_type` is not 'stock_orders' or 'sales'.
        Exception: For other database or execution errors.
    """
    try:
        # Convert datetime to ISO string if necessary
        date_str = date.isoformat() if isinstance(date, datetime) else date

        # Validate transaction type
        if transaction_type not in {"stock_orders", "sales"}:
            raise ValueError("Transaction type must be 'stock_orders' or 'sales'")

        # Prepare transaction record as a single-row DataFrame
        transaction = pd.DataFrame([{
            "item_name": item_name,
            "transaction_type": transaction_type,
            "units": quantity,
            "price": price,
            "transaction_date": date_str,
        }])

        # Insert the record into the database
        transaction.to_sql("transactions", db_engine, if_exists="append", index=False)

        # Fetch and return the ID of the inserted row
        result = pd.read_sql("SELECT last_insert_rowid() as id", db_engine)
        return int(result.iloc[0]["id"])

    except Exception as e:
        print(f"Error creating transaction: {e}")
        raise

def get_all_inventory(as_of_date: str) -> Dict[str, int]:
    """
    Retrieve a snapshot of available inventory as of a specific date.

    This function calculates the net quantity of each item by summing 
    all stock orders and subtracting all sales up to and including the given date.

    Only items with positive stock are included in the result.

    Args:
        as_of_date (str): ISO-formatted date string (YYYY-MM-DD) representing the inventory cutoff.

    Returns:
        Dict[str, int]: A dictionary mapping item names to their current stock levels.
    """
    # SQL query to compute stock levels per item as of the given date
    query = """
        SELECT
            item_name,
            SUM(CASE
                WHEN transaction_type = 'stock_orders' THEN units
                WHEN transaction_type = 'sales' THEN -units
                ELSE 0
            END) as stock
        FROM transactions
        WHERE item_name IS NOT NULL
        AND transaction_date <= :as_of_date
        GROUP BY item_name
        HAVING stock > 0
    """

    # Execute the query with the date parameter
    result = pd.read_sql(query, db_engine, params={"as_of_date": as_of_date})

    # Convert the result into a dictionary {item_name: stock}
    return dict(zip(result["item_name"], result["stock"]))

def get_stock_level(item_name: str, as_of_date: Union[str, datetime]) -> pd.DataFrame:
    """
    Retrieve the stock level of a specific item as of a given date.

    This function calculates the net stock by summing all 'stock_orders' and 
    subtracting all 'sales' transactions for the specified item up to the given date.

    Args:
        item_name (str): The name of the item to look up.
        as_of_date (str or datetime): The cutoff date (inclusive) for calculating stock.

    Returns:
        pd.DataFrame: A single-row DataFrame with columns 'item_name' and 'current_stock'.
    """
    # Convert date to ISO string format if it's a datetime object
    if isinstance(as_of_date, datetime):
        as_of_date = as_of_date.isoformat()

    # SQL query to compute net stock level for the item
    stock_query = """
        SELECT
            item_name,
            COALESCE(SUM(CASE
                WHEN transaction_type = 'stock_orders' THEN units
                WHEN transaction_type = 'sales' THEN -units
                ELSE 0
            END), 0) AS current_stock
        FROM transactions
        WHERE item_name = :item_name
        AND transaction_date <= :as_of_date
    """

    # Execute query and return result as a DataFrame
    return pd.read_sql(
        stock_query,
        db_engine,
        params={"item_name": item_name, "as_of_date": as_of_date},
    )

def get_supplier_delivery_date(input_date_str: str, quantity: int) -> str:
    """
    Estimate the supplier delivery date based on the requested order quantity and a starting date.

    Delivery lead time increases with order size:
        - ≤10 units: same day
        - 11–100 units: 1 day
        - 101–1000 units: 4 days
        - >1000 units: 7 days

    Args:
        input_date_str (str): The starting date in ISO format (YYYY-MM-DD).
        quantity (int): The number of units in the order.

    Returns:
        str: Estimated delivery date in ISO format (YYYY-MM-DD).
    """
    # Debug log (comment out in production if needed)
    print(f"FUNC (get_supplier_delivery_date): Calculating for qty {quantity} from date string '{input_date_str}'")

    # Attempt to parse the input date
    try:
        input_date_dt = datetime.fromisoformat(input_date_str.split("T")[0])
    except (ValueError, TypeError):
        # Fallback to current date on format error
        print(f"WARN (get_supplier_delivery_date): Invalid date format '{input_date_str}', using today as base.")
        input_date_dt = datetime.now()

    # Determine delivery delay based on quantity
    if quantity <= 10:
        days = 0
    elif quantity <= 100:
        days = 1
    elif quantity <= 1000:
        days = 4
    else:
        days = 7

    # Add delivery days to the starting date
    delivery_date_dt = input_date_dt + timedelta(days=days)

    # Return formatted delivery date
    return delivery_date_dt.strftime("%Y-%m-%d")

def get_cash_balance(as_of_date: Union[str, datetime]) -> float:
    """
    Calculate the current cash balance as of a specified date.

    The balance is computed by subtracting total stock purchase costs ('stock_orders')
    from total revenue ('sales') recorded in the transactions table up to the given date.

    Args:
        as_of_date (str or datetime): The cutoff date (inclusive) in ISO format or as a datetime object.

    Returns:
        float: Net cash balance as of the given date. Returns 0.0 if no transactions exist or an error occurs.
    """
    try:
        # Convert date to ISO format if it's a datetime object
        if isinstance(as_of_date, datetime):
            as_of_date = as_of_date.isoformat()

        # Query all transactions on or before the specified date
        transactions = pd.read_sql(
            "SELECT * FROM transactions WHERE transaction_date <= :as_of_date",
            db_engine,
            params={"as_of_date": as_of_date},
        )

        # Compute the difference between sales and stock purchases
        if not transactions.empty:
            total_sales = transactions.loc[transactions["transaction_type"] == "sales", "price"].sum()
            total_purchases = transactions.loc[transactions["transaction_type"] == "stock_orders", "price"].sum()
            return float(total_sales - total_purchases)

        return 0.0

    except Exception as e:
        print(f"Error getting cash balance: {e}")
        return 0.0


def generate_financial_report(as_of_date: Union[str, datetime]) -> Dict:
    """
    Generate a complete financial report for the company as of a specific date.

    This includes:
    - Cash balance
    - Inventory valuation
    - Combined asset total
    - Itemized inventory breakdown
    - Top 5 best-selling products

    Args:
        as_of_date (str or datetime): The date (inclusive) for which to generate the report.

    Returns:
        Dict: A dictionary containing the financial report fields:
            - 'as_of_date': The date of the report
            - 'cash_balance': Total cash available
            - 'inventory_value': Total value of inventory
            - 'total_assets': Combined cash and inventory value
            - 'inventory_summary': List of items with stock and valuation details
            - 'top_selling_products': List of top 5 products by revenue
    """
    # Normalize date input
    if isinstance(as_of_date, datetime):
        as_of_date = as_of_date.isoformat()

    # Get current cash balance
    cash = get_cash_balance(as_of_date)

    # Get current inventory snapshot
    inventory_df = pd.read_sql("SELECT * FROM inventory", db_engine)
    inventory_value = 0.0
    inventory_summary = []

    # Compute total inventory value and summary by item
    for _, item in inventory_df.iterrows():
        stock_info = get_stock_level(item["item_name"], as_of_date)
        stock = stock_info["current_stock"].iloc[0]
        item_value = stock * item["unit_price"]
        inventory_value += item_value

        inventory_summary.append({
            "item_name": item["item_name"],
            "stock": stock,
            "unit_price": item["unit_price"],
            "value": item_value,
        })

    # Identify top-selling products by revenue
    top_sales_query = """
        SELECT item_name, SUM(units) as total_units, SUM(price) as total_revenue
        FROM transactions
        WHERE transaction_type = 'sales' AND transaction_date <= :date
        GROUP BY item_name
        ORDER BY total_revenue DESC
        LIMIT 5
    """
    top_sales = pd.read_sql(top_sales_query, db_engine, params={"date": as_of_date})
    top_selling_products = top_sales.to_dict(orient="records")

    return {
        "as_of_date": as_of_date,
        "cash_balance": cash,
        "inventory_value": inventory_value,
        "total_assets": cash + inventory_value,
        "inventory_summary": inventory_summary,
        "top_selling_products": top_selling_products,
    }


def search_quote_history(search_terms: List[str], limit: int = 5) -> List[Dict]:
    """
    Retrieve a list of historical quotes that match any of the provided search terms.

    The function searches both the original customer request (from `quote_requests`) and
    the explanation for the quote (from `quotes`) for each keyword. Results are sorted by
    most recent order date and limited by the `limit` parameter.

    Args:
        search_terms (List[str]): List of terms to match against customer requests and explanations.
        limit (int, optional): Maximum number of quote records to return. Default is 5.

    Returns:
        List[Dict]: A list of matching quotes, each represented as a dictionary with fields:
            - original_request
            - total_amount
            - quote_explanation
            - job_type
            - order_size
            - event_type
            - order_date
    """
    conditions = []
    params = {}

    # Build SQL WHERE clause using LIKE filters for each search term
    for i, term in enumerate(search_terms):
        param_name = f"term_{i}"
        conditions.append(
            f"(LOWER(qr.response) LIKE :{param_name} OR "
            f"LOWER(q.quote_explanation) LIKE :{param_name})"
        )
        params[param_name] = f"%{term.lower()}%"

    # Combine conditions; fallback to always-true if no terms provided
    where_clause = " AND ".join(conditions) if conditions else "1=1"

    # Final SQL query to join quotes with quote_requests
    query = f"""
        SELECT
            qr.response AS original_request,
            q.total_amount,
            q.quote_explanation,
            q.job_type,
            q.order_size,
            q.event_type,
            q.order_date
        FROM quotes q
        JOIN quote_requests qr ON q.request_id = qr.id
        WHERE {where_clause}
        ORDER BY q.order_date DESC
        LIMIT {limit}
    """

    # Execute parameterized query
    with db_engine.connect() as conn:
        result = conn.execute(text(query), params)
        return [dict(row._mapping) for row in result]

########################
########################
########################
# MULTI-AGENT SYSTEM — BEAVER'S CHOICE PAPER COMPANY
########################
########################
########################


dotenv.load_dotenv()
API_KEY = os.getenv("UDACITY_OPENAI_API_KEY")

model = OpenAIServerModel(
    model_id="gpt-4o-mini",
    api_base="https://openai.vocareum.com/v1",
    api_key=API_KEY,
)

# ========================
# Tools for Inventory Agent
# ========================

@tool
def check_paper_inventory(item_name: str = "ALL") -> str:
    """
    Check current stock level for paper products.

    Args:
        item_name: Exact product name to look up, or 'ALL' to list every item in stock.

    Returns:
        Stock level description for the requested item(s).
    """
    today = datetime.now().strftime("%Y-%m-%d")
    if item_name.strip().upper() == "ALL":
        inventory = get_all_inventory(today)
        if not inventory:
            return "No inventory currently available."
        lines = [f"  {item}: {int(qty)} units" for item, qty in sorted(inventory.items())]
        return "Current inventory:\n" + "\n".join(lines)
    result = get_stock_level(item_name, today)
    stock = int(result["current_stock"].iloc[0])
    return f"{item_name}: {stock} units currently in stock."


@tool
def check_reorder_needs(request_date: str) -> str:
    """
    Identify which inventory items are at or below their minimum stock threshold.

    Args:
        request_date: Date in YYYY-MM-DD format used as the inventory snapshot cutoff.

    Returns:
        List of items requiring reorder with current and minimum stock levels,
        or a confirmation that all items are adequately stocked.
    """
    inventory_df = pd.read_sql("SELECT * FROM inventory", db_engine)
    needs_reorder = []
    for _, item in inventory_df.iterrows():
        stock_info = get_stock_level(item["item_name"], request_date)
        current_stock = int(stock_info["current_stock"].iloc[0])
        min_stock = int(item["min_stock_level"])
        if current_stock <= min_stock:
            needs_reorder.append(
                f"  {item['item_name']}: {current_stock} units (min: {min_stock})"
            )
    if not needs_reorder:
        return "All items are adequately stocked. No reorders needed."
    return "Items needing reorder:\n" + "\n".join(needs_reorder)


@tool
def reorder_supplies(item_name: str, quantity: int, request_date: str) -> str:
    """
    Place a supply reorder from the supplier and record the stock_orders transaction.

    Args:
        item_name: Exact name of the paper product to reorder.
        quantity: Number of units to purchase.
        request_date: Date of the reorder in YYYY-MM-DD format.

    Returns:
        Reorder confirmation with total cost and estimated delivery date,
        or an error message if the item is unknown or funds are insufficient.
    """
    inv_df = pd.read_sql(
        "SELECT unit_price FROM inventory WHERE item_name = :item",
        db_engine,
        params={"item": item_name},
    )
    if inv_df.empty:
        item_info = next((p for p in paper_supplies if p["item_name"] == item_name), None)
        if not item_info:
            return f"Error: '{item_name}' is not in our product catalog."
        unit_price = item_info["unit_price"]
    else:
        unit_price = float(inv_df["unit_price"].iloc[0])

    total_cost = unit_price * quantity
    cash = get_cash_balance(request_date)
    if cash < total_cost:
        return (
            f"Insufficient funds. Reorder cost: ${total_cost:.2f}, "
            f"but only ${cash:.2f} available."
        )

    delivery_date = get_supplier_delivery_date(request_date, quantity)
    create_transaction(item_name, "stock_orders", quantity, total_cost, request_date)
    return (
        f"Reorder confirmed: {quantity} units of '{item_name}' "
        f"@ ${unit_price:.4f}/unit = ${total_cost:.2f}. "
        f"Estimated delivery: {delivery_date}."
    )


@tool
def check_delivery_timeline(item_name: str, quantity: int, request_date: str) -> str:
    """
    Return the estimated supplier delivery date for a given item and quantity.

    Args:
        item_name: Name of the paper product.
        quantity: Number of units to be shipped.
        request_date: Starting date for the lead-time calculation (YYYY-MM-DD).

    Returns:
        Human-readable delivery estimate string.
    """
    delivery_date = get_supplier_delivery_date(request_date, quantity)
    return (
        f"Delivery estimate for {quantity} units of '{item_name}': "
        f"expected by {delivery_date}."
    )


@tool
def list_catalog_items(keyword: str = "") -> str:
    """
    Search the full product catalog by keyword to find the exact product name before
    checking inventory or generating a quote.

    Use this whenever a customer request uses natural language (e.g., 'glossy paper',
    'cups', 'cardstock') that may not exactly match a catalog name.

    Args:
        keyword: Partial name or category to search (e.g., 'glossy', 'cardstock',
                 'cups', 'poster'). Pass empty string to list all catalog items.

    Returns:
        Matching product names with categories and unit prices.
    """
    kw = keyword.strip().lower()
    matches = [
        p for p in paper_supplies
        if kw == "" or kw in p["item_name"].lower() or kw in p["category"].lower()
    ]
    if not matches:
        return f"No catalog items found matching '{keyword}'."
    lines = [
        f"  {p['item_name']} ({p['category']}) — ${p['unit_price']:.4f}/unit"
        for p in matches
    ]
    header = f"Catalog items matching '{keyword}':" if kw else "Full product catalog:"
    return header + "\n" + "\n".join(lines)


# ========================
# Tools for Quote Agent
# ========================

@tool
def get_quote_history_tool(search_terms: str) -> str:
    """
    Search historical quotes (from quote_requests.csv + quotes.csv) to inform
    pricing for a new customer request. Use job type, event type, item names, and
    order size as search keywords for the best matches.

    Args:
        search_terms: Comma-separated keywords drawn from the request — include item
                      names, event type, job type, and order size
                      (e.g., 'glossy paper,ceremony,office manager,small').

    Returns:
        Up to five valid historical quotes with totals, job context, and explanations.
        Invalid/error quotes (amount = -1) are excluded automatically.
    """
    terms = [t.strip() for t in search_terms.split(",") if t.strip()]
    # Fetch extra to compensate for filtering out error rows (total_amount == -1)
    raw = search_quote_history(terms, limit=15)
    valid = [q for q in raw if float(q.get("total_amount", -1)) > 0][:5]
    if not valid:
        return "No valid historical quotes found for these search terms."
    lines = []
    for q in valid:
        req = str(q.get("original_request", "N/A"))[:100]
        lines.append(
            f"- Request: {req}\n"
            f"  Amount: ${float(q.get('total_amount', 0)):.2f} | "
            f"Job: {q.get('job_type', 'N/A')} | "
            f"Size: {q.get('order_size', 'N/A')} | "
            f"Event: {q.get('event_type', 'N/A')}\n"
            f"  Explanation: {str(q.get('quote_explanation', ''))[:150]}"
        )
    return "Historical quotes:\n\n" + "\n\n".join(lines)


@tool
def generate_customer_quote(item_name: str, quantity: int, request_date: str) -> str:
    """
    Generate a price quote applying automatic bulk-discount tiers.

    Discount schedule:
      - 5,000+ units  → 20% off  (bulk)
      - 1,000+ units  → 10% off  (wholesale)
      -   500+ units  →  5% off  (volume)
      - Under 500     →  standard pricing

    Args:
        item_name: Exact paper product name from the catalog.
        quantity: Number of units the customer wants to purchase.
        request_date: Date of the quote in YYYY-MM-DD format.

    Returns:
        Detailed quote with unit price, discount tier, total, and availability status.
    """
    inv_df = pd.read_sql(
        "SELECT unit_price FROM inventory WHERE item_name = :item",
        db_engine,
        params={"item": item_name},
    )
    if inv_df.empty:
        item_info = next((p for p in paper_supplies if p["item_name"] == item_name), None)
        if not item_info:
            return f"Item '{item_name}' not found in our product catalog."
        unit_price = item_info["unit_price"]
    else:
        unit_price = float(inv_df["unit_price"].iloc[0])

    if quantity >= 5000:
        discount, tier = 0.20, "bulk (20% off)"
    elif quantity >= 1000:
        discount, tier = 0.10, "wholesale (10% off)"
    elif quantity >= 500:
        discount, tier = 0.05, "volume (5% off)"
    else:
        discount, tier = 0.00, "standard (no discount)"

    final_price = unit_price * (1 - discount)
    total = final_price * quantity

    stock_info = get_stock_level(item_name, request_date)
    current_stock = int(stock_info["current_stock"].iloc[0])
    if current_stock >= quantity:
        availability = f"In stock ({current_stock} available)"
    else:
        availability = (
            f"Partial stock ({current_stock} available; "
            f"{quantity - current_stock} on backorder)"
        )

    return (
        f"Quote ({request_date}):\n"
        f"  Item:                {item_name}\n"
        f"  Quantity:            {quantity:,} units\n"
        f"  Standard unit price: ${unit_price:.4f}\n"
        f"  Discount tier:       {tier}\n"
        f"  Final unit price:    ${final_price:.4f}\n"
        f"  Quote total:         ${total:,.2f}\n"
        f"  Availability:        {availability}"
    )


# ========================
# Tools for Sales Agent
# ========================

@tool
def check_cash_balance_tool(as_of_date: str) -> str:
    """
    Check the company's current cash balance.

    Args:
        as_of_date: Date in YYYY-MM-DD format.

    Returns:
        Cash balance formatted as a string.
    """
    balance = get_cash_balance(as_of_date)
    return f"Cash balance as of {as_of_date}: ${balance:,.2f}"


@tool
def fulfill_sale(
    item_name: str, quantity: int, unit_price: float, sale_date: str
) -> str:
    """
    Finalize a sale: verify available stock, record the revenue transaction, confirm completion.

    Args:
        item_name: Paper product being sold.
        quantity: Number of units to sell.
        unit_price: Agreed price per unit for this transaction (apply any discounts before calling).
        sale_date: Date of the sale in YYYY-MM-DD format.

    Returns:
        Sale confirmation with transaction ID and remaining stock,
        or an error if inventory is insufficient.
    """
    stock_info = get_stock_level(item_name, sale_date)
    current_stock = int(stock_info["current_stock"].iloc[0])
    if current_stock < quantity:
        return (
            f"Sale failed: only {current_stock} units of '{item_name}' in stock, "
            f"but {quantity} were requested."
        )
    total_price = unit_price * quantity
    transaction_id = create_transaction(item_name, "sales", quantity, total_price, sale_date)
    remaining = current_stock - quantity
    return (
        f"Sale confirmed (Transaction #{transaction_id}):\n"
        f"  Item:            {item_name}\n"
        f"  Quantity sold:   {quantity:,} units\n"
        f"  Unit price:      ${unit_price:.4f}\n"
        f"  Revenue:         ${total_price:,.2f}\n"
        f"  Remaining stock: {remaining:,} units"
    )


@tool
def generate_global_report(as_of_date: str) -> str:
    """
    Generate a full financial and inventory report for the company.

    Args:
        as_of_date: Report cutoff date in YYYY-MM-DD format.

    Returns:
        Formatted summary including cash balance, inventory value, total assets,
        and the top-five best-selling products.
    """
    report = generate_financial_report(as_of_date)
    lines = [
        f"=== Global Report: {as_of_date} ===",
        f"Cash balance:    ${report['cash_balance']:>12,.2f}",
        f"Inventory value: ${report['inventory_value']:>12,.2f}",
        f"Total assets:    ${report['total_assets']:>12,.2f}",
    ]
    if report["top_selling_products"]:
        lines.append("\nTop Selling Products:")
        for p in report["top_selling_products"]:
            if p.get("item_name"):
                lines.append(
                    f"  {p['item_name']}: "
                    f"{int(p.get('total_units', 0))} units "
                    f"(${float(p.get('total_revenue', 0)):,.2f})"
                )
    return "\n".join(lines)


# ========================
# Response Post-Processing
# ========================

_MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
_MONTH_PAT = "|".join(_MONTH_NAMES)


def _sanitize_response(response: str, request_date: str) -> str:
    """
    Deterministic post-processing applied to every customer-facing response:

    1. Replace any bracket-enclosed template tokens (e.g. [insert estimated restock date])
       with a generic customer-safe fallback — LLM prompt guards alone are not reliable.

    2. Replace delivery/restock dates that predate the request date with a recalculated
       estimate (7-day lead time from request_date) so customers never receive a date in
       the past.
    """
    # --- Issue 1: unfilled template tokens ---
    response = re.sub(
        r"\[[^\]]+\]",
        "currently unavailable — please contact us for an update",
        response,
    )

    # --- Issue 2: stale past-dated delivery/restock dates ---
    try:
        req_dt = datetime.strptime(request_date, "%Y-%m-%d")
    except ValueError:
        return response  # can't validate without a parseable request date

    # Default fallback: 7-day lead time (>1 000-unit tier in get_supplier_delivery_date)
    fallback_dt = req_dt + timedelta(days=7)
    fallback_iso = fallback_dt.strftime("%Y-%m-%d")
    fallback_written = (
        fallback_dt.strftime("%B") + " " + str(fallback_dt.day) + ", " + str(fallback_dt.year)
    )

    def _fix_iso(m: re.Match) -> str:
        try:
            if datetime.strptime(m.group(), "%Y-%m-%d") < req_dt:
                return fallback_iso
        except ValueError:
            pass
        return m.group()

    response = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", _fix_iso, response)

    def _fix_written(m: re.Match) -> str:
        raw = m.group()
        for fmt in ("%B %d, %Y", "%B %d %Y"):
            try:
                if datetime.strptime(raw, fmt) < req_dt:
                    return fallback_written
                return raw
            except ValueError:
                continue
        return raw

    response = re.sub(
        rf"\b(?:{_MONTH_PAT})\s+\d{{1,2}},?\s+\d{{4}}\b",
        _fix_written,
        response,
    )

    return response


# ========================
# Agent Definitions
# ========================

class InventoryAgent(ToolCallingAgent):
    """Manages stock queries, low-stock detection, and supply reordering."""

    def __init__(self, model):
        super().__init__(
            tools=[
                list_catalog_items,
                check_paper_inventory,
                check_reorder_needs,
                reorder_supplies,
                check_delivery_timeline,
            ],
            model=model,
            name="inventory_agent",
            description=(
                "Handles all inventory-related tasks: checking stock levels, "
                "identifying items below minimum threshold, placing reorder transactions, "
                "and providing supplier delivery timelines. "
                "Use list_catalog_items first to find the exact product name when "
                "a request uses natural language item descriptions."
            ),
        )


class QuoteAgent(ToolCallingAgent):
    """Generates accurate price quotes informed by history and bulk-discount rules."""

    def __init__(self, model):
        super().__init__(
            tools=[
                list_catalog_items,
                get_quote_history_tool,
                generate_customer_quote,
                check_paper_inventory,
            ],
            model=model,
            name="quote_agent",
            description=(
                "Generates price quotes for customers. Workflow: "
                "(1) use list_catalog_items to map natural language item names to exact catalog names, "
                "(2) use get_quote_history_tool with item names + event type + job type as keywords "
                "to find comparable historical quotes from quote_requests.csv / quotes.csv, "
                "(3) use generate_customer_quote for EVERY requested item — never skip an item, "
                "(4) check availability with check_paper_inventory. "
                "Output rules: "
                "Every item must receive a definitive response — either a quoted price or a clear "
                "out-of-stock / not-in-catalog notice. 'Quote pending' is not acceptable. "
                "For each item show: item name, quantity, standard unit price, discount tier and "
                "percentage applied (e.g. 'wholesale — 10% off'), discounted unit price, and line "
                "total. Finish with a grand total. "
                "If an item is not in our catalog, state that explicitly and suggest the closest "
                "available alternative by name. "
                "Do not include placeholder text such as [Customer], [Your Name], [Your Position], "
                "or any other unfilled template tokens in the response."
            ),
        )


class SalesAgent(ToolCallingAgent):
    """Finalizes sales, tracks cash, and produces financial reports."""

    def __init__(self, model):
        super().__init__(
            tools=[
                fulfill_sale,
                check_cash_balance_tool,
                check_delivery_timeline,
                generate_global_report,
                check_paper_inventory,
            ],
            model=model,
            name="sales_agent",
            description=(
                "Finalizes sales transactions by verifying inventory and recording revenue. "
                "Provides cash-balance lookups, delivery timelines, and full financial reports."
            ),
        )


# ========================
# Orchestrator
# ========================

class Orchestrator(ToolCallingAgent):
    """Master orchestrator for Beaver's Choice Paper Company."""

    def __init__(self, model):
        self.model = model
        self.inventory_agent = InventoryAgent(model)
        self.quote_agent = QuoteAgent(model)
        self.sales_agent = SalesAgent(model)

        @tool
        def handle_inventory_request(request: str) -> str:
            """
            Delegate an inventory-related task to the inventory agent.

            Args:
                request: Full description of the task, including item names, quantities,
                         and dates where relevant (e.g., 'Check stock for A4 paper as of 2025-03-15').

            Returns:
                Result from the inventory agent.
            """
            return self.inventory_agent.run(request)

        @tool
        def handle_quote_request(request: str) -> str:
            """
            Delegate a pricing or quote task to the quote agent.

            Args:
                request: Customer request including product name, quantity, date,
                         and any relevant context such as event type or job size.

            Returns:
                Detailed price quote from the quote agent.
            """
            return self.quote_agent.run(request)

        @tool
        def handle_sales_request(request: str) -> str:
            """
            Delegate an order-finalization task to the sales agent.

            Args:
                request: Order details including item name, quantity, agreed unit price,
                         and sale date.

            Returns:
                Sale confirmation or error message from the sales agent.
            """
            return self.sales_agent.run(request)

        super().__init__(
            tools=[handle_inventory_request, handle_quote_request, handle_sales_request],
            model=model,
            name="orchestrator",
            description="""
            You are the orchestrator for Beaver's Choice Paper Company.
            Route each incoming request to the appropriate specialized agent:

            - Inventory questions (stock levels, low-stock alerts, reorders, delivery times)
              → handle_inventory_request
            - Pricing or quote requests (bulk discounts, availability, historical context)
              → handle_quote_request
            - Confirmed purchases / order finalization
              → handle_sales_request
            - Multi-step requests (e.g., "get a quote and place the order")
              → call both handle_quote_request then handle_sales_request in sequence.

            STRICT OUTPUT RULES — apply to every response before returning it:
            1. No template tokens: never include [Customer], [Your Name], [Your Position],
               [Manufacturer's Name], or any other unfilled placeholder in the final response.
               If the sub-agent returns such tokens, replace them with appropriate text or remove them.
            2. No internal financials: if an order cannot be fulfilled due to insufficient stock,
               say only that the item is currently unavailable or out of stock and offer alternatives
               or a reorder timeline. Never mention cash balance, funding constraints, or internal
               cost figures as reasons for declining a customer order.
            3. Every item gets a definitive answer: for each line item in the request, the response
               must include either a quoted price with breakdown or a clear explanation of why it
               cannot be quoted (not in catalog, out of stock). Never leave an item as 'pending'
               without stating what information is missing and when the customer can expect follow-up.
            4. Discount rationale required: whenever a discount is applied, state the tier name,
               the percentage, and the resulting unit price so the customer understands the pricing.
            """,
        )

    def handle_request(
        self,
        customer_request: str,
        event_type: str = "",
        order_size: str = "",
        job_type: str = "",
        request_date: str = "",
    ) -> str:
        """
        Process a customer or operator request through the multi-agent system.

        Args:
            customer_request: Free-text request from a customer or internal operator.
            event_type: Event context from quote_requests_sample.csv (e.g. 'ceremony').
            order_size: Order-size category from the sample data ('small'/'medium'/'large').
            job_type: Customer's job title (e.g. 'office manager', 'hotel manager').
            request_date: ISO date string (YYYY-MM-DD) used to validate delivery dates
                          and anchor fallback estimates. Defaults to today if omitted.

        Returns:
            Final response after coordinating the appropriate specialized agents.
        """
        context_parts = []
        if job_type:
            context_parts.append(f"Customer job: {job_type}")
        if event_type:
            context_parts.append(f"Event type: {event_type}")
        if order_size:
            context_parts.append(f"Order size: {order_size}")
        context_line = " | ".join(context_parts)

        raw_response = self.run(
            f"""Customer request: "{customer_request}"
{f'Context — {context_line}' if context_line else ''}

Routing instructions:
1. Stock / inventory queries or reorder decisions → handle_inventory_request
2. Price quotes (most requests fall here):
   → handle_quote_request
   Pass event_type="{event_type}", order_size="{order_size}", job_type="{job_type}"
   as keywords alongside item names when calling get_quote_history_tool so it finds
   the most relevant rows from the historical quotes DB.
3. Confirmed purchase / order finalisation → handle_sales_request
4. Multi-step (quote then buy): call handle_quote_request then handle_sales_request.

Before returning the final response, apply ALL of the following checks:
- Remove any unfilled template tokens ([Customer], [Your Name], [Your Position],
  [Manufacturer's Name], etc.). Replace generic salutations with "Dear valued customer"
  and sign off as "Beaver's Choice Paper Company".
- Do NOT mention cash balance, funding issues, or internal financial constraints as
  reasons for declining or modifying an order. If stock is unavailable, say the item
  is currently out of stock and provide an estimated restock date via check_delivery_timeline.
- Every item in the request must have a definitive quoted price OR a clear explanation
  (not in catalog → name the closest alternative; out of stock → give reorder timeline).
  Never leave any item with a vague status like "Quote pending" alone.
- Whenever a discount is applied, include the tier name, percentage, standard unit
  price, and discounted unit price so the customer can see exactly how the total was reached.
"""
        )
        # Deterministic post-processing: fix template tokens and stale dates that
        # LLM prompt guards may have missed.
        sanitize_date = request_date or datetime.now().strftime("%Y-%m-%d")
        return _sanitize_response(raw_response, sanitize_date)


# ========================
# Test Scenarios
# ========================

def run_test_scenarios():
    print("Initializing Database...")
    init_database(db_engine)

    try:
        quote_requests_sample = pd.read_csv("quote_requests_sample.csv")
        quote_requests_sample["request_date"] = pd.to_datetime(
            quote_requests_sample["request_date"], format="%m/%d/%y", errors="coerce"
        )
        quote_requests_sample.dropna(subset=["request_date"], inplace=True)
        quote_requests_sample = quote_requests_sample.sort_values("request_date")
    except Exception as e:
        print(f"FATAL: Error loading test data: {e}")
        return

    initial_date = quote_requests_sample["request_date"].min().strftime("%Y-%m-%d")
    report = generate_financial_report(initial_date)
    current_cash = report["cash_balance"]
    current_inventory = report["inventory_value"]

    print("Initializing multi-agent system...")
    orchestrator = Orchestrator(model)

    results = []
    for idx, row in quote_requests_sample.iterrows():
        request_date = row["request_date"].strftime("%Y-%m-%d")

        print(f"\n=== Request {idx + 1} ===")
        print(f"Context: {row['job']} organizing {row['event']}")
        print(f"Request Date: {request_date}")
        print(f"Cash Balance: ${current_cash:.2f}")
        print(f"Inventory Value: ${current_inventory:.2f}")

        # quote_requests_sample.csv columns: job, need_size, event, request, request_date
        request_with_date = f"{row['request']} (Date of request: {request_date})"

        try:
            response = orchestrator.handle_request(
                customer_request=request_with_date,
                event_type=str(row.get("event", "")),
                order_size=str(row.get("need_size", "")),
                job_type=str(row.get("job", "")),
                request_date=request_date,
            )
        except Exception as e:
            response = f"Error processing request: {e}"

        report = generate_financial_report(request_date)
        current_cash = report["cash_balance"]
        current_inventory = report["inventory_value"]

        print(f"Response: {response}")
        print(f"Updated Cash: ${current_cash:.2f}")
        print(f"Updated Inventory: ${current_inventory:.2f}")

        results.append(
            {
                "request_id": idx + 1,
                "request_date": request_date,
                "cash_balance": current_cash,
                "inventory_value": current_inventory,
                "response": response,
            }
        )

        time.sleep(1)

    final_date = quote_requests_sample["request_date"].max().strftime("%Y-%m-%d")
    final_report = generate_financial_report(final_date)
    print("\n===== FINAL FINANCIAL REPORT =====")
    print(f"Final Cash: ${final_report['cash_balance']:.2f}")
    print(f"Final Inventory: ${final_report['inventory_value']:.2f}")

    pd.DataFrame(results).to_csv("test_results.csv", index=False)
    return results


if __name__ == "__main__":
    results = run_test_scenarios()
