# List PRs and worktrees
function prls
    gh pr list
    echo -e "\n🌲 Worktrees..."
    git worktree list
end
