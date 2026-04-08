- be concise, no filler, straight to the point, use less words
- when merging pull requests, always use rebase and merge strategy
- create agent teams to run tasks in parallel whenever possible
  - always create devil's advocate agent for peer review

# Tech Stack

- use the latest stable version for all tools and frameworks
- do not write tests until you are told to do so
- python related
  - use `uv` instead of `pip`
  - prefer python over bash scripts for local running tasks
  - use the following python with inline `uv` pattern if scripting is needed:

```python
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "requests",
#     "rich",
# ]
# ///
```

- javascript / web development
  - prefer typescript over javascript
  - use `vite` as dev server and bundler
  - use static-first approach, only use backend when strictly necessary

- use `Cloudflare Pages` with `wrangler` cli for static site deployment related tasks
- use more efficient commands as follow

| use  | avoid |
| ---- | ----- |
| fd   | find  |
| rg   | grep  |
| pnpm | npm   |
| pnpx | npx   |
| uv   | pip   |
