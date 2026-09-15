#!/usr/bin/env bash

set -Eeuo pipefail

on_error() {
  printf 'worktree setup failed at line %s\n' "$1" >&2
}

trap 'on_error "$LINENO"' ERR

if [ "$#" -ne 2 ]; then
  printf 'usage: %s <original-repository-path> <worktree-repository-path>\n' "$0" >&2
  exit 1
fi

if ! original_repo_path="$(cd -- "$1" 2>/dev/null && pwd -P)"; then
  printf 'worktree setup failed: original repository path is not accessible: %s\n' "$1" >&2
  exit 1
fi

if ! worktree_repo_path="$(cd -- "$2" 2>/dev/null && pwd -P)"; then
  printf 'worktree setup failed: worktree repository path is not accessible: %s\n' "$2" >&2
  exit 1
fi

cd -- "$worktree_repo_path"

validate_current_branch() {
  local current_branch

  if ! current_branch="$(git symbolic-ref --quiet --short HEAD 2>/dev/null)"; then
    if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
      printf 'worktree setup failed: detached HEAD is not supported; checkout a feature branch before running setup\n' >&2
    else
      printf 'worktree setup failed: worktree path is not a Git worktree: %s\n' "$worktree_repo_path" >&2
    fi
    exit 1
  fi

  case "$current_branch" in
    main|master)
      printf 'worktree setup failed: branch "%s" is not allowed; checkout a feature branch before running setup\n' "$current_branch" >&2
      exit 1
      ;;
  esac

  printf 'worktree setup: branch validation passed: %s\n' "$current_branch"
}

validate_current_branch

shopt -s nullglob
setup_scripts=(.agents/scripts/setup-worktree-*.sh)

for setup_script in "${setup_scripts[@]}"; do
  [ -f "$setup_script" ] || continue

  if ! bash "$setup_script" "$original_repo_path" "$worktree_repo_path"; then
    printf 'worktree setup failed: %s\n' "$setup_script" >&2
    exit 1
  fi
done
