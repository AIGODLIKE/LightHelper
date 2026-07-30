# Project Agent Instructions

Read `PROJECT_CONTEXT.md` before reading or searching source code. Use it to
select the smallest relevant scope, then verify important claims against the
current source files because the summary does not override source code.

Refresh `PROJECT_CONTEXT.md` whenever code, structure, dependencies, build
behavior, verification commands, durable constraints, or known risks change.
Before committing, refresh the summary and include it when changed. After a
successful commit, compare it with `HEAD` and report whether it is current.

This is a Blender Extension project. Keep `AGENTS.md` and
`PROJECT_CONTEXT.md` out of release archives, build with Blender's Extension
CLI, and inspect the produced archive before release.
