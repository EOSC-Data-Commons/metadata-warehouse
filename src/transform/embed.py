"""Embeddings from the OpenAI compatible endpoints this project has access to.

All of them are vLLM behind the same API, so an endpoint is an entry in API_ENDPOINTS rather than
a class: what differs is the rate limit and how much its answers can be trusted (see ApiEndpoint).

Texts in, vectors out, so any job can use it:

    from .embed import build_embedder

    with build_embedder() as embedder:               # ferro by default, no key needed
        vectors = embedder.embed_texts(['a text', 'another one'])
    logger.info(embedder.stats())

Nothing is verified unless asked for: check_batching() re-embeds a sample of a batch one text at a
time and compares, which is how to tell whether an endpoint's batch_size is safe (some return
different vectors for a batched text than for the same text alone).
"""

import logging
import math
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from threading import Lock, local
from typing import Any, NamedTuple

import requests
from requests.adapters import HTTPAdapter

logger = logging.getLogger(__name__)

# The endpoints, all vLLM behind the same API, configured in API_ENDPOINTS below
CESNET_API_URL = 'https://llm.ai.e-infra.cz/v1'
EGI_API_URL = 'https://llm.ai.egi.eu/v1'
FERRO_API_URL = 'http://46.60.19.44:8000/v1'
# which of API_ENDPOINTS to use when nothing is specified: ours, no key and no rate limit
DEFAULT_ENDPOINT = 'ferro'
# The model trained window, vLLM rejects anything longer, see ApiEndpoint.truncate_tokens
MODEL_CONTEXT_TOKENS = 512


class EmbeddingModel(NamedTuple):
    """An embedding model and everything that has to change with it.

    The task prefixes belong to the model family, using the wrong one silently degrades retrieval.
    doc_prefix is prepended here; the SEARCH API must prepend query_prefix to user queries.
    """

    name: str
    dims: int
    doc_prefix: str
    query_prefix: str


# Dims measured against the API, prefixes copied from each model card (never guess them)
EMBEDDING_MODELS = {
    'nomic-embed-text-v2-moe': EmbeddingModel('nomic-embed-text-v2-moe', 768, 'search_document: ', 'search_query: '),
    'nomic-embed-text-v1.5': EmbeddingModel('nomic-embed-text-v1.5', 768, 'search_document: ', 'search_query: '),
    'multilingual-e5-large-instruct': EmbeddingModel('multilingual-e5-large-instruct', 1024, 'passage: ', 'query: '),
}

# changing it needs a matching vector(N) in create_sql/appdb/tables.sql and a full --reset
EMBEDDING_MODEL = EMBEDDING_MODELS['nomic-embed-text-v2-moe']
# what a text the model refuses is truncated to, short enough for any script
SAFE_CHUNK_CHARS = 400

# Texts of a batch re-embedded alone to check it against, see _worst_mismatch
VERIFY_SAMPLE_SIZE = 3
# a correct match sits at ~1.0000, a wrong vector well below
VERIFY_MIN_COSINE = 0.999

# cap on a Retry-After we obey, a shared endpoint occasionally asks for minutes
MAX_RETRY_AFTER = 120.0


class ContextWindowExceededError(RuntimeError):
    """A batch the embedding model refused because one of its texts is too long."""


def retry_after_seconds(response: requests.Response | None) -> float | None:
    """How long the server asked us to wait, from its Retry-After header. None when it sent none.

    Both forms RFC 9110 allows: a number of seconds, or an HTTP date. Capped at MAX_RETRY_AFTER,
    since a request holds one of `concurrency` threads and the whole batch waits behind it.
    """
    header = response.headers.get('Retry-After') if response is not None else None
    if not header:
        return None
    try:
        seconds = float(header)
    except ValueError:
        try:
            when = parsedate_to_datetime(header)
        except (TypeError, ValueError):
            return None
        seconds = (when - datetime.now(when.tzinfo)).total_seconds()
    return min(max(seconds, 0.0), MAX_RETRY_AFTER)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two vectors, 1.0 when they point the same way."""
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


@dataclass(frozen=True)
class ApiEndpoint:
    """One OpenAI compatible embeddings endpoint.

    A new one is an entry in API_ENDPOINTS, not a subclass: what differs between them is only what
    the service tolerates, and how much its answers can be trusted.
    """

    name: str
    base_url: str
    # the rate limit: whatever saturates our own GPU, small and polite numbers on a shared service
    batch_size: int
    concurrency: int
    # environment variable holding the bearer token, None for an endpoint that needs no auth
    api_key_env: str | None = None
    # sends truncate_prompt_tokens so the server clips a long text, else embed_batch splits it out
    truncate_tokens: int | None = None
    # correctness, not politeness: re-check every batch against a batch of 1, see _verified()
    verify_every_batch: bool = False


API_ENDPOINTS = {
    # No rate limit, ~500 texts/s
    'ferro': ApiEndpoint(
        name='ferro GPU',
        base_url=FERRO_API_URL,
        batch_size=64,
        concurrency=64,
        truncate_tokens=MODEL_CONTEXT_TOKENS,
    ),
    # Shared, so rate limited: measured clean at 8 requests in flight, 429 with Retry-After 120 from
    # 16 up. Batches of 64 are reproducible (--check-batching 64), it is the fan out that has to stay
    # small. Accepts truncate_prompt_tokens and ignores it, so embed_batch splits a long text instead.
    'egi': ApiEndpoint(
        name='EGI',
        base_url=EGI_API_URL,
        batch_size=64,
        concurrency=8,
        api_key_env='EGI_API_KEY',
        verify_every_batch=False,
    ),
    # Non reproducible above a batch size that moves with its load: leave the verification on
    'cesnet': ApiEndpoint(
        name='Cesnet',
        base_url=CESNET_API_URL,
        batch_size=16,
        concurrency=3,
        api_key_env='CESNET_API_KEY',
        verify_every_batch=True,
    ),
}


class ApiEmbeddings:
    """Embeddings from any of the API_ENDPOINTS.

    One HTTP client, one request with retries, and a fan out of `concurrency` requests of
    `batch_size` texts. How much the answers are trusted comes from the endpoint, not from a
    subclass: see ApiEndpoint.
    """

    def __init__(
        self,
        endpoint: ApiEndpoint,
        model: EmbeddingModel = EMBEDDING_MODEL,
        api_key: str | None = None,
        concurrency: int | None = None,
        base_url: str | None = None,
    ):
        self.endpoint = endpoint
        self.model = model
        self.batch_size = endpoint.batch_size
        self.concurrency = concurrency or endpoint.concurrency
        self.lock = Lock()
        self.texts = 0
        self.requests = 0
        self.batches = 0
        self.splits = 0
        self.truncated = 0
        self.rate_limited = 0
        self.worst_similarity = 1.0
        self.url = f'{(base_url or endpoint.base_url).rstrip("/")}/embeddings'
        self.headers = {'Authorization': f'Bearer {api_key}'} if api_key else {}
        # one session per thread, embed_texts fans out over `concurrency` of them
        self.local = local()
        self.sessions: list[requests.Session] = []

    @property
    def session(self) -> requests.Session:
        """This thread's own session, with keep alive so a batch reuses one connection.

        Per thread because requests.Session is not documented as thread safe. Every session opened
        is kept in self.sessions, so close() can close them all.
        """
        session = getattr(self.local, 'session', None)
        if session is None:
            session = requests.Session()
            session.headers.update(self.headers)
            session.mount('http://', HTTPAdapter(pool_connections=1, pool_maxsize=1))
            session.mount('https://', HTTPAdapter(pool_connections=1, pool_maxsize=1))
            self.local.session = session
            with self.lock:
                self.sessions.append(session)
        return session

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed any number of texts, batch_size per request, `concurrency` requests in flight.

        One vector per input text, in the same order. Identical texts are sent once and reused: a
        quarter of the chunks of a dataset batch are exact duplicates and the API is the bottleneck.
        """
        if not texts:
            return []
        unique_texts = list(dict.fromkeys(texts))
        batches = [unique_texts[i : i + self.batch_size] for i in range(0, len(unique_texts), self.batch_size)]
        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            vectors = [vector for batch_vectors in pool.map(self.embed_batch, batches) for vector in batch_vectors]
        by_text = dict(zip(unique_texts, vectors, strict=True))
        return [by_text[text] for text in texts]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed one batch, applying whatever checking this endpoint needs.

        A batch rejected for exceeding the context is halved down to the single offending text,
        which is then truncated: truncating the whole batch would corrupt the rest of it. Endpoints
        with truncate_tokens never get here, the server clips instead.
        """
        try:
            vectors = self._request(texts)
        except ContextWindowExceededError:
            if len(texts) > 1:
                return self._embed_halves(texts)
            with self.lock:
                self.truncated += 1
            logger.debug(f'text over the model context, truncating to {SAFE_CHUNK_CHARS} chars: {texts[0][:80]}...')
            return self._request([texts[0][:SAFE_CHUNK_CHARS]])

        # a batch of 1 is the reference, there is nothing to compare it against
        if not self.endpoint.verify_every_batch or len(texts) == 1:
            return vectors
        return self._verified(texts, vectors)

    def _verified(self, texts: list[str], vectors: list[list[float]]) -> list[list[float]]:
        """Return the batch, or re-embed it in halves when it cannot be reproduced.

        No fixed batch size is safe on an endpoint that needs this, so each batch is checked against
        the batch of 1 reference and halved on a mismatch, until it shrinks to a batch of 1.
        """
        mismatch = self._worst_mismatch(texts, vectors)
        with self.lock:
            self.batches += 1
            if mismatch:
                self.splits += 1
                self.worst_similarity = min(self.worst_similarity, mismatch[1])
        if not mismatch:
            return vectors
        index, similarity = mismatch
        # the magnitude matters: ~0.999 is batching noise, ~0.4 is a wrong vector
        logger.debug(
            f'batch of {len(texts)} not reproducible: item {index} ({len(texts[index])} chars) '
            f'similarity {similarity:.4f}, splitting'
        )
        return self._embed_halves(texts)

    def _embed_halves(self, texts: list[str]) -> list[list[float]]:
        """Embed the two halves of a batch separately, each checked in turn."""
        mid = len(texts) // 2
        return self.embed_batch(texts[:mid]) + self.embed_batch(texts[mid:])

    def _worst_mismatch(self, texts: list[str], vectors: list[list[float]]) -> tuple[int, float] | None:
        """Re-embed a few of the texts one at a time, looking for one that disagrees.

        Returns (index, similarity) of the worst disagreement, so the caller can report how bad it
        was. Costs VERIFY_SAMPLE_SIZE extra single text requests per batch.
        """
        worst: tuple[int, float] | None = None
        for i in random.sample(range(len(texts)), min(VERIFY_SAMPLE_SIZE, len(texts))):
            similarity = cosine_similarity(self._request([texts[i]])[0], vectors[i])
            if similarity < VERIFY_MIN_COSINE and (worst is None or similarity < worst[1]):
                worst = (i, similarity)
        return worst

    def check_batching(self, texts: list[str], sample: int = VERIFY_SAMPLE_SIZE) -> float:
        """Embed texts as one batch, re-embed a sample of them alone, and compare. Never automatic.

        The question it answers is whether this endpoint's batch_size is safe: a service that
        returns a different vector for a batched text than for the same text on its own is
        silently degrading every search that follows. Returns the worst cosine of the sample, so a
        caller can decide what to do; a correct endpoint sits at ~1.000000.
        """
        batched = self.embed_texts(texts)
        indexes = random.sample(range(len(texts)), min(sample, len(texts)))
        # embed_batch, not _request: it truncates a text the model finds too long instead of raising
        similarities = [cosine_similarity(self.embed_batch([texts[i]])[0], batched[i]) for i in indexes]
        worst = min(similarities)
        logger.info(
            f'batch of {len(texts)} on {self.endpoint.name}: {len(indexes)} of its texts re-embedded '
            f'alone, worst similarity {worst:.6f}'
        )
        return worst

    def _request(self, texts: list[str], retries: int = 3, rate_limit_retries: int = 8) -> list[list[float]]:
        """POST one embeddings request, retrying transient failures. Both counts are retries, not attempts.

        Being throttled has its own, larger budget: on a shared endpoint a 429 is the service
        working as intended, not a failure, and it is the one saying when to come back (see _wait).
        A hard failure keeps the small budget, there is little point hammering a broken endpoint.
        """
        payload: dict[str, Any] = {
            'model': self.model.name,
            'input': [self.model.doc_prefix + text for text in texts],
        }
        if self.endpoint.truncate_tokens:
            payload['truncate_prompt_tokens'] = self.endpoint.truncate_tokens
        failures, throttles = 0, 0
        while True:
            try:
                # (connect, read): a cold vLLM can take minutes to answer a large batch
                response = self.session.post(self.url, json=payload, timeout=(30, 300))
                response.raise_for_status()
                return self._vectors(response, texts)
            except requests.HTTPError as e:
                self._raise_if_fatal(e, texts)
                throttled = e.response is not None and e.response.status_code == 429
                spent, budget = (throttles, rate_limit_retries) if throttled else (failures, retries)
                if spent >= budget:
                    raise
                if throttled:
                    throttles += 1
                    with self.lock:
                        self.rate_limited += 1
                else:
                    failures += 1
                # a 429, like a 503, usually says when the endpoint will answer in Retry-After
                self._wait(spent, e, e.response)
            # RequestException covers the connection drops vLLM throws under a wide fan out
            except (requests.RequestException, ValueError, KeyError) as e:
                if failures >= retries:
                    raise
                failures += 1
                self._wait(failures - 1, e)

    def _vectors(self, response: requests.Response, texts: list[str]) -> list[list[float]]:
        """The embeddings of one answer, back in the order the texts were sent."""
        data = sorted(response.json()['data'], key=lambda d: d['index'])
        if len(data) != len(texts):
            raise ValueError(f'API returned {len(data)} embeddings for {len(texts)} texts')
        with self.lock:
            self.texts += len(texts)
            self.requests += 1
        return [d['embedding'] for d in data]

    @staticmethod
    def _raise_if_fatal(error: requests.HTTPError, texts: list[str]) -> None:
        """Raise the failures no retry can fix, and return for the ones a retry can.

        A 4xx that is not rate limiting will answer the same to the same payload: a text over the
        model context becomes a ContextWindowExceededError for embed_batch to split out, and
        anything else (a bad model name, a rejected key) ends the run rather than looping.
        """
        response = error.response
        if response is None or response.status_code == 429 or response.status_code >= 500:
            return
        if 'ContextWindowExceeded' in response.text or 'maximum context length' in response.text:
            raise ContextWindowExceededError(len(texts)) from error
        raise RuntimeError(f'embeddings request rejected: {response.text[:500]}') from error

    @staticmethod
    def _wait(attempt: int, error: Exception, response: requests.Response | None = None) -> None:
        """Wait before the next attempt: as long as the server asked, else exponentially longer."""
        asked = retry_after_seconds(response)
        wait = asked if asked is not None else min(float(2**attempt), MAX_RETRY_AFTER)
        source = 'Retry-After' if asked is not None else 'backoff'
        logger.warning(f'embeddings request failed ({error}), retrying in {wait:.0f}s ({source})')
        time.sleep(wait)

    def describe(self) -> str:
        """What this client embeds with, worth printing before a long run."""
        return (
            f'embedding with {self.model.name} ({self.model.dims} dims, '
            f'doc prefix {self.model.doc_prefix!r}) on {self.endpoint.name} at {self.url}, '
            f'{self.concurrency} parallel requests of {self.batch_size} texts'
        )

    def stats(self) -> str:
        """One line summary of the requests made and what any checking caught."""
        with self.lock:
            base = f'{self.texts} texts in {self.requests} requests, {self.endpoint.name}'
            if self.rate_limited:
                base += f', {self.rate_limited} rate limited'
            if self.endpoint.verify_every_batch:
                if not self.splits and not self.truncated:
                    return f'{base}, {self.batches} batches all reproducible'
                return (
                    f'{base}, {self.splits}/{self.batches} batches split '
                    f'(worst similarity {self.worst_similarity:.4f}), {self.truncated} texts truncated'
                )
            return base

    def __enter__(self) -> 'ApiEmbeddings':
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        """Close every session this client opened."""
        with self.lock:
            for session in self.sessions:
                session.close()
            self.sessions.clear()


def resolve_endpoint(name: str) -> ApiEndpoint:
    """Look up one of API_ENDPOINTS by name, failing with the valid choices rather than a KeyError."""
    try:
        return API_ENDPOINTS[name]
    except KeyError:
        raise ValueError(f'Unknown endpoint {name!r}, pick one of: {", ".join(API_ENDPOINTS)}') from None


def endpoint_api_key(endpoint: ApiEndpoint) -> str | None:
    """The bearer token for an endpoint, from the environment. None when it needs none."""
    return os.environ.get(endpoint.api_key_env) if endpoint.api_key_env else None


def build_embedder(
    endpoint_name: str = DEFAULT_ENDPOINT,
    *,
    base_url: str | None = None,
    concurrency: int | None = None,
) -> ApiEmbeddings:
    """Build the embeddings client for one of API_ENDPOINTS. The entry point for every caller.

    base_url and concurrency override the endpoint's defaults for this client only.
    """
    endpoint = resolve_endpoint(endpoint_name)
    api_key = endpoint_api_key(endpoint)
    if endpoint.api_key_env and not api_key:
        raise ValueError(f'Missing {endpoint.api_key_env} in the environment, needed for {endpoint.name}')
    return ApiEmbeddings(
        endpoint,
        api_key=api_key,
        concurrency=concurrency,
        base_url=base_url,
    )
