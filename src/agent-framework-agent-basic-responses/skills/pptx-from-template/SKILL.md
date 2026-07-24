---
name: pptx-generation
description: >
  Use this skill whenever the user wants to generate, build, or fill in a
  PowerPoint (.pptx) deck. Works WITH an uploaded template (inherits its theme,
  fonts, colors, layouts) OR WITHOUT one (creates an original design from the
  user's style instructions, or a sensible default when none are given).
---

# PPTX Generation Skill

Use this skill when the user wants to build a PowerPoint (.pptx) deck. It has two
modes; pick based on whether a usable template is available. **Do not demand a
template just because this skill exists.**

## Inputs
- template_path: OPTIONAL path to an existing .pptx/.potx template. In the hosted
  Code Interpreter flow an uploaded template is typically saved under `/mnt/data/`;
  inspect the container files before generating if the user mentions a template.
- style_instructions: OPTIONAL description of audience, mood, density, typography,
  color palette, branding, or visual references (e.g. "executive", "minimalist",
  "corporate navy + teal", "technical, dense").
- slides[]: ordered items with layout, title, bullets (<=5, short), optional notes, optional image.
- output_path: where to write the finished .pptx.

## Procedure
1. Decide the mode:
   - **Template mode** — a valid .pptx/.potx is available (uploaded or path given).
   - **No-template mode** — no template; build an original design.
2. Template mode:
   a. Inspect the template first: enumerate its slide layouts + theme (fonts, palette, placeholders). Inherit styling; never hard-code it.
   b. Map each requested slide to a template layout by name; if missing, use the closest match and note the substitution.
   c. Fill the layout placeholders (title/body/content) so theme styling is preserved. Do not edit the master directly.
3. No-template mode:
   a. Build the deck with `python-pptx` using a consistent original theme.
   b. Translate style_instructions into deliberate choices for page size, background, accent colors, typography, spacing, hierarchy, and layout variety. If no style is given, choose a restrained, readable business look.
   c. Create small reusable layout helpers so styling stays consistent across slides.
4. Respect limits: <=5 bullets/slide, ~8 words each; split long content across slides; put nuance in speaker notes.
5. Write to output_path and report: which mode was used, the key style decisions, and the layout used per slide.

## Guardrails
- Template mode: preserve the template fonts/colors/logo (brand fidelity is the point).
- No-template mode: never claim to have inherited branding — state clearly that the deck uses an ORIGINAL design based on the user's instructions.
- Do not invent images; leave a labeled placeholder if one is missing.
- Only stop to ask for a template when the user EXPLICITLY requires exact template/brand fidelity and no readable template is available. Otherwise proceed in no-template mode.
