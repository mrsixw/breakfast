@e2e @live
Feature: Listing pull requests from live GitHub
  Every scenario here queries the frozen fixture repo mrsixw/breakfast-fixtures
  over the real API. Its pull requests never change, so the counts below are
  exact. See docs/design/testing.md for the inventory.

  Scenario: The fixture repo still holds the inventory the suite assumes
    When I run `breakfast -o mrsixw:breakfast-fixtures --fetch-state all --format json --no-colour`
    Then the exit code is 0
    And stdout is valid JSON
    And the JSON payload has 8 entries
    And the payload matches the recorded fixture inventory

  Scenario: The default view lists only open pull requests
    When I run `breakfast -o mrsixw:breakfast-fixtures --format json --no-colour`
    Then the exit code is 0
    And stdout is valid JSON
    And the JSON payload has 6 entries

  Scenario: The table renders the open pull requests
    When I run `breakfast -o mrsixw:breakfast-fixtures --no-colour`
    Then the exit code is 0
    And stdout contains "Open PR with no labels"
    And stdout contains "Draft PR awaiting work"

  Scenario: Every JSON entry carries the documented fields
    When I run `breakfast -o mrsixw:breakfast-fixtures --format json --no-colour`
    Then the exit code is 0
    And stdout is valid JSON
    And every entry has the fields "repo,title,author,url,state"

  Scenario Outline: Filters narrow the result set
    When I run `breakfast -o mrsixw:breakfast-fixtures <flags> --format json --no-colour`
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

  Scenario: An unknown owner fails cleanly
    When I run `breakfast -o breakfast-fixtures-does-not-exist --no-colour`
    Then the exit code is 1
    And stderr contains "not found"
