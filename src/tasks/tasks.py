from celery import Celery

print('celery')
broker_url = 'redis://broker:6379/0'

app = Celery('tasks')

@app.task
def add(x, y):
    return x + y

add(1,2)

print(app.task)

result = add.delay(4, 4)
print(result)
print('added task')