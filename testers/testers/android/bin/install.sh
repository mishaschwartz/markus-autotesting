#!/usr/bin/env bash

set -e

install_packages() {
    echo "[ANDROID-INSTALL] Installing system packages"
    sudo apt-get -y install maven
}

# script starts here
if [[ $# -ne 0 ]]; then
    echo "Usage: $0"
    exit 1
fi

# vars
THISSCRIPT=$(readlink -f ${BASH_SOURCE})
TESTERDIR=$(dirname $(dirname ${THISSCRIPT}))
SPECSDIR=${TESTERDIR}/specs

# main
install_packages
touch ${SPECSDIR}/.installed
