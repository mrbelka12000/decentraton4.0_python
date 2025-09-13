import argparse
from pathlib import Path
import pandas as pd
from client import handle_clients_logic


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



def main():

    # Resolve path robustly: absolute OR relative to script location
    p = Path("case 1")
    clients_df, transactions_df, transfers_df = load_data(p)

    handle_clients_logic(clients_df, transactions_df, transfers_df)


if __name__ == "__main__":
    main()