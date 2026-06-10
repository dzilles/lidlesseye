import argparse
import getpass
import os
from pathlib import Path

import yaml


APP_DIR = Path.home() / ".config" / "lidlesseye"
SECRETS_FILE = APP_DIR / "secrets.yaml"


def load_secrets() -> dict:
    if not SECRETS_FILE.exists():
        return {}

    with SECRETS_FILE.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def save_secrets(secrets: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)

    with SECRETS_FILE.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(secrets, handle, sort_keys=True)

    try:
        os.chmod(SECRETS_FILE, 0o600)
    except OSError:
        # Windows does not consistently support POSIX-style chmod semantics.
        pass


def set_google_api_key(api_key: str | None = None) -> None:
    key = api_key or getpass.getpass("Gemini API key: ").strip()
    if not key:
        raise ValueError("No API key provided.")

    secrets = load_secrets()
    secrets["GOOGLE_API_KEY"] = key
    save_secrets(secrets)
    print(f"Stored GOOGLE_API_KEY in {SECRETS_FILE}")


def load_env_from_vault() -> None:
    secrets = load_secrets()
    for key, value in secrets.items():
        os.environ.setdefault(key, str(value))


def parse_args():
    parser = argparse.ArgumentParser(description="Manage Project LidlessEye local secrets.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    set_key = subparsers.add_parser("set-google-key", help="Store the Gemini API key locally.")
    set_key.add_argument("api_key", nargs="?", help="Gemini API key. Prefer the hidden prompt for security.")
    set_key.add_argument("--value", help="Gemini API key. If omitted, input is hidden.")

    subparsers.add_parser("path", help="Print the local secrets file path.")
    return parser.parse_args()


def main():
    args = parse_args()

    if args.command == "set-google-key":
        set_google_api_key(args.value or args.api_key)
    elif args.command == "path":
        print(SECRETS_FILE)


if __name__ == "__main__":
    main()

