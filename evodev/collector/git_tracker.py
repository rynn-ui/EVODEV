"""Git repository tracker for non-invasive diff and file change analysis."""

from pathlib import Path
import subprocess
from typing import List, Optional


class GitTracker:
    """Safely interrogates local git repositories for diffs and branch information."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path.resolve()

    def is_git_repo(self) -> bool:
        """Check if target path is inside a git working tree."""
        try:
            res = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=5,
            )
            return res.returncode == 0 and res.stdout.strip() == "true"
        except Exception:
            return False

    def get_head_commit(self) -> Optional[str]:
        """Get latest git commit hash."""
        if not self.is_git_repo():
            return None
        try:
            res = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode == 0:
                return res.stdout.strip()
        except Exception:
            pass
        return None

    def get_current_branch(self) -> Optional[str]:
        """Get currently checked out branch name."""
        if not self.is_git_repo():
            return None
        try:
            res = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode == 0:
                return res.stdout.strip()
        except Exception:
            pass
        return None

    def get_changed_files(self) -> List[str]:
        """Get list of modified, added, or deleted files relative to HEAD."""
        if not self.is_git_repo():
            return []
        try:
            res = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode == 0:
                lines = res.stdout.strip().splitlines()
                changed = []
                for line in lines:
                    if len(line) > 3:
                        changed.append(line[3:].strip())
                return changed
        except Exception:
            pass
        return []

    def get_diff_summary(self, max_lines: int = 150) -> str:
        """Get concise summary of uncommitted diffs."""
        if not self.is_git_repo():
            return ""
        try:
            res = subprocess.run(
                ["git", "diff", "--stat"],
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
            # If no unstaged diff, check staged diff
            res_staged = subprocess.run(
                ["git", "diff", "--cached", "--stat"],
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res_staged.returncode == 0:
                return res_staged.stdout.strip()
        except Exception:
            pass
        return ""
