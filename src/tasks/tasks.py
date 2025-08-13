from celery import Celery
import time

print('celery')
broker_url = 'redis://broker:6379/0'

celery_app = Celery('tasks')
celery_app.task_serializer = 'json'
celery_app.ignore_result = False

@celery_app.task
def add(x, y):
    print('sleeping')
    time.sleep(10)
    print('slept')
    return x + y

#add(1,2)

print(celery_app.task)

result = add.delay(4, 6)
print(result)
print('added task')