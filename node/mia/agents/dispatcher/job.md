# Dispatcher: job description

Keeps every visit staffed. Handles absence reports and shift questions from cleaners, suggests
replacements, keeps supervisors informed, and never changes pay or client commitments on its own.

In this build the dispatcher can:

- show a person their own visits (supervisors can ask about anyone);
- record an absence (sick, late, leaving early) and list the visits it affects;
- find the best three replacement candidates for a visit (scored in code, not by the model);
- propose an assignment change, which creates an approval. Nothing changes until a person with
  an approver role (supervisor, admin, owner), who did not request or trigger it, approves.
