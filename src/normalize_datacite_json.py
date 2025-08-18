from typing import Any

DATACITE = 'http://datacite.org/schema/kernel-4'
XML = 'http://www.w3.org/XML/1998/namespace'

def get_identifier(entry: dict, identifier_type: str):
    if identifier := entry.get(f'{DATACITE}:identifier'):
        if id_type := identifier.get(f'@identifierType'):
            if id_type == identifier_type and '#text' in identifier:
                return identifier['#text']

    #print(f'No DOI given for {entry}')
    return None

def harmonize_creator(entry: dict):
    '''
    Given an entry of 'datacite_creators', harmonizes its structure.

    :param entry: Given entry from 'creators':
    :return: A harmonized entry.
    '''

    cr = entry[f'{DATACITE}:creator']

    return {
        **harmonize_props(cr, f'{DATACITE}:creatorName', {'@nameType': 'nameType'}),
        **harmonize_props(cr, f'{DATACITE}:givenName', {}),
        **harmonize_props(cr, f'{DATACITE}:familyName', {}),
        **harmonize_props(cr, f'{DATACITE}:nameIdentifier', {'@nameIdentifierScheme': 'nameIdentifierScheme'})
    }


def harmonize_props(entry: dict, field_name: str, attr_map: dict):
    '''
    Give a dict and a field_name, returns a dict with that field's value in a harmonized format.

    :param entry: given dict.
    :param field_name: name of the field to harmonize.
    :param attr_map: key-value map or attribute names.
    :return: the specified field of the given dict in a harmonized format.
    '''
    #print(type(entry), field_name, entry)

    # ignore non-existing fields
    if field_name not in entry:
        return {}

    name = field_name[len(DATACITE) + 1:]

    if isinstance(entry[field_name], str):
        return {
            name: entry[field_name]
        }
    elif isinstance(entry[field_name], dict):
        harmonized_entry =  {}

        if '#text' in entry[field_name]:
            harmonized_entry[name] = entry[field_name]['#text']

        for k, v in attr_map.items():
            if entry[field_name].get(k) is not None:
                harmonized_entry[v] = entry[field_name][k]

        return harmonized_entry

    else:
        raise Exception('Neither string nor dict')


def make_object(subfield: list | dict, subfield_name: str):
    '''
    Given a subfield, turn it into a dict.

    :param subfield: subfield's value, could be a list of values or a single item.
    :param subfield_name: subfield's name, e.g., 'datacite:title' or 'datacite:subject'.
    :return: A dict for each subfield.
    '''
    if isinstance(subfield, list):
        res = list(map(lambda fi: {subfield_name: fi}, subfield))
        return res
    else:
        return [{subfield_name: subfield}]


def make_array(field: dict | list | None, subfield_name: str):
    '''
    Given a field value like 'datacite:titles' or 'datacite:subjects',
    returns an array of objects with the subfield name as an index.

    :param field: name of the field, e.g., 'datacite:titles' or 'datacite:subjects'.
    :param subfield_name: name og the subfield, e.g., 'datacite:title' or 'datacite:subject'.
    :return: a list of objects with the subfield name as an index.
    '''

    if field is None:
        return []

    if isinstance(field, dict):
        # field is a dict, thus the subfield is an object or a list
        res = list(map(lambda val: make_object(val, subfield_name), field.values()))
        return [x for sublist in res for x in sublist]
    elif isinstance(field, list):
        # field is a list
        return field
    else:
        raise Exception('Neither dict nor list')


def remove_empty_item(item: tuple[str, Any]):
    # only ignore None values and empty lists (do not rely on conversions to falsy/truthy)
    if isinstance(item[1], list):
        return len(item[1]) > 0
    else:
        return item[1] is not None

def normalize_datacite_json(input: dict):
    # print(json.dumps(input))

    try:
        res =  {
            'doi': get_identifier(input, 'DOI'),
            'url': get_identifier(input, 'URL'),
            'titles': list(map(lambda el: harmonize_props(el, f'{DATACITE}:title', {f'@{XML}:lang': 'lang', '@titleType': 'titleType' }), make_array(input.get(f'{DATACITE}:titles'), f'{DATACITE}:title'))),
            'subjects': list(map(lambda el: harmonize_props(el, f'{DATACITE}:subject', {f'@{XML}:lang': 'lang'}), make_array(input.get(f'{DATACITE}:subjects'), f'{DATACITE}:subject'))),
            'creators': list(map(lambda cr: harmonize_creator(cr), make_array(input.get(f'{DATACITE}:creators'), f'{DATACITE}:creator'))),
            'publicationYear': input.get('http://datacite.org/schema/kernel-4:publicationYear'),
            'descriptions': list(map(lambda el: harmonize_props(el, f'{DATACITE}:description', {'@descriptionType': 'descriptionType', f'@{XML}:lang': 'lang'}), make_array(input.get(f'{DATACITE}:descriptions'), f'{DATACITE}:description')))
        }

        # remove None values and empty lists
        return dict(filter(remove_empty_item, res.items()))

    except Exception as e:
        #print(f'Error {str(e)} when processing {input}', file=sys.stderr)
        raise e