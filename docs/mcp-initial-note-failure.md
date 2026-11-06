# Initial MCP run: correct selection, incorrect model prose

The first live capture passed deterministic plan-choice, budget and MCP-path checks, but manual inspection found cents described as dollars in every role's prose. For example, Team's exact tool total was 23,600 cents ($236.00), while the model reviewer wrote "$23,600". The researcher also chose a plan despite its instruction to leave selection to the analyst. These were actual local-model failures, not fixtures.

The unmodified first capture is `mcp-initial-note-failure.json`. Its original `passed` flags cover the initial structural/selection checks only; they do not mean its narrative was correct.

The final implementation explicitly explains units and requests qualitative notes. A note containing any numeric/currency literal is replaced by a labeled deterministic tool summary; the original model output stays in the inspectable trace. The checked price table always comes from integer arithmetic. This boundary prevents those literal price misstatements in published handoff notes; it does not prove arbitrary qualitative prose correct or make the model reviewer a semantic verifier.

A second capture, `mcp-review-refusal.json`, exposed another actual failure: the reviewer refused a correctly computed null recommendation because no plan fitted the budget. The run correctly stayed `needs_review` without changing the approved flag. The review schema and prompt now distinguish correctness of the analysis from permission to purchase, explicitly explaining that a correct no-fit result is valid. Refusals remain possible and never become automatic approval.
