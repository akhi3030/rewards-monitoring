import os
import sys
import time
from collections import defaultdict
from typing import Dict, List, Optional

from solana.rpc.api import Client
from solders.pubkey import Pubkey


RPC_URL = "http://127.0.0.1:8899"
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))


def lamports_to_sol(lamports: int) -> float:
    return lamports / 1_000_000_000


def get_client() -> Client:
    return Client(RPC_URL)


def get_current_epoch(client: Client) -> int:
    resp = client.get_epoch_info()
    return resp.value.epoch


def get_inflation_rewards_for_epoch(
    client: Client,
    addresses: List[str],
    epoch: int,
) -> Dict[str, int]:
    """
    Returns a mapping of address -> reward lamports for the requested epoch.
    """
    if not addresses:
        return {}

    pubkeys = [Pubkey.from_string(address) for address in addresses]
    resp = client.get_inflation_reward(pubkeys, epoch=epoch)

    rewards: Dict[str, int] = {}
    for address, reward_info in zip(addresses, resp.value):
        if reward_info is None:
            rewards[address] = 0
        else:
            rewards[address] = reward_info.amount
    return rewards


def chunked(items: List[str], size: int) -> List[List[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def fetch_all_stake_accounts(client: Client) -> List[dict]:
    """
    Fetch all stake-program accounts using getProgramAccounts.
    """
    stake_program = Pubkey.from_string("Stake11111111111111111111111111111111111111")
    resp = client.get_program_accounts(
        stake_program,
        encoding="jsonParsed",
    )
    return [acct.account.data.parsed for acct in resp.value]


def extract_staker_and_withdrawer(parsed_accounts: List[dict]) -> Dict[str, List[str]]:
    """
    Builds owner -> [stake_account_addresses] using both staker and withdrawer authorities.
    This is not perfect identity resolution, but it provides a practical per-authority view.
    """
    owner_to_accounts: Dict[str, List[str]] = defaultdict(list)

    for parsed in parsed_accounts:
        try:
            info = parsed["info"]
            meta = info.get("meta", {})
            authorized = meta.get("authorized", {})
            staker = authorized.get("staker")
            withdrawer = authorized.get("withdrawer")
            stake_pubkey = info.get("stakeAccount")
        except Exception:
            continue

        if not stake_pubkey:
            continue

        if staker:
            owner_to_accounts[staker].append(stake_pubkey)
        if withdrawer and withdrawer != staker:
            owner_to_accounts[withdrawer].append(stake_pubkey)

    return owner_to_accounts


def fetch_all_stake_accounts_with_addresses(client: Client) -> List[dict]:
    stake_program = Pubkey.from_string("Stake11111111111111111111111111111111111111")
    resp = client.get_program_accounts(
        stake_program,
        encoding="jsonParsed",
    )

    result = []
    for acct in resp.value:
        try:
            result.append(
                {
                    "pubkey": str(acct.pubkey),
                    "parsed": acct.account.data.parsed,
                }
            )
        except Exception:
            continue
    return result


def build_authority_to_stake_accounts(client: Client) -> Dict[str, List[str]]:
    authority_map: Dict[str, List[str]] = defaultdict(list)
    accounts = fetch_all_stake_accounts_with_addresses(client)

    for entry in accounts:
        pubkey = entry["pubkey"]
        parsed = entry["parsed"]

        try:
            info = parsed["info"]
            meta = info.get("meta", {})
            authorized = meta.get("authorized", {})
            staker = authorized.get("staker")
            withdrawer = authorized.get("withdrawer")
        except Exception:
            continue

        if staker:
            authority_map[staker].append(pubkey)
        if withdrawer and withdrawer != staker:
            authority_map[withdrawer].append(pubkey)

    return authority_map


def get_epoch_rewards_grouped_by_authority(client: Client, epoch: int) -> Dict[str, int]:
    authority_to_accounts = build_authority_to_stake_accounts(client)

    all_accounts = []
    for accounts in authority_to_accounts.values():
        all_accounts.extend(accounts)

    unique_accounts = sorted(set(all_accounts))
    account_rewards: Dict[str, int] = {}

    # Chunk requests to avoid oversized RPC calls.
    for batch in chunked(unique_accounts, 100):
        batch_rewards = get_inflation_rewards_for_epoch(client, batch, epoch)
        account_rewards.update(batch_rewards)

    authority_rewards: Dict[str, int] = {}
    for authority, stake_accounts in authority_to_accounts.items():
        total = sum(account_rewards.get(stake_account, 0) for stake_account in stake_accounts)
        authority_rewards[authority] = total

    return authority_rewards


def print_epoch_rewards(epoch: int, authority_rewards: Dict[str, int]) -> None:
    print(f"\n=== Epoch {epoch} staking rewards ===")
    print(f"Authorities with rewards: {sum(1 for v in authority_rewards.values() if v > 0)}")
    print()

    sorted_rewards = sorted(
        authority_rewards.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    for authority, lamports in sorted_rewards:
        if lamports <= 0:
            continue
        print(f"{authority}: {lamports} lamports ({lamports_to_sol(lamports):.9f} SOL)")

    total_lamports = sum(authority_rewards.values())
    print()
    print(f"Total rewards this epoch: {total_lamports} lamports ({lamports_to_sol(total_lamports):.9f} SOL)")
    print("=====================================")


def main() -> None:
    client = get_client()

    try:
        current_epoch = get_current_epoch(client)
    except Exception as exc:
        print(f"Failed to fetch current epoch: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Connected to {RPC_URL}")
    print(f"Starting at current epoch: {current_epoch}")
    print(f"Polling every {POLL_INTERVAL_SECONDS} seconds...")

    last_seen_epoch = current_epoch


    authority_rewards = get_epoch_rewards_grouped_by_authority(client, current_epoch)
    print_epoch_rewards(current_epoch, authority_rewards)
 

    

    while True:
        try:
            current_epoch = get_current_epoch(client)

            if current_epoch > last_seen_epoch:
                completed_epoch = current_epoch - 1
                print(f"\nEpoch changed: {last_seen_epoch} -> {current_epoch}")
                print(f"Fetching staking rewards for completed epoch {completed_epoch}...")

                authority_rewards = get_epoch_rewards_grouped_by_authority(
                    client,
                    completed_epoch,
                )
                print_epoch_rewards(completed_epoch, authority_rewards)
                last_seen_epoch = current_epoch

        except KeyboardInterrupt:
            print("\nStopped.")
            sys.exit(0)
        except Exception as exc:
            print(f"Error while monitoring rewards: {exc}", file=sys.stderr)

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
