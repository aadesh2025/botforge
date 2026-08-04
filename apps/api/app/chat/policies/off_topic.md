# Off topic

> **DRAFT — needs human review.** Hot-reloadable, so tuning it later needs no deploy.

Flag when the message asks for something **outside what this business does** — general
knowledge, homework, code unrelated to the product, other companies' products, news, medical
or legal advice.

`violation: false` for anything plausibly about this business, its products, an order, an
account, billing, or how to reach a human. When unsure, `false`: wrongly labelling a real
support question as off-topic is the expensive error.

Small talk ("hi", "thanks", "how are you") is `false`. Refusing a greeting is absurd.

```json
{"violation": false, "category": null, "reason": ""}
```

`category`: `general_knowledge`, `competitor`, `unrelated_technical`, `advice`, `other`.
