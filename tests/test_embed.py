"""Tests for the parts of the embeddings client that need no endpoint."""

import json
import unittest
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from typing import Any
from unittest.mock import patch

import requests

from src.transform.embed import (
    API_ENDPOINTS,
    MAX_RETRY_AFTER,
    ApiEmbeddings,
    ContextWindowExceededError,
    cosine_similarity,
    retry_after_seconds,
)


def response(retry_after: str | None) -> requests.Response:
    """A response carrying just the header under test."""
    res = requests.Response()
    res.status_code = 429
    if retry_after is not None:
        res.headers['Retry-After'] = retry_after
    return res


class TestRetryAfter(unittest.TestCase):
    def test_delta_seconds(self):
        self.assertEqual(retry_after_seconds(response('30')), 30.0)

    def test_http_date(self):
        when = datetime.now(UTC) + timedelta(seconds=40)
        # HTTP dates have a one second resolution, so the parsed delta is 39.x
        self.assertAlmostEqual(retry_after_seconds(response(format_datetime(when))) or 0, 40.0, delta=1.5)

    def test_a_date_in_the_past_does_not_wait(self):
        past = format_datetime(datetime.now(UTC) - timedelta(minutes=5))
        self.assertEqual(retry_after_seconds(response(past)), 0.0)

    def test_capped(self):
        self.assertEqual(retry_after_seconds(response('7200')), MAX_RETRY_AFTER)

    def test_no_header_or_no_response_falls_back(self):
        self.assertIsNone(retry_after_seconds(response(None)))
        self.assertIsNone(retry_after_seconds(None))

    def test_unparsable_header_falls_back(self):
        self.assertIsNone(retry_after_seconds(response('soon')))
        self.assertIsNone(retry_after_seconds(response('')))


def api_response(status: int, *, vectors: int = 0, body: str = '') -> requests.Response:
    """One answer from the embeddings API, or one of its errors."""
    res = requests.Response()
    res.status_code = status
    if vectors:
        res._content = json.dumps({'data': [{'index': i, 'embedding': [0.1, 0.2]} for i in range(vectors)]}).encode()
    else:
        res._content = (body or f'{{"error": "status {status}"}}').encode()
    return res


class FakeSession:
    """Hands out canned answers in order, counting the posts."""

    def __init__(self, responses: list[requests.Response]):
        self.responses = responses
        self.posts = 0

    def post(self, url: str, **_kwargs: Any) -> requests.Response:
        self.posts += 1
        return self.responses.pop(0)


def embedder_with(responses: list[requests.Response]) -> ApiEmbeddings:
    """A client whose session answers from a list, no endpoint involved."""
    embedder = ApiEmbeddings(API_ENDPOINTS['ferro'])
    embedder.local.session = FakeSession(responses)
    return embedder


@patch('src.transform.embed.time.sleep')
class TestRetryBudgets(unittest.TestCase):
    """A 429 draws on its own budget, larger than the one a hard failure spends."""

    def test_rate_limiting_survives_more_retries_than_a_hard_failure(self, sleep):
        embedder = embedder_with([api_response(429)] * 5 + [api_response(200, vectors=1)])
        self.assertEqual(len(embedder._request(['a'])), 1)
        self.assertEqual(embedder.rate_limited, 5)
        self.assertEqual(sleep.call_count, 5)

    def test_rate_limiting_gives_up_after_its_budget(self, _sleep):
        embedder = embedder_with([api_response(429)] * 20)
        with self.assertRaises(requests.HTTPError):
            embedder._request(['a'], rate_limit_retries=8)
        # the first attempt is not a retry
        self.assertEqual(embedder.local.session.posts, 9)

    def test_a_server_error_keeps_the_small_budget(self, _sleep):
        embedder = embedder_with([api_response(503)] * 20)
        with self.assertRaises(requests.HTTPError):
            embedder._request(['a'], retries=3)
        self.assertEqual(embedder.local.session.posts, 4)
        self.assertEqual(embedder.rate_limited, 0)

    def test_being_throttled_does_not_spend_the_failure_budget(self, _sleep):
        responses = [api_response(429), api_response(503), api_response(429), api_response(503)]
        responses += [api_response(429), api_response(503), api_response(200, vectors=1)]
        embedder = embedder_with(responses)
        self.assertEqual(len(embedder._request(['a'], retries=3, rate_limit_retries=8)), 1)

    def test_a_too_long_text_is_not_retried(self, _sleep):
        embedder = embedder_with([api_response(400, body='{"error": "maximum context length"}')])
        with self.assertRaises(ContextWindowExceededError):
            embedder._request(['a'])
        self.assertEqual(embedder.local.session.posts, 1)

    def test_a_rejected_request_is_not_retried(self, _sleep):
        embedder = embedder_with([api_response(401, body='{"error": "invalid api key"}')])
        with self.assertRaisesRegex(RuntimeError, 'invalid api key'):
            embedder._request(['a'])
        self.assertEqual(embedder.local.session.posts, 1)

    def test_a_short_answer_is_retried(self, _sleep):
        embedder = embedder_with([api_response(200, vectors=1), api_response(200, vectors=2)])
        self.assertEqual(len(embedder._request(['a', 'b'])), 2)


class TestCosineSimilarity(unittest.TestCase):
    def test_identical_vectors_match(self):
        self.assertAlmostEqual(cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]), 1.0)

    def test_scale_does_not_matter(self):
        self.assertAlmostEqual(cosine_similarity([1.0, 2.0], [2.0, 4.0]), 1.0)

    def test_orthogonal_and_zero_vectors(self):
        self.assertAlmostEqual(cosine_similarity([1.0, 0.0], [0.0, 1.0]), 0.0)
        self.assertEqual(cosine_similarity([0.0, 0.0], [1.0, 1.0]), 0.0)


if __name__ == '__main__':
    unittest.main()
