# secrets/

Put an optional `cookies.txt` here (Netscape cookie-file format) if you
need Instagram (or another platform) authenticated as a real account —
see the main [README.md](../README.md#instagram-cookies-optional).

**Never commit anything in this directory except this file and
`.gitkeep`** — `cookies.txt` is a live session credential, equivalent to
a password for whatever account it belongs to. `.gitignore` already
excludes it, but double-check before you `git add -A`.
