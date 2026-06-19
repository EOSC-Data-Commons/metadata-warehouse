# Different approaches to enriching metadata
# A single method is not guaranteed to obtain new data for a specific record,
# a sequence of different attempts might yield best results
import requests
from lxml import etree as ET
import time
import copy

def get_doi(raw_metadata: str):
    """
    Get DOI from raw_metadata XML, if available
    
    TODO: remove, we have a doi field in the records table

    :param raw_metadata: string obtained from records.raw_metadata
    :return: a string with the record's DOI, like '10.15151/ESRF-ES-1872173799'
    """
    # raw_metadata gets treated as string, transform into XML tree
    rec = ET.ElementTree(ET.fromstring(raw_metadata))
    doi = rec.xpath("//*[local-name()='identifier'][@identifierType='DOI']/text()")

    if doi == []:
        return None
    else: 
        return doi[0]

# Enrich via OpenAIRE API, resolve record's DOI ----

OPENAIRE_API_URL = "https://api.openaire.eu/graph/v2/researchProducts"

def enrich_subjects_from_openaire(doi):
    api_result = _openaire_doi_resolve(doi)
    subjects = _opeanaire_get_subjects(api_result)

    return _opeanaire_subjects_to_list(subjects)

def _openaire_doi_resolve(doi):
    """
    Query the OpenAIRE API to obtain more metadata for a given DOI.
    The API used: https://api.openaire.eu/graph/

    The resulting data has a "subjects" key which is the most interesting for providing keyword/discipline metadata.

    :param doi: string with DOI to check for more metadata.
    :return: a dict of metada or None if none available
    """

    # If the DOI starts with http(s) strip the start of the string
    doi_param = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")

    # It seems the pid parameter is case-insensitive

    response = requests.get(
        OPENAIRE_API_URL,
        params={"pid": doi_param}, 
        timeout=10
    )
    data = response.json()
    # Results are always a list, even though this method is intended for single DOI and resultset
    results = data.get("results", [])
    if results == []:
        return {}
    else:
        return results[0]

def _opeanaire_get_subjects(response):
    """
    Get the list of subjects from an OpenAIRE response.
    If the response had no data for given DOI, or if the response is present but has no subject, return an empty list.

    :param response: Dictionary gathered from openaire_doi_get_info() for a single DOI.
    :return: a list of dicts, one element for each subject gathered.
        The dicts are of a format:
        {
        'subject': {'scheme': 'keyword', 'value': 'keyword text'},
        'provenance': None
        }
        We are primarily interested in ['subject']['value']
    """
    if response == {}:
        # list of subjects for this record: empty
        return []
    
    subjects = response["subjects"]
    if subjects is None:
        # also an empty list, for consistency
        subjects = []

    return subjects


def _opeanaire_subjects_to_list(subjects_list):
    """
    Turn the list of subjects recieved from _opeanaire_get_subjects() into
    a list of strings.
    """
    return [sub['subject']['value'] for sub in subjects_list if sub != []]


# ALTERNATIVE - BATCH OpenAIRE requests

# A GET request to the API can process up to 10 DOI pids at once - so we'll get results faster
# and avoid getting rate limited
# There is a complication that multiple DOIs can be linked to a single OpenAIRE id and the response
# would then return a smaller number of results
# Therefore, an additional step is needed where each resultset's subjects are
# linked to the original DOIs.

def _openaire_batch_doi_resolve(doi_list: list[str]):
    """
    Query the OpenAIRE API to obtain more metadata for given DOIs.
    The API used: https://api.openaire.eu/graph/

    The resulting payload has a "subjects" key which is the most interesting for providing keyword/discipline metadata.
    We cannot guess the length of the resulting list in advance, it can be shorter than the list of DOIs:
    1) if there is no info for a given DOI, it will not appear in results. If none of the DOIs have info, the result is an empty list.
    2) if multiple DOIs are linked to a single OpenAIRE id, they will all result in a single result element.

    :param doi: List[str], DOIs to check for more metadata.
    :return: List[dict] of metadata
    """

    results = []
    # The API can only process 10 DOIs at once, so we need to send the requests in batches
    # We'll then extend the resultset for each batch
    for i in range(0, len(doi_list), 10):
        batch = doi_list[i:i + 10]

        # The pid parameter is case-insensitive, no need to adjust

        # If the DOI starts with http(s) strip the start of the string
        dois = [doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
                    for doi
                    in batch
            ]
        
        # For sending as a parameter, the OR operator can be written as commas between pids
        doi_param = ",".join(dois)


        response = requests.get(
            OPENAIRE_API_URL,
            params={"pid": doi_param}, 
            timeout=30
        )
        data = response.json()

        batch_results = data.get("results", [])

        results.extend(batch_results)

        # Wait a bit, to not overwhelm the API
        time.sleep(0.5)
    
    return(results)
    

def _opeanaire_get_doi_subjects(response: list[dict]):
    """
    Transform API response into a list of DOI-sets and their subject-sets.

    A single OpenAIRE ID will result in one or more DOIs and zero or more subjects.
    If is has no linked subjects, we can't enrich anything so we skip that ID entirely.
    The OpenAIRE ID itself doesn't concern us so it is not retained. 
    
    :param response: List[dict], the API response
    :return: List[dict]
        dict:
            DOI - DOI that is linked to at least one subject
            [Subjects] - all subjects for the given DOI
    """
    if response == []:
        # no DOIs with any results
        return []
    
    # sets of DOIs with relevant sets of subjects. Later, spread to individual DOIs
    enriched_dois = []
    enriched_subjects = []

    for el in response:
        res_subjects = el["subjects"]
        if (res_subjects is None or res_subjects == []):
            # this element doesn't contribute to enriching subjects,
            # so even the DOIs don't matter
            continue

        current_pids = el["pids"]
        
        current_dois = [pid['value'] for pid in current_pids if pid['scheme'] == 'doi']

        enriched_dois.append(current_dois)

        # subjects have multiple fields, we are interested in text values
        subjects_list = [sub['subject']['value'] for sub in res_subjects]

        enriched_subjects.append(subjects_list)

    # Create a list of dicts. If a single object has multiple DOIs, they are spread to separate elements

    doi_subjects = []

    for ix in range(len(enriched_dois)):
        for doi in enriched_dois[ix]:
            # each individual DOI in the list will create a separate dict with the same subjects
            doi_sub_pair = {'doi': doi,
                           'subjects': enriched_subjects[ix]}
            doi_subjects.append(doi_sub_pair)

    return doi_subjects

def _ids_connect_with_openaire_subjects(id_dois: list[dict],
                                        doi_subjects: list[dict]):
    """
    Connect id-doi from database to relevant doi-subject list.

    The first parameter is what we can obtain from our database. The second
    is metadata the OpenAIRE API can supply for these records.
    This function joins them via the common factor, the DOI.

    This is necessary because the API response condenses multiple DOIs into a single element, so we don't
    have a 1-1 relationship between our initial records and API-enriched subject lists.

    TODO: rework, we also use this for OpenAlex

    :param id_dois: List[dict: 
        {'id': str, record id from database,
        'doi': str, record DOI
        }
    ]
    
    :param doi_subjects: List[dict: 
        {'doi': str, record DOI,
        'subjects': List[str], subjects from API response
        }
    ]

    :return: List[dict:
        {'id': str, record id from database,
        'doi': str, record DOI,
        'enriched_subjects': None/set[str], subjects from API response
        }
    ]
    """
    output_list = copy.deepcopy(id_dois)

    for ix in range(len(output_list)):
        # It's possible that the database DOI and API doi differ in capitalisation,
        # so we'll use lowercase versions of both for joining

        current_doi = output_list[ix]['doi'].lower()
        
        matched_subjects = next(
        # Generator expression, next() stops at the first match
            (item['subjects'] for item in doi_subjects if item['doi'].lower() == current_doi),
            None
        )
        # Turn it into a set, to prevent multiple enrichment methods from
        # repeatedly adding the same subjects from multiple sources
        if matched_subjects:
            matched_subjects = set(matched_subjects)
        
        # Add a new key to the dicts with database ID
        output_list[ix]['enriched_subjects'] = matched_subjects
    
    return(output_list)


def batch_enrich_subjects_from_openaire(records_id_doi: list[dict]):
    """
    :param records_id_doi: List[dict: 
        {'id': str, record id from database,
        'doi': str, record DOI
        }
    ]
    :return: List[dict] like input, with new key:
            'enriched_subjects': None/set[str]
    """
    
    dois_to_enrich = [rec['doi'] for rec in records_id_doi]
    api_result = _openaire_batch_doi_resolve(dois_to_enrich)

    doi_subjects = _opeanaire_get_doi_subjects(api_result)

    # Don't alter the input
    output_list = copy.deepcopy(records_id_doi)
    output_list = _ids_connect_with_openaire_subjects(output_list, doi_subjects)

    # List of following:
    #[
    # id: str
    # doi: str
    # enriched_subjects: {str}
    #]
    return output_list


# Enrich via OpenAlex API by records' DOI ----

# The kind of subjects we can get from OpenAlex: Keywords and Topics
#   https://help.openalex.org/hc/en-us/articles/24736201130391-Keywords
#   https://help.openalex.org/hc/en-us/articles/24736129405719-Topics
# Both are generated by openAlex via machine learning! Matching potential keywords/topics to
# a record's metadata based on its title and abstract. Topics: also inclcude citations and journal name.

# That is why they have an associated score representing match similarity, and so we
# introduce a score treshold to get fewer, better matching subjects.
# TODO: state suggestion for default value and implement it as new default

OPENALEX_API_URL = "https://api.openalex.org/works"

def _openalex_batch_doi_resolve(dois: list[str], api_key: str):
    all_results = []
    chunk_size = 100

    # Strip any existing https://doi.org/ or http://doi.org/ prefix
    # so we can add it back consistently for every DOI
    clean_dois = [
        doi.replace("https://doi.org/", "")
           .replace("http://doi.org/", "")
        for doi in dois
    ]

    for i in range(0, len(clean_dois), chunk_size):
        chunk = clean_dois[i : i + chunk_size]

        # Join with pipe — each DOI gets the full https://doi.org/ prefix
        doi_filter = "|".join(f"https://doi.org/{doi}" for doi in chunk)
        # Build URL as f-string to avoid requests encoding the colons and pipes
        url = f"{OPENALEX_API_URL}?filter=doi:{doi_filter}&per_page={chunk_size}&api_key={api_key}"

        response = requests.get(url, timeout=30)
        response.raise_for_status()
        all_results.extend(response.json().get("results", []))

    return all_results

def _opeanalex_get_doi_subjects(response: list[dict], score_treshold: float = 0.5):
    """
    Transform API response into a list of DOIs and their subject-sets.

    OpenAlex responses have 3 machine-derived fields of interest:
    topics, keywords, concepts

    Concepts are a legacy version of keywords so we'll skip those.
    We'll consider keywords and concepts as subjects of interest. We'll further filter them out by similarity score.
    
    :param response: List[dict], the API response
    :param score_treshold: float, minimum similarity score a topic/keyword must have to be included as a subject
    :return: List[dict]
        dict:
            DOI - DOI that is linked to at least one subject
            [Subjects] - all subjects for the given DOI
    """
    if response == []:
        # no DOIs with any results
        return []
    
    # sets of DOIs with relevant sets of subjects. Later, spread to individual DOIs
    enriched_dois = []
    enriched_subjects = []

    for el in response:
        kw_list = el['keywords']
        top_list = el['topics']

        if ((kw_list + top_list) == []):
            # this element doesn't contribute to enriching subjects,
            # so even the DOIs don't matter
            continue

        keywords = [item['display_name'] for item in kw_list if item['score'] >= score_treshold]
        topics = [item['display_name'] for item in top_list if item['score'] >= score_treshold]

        # We'll consider both as subjects
        subjects = keywords + topics

        # Since we filtered by score it's possible that no keywords/topics are left,
        # if so, no enrichment will happen for this DOI
        if not subjects:
            continue
        
        current_doi = el['doi']

        # Strip DOI from prefixes and make it lowercase
        current_doi = current_doi.replace("https://doi.org/", "").replace("http://doi.org/", "").lower()

        enriched_dois.append(current_doi)

        enriched_subjects.append(subjects)

    # Create a list of dicts as output

    doi_subjects = []

    for ix in range(len(enriched_dois)):
        doi_sub_pair = {'doi': enriched_dois[ix],
                        'subjects': enriched_subjects[ix]}
        doi_subjects.append(doi_sub_pair)

    return doi_subjects

def batch_enrich_subjects_from_openalex(records_id_doi: list[dict], 
                                        api_key: str,
                                        score_treshold: float = 0.5):
    """
    :param records_id_doi: List[dict: 
        {'id': str, record id from database,
        'doi': str, record DOI
        }
    ]
    :param api_key: str, API key for communicating with OpenAlex API
    :param score_treshold: float, minimum similarity score a topic/keyword must have to be included as a subject
    :return: List[dict] like input, with new key:
            'enriched_subjects': None/set[str]
    """
    
    dois_to_enrich = [rec['doi'] for rec in records_id_doi]
    api_result = _openalex_batch_doi_resolve(dois_to_enrich, api_key)

    doi_subjects = _opeanalex_get_doi_subjects(api_result, score_treshold)

    # Don't alter the input
    output_list = copy.deepcopy(records_id_doi)
    output_list = _ids_connect_with_openaire_subjects(output_list, doi_subjects)

    # List of following:
    #[
    # id: str
    # doi: str
    # enriched_subjects: {str}
    #]
    return output_list