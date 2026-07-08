#!/bin/bash
# Install music command system-wide
set -e

if [ "$EUID" -ne 0 ]; then
    echo "Run as root: sudo ./install.sh"
    exit 1
fi

DIR="$(cd "$(dirname "$0")" && pwd)"
pip install -e "$DIR"
echo ""
echo "Installed. Run: music --help"
