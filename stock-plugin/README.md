# ELM — long-term memory for Hermes (preview)

ELM gives Hermes a local, reviewable long-term memory. It is a normal Hermes plugin: no changes to Hermes itself.

- **You decide what is remembered.** Save notes yourself, or let the model *propose* notes that you approve.
- **Private by default.** Memory belongs to one chat unless you share it with a project or across your chats.
- **Recalled automatically.** Relevant approved notes are added to the model's context when they match what you ask.
- **Local.** Everything is stored on your computer, in your Hermes profile. Nothing is uploaded except what ends up in a chat you send to your model provider.

> **Preview.** This build is for testing. Please use the [tester guide](TESTING.md) and report what you find.

## Requirements

- Hermes **0.23.1 or newer** (Desktop, TUI or CLI), on Windows, macOS or Linux.
- A model configured in Hermes. ELM itself works without any model; the optional search planner and organizer use one.

## Install

```sh
hermes plugins install "https://github.com/Miawd3/ELM-Hermes-plugin.git#stock-plugin"
hermes plugins enable elm
```

Or in Desktop: **Plugins → Install from repository**, paste the URL above.

Restart Hermes. In Desktop, open **Capabilities → Plugins** and make sure **ELM** is switched **On**.

Check it: `hermes elm doctor` should print `Storage: ok`.

### Optional: make ELM Hermes's memory provider

Hermes has one slot for an external long-term memory. To put ELM there:

```sh
hermes memory setup elm        # or: hermes config set memory.provider elm
```

Restart Hermes. `hermes elm doctor` then says `Memory slot: ELM is the memory provider`, and chats show
**🧠 ELM — recalled N memories** when a note is added. Everything else (grants, `/elm` commands,
privacy) works exactly the same; Hermes's own built-in memory keeps working next to it. ELM recalls
the same way in both modes, never twice. To go back: `hermes config set memory.provider builtin`.
Only one external memory provider can be active, so this replaces another one (for example Honcho or mem0) if you had it.

## Turn ELM on for a chat

ELM never turns itself on. You enable it for **one chat at a time**.

**Desktop (and TUI chats served by the Desktop/gateway):** Hermes cannot tell these apps apart, so you grant access from a terminal on the same computer. The model can never grant access.

1. Open the chat and send any message so it is saved.
2. In a terminal run:
   ```sh
   hermes elm grant
   ```
   Pick the chat from the list (newest first) and confirm with `y`. For a named profile: `hermes -p NAME elm grant`.
   Desktop's **Settings → Plugins → ELM** page also shows the exact command for the chat you are in.
3. Back in the chat, send `/elm status`, or press **Refresh** on the ELM settings page.

A grant lasts 24 hours by default (`--hours` up to 168). Turn it off with `/elm off` or `hermes elm revoke`; your saved notes are kept.

**Classic CLI (`hermes chat`):** just type `/elm on` in the chat.

## Use it

| You want to… | Do this |
|---|---|
| Save something | `/elm save reference The staging server is at 10.0.0.5` (kinds: `user`, `project`, `reference`, `skill`) |
| Find something | `/elm search staging server`, or just ask — matching notes are recalled automatically |
| Review model proposals | `/elm pending`, then `/elm approve <id>` or `/elm trash <id>` |
| Browse / edit | `/elm list`, `/elm edit <id> <new text>`, `/elm restore <id>`, or the memory manager in **Settings → Plugins → ELM** |
| Share with other chats | Grant with `--project NAME` (same project) or `--user` (your shared user facts) |
| Keep a record of the conversation | Grant with `--capture` (saves finished turns as plain text on this computer) |
| See every command | `/elm help` |

Model choices for the optional search planner and organizer: **Settings → Models → Auxiliary → ELM Search / ELM Organizer**.

## What happens when…

- **A long chat is compressed:** ELM keeps the chat's access and its private notes, even if Hermes moves the chat to a new session ID.
- **You delete a chat:** its private notes and captured text are deleted too. Project and shared notes stay. Archiving a chat keeps everything.
- **You say "ok" or "thanks":** nothing is recalled. Recall only uses meaningful words and doesn't repeat a note it already added to the chat.
- **You uninstall ELM:** your data stays in `<profile>/plugin-data/elm/` until you delete that folder.

## Privacy and limits

- This is personal memory for one person per Hermes profile, **not** a multi-user permission system. Use separate profiles for separate people.
- Any app connected to the *same* granted chat (for example an editor client) can use that chat's memory.
- Notes recalled into a chat are sent to your model provider like any other message.
- Captured text is stored as plain text; don't enable capture in chats that contain passwords or secrets.
- Not included yet: native chat folders, "important message" markers, semantic (embedding) search.

## Uninstall

```sh
hermes plugins disable elm
hermes plugins remove elm
```

Then delete `<profile>/plugin-data/elm/` if you also want to delete your memory (`hermes elm doctor` shows the profile path before you remove it).

## More

- [Tester guide](TESTING.md) · [Changelog](CHANGELOG.md) · [Detailed behaviour and verification notes](docs/DETAILS.md)
- License: Apache-2.0
