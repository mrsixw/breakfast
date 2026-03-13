# Troubleshooting

## "GITHUB_TOKEN not set in environment - exiting..."

breakfast requires a GitHub personal access token. Set it in your environment:

```bash
export GITHUB_TOKEN="ghp_your_token_here"
```

The token needs `repo` scope to access pull request data. Generate one at [github.com/settings/tokens](https://github.com/settings/tokens).

## No PRs displayed

- Verify the organization name is correct (`-o`)
- Check that the repo filter (`-r`) matches at least one repository name (it's a substring match)
- If using `--mine-only`, ensure the token belongs to the user whose PRs you want to see
- If using `--ignore-author`, check you haven't accidentally filtered out the authors you want

## API errors (502, 503, 504)

breakfast automatically retries REST API requests on transient server errors with exponential backoff (up to 3 retries). If errors persist:

- Check [GitHub Status](https://www.githubstatus.com/) for ongoing incidents
- Verify your token hasn't been revoked
- Check your [API rate limit](https://docs.github.com/en/rest/rate-limit): `curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/rate_limit`

## Slow performance

PR details are fetched in parallel (up to 8 concurrent requests). If output is slow:

- Use `--repo-filter` to narrow down the repos queried
- Use `--ignore-author` to reduce the number of PRs processed
- Large organizations with many repos will take longer on the initial GraphQL query

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

## "GraphQL request failed" errors

This typically means the organization name is incorrect or your token doesn't have access to the organization. Verify:

```bash
curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/orgs/YOUR_ORG
```
