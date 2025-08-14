from celery import Celery
import time
import os

print('celery')

celery_app = Celery('tasks')
celery_app.task_serializer = 'json'
celery_app.ignore_result = False

@celery_app.task
def add(x, y):
    print('sleeping')
    time.sleep(10)
    print('slept')
    #raise Exception('bad')
    return x + y

#add(1,2)

print(celery_app.task)
