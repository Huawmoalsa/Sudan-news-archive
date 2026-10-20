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

## Archive Schema & Classification

Each archived item may include these classification fields:

- `content_type`:
  - `news_report`: reserved for items identified as news reports.
  - `opinion_analysis`: opinion, commentary, or analysis content identified by the rules.
  - `promotional`: fundraising, donation, or promotional content identified by the rules.
  - `uncertain`: the rules did not identify a content type.

- `relevance_to_sudan`:
  - `direct`: Sudan-related keywords were found.
  - `indirect`: keywords associated with neighboring countries or regional topics were found, without a direct Sudan keyword.
  - `unclear`: the current rules did not identify either category.

- `classification_method`: `keyword_rules` identifies items classified using simple keyword-matching rules.

These labels are preliminary automation, not editorial judgments, semantic analysis,
or verification of factual accuracy. Keyword matching can produce false positives
and false negatives. For example, mentioning Egypt does not by itself establish
a meaningful connection to Sudan. `uncertain` and `unclear` indicate limitations
of the current rules, not proof that an item is irrelevant or not a news report.

Items remain `unverified` unless independently verified. Classification does not
change verification status.
