# HoloSplat project page

Source of <https://heaticy.github.io/HoloSplat/>, served by GitHub Pages from the `gh-pages` branch of
`Heaticy/HoloSplat`; `main` is reserved for the code release. In RealTime-4DGS this repository is the
`web/` submodule.

- `index.html`, `static/css/index.css`, `static/js/index.js`: the page. Numbers and figure captions come from the paper.
- `tools/update_assets.py`: rebuilds `static/images/*.jpg` and `static/videos/*.mp4`. Stages (`--stage`, default all):
  `figures` crops paper figures from `paper/arxiv/HoloSplat_arxiv.pdf` (run `make -C paper arxiv` first);
  `video` and `clips` take the narrated video `pv/final/out/holosplat_pv_web.mp4` and cut the looping clips at its
  white fades, matching each clip to the segment that looks like its current poster (the script stops if no segment
  clearly matches); `orbits` encodes the live 0013_08 session renders; `compare` takes the DNA-Rendering
  before/after-calibration clips listed in `NSC_SLIDES` from the newest `pv/runs/*_SGT_NSC_Slider_Candidates` run
  (made by `pv/offline/render_nsc_slider.py`); `hero` encodes the newest `pv/runs/*_SGT_Showcase_0678_02`
  run (made by `pv/offline/render_showcase.py`); `teaser` copies the labelled web cut of the newest
  `pv/runs/*_SGT_TeaserLive_0678_02` run (made by `pv/teaser_live/`). Run it from the RealTime-4DGS root with
  `methods/pointsplat/.venv/bin/python web/tools/update_assets.py`, then check the images and clips before committing.

When the arXiv ID is out, replace the `is-soon` Paper button in `index.html` with a link to the abstract page
and set `journal = {arXiv preprint arXiv:<id>}` in the BibTeX block.
