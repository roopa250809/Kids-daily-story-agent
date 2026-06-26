# Week 4 Prompt / Router Fix

## Summary of Change

The prompt in `src/story_agent.py::_generate_story_payload` now computes an age-specific word budget, lists every required child interest, injects profile and global avoided topics, requires explicit selected-theme wording, and asks for the lesson in `parent_note`.

## Failure Category Targeted

The fix targets lesson / moral alignment, personalization / missing required interest, safety / forbidden content, and reading-level length control.

## Router Note

No graph router change was made yet. The next recommended router/control-flow fix is a validation-driven repair branch: when `validate_story_node` reports missing interests, route back to `revise_story_node` with an explicit checklist before parent approval.

## Regression Result

The previously passing example `happy_age6_space_soccer_kindness` stayed passing. Three failed examples were re-run and still failed, mainly because the model omitted one required interest.
