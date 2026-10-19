# Sudan News Archive

Daily RSS/Atom collection for later, on-demand analysis.

## Configure sources
Add one verified RSS or Atom URL per line to `config/feeds.txt`.
Lines starting with `#` are ignored.

## Run locally
    python scripts/collect.py

Archives are stored at `archive/YYYY/MM/YYYY-MM-DD.json`.

## Automation
GitHub Actions runs daily at 05:17 UTC and can also be started manually
from the Actions tab.

## Evidence discipline
Items are marked `unverified` by default. Multiple outlets repeating the
same claim are not automatically independent confirmation. Collection
does not perform strategic analysis.
