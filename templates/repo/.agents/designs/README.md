# Designs

One record per new screen or page, `<slug>.md`, created **before** the page is implemented. The
design-gate hook refuses a new page file (Angular `*.component.ts` under a feature, Next.js `page.tsx`)
unless a record for that feature exists with `approved: true`.

```markdown
---
slug: <feature-or-page>
artifact: https://claude.ai/...           # the design canvas (orchestrator `design` skill)
approved: true                            # set by the person after reviewing the canvas
approved_by: <name>
date: YYYY-MM-DD
---

What the screen is for, the states it has (empty, loading, error, populated), and what was decided in review.
```
