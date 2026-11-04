@e2e @live
Feature: Listing pull requests from live GitHub
  Every scenario here queries the frozen fixture repo mrsixw/breakfast-fixtures
  over the real API. Its pull requests never change, so the counts below are
  exact. See docs/design/testing.md for the inventory.

  Scenario: The fixture repo still holds the inventory the suite assumes
    When I run `breakfast -o mrsixw:breakfast-fixtures --include-archived --fetch-state all --format json --no-colour`
    Then the exit code is 0
    And stdout is valid JSON
    And the JSON payload has 8 entries
    And the payload matches the recorded fixture inventory

  Scenario: The default view lists only open pull requests
    When I run `breakfast -o mrsixw:breakfast-fixtures --include-archived --format json --no-colour`
    Then the exit code is 0
    And stdout is valid JSON
    And the JSON payload has 6 entries

  Scenario: The table renders the open pull requests
    When I run `breakfast -o mrsixw:breakfast-fixtures --include-archived --no-colour`
    Then the exit code is 0
    And stdout contains "Open PR with no labels"
    And stdout contains "Draft PR awaiting work"

  # Issue #493: the approvals phase used to run unannounced on the live path,
  # so a slow run was indistinguishable from a hung one. Only the real binary
  # can prove the label lands on stderr and never pollutes the piped table.
  Scenario: The approvals phase announces itself on stderr, not stdout
    When I run `breakfast -o mrsixw:breakfast-fixtures --include-archived --approvals --no-cache --no-colour`
    Then the exit code is 0
    And stderr contains "Fetching approvals"
    And stdout contains "Open PR with no labels"
    And stdout does not contain "Fetching approvals"
    # Issue #496: that label used to open with a "\n", ending the PR detail
    # line without its "...Done" and leaving the phase looking unfinished.
    And every progress phase on stderr is closed

  Scenario: Every JSON entry carries the documented fields
    When I run `breakfast -o mrsixw:breakfast-fixtures --include-archived --format json --no-colour`
    Then the exit code is 0
    And stdout is valid JSON
    And every entry has the fields "repo,title,author,url,state"

  # A label column is only worth having if it links somewhere real. The anchor
  # is emitted whether or not stdout is a terminal, so this layer can prove the
  # OSC 8 payload and its URL actually reach the stream from the built binary.
  Scenario: The labels column links each label to a filtered PR search
    When I run `breakfast -o mrsixw:breakfast-fixtures --include-archived --show-labels --no-colour`
    Then the exit code is 0
    And stdout contains "bug"
    And stdout contains "pulls?q=is%3Apr+is%3Aopen+label%3A%22bug%22"
    And stdout contains "pulls?q=is%3Apr+is%3Aopen+label%3A%22enhancement%22"

  Scenario Outline: Filters narrow the result set
    When I run `breakfast -o mrsixw:breakfast-fixtures --include-archived <flags> --format json --no-colour`
    Then the exit code is 0
    And stdout is valid JSON
    And the JSON payload has <count> entries

    Examples:
      | flags                              | count |
      | --no-drafts                        | 4     |
      | --drafts-only                      | 2     |
      | --label bug                        | 2     |
      | --exclude-label bug                | 4     |
      | --label 'b*'                       | 2     |
      | --exclude-label 'w*'               | 5     |
      | --label bug --label wip            | 2     |
      | --label bug --label wip --label-match all | 1 |
      | --label bug --label enhancement --label-match all | 0 |
      | --filter-author mrsixw             | 6     |
      | --filter-author octocat            | 0     |
      | --ignore-author mrsixw             | 0     |
      | --limit 2                          | 2     |

  # The fixture repo is archived, so every other scenario opts in with
  # --include-archived. Without it the repo's PRs are skipped by default.
  Scenario: Archived repositories are skipped by default
    When I run `breakfast -o mrsixw:breakfast-fixtures --format json --no-colour`
    Then the exit code is 0
    And stdout is valid JSON
    And the JSON payload has 0 entries

  Scenario: An unknown owner fails cleanly
    When I run `breakfast -o breakfast-fixtures-does-not-exist --no-colour`
    Then the exit code is 1
    And stderr contains "not found"
