#!/usr/bin/env -S uv run --script

# xmlstarlet sel -N oai="http://www.openarchives.org/OAI/2.0/" -t -v "//oai:header/oai:identifier" data/zenodo/zenodo_parts.xml >> zenodo_ids.txt

import argparse
import asyncio
import json
import logging
from pathlib import Path
from typing import NamedTuple

import aiohttp
from aiohttp import ClientSession

MAX_CONCURRENT = 3
REQUEST_TIMEOUT = 60

MAX_RETRIES = 5
RETRY_BASE_DELAY = 2.0
RETRY_MAX_DELAY = 120.0
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-8s  %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger(__name__)


class RequestConfig(NamedTuple):
    api_url: str
    out_file: Path


def zenodo_config(rec_id: str, output_dir: Path) -> RequestConfig:
    return RequestConfig(
        api_url=f'https://zenodo.org/api/records/{rec_id}/files',
        out_file=output_dir / f'oai_{rec_id}_.json',
    )


def hal_config(rec_id: str, output_dir: Path) -> RequestConfig:
    version_seg = rec_id.rfind('v')
    rec_id_no_version = rec_id[:version_seg] if version_seg > 0 else rec_id
    return RequestConfig(
        api_url=f'https://api.archives-ouvertes.fr/search/?q=halId_s:{rec_id_no_version}&wt=json&fl=halId_s,fileMain_s,files_s,fileType_s,modifiedDate_tdate,producedDate_tdate,version_i',
        out_file=output_dir / f'oai_{rec_id}_.json',
    )


PROVIDERS = {
    'zenodo': zenodo_config,
    'hal': hal_config,
}


async def download_file_meta(session: ClientSession, rec_id: str, output_dir: Path, provider: str):
    config = PROVIDERS[provider](rec_id, output_dir)

    if config.out_file.exists():
        log.info('Already downloaded, skipping: %s', config.out_file.name)
        return

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with session.get(config.api_url) as resp:
                if resp.status in RETRYABLE_STATUSES:
                    retry_after = resp.headers.get('Retry-After')
                    delay = (
                        float(retry_after)
                        if retry_after
                        else min(RETRY_BASE_DELAY * (2 ** (attempt - 1)), RETRY_MAX_DELAY)
                    )
                    if attempt < MAX_RETRIES:
                        log.warning(
                            'HTTP %d for %s — attempt %d/%d, retrying in %.1fs',
                            resp.status,
                            rec_id,
                            attempt,
                            MAX_RETRIES,
                            delay,
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        log.error('HTTP %d for %s — giving up after %d attempts', resp.status, rec_id, MAX_RETRIES)
                        return

                if resp.status != 200:
                    log.error('HTTP %d for %s (%s)', resp.status, rec_id, config.api_url)
                    return

                data = await resp.json(content_type=None)
                config.out_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
                log.info('Saved → %s', config.out_file.name)
                return

        except asyncio.TimeoutError:
            delay = min(RETRY_BASE_DELAY * (2 ** (attempt - 1)), RETRY_MAX_DELAY)
            if attempt < MAX_RETRIES:
                log.warning('Timeout for %s — attempt %d/%d, retrying in %.1fs', rec_id, attempt, MAX_RETRIES, delay)
                await asyncio.sleep(delay)
            else:
                log.error('Timeout for %s — giving up after %d attempts', rec_id, MAX_RETRIES)

        except aiohttp.ClientError as exc:
            log.error('Network error for %s: %s', rec_id, exc)
            return

        except Exception as exc:
            log.exception('Unexpected error for %s: %s', rec_id, exc)
            return


async def main() -> None:
    parser = argparse.ArgumentParser(description='Download file metadata from Zenodo or HAL')
    parser.add_argument('--input', required=True, help='File with record IDs, one per line')
    parser.add_argument('--output', required=True, help='Directory to write results to')
    parser.add_argument('--provider', required=True, choices=PROVIDERS.keys(), help='API provider to use')
    args = parser.parse_args()

    input_file = Path(args.input)
    output_dir = Path(args.output)

    ids = input_file.read_text().strip().splitlines()
    log.info('Loaded %d IDs from %s', len(ids), input_file)

    output_dir.mkdir(parents=True, exist_ok=True)

    connector = aiohttp.TCPConnector(limit_per_host=MAX_CONCURRENT)
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = [download_file_meta(session, id.split(':')[-1], output_dir, args.provider) for id in ids]
        await asyncio.gather(*tasks)


if __name__ == '__main__':
    asyncio.run(main())
