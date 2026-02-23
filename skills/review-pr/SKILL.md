---
name: review-pr
description: Review a pull request for code quality and issues
allowed_tools: [Bash, Read, Glob, Grep]
args: [pr_number]
user_invocable: true
---
Review pull request #{pr_number}. Follow these steps:

1. Get PR details: `gh pr view {pr_number}`
2. Get the diff: `gh pr diff {pr_number}`
3. Analyze the changes for:
   - Code quality and readability
   - Potential bugs or edge cases
   - Security vulnerabilities (OWASP top 10)
   - Test coverage
   - Breaking changes
   - Performance implications
4. Read any related files for context if needed.
5. Provide a structured review with:
   - Summary of changes
   - Issues found (with file:line references)
   - Suggestions for improvement
   - Overall assessment (approve/request changes)
