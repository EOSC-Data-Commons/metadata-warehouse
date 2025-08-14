import pgsql
import os
from dotenv import load_dotenv

load_dotenv()

#print(os.environ)

user = os.environ['POSTGRES_ADMIN']
pw = os.environ['POSTGRES_PASSWORD']

with pgsql.Connection(('127.0.0.1', 5432), user, pw, tls = False) as db:
    print(db)

    test = db.execute("""
    CREATE TABLE raw( id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, info XML);
    """)



