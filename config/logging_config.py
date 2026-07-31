LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {
            '()': 'uvicorn.logging.DefaultFormatter',
            'fmt': '%(levelprefix)s %(asctime)s %(name)s@%(lineno)d %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S',
            'use_colors': True,
        },
    },
    'handlers': {
        'default': {
            'formatter': 'default',
            'class': 'logging.StreamHandler',
            'filters': [],
            'stream': 'ext://sys.stdout',
        },
    },
    'root': {
        'handlers': ['default'],
        'level': 'INFO',
    },
    'loggers': {
        '': {'handlers': ['default'], 'level': 'INFO'},
        'app': {'handlers': ['default'], 'level': 'INFO', 'propagate': False},
        'celery.task': {'handlers': ['default'], 'level': 'INFO', 'propagate': False},
        'opensearch': {'handlers': ['default'], 'level': 'INFO', 'propagate': False},
        'watchfiles.main': {
            'handlers': ['default'],
            'level': 'WARN',
            'propagate': True,
        },
        'urllib3': {'handlers': ['default'], 'level': 'INFO', 'propagate': False},
        'transform.tasks': {'handlers': ['default'], 'level': 'INFO', 'propagate': False},
    },
}
