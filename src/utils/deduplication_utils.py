from typing import Any

PROVIDER_PRECEDENCE: dict[str, dict[str, Any]] = {
    'DANS': {
        'rank': 10,
        'harvest_urls': [
            'https://phys-techsciences.datastations.nl/oai',  # preferred DANS endpoint
            'https://archaeology.datastations.nl/oai',  # fallback
            'https://ssh.datastations.nl/oai',
            'https://lifesciences.datastations.nl/oai',
            'https://dataverse.nl/oai',
        ],
    },
    'ZENODO': {
        'rank': 20,
        'harvest_urls': [
            'https://zenodo.org/oai2d',
        ],
    },
    'HAL': {
        'rank': 30,
        'harvest_urls': [
            'https://api.archives-ouvertes.fr/oai/hal',
        ],
    },
    'DABAR': {
        'rank': 40,
        'harvest_urls': [
            'https://dabar.srce.hr/oai/',
        ],
    },
    'SWISS': {
        'rank': 50,
        'harvest_urls': [
            'https://www.swissubase.ch/oai-pmh/v1/oai',
        ],
    },
    'ONE': {
        'rank': 60,
        'harvest_urls': [
            'https://demo.onedata.org/oai_pmh',
        ],
    },
    'FINBIF': {
        'rank': 70,
        'harvest_urls': [
            'https://api.gbif.org',
        ],
    },
    'DATAVERSELV': {
        'rank': 80,
        'harvest_urls': [
            'https://dv.dataverse.lv/oai',
            'https://dataverse.rsu.lv/oai',
            'https://repository.clarin.lv/repository/oai/request',
        ],
    },
    'MDDB': {
        'rank': 90,
        'harvest_urls': [
            'https://mdposit.mddbr.eu/api/rest/v1',
        ],
    },
    'DASCH': {
        'rank': 100,
        'harvest_urls': [
            'https://repository.dasch.swiss/dpe/oai',
        ],
    },
    'EMPIAR': {
        'rank': 110,
        'harvest_urls': [
            'https://www.ebi.ac.uk/empiar/api/',
        ],
    },
    'PANOSC': {
        'rank': 120,
        'harvest_urls': [
            'https://data.cells.es/iws/icat_plus/oaipmh/request',  # ALBA
            'https://public-data.desy.de/oaipmh/oai',  # DESY
            'https://api.opendata.elettra.eu/oaipmh/',  # Elettra
            'https://icatplus.esrf.fr/oaipmh/request',  # ESRF
            'https://oai.panosc.ess.eu/openaire/oai',  # ESS
            'https://in.xfel.eu/metadata/oai-pmh/oai2',  # EuXFEL
            'https://data.helmholtz-berlin.de/oaipmh/request',  # HZB
            'https://rodare.hzdr.de/oai2d',  # HZDR
            'https://fairdata.ill.fr/openaire/oai',  # ILL
            'https://icat.isis.stfc.ac.uk/oaipmh/request',  # ISIS
            'https://scicat.maxiv.lu.se/openaire/oai',  # MAX IV
            'https://doi.psi.ch/oaipmh/oai',  # PSI
        ],
    },
}

UNKNOWN_RANK = 999


def _precedence_key(row: dict[str, Any]) -> tuple[int, int]:
    code_entry = PROVIDER_PRECEDENCE.get(row['code'])
    if code_entry is None:
        return UNKNOWN_RANK, UNKNOWN_RANK

    code_rank = code_entry['rank']
    harvest_urls = code_entry.get('harvest_urls', [])
    try:
        url_rank = harvest_urls.index(row['harvest_url'])
    except ValueError:
        url_rank = len(harvest_urls)  # known code, unlisted url -> lowest priority within that code

    return code_rank, url_rank


def pick_winner(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return min(rows, key=_precedence_key)
