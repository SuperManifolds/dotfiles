# Managed by dotfiles (stow package: fish)

# --- Environment ---------------------------------------------------------
# Mirror the defaults Prezto's zprofile set (only when not already set).
set -qx EDITOR; or set -gx EDITOR nano
set -qx VISUAL; or set -gx VISUAL nano
set -qx PAGER; or set -gx PAGER less
set -qx LANG; or set -gx LANG en_US.UTF-8
set -qx LESS; or set -gx LESS '-g -i -M -R -S -w -X -z-4'

# bun
set -gx BUN_INSTALL "$HOME/.bun"
set -gx ENABLE_EXPERIMENTAL_MCP_CLI true

# --- PATH ----------------------------------------------------------------
# fish does NOT read /etc/profile or /etc/profile.d, so paths that bash/zsh
# pick up there must be added explicitly: OrbStack guest dirs (from
# /etc/profile.d/999-orbstack.sh) and Go (from /etc/profile). fish_add_path
# is idempotent and dedupes.

# Lower-priority paths (append). -g keeps these in global (not universal)
# scope so PATH is rebuilt deterministically from this file each session.
for d in /usr/local/go/bin /opt/orbstack-guest/bin $HOME/.iximiuz/labctl/bin
    test -d $d; and fish_add_path -g --append $d
end

# Higher-priority paths (prepend). Listed low→high so the last entry ends up
# frontmost — yielding .bun > .local > .cargo > orbstack-hiprio > ... order,
# matching the old zsh PATH precedence.
for d in /usr/local/sbin /usr/local/bin $HOME/sbin $HOME/bin \
         /opt/orbstack-guest/data/bin/cmdlinks /opt/orbstack-guest/bin-hiprio \
         $HOME/.cargo/bin $HOME/.local/bin $HOME/.bun/bin
    test -d $d; and fish_add_path -g $d
end

# Homebrew (macOS / Linuxbrew). Sets its own PATH/MANPATH.
if test -x /opt/homebrew/bin/brew
    /opt/homebrew/bin/brew shellenv | source
end

# --- Prompt & completions ------------------------------------------------
# Starship prompt (cross-platform). Installed by the ansible fish role.
if type -q starship
    starship init fish | source
end

# iximiuz labctl completions (mirrors the zsh setup).
if type -q labctl
    labctl completion fish | source
end

# --- Aliases -------------------------------------------------------------
# Claude Code with permission prompts disabled. Forwards extra args.
alias clauded='claude --dangerously-skip-permissions'
alias claudedr='claude --dangerously-skip-permissions --resume'
alias t='tmux'
alias ta='tmux attach'

# Added by OrbStack: command-line tools and integration
# This won't be added again if you remove it.
source ~/.orbstack/shell/init2.fish 2>/dev/null || :
