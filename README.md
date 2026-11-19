# HoloSplat project page

Source of <https://heaticy.github.io/HoloSplat/>, served by GitHub Pages from the `gh-pages` branch of
`Heaticy/HoloSplat`; `main` is reserved for the code release. In RealTime-4DGS this repository is the
`web/` submodule.

- `index.html`, `static/css/index.css`, `static/js/index.js`: the page. Numbers and figure captions come from the paper.
- `tools/update_assets.py`: rebuilds `static/images/*.jpg` from `paper/arxiv/HoloSplat_arxiv.pdf` (run
  `make -C paper arxiv` first) and `static/videos/*.mp4` from the supplementary-video outputs under `pv/`.
  Run it from the RealTime-4DGS root with `methods/pointsplat/.venv/bin/python web/tools/update_assets.py`,
  then check the images before committing.

When the arXiv ID is out, replace the `is-soon` Paper button in `index.html` with a link to the abstract page
and set `journal = {arXiv preprint arXiv:<id>}` in the BibTeX block.
