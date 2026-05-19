#!/usr/bin/env python3

import re
import json
import subprocess

LAMPORTS_PER_SOL = 1_000_000_000


def get_solana_stakes_output() -> str:
    """
    Run `solana stakes` and return the raw output.
    """
    result = subprocess.run(
        ["../community-cluster/bin/solana", "stakes", "-ul"],
        capture_output=True,
        text=True,
        check=True,
    )

    return result.stdout


def sol_to_lamports(value: str):
    """
    Convert a CLI-formatted SOL amount like `1.234 SOL` into integer lamports.
    Returns None if the value is not a SOL-denominated numeric amount.
    """
    m = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s+SOL$", value)
    if not m:
        return None

    sol_amount = float(m.group(1))
    return int(round(sol_amount * LAMPORTS_PER_SOL))


def parse_solana_stakes(output: str) -> dict:
    """
    Parse `solana stakes` CLI output into a structured dictionary.

    Returns:
    {
        "<stake_account_pubkey>": {
            "balance": 1234000000,
            "delegated_stake": 1233000000,
            "delegated_vote_account_address": "...",
            "activation_epoch": "123",
            ...
        },
        ...
    }
    """

    stakes = {}
    current_account = None

    # Example:
    # Stake Pubkey: XXXXX
    stake_pubkey_re = re.compile(r"^Stake Pubkey:\s+(.+)$")

    # Example:
    # Balance: 1.23 SOL
    kv_re = re.compile(r"^\s*([^:]+):\s+(.+)$")

    for line in output.splitlines():
        line = line.rstrip()

        # Start of a new stake account block
        m = stake_pubkey_re.match(line)
        if m:
            current_account = m.group(1).strip()
            stakes[current_account] = {}
            continue

        if current_account is None:
            continue

        # Generic key/value parser
        m = kv_re.match(line)
        if m:
            key = (
                m.group(1)
                .strip()
                .lower()
                .replace(" ", "_")
            )

            value = m.group(2).strip()
            lamports_value = sol_to_lamports(value)

            stakes[current_account][key] = (
                lamports_value if lamports_value is not None else value
            )

    return stakes


if __name__ == "__main__":
    try:
        raw_output = get_solana_stakes_output()
        parsed = parse_solana_stakes(raw_output)

        print(json.dumps(parsed, indent=2))

    except subprocess.CalledProcessError as e:
        print("Failed to run `solana stakes`")
        print(e.stderr)
