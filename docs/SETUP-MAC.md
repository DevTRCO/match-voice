# Setting up match-voice on the Mac

## 1. Tools (once)
```bash
xcode-select --install          # only if git is missing
brew install python@3.13 gh     # python 3.11+ is enough
gh auth login                   # log in as DevTRCO
```

## 2. Get the code
```bash
git clone https://github.com/DevTRCO/match-voice.git
cd match-voice
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest -q             # expect 186 passed
```

## 3. API key (by hand, never through chat or git)
Create the file `.env` in the repository root with one line:
```
ANTHROPIC_API_KEY_2=your-key
```
Use the key from the Anthropic Console workspace you set up for this project. `.env` is git-ignored.
The tests and the generator do not need it. Only the analyst does.

## 4. Work with Claude Code on the Mac
```bash
cd match-voice
claude
```
Claude reads `CLAUDE.md` on start, which has the decisions, rules and next steps. Its memory from the Windows
machine does not carry over, so that file is the handover. Say "continue with step 1 of the Next list".

## 5. Keep both machines in sync
Commit and push from one machine, `git pull` on the other. Do not copy `.venv` or `.env` between machines.
Generated matches are small and are committed. The model cache (`data/cache/`) is local to each machine.
