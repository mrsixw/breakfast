# Troubleshooting

## "GITHUB_TOKEN not set in environment - exiting..."

breakfast requires a GitHub personal access token. Set it in your environment:

```bash
export GITHUB_TOKEN="ghp_your_token_here"
```

The token needs `repo` scope to access pull request data. Generate one at [github.com/settings/tokens](https://github.com/settings/tokens).

## No PRs displayed

- Verify the owner name is correct (`-o` / `--owner`)
- Check that the repo filter (`-r`) matches at least one repository name (it's a substring match)
- If using `--mine-only`, ensure the token belongs to the user whose PRs you want to see
- If using `--ignore-author`, check you haven't accidentally filtered out the authors you want

## API errors (502, 503, 504), timeouts, and network loss

breakfast automatically retries REST and GraphQL API requests on transient server errors and network timeouts with exponential backoff (up to 3 retries).

To prevent the CLI from hanging indefinitely on stalled or flaky connections (e.g. captive portals or misconfigured VPNs), an explicit timeout is set on all API requests: a connection timeout of 5 seconds and a read timeout of 30 seconds.

If you lose internet connectivity, a request times out, or GitHub is experiencing outages, breakfast will automatically fall back to the most recent cached results on disk, even if expired, and print an offline mode banner.

If you know you are offline or have weak connectivity, you can force breakfast to use the local cache immediately without making any network requests by passing `--offline`.

### `--mine-only` and `--needs-my-review` in offline mode

breakfast caches your GitHub login in `user.json` inside the cache directory after the first successful online run. In offline mode (either `--offline` or automatic fallback), it reads this cached login so `--mine-only` and `--needs-my-review` work correctly.

If you see the warning:

```text
⚠️  Offline mode: no cached login found — --mine-only / --needs-my-review skipped.
```

Run breakfast once without `--offline` while connected, then the cached login will be available for future offline runs.

If errors persist and no cached data exists:

- Check [GitHub Status](https://www.githubstatus.com/) for ongoing incidents
- Verify your token hasn't been revoked
- Check your [API rate limit](https://docs.github.com/en/rest/rate-limit): `curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/rate_limit`

## Slow performance

PR details are fetched in parallel (up to 8 concurrent requests), and results are cached to disk for 5 minutes by default. If output is slow on the first run:

- Use `--repo-filter` to narrow down the repos queried
- Use `--ignore-author` to reduce the number of PRs processed
- Owners with many repos will take longer on the initial GraphQL query

Subsequent runs within the TTL window will be near-instant (served from the local cache). To force a fresh fetch, use `--no-cache`. To tune the cache window, use `--cache-ttl` (e.g. `--cache-ttl 10m`).

## Terminal hyperlinks not working

The "Link" column uses OSC 8 terminal hyperlinks. If you see escape codes instead of clickable links, your terminal may not support them. Supported terminals include:

- iTerm2
- GNOME Terminal
- Windows Terminal
- Alacritty (v0.11+)
- WezTerm

Use `--json` output and extract the `url` field as an alternative.

## Table columns drift around `Checks` or `Mergeable?`

Some terminal and font combinations render the status emoji at uneven widths. If the `|` separators stop lining up, switch the status cells to ASCII:

```bash
breakfast -o my-org -r my-app --checks --status-style ascii
```

Or set it once in config:

```toml
status-style = "ascii"
```

## Debugging with the trace log

breakfast writes a trace log on every invocation to:

```text
~/.local/state/breakfast/breakfast.log
```

(or `$XDG_STATE_HOME/breakfast/breakfast.log` if `XDG_STATE_HOME` is set.)

The log is **overwritten on each run**, so it always reflects the most recent execution. It captures resolved options, cache hits/misses, API calls with timing, filter counts, and the final render. Use it to diagnose unexpected behaviour:

```bash
cat ~/.local/state/breakfast/breakfast.log
```

Example output:

```text
2026-03-23 08:00:01 INFO    startup org=acme repo_filter='' mine_only=False ...
2026-03-23 08:00:01 DEBUG   cache_miss layer=graphql path=~/.cache/breakfast/graphql_abc123.json reason=file_not_found
2026-03-23 08:00:02 DEBUG   api_call type=graphql status=200 elapsed_ms=812
2026-03-23 08:00:04 DEBUG   api_call type=rest url=https://api.github.com/repos/acme/foo/pulls/7 status=200 elapsed_ms=134
2026-03-23 08:00:05 INFO    filter_result before=42 after=38
2026-03-23 08:00:05 INFO    render format=table row_count=38
```

## "Owner not found" errors

breakfast uses the `repositoryOwner` GitHub GraphQL field, which resolves both
organizations and personal accounts. If you see an owner-not-found error:

- Double-check the owner login (organization name or personal username) passed with `-o`
- Verify your token has access to the account's repositories
- For organizations, you can verify with:

```bash
curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/orgs/YOUR_ORG
```

- For personal accounts:

```bash
curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/users/YOUR_USER
```

## Mergeable status shows "unknown" unexpectedly

GitHub computes PR mergeability **lazily** — it does not calculate whether a PR has conflicts until someone (or something) asks. Immediately after a push to a PR branch or its base branch, GitHub marks `mergeable` as `null` while it queues the computation. This typically resolves within a few seconds.

When `--filter-mergeable` is used, breakfast maps `mergeable: null` to `unknown`. This means:

- A PR may briefly appear as `unknown` right after a push, even if it is actually clean.
- Running breakfast again a few seconds later will show the correct `clean` or `conflict` status.

If you consistently see `unknown` for a PR that has been idle for a while, it may indicate a GitHub API issue. Try refreshing with `--refresh` to bypass the local cache and fetch fresh data.

## "Warning: Unknown config key '...' in config"

If you see a yellow warning on startup:

```text
⚠️  Unknown config key 'cheks' in config.toml — did you mean 'checks'?
```

This indicates that your `breakfast.toml` (or `config.toml`) contains a key that breakfast does not recognize. This is usually due to a typo or a deprecated/removed option.

- Double-check the option name against the default config template (which you can generate using `breakfast --init-config`).
- If you made a typo, correct the key name in your configuration file.
- If you have an outdated config file, you can run `breakfast --update-config` to append any missing options from the newest default template.
