@e2e
Feature: breakfast CLI contract
  The built zipapp must honour its documented exit codes and stream discipline
  without any network access. These scenarios need no token, so they run on
  every pull request including those from forks.

  Scenario: Version matches the VERSION file
    When I run `breakfast --version`
    Then the exit code is 0
    And stdout reports the version from the VERSION file

  Scenario: Help lists the headline options
    When I run `breakfast --help`
    Then the exit code is 0
    And stdout contains "--owner"
    And stdout contains "--format"
    And stdout contains "--offline"

  Scenario: Missing owner is a usage error
    Given no GitHub token is set
    When I run `breakfast --no-colour`
    Then the exit code is 1
    And stderr contains "Owner must be provided"
    And stdout is empty

  Scenario: Missing token is a usage error
    Given no GitHub token is set
    When I run `breakfast --owner acme --no-colour`
    Then the exit code is 1
    And stderr contains "GH_TOKEN or GITHUB_TOKEN not set"
    And stdout is empty

  Scenario: Draft flags are mutually exclusive
    Given the GitHub token is "not-a-real-token"
    When I run `breakfast --owner acme --no-drafts --drafts-only --no-colour`
    Then the exit code is 1
    And stderr contains "mutually exclusive"
    And stdout is empty

  Scenario: An invalid search pattern is rejected
    Given the GitHub token is "not-a-real-token"
    When I run `breakfast --owner acme --search ( --no-colour`
    Then the exit code is 1
    And stderr contains "not valid regex"
    And stdout is empty

  Scenario: Refresh requires the cache to be enabled
    Given the GitHub token is "not-a-real-token"
    When I run `breakfast --owner acme --refresh --no-colour`
    Then the exit code is 1
    And stderr contains "requires the cache to be enabled"

  Scenario: Offline mode fails before any network call
    Given the GitHub token is "not-a-real-token"
    When I run `breakfast --owner acme --offline --no-colour`
    Then the exit code is 1
    And stderr contains "no cached data was found"
    And stdout is empty

  Scenario Outline: Completions are generated for <shell> without a token
    Given no GitHub token is set
    When I run `breakfast completions <shell>`
    Then the exit code is 0
    And stdout contains "_BREAKFAST_COMPLETE"

    Examples:
      | shell |
      | bash  |
      | zsh   |
      | fish  |

  # The user's shell evaluates stdout, so a notice landing there is a startup
  # syntax error rather than a cosmetic wart. Only genuinely separate streams
  # can prove this, which is why it belongs at this layer.
  Scenario: The deprecated --completion flag keeps stdout evaluable
    Given no GitHub token is set
    When I run `breakfast --completion bash`
    Then the exit code is 0
    And stdout contains "_BREAKFAST_COMPLETE"
    And stdout does not contain "deprecated"
    And stderr contains "deprecated"

  Scenario: Generating a config writes a real file
    Given no GitHub token is set
    When I run `breakfast --init-config`
    Then the exit code is 0
    And the config file exists in the sandbox
    And running it again reports that the config already exists
