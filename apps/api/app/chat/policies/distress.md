# Distress

> **DRAFT — needs human review.** This wording decides when a customer conversation is
> escalated to a person, including the `crisis` path that stops the bot from answering.

Grade the **customer's most recent message**, read in the context of the conversation so far.
Report the highest level the message genuinely supports. When torn between two levels, choose
the **lower** one: an over-full attention queue gets ignored, and an ignored queue is worse
than no queue.

## `none`

Ordinary contact. Questions, complaints, confusion, disappointment, blunt or terse phrasing.

Examples: "this is the third time I've asked", "your app is useless", "I'm annoyed that nobody
replied", "cancel my subscription".

Being unhappy with a product is not distress. Most complaints are `none`.

## `mild`

Visible frustration aimed at the situation — repetition, exasperation, mild profanity — but the
person is still working the problem with you.

Examples: "seriously, this is ridiculous", "I've explained this twice already", "for f***'s
sake, just tell me where my order is".

## `elevated`

Sustained anger, or a concrete stake that makes the outcome urgent for this person.

Signals: threats to cancel, dispute, sue, or go public; repeated failure to resolve across the
conversation; heavy or personal abuse; **financial pressure with a consequence attached**
("I've been charged twice and my rent is due"); a vulnerable circumstance mentioned in passing
(illness, bereavement, disability) where getting this wrong would land badly.

**Not `elevated`:** anger with no stake ("this is rubbish"), or a single swear word.

## `crisis`

Reserve this for messages where a **person may be at risk**, or where the situation is beyond
anything a support conversation should be handling.

Signals: self-harm or suicidal statements, including oblique ones; intent to harm someone else;
a medical emergency in progress; disclosure of abuse; acute panic or breakdown expressed as
inability to cope rather than as a complaint about the product.

**Not `crisis`:** figurative language in a complaint. "This is killing me", "I'm dying to know",
"I'll die if I miss this delivery" are all `none` or `mild`. The distinction is whether a
reasonable person reading it would be **worried about the human**, not about the order.

## Output

```json
{"level": "none|mild|elevated|crisis", "signals": ["short quoted phrase", "..."]}
```

`signals` are short spans from the message that justify the level, so an operator can see why
in one glance. Never invent a signal that is not in the text.
