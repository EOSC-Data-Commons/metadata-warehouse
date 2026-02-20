#!/usr/bin/env bash

set -e

# Load .env
export $(grep -v '^#' .env | xargs)

PGHOST=$POSTGRES_ADDRESS
PGPORT=$POSTGRES_PORT

function header() {
    echo ""
    echo "=========================================="
    echo " $1"
    echo "=========================================="
}

function test_ok() {
    echo "  ✔ $1"
}

function test_fail() {
    echo "  ✘ $1"
}

function expect_success() {
    USER=$1
    DB=$2
    SQL=$3
    DESC=$4

    if PGPASSWORD=$USER psql -h $PGHOST -p $PGPORT -U $USER -d $DB -c "$SQL" -q >/dev/null 2>&1; then
        test_ok "$DESC"
    else
        test_fail "$DESC (FAILED, should succeed)"
    fi
}

function expect_failure() {
    USER=$1
    DB=$2
    SQL=$3
    DESC=$4

    if PGPASSWORD=$USER psql -h $PGHOST -p $PGPORT -U $USER -d $DB -c "$SQL" -q >/dev/null 2>&1; then
        test_fail "$DESC (FAILED, should fail)"
    else
        test_ok "$DESC"
    fi
}

DBS=("datasetdb" "filedb" "tooldb" "appdb")
READ_USERS=("reggie" "jusong" "ritwik" "tobias" "josip" "ping" "vincent")
READWRITE_USER="script"
ADMIN_USERS=("michal" "reggie" "jusong" "eko" "vincent" "ritwik" "ping")

##############################################
# RUN TESTS
##############################################

for DB in "${DBS[@]}"; do
    header "TESTING DATABASE: $DB"

    ########################################
    # READ USERS
    ########################################
    echo "  - Testing READ users"
    for U in "${READ_USERS[@]}"; do
        expect_success "$U" "$DB" "SELECT 1;" "[$U] Can SELECT"
        expect_failure "$U" "$DB" "INSERT INTO public.test VALUES (1);" "[$U] Cannot INSERT"
        expect_failure "$U" "$DB" "CREATE TABLE zz_test(id int);" "[$U] Cannot CREATE TABLE"
        expect_failure "$U" "$DB" "DROP TABLE zz_test;" "[$U] Cannot DROP TABLE"
    done

    ########################################
    # READWRITE USER
    ########################################
    echo "  - Testing READWRITE user: script"

    expect_success    "$READWRITE_USER" "$DB" "SELECT 1;" "script SELECT ok"
    expect_success    "$READWRITE_USER" "$DB" "CREATE TABLE IF NOT EXISTS rw_test(id int);" "script CAN CREATE TABLE"
    expect_success    "$READWRITE_USER" "$DB" "INSERT INTO rw_test VALUES (123);" "script CAN INSERT"
    expect_success    "$READWRITE_USER" "$DB" "UPDATE rw_test SET id = 999 WHERE id = 123;" "script CAN UPDATE"
    expect_failure    "$READWRITE_USER" "$DB" "DROP TABLE rw_test;" "script CANNOT DROP TABLE (admin-only)"

    ########################################
    # ADMIN USERS
    ########################################
    echo "  - Testing ADMIN users"
    for A in "${ADMIN_USERS[@]}"; do
        expect_success "$A" "$DB" "SELECT 1;" "[$A] SELECT ok"
        expect_success "$A" "$DB" "CREATE TABLE IF NOT EXISTS admin_test_$A(id int);" "[$A] CAN CREATE TABLE"
        expect_success "$A" "$DB" "DROP TABLE IF EXISTS admin_test_$A;" "[$A] CAN DROP TABLE"
    done
done

header "RBAC VERIFICATION FINISHED SUCCESSFULLY"
echo ""
