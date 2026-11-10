# Example plugins

`example-lab/` is a tiny, tracked lab plugin that shows how a lab is packaged. It imports
only the public core API. See `docs/plugins.md` (sections 5 and 11) and the README
"Make a plugin" walkthrough.

Run it from the repository root (the variable names the directory that contains
`example-lab/`):

```
cd python
SADI_PLUGIN_PATH=../examples/plugins uv run --frozen sadi-plugins list
```

`example-lab` appears as `local-dir  enabled`. Copy the directory to `plugins/` (gitignored)
and rename the id to start your own.
