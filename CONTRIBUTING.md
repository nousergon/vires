# Contributing to Vires

Thanks for your interest. Vires is licensed under **AGPL-3.0-only**.

## Developer Certificate of Origin (DCO)

All contributions are accepted under the [Developer Certificate of Origin
1.1](https://developercertificate.org/). By signing off your commits you
certify that you wrote the patch or otherwise have the right to submit it
under the project's license.

Sign off every commit with the `-s` flag:

```bash
git commit -s -m "your message"
```

This appends a `Signed-off-by: Your Name <you@example.com>` trailer. Commits
without a sign-off will not be merged.

## Inbound = outbound

Contributions are made under the same license as the project (AGPL-3.0-only).

## Development

See `README.md` for local setup. Run the test suite (`uv run pytest`) and the
linter (`uv run ruff check .`) before opening a PR; CI must be green.
