from dataclasses import dataclass, field
from typing import List
from collections import defaultdict
from ai_client import get_recomended_product, generate_push_notification
import pandas as pd
from typing import Optional
from profits import calculate_profit_for_client_by_product
from deposit import choose_deposit_product
from csv_save import save_push_notifications

# ---------- Models ----------
@dataclass
class Transaction:
    client_code: int
    name: str
    status: str
    city: str
    date: str
    category: str
    amount: float
    currency: str
    product: Optional[str] = None

@dataclass
class Transfer:
    client_code: int
    name: str
    status: str
    city: str
    date: str
    type: str
    direction: str
    amount: float
    currency: str
    product: Optional[str] = None

@dataclass
class Client:
    client_code: int
    name: str
    status: str
    age: int
    city: str
    avg_monthly_balance_KZT: int
    transactions: List[Transaction]
    transfers: List[Transfer]
    total_transfers_in: float = 0.0
    total_transfers_out: float = 0.0
    total_transfers: float = 0.0
    total_transactions: float = 0.0
    available_balance: float = 0.0
    max_potential_profit: float = 0.0
    product: Optional[str] = None


def build_clients(clients_df: pd.DataFrame, transactions_df: pd.DataFrame, transfers_df: pd.DataFrame) -> list[Client]:
    clients: list[Client] = []

    # Standardize columns
    transactions_df = transactions_df.rename(columns={"products": "product"})
    transactions_df = transactions_df.drop(columns=["products"], errors="ignore")  # in case both existed
    for _, row in clients_df.iterrows():
        code = row["client_code"]

    # Transactions

        if "product" not in transactions_df.columns:
            transactions_df["product"] = None 

        client_transactions = [
            Transaction(**t.to_dict())
            for _, t in transactions_df[transactions_df["client_code"] == code].iterrows()
        ]

        if "product" not in transfers_df.columns:
            transfers_df["product"] = None 
    # Transfers
        client_transfers = [
            Transfer(**tr.to_dict())
            for _, tr in transfers_df[transfers_df["client_code"] == code].iterrows()
        ]

    # Group sums
        totals_by_category = defaultdict(float)
        for tx in client_transactions:
            totals_by_category[tx.category] += tx.amount

        totals_by_transfer = defaultdict(float)
        for tr in client_transfers:
            key = f"{tr.type}_{tr.direction}"
            totals_by_transfer[key] += tr.amount

    # Create client object
        client = Client(
            client_code=row["client_code"],
            name=row["name"],
            status=row["status"],
            age=row["age"],
            city=row["city"],
            avg_monthly_balance_KZT=row["avg_monthly_balance_KZT"],
            transactions=client_transactions,
            transfers=client_transfers,
        )

    # Attach summaries (optional: as attributes)
        client.totals_by_category = dict(totals_by_category)
        client.totals_by_transfer = dict(totals_by_transfer)
        clients.append(client)   # ✅ append instead of overwrite

    return clients



def handle_clients_logic(clients_df, transactions_df, transfers_df):
    clients = build_clients(clients_df, transactions_df, transfers_df)

    clients = calculations(transactions_df, transfers_df, clients)
    result = []
    for client in clients:
        
        print(f"\nClient: {client.name}, client_code: {client.client_code}, Age: {client.age}, City: {client.city}, Avg Balance: {client.avg_monthly_balance_KZT}₸")
        best_product = choose_best_product(client, transfers_df)
        push_notification = generate_push_notification(
                name=client.name,
                age=client.age,
                profit=client.max_potential_profit,
                product_type=best_product)

        result.append((client.client_code, best_product, push_notification))
    
    save_push_notifications(result)
    # print_comparison_report(clients, "result.csv")


def choose_best_product(client: Client, transfers_df) -> str:
    
    # 1) Check transfers for related products
        # mapping: продукт -> связанные типы переводов
    best_product, score = recommend_product_by_transfers(
        transfers_df[transfers_df["client_code"] == client.client_code],
        product_transfer_map
    )

    if best_product is not None:
        print(f"Client {client.client_code} - Recommended by Transfers Logic: {best_product} (Score: {score})")
        return best_product

    deposits_info = choose_deposit_product(client)
    if deposits_info["product"] is not None and deposits_info["confidence"] >= 0.8:
        print(f"Client {client.client_code} - Recommended by Deposit Logic: {deposits_info['product']} (Confidence: {deposits_info['confidence']})")
        return deposits_info["product"]
    
    if client.product is not None:
        print(f"Client {client.client_code} - Recommended by Transaction Logic: {client.product} (Potential Profit: {client.max_potential_profit}₸)")
        return client.product

    ai_product, accuracy = get_recomended_product(client)

    print(f"Client {client.client_code} - Recommended by AI: {ai_product} (Accuracy: {accuracy})")
    return ai_product

def calculations(transactions_df, transfers_df, clients):
    # GROUP TRANSACTIONS
    grouped_transactions = (
        transactions_df
        .groupby(["client_code", "category"])["amount"]
        .sum()
        .reset_index()
        .sort_values(by="amount", ascending=False)
    )
    grouped_transactions = grouped_transactions.sort_values(
        by=["client_code", "amount"], ascending=[True, False]
    )

    spent_categories_per_client = grouped_transactions.groupby("client_code").head(10000)
    clients = group_category_product(spent_categories_per_client, clients)

    transactions_total_dict = dict(
        transactions_df.groupby("client_code")["amount"].sum()
    )

    # Calculate total in/out transfers per client
    transfer_direction_sums = (
        transfers_df
        .groupby(["client_code", "direction"])["amount"]
        .sum()
        .unstack(fill_value=0)  # makes columns 'in', 'out'
        .reset_index()
    )

    # Calculate total in/out transfers per client
    transfer_types_sums = (
        transfers_df
        .groupby(["client_code", "type"])["amount"]
        .sum()
        .unstack(fill_value=0)  # makes columns 'in', 'out'
        .reset_index()
    )


    clients = group_transfers_by_type(transfers_df, clients)

    in_totals = dict(zip(transfer_direction_sums["client_code"], transfer_direction_sums.get("in", 0)))
    out_totals = dict(zip(transfer_direction_sums["client_code"], transfer_direction_sums.get("out", 0)))

    # Attach calculated fields to clients
    for client in clients:
        client.total_transfers_in = in_totals.get(client.client_code, 0.0)
        client.total_transfers_out = out_totals.get(client.client_code, 0.0)
        client.total_transfers = client.total_transfers_in + client.total_transfers_out
        client.total_transactions = transactions_total_dict.get(client.client_code, 0.0)



    return clients

# mapping: продукт -> связанные типы переводов
product_transfer_map = {
   "Обмен валют": ["fx_buy", "fx_sell"],
   "Инвестиции": ["invest_out", "invest_in"],
   "Золотые слитки": ["gold_buy_out", "gold_sell_in"]
}

def recommend_product_by_transfers(client_transfers, product_map):

    scores = {product: 0 for product in product_map}

    for _, tr in client_transfers.iterrows():
        tr_type = tr["type"]
        tr_amount = tr["amount"]
        for product, related_types in product_map.items():
            if tr_type in related_types:
                # можно учитывать не только факт операции, но и её сумму
                scores[product] += tr_amount

    # выбрать продукт с максимальным "весом"
    if max(scores.values()) == 0:
        return None, 0 # нет подходящего продукта

    best_product = max(scores, key=scores.get)
    return best_product, scores[best_product]


PRODUCT_CATEGORIES = {
    "Карта для путешествий": ["Путешествия", "Отели", "Такси"],
    "Кредитная карта": ["Едим дома", "Смотрим дома", "Играем дома"],
    "Премиальная карта": ["Ювелирные изделия", "Косметика и Парфюмерия", "Кафе и рестораны",],
    "Депозит Накопительный":[],
    "Депозит Мультивалютный": [],
    "Депозит Сберегательный": [],
    "Золотые слитки": [],
    "Инвестиции": [],
    "Обмен валют": [],
    "Кредит наличными": [],
    "Другое": []
}


def get_dynamic_threshold(client: Client, product: str) -> float:
    base = {
        "Премиальная карта": 0.30,
        "Кредитная карта":   0.26,
        "Карта для путешествий": 0.26,
    }
    thr = base.get(product, 0.0)

    if product == "Премиальная карта":
        if client.avg_monthly_balance_KZT >= 1_500_000 or client.status == "Премиальный клиент":
            thr -= 0.10
        if client.status == "Студент":
            thr += 0.10

    if product == "Кредитная карта":
        if client.age < 25:
            thr -= 0.05
        if any(tr.type in ("installment_payment_out", "cc_repayment_out") for tr in client.transfers):
            thr -= 0.05

    if product == "Карта для путешествий":
        travel_cats = set(PRODUCT_CATEGORIES["Карта для путешествий"])
        travel_spend = sum(tx.amount for tx in client.transactions if tx.category in travel_cats)
        if travel_spend >= 400_000:
            thr -= 0.10
        if client.status == 'обычный':
            thr += 0.15


    return max(min(thr, 0.9), 0.05)  # защита от экстремумов

# --- 3) Сервисные функции подсчета доли ---
def _build_cat_to_product() -> dict:
    cat_to_product = {}
    for prod, cats in PRODUCT_CATEGORIES.items():
        for c in cats:
            cat_to_product[c] = prod
    return cat_to_product

def _share_by_product_for_client(df_client: pd.DataFrame, product: str) -> float:
    """Доля трат клиента в категориях, релевантных product."""
    cats = set(PRODUCT_CATEGORIES.get(product, []))
    total = df_client["amount"].sum()
    if total <= 0:
        return 0.0
    relevant = df_client[df_client["category"].isin(cats)]["amount"].sum()
    return float(relevant) / float(total)

# --- 4) Основная функция выбора продукта с учётом динамического порога ---
def group_category_product(spent_categories_per_client: pd.DataFrame, clients: list[Client]):
    cat_to_product = _build_cat_to_product()
    df = spent_categories_per_client.copy()
    df["product"] = df["category"].map(cat_to_product).fillna("Другое")

    grouped = (
        df.groupby(["client_code", "product"], as_index=False)["amount"]
          .sum()
          .sort_values(["client_code", "amount"], ascending=[True, False])
    )

    # быстрое разбиение по клиентам
    df_by_client = {cid: g.drop(columns=["product"]) for cid, g in df.groupby("client_code")}

    for client_code, group in grouped.groupby("client_code"):
        client = clients[client_code - 1]
        df_client = df_by_client.get(client_code, df.iloc[0:0])

        max_profit = 0.0
        max_product = None

        for row in group.itertuples():
            product = row.product

            # если продукт из «процентных» — проверяем долю против динамического порога
            if product in ("Премиальная карта", "Кредитная карта", "Карта для путешествий"):
                share = _share_by_product_for_client(df_client, product)
                thr = get_dynamic_threshold(client, product)
                if share < thr:
                    continue

            profit = calculate_profit_for_client_by_product(client, product)
            if profit > max_profit:
                max_profit = profit
                max_product = product
        client.max_potential_profit = max_profit
        client.product = max_product


    return clients


def group_transfers_by_type(
    transfers_df: pd.DataFrame,
    clients,
) -> List[Client]:
    """
    Aggregates transfers by type and direction, sets per-client totals and dicts:
      - client.transfer_sums_by_type:        {"salary_in": 100000, "card_out": 25000, ...}
      - client.transfer_sums_by_direction:   {"in": 120000, "out": 50000}
      - client.transfer_sums_by_direction_type: {"in": {"salary_in": ...}, "out": {"card_out": ...}}
      - client.total_transfers_in / _out / _total
    Optionally normalizes amounts to base_currency using `currency_rates`.
    """
    if transfers_df.empty or not len(clients):
        return clients

    df = transfers_df.copy()

    # Build quick lookup for clients
    clients_by_code = {c.client_code: c for c in clients}

    # 1) sums by type (direction-agnostic)
    by_type = (
        df.groupby(["client_code", "type"])["amount"]
          .sum()
          .unstack(fill_value=0.0)
    )  # index: client_code, columns: type


    # 3) sums by direction × type (nice for fine-grained inspection)
    by_dir_type = pd.pivot_table(
        df,
        index="client_code",
        columns=["direction", "type"],
        values="amount",
        aggfunc="sum",
        fill_value=0.0,
    )  # columns: MultiIndex (direction, type)

    # Write back into clients
    for code, client in clients_by_code.items():
        # by type
        if code in by_type.index:
            client.transfer_sums_by_type = {k: float(v) for k, v in by_type.loc[code].to_dict().items()}
        else:
            client.transfer_sums_by_type = {}

        # by direction × type
        if code in by_dir_type.index:
            # convert to nested dict {"in": {type: sum}, "out": {type: sum}}
            nested = {}
            row = by_dir_type.loc[code]
            # row is a Series indexed by MultiIndex (direction, type)
            for (direction, ttype), val in row.items():
                nested.setdefault(direction, {})[ttype] = float(val)
            client.transfer_sums_by_direction_type = nested
        else:
            client.transfer_sums_by_direction_type = {}

    return clients


import csv
from typing import Dict, List, Tuple, Optional

# --- helpers ---
def normalize(s: Optional[str]) -> str:
    return (s or "").strip().lower()

def load_csv_products(filename: str = "result.csv") -> Dict[int, str]:
    """
    Reads result.csv with columns: client_code, product, push_notification
    and returns {client_code: product}.
    """
    mapping: Dict[int, str] = {}
    with open(filename, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # client_code may be str in CSV; cast to int if possible
            try:
                code = int(row["client_code"])
            except (ValueError, KeyError):
                # skip malformed row
                continue
            mapping[code] = row.get("product", "")
    return mapping

def compare_csv_to_first_tx(clients: List[Client],
                            csv_map: Dict[int, str]) -> List[Tuple[int, str, str]]:
    """
    Compares CSV product vs client's first transaction's product.
    Returns a list of mismatches: [(client_code, csv_product, first_tx_product), ...]
    """
    mismatches = []
    for c in clients:
        if not c.transactions:
            # No transactions to compare; skip or treat as mismatch if you prefer
            continue
        first_tx_product = c.transactions[0].product  # as requested: strictly first item
        csv_prod = csv_map.get(c.client_code)

        # only compare if we actually have a CSV entry
        if csv_prod is None:
            # you can log missing CSV rows if useful
            # print(f"[Missing CSV] client_code={c.client_code}")
            continue

        if normalize(csv_prod) != normalize(first_tx_product):
            mismatches.append((c.client_code, csv_prod, first_tx_product))
    return mismatches

def print_comparison_report(clients: List[Client], csv_file: str = "result.csv") -> None:
    csv_map = load_csv_products(csv_file)
    mismatches = compare_csv_to_first_tx(clients, csv_map)

    total = len([c for c in clients if c.client_code in csv_map])
    print(f"Compared {total} clients found in CSV.")
    if not mismatches:
        print("✅ No mismatches: CSV product matches clients' first transaction product.")
        return

    print("❗Mismatches found:")
    for code, csv_prod, tx_prod in mismatches:
        print(f"- client_code={code}: csv='{csv_prod}' vs first_tx='{tx_prod}'")