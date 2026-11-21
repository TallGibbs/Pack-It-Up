---
name: gemini-outputs
description: Use before making or changing anything for the demo or presentation that is not the app itself (slides, the demo video's narration or cards, a poster, a one-pager, generated images, copy for the submission). In Pack It Up those outputs are made by a Gemini model through backend/llm, not written or designed by the coding agent.
---

# Demo and presentation outputs are made by Gemini

Pack It Up is a Gemini hackathon entry, so what judges and viewers see is made by Gemini. The coding agent builds the pipeline that asks Gemini; it does not write the finished copy or the design itself. The rule is in `AGENTS.md`, "Demo and presentation outputs are made by Gemini".

## Steps

1. **Check whether a builder already exists** (table in `AGENTS.md`): the slide deck is `python -m scripts.slides.build`, the video is `python -m scripts.video.build`. To change an existing output, change its brief or prompt and run its builder again. Never hand-edit `frontend/slides/index.html` or the rendered video.
2. **Load Google's skills before touching model code:** `gemini-skills:gemini-api-dev` (models, TTS, image and video), plus `gemini-api-cli` or `gemini-omni-flash-api` if you need them. Where they disagree with `backend/llm/models.toml` and `FAILURES.md`, the repo wins.
3. **Write a brief of facts** next to the builder (see `scripts/slides/brief.md`): only facts from the repo, numbers only from `eval/RESULTS.md` with the caveats in its "What these tables do not show" section, the order of the content, and a "never on a slide" list (features not built, invented numbers, names, faces). No finished sentences for the output; Gemini writes those.
4. **Write the prompt** for format and constraints (see `scripts/slides/prompt.md`): size, structure, the images Gemini may use by path, readability, no external resources, plain wording.
5. **Call Gemini through `backend/llm/` only:** add or reuse a job in `models.toml` (text and HTML: `gemini-4-carbon` or `gemini-4-neon`; speech: `gemini-3.8-flash-tts`; images: `gemini-nano-banana-2.1`; video: `gemini-omni-1.2-flash`) and call `for_job("<job>")`. No other file imports a model SDK (`tests/test_planner_agents.py` checks this).
6. **Check the output in the builder, not by eye only:** every number in the output appears in the brief; only the allowed images and links; the required structure. On failure, send the errors back to the model once, then stop.
7. **Real app footage stays real:** screenshots and recordings are captures of the running app (`scripts/video/shoot.mjs` drives headless Chrome). Never ask a model to draw the app. Label generated imagery as generated where it appears.
8. **Say which model made it** in the output (header comment, end-card line, or description), and add a row to the table in `AGENTS.md` for any new builder.
9. **Media never goes in git:** screenshots, audio, video and renders go to git-ignored folders (`.cache/`, `frontend/slides/shots/`).
10. **Look before you ship:** render the output (PNGs, PDF, contact sheet) and look at it for wrong numbers, faces, and names other than the team's first names. Show it to Chris before it goes out.
