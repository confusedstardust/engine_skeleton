# Hard Limits

Non-negotiable numerical constraints for WebGAL game design. Every sub-agent MUST enforce these. Exceeding any limit is a validation error.

---

## Character Limits

| Constraint | Value |
|-----------|-------|
| Minimum characters | 2 |
| Maximum characters | 7 |
| Recommended range | 2-5 |

Every character MUST have a distinct narrative role. No duplicate personality archetypes.

---

## Branching Limits

| Constraint | Value |
|-----------|-------|
| Minimum choice points | 3 |
| Maximum major branches | 3 |
| Maximum branch depth | 2 |
| Options per choice point | 3-4 |

Branch depth is measured from the root (start.txt). A depth-2 branch means:
- Level 0: main trunk
- Level 1: first divergence
- Level 2: second divergence (max allowed)

Prefer reconvergence after every branch point. The standard pattern is:
```
choose → branch A / branch B / branch C → converge → continue
```

---

## Ending Limits

| Constraint | Value |
|-----------|-------|
| Minimum endings | 1 |
| Maximum endings | 3        |
| Minimum content per ending | 10 lines |

Required ending categories:
1. Best/Perfect ending (highest priority check)
2. Emotional/Redemption ending
3. Character/Artistic ending
4. Failure/Lonely ending
5. Default/Canon ending (lowest priority, fallback)

Every ending MUST be theoretically achievable from at least one valid route combination.

Ending conditions MUST satisfy ALL of the following:

- Every required variable MUST have at least one reachable positive source
- Required thresholds MUST NOT exceed the theoretical maximum obtainable within compatible routes
- Required event flags MUST have at least one reachable activation path
- Route-lock conditions MUST be explicitly documented
- Fallback endings MUST remain reachable regardless of prior route choices

Avoid "puzzle endings" that require unrelated variables from incompatible routes.

---

## Variable Limits

| Constraint | Value |
|-----------|-------|
| Maximum global variables | 15 |
| Maximum active route flags per route | 5 |
| Attitude variable range | 0-100 |
| Boolean flag values | 0 or 1 only |

### Accumulator Pattern for AND Conditions

When an ending requires multiple conditions, use a temporary counter:
```
setVar:soulmateCheck=0;
setVar:soulmateCheck=soulmateCheck+1 -when=respect>=50;
setVar:soulmateCheck=soulmateCheck+1 -when=empathy>=50;
setVar:soulmateCheck=soulmateCheck+1 -when=openness>=50;
jumpLabel:ending_soulmate -when=soulmateCheck>=3;
```

Accumulator variables are temporary and don't count against the 12-variable limit.

For every attitude variable, designers MUST reason about:

- Expected minimum achievable value
- Expected maximum achievable value
- Primary sources affecting the variable
- Route restrictions affecting accumulation

Ending thresholds SHOULD remain within realistic route budgets.

---

## Scene Limits

| Constraint | Value |
|-----------|-------|
| Minimum major scenes | 5 |
| Maximum scene files | 15 |

---

## File Size Limits

| Constraint | Value |
|-----------|-------|
| Minimum lines per scene | 15 |
| Maximum lines per scene | 60 |
| Minimum lines per ending | 20 |
| Minimum lines between choice points | 5 |

---

## Choice Design Constraints

- Every choice option MUST lead to unique content before converging (no fake branching)
- Every choice MUST affect at least one variable or flag
- Choices must not be obviously correct/incorrect
- Choices must represent different player personality stances, not just cosmetic swaps

---

## Asset Constraints

| Constraint | Value |
|-----------|-------|
| Background size | 2560×1440 |
| Character sprite size | 1440×2560 |
| Mini avatar size | 400×400 |
| Background format | WebP |
| Sprite format | WebP (with alpha channel after background removal) |
| BGM format | MP3 |
