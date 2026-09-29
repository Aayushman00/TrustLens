# What We're Doing, Step by Step

**Goal:** Remove one line (a "Co-Authored-By" trailer) from one old commit's message, on the `Main` branch, without breaking anything else.

## The problem
`Main`'s history isn't a straight line — it has merge commits (PR #3, PR #4), meaning two branches joined back together at those points. Any tool that "replays commits one by one" flattens that shape.

## Step-by-step plan

1. **Get a safe local copy of Main to experiment on.**
   `git checkout Main` — switch to the branch.
   `git fetch origin` — pull the latest from GitHub without touching your files.
   *(We work on a copy, `main-rewrite`, not the real `Main`, until we're sure.)*

2. **First attempt: `git rebase -i <commit>^`** — this walks through commits one at a time and lets you edit one. Problem: it forces everything into one straight line, so any merge commit it touches gets flattened. It hit an unrelated commit ("Convert architecture diagram to flowchart format") we didn't expect — sign that the history is more tangled than assumed.
   → **Aborted.** Ran `git status` / compared to `origin/Main` to confirm the copy matches original exactly — nothing lost.

3. **Second attempt (proposed): `git filter-repo --commit-callback`** — this can edit the message of ONE specific commit (matched by its hash) without touching the rest of the graph's shape. Merges stay merges.
   ```
   git filter-repo --commit-callback '
   if commit.original_id == b"<b4d4b3e sha>":
       commit.message = commit.message.replace(b"Co-Authored-By: ...\n", b"")
   ' --force
   ```

4. **Verify before trusting it:**
   `git diff <old-tip> <new-tip>` — should show **zero** file changes, proving only the message changed, not the code.
   `git log --graph` before/after — confirms merge shape is unchanged.

5. **Only after verification passes, update the real branch:**
   `git push --force-with-lease origin Main` — uploads the rewritten history. `--force-with-lease` refuses to push if someone else changed remote `Main` since we last fetched, so we don't overwrite others' work by accident.

## Where we are now
Steps 1–2 done, aborted safely. Step 3 proposed, waiting for your yes before running it.
