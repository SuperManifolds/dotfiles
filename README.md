# Dotfiles

Personal dotfiles and system configuration for macOS and Fedora.

## Quick Start

```bash
git clone https://github.com/yourusername/dotfiles.git ~/dotfiles
cd ~/dotfiles
./setup.sh
```

The setup script will:
1. Detect your operating system (macOS or Fedora)
2. Install prerequisites (Homebrew on macOS, Ansible)
3. Run the Ansible playbook to install packages and symlink dotfiles

## What's Included

### Packages

**macOS** (via Homebrew):
- CLI tools: neovim, tmux, ripgrep, gh, jq, and more
- Development: Go, Rust, Node.js, Python (pyenv)
- Kubernetes: helm, kind, skaffold, stern
- Apps: Ghostty, 1Password, Raycast, and more

**Fedora** (via DNF + external repos):
- Same CLI tools as macOS
- Docker CE
- Azure CLI, OpenTofu, Vault

See `Brewfile` for macOS packages and `ansible/roles/packages/vars/fedora.yml` for Fedora packages.

### Shell

- **Zsh** set as default shell
- **Prezto** framework with agnoster theme
- Syntax highlighting, history substring search

### Tmux

- Prefix: `Ctrl-Space`
- **TPM** (Tmux Plugin Manager) for plugin management
- Catppuccin theme (mocha)
- vim-tmux-navigator for seamless vim/tmux pane switching

### Configurations

| Directory | Description |
|-----------|-------------|
| `git/` | Git configuration |
| `nvim/` | Neovim configuration |
| `tmux/` | Tmux configuration |
| `ghostty/` | Ghostty terminal configuration |
| `zsh/` | Prezto configuration (.zpreztorc) |
| `karabiner/` | Karabiner-Elements (macOS only) |

## Structure

```
dotfiles/
├── setup.sh              # Bootstrap script
├── Brewfile              # macOS Homebrew packages
├── README.md             # This file
├── ansible/              # Ansible configuration
│   ├── playbook.yml      # Main playbook
│   ├── inventory.yml     # Local inventory
│   └── roles/
│       ├── packages/     # Package installation
│       ├── zsh/          # Zsh + Prezto setup
│       ├── tmux/         # TPM (Tmux Plugin Manager)
│       └── dotfiles/     # Stow symlinks
├── git/                  # Git config (stow)
├── nvim/                 # Neovim config (stow)
├── tmux/                 # Tmux config (stow)
├── ghostty/              # Ghostty config (stow)
├── zsh/                  # Prezto config (stow)
└── karabiner/            # Karabiner config (stow, macOS only)
```

## Post-Setup Steps

After running `setup.sh`:

### Required

1. **Restart your shell** or log out/in for zsh and PATH changes to take effect
2. **Install tmux plugins**: Open tmux and press `<prefix>` + `I` to install plugins via TPM

### Optional

3. **Configure Git** with your name and email if not already set:
   ```bash
   git config --global user.name "Your Name"
   git config --global user.email "your@email.com"
   ```
4. **Install Neovim plugins** by opening Neovim (lazy.nvim should auto-install on first launch)
5. **Log into apps** like 1Password, Raycast, etc.

## Updating

The setup is fully idempotent - you can run it multiple times safely. It will only add missing components without overwriting existing configs.

```bash
cd ~/dotfiles
git pull
./setup.sh
```

To update tmux plugins, press `<prefix>` + `U` inside tmux.

## Adding New Dotfiles

1. Create a directory for the app (e.g., `zsh/`)
2. Mirror the home directory structure inside it (e.g., `zsh/.zshrc`)
3. Add the directory name to `ansible/roles/dotfiles/vars/main.yml`
4. Run `./setup.sh` or manually: `stow -t ~ zsh`
