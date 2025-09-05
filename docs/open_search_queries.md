# OpenSearch Sample Queries

This page contains some sample queries illustrating the possibilities and schema usage.
These queries can be run from the command line directly with curl 

```commandline
curl '127.0.0.1:9200/test_datacite/_search' -H 'Content-Type: application/json' -d '{
    ...
  }' | jq
```

or from the OpenSearch Dashboards[ dev tools](https://docs.opensearch.org/latest/dashboards/dev-tools/index-dev/):

```commandline
GET /test_datacite/_search
{
 ...
}
```

The sample queries are based on the OpenSearch [mapping](../src/config/opensearch_mapping.json).

## Lexical Queries

### Simple Field Queries

#### Searching for a Title

The field `_title` is a virtual field created at indexing containing the title string without any of its attributes.
The original field title contains an object (nested field) and requires a nested query, see below.

```json
{
  "query": {
    "query_string": {
          "default_operator": "AND",
          "default_field": "_title",
          "query": "math*"
        }
  }
}
```

#### Searching for Several Fields

The field `_all_fields` is a virtual field created at indexing combining several fields such as title, subject, description etc.

```json
{
  "query": {
    "query_string": {
          "default_operator": "AND",
          "default_field": "_all_fields",
          "query": "math*"
        }
  }
}
```

### Query for a Nested Field

As `title` is a nested field, this requires a nested query:

#### Query for Titles in a Given Language

This searches for documents that have at least one title tagged as English:

```json
{
  "query": {
    "nested": {
      "path": "titles",
      "query": {
        "match": {
          "titles.lang": "en"
        }
      }
    }
  }
}
```

This can also be combined with a query string using a boolean query:

```json
{
  "query": {
    "nested": {
      "path": "titles",
      "query": {
        "bool": {
          "must": [
            {
              "match": {
                "titles.lang": "en"
              }
            },
            {
              "query_string": {
                "default_operator": "AND",
                "query": "farm*",
                "default_field": "titles.title"
              }
            }
          ]
        }
      }
    }
  }
}

```

#### Query for a Date Range on a Specific Datetype

This searches for a date range on a specific type of date:

```json
{
  "query": {
    "nested": {
      "path": "dates",
      "query": {
        "bool": {
          "must": [
            {
              "range": {
                "dates.date": {
                  "lte": "1969-03-01",
                  "format": "yyyy-MM-dd"
                }
              }
            },
            {
              "match": {
                "dates.dateType": "Collected"
              }
            }
          ]
        }
      }
    }
  }
}
```
