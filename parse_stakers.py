import csv
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict


TIMESTAMP_RE = re.compile(r"^Timestamp:\s+(.+?)\s*$")
STAKE_PUBKEY_RE = re.compile(r"^Stake Pubkey:\s+(\S+)\s*$")
BALANCE_RE = re.compile(r"^Balance:\s+([0-9]+(?:\.[0-9]+)?)\s+SOL\s*$")


def parse_timestamp(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S UTC")


def parse_log_balances(log_path: Path):
    records = []
    current_timestamp = None
    current_pubkey = None

    for raw_line in log_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        ts_match = TIMESTAMP_RE.match(line)
        if ts_match:
            current_timestamp = ts_match.group(1)
            current_pubkey = None
            continue

        pubkey_match = STAKE_PUBKEY_RE.match(line)
        if pubkey_match:
            current_pubkey = pubkey_match.group(1)
            continue

        balance_match = BALANCE_RE.match(line)
        if balance_match and current_timestamp and current_pubkey:
            records.append(
                {
                    "timestamp": current_timestamp,
                    "stake_pubkey": current_pubkey,
                    "balance_sol": float(balance_match.group(1)),
                }
            )

    return records


def write_balance_delta_csv(records, output_path: Path):
    balances_by_pubkey = defaultdict(dict)
    all_timestamps = set()
    first_seen_order = {}

    for record in records:
        pubkey = record["stake_pubkey"]
        timestamp = record["timestamp"]
        balance = record["balance_sol"]

        balances_by_pubkey[pubkey][timestamp] = balance
        all_timestamps.add(timestamp)

        if pubkey not in first_seen_order:
            first_seen_order[pubkey] = len(first_seen_order)

    ordered_timestamps = sorted(all_timestamps, key=parse_timestamp)
    delta_columns = ordered_timestamps[1:]

    rows = []

    for pubkey, balances in balances_by_pubkey.items():
        row = {"stake_pubkey": pubkey}
        deltas = []

        previous_balance = balances.get(ordered_timestamps[0])

        for timestamp in delta_columns:
            current_balance = balances.get(timestamp)

            if previous_balance is None or current_balance is None:
                delta = ""
            else:
                delta = current_balance - previous_balance

            row[timestamp] = delta
            deltas.append(delta)
            previous_balance = current_balance

        has_non_zero_delta = any(
            isinstance(delta, (int, float)) and delta != 0
            for delta in deltas
        )

        rows.append((has_non_zero_delta, first_seen_order[pubkey], row))

    # Non-zero deltas first, then stable pubkeys; preserve first-seen order within each group
    rows.sort(key=lambda item: (not item[0], item[1]))

    with output_path.open("w", newline="", encoding="utf-8") as f:
        fieldnames = ["stake_pubkey"] + delta_columns
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for _, _, row in rows:
            writer.writerow(row)

    print(f"Wrote {len(rows)} rows to {output_path}")


def main():
    input_path = Path("solana_status.log")
    output_path = Path("all_pubkey_balance_deltas.csv")

    records = parse_log_balances(input_path)
    write_balance_delta_csv(records, output_path)


if __name__ == "__main__":
    main()

