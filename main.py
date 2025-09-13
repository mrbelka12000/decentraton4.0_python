import argparse
from pathlib import Path
import pandas as pd
from dataclasses import dataclass
from typing import List
from collections import defaultdict
from client import answer

# ---------- Models ----------
@dataclass
class Transaction:
    client_code: int
    name: str
    product: str
    status: str
    city: str
    date: str
    category: str
    amount: float
    currency: str

@dataclass
class Transfer:
    client_code: int
    name: str
    product: str
    status: str
    city: str
    date: str
    type: str
    direction: str
    amount: float
    currency: str

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
    total_transactions: float = 0.0
    top4_categories: List[dict] = None
    available_balance: float = 0.0


def read_many_csv(files: list[Path]) -> pd.DataFrame:
    """Concat many CSVs safely; return empty DF if none."""
    frames = []
    for f in files:
        df = pd.read_csv(f)
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def load_data(base_path: Path):
    # 1) Validate directories/files
    if not base_path.exists():
        raise FileNotFoundError(f"Folder not found: {base_path}")

    # clients_csv = base_path / "clients.csv"
    # if not clients_csv.exists():
    #     # Try to locate it anywhere under base_path as a fallback
    #     candidates = list(base_path.rglob("clients.csv"))
    #     if not candidates:
    #         raise FileNotFoundError(f"clients.csv not found under: {base_path}")
    #     clients_csv = candidates[0]

    # 2) Gather all transaction/transfer CSVs
    client_files      = sorted([p for p in base_path.glob("**/*.csv") if "clients" in p.name])
    transaction_files = sorted([p for p in base_path.glob("**/*.csv") if "transactions" in p.name])
    transfer_files    = sorted([p for p in base_path.glob("**/*.csv") if "transfers"    in p.name])

    # 3) Read CSVs
    clients_df      = read_many_csv(client_files)
    transactions_df = read_many_csv(transaction_files)
    transfers_df    = read_many_csv(transfer_files)

    return clients_df, transactions_df, transfers_df


def build_clients(clients_df: pd.DataFrame, transactions_df: pd.DataFrame, transfers_df: pd.DataFrame) -> list[Client]:
    clients: list[Client] = []


    for _, row in clients_df.iterrows():
        code = row["client_code"]

    # Transactions
        client_transactions = [
            Transaction(**t.to_dict())
            for _, t in transactions_df[transactions_df["client_code"] == code].iterrows()
        ]

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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-path",
        default="case 1",
        help="Path to the folder containing clients.csv and many *transactions*.csv / *transfers*.csv",
    )

    args = parser.parse_args()

    # Resolve path robustly: absolute OR relative to script location
    p = Path(args.base_path)
    if not p.is_absolute():
        # First try relative to current working dir
        p = p.resolve()
        # If still missing, try relative to script file
        if not p.exists():
            p = (Path(__file__).parent / args.base_path).resolve()

    clients_df, transactions_df, transfers_df = load_data(p)
    clients = build_clients(clients_df, transactions_df, transfers_df)

    clients = calculations(transactions_df, transfers_df, clients)
    print(f"Loaded {len(clients)} clients from {p}")
    answer(clients[11])
    # print(clients[0].top4_categories,clients[0].total_transactions,clients[0].total_transfers_in, clients[0].total_transfers_out)

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
    top4_transactions = grouped_transactions.groupby("client_code").head(4)
    
    top4_transactions_map = (
    top4_transactions
    .groupby("client_code", group_keys=False)
    .apply(
        lambda df: [
            {"category": cat, "amount": float(amt)}
            for cat, amt in zip(df["category"], df["amount"])
        ],
        include_groups=False
    )
    .to_dict()
    )

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
        client.top4_categories = top4_transactions_map.get(client.client_code, [])
        client.total_transactions = transactions_total_dict.get(client.client_code, 0.0)
    return clients

if __name__ == "__main__":
    main()

