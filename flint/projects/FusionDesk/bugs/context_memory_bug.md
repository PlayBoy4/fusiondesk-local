# Fusion Slow / Context Bug

## Problem
Fusion/Tatum is forgetting information already provided in the same chat.
It also gives inconsistent answers about internet/tool access.

## Example
- User gave name and birthday.
- Bot later said it did not see the name or birthday.
- Bot first said no internet, then said it had agent_reach, then failed to use prior context.

## Required Fix
- Add short-term conversation memory.
- Add tool-state awareness.
- Add visible context recap before tool use.
- Never claim internet access unless the connector is active.
- If user says “I already gave it,” check current conversation state first.

## Priority
HIGH
