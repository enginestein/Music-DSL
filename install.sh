#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Run as root:"
    echo "  sudo ./install.sh"
    exit 1
fi

DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="/opt/music"
VENV="$INSTALL_DIR/venv"

# Install packages based on whatever distro
install_packages() {
    if command -v pacman >/dev/null; then
        pacman -Sy --needed --noconfirm python python-pip python-setuptools

    elif command -v apt >/dev/null; then
        apt update
        apt install -y python3 python3-pip python3-venv python3-setuptools

    elif command -v dnf >/dev/null; then
        dnf install -y python3 python3-pip python3-setuptools

    elif command -v yum >/dev/null; then
        yum install -y python3 python3-pip python3-setuptools

    elif command -v zypper >/dev/null; then
        zypper --non-interactive install python3 python3-pip python3-setuptools

    elif command -v apk >/dev/null; then
        apk add python3 py3-pip py3-setuptools

    elif command -v xbps-install >/dev/null; then
        xbps-install -Sy python3 python3-pip python3-setuptools

    elif command -v emerge >/dev/null; then
        emerge dev-lang/python dev-python/pip

    elif command -v eopkg >/dev/null; then
        eopkg install python3 python3-pip

    else
        echo "Unsupported package manager."
        exit 1
    fi
}

echo "Installing dependencies..."
install_packages

mkdir -p "$INSTALL_DIR"
cp -r "$DIR/"* "$INSTALL_DIR/"

# Create venv environment
python3 -m venv "$VENV"

"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install -e "$INSTALL_DIR"

# Create symlink 
ln -sf "$VENV/bin/music" /usr/local/bin/music

# Print success
echo
echo "Installation complete!"
echo "Run:"
echo "  music --help"
