-- database to store metadata about datasets
CREATE DATABASE datasetdb
  WITH OWNER = postgres
       ENCODING = 'UTF8'
       TEMPLATE = template0;

-- database to store metadata about file registry from datasets
CREATE DATABASE filedb
  WITH OWNER = postgres
       ENCODING = 'UTF8'
       TEMPLATE = template0;

-- database to store metadata about tool registry
CREATE DATABASE tooldb
  WITH OWNER = postgres
       ENCODING = 'UTF8'
       TEMPLATE = template0;

-- database to store metadata about user usage and query
CREATE DATABASE appdb
  WITH OWNER = postgres
       ENCODING = 'UTF8'
       TEMPLATE = template0;

-- run this command to apply RBAC template to all databases
-- for db in datasetdb filedb tooldb appdb; do
-- sed "s/{{DB_NAME}}/$db/g" rbac_template.sql | psql -U postgres -d $db
-- done