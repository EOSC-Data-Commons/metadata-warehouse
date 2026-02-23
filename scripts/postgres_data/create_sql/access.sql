-- DATASET
GRANT datasetdb_read      TO reggie, jusong, ritwik;
GRANT datasetdb_readwrite TO script;
GRANT datasetdb_admin     TO tobias, josip, michal, ping, vincent;

-- TOOL
GRANT tooldb_read         TO tobias, josip, ping, vincent, ritwik;
GRANT tooldb_readwrite    TO script;
GRANT tooldb_admin        TO michal, jusong, reggie, eko;

-- FILE
GRANT filedb_read         TO tobias, josip, ping, vincent, ritwik;
GRANT filedb_readwrite    TO script;
GRANT filedb_admin        TO michal, reggie, jusong, eko;

-- APP
GRANT appdb_read          TO jusong, reggie, josip, tobias;
GRANT appdb_readwrite     TO script;
GRANT appdb_admin         TO michal, vincent, ritwik, ping;
