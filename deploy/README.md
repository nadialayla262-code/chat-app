# Your own box

One run puts the spine, Homei, Handi, HTTPS and a weekly restore-tested backup on a
machine you own. Debian 12 or Ubuntu 24.04. Not in the Netherlands.

    git clone <this repository> cxi && cd cxi
    sudo ./deploy/install.sh cxi.example.org you@example.com

Add `--with-ollama` to put the local model on the same box (CPU-only is slow but works;
a box with 8 GB of memory runs `qwen3:4b`). Then open `https://cxi.example.org/_/`
once, create the superuser, put its email and password in `/etc/cxi/env`, and
`systemctl restart cxi-handi`.

The script is safe to run again: it keeps your settings, never touches the database,
and deletes nothing. `--dry-run` prints every step and changes nothing.

Moving from the Mac: stop the Mac's spine, copy `pb_data/` to `/opt/cxi/app/pb_data`
on the box, `chown -R cxi:cxi /opt/cxi`, `systemctl restart cxi-spine`. Point Lovable
at `https://cxi.example.org` in its one thin-layer file. Google then holds views only.

What is not here yet: WireGuard for a private admin path (the admin page is behind the
superuser password only), and off-box copies of the backups. Both are one unit each.
