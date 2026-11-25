# Evidence report

Open `index.html` in a browser after cloning, or serve the repository root with a local static server. Links point to files within the repository, so keep the full tree together. No scripts, remote assets, tracking or runtime network requests are included in the report.

Regenerate with `uv run python study/report.py`. Check drift with `uv run python study/report.py --check`. Source inputs are the committed Olist aggregate JSON and separate synthetic cancellation JSON. Recompute synthetic results with `uv run python study/cancellation.py`; full Olist reproduction is documented under `study/`.

Olist-derived values, chart and cohort table in this report are CC BY-NC-SA 4.0, with attribution, changes and source links in the page. Code and the separately labeled synthetic fixtures are MIT. The report does not license commercial reuse of Olist-derived artifacts.

The local report was pixel-inspected at 320, 390 and 1280 CSS-pixel widths on 24 November 2026. The first narrow render exposed overflow and an awkward table heading wrap; both were fixed and re-rendered. A local inspection is not a deployed-site check. Hosting and actual hosted CI still require verification before release.

After local source recovery on 25 November 2026, the study was reproduced twice with identical aggregates and the regenerated report was inspected again at all three widths. The study snapshot label remains 24 November because the pinned historical input population and results did not change.

## Hosted report

The [live report](https://zaaby.github.io/join-proof-lab/report/index.html) is hosted with GitHub Pages from this repository. On 25 November 2026, its deployed pixels were inspected at 320, 390 and 1280 CSS-pixel widths, with no horizontal overflow. Relative Markdown document links were checked for the intended content, and the manifest and aggregate JSON downloads matched the committed bytes. Markdown links may display as source text rather than a themed page. The engine's hosted validation passed on Python 3.10 and 3.12; check the Actions page for the result attached to a particular revision.
