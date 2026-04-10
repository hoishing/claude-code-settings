# General Preferences

- be concise, no filler, straight to the point, use less words
- when merging pull requests, always use rebase and merge strategy
- create agent teams to run tasks in parallel whenever possible
  - create devil's advocate, prefer /codex:adversarial-review skills for peer review

# Tech Stack

- use the latest stable version for all tools and frameworks
- do not write tests until you are told to do so

## Python

- use `uv` instead of `pip`
- use python script with inline `uv` pattern instead of bash scripts for local tools and tasks, eg.

```python
# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "whatever-dependencies", ...
# ]
# ///

# python scripts ...
```

## Web Development

- frontend-first, use backend unless strictly necessary
- use `Cloudflare Pages` with `wrangler` cli to deploy static site

| prefer                           | avoid                      |
| -------------------------------- | -------------------------- |
| typescript                       | vanilla javascript         |
| pnpm                             | npm                        |
| pnpx                             | npx                        |
| react SPA or Astro SSG with Vite | full stack app with nextjs |
