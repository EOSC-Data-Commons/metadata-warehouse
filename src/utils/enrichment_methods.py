# Different approaches to enriching metadata
# A single method is not guaranteed to obtain new data for a specific record,
# a sequence of different attempts might yield best results
import requests

def openaire_doi_get_info(doi):
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