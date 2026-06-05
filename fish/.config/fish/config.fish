# Managed by dotfiles (stow package: fish)

# Homebrew
if test -x /opt/homebrew/bin/brew
    /opt/homebrew/bin/brew shellenv | source
end

# Add ~/.local/bin to PATH
if test -d ~/.local/bin; and not contains -- ~/.local/bin $PATH
    fish_add_path ~/.local/bin
end

# Starship prompt (cross-platform). Installed by the ansible fish role.
if type -q starship
    starship init fish | source
end

# Claude Code with permission prompts disabled. Forwards extra args.
alias clauded='claude --dangerously-skip-permissions'
