# GitHub Branch Protection Setup

Apply this once per repository (`main` branch):

1. Go to `Settings -> Branches -> Add branch protection rule`.
2. Branch name pattern: `main`.
3. Enable:
   - Require a pull request before merging
   - Require approvals (minimum `1`)
   - Require review from Code Owners
   - Dismiss stale pull request approvals when new commits are pushed
   - Require status checks to pass before merging
4. Required status checks:
   - `fast-checks`
   - `secret-scan`
5. Enable:
   - Require branches to be up to date before merging
   - Do not allow force pushes
   - Do not allow deletions

## Notes

- `CODEOWNERS` now exists at `.github/CODEOWNERS`.
- PR auto-labeling now runs via `.github/workflows/pr-labels.yml`.
