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

## Inbound license

By submitting a contribution, you agree that your contribution is licensed to
the project under the **MIT License**, regardless of the project's outbound
license (AGPL-3.0-only; see LICENSE). This permits the project to distribute
your contribution under its current license and under commercial licenses. If
you cannot contribute under these terms, please open an issue instead of a
pull request.

## Development

See `README.md` for local setup. Run the test suite (`uv run pytest`) and the
linter (`uv run ruff check .`) before opening a PR; CI must be green.
