# Getting started on Windows (for a first-time coder)

This walks you from a fresh Windows PC to running the dashboard script on your
own machine and seeing a preview of the screen in your browser. No prior
programming experience assumed. Take it one numbered step at a time.

When you're done here, follow [`README.md`](README.md) → **One-time setup** to
point it at *your* TRMNL device and put it on autopilot (GitHub Actions running
the update, and a free external timer to trigger it on schedule).

Everything below is free.

---

## What you're installing and why

| Tool | What it's for |
| --- | --- |
| **Git** | Downloads the code and tracks your changes. |
| **Python** | The language the script is written in; runs it. |
| **VS Code** | The editor you'll read and change the code in. It also gives you a built-in terminal. |
| **A GitHub account** | Where your copy of the project lives online, and what runs it on a schedule for free. |

A **terminal** (also called a "command line" or "shell") is the text box where
you type commands. On Windows the one we'll use is **PowerShell**, and VS Code
has it built in — you'll see it near the bottom of the window.

---

## 1. Install Git

1. Go to <https://git-scm.com/download/win> — the download starts automatically
   ("64-bit Git for Windows Setup").
2. Run the installer. **Click Next through every screen** — the defaults are
   fine. Don't worry about the options you don't recognise.
3. When it finishes, you're done. Nothing opens; that's expected.

To check it worked, open the Start menu, type `PowerShell`, press Enter, and in
the window that opens type:

```powershell
git --version
```

You should see something like `git version 2.47.0`. If it says "not
recognized", restart your PC and try again.

---

## 2. Install Python

1. Go to <https://www.python.org/downloads/windows/> and download the latest
   **"Windows installer (64-bit)"** under the newest stable release.
2. Run it. **On the first screen, tick the box that says
   "Add python.exe to PATH"** at the bottom. This matters — if you miss it,
   the commands later won't work.
3. Click **"Install Now"**, accept any admin prompt, and let it finish.

Check it, in a **new** PowerShell window (open a fresh one so it picks up the
change):

```powershell
python --version
```

You should see `Python 3.13.x` or similar. If you instead get sent to the
Microsoft Store, or it says "not recognized", re-run the installer, choose
**Modify**, and make sure "Add Python to environment variables" is ticked.

---

## 3. Install VS Code

1. Go to <https://code.visualstudio.com/> and click the big blue **Download for
   Windows** button.
2. Run the installer. Accept the licence. On the "Select Additional Tasks"
   screen, tick **"Add 'Open with Code' action to Windows Explorer file context
   menu"** and **"Add to PATH"** — both are handy. Then Next → Install.
3. Launch VS Code when it finishes.

### Add the Python extension

1. In VS Code, click the **Extensions** icon in the left bar (four little
   squares), or press `Ctrl+Shift+X`.
2. Search for **Python** — the one published by **Microsoft**. Click
   **Install**. (This also pulls in "Pylance", which is what you want.)

---

## 4. Get your own copy of the project

You should already have your own repository on GitHub — either from clicking
**"Use this template"** on James's repo, or a fresh repo he helped you set up.
Open that repo's page on github.com in your browser.

1. Click the green **`< > Code`** button, and under **HTTPS** click the copy
   icon to copy the URL. It looks like
   `https://github.com/your-username/trmnl-dashboard.git`.
2. In VS Code, press `Ctrl+Shift+P`, type **`Git: Clone`**, press Enter, and
   paste the URL.
3. It asks where to put the folder — pick somewhere like your `Documents`
   folder. When it finishes, click **"Open"** in the popup.
4. If VS Code asks *"Do you trust the authors of the files in this folder?"* —
   yes, it's your code, click **"Yes, I trust the authors"**.

You now have the project open. On the left you'll see files like
`fetch_and_push.py`, `template.html`, and `README.md`.

---

## 5. Open the terminal in VS Code

- Menu bar: **Terminal → New Terminal**, or press `` Ctrl+` `` (the key above
  Tab).
- A panel opens at the bottom. The text prompt there should show your project
  folder name. This is where you type the commands in the next steps.

If the prompt says "cmd" or something odd, click the **`v`** next to the `+` in
the terminal panel's top-right and choose **PowerShell**.

---

## 6. Create a virtual environment

A "virtual environment" (venv) is a private box for this project's Python
add-ons, so they don't collide with anything else on your PC. You make it once.

In the VS Code terminal:

```powershell
python -m venv .venv
```

That creates a `.venv` folder (it's ignored by Git on purpose). Now switch your
terminal into it:

```powershell
.\.venv\Scripts\Activate.ps1
```

Your prompt should now start with **`(.venv)`**. That means it's active.

> **If you get a red error about "running scripts is disabled on this
> system"**, run this once, then try the `Activate.ps1` line again:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
> ```
> Answer `Y` if it prompts. This is a standard, safe setting for development.

VS Code usually notices the `.venv` and will offer to use it automatically —
if it pops up a message asking to select it, say yes. From now on, each time
you open a new terminal, run the `Activate.ps1` line again (or just let VS Code
do it — new terminals it opens are usually activated for you).

---

## 7. Install the project's dependencies

With `(.venv)` showing in your prompt:

```powershell
pip install -r requirements.txt
```

This downloads the three small libraries listed in
[`requirements.txt`](requirements.txt). Takes a few seconds. Warnings in yellow
are usually fine; a red **ERROR** is not — if you get one, copy the text and
ask James.

---

## 8. See a preview — no device or accounts needed yet

```powershell
python preview.py --fake
```

This renders the screen layout with made-up sample data and opens
`preview.html` in your browser. It won't be your real weather or teams, but it
proves everything is installed and working. If a browser tab opens with a
dashboard-looking layout: **you're set up.** 🎉

---

## 9. Now do the real setup

Open [`README.md`](README.md) and work through **"One-time setup"**. In short,
you'll:

1. Make a **TRMNL account** and create a **private plugin** (Webhook strategy).
   TRMNL gives you a webhook URL that is the *only* thing tying the data to
   *your* screen.
2. Get a free **football-data.org API key**.
3. Pick your **weather location** (a latitude/longitude).
4. Copy `.env.example` to `.env` and fill in those values:
   ```powershell
   copy .env.example .env
   ```
   Then open `.env` in VS Code and replace each `REPLACE_WITH_...`. **Never
   share this file or commit it** — it's your private config, and Git is
   already set to ignore it.
5. Run `python fetch_and_push.py` to push real data to your screen.
6. Add the same values as **Secrets and variables** in your GitHub repo so the
   included GitHub Action can run the update in the cloud, without your PC being
   on.
7. Set up a free external timer to trigger that Action on a schedule. GitHub's
   own built-in schedule is unreliable for new repos — it can sit idle for
   hours or days — so the README's **"Make the schedule reliable"** step walks
   you through pointing a free service (cron-job.org) at it instead. Do this
   step or the screen won't refresh on its own.

---

## Making it yours

The teams in the sports panel (Liverpool, Blue Jays, Maple Leafs, Raptors,
Bills) are written into [`fetch_and_push.py`](fetch_and_push.py) — look for
`collect_games()` and the ESPN calls around it. Changing those to your teams is
a good first coding exercise; the README's **Notes** section explains how the
pieces connect. Ask James — that's the fun part.

---

## Everyday commands, once you're set up

| You want to… | Do this |
| --- | --- |
| Open the project | Open VS Code → **File → Open Recent** |
| Turn on the venv in a new terminal | `.\.venv\Scripts\Activate.ps1` |
| Preview the layout | `python preview.py --fake` (or `python preview.py` for live data) |
| Push real data to your screen now | `python fetch_and_push.py` |
| Save your code changes | In VS Code's **Source Control** tab (`Ctrl+Shift+G`): type a message, **Commit**, then **Sync / Push** |

If something breaks, the error text in the terminal is the thing to copy and
send to James — it almost always says what's wrong.
