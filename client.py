from dataclasses import dataclass, field
from typing import List
from collections import defaultdict
from ai_client import get_recomended_product, generate_push_notification
import pandas as pd
from typing import Optional
from profits import calculate_profit_for_client_by_product
from deposit import pick_deposit_product_for_client
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

    # return
    for client in clients:
        
        client = pick_deposit_product_for_client(client)
        print(f"Client {client.client_code} assigned product: {client.product}, potential profit: {client.max_potential_profit}₸, deposit confidence: {client.deposit_selection_confidence:.2f}")
        continue
        best_product = choose_best_product(client, transfers_df)
        print(f"\nClient: {client.name}, client_code: {client.client_code}, Age: {client.age}, City: {client.city}, Avg Balance: {client.avg_monthly_balance_KZT}₸, Product: {best_product}")
        
        profit = calculate_profit_for_client_by_product(client, best_product)
        
        push_notification = generate_push_notification(
                name=client.name,
                age=client.age,
                profit=profit,
                product_type=best_product)

        # TODO save push to csv file with format: client_code, product, push_notification
        print(f"Push notification for {client.name}:\n{push_notification}\n")

def choose_best_product(client: Client, transfers_df) -> str:
    # 1) Check transfers for related products
        # mapping: продукт -> связанные типы переводов
    best_product, score = recommend_product_by_transfers(
        transfers_df[transfers_df["client_code"] == client.client_code],
        product_transfer_map
    )

    if best_product is not None:
        return best_product

    

    recomended_product, accuracy = get_recomended_product(client)
    if accuracy >= 8:
        return recomended_product

    return client.product if client.product else "Другое"

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

    spent_categories_per_client = grouped_transactions.groupby("client_code").head(100)
    clients = group_category_product(spent_categories_per_client, clients)

    transactions_total_dict = dict(
        transactions_df.groupby("client_code")["amount"].sum()
    )

    # Calculate total in/out transfers per client
    transfer_sums = (
        transfers_df
        .groupby(["client_code", "direction"])["amount"]
        .sum()
        .unstack(fill_value=0)  # makes columns 'in', 'out'
        .reset_index()
    )

    in_totals = dict(zip(transfer_sums["client_code"], transfer_sums.get("in", 0)))
    out_totals = dict(zip(transfer_sums["client_code"], transfer_sums.get("out", 0)))

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

def group_category_product(spent_categories_per_client: pd.DataFrame, clients):

    # строим обратный словарь: category → product
    cat_to_product = {}
    for product, cats in PRODUCT_CATEGORIES.items():
        for c in cats:
            cat_to_product[c] = product

    df = spent_categories_per_client.copy()
    df["product"] = df["category"].map(cat_to_product)

    grouped = (
        df.groupby(["client_code", "product"], as_index=False)["amount"]
        .sum()
        .sort_values(["client_code", "amount"], ascending=[True, False])
    )

    for client_code, group in grouped.groupby("client_code"):
        max_profit = 0.0
        max_product = None

        for row in group.itertuples():
            product = row.product
            profit = calculate_profit_for_client_by_product(clients[client_code-1], product)
            print(f"Client {client_code} - Product: {product}, MaxProduct: {max_product}, OldProfit: {max_profit}₸, NewProfit: {profit:.2f}₸")
            if profit > max_profit:
                max_profit = profit
                max_product = product

        clients[client_code-1].max_potential_profit = max_profit
        clients[client_code-1].product = max_product
        print(f"Client {client_code} - Recommended Product: {max_product}, Potential Profit: {max_profit}₸, GROUPED DATA:\n{group}\n")

    return clients
