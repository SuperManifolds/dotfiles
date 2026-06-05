# Create worktree and checkout PR
function prn --argument number
    if test -z "$number"
        echo "first argument must be PR number" >&2
        return 1
    end
    set -l prdir (basename $PWD).$number
    git worktree add ../$prdir
    cd ../$prdir
    gh pr checkout $number
    git branch -D $prdir
end
