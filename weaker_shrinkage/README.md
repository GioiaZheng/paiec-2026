# Weaker shrinkage ablation

Fixed Beta(0.5,0.5): `(successes + 0.5) / (labels + 1)`. Uses only acquired
binary labels for the same complete subject configuration and benchmark alias.
Returns 0.5 with no matching labels. No dependencies, fitting or retained state.

This is a local experimental control. The submitted baseline remains Beta(1,1).
