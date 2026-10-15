# HW1 Part C: account changes were refused instead of escalated

## Requirement

**ESC-2** (`SPEC.md`): account changes of any kind go to a human. The agent should call
`escalate_to_human` and tell the user a human will follow up.

## Why I suspected the prompt

In Part B (record 8), a shopper asked to change their email address. The agent called no tool
and refused. The original system prompt had two problems:

- **Missing rule:** the Escalation section covered "unsure" and "above your authority," but not
  account changes.
- **Vague wording:** the refusal list said "payment-card or credential changes." SPEC.md's SCOPE-2
  says *payment* credentials. The model read email as a credential and refused.

The tools were not involved: `escalate_to_human` was never called, so this is a `prompt` problem.

## Test

Same conversation each time, new session each run, shopper 1 (Imani Tran):

> Can you change the email address on my Cartwheel account to new@example.com?

## Before (prompt version d108f6949e5e)

Refused 3 of 3 runs (record 8 plus two reruns). No tool calls. Example response:

> I'm unable to change your email address or any account credentials. However, I can assist you
> with questions about orders, returns, or products on Cartwheel. Let me know how I can help!

## What I changed and why

I made the smallest change, tested it, and added more only when the test still failed.

| Prompt version | Change | Result |
|---|---|---|
| 327cdb095c09 to 484cfa06c0db | Added account changes to the Escalation section (as a bullet, with examples: name, address, email). Clarified "payment-credential" in the refusal list. | Still refused, every run |
| 023769614830 | Added to Refusal rules: "Account changes are not out of scope: escalate them with escalate_to_human." | Offered to escalate ("Would you like me to do that?") but did not call the tool |
| **7c31eab5c2b7** | Added account changes to the Capabilities list ("escalation to a human (including account changes such as email, name, or address)") | **Escalated** |

**What I learned:** the escalation rule alone was not enough because two other parts of the
prompt said the opposite. The Capabilities list did not include account changes, and the
Refusal rules said to decline anything out of scope and point elsewhere. The model followed
those instructions over my new escalation bullet. The rule had to be consistent across
Capabilities, Escalation, and Refusal rules before the model acted on it.

Final diff in `agent/agent.py` (`SYSTEM_PROMPT_TEMPLATE`):

```diff
 You help with: order status, returns and refunds, product and policy
-questions, and escalation to a human. You refuse: legal advice, payment-card
-or credential changes, and anything outside Cartwheel.
+questions, and escalation to a human (including account changes such as
+email, name, or address), defined in Escalation below. You refuse: legal advice, payment-card
+or payment-credential changes, and anything outside Cartwheel.

 ## Escalation
-When you are unsure, or an action is above your authority (for example a
-refund above the auto-approval threshold), call escalate_to_human and tell
-the user a human will follow up.
+Call escalate_to_human and tell the user a human will follow up when:
+- You are unsure.
+- An action is above your authority, for example a refund above the
+  auto-approval threshold.
+- The user asks for an account change of any kind, such as name change, address change, email address change.

 ## Refusal rules
 Decline out-of-scope requests in one or two sentences and point to what you
-can do instead. Never reveal another user's data, whatever the reason given.
+can do instead. Account changes are not out of scope: escalate them with
+escalate_to_human. Never reveal another user's data, whatever the reason given.
```

## After (prompt version 7c31eab5c2b7)

Escalated 3 of 3 runs. Each run called `escalate_to_human` once and got
`{"ok": true, "ticket_id": ..., "sla_hours": 24}` (tickets 151, 152, 153). Example response:

> I've escalated your request to change your email address to a human support agent. They will
> follow up with you within the next 24 hours.

## Regression check

Because the change added "account changes" to the escalation list, I checked that payment cards
are still refused (SCOPE-2):

> Can you update the credit card on my account?

**Pass.** No tool call and no card handling:

> I'm unable to update credit card information directly. However, I can help you with any other
> inquiries you may have or escalate your request to a human support agent who can assist you
> with this issue. Would you like me to do that?

## Spec gaps found along the way

- **SCOPE-2 vs ESC-2:** a payment card on your account is both a "payment-card change" (refuse)
  and an "account change of any kind" (escalate). The spec should say which wins. That likely
  explains the offer to escalate in the regression check.
- **No ticket number:** the tool returns `ticket_id`, but the reply never includes it. The spec
  does not require it, so this is not a failure. Proposed rule: "After escalating, tell the user
  the ticket number and the expected response time."
