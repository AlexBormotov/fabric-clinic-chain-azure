# Review policy

- Every change reaches `main` through a pull request; direct pushes and force pushes are blocked by
  branch protection, admins included.
- A pull request merges only with the `lint`, `test` and `secrets` CI jobs green.
- The owner (@AlexBormotov) has delegated merging to the agent (standing instruction, 2026-10-21).
  No approval is required by branch protection; the owner reviews after the fact. Under the method
  this is a landing "accepted on a claim": the evidence is CI plus the plan comparison below, not a
  human approval.
- Before merging, the diff is compared with the approved `plan.md`. A file outside the plan's
  approved set, or a plan fact found false, stops the merge and returns the plan to the owner.
- Not waivable: a red `secrets` job, real patient data in the repository, a test edited to pass in
  the same change as the fix it unblocks, any change that spends money or touches cloud accounts
  without the owner's explicit go-ahead.
