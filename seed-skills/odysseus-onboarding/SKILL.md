---
name: odysseus-onboarding
description: Living tour of Odysseus — explain what the app does, how each tab works, how the agent differs from chat, and what to try first. Use whenever a user asks for help getting started or "what can you do".
version: 1.0.0
category: general
tags: [onboarding, tutorial, help, features, capabilities, getting-started]
status: published
confidence: 1.0
source: taught
owner: REPLACE_WITH_YOUR_USERNAME
created: 2026-06-03T00:00:00Z
---

## When to Use

Trigger this skill any time the user asks something that boils down to "what is this?", "what can it do?", "how do I get started?", or "show me around". Concrete examples:

- "What can you do?" / "What are your capabilities?"
- "How do I use Odysseus?" / "How does this work?"
- "I'm new — where do I start?" / "Walk me through this"
- "What's in the [chat / cookbook / documents / research / compare / notes / calendar / email / memory / skills / gallery / settings] tab?"
- "What's the difference between chat and agent mode?"
- "How do I connect a model?" / "How do I add my email?"
- "What's the deal with skills / memory / vault / MCP?"

Also trigger when the user seems confused after a feature didn't behave as expected — they may not realize the feature exists or needs configuration first.

## Procedure

1. **Ask what they want**, don't dump the whole tour. The catalog in this skill is long; if they only need one tab, route them straight to it.
2. **If their question matches a specific tab/feature**, pull the section for it from this skill and adapt — don't recite verbatim. Add anything specific to their setup you know from prior memory.
3. **If they really want a full tour**, walk them through the "First five minutes" checklist in the body. Stop after each step and ask if they want to keep going or dive into something.
4. **Always end with a concrete next action** ("try clicking X", "open Settings → Models and add an endpoint"), never an open-ended "let me know if you have questions".
5. **If they ask about something admin-only** (shell, MCP, settings, model serving, vault) and they're not an admin, say so and tell them to ask their admin.

## Pitfalls

- **Don't pretend features exist that don't.** This skill is the source of truth. If the user asks about something not in here (e.g., "voice cloning?"), say "not as a built-in — you'd need to wire it as an MCP server or use the TTS settings."
- **Don't recommend the agent tool for trivial things.** Plain chat is faster and cheaper. Agent mode is for multi-step tasks that need tools (shell, web, file I/O).
- **Don't talk past the user's role.** Admin-only features are useless to a regular user; mention but redirect.
- **ChromaDB is optional** on this deployment. If the user asks about Memory or Personal Docs and the page shows "ChromaDB unavailable", explain it's a separate service that the operator hasn't started — keyword fallback still works for chat memory.
- **Browser tab ≠ chat session.** Each tab in the UI represents a different session (left sidebar). The browser tab is just a window into the SPA.
- **Privacy is not enforced, it's chosen.** If the user points their LLM at OpenAI/OpenRouter, prompts leave the box. Local Ollama / vLLM keeps everything on-device. They picked the destination in Settings → Models.

## Verification

- The user can name one feature they didn't know about before and say what tab it's in.
- They've completed at least the first item in the "First five minutes" checklist (configured a model endpoint).
- They know the difference between Chat (single turn) and Agent (loop with tools).
- They know admin-only features are admin-only.

## The five-minute tour

If they want the whole thing, walk through these in order:

1. **Add a model endpoint** — Settings → Models → Add. Pick a provider (Ollama, OpenAI, OpenRouter, vLLM, llama.cpp) and paste a URL. Without this nothing in Chat works.
2. **Send a chat message** — left sidebar "+" for a new session, type a message, send. If they're an admin and want tool use, toggle Agent mode in the composer.
3. **Try Compare** — same prompt to 2-3 models side-by-side, blind. Good for picking a daily driver.
4. **Add an email account** (optional) — Settings → Email Accounts → Add IMAP. Use an app password, not the real one. Then check Email tab.
5. **Enable 2FA** — user menu → 2FA. Stash the backup codes in a password manager; you won't see them again (they're bcrypt-hashed at rest now).

## The tab tour (reference)

### Chat
The default tab. Streams responses from whichever endpoint is selected (top-right model picker). Each conversation is a "session" persisted to SQLite — left sidebar lists them, you can rename, fold into folders, search.

- **Attachments**: drag files in (vision for images, text/PDF extraction for docs).
- **Web search**: toggle in composer if a search provider is configured (SearXNG, DuckDuckGo, Brave, Tavily, Serper, Google PSE).
- **Presets**: save a system prompt + model + settings combo to re-launch fast.
- **Folders**: organize sessions; right-click a session for actions.
- **Incognito / Nobody**: ephemeral sessions; wiped on restart.

### Agent
Same chat interface, but the model can call tools (shell, web, files, skills, memory). Toggle in the composer or via session settings. Built on opencode (see https://github.com/anomalyco/opencode).

- **Shell / Python tools are admin-only** for safety. Non-admin agents can still browse, take notes, search memory, etc.
- The agent runs **on the server**, not in your browser — closing the tab doesn't stop it.
- Long-running background jobs (`#!bg ...`) are picked up by the background-job monitor; the agent gets the output when they finish.

### Cookbook
Scans your hardware, recommends LLM models that fit, and one-click downloads + serves them via tmux. Built on [llmfit](https://github.com/AlexsJones/llmfit). VRAM-aware, knows GGUF / FP8 / AWQ formats, can serve via vLLM or llama.cpp.

- **Admin-only** — this is privileged model-serving on the host.
- The "What Fits?" tab tells you what your GPU can actually run before you download.
- On Apple Silicon, this works natively (Metal). In Docker it falls back to CPU.

### Deep Research
Multi-step research runs that crawl sources, read, and synthesize into a visual report (HTML page with TOC, sources panel, OG images). Adapted from [Tongyi DeepResearch](https://github.com/Alibaba-NLP/DeepResearch).

- Picks a search provider, fetches pages, summarizes per-page with a small "web summarization" model, then composes the final report with the main model.
- Runs in the background; close the tab and come back.
- SSRF-protected: won't fetch internal IPs or metadata services.

### Compare
Run the same prompt against multiple models side-by-side. **Blind mode** hides which model is which so you don't bias. Synthesis step lets a third model combine the best parts.

### Documents
Multi-tab text editor for markdown / HTML / CSV with syntax highlighting. The AI assists — it doesn't write *for* you. Inline suggestions, "rewrite this paragraph", but the user is the author.

- Per-document and global "ask the AI" panel.
- Auto-saves; per-tab undo history.
- Can attach a document to a chat session as context.

### Notes & Tasks
Google Keep–style notes with reminders (ntfy / browser push / email). Tasks are scheduled actions the agent can run — cron-style or event-triggered. Examples of built-in tasks:

- `tidy_sessions` / `tidy_documents` / `tidy_research`: housekeeping
- `summarize_emails` / `draft_email_replies` / `extract_email_events` / `check_email_urgency`: AI on incoming mail
- `daily_brief`: morning digest (calendar + email + todos)
- `consolidate_memory` / `audit_skills`: maintenance on the agent's own state

**Admin-only**: `run_local`, `run_script`, `ssh_command` — these execute arbitrary shell. The agent can't create these tasks; only a human admin can, via the UI.

### Calendar
Local-first calendar with CalDAV sync (Radicale, Nextcloud, Apple, Fastmail). Import / export `.ics`. Per-calendar colors. The agent can read it (daily-brief task uses it).

### Email
IMAP/SMTP inbox with AI triage layered on top. Per-account routing.
- **Auto-summary / auto-reply / auto-tag / auto-spam** are opt-in; off by default.
- **Important note**: when those are enabled, email bodies are sent to whichever LLM you configured. If that's a cloud provider, your email content leaves the box. Use local Ollama if email privacy matters.
- Auto-summary writes a summary into the message metadata; auto-reply drafts a reply (you still send it manually).

### Memory & Skills
The agent learns over time.
- **Memory** = facts about you and your work (vector + keyword retrieval).
- **Skills** = reusable procedures the agent applies when it recognizes a recurring pattern. This onboarding doc *is itself a skill* — you're reading the agent's own how-to-onboard-a-user playbook.
- Both are stored locally. Memory uses ChromaDB (if available) + fastembed ONNX for embeddings.

### Gallery
All generated and uploaded images in one library. Albums, search, edit. Image editor for crop / harmonize / inpaint / upscale (requires a diffusion endpoint configured).

### Library
Personal documents indexed for RAG retrieval. Drop PDFs / .docx / .epub / markdown, the agent can cite them in answers.
- Per-user owner-scoped.
- Needs ChromaDB to be running for semantic search; falls back to keyword.

### Settings
Most config lives here. The most important panels:
- **Models** — provider endpoints, default model, per-task overrides
- **Email Accounts** — IMAP/SMTP creds (encrypted at rest with Fernet)
- **Integrations** — Miniflux, Gitea, Linkding, Home Assistant, ntfy, etc.
- **MCP** — Model Context Protocol servers, admin-only
- **Vault** — Bitwarden CLI integration for secret retrieval, admin-only
- **Users** — admin-only; create accounts for household members
- **API Tokens** — admin-only; for external scripts to hit the API
- **Theme Editor / Backgrounds** — cosmetic
- **Danger Zone** — wipes (admin-only; irreversible)

## How the agent differs from plain chat

| | Chat | Agent |
|---|---|---|
| Loops | one turn = one response | model decides when it's done |
| Tools | none | web, files, shell, memory, skills, MCP servers |
| Speed | fast | slow (depends on tool latency) |
| Cost | one model call | many model calls per session |
| Background | foreground only | background `#!bg` jobs supported |
| Good for | "explain X", "rewrite this" | "draft and send 3 reply emails", "find the bug in this repo and propose a patch" |

Default to Chat. Switch to Agent only when the request genuinely needs tools.

## Privacy & ownership

- **Per-user owner scoping** on everything: chat sessions, notes, calendar, email accounts, library docs, skills, memory, gallery images. You can't see your spouse's data and vice versa.
- **Admins** can see admin-managed config (Settings, Users, Integrations) but the data scoping still applies — being an admin doesn't make you read someone else's chats.
- **Secrets** (IMAP/SMTP passwords, integration API keys, persisted session tokens) are encrypted at rest with Fernet.
- **Logs** mask Bearer / sk- / hf_ / ody_ / AWS / Slack tokens and `password=` URI fragments before writing.
- **Email HTML** from senders is allowlist-sanitized before render — incoming email can't run scripts in your browser.

## Admin vs regular user

| Feature | Regular | Admin |
|---|---|---|
| Chat, Documents, Notes, Calendar, Email, Library, Gallery | ✅ | ✅ |
| Web search, Compare, Research, Memory, Skills | ✅ | ✅ |
| 2FA, change password, theme | ✅ | ✅ |
| Create users, Integrations, MCP, Vault, API Tokens, Settings → Models | ❌ | ✅ |
| Shell tool, Python tool, run_*/ssh_command tasks, Cookbook | ❌ | ✅ |
| Wipes / Danger Zone | ❌ | ✅ |
| Open signup toggle | ❌ | ✅ |

Non-admins still get a useful product. Asking your admin for a feature you can't access is normal.

## First five minutes for a new user

A concrete starter checklist. Do them in order, stop when you have what you need.

1. **Change your password** — user menu → Change Password. The bootstrap-time password lands in logs forever; rotate it.
2. **Enable 2FA** — user menu → 2FA. Set up your authenticator. **Save the backup codes** in a password manager — they're hashed at rest, so this is your only chance to capture them.
3. **Add a model endpoint** — Settings → Models → Add. If you don't have one, use OpenRouter as a quick start (free models available) or run Ollama on another tailnet host and point at it.
4. **Send a chat message** — left sidebar "+" → say hi. Make sure responses stream.
5. **Pick a default model** — Settings → Models → Default. Saves you the per-session picker.
6. *(optional)* Connect email — Settings → Email Accounts → Add. Use IMAP/SMTP with an **app password**, not your real account password.
7. *(optional)* Try Compare with the same prompt across 2-3 models to pick a daily driver.
8. *(optional)* Drop a few PDFs into Library so the agent can cite them.

## Common questions

**Q: Where is my data stored?**  
On the server's disk (this deployment: a t4g.medium EC2 with an encrypted EBS root volume, daily snapshots, 14-day retention). SQLite for structured data; files under `data/`. No cloud third-party storage unless you configure one (e.g., S3 backups, cloud LLM).

**Q: Can I export everything?**  
Yes — Settings → Backup → Export. Round-trips memory, presets, skills, notes, calendar. Email + chat history are in the SQLite DB you can snapshot via the AWS console.

**Q: How do I share something with my spouse?**  
There's no built-in cross-user share. The recommended pattern is to copy/paste the content into a chat with them via another tool, or grant them admin so they can see the system config (still not your private chats — that's by design).

**Q: Can the agent send emails on its own?**  
Yes if you have Email Send enabled AND the agent is in Agent mode AND you've granted it tool access. By default `draft_email_replies` only drafts; sending still requires you to click Send.

**Q: What happens if the box reboots?**  
- systemd brings `odysseus.service` back up automatically
- Tailscale reconnects (state on the EBS volume)
- Active chat sessions persist
- In-flight agent tool calls are lost (no checkpointing)

**Q: Why does the URL have `-1` in it (`odysseus-1.<tailnet>.ts.net`)?**  
A previous Tailscale node with the same hostname was orphaned from an earlier deploy. Remove the stale `odysseus` node in the Tailscale admin console, then restart `tailscaled` on the box to reclaim the clean hostname.

**Q: How do I update Odysseus?**  
SSH in via Tailscale: `cd /opt/odysseus/app && git pull && ./venv/bin/pip install -r requirements.txt && sudo systemctl restart odysseus`.
