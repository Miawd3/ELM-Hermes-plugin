# ELM preview — tester guide

Thanks for testing. This takes about 20 minutes. You need Hermes **0.23.1 or newer** with a working model.

Use a separate test profile so your normal Hermes is untouched. Everything below uses the profile name `elmtest`; if you test in your normal profile, drop `-p elmtest` everywhere.

## 1. Set up

```sh
hermes profile create elmtest --clone          # copies your model settings
hermes -p elmtest plugins install "https://github.com/Miawd3/ELM-Hermes-plugin.git#stock-plugin"
hermes -p elmtest plugins enable elm
hermes -p elmtest elm doctor
```

✅ `elm doctor` prints `ELM 0.2.1-preview` and `Storage: ok`.

Start Hermes Desktop and switch to the **elmtest** profile. In **Capabilities → Plugins**, make sure **ELM** is **On**.

## 2. Checklist

Tick each line and note anything surprising. "Chat A" and "Chat B" are two new Desktop chats in the elmtest profile.

| # | Do this | Expected |
|---|---|---|
| 1 | In chat A send `hello`, then `/elm status` | A short error with a hint: `ELM is not on for this chat. In a terminal run: hermes elm grant <id>` (no memory shown) |
| 2 | Open **Settings → Plugins → ELM** | Page explains the grant and shows a `hermes -p elmtest elm grant …` command |
| 3 | In a terminal: `hermes -p elmtest elm grant`, pick chat A, answer `y` | "ELM granted to chat … until …" |
| 4 | In chat A: `/elm status` (or Refresh the settings page) | Shows ELM on for this chat only |
| 5 | `/elm save reference The test lighthouse has 4411 steps` | Saved, with an ID |
| 6 | Ask in plain words: `How many steps does the test lighthouse have?` | The model answers 4411 (the note was recalled) |
| 7 | Send `thanks` | Normal reply; nothing about ELM |
| 8 | Ask the model: `Please remember that my favourite colour is teal` | The model may propose a note; it is **not** saved until you approve |
| 9 | `/elm pending`, then `/elm approve <id>` | The proposal becomes an approved note |
| 10 | In chat B (not granted): `/elm search lighthouse` | Refused; chat B cannot see chat A's notes |
| 11 | In chat A: `/compress`, then ask again `How many steps does the test lighthouse have?` | Still answers 4411; `/elm status` still on |
| 12 | Settings → Plugins → ELM: open the memory manager | Lists your notes; saving, approving, trashing and restoring work |
| 13 | Settings → Plugins → ELM: turn on **Inline answer cards** | Preview card appears; nothing else changes |
| 14 | In chat A: `/elm off`, then `/elm search lighthouse` | Refused with the grant hint. (The model may still remember 4411 from earlier messages in this chat; that is normal.) |
| 15 | `hermes -p elmtest elm grant` chat A again, then `/elm list` | Your notes are still there |
| 16 | Delete chat A in Desktop, then `hermes -p elmtest elm doctor` | `records` and `chats with elm state` go down (chat A's private notes are gone) |
| 17 | Optional: grant chat B with `--project Test`, save a `project` note, grant a new chat C with `--project Test`, search there | Chat C finds the project note; a chat without the project does not |
| 18 | Optional, memory slot: `hermes -p elmtest memory setup elm`, restart Hermes, repeat steps 3–6 in a new chat | `hermes -p elmtest elm doctor` says `Memory slot: ELM is the memory provider`; the chat shows **🧠 ELM — recalled 1 memory** and the model answers 4411 |
| 20 | Optional, auto mode: `hermes -p elmtest elm auto on`, restart, save a note in a new chat D (no grant), ask about it in a new chat E, then send `/elm private` in a new chat F and ask again | D saves without a grant; E recalls the note (🧠 indicator in memory-slot mode); F does **not** recall it. `hermes -p elmtest elm auto off` turns D/E off again |
| 19 | Optional, routing: set up two agents as in the README (*memory-aware agent routing*), restart, grant a new chat, then ask: `Use delegate_task once with agent "careful" to explain ocean tides in two sentences`, then the same request with a slightly different goal and *without* an agent | `hermes -p elmtest elm routes` lists `careful: 2/2 succeeded` (ELM sent the second task to `careful`, not the default) |

## 3. Report

Open an issue at https://github.com/Miawd3/ELM-Hermes-plugin/issues (or send it to the person who asked you to test) with:

```text
Step number(s):
What you did:
What you expected:
What happened (paste exact text or a screenshot):
OS and Hermes app (Desktop / TUI / CLI):
Output of: hermes version
Output of: hermes -p elmtest elm doctor
```

`elm doctor` shows counts and versions only, never your notes or chat IDs. Please don't paste memory content or anything private.

Useful extra detail for errors: the last lines of `logs/errors.log` in your Hermes home (check them for secrets before sharing).

## 4. Clean up

```sh
hermes -p elmtest plugins remove elm
hermes profile delete elmtest      # removes the test profile and its ELM data
```

If you tested in your normal profile instead: `hermes plugins remove elm`, then delete `<your Hermes home>/plugin-data/elm/` if you also want the notes gone.

## Known limits in this preview

- Desktop chats need the terminal grant; `/elm on` only works in the classic CLI.
- Recall is keyword-based (no semantic search): ask using words that appear in the note.
- Native chat folders and "important message" markers are not part of this preview.
