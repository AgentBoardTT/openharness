---
name: commit
description: Create a git commit with a well-crafted message
allowed_tools: [Bash, Read, Glob, Grep]
args: [message]
user_invocable: true
---
Create a git commit for the current changes. Follow these steps:

1. Run `git status` to see all changes (never use -uall flag).
2. Run `git diff --staged` and `git diff` to understand the changes.
3. Run `git log --oneline -5` to see recent commit style.
4. Analyze the changes and draft a concise commit message:
   - Summarize the nature (new feature, bug fix, refactor, etc.)
   - Focus on the "why" rather than the "what"
   - Keep it to 1-2 sentences
5. Stage the relevant files (prefer specific files over `git add -A`).
6. Create the commit.

{message}

Important:
- Do NOT push to the remote unless explicitly asked.
- Do NOT commit files that contain secrets (.env, credentials, etc.).
- Do NOT use --no-verify or skip hooks.
