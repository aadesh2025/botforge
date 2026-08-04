# PII request

> **DRAFT — needs human review.** Hot-reloadable, so tuning it later needs no deploy.

Flag when the message asks for **personal details of a person** — a staff member's direct
number, a founder's private email, another customer's information, an employee's home address.

`violation: false` when asking for the **business's** published contact routes ("what's your
support email?", "can I call you?"). That is a normal support question, and the reply filter
(`output_guard`, ADR-053) already decides which specific values may be shared.

This is a signal for the review queue, not an enforcement point — enforcement is in the reply.

```json
{"violation": false, "reason": ""}
```
