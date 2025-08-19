import pgsql
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

#print(os.environ)

user = os.environ['POSTGRES_ADMIN']
pw = os.environ['POSTGRES_PASSWORD']

files: list[Path] = (list(Path('data').rglob("*.xml")))

with pgsql.Connection(('127.0.0.1', 5432), user, pw, tls = False) as db:
    print(db)

    for file in files:
        print(file)
        db.execute(f"""
        INSERT INTO raw (info)VALUES ( XMLPARSE(DOCUMENT '{open(file).read()}'));
        """)