# Add a worktree for a branch — checks out origin/<branch> if it exists,
# otherwise creates a new branch off origin's default branch. Works from
# the bare repo or from inside any existing worktree.
function wt --argument branch
    if test -z "$branch"
        echo "usage: wt <branch>" >&2
        return 1
    end

    set -l common_dir (git rev-parse --git-common-dir 2>/dev/null)
    if test -z "$common_dir"
        echo "wt: not inside a git repository" >&2
        return 1
    end
    set common_dir (cd $common_dir; and pwd)
    set -l root (dirname $common_dir)
    set -l target $root/$branch

    if test -e $target
        echo "wt: $target already exists" >&2
        return 1
    end

    git -C $root fetch origin; or return $status

    if git -C $root show-ref --verify --quiet refs/remotes/origin/$branch
        git -C $root worktree add -b $branch $target origin/$branch; or return $status
    else
        set -l base (git -C $root symbolic-ref refs/remotes/origin/HEAD --short 2>/dev/null)
        test -n "$base"; or set base origin/main
        git -C $root worktree add -b $branch $target $base; or return $status
    end

    cd $target
end
