# Fixed shrinkage candidate

Prediction is `(successes + 1) / (matching_labels + 2)` for the target's
complete visible subject attributes and anonymous benchmark ID. No matches
returns 0.5. This is a Beta(1,1) posterior mean with fixed prior strength 2;
it is an experimental comparator, not a validated improvement. No fitting,
external data, persistent state, custom acquisition, API, or dependencies.

Compare with official empirical mean and constant 0.5 at every budget.
Select any tuned prior using development benchmarks only. Never choose a
prior from the final held-out benchmark results or anonymous feedback IDs.
