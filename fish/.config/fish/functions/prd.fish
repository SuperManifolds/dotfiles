# Delete PR worktree
function prd --argument number
    if test -z "$number"
        echo "first argument must be PR number" >&2
        return 1
    end
    set -l prdir (basename $PWD).$number
    rm -fr ../$prdir
    git worktree prune
end
