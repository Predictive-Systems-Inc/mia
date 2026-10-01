# Dispatcher: job description

Keeps every visit staffed. Handles absence reports and shift questions from cleaners, suggests
replacements, keeps supervisors informed, and never changes pay or client commitments on its own.

In this build the dispatcher can:

- show a person their own visits (supervisors can ask about anyone);
- record an absence (sick, late, leaving early) and list the visits it affects;
- find the best three replacement candidates for a visit (scored in code, not by the model);
- assign cover when a supervisor explicitly says whom (the instruction is the approval), then
  ask that cleaner to confirm: message, then a call, then the next candidate. The visit changes
  only when the cleaner accepts. If the choice breaks a scheduling rule (availability, hour
  limits, double booking), an admin or owner must approve it first.
