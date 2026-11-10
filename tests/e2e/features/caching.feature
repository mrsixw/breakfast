@e2e @live
Feature: Caching across separate processes
  The cache is written by one process and read by the next, which is precisely
  what an in-process test cannot exercise.

  Scenario: A warm cache serves an offline run identically
    Given the cache directory is empty
    When I run `breakfast -o mrsixw:breakfast-fixtures --include-archived --cache --format json --no-colour`
    Then the exit code is 0
    And the cache directory holds a "v2/prs_*.json" file
    And the cache directory holds a "v2/graphql_*.json" file
    And the cache directory holds a "v2/repos_*.json" file
    And a second offline run prints byte-identical output
    And an offline run with another GitHub token finds no cached data

  Scenario: Debug summary reports real API activity
    Given the cache directory is empty
    When I run `breakfast -o mrsixw:breakfast-fixtures --include-archived --api-stats --no-colour`
    Then the exit code is 0
    And stderr contains "Debug summary"
    And stderr reports at least 6 processed pull requests
