#!/usr/bin/env bash
set -Eeuo pipefail

readonly APP_PACKAGE=com.flapp.clients.apex
readonly DOWNLOAD_DIR="${1:-/home/app/Download}"

installed_status=""
installed_version=""
installed_arch=""
read_installed_package() {
    local record
    record=$(dpkg-query --show \
        --showformat='${db:Status-Status}\t${Version}\t${Architecture}' \
        "${APP_PACKAGE}" 2>/dev/null || true)
    IFS=$'\t' read -r installed_status installed_version installed_arch <<< "${record}"
}

read_installed_package
if [[ -e "${DOWNLOAD_DIR}" && ! -d "${DOWNLOAD_DIR}" ]]; then
    echo "Fastlink package directory is not a directory: ${DOWNLOAD_DIR}" >&2
    exit 1
fi

# Identify packages by their Debian metadata, not the download filename or mtime.
# Require one target version so a stale download cannot cause an accidental rollback.
shopt -s nullglob
deb_file=""
for candidate in "${DOWNLOAD_DIR}"/*.deb; do
    [[ -f "${candidate}" ]] || continue
    if ! package=$(dpkg-deb --field "${candidate}" Package); then
        echo "Cannot read deb package: ${candidate}. Finish or replace the download before starting." >&2
        exit 1
    fi
    [[ "${package}" == "${APP_PACKAGE}" ]] || continue
    if [[ -n "${deb_file}" ]]; then
        echo "Multiple Fastlink deb packages in ${DOWNLOAD_DIR}. Keep only the version to install." >&2
        exit 1
    fi
    deb_file="${candidate}"
done

if [[ -z "${deb_file}" ]]; then
    if [[ "${installed_status}" != installed ]]; then
        echo "Fastlink is not installed; place its deb package in ${DOWNLOAD_DIR}." >&2
        exit 1
    fi
    echo "No Fastlink deb in ${DOWNLOAD_DIR}; keeping installed version ${installed_version}."
    exit 0
fi

deb_version=$(dpkg-deb --field "${deb_file}" Version)
deb_arch=$(dpkg-deb --field "${deb_file}" Architecture)
host_arch=$(dpkg --print-architecture)
if [[ -z "${deb_version}" || -z "${deb_arch}" ]]; then
    echo "Fastlink deb is missing Version or Architecture metadata: ${deb_file}" >&2
    exit 1
fi
if [[ "${deb_arch}" != "${host_arch}" && "${deb_arch}" != all ]]; then
    echo "Fastlink deb architecture ${deb_arch} does not match container architecture ${host_arch}." >&2
    exit 1
fi

if [[ "${installed_status}" == installed && "${installed_arch}" == "${deb_arch}" ]] && \
    dpkg --compare-versions "${installed_version}" eq "${deb_version}"; then
    echo "Fastlink ${installed_version} matches ${deb_file}; skipping installation."
    exit 0
fi

echo "Installing Fastlink ${deb_version} from ${deb_file} (current: ${installed_version:-not installed}, status: ${installed_status:-not installed})."
# The image already contains dependencies. Try the local package first, so an
# ordinary upgrade/downgrade also works offline. Refresh APT only if necessary.
install_args=(install -y --no-install-recommends --allow-downgrades --reinstall "${deb_file}")
if ! apt-get "${install_args[@]}"; then
    echo "Local installation failed; refreshing APT metadata and retrying."
    apt-get update
    apt-get "${install_args[@]}"
fi

read_installed_package
if [[ "${installed_status}" != installed || "${installed_arch}" != "${deb_arch}" ]] || \
    ! dpkg --compare-versions "${installed_version}" eq "${deb_version}"; then
    echo "Fastlink installation did not finish with the requested version ${deb_version}." >&2
    exit 1
fi
apt-get clean
rm -rf /var/lib/apt/lists/*
echo "Fastlink ${installed_version} is ready."
