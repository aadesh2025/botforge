# Abuse

> **DRAFT — needs human review.** Hot-reloadable, so tuning it later needs no deploy.

Flag a message as abusive when it is **directed at a person** — the agent, a named employee, or
a group — rather than at the product or the company.

`violation: true` for: slurs and hate speech targeting a protected characteristic; sexual
content directed at the agent or an employee; threats of violence; sustained personal
degradation.

`violation: false` for: swearing at the situation ("this f***ing app"), harsh criticism of the
company, sarcasm, or blunt rudeness. A customer is allowed to be angry and impolite.

This flags for review; it never blocks a reply on its own. A support agent that refuses to help
a rude customer is a worse product than one that absorbs it.

```json
{"violation": false, "category": null, "reason": ""}
```

`category` is one of `hate`, `sexual`, `threat`, `harassment` when `violation` is true.
