# Git/PR workflow functions

# List PRs and worktrees
prls() {
    gh pr list
    echo -e "\n🌲 Worktrees..."
    git worktree list
}

# Create worktree and checkout PR
prn() {
    local number="${1:?first argument must be PR number}"
    local prdir="${PWD##*/}.$number"
    git worktree add ../$prdir
    cd ../$prdir
    gh pr checkout $number
    git branch -D $prdir
}

# Delete PR worktree
prd() {
    local number="${1:?first argument must be PR number}"
    local prdir="${PWD##*/}.$number"
    rm -fr ../$prdir
    git worktree prune
}

# Add a worktree for a branch — checks out origin/<branch> if it exists,
# otherwise creates a new branch off origin's default branch. Works from
# the bare repo or from inside any existing worktree.
wt() {
    local branch="${1:?usage: wt <branch>}"

    local common_dir
    common_dir=$(git rev-parse --git-common-dir 2>/dev/null) || {
        echo "wt: not inside a git repository" >&2
        return 1
    }
    common_dir=$(cd "$common_dir" && pwd)
    local root=${common_dir:h}
    local target="$root/$branch"

    if [[ -e $target ]]; then
        echo "wt: $target already exists" >&2
        return 1
    fi

    git -C "$root" fetch origin || return $?

    if git -C "$root" show-ref --verify --quiet "refs/remotes/origin/$branch"; then
        git -C "$root" worktree add -b "$branch" "$target" "origin/$branch" || return $?
    else
        local base
        base=$(git -C "$root" symbolic-ref refs/remotes/origin/HEAD --short 2>/dev/null)
        base=${base:-origin/main}
        git -C "$root" worktree add -b "$branch" "$target" "$base" || return $?
    fi

    cd "$target"
}
