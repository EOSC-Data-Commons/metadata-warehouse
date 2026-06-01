# Different approaches to enriching metadata
# A single method is not guaranteed to obtain new data for a specific record,
# a sequence of different attempts might yield best results
import requests
from lxml import etree as ET

def get_doi(raw_metadata: str):
    """
    Get DOI from raw_metadata XML, if available
    
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
        "https://api.openaire.eu/graph/v2/researchProducts",
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

# A GET request to the API can process multiple DOI pids at once - so we'll get results faster
# and avoid getting rate limited
# There is a complication that multiple DOIs can be linked to a single OpenAIRE id, so if we make
# a request with 100 DOIs we could get a resultset of 20 results.  
# Therefore, an additional step is needed where each resultset's subjects are
# linked to the original DOIs.

def _openaire_batch_doi_resolve(doi_list):
    """
    Query the OpenAIRE API to obtain more metadata for a given DOI.
    The API used: https://api.openaire.eu/graph/

    The resulting data has a "subjects" key which is the most interesting for providing keyword/discipline metadata.

    :param doi: string with DOI to check for more metadata.
    :return: a dict of metada or None if none available
    """

    # The pid parameter is case-insensitive, no need to adjust

    # If the DOI starts with http(s) strip the start of the string
    doi_list = [doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
                for doi
                in doi_list
        ]
    
    # For sending as a parameter, the OR operator can be written as commas between pids
    doi_param = ",".join(doi_list)


    response = requests.get(
        "https://api.openaire.eu/graph/v2/researchProducts",
        params={"pid": doi_param}, 
        timeout=10
    )
    data = response.json()
    # Results are always a list, even though this method is intended for single DOI and resultset
    results = data.get("results", [])
    
    return(results)
    

def _opeanaire_get_doi_subjects(response):
    """
    Get a batch of DOIS and their subjects for all API response elements.

    # TODO empty response format
    
    :param response: List[Dictionary response for a given openAIRE id]
    :return: List[dict]
        dict:
            [DOIs] - all DOIs linked to a single OpenAIRE id, for later joining
            [Subjects] - all subjects for those DOIs
    """
    if response == []:
        # no DOIs with any results
        return []
    
    # objects to be returned - each DOI that obtained new subjects
    enriched_dois = []
    enriched_subjects = []

    for el in response:
        res_subjects = el["subjects"]

        if (res_subjects is None or res_subjects == []):
            # this element doesn't contribute to enriching subjects
            continue

        current_pids = el["pids"]
        current_dois = [pid['value'] for pid in current_pids if pid['scheme'] == 'doi']

        enriched_dois.append(current_dois)

        # subjects have multiple fields, we are interested in text values
        print(res_subjects)
        #subjects_list = [sub['subject']['value'] for sub in res_subjects if sub != []]
        subjects_list = [sub['subject']['value'] for sub in res_subjects]

        enriched_subjects.append(subjects_list)

    # Create a list of dicts. If a single object has multiple DOIs, each should be a separate element

    doi_subjects = []

    for ix in range(len(enriched_dois)):
        for doi in enriched_dois[ix]:
            # each individual DOI will be a single dict with the same subjects
            doi_sub_pair = {'doi': doi,
                           'subjects': enriched_subjects[ix]}
            doi_subjects.append(doi_sub_pair)

    return doi_subjects

def batch_enrich_subjects_from_openaire(doi_list):
    api_results = _openaire_batch_doi_resolve(doi_list)
    # TODO - implement subjects to list for batch method
    openaire_subjects = _opeanaire_batch_get_subjects(api_result)
    
    # TODO - append relevant subjects to individual DOIs in list

    # List of following:
    #[
    # doi: str
    # subjects: [str]
    #]

    # Return a list
    return doi_subjects_list
