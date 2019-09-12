#!/usr/bin/env bash

set -e

create_venv() {
    rm -rf ${VENV_DIR} # clean up existing venv if any
    python${PY_VERSION} -m venv ${VENV_DIR}
    source ${VENV_DIR}/bin/activate
    pip install wheel
    local pth_file=${VENV_DIR}/lib/python${PY_VERSION}/site-packages/lib.pth
    echo ${TESTERS_DIR} >> ${pth_file}
}

cache_dependencies() {
	pushd ${FILES_DIR} > /dev/null
	MAVEN_OPTS="-Dmaven.repo.local=${CACHE_DIR}" mvn dependency:resolve
	popd > /dev/null
}

# script starts here
if [[ $# -lt 2 ]]; then
    echo "Usage: $0 settings_json files_dir"
    exit 1
fi

# vars
SETTINGS_JSON=$1
FILES_DIR=$(readlink -f $2)

ENV_DIR=$(echo ${SETTINGS_JSON} | jq --raw-output .env_loc)

VENV_DIR=${ENV_DIR}/venv
THIS_SCRIPT=$(readlink -f ${BASH_SOURCE})
CACHE_DEPENDENCIES=$(echo ${SETTINGS_JSON} | jq --raw-output .env_data.maven_cache_dependencies)
CACHE_DIR=${ENV_DIR}/.m2
THIS_DIR=$(dirname ${THIS_SCRIPT})
PY_VERSION=3.7
TESTERS_DIR=$(readlink -f ${THIS_DIR}/../../../)

# main
create_venv
[[ ${CACHE_DEPENDENCIES} == true ]] && cache_dependencies
