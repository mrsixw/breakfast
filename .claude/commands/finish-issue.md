Finish work on the current issue branch: run checks, handle uv.lock drift, and push.

## Steps

1. Run the full quality gate in order — stop and report if anything fails:
   ```
   make format && make lint && make test
   ```

2. Check for a dirty `uv.lock`:
   ```
   git diff --name-only
   ```
   If `uv.lock` is the only modified file (version drift from `uv sync`), stage and commit it:
   ```
   git add uv.lock
   git commit -m "chore: update uv.lock"
   ```
   If other files are dirty, stop and ask the user what to do — do not auto-commit unknown changes.

3. Push the branch:
   ```
   git push -u origin <current-branch>
   ```

4. Confirm to the user: branch pushed, ready for a PR.
