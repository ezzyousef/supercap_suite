# Beginner's Guide: Running This App with Visual Studio Code

This guide assumes you have never programmed before. Follow every step in
order — don't skip ahead. It's written for Windows, with notes for macOS
where the steps differ. It should take about 20-30 minutes the first time.

**Two different things are called "Visual Studio":**
- **Visual Studio Code** ("VS Code") — a free, lightweight code editor. **This is what we use.**
- **Visual Studio** (no "Code") — a much bigger program for C++/C#/.NET. **We do NOT need this one.**

If you already have "Visual Studio" installed, that's fine, but for this
guide, install **Visual Studio Code** separately (step 2 below).

---

## Step 1 — Install Python

The app is written in Python, so your computer needs Python installed to run it.

1. Go to **https://www.python.org/downloads/** in your web browser.
2. Click the big yellow "Download Python 3.x.x" button (any version 3.10 or
   newer works — the site will suggest the latest one automatically).
3. Run the downloaded installer.
4. **Important:** on the very first installer screen, check the box that
   says **"Add python.exe to PATH"** (Windows) before clicking Install. If
   you miss this box, later steps won't find Python and you'll need to
   reinstall.
5. Click "Install Now" and wait for it to finish, then close the installer.

**Check it worked:**
1. Open the Start Menu, type `cmd`, and press Enter to open Command Prompt.
2. Type this and press Enter:
   ```
   python --version
   ```
3. You should see something like `Python 3.12.1`. If you instead see an
   error like "python is not recognized," restart your computer (this
   refreshes the PATH) and try again. If it still fails, reinstall Python
   and make sure you checked the "Add to PATH" box.

*(macOS: download the macOS installer from the same page, or if you have
Homebrew, run `brew install python3` in Terminal. Check with `python3 --version`.)*

---

## Step 2 — Install Visual Studio Code

1. Go to **https://code.visualstudio.com/**.
2. Click the "Download" button for your operating system (Windows/Mac/Linux).
3. Run the installer, accepting all the default options, and let it finish.
4. Open VS Code once to confirm it launches (Start Menu → "Visual Studio Code").

## Step 3 — Install the Python extension for VS Code

1. In VS Code, look at the row of icons on the far left edge. Click the
   icon that looks like four squares (one detached) — this is the
   **Extensions** panel. (Or press `Ctrl+Shift+X`.)
2. In the search box at the top, type `Python`.
3. Find the extension simply called **"Python"** published by **Microsoft**
   (it has a blue/yellow icon) and click **Install**.
4. Wait for it to finish installing. You can close the Extensions panel now.

---

## Step 4 — Get the app onto your computer

1. Download the `supercap_suite.zip` file that was shared with you (or the
   project folder, if you received it unzipped).
2. Find the downloaded `.zip` file (usually in your Downloads folder).
3. Right-click it and choose **"Extract All..."** (Windows) or double-click
   it (macOS) to unzip it.
4. Choose somewhere easy to find, e.g. extract it to your Desktop. You
   should end up with a folder called `supercap_suite` containing folders
   like `core`, `ui`, `docs`, and a file called `main.py`.

---

## Step 5 — Open the project folder in VS Code

1. Open VS Code.
2. Go to the menu **File → Open Folder...** (on macOS: **File → Open...**).
3. Browse to and select the `supercap_suite` folder (the one containing
   `main.py`) and click "Select Folder" / "Open".
4. VS Code will reload showing the project's files in the left-hand
   sidebar (an "Explorer" panel). You should see `main.py`, `core/`, `ui/`,
   `docs/`, `requirements.txt`, and `README.md`.
5. If VS Code asks "Do you trust the authors of the files in this folder?"
   click **Yes, I trust the authors**.

---

## Step 6 — Open a terminal inside VS Code

1. Go to the menu **Terminal → New Terminal** (or press `` Ctrl+` `` — the
   backtick key, usually above Tab).
2. A panel opens at the bottom of the window with a command prompt. This
   terminal automatically starts in your project folder, so you don't need
   to type any `cd` (change directory) commands.

---

## Step 7 — Create a virtual environment (recommended, keeps things tidy)

A "virtual environment" is a private, isolated copy of Python just for this
project, so installing packages for this app doesn't affect anything else
on your computer. This step is optional but strongly recommended.

In the terminal you just opened, type:

```
python -m venv venv
```

Press Enter and wait a few seconds — this creates a folder called `venv`
inside your project.

**Activate it:**

- Windows (Command Prompt or PowerShell):
  ```
  venv\Scripts\activate
  ```
- macOS/Linux:
  ```
  source venv/bin/activate
  ```

After activating, you should see `(venv)` appear at the start of the
terminal prompt line. You'll need to repeat this "activate" command every
time you open a new terminal to work on this project (you do NOT need to
recreate the `venv` folder each time, just re-activate it).

If VS Code asks "We noticed a new environment has been created, do you want
to select it for the workspace folder?" — click **Yes**.

---

## Step 8 — Install the required packages

With the terminal still open (and `(venv)` showing if you did Step 7), type:

```
pip install -r requirements.txt
```

Press Enter. This downloads and installs everything the app needs
(PySide6 for the window/buttons, pandas for reading Excel files,
matplotlib for plots, scipy for the equivalent-circuit fitting, etc.). It
can take a few minutes depending on your internet connection — you'll see
a lot of text scroll by; that's normal.

If it finishes without a red "ERROR" message at the end, you're done with
this step.

---

## Step 9 — Run the app

In the same terminal, type:

```
python main.py
```

Press Enter. After a few seconds, the application window should open, with
tabs across the top: Manual Calculator, GCD, Cyclic Voltammetry, Rate
Study, EIS, DSC, and About.

**To stop the app**, just close its window, or click back in the terminal
and press `Ctrl+C`.

**Every time you want to run the app again later:** open VS Code, open a
terminal (Step 6), activate the virtual environment if you made one
(Step 7's activate command), then run `python main.py` again. You do NOT
need to repeat Steps 7-8 (creating the environment / installing packages)
unless you deleted the `venv` folder.

---

## Troubleshooting

**"python is not recognized as an internal or external command"**
Python isn't on your PATH. Reinstall Python (Step 1) and make sure you
check "Add python.exe to PATH" during installation, then restart your
computer.

**"No module named PySide6" (or pandas, numpy, etc.)**
The packages weren't installed, or you're not in the virtual environment
you installed them into. Run Step 7's activate command, then re-run Step 8.

**pip install fails with a network/SSL error**
Usually a firewall or proxy issue. Try again on a different network, or
ask your IT department if you're on a work/school computer with a
restrictive network.

**The window opens but looks broken/blank**
Make sure your graphics drivers are up to date. On some remote-desktop or
virtual-machine setups, Qt (the toolkit this app's window is built with)
can have display issues — try running it on a normal, non-remote desktop
session.

**I get a different error I don't understand**
Copy the full red error text from the terminal and search for it online,
or share it with whoever gave you this app for help. Errors in Python
almost always tell you the exact file and line number where something
went wrong, which is very useful information to pass along.

---

## Step 10 (optional) — Build a standalone .exe so you don't need Python installed every time

If you want to share the app with someone (or run it yourself) without
them needing to install Python and all these packages, you can package it
into a single executable file.

1. With your virtual environment activated (Step 7), install PyInstaller:
   ```
   pip install pyinstaller
   ```
2. Build the executable:
   ```
   pyinstaller --onefile --windowed --name SupercapSuite main.py
   ```
3. Wait for it to finish (this can take a few minutes). When done, look
   inside the new `dist` folder that appeared in your project — you'll
   find `SupercapSuite.exe` (Windows) or `SupercapSuite` (macOS/Linux).
4. That single file can be copied to another computer of the **same
   operating system** and double-clicked to run, without installing Python.

**Important limitation:** you can only build a Windows .exe on a Windows
computer, a macOS app on a macOS computer, and so on — there's no way to
build a Windows executable from a Mac or Linux machine (or vice versa) in
this setup.

---

## Quick reference: the commands you'll actually use most often

```
cd path\to\supercap_suite     (only needed if your terminal isn't already there)
venv\Scripts\activate          (Windows — do this every session)
python main.py                 (run the app)
```
