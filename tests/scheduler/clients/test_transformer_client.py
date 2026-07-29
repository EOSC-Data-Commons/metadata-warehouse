from scheduler.clients import transformer_client


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.raise_for_status_called = False

    def raise_for_status(self):
        self.raise_for_status_called = True

    def json(self):
        return self.payload


def test_get_endpoints_to_harvest_requests_active_scheduled_runs(monkeypatch):
    response = FakeResponse({'harvest_runs': []})
    calls = []

    def fake_get(url, params, timeout):
        calls.append({'url': url, 'params': params, 'timeout': timeout})
        return response

    monkeypatch.setattr(transformer_client, 'WAREHOUSE_API_URL', 'http://warehouse-api.test')
    monkeypatch.setattr(transformer_client.requests, 'get', fake_get)

    assert transformer_client.get_endpoints_to_harvest() == []
    assert calls == [
        {
            'url': 'http://warehouse-api.test/harvest_run',
            'params': {'only_active': True, 'respect_schedule': True},
            'timeout': 30,
        }
    ]
    assert response.raise_for_status_called is True


def test_get_endpoints_to_harvest_filters_unscheduled_and_invalid_runs(monkeypatch):
    response = FakeResponse(
        {
            'harvest_runs': [
                {
                    'harvest_url': 'https://hal.science/oai/oai.php',
                    'should_be_harvested': True,
                    'depends_on_endpoint_id': None,
                },
                {
                    'harvest_url': 'https://dabar.srce.hr/oai',
                    'should_be_harvested': False,
                    'depends_on_endpoint_id': None,
                },
                {
                    'harvest_url': None,
                    'should_be_harvested': True,
                    'depends_on_endpoint_id': None,
                },
            ]
        }
    )

    monkeypatch.setattr(transformer_client.requests, 'get', lambda *args, **kwargs: response)

    assert transformer_client.get_endpoints_to_harvest() == [
        'https://hal.science/oai/oai.php',
    ]


def test_get_endpoints_to_harvest_defers_dependent_runs_to_end(monkeypatch):
    response = FakeResponse(
        {
            'harvest_runs': [
                {
                    'harvest_url': 'https://zenodo.org/oai2d',
                    'should_be_harvested': True,
                    'depends_on_endpoint_id': 'hal-endpoint-id',
                },
                {
                    'harvest_url': 'https://hal.science/oai/oai.php',
                    'should_be_harvested': True,
                    'depends_on_endpoint_id': None,
                },
                {
                    'harvest_url': 'https://dependent.example.test/oai',
                    'should_be_harvested': True,
                    'depends_on_endpoint_id': 'other-master-id',
                },
            ]
        }
    )

    monkeypatch.setattr(transformer_client.requests, 'get', lambda *args, **kwargs: response)

    assert transformer_client.get_endpoints_to_harvest() == [
        'https://hal.science/oai/oai.php',
        'https://zenodo.org/oai2d',
        'https://dependent.example.test/oai',
    ]


def test_order_runs_by_dependency_preserves_transformer_order_inside_each_group():
    first_dependent = {'harvest_url': 'dependent-a', 'depends_on_endpoint_id': 'master-a'}
    first_independent = {'harvest_url': 'independent-a', 'depends_on_endpoint_id': None}
    second_dependent = {'harvest_url': 'dependent-b', 'depends_on_endpoint_id': 'master-b'}
    second_independent = {'harvest_url': 'independent-b'}

    assert transformer_client.order_runs_by_dependency(
        [
            first_dependent,
            first_independent,
            second_dependent,
            second_independent,
        ]
    ) == [
        first_independent,
        second_independent,
        first_dependent,
        second_dependent,
    ]
