import csv
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict


TIMESTAMP_RE = re.compile(r"^Timestamp:\s+(.+?)\s*$")
VALIDATORS_CMD_RE = re.compile(r"^\$\s+\.\./community-cluster/bin/solana validators -ul\s*$")
SEPARATOR_RE = re.compile(r"^-{10,}\s*$")


def parse_timestamp(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S UTC")


def parse_number(value: str):
    value = value.split(" ")[0]
    try:
        return float(value)
    except ValueError:
        return None


def split_table_row(line: str):
    # Validators table is column-aligned with 2+ spaces between columns
    return re.split(r"\s{2,}", line.strip())


def normalize_header(columns):
    """
    Join split multi-word headers like:
    ['Vote', 'Account', 'Last', 'Vote', 'Active', 'Stake']
    into:
    ['vote account', 'last vote', 'active stake']
    """
    normalized = [c.strip().lower() for c in columns]
    merged = []

    i = 0
    while i < len(normalized):
        if i + 1 < len(normalized) and normalized[i] == "vote" and normalized[i + 1] == "account":
            merged.append("vote account")
            i += 2
        elif i + 1 < len(normalized) and normalized[i] == "active" and normalized[i + 1] == "stake":
            merged.append("active stake")
            i += 2
        elif i + 1 < len(normalized) and normalized[i] == "last" and normalized[i + 1] == "vote":
            merged.append("last vote")
            i += 2
        elif i + 1 < len(normalized) and normalized[i] == "root" and normalized[i + 1] == "block":
            merged.append("root block")
            i += 2
        else:
            merged.append(normalized[i])
            i += 1

    return merged


def parse_validators_sections(log_path: Path):
    records = []

    current_timestamp = None
    in_validators_section = False
    header = None
    vote_idx = None
    active_stake_idx = None

    for raw_line in log_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip("\n")
        stripped = line.strip()

        if not stripped:
            continue

        ts_match = TIMESTAMP_RE.match(stripped)
        if ts_match:
            current_timestamp = ts_match.group(1)
            in_validators_section = False
            header = None
            vote_idx = None
            active_stake_idx = None
            continue

        if VALIDATORS_CMD_RE.match(stripped):
            in_validators_section = True
            header = None
            vote_idx = None
            active_stake_idx = None
            continue

        # Exit validators section on the next command block separator or another command
        if in_validators_section and (
            SEPARATOR_RE.match(stripped) or (stripped.startswith("$ ") and not VALIDATORS_CMD_RE.match(stripped))
        ):
            in_validators_section = False
            header = None
            vote_idx = None
            active_stake_idx = None
            continue

        if not in_validators_section or current_timestamp is None:
            continue


        columns = split_table_row(line)
        if not columns:
            continue


        if header is None:
            candidate_header = normalize_header(columns)
            if "vote account" in candidate_header and "active stake" in candidate_header:
                header = candidate_header
                vote_idx = header.index("vote account")
                active_stake_idx = header.index("active stake")
            continue

        if vote_idx is None or active_stake_idx is None:
            continue

        # Ignore ruler/subheader lines
        if set(stripped) <= {"-", " "}:
            continue

        if len(columns) <= max(vote_idx, active_stake_idx):
            continue


        print()
        print(columns)
        print(columns[vote_idx], columns[-1], parse_number(columns[-1]))

        vote_account = columns[vote_idx].strip()
        active_stake = parse_number(columns[-1])

        if vote_account and active_stake is not None:
            records.append(
                {
                    "timestamp": current_timestamp,
                    "vote_account": vote_account,
                    "active_stake": active_stake,
                }
            )

    return records


def write_active_stake_delta_csv(records, output_path: Path):
    stakes_by_vote_account = defaultdict(dict)
    all_timestamps = set()
    first_seen_order = {}

    for record in records:
        vote_account = record["vote_account"]
        timestamp = record["timestamp"]
        active_stake = record["active_stake"]

        stakes_by_vote_account[vote_account][timestamp] = active_stake
        all_timestamps.add(timestamp)

        if vote_account not in first_seen_order:
            first_seen_order[vote_account] = len(first_seen_order)

    ordered_timestamps = sorted(all_timestamps, key=parse_timestamp)
    delta_columns = ordered_timestamps[1:]

    rows = []

    for vote_account, stakes in stakes_by_vote_account.items():
        row = {"vote_account": vote_account}
        deltas = []

        previous_value = stakes.get(ordered_timestamps[0])

        for timestamp in delta_columns:
            current_value = stakes.get(timestamp)

            if previous_value is None or current_value is None:
                delta = ""
            else:
                delta = current_value - previous_value

            row[timestamp] = delta
            deltas.append(delta)
            previous_value = current_value

        has_non_zero_delta = any(
            isinstance(delta, (int, float)) and delta != 0
            for delta in deltas
        )

        rows.append((has_non_zero_delta, first_seen_order[vote_account], row))

    # Non-zero delta rows first, preserve first-seen order within groups
    rows.sort(key=lambda item: (not item[0], item[1]))

    with output_path.open("w", newline="", encoding="utf-8") as f:
        fieldnames = ["vote_account"] + delta_columns
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for _, _, row in rows:
            writer.writerow(row)

    print(f"Wrote {len(rows)} rows to {output_path}")


def main():
    input_path = Path("solana_status.log")
    output_path = Path("validator_vote_account_active_stake_deltas.csv")

    records = parse_validators_sections(input_path)
    write_active_stake_delta_csv(records, output_path)


if __name__ == "__main__":
    main()

