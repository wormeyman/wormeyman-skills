---
name: getting-command-output
description: Use when a command needs the user's hands - a sudo password, a passphrase, or a machine the agent cannot reach (another computer, a live USB) - and the agent must read the output afterwards. Also use whenever you are about to write "paste the output here", "run this and tell me what it says", or "copy the result back". Covers tmux windows, logging with script, waiting, secrets in logs, and sending results back with Tailscale Taildrop.
---

# Getting command output without pasting

The user types only what you can't: a password or passphrase. Everything else comes back to you as a file you read yourself. **Never ask the user to paste output.**

**Read the script or command first.** You need the order of its prompts, and you need to know whether it prints a secret (see Secrets).

## On the machine you run on

This assumes the user works in a tmux session (`<session>` below; ask once if you don't know it). In one shell call, open a window and run the command inside `script`, which logs everything:

```bash
LOG=<scratch dir>/logs/<name>.log; mkdir -p "$(dirname "$LOG")"
tmux new-window -d -P -F '#{window_index}' -t <session>: -n <name> -c <dir>
tmux send-keys -t <session>:<name> -l "script --flush --quiet --command '<command>' $LOG"
tmux send-keys -t <session>:<name> Enter
```

- The text is typed into the user's shell, so match its syntax. Keep `<command>` free of single quotes, or put it in a script file.
- **Press Enter yourself when sudo or a passphrase prompt gates the command.** Typing the password is the user's OK. For a command that changes things with no prompt at all, send it without Enter and ask them to press it.
- Tell the user the window number (`-P` prints it) and the prompts they will see, in order.
- Wait in the background: `timeout 1800 bash -c 'until grep -q "Script done" "$0"; do sleep 2; done' "$LOG"`.
- Read it: `sed 's/\x1b\[[0-9;?]*[A-Za-z]//g; s/\r//g' "$LOG"`. The last line has `COMMAND_EXIT_CODE`.
- Then `tmux kill-window -t <session>:<name>`. Never type into a window running an agent.

Use `script` (util-linux), not `tee`: prompts, progress bars and `[Y/n]` keep working, and stderr and the exit code land in the log.

**Reboots:** a scratch dir in `/tmp` does not survive one. If the step ends in a reboot, tell the user to wait until you have read the log. After a reboot, read the last boot with `journalctl -b -1`.

## On a machine you can't reach

Use Tailscale's Taildrop. Give the user one line that saves output and exit codes to a file and sends it to your machine. In fish:

```
begin; <cmd1>; echo "exit: $status"; <cmd2>; echo "exit: $status"; end &> ~/Downloads/<name>.txt; tailscale file cp ~/Downloads/<name>.txt <your-host>:
```

In bash or zsh, use `{ ...; } &> file` and `$?`. On a Mac the CLI may only exist at `/Applications/Tailscale.app/Contents/MacOS/Tailscale`. sudo's prompt still shows on screen.

Receive it yourself, in the background. No sudo is needed if your user is tailscale's operator (`tailscale set --operator=$USER`):

```bash
tailscale file get --wait --verbose --conflict=rename ~/Downloads
```

`--verbose` shows the saved name. For anything longer, write a script, Taildrop it over, and make its last step send the report back the same way.

**A machine you can SSH into:** run it there yourself. **A live USB:** have the user start sshd and add their keys from `https://github.com/<user>.keys`, then SSH in.

## Secrets

Passphrases typed at a prompt don't echo, so they never reach the log. A command that **prints** a secret (`systemd-cryptenroll --recovery-key`, a private key) must not run under `script`:

- Run it plainly in its own window, followed on the same line by writing its exit code to the log and a check that prints no secret (for example the key slot list). Staying on one terminal also keeps sudo's cached password, which is per terminal on many distros.
- Never `capture-pane` that window. Kill it only after the user says the secret is saved, so it leaves tmux's scrollback.

## Common mistakes

| Mistake | Instead |
|---|---|
| "Paste the output here" | Log to a file and read it |
| Copying to the clipboard for the user to paste | Taildrop the file back |
| `cmd \| tee log` | `script --command cmd log` |
| A wait loop with no timeout | `timeout 1800 ...` |
| Letting a reboot wipe an unread log | Read it first, or `journalctl -b -1` |
| Leaving finished windows or sent copies | `kill-window`; delete the copies once read |
