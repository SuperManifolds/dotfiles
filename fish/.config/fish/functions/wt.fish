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
    set common_dir (cd $common_dir 2>/dev/null; and pwd)
    if test -z "$common_dir"
        echo "wt: could not resolve git common dir" >&2
        return 1
    end

    # Always place worktrees directly inside the main repo folder, as
    # <repo>/<branch>. The main repo folder is the directory holding the git
    # data: its parent when the git dir is nested (".bare"/".git" layouts),
    # or the bare repo directory itself otherwise. Deterministic — it does not
    # depend on where any existing worktrees happen to live.
    set -l root
    if string match -q '.*' (basename $common_dir)
        set root (dirname $common_dir)
    else
        set root $common_dir
    end
    set -l target $root/$branch

    if test -e $target
        echo "wt: $target already exists" >&2
        return 1
    end

    # Run git from the bare repo location — the worktree-container
    # directory ($root) typically has no .git file of its own.
    git -C $common_dir fetch origin; or return $status

    if git -C $common_dir show-ref --verify --quiet refs/heads/$branch
        # Local branch already exists — check it out, don't recreate it.
        git -C $common_dir worktree add $target $branch; or return $status
    else if git -C $common_dir show-ref --verify --quiet refs/remotes/origin/$branch
        # Track the existing remote branch.
        git -C $common_dir worktree add -b $branch $target origin/$branch; or return $status
    else
        # New branch off origin's default branch.
        set -l base (git -C $common_dir symbolic-ref refs/remotes/origin/HEAD --short 2>/dev/null)
        test -n "$base"; or set base origin/main
        git -C $common_dir worktree add -b $branch $target $base; or return $status
    end

    cd $target
end
