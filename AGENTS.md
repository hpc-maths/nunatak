# Engineering Guidelines

These rules apply to every change in this repository: bug fixes, new features,
refactoring, and documentation. They exist to keep the codebase simple,
readable, and maintainable over the long term.

## Design principles

- Favor quality, simplicity, robustness, and long-term maintainability over
  development speed.
- Keep implementations clean and concise. The best code is the code you do
  not have to write.
- Don't repeat yourself: factor shared logic instead of duplicating it.
- Divide and conquer: break large problems into small, independent,
  composable pieces.

## Code and reviews

- A pull request must be small enough for a human to review comfortably.
  If it is not, split it.
- A pull request addresses a single concern. Do not mix refactoring, bug
  fixes, and features in the same change.
- Comments explain constraints that the code cannot express by itself.
  Avoid noise:
  - never mention the number of tests that pass;
  - never add a comment saying that a line fixes a previous implementation.
    Git history already records that.

## Commits and pull requests

- Code comments, commit messages, and pull request descriptions are written
  in English.
- Commit and pull request descriptions are concise: state what changed and
  why, nothing more.
- Never add your name, or an agent name, to commits, documentation, or pull
  request descriptions.

## Documentation

Every new feature or behavior change must be documented at three levels:

1. **User guide**: how to use the feature, from the user's point of view.
2. **Philosophy and reference**: why we chose this design and how it fits
   into the big picture.
3. **API**: each function, its parameters, and its return values.

Documentation must earn its place: remove anything that does not help the
reader.
