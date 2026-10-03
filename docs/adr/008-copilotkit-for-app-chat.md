# 008: CopilotKit as the chat layer for the web and mobile apps

## Status
Proposed. To be decided by the Sprint 4 test below, before any app chat code is written.

## Context
The plan builds the office web app (React with Vite) and the cleaner app (Expo) in Phase 1,
with chat over AG-UI and shared chat components. The node already serves AG-UI at `/ag-ui`
(Pydantic AI `AGUIAdapter`). CopilotKit (MIT core) is a React front end for AG-UI agents with a
Pydantic AI integration. It has:

- chat components and headless hooks;
- generative UI (render tool calls, progress and state);
- human in the loop (pause the run and wait for the user);
- shared state between app and agent, and frontend tools (functions that run in the browser);
- a React Native package.

It also has a Node.js Copilot Runtime, which can be self-hosted or run on its hosted Copilot
Cloud, and premium features (fully headless chat UI, observability, Inspector) that need a
license key (free for self-hosting; paid Pro and Enterprise plans for the cloud).

Fit with the architecture:

- Good: AG-UI and Pydantic AI support, React for web, a React Native package for mobile,
  hooks to build our own block components.
- Conflict: Copilot Cloud would carry chat, which is business data, through a third party. Mia
  Cloud never holds business data (CLAUDE.md), and nothing leaves the node except through the
  egress layer (rule 6).
- Conflict: the Copilot Runtime is an extra Node.js server per client install, against "static
  apps served by the node, no extra server to install" (plan). The React Native docs say a
  self-hosted runtime is required there.
- Care needed: frontend tools run in the browser, outside the tool guard (rules 3 and 4).
  Human in the loop pauses a run in the UI, but approvals are records decided by the node's
  approval service (ADR 003, ADR 005).

## Decision
1. Copilot Cloud is not used.
2. Mia's message blocks (`mia/chat/blocks.py`) stay the format agents return. They also feed
   channel adapters and voice (ADR 007), so the apps only render them.
3. If adopted, CopilotKit is used only as a UI library inside the apps: its hooks and headless
   pieces carry the AG-UI stream and state, and our own components render the blocks.
4. Frontend tools may only change the UI (open a visit, filter the board). Every write goes
   through a node tool or endpoint with the permission check.
5. The approval card's Approve and Reject call the node's approvals endpoint; a human in the
   loop pause never decides an approval by itself.
6. Sprint 4 test (one to two days), before building app chat:
   - connect a React with Vite page and an Expo screen straight to the node's `/ag-ui`, with
     no Copilot Runtime;
   - render text, card, quick replies and approval card blocks, with Approve and Reject wired
     to `/approvals/{id}/decide`;
   - capture outbound traffic during use, with and without a license key, and confirm nothing
     leaves the node;
   - check whether the free (non-premium) hooks are enough for our own components.

   Adopt CopilotKit if all four pass. If the runtime is required, or anything leaves the node,
   use the AG-UI client libraries directly instead and write our own small hooks.

## Consequences
- Agents, tools, approvals, blocks and channels do not change whichever way the test goes.
- Adopting CopilotKit adds npm dependencies to apps/web and apps/mobile only; the node gains
  none.
- If the runtime turns out to be required for mobile, that alone rules out CopilotKit for the
  cleaner app, unless the product owner accepts an extra service in the install (new ADR).
