import argparse
from pathlib import Path
import pandas as pd
from client import handle_clients_logic
from dotenv import load_dotenv
load_dotenv()


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
    if not base_path.exists():
        raise FileNotFoundError(f"Folder not found: {base_path}")

    client_files      = sorted([p for p in base_path.glob("**/*.csv") if "clients" in p.name])
    transaction_files = sorted([p for p in base_path.glob("**/*.csv") if "transactions" in p.name])
    transfer_files    = sorted([p for p in base_path.glob("**/*.csv") if "transfers"    in p.name])

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