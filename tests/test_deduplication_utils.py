from typing import Any

import pytest

from src.utils.deduplication_utils import PROVIDER_PRECEDENCE, UNKNOWN_RANK, _precedence_key, pick_winner


def _row(code: str, harvest_url: str, id_: int = 1) -> dict[str, Any]:
    return {'id': id_, 'code': code, 'harvest_url': harvest_url}


class TestPrecedenceKey:
    def test_known_code_preferred_url(self):
        row = _row('DANS', 'https://phys-techsciences.datastations.nl/oai')
        assert _precedence_key(row) == (10, 0)

    def test_known_code_fallback_url(self):
        row = _row('DANS', 'https://archaeology.datastations.nl/oai')
        assert _precedence_key(row) == (10, 1)

    def test_known_code_unlisted_url(self):
        row = _row('DANS', 'https://not-in-config.example.org/oai')
        harvest_urls = PROVIDER_PRECEDENCE['DANS']['harvest_urls']
        assert _precedence_key(row) == (10, len(harvest_urls))

    def test_unknown_code(self):
        row = _row('NOT_A_REAL_PROVIDER', 'https://example.org/oai')
        assert _precedence_key(row) == (UNKNOWN_RANK, UNKNOWN_RANK)

    def test_single_url_provider(self):
        row = _row('ZENODO', 'https://zenodo.org/oai2d')
        assert _precedence_key(row) == (20, 0)


class TestPickWinner:
    def test_higher_ranked_code_wins(self):
        dans_row = _row('DANS', 'https://phys-techsciences.datastations.nl/oai', id_=1)
        zenodo_row = _row('ZENODO', 'https://zenodo.org/oai2d', id_=2)

        winner = pick_winner([zenodo_row, dans_row])
        assert winner['id'] == 1  # DANS (rank 10) beats ZENODO (rank 20)

    def test_preferred_url_wins_within_same_code(self):
        preferred = _row('DANS', 'https://phys-techsciences.datastations.nl/oai', id_=1)
        fallback = _row('DANS', 'https://archaeology.datastations.nl/oai', id_=2)

        winner = pick_winner([fallback, preferred])
        assert winner['id'] == 1

    def test_known_code_beats_unknown_code(self):
        known = _row('HAL', 'https://api.archives-ouvertes.fr/oai/hal', id_=1)
        unknown = _row('SOME_NEW_PROVIDER', 'https://example.org/oai', id_=2)

        winner = pick_winner([unknown, known])
        assert winner['id'] == 1

    def test_known_code_unlisted_url_beats_unknown_code(self):
        # known code with an unlisted url still ranks by its code's rank first,
        # so it should still beat a completely unknown provider code.
        known_unlisted_url = _row('DABAR', 'https://not-configured.example.org/oai', id_=1)
        unknown_code = _row('SOME_NEW_PROVIDER', 'https://example.org/oai', id_=2)

        winner = pick_winner([unknown_code, known_unlisted_url])
        assert winner['id'] == 1

    def test_tie_returns_first_in_list_order(self):
        # identical code + harvest_url -> identical precedence key;
        # min() is stable and returns the first element encountered.
        row_a = _row('HAL', 'https://api.archives-ouvertes.fr/oai/hal', id_=1)
        row_b = _row('HAL', 'https://api.archives-ouvertes.fr/oai/hal', id_=2)

        winner = pick_winner([row_a, row_b])
        assert winner['id'] == 1

        winner_reversed = pick_winner([row_b, row_a])
        assert winner_reversed['id'] == 2

    def test_multiple_providers_lowest_rank_wins_overall(self):
        rows = [
            _row('PANOSC', 'https://icat.isis.stfc.ac.uk/oaipmh/request', id_=1),
            _row('EMPIAR', 'https://www.ebi.ac.uk/empiar/api/', id_=2),
            _row('DANS', 'https://phys-techsciences.datastations.nl/oai', id_=3),
            _row('ZENODO', 'https://zenodo.org/oai2d', id_=4),
        ]

        winner = pick_winner(rows)
        assert winner['id'] == 3  # DANS has the lowest rank (10) of the group

    def test_single_row_group_returns_that_row(self):
        row = _row('HAL', 'https://api.archives-ouvertes.fr/oai/hal', id_=1)
        winner = pick_winner([row])
        assert winner['id'] == 1

    @pytest.mark.parametrize(
        'code,harvest_url,expected_key',
        [
            ('DANS', 'https://phys-techsciences.datastations.nl/oai', (10, 0)),
            ('ZENODO', 'https://zenodo.org/oai2d', (20, 0)),
            ('PANOSC', 'https://doi.psi.ch/oaipmh/oai', (120, 11)),  # last url in PANOSC's list
        ],
    )
    def test_precedence_key_parametrized(self, code, harvest_url, expected_key):
        assert _precedence_key(_row(code, harvest_url)) == expected_key
