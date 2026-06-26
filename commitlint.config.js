// commitlint.config.js — Enforce conventional commits
// Docs: https://commitlint.js.org/reference/rules-configuration.html

module.exports = {
  extends: ['@commitlint/config-conventional'],
  rules: {
    // Type must be one of the following
    'type-enum': [2, 'always', [
      'feat',     // New feature
      'fix',      // Bug fix
      'docs',     // Documentation only
      'style',    // Code style (formatting, whitespace)
      'refactor', // Code refactoring (no feature/fix)
      'perf',     // Performance improvement
      'test',     // Adding/updating tests
      'ci',       // CI/CD changes
      'chore',    // Maintenance tasks
      'revert',   // Revert a commit
      'build',    // Build system or dependencies
    ]],
    // Subject should not be empty
    'subject-empty': [2, 'never'],
    // Type should not be empty
    'type-empty': [2, 'never'],
    // Max header length
    'header-max-length': [2, 'always', 100],
  },
};
