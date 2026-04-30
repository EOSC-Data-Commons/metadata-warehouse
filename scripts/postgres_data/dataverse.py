#!/usr/bin/env -S uv run --script

"""
Async DOI metadata downloader for Dataverse repositories.

Reads export_dois.csv (columns: doi, harvest_url) and downloads each DOI's
latest-published version as JSON from the appropriate Dataverse base URL.

Output files are named like: doi_10.17026_AR_6H2OUJ.dataverse_json.json
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

import aiohttp
import pandas as pd

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CSV_FILE = 'dans_arch.csv'
OUTPUT_DIR = Path('doi_dataverse')

HARVEST_URL_TO_BASE_URL: dict[str, str] = {
    'https://archaeology.datastations.nl/oai': 'https://archaeology.datastations.nl',
    'https://ssh.datastations.nl/oai': 'https://ssh.datastations.nl',
    'https://lifesciences.datastations.nl/oai': 'https://lifesciences.datastations.nl',
    'https://phys-techsciences.datastations.nl/oai': 'https://phys-techsciences.datastations.nl',
    'https://dataverse.nl/oai': 'https://dataverse.nl',
}

# Max simultaneous HTTP requests (be a good citizen to the servers)
MAX_CONCURRENT = 5

# Per-request timeout in seconds
REQUEST_TIMEOUT = 60

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-8s  %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def doi_to_filename(doi: str) -> str:
    """
    Convert a DOI string into a safe filename component.
    e.g. '10.17026/AR/6H2OUJ' -> 'doi_10.17026_AR_6H2OUJ.dataverse_json.json'
    """
    safe = doi.replace('/', '_')
    return f'doi_{safe}.dataverse_json.json'


def build_api_url(base_url: str, doi: str) -> str:
    return f'{base_url}/api/datasets/:persistentId/versions/:latest-published?persistentId=doi:{doi}'


def load_csv(csv_file: str) -> list[dict[str, str]]:
    """Return list of {doi, harvest_url} dicts from the CSV using pandas."""
    # sep=None + engine="python" lets pandas auto-detect tab vs comma
    df = pd.read_csv(csv_file, sep=None, engine='python', dtype=str)
    df.columns = df.columns.str.strip()
    df = df[['doi', 'harvest_url']].dropna()
    df = df[df['doi'].str.strip() != '']
    df['doi'] = df['doi'].str.strip()
    df['harvest_url'] = df['harvest_url'].str.strip()
    return df.to_dict(orient='records')


# ---------------------------------------------------------------------------
# Core download logic
# ---------------------------------------------------------------------------


async def download_doi(
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
    doi: str,
    harvest_url: str,
    output_dir: Path,
) -> None:
    base_url = HARVEST_URL_TO_BASE_URL.get(harvest_url)
    if base_url is None:
        log.warning('Unknown harvest_url %r for DOI %s — skipping.', harvest_url, doi)
        return

    api_url = build_api_url(base_url, doi)
    out_file = output_dir / doi_to_filename(doi)

    if out_file.exists():
        log.info('Already downloaded, skipping: %s', out_file.name)
        return

    async with semaphore:
        try:
            log.info('Fetching %s', api_url)
            async with session.get(api_url) as resp:
                if resp.status != 200:
                    log.error('HTTP %d for DOI %s (%s)', resp.status, doi, api_url)
                    return
                data = await resp.json(content_type=None)

            out_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding='utf-8',
            )
            log.info('Saved  → %s', out_file.name)

        except asyncio.TimeoutError:
            log.error('Timeout for DOI %s', doi)
        except aiohttp.ClientError as exc:
            log.error('Network error for DOI %s: %s', doi, exc)
        except Exception as exc:
            log.exception('Unexpected error for DOI %s: %s', doi, exc)


async def main() -> None:
    rows = load_csv(CSV_FILE)
    if not rows:
        log.error('No valid rows found in %s — exiting.', CSV_FILE)
        sys.exit(1)

    log.info('Loaded %d DOIs from %s', len(rows), CSV_FILE)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = [download_doi(session, semaphore, row['doi'], row['harvest_url'], OUTPUT_DIR) for row in rows]
        await asyncio.gather(*tasks)

    log.info("Done. JSON files written to '%s/'.", OUTPUT_DIR)


if __name__ == '__main__':
    asyncio.run(main())
