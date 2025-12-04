#!/usr/bin/env bash
set -euo pipefail

DOTFILES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HEADLESS=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --headless)
            HEADLESS=true
            shift
            ;;
        *)
            shift
            ;;
    esac
done

echo "==> Detecting operating system..."

if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
    echo "    Detected: macOS"
elif [[ -f /etc/fedora-release ]]; then
    OS="fedora"
    echo "    Detected: Fedora"
else
    echo "Error: Unsupported operating system"
    exit 1
fi

install_macos_deps() {
    # Install Xcode Command Line Tools
    if ! xcode-select -p &>/dev/null; then
        echo "==> Installing Xcode Command Line Tools..."
        xcode-select --install
        echo "    Please complete the Xcode CLI tools installation, then re-run this script."
        exit 0
    fi

    # Install Homebrew
    if ! command -v brew &>/dev/null; then
        echo "==> Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

        # Add Homebrew to PATH for this session
        if [[ -f /opt/homebrew/bin/brew ]]; then
            eval "$(/opt/homebrew/bin/brew shellenv)"
        elif [[ -f /usr/local/bin/brew ]]; then
            eval "$(/usr/local/bin/brew shellenv)"
        fi
    fi

    # Install Ansible
    if ! command -v ansible &>/dev/null; then
        echo "==> Installing Ansible..."
        brew install ansible
    fi
}

install_fedora_deps() {
    # Install Ansible
    if ! command -v ansible &>/dev/null; then
        echo "==> Installing Ansible..."
        sudo dnf install -y ansible
    fi
}

run_ansible() {
    echo "==> Running Ansible playbook..."
    cd "$DOTFILES_DIR/ansible"

    local extra_vars=""
    if [[ "$HEADLESS" == "true" ]]; then
        extra_vars="-e install_desktop=false"
        echo "    Headless mode: skipping desktop/GUI packages"
    fi

    if [[ "$OS" == "macos" ]]; then
        ansible-playbook -i inventory.yml playbook.yml $extra_vars
    else
        ansible-playbook -i inventory.yml playbook.yml $extra_vars --ask-become-pass
    fi
}

main() {
    echo ""
    echo "╔════════════════════════════════════════╗"
    echo "║       Dotfiles Setup Script            ║"
    echo "╚════════════════════════════════════════╝"
    echo ""

    if [[ "$OS" == "macos" ]]; then
        install_macos_deps
    else
        install_fedora_deps
    fi

    run_ansible

    echo ""
    echo "==> Setup complete!"
    echo "    You may need to restart your shell or log out/in for all changes to take effect."
}

main "$@"
