---
name: debug
description: Debug an error or unexpected behavior
allowed_tools: [Bash, Read, Glob, Grep]
args: [description]
user_invocable: true
---
Debug the following issue: {description}

Follow these steps:

1. Understand the error:
   - Parse any error messages or stack traces
   - Identify the file(s) and line number(s) involved
2. Read the relevant source files.
3. Search for related code patterns using Grep.
4. Identify the root cause:
   - Check for common issues (typos, wrong variable names, missing imports)
   - Trace the data flow
   - Check edge cases
5. Propose a fix with explanation.
6. If you can fix it, apply the change using Edit.
7. Run any related tests to verify the fix.
