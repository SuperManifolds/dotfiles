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
