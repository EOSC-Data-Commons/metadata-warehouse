import sys
import datetime
from typing import Any, Callable

DATACITE = 'http://datacite.org/schema/kernel-4'
XML = 'http://www.w3.org/XML/1998/namespace'
DATE_FORMAT = '%Y-%m-%d'


def get_identifier(entry: dict[str, Any], identifier_type: str) -> Any | None:
    if identifier := entry.get(f'{DATACITE}:identifier'):
        if id_type := identifier.get(f'@identifierType'):
            if id_type == identifier_type and '#text' in identifier:
                return identifier['#text']

    # print(f'No DOI given for {entry}')
    return None


def harmonize_creator(entry: dict[str, Any]) -> dict[str, Any]:
    '''
    Given an entry of 'datacite_creators', harmonizes its structure.

    :param entry: Given entry from 'creators':
    :return: A harmonized entry.
    '''

    cr = entry[f'{DATACITE}:creator']

    return {
        **harmonize_props(cr, f'{DATACITE}:creatorName', {'@nameType': 'nameType'}, {}),
        **harmonize_props(cr, f'{DATACITE}:givenName', {}, {}),
        **harmonize_props(cr, f'{DATACITE}:familyName', {}, {}),
        **harmonize_props(cr, f'{DATACITE}:nameIdentifier', {'@nameIdentifierScheme': 'nameIdentifierScheme'}, {})
    }


def harmonize_props(entry: dict[str, Any], field_name: str, attr_map: dict[str, str],
                    normalization: dict[str, Callable[[Any], Any]]) -> dict[str, Any]:
    '''
    Give a dict and a field_name, returns a dict with that field's value in a harmonized format.

    :param entry: given dict.
    :param field_name: name of the field to harmonize.
    :param attr_map: key-value map or attribute names.
    :param normalization dict of field names to functions that normalize the value of the given field.
    :return: the specified field of the given dict in a harmonized format.
    '''
    # print(type(entry), field_name, entry)

    # ignore non-existing fields
    if field_name not in entry:
        return {}

    name = field_name[len(DATACITE) + 1:]

    if isinstance(entry[field_name], str):
        if name in normalization:
            return {
                name: normalization[name](entry[field_name])
            }
        else:
            return {
                name: entry[field_name]
            }
    elif isinstance(entry[field_name], dict):
        harmonized_entry = {}

        if '#text' in entry[field_name]:
            if name in normalization:
                harmonized_entry[name] = normalization[name](entry[field_name]['#text'])
            else:
                harmonized_entry[name] = entry[field_name]['#text']

        for k, v in attr_map.items():
            if entry[field_name].get(k) is not None:
                harmonized_entry[v] = entry[field_name][k]

        return harmonized_entry

    else:
        raise Exception('Neither string nor dict')


def make_object(subfield: list[dict[str, Any]] | dict[str, Any], subfield_name: str) -> list[dict[str, Any]]:
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


def make_array(field: dict[str, Any] | list[dict[str, Any]] | None, subfield_name: str) -> list[dict[str, Any]]:
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


def remove_empty_item(item: tuple[str, Any]) -> bool:
    # only ignore None values and empty lists (do not rely on conversions to falsy/truthy)
    if isinstance(item[1], list):
        return len(item[1]) > 0
    else:
        return item[1] is not None


def normalize_date_precision(date_str: str) -> str:
    if len(date_str) == 10:
        # day precision
        try:
            # will raise an exception if the date str does not conform to the expected format
            datetime.datetime.strptime(date_str, DATE_FORMAT)
        except ValueError as e:
            print(f'Date {date_str} invalid: {e}', file=sys.stderr)
            raise e
        return date_str
    elif len(date_str) == 7:
        # month precision
        return f'{date_str}-01'
    elif len(date_str) == 4:
        # year precision
        return f'{date_str}-01-01'
    else:
        # day and/or month without leading zero
        parts = date_str.split('-')

        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 else 1
        day = int(parts[2]) if len(parts) > 2 else 1

        try:
            normalized_date = datetime.datetime(year, month, day).strftime(DATE_FORMAT)
            #print(f'{date_str}, {parts}, {normalized_date}')
        except Exception as e:
            print(f'Could not normalize date: {date_str}, {parts} {e}', file=sys.stderr)
            raise e
        return normalized_date

def normalize_date_string(date_str: str) -> str:
    if ' ' in date_str:
        # date contains date time: 2025-07-15 09:46:15
        return normalize_date_precision(date_str.split(' ')[0])
    elif '/' in date_str:
        # date is a period: 2021-11-08/2021-11-23
        return normalize_date_precision(date_str.split('/')[0])
    else:
        # date may not have day precision
        return normalize_date_precision(date_str)


def normalize_datacite_json(input: dict[str, Any]) -> dict[str, Any]:
    # print(json.dumps(input))

    try:
        res = {
            'doi': get_identifier(input, 'DOI'),
            'url': get_identifier(input, 'URL'),
            'titles': list(map(lambda el: harmonize_props(el, f'{DATACITE}:title',
                                                          {f'@{XML}:lang': 'lang', '@titleType': 'titleType'}, {}),
                               make_array(input.get(f'{DATACITE}:titles'), f'{DATACITE}:title'))),
            'subjects': list(map(lambda el: harmonize_props(el, f'{DATACITE}:subject',
                                                            {f'@{XML}:lang': 'lang', '@subjectScheme': 'subjectScheme',
                                                             '@schemeURI': 'schemaUri', '@valueURI': 'valueUri',
                                                             '@classificationCode': 'classificationCode'}, {}),
                                 make_array(input.get(f'{DATACITE}:subjects'), f'{DATACITE}:subject'))),
            'creators': list(map(lambda cr: harmonize_creator(cr),
                                 make_array(input.get(f'{DATACITE}:creators'), f'{DATACITE}:creator'))),
            'publicationYear': input.get(f'{DATACITE}:publicationYear'),
            'descriptions': list(map(lambda el: harmonize_props(el, f'{DATACITE}:description',
                                                                {'@descriptionType': 'descriptionType',
                                                                 f'@{XML}:lang': 'lang'}, {}),
                                     make_array(input.get(f'{DATACITE}:descriptions'), f'{DATACITE}:description'))),
            'dates': list(map(lambda el: harmonize_props(el, f'{DATACITE}:date', {'@dateType': 'dateType'},
                                                         {'date': normalize_date_string}),
                              make_array(input.get(f'{DATACITE}:dates'), f'{DATACITE}:date')))
        }

        # remove None values and empty lists
        return dict(filter(remove_empty_item, res.items()))

    except Exception as e:
        # print(f'Error {str(e)} when processing {input}', file=sys.stderr)
        raise e
