# ssh wrapper: tint the Ghostty background per destination host as a
# "where am I connected" indicator, then reset on disconnect.
#
# Colors are set with OSC 11 (background) and reset with OSC 111, which
# restores Ghostty's configured `background`. Edit the switch below to
# taste; hex values are given without a leading '#'.
#
# tmux note: inside tmux these escapes are only forwarded to Ghostty when
# `set -g allow-passthrough on` is set in tmux.conf.

function __ghostty_osc --argument payload
    if set -q TMUX
        printf '\ePtmux;\e\e]%s\a\e\\' $payload
    else
        printf '\e]%s\a' $payload
    end
end

function ssh --description 'ssh with a per-host Ghostty background-color indicator'
    # --- Resolve the destination: first non-option operand. ------------
    set -l optargs b c D E e F I i J L l m O o P p Q R S W w # options that take a value
    set -l dest ''
    set -l i 1
    set -l argc (count $argv)
    while test $i -le $argc
        set -l a $argv[$i]
        if string match -qr '^-' -- $a
            set -l flag (string sub -s 2 -l 1 -- $a)
            if contains -- $flag $optargs; and test (string length -- $a) -eq 2
                set i (math $i + 2) # skip "-p 2222" style value
                continue
            end
            set i (math $i + 1)
            continue
        end
        set dest $a
        break
    end

    # Strip user@ and any :port / trailing path.
    set -l host (string replace -r '^[^@]*@' '' -- $dest)
    set host (string replace -r '[:/].*$' '' -- $host)

    # --- Host -> background color. Edit freely. Empty = no tint. -------
    set -l bg
    switch $host
        case mozzarella monterey stilton emmental
            set bg 190b0c # red
        case synology
            set bg 0a131a # blue
        case agent-mac
            set bg 191007 # orange
        case nuremburg
            set bg 19180a # yellow
        case cachyos
            set bg 09130e # green
        case orb
            set bg 130b19 # purple
    end

    # Unknown host: leave the background untouched.
    if test -z "$bg"
        command ssh $argv
        return $status
    end

    __ghostty_osc "11;#$bg"
    command ssh $argv
    set -l rc $status
    __ghostty_osc 111 # reset background to Ghostty's configured default
    return $rc
end
