#!/usr/bin/bash

# https://www.shellcheck.net/wiki/SC1091
# shellcheck source=/dev/null
source /usr/bin/setup_env_in_openshift.sh

mkdir -p "${PACKIT_HOME}/.ssh"
chmod 0700 "${PACKIT_HOME}/.ssh"

grep -q gitlab.com "${PACKIT_HOME}/.ssh/known_hosts" || ssh-keyscan gitlab.com >>"${PACKIT_HOME}/.ssh/known_hosts"

exec run_worker_.sh
