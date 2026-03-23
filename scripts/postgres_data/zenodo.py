#!/usr/bin/env -S uv run --script

import asyncio
import json
import logging
from pathlib import Path

import aiohttp
from aiohttp import ClientSession

ID_FILE = 'zenodo_ids.txt'
OUTPUT_DIR = Path("meta_zenodo")

MAX_CONCURRENT = 3
REQUEST_TIMEOUT = 60

MAX_RETRIES = 5
RETRY_BASE_DELAY = 2.0
RETRY_MAX_DELAY = 120.0
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

async def download_file_meta(session: ClientSession, rec_id: str, output_dir: Path):
    api_url = f'https://zenodo.org/api/records/{rec_id}/files'
    out_file = output_dir / f'oai_{rec_id}_.json'

    if out_file.exists():
        log.info("Already downloaded, skipping: %s", out_file.name)
        return

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with session.get(api_url) as resp:
                if resp.status in RETRYABLE_STATUSES:
                    retry_after = resp.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else min(RETRY_BASE_DELAY * (2 ** (attempt - 1)), RETRY_MAX_DELAY)
                    if attempt < MAX_RETRIES:
                        log.warning("HTTP %d for %s — attempt %d/%d, retrying in %.1fs", resp.status, rec_id, attempt, MAX_RETRIES, delay)
                        await asyncio.sleep(delay)
                        continue
                    else:
                        log.error("HTTP %d for %s — giving up after %d attempts", resp.status, rec_id, MAX_RETRIES)
                        return

                if resp.status != 200:
                    log.error("HTTP %d for %s (%s)", resp.status, rec_id, api_url)
                    return

                data = await resp.json(content_type=None)
                out_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                log.info("Saved → %s", out_file.name)
                return

        except asyncio.TimeoutError:
            delay = min(RETRY_BASE_DELAY * (2 ** (attempt - 1)), RETRY_MAX_DELAY)
            if attempt < MAX_RETRIES:
                log.warning("Timeout for %s — attempt %d/%d, retrying in %.1fs", rec_id, attempt, MAX_RETRIES, delay)
                await asyncio.sleep(delay)
            else:
                log.error("Timeout for %s — giving up after %d attempts", rec_id, MAX_RETRIES)

        except aiohttp.ClientError as exc:
            log.error("Network error for %s: %s", rec_id, exc)
            return

        except Exception as exc:
            log.exception("Unexpected error for %s: %s", rec_id, exc)
            return

async def main() -> None:
    with open(ID_FILE) as f:
        ids = f.read().strip('\n').split('\n')

    print(len(ids))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    connector = aiohttp.TCPConnector(limit_per_host=MAX_CONCURRENT)
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = [
            download_file_meta(session, id.split(':')[-1], OUTPUT_DIR)
            for id in ids
        ]
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
