---
title: hued
tagline: Declarative per-directory terminal colors
tags: [cli, shell, python]
featured: true
order: 40
---

A shell hook and CLI that recolors your terminal based on which directory you are in, using OSC 10
and 11. Drop a `.hued` file in a project and every shell that enters it picks up the color — so the
window you are about to type a destructive command into looks different from the one you are not.

Deliberately platform-agnostic; anything OS-specific lives under `contrib/<os>/`. Installs from the
`orochi235/hued` Homebrew tap.
