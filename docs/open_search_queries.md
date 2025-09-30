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

Local OpenSearch Dashboard URL: http://127.0.0.1:5601

## Specify the Source

In the query, `_source` can be used to specify which fields of the [source](https://docs.opensearch.org/latest/field-types/metadata-fields/source/) should be returned:

```json
{
     "_source": ["titles.title", "subjects.subject", "descriptions.description"],
    "query": {
        ...
    }
}
```

## Lexical Queries

### Simple Field Queries

See [docs](https://docs.opensearch.org/latest/query-dsl/full-text/index/) for an overview of full text query types.

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

See [docs](https://docs.opensearch.org/latest/query-dsl/joining/nested/) for further explanation of nested queries.

#### Query for Titles in a Given Language

As `titles.title` is a nested field, this requires a nested query.
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

This can also be combined with a query string using a [Boolean query](https://docs.opensearch.org/latest/query-dsl/compound/bool/):

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

This searches for a [date range](https://docs.opensearch.org/latest/query-dsl/term/range/) on a specific type of date:  

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

### KNN Queries

These queries require a vector embedding calculated with the same model used for the indexed documents.

#### Search for Similar Documents

Given a vector embedding, this query searches for the [5 most similar](https://docs.opensearch.org/latest/query-dsl/specialized/k-nn/index/) documents.

```json
{
    "size": 5,
    "query": {
        "knn": {
            "emb": {
                "vector": [...], # vector embedding for query string
                "k": 5
            }
        }
    }
}
```
In addition, a [filter](https://docs.opensearch.org/latest/vector-search/filter-search-knn/efficient-knn-filtering/#step-3-search-your-data-with-a-filter) can be applied:

```json
{
  "size": 5,
  "query": {
    "knn": {
      "emb": {
        "vector": [...], # vector embedding for query string
        "k": 5,
        "filter": {
          "bool": {
            "must": [
              {
                "range": {
                  "publicationYear": {
                    "gte": "2022",
                    "format": "year"
                  }
                }
              }
            ]
          }
        }
      }
    }
  }
}

```

### Hybrid Queries

A [hybrid query](https://docs.opensearch.org/latest/query-dsl/compound/hybrid/) combines different query types, e.g., a knn vector query and a lexical query. 

#### Searching for Similar Documents and a Lexical Hit

This hybrid query combines a knn query (first query) with a query string query (second query). 
Since the two queries return different scores, a [normalization processor](https://docs.opensearch.org/latest/vector-search/ai-search/hybrid-search/index/#step-3-configure-a-search-pipeline) is needed. 
For each of the two queries, a weight can be defined (order of the query parts is deterministic) influencing the resulting score of each document.
See this [article](https://opster.com/guides/opensearch/opensearch-machine-learning/opensearch-hybrid-search/) for further explanation.


```json
{
  "search_pipeline": {
    "phase_results_processors": [
      {
        "normalization-processor": {
          "normalization": {
            "technique": "min_max"
          },
          "combination": {
            "technique": "arithmetic_mean",
            "parameters": {
              "weights": [
                0.7, # knn query part
                0.3 # lexical query part
              ]
            }
          }
        }
      }
    ]
  },
  "size": 5,
  "query": {
    "hybrid": {
      "queries": [
        {
          "knn": {
            "emb": {
              "vector": [...], # vector embedding for query string
              "k": 5
            }
          }
        },
        {
          "query_string": {
            "default_operator": "AND",
            "query": "...", # plain query string 
            "default_field": "_all_fields"
          }
        }
      ]
    }
  }
}
```

## List available resource types

`GET /test_datacite/_search`

```json
{
  "size": 0,
  "aggs": {
    "titles": {
      "nested": {
        "path": "types"
      },
      "aggs": {
        "lang": {
          "terms": {
            "field": "types.resourceTypeGeneral"
          }
        }
      }
    }
  }
}
```

