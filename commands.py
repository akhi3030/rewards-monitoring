#!/usr/bin/env python3

import subprocess
import time
from datetime import datetime
from pathlib import Path

# Configuration
OUTPUT_FILE = Path("solana_status.log")
INTERVAL_SECONDS = 30 * 60

COMMANDS = [
    ["../community-cluster/bin/solana", "epoch", "-ul"],
    ["../community-cluster/bin/solana", "stakes", "-ul"],
    ["../community-cluster/bin/solana", "validators", "-ul"],
]


def run_command(cmd):
    """Run a shell command and return stdout/stderr."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes timeout
        )

        output = result.stdout.strip()
        error = result.stderr.strip()

        if result.returncode != 0:
            return f"ERROR (exit code {result.returncode}):\n{error}"

        return output

    except Exception as e:
        return f"EXCEPTION:\n{str(e)}"


def write_log(message):
    """Append message to log file."""
    with open(OUTPUT_FILE, "a") as f:
        f.write(message)
        f.write("\n")


def main():
    print(f"Writing logs to: {OUTPUT_FILE.resolve()}")
    print("Starting Solana monitoring...")

    while True:
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

        separator = "=" * 80
        write_log(f"\n{separator}")
        write_log(f"Timestamp: {timestamp}")
        write_log(separator)

        for cmd in COMMANDS:
            command_str = " ".join(cmd)

            print(f"[{timestamp}] Running: {command_str}")

            write_log(f"\n$ {command_str}\n")

            output = run_command(cmd)

            write_log(output)
            write_log("\n" + ("-" * 80))

        print(f"[{timestamp}] Completed. Sleeping for 30 minutes...\n")

        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
