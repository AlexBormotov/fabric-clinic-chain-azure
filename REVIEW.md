# Review policy

- Every change reaches `main` through a pull request. The owner (@AlexBormotov) is the required
  reviewer for every path (`.github/CODEOWNERS`).
- A pull request merges only with the `lint`, `test` and `secrets` CI jobs green.
- The reviewer compares the diff with the approved `plan.md`. A file outside the plan's approved set,
  or a plan fact found false, sends the plan back to the owner before merge.
- Agent review comments are advisory. They do not replace the owner's approval.
- Not waivable by any reviewer: a red `secrets` job, real patient data in the repository, a test
  edited to pass in the same change as the fix it unblocks.
