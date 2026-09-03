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

## Writing style

These rules apply to documentation, commit messages, pull request
descriptions, and code comments. AI-assisted drafts share a recognisable
set of tics; each rule below names one and gives the fix.

- Write prose. Reserve a list for items that are genuinely parallel, and a
  table for data that is genuinely tabular.
- Cut filler: `in order to achieve this` becomes `to achieve this`,
  `it is important to note that the data shows` becomes `the data shows`,
  `has the ability to` becomes `can`.
- Do not inflate. No `plays a crucial role`, `is a testament to`,
  `marks a pivotal moment`, `underscores the importance of`.
- Avoid the words `delve`, `crucial`, `key` (adjective), `leverage`,
  `landscape`, `seamless`, `robust`, `powerful`, `showcase`, `tapestry`.
- Name the source of a claim, or drop the claim. Never `experts agree`,
  never `studies show`.
- Do not restate a heading in the sentence below it. A closing paragraph
  earns its place by adding something - what the reader can now do, what
  the design leaves out, where to go next - or it is cut.
- Vary sentence length. A run of sentences of the same length reads as
  machine output.
- Prefer the active voice, and name the actor. `is` and `has` are good
  verbs; do not work around them.
- Punctuate with a spaced hyphen, a comma, or a full stop. The
  documentation uses no em dashes.
- Bold defines a term. It does not emphasise. No emojis.

Apply these as defaults, not as a filter: a listed word is right when it is
the accurate one, and a list beats prose when the items really are a list.

### Voice

The voice of this documentation comes from the workshop material in
[gouarin/dev_env_and_automatisation](https://github.com/gouarin/dev_env_and_automatisation).
Those pages are French and teach a course; what transfers is the posture,
not the vocabulary.

- Address the reader as `you` for what they do, and use `we` for the
  choices nunatak made. Never `I`: the workshop uses `je` not once in
  fifteen thousand words.
- Motivate before explaining. Show the situation that hurts - the loop at
  3% of peak, the counter that lies - then the thing that answers it.
- Frame a heading as the question the reader arrived with when the section
  answers one: `What does this number mean?` beats `Number semantics`.
- Name a tool's cost in the same breath as its benefit. Nix and Guix
  reproduce an environment to the bit, run only on linux, and have a steep
  learning curve. Both halves belong in the same paragraph.
- Link every tool, standard, and external resource on first mention.
- Keep sentences short: the workshop's median sentence is twelve words.
  Long sentences are allowed, they are just rare.
- Say when a step is cheap. `You only need to add a LICENSE file` tells the
  reader the cost before they commit to it.
- Put a warning, a prerequisite, or a side remark in a typed admonition
  rather than in the flow of the paragraph.
