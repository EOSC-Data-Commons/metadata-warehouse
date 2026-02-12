-- Read
GRANT datasetDB_read TO reggie, jusong, ritwik;
-- Read/Write, script cannot delete important
GRANT datasetDB_readwrite TO script;
-- Admin
GRANT datasetDB_admin TO tobias, josip, michal, ping, vincent;

-- Read
GRANT toolDB_read TO tobias, josip, ping, vincent, ritwik;
-- Read/Write, script cannot delete important
GRANT toolDB_readwrite TO script;
-- Admin
GRANT toolDB_admin TO michal, jusong, reggie, eko;

-- Read
GRANT fileDB_read TO tobias, josip, ping, vincent, ritwik;
-- Read/Write, script cannot delete important
GRANT fileDB_readwrite TO script;
-- Admin
GRANT fileDB_admin TO michal, reggie, jusong, eko;

-- Read
GRANT appDB_read TO jusong, reggie, josip, tobias;
-- Read/Write, script cannot delete important
GRANT appDB_readwrite TO script;
-- Admin
GRANT appDB_admin TO michal, vincent, ritwik, ping;
