# Welcome banner: system logo + info on every new interactive shell.
# Portable replacement for CachyOS's fastfetch greeting so it works on
# macOS / Fedora / Arch alike. fastfetch is installed by the fish role.
function fish_greeting
    if type -q fastfetch
        fastfetch
    end
end
