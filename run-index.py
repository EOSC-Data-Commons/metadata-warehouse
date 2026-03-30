import argparse
from decimal import InvalidOperation
import httpx
from urllib.parse import quote

BASE = "http://127.0.0.1:8080"
DEFAULT_INDEX_NAME = "test_datacite"


def get_all_harvest_urls(print_urls: bool = False):
    """
    Fetch all harvest URLs from /config.

    Args:
        print_urls (bool): If True, print each URL to stdout.

    Returns:
        list[str]: List of harvest URLs.
    """
    r = httpx.get(f"{BASE}/config")
    r.raise_for_status()
    data = r.json()
    urls = [
        e.get("harvest_url")
        for e in data.get("endpoints_configs", [])
        if e.get("harvest_url")
    ]

    if print_urls:
        for url in urls:
            print(url)

    return urls


def get_id(url):
    encoded = quote(url, safe="")
    r = httpx.get(
        f"{BASE}/harvest_run?harvest_url={encoded}",
        headers={"accept": "application/json"},
    )
    r.raise_for_status()
    data = r.json()
    print(data)  # Or print only an ID: print(data.get("id"))


def index_harvest(url: str, index_name: str | None = None):
    """Fetch harvest_run_id from harvest URL and call /index API."""
    # 1. Call /harvest_run to get ID
    encoded_url = quote(url, safe="")
    r = httpx.get(
        f"{BASE}/harvest_run?harvest_url={encoded_url}",
        headers={"accept": "application/json"},
    )
    r.raise_for_status()
    data = r.json()['harvest_runs'][0]

    harvest_run_id = data.get("id")
    if not harvest_run_id:
        raise ValueError(f"No 'id' found in response for URL {url}")

    # 2. Call /index API
    params = {"harvest_run_id": harvest_run_id}
    if index_name:
        params["index_name"] = index_name
    else:
        params["index_name"] = DEFAULT_INDEX_NAME

    r2 = httpx.get(f"{BASE}/index", params=params, timeout=None)
    r2.raise_for_status()
    index_response = r2.json()
    print(f"Indexing response: {index_response}")


def index_all():
    """Index all harvest URLs from config."""
    urls = get_all_harvest_urls(print_urls=False)
    for url in urls:
        index_harvest(url)


def main():
    parser = argparse.ArgumentParser(description="Harvest CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list command
    subparsers.add_parser("list", help="List all available harvest URLs")

    # get command
    get_parser = subparsers.add_parser("get", help="Get harvest run for a specific URL")
    get_parser.add_argument("url", help="The harvest URL to query")

    # indexing command
    index_parser = subparsers.add_parser(
        "indexing", help="indexing harvest run for a specific URL"
    )
    index_parser.add_argument("url", help="The harvest URL to query")

    # indexing-all command
    subparsers.add_parser(
        "indexing-all", help="indexing harvest run for a specific URL"
    )

    args = parser.parse_args()

    if args.command == "list":
        get_all_harvest_urls(print_urls=True)
    elif args.command == "get":
        get_id(args.url)
    elif args.command == "indexing":
        index_harvest(args.url)
    elif args.command == "indexing-all":
        index_all()
    else:
        raise InvalidOperation(f"unknown command {args.command}")


if __name__ == "__main__":
    main()
