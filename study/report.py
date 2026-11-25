"""Generate the repository-native, static study report from committed evidence."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def money(units):
    return f"{units / 100:,.2f}"


def render():
    raw = (HERE / "results/olist.json").read_bytes()
    study = json.loads(raw)
    full, *months = study["cohorts"]
    synthetic = json.loads((HERE / "results/cancellation.json").read_text())["cases"]
    payment = full["measures"][1]
    failures = sum(not row["naive_gate_passed"] for row in months)
    cards = []
    for title, units in [
        ("Original payment sum", payment["source_units"]),
        ("Naive joined sum", payment["output_units"]),
        ("Repeated payment exposure", payment["absolute_exposure_units"]),
    ]:
        cards.append(
            f'<section class="metric"><span>{title}</span><strong>{money(units)}</strong><small>Dataset monetary units</small></section>'
        )
    bars = []
    for title, value in [
        ("Source", payment["source_units"]),
        ("Naive join", payment["output_units"]),
        ("Preaggregated", full["preaggregated_sql"]["payments_units"]),
    ]:
        width = 100 * value / payment["output_units"]
        bars.append(
            f'<div class="bar-row"><div class="bar-label"><span>{title}</span><b>{money(value)}</b></div><div class="track"><div class="bar" style="width:{width:.4f}%"></div></div></div>'
        )
    rows = []
    for row in months:
        measure = row["measures"][1]
        delta = measure["delta_units"]
        source = measure["source_units"]
        percent = f"{100 * delta / source:.2f}%" if source else "No payments"
        rows.append(
            f'<tr><th scope="row">{html.escape(row["cohort"])}</th><td>{row["source_rows"]["orders"]:,}</td><td>{percent}</td><td>{"Pass" if row["naive_gate_passed"] else "Fail"}</td></tr>'
        )
    cases = []
    for case in synthetic:
        cases.append(
            f'<section class="case"><h3>{"Equal positive amounts" if case["fixture"] == "cancellation" else "Signed amounts cancel"}</h3><dl><div><dt>Source / joined rows</dt><dd>{case["source_rows"]} / {case["output_rows"]}</dd></div><div><dt>Source / joined total</dt><dd>{money(case["source_units"])} / {money(case["output_units"])}</dd></div><div><dt>Gross exposure</dt><dd>{money(case["exposure_units"])}</dd></div><div><dt>Contribution gate</dt><dd>Fail</dd></div></dl><p>{"A contributes twice, B disappears." if case["fixture"] == "cancellation" else "A and B contribute twice; C and D disappear. Positive and negative errors offset."}</p></section>'
        )
    template = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Join Proof Lab | Evidence report</title><style>
:root{--ink:#251f21;--secondary:#585254;--teal:#73a89a;--rule:#eae9ea;--sand:#f4efec}*{box-sizing:border-box;overflow-wrap:anywhere}body{margin:0;background:white;color:var(--ink);font:16px/1.6 Arial,Helvetica,sans-serif}main{max-width:1020px;margin:auto;padding:44px 36px}h1,h2{font-family:Georgia,serif;font-weight:400;letter-spacing:-.025em;line-height:1.15}h1{font-size:48px;max-width:760px;margin:14px 0 20px}h2{font-size:30px;margin:0 0 18px}h3{font-size:18px;line-height:1.4;margin:0 0 14px}p{margin:0 0 18px}.eyebrow,small{color:var(--secondary);font-size:13px}.eyebrow{letter-spacing:.08em;text-transform:uppercase}.intro{max-width:740px;font-size:19px}.section{padding:34px 0;border-top:1px solid var(--rule);margin-top:30px}.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:30px 0}.metric{border:1px solid var(--rule);border-radius:8px;padding:18px}.metric span,.metric strong,.metric small{display:block}.metric strong{font-size:25px;letter-spacing:-.03em;font-weight:600;margin:10px 0;color:var(--ink)}.callout{background:var(--sand);padding:18px 20px;border-radius:8px;margin:20px 0}.bar-row{margin:22px 0}.bar-label{display:flex;justify-content:space-between;gap:16px;margin-bottom:8px}.bar-label b{font-weight:600}.track{height:20px;background:#f7f7f7;border-radius:3px;overflow:hidden}.bar{height:100%;background:var(--teal)}.caption{font-size:14px;color:var(--secondary)}.cases{display:grid;grid-template-columns:1fr 1fr;gap:24px}.case{border:1px solid var(--rule);border-radius:8px;padding:20px}dl{margin:0 0 16px}dl div{display:flex;justify-content:space-between;gap:14px;padding:9px 0;border-bottom:1px solid var(--rule)}dt{color:var(--secondary)}dd{margin:0;font-weight:600;text-align:right}a{color:inherit;text-underline-offset:3px;overflow-wrap:anywhere}li{margin-bottom:12px}table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:right;border-bottom:1px solid var(--rule);padding:10px 8px}th:first-child{text-align:left}thead{color:var(--secondary)}th,td{overflow-wrap:normal}th:nth-child(2),td:nth-child(2){white-space:nowrap}tbody th{font-weight:400}.evidence{overflow-wrap:anywhere;font-family:monospace;font-size:12px}footer{border-top:1px solid var(--rule);padding-top:20px;margin-top:30px;color:var(--secondary);font-size:13px}@media(max-width:600px){main{padding:26px 22px}h1{font-size:34px}h2{font-size:26px}.intro{font-size:17px}.metrics,.cases{grid-template-columns:1fr}.metrics{gap:12px}.metric strong{font-size:28px}.bar-label{flex-direction:column;gap:0}.section{padding-top:28px}.case{padding:16px}dl div{flex-direction:column;gap:2px}dd{text-align:left}th,td{padding:10px 4px;font-size:12px}}
</style></head><body><main><header><div class="eyebrow">Join Proof Lab · Reproducible ETL study</div><h1>A correct-looking total can still count the wrong facts.</h1><p class="intro">Exact contribution checks for a narrow star-join contract. The real-data study shows fanout; separate controlled examples show why totals alone cannot establish conservation.</p><p class="caption">Study snapshot: 24 November 2026 · Historical Olist data, not current trading activity.</p></header>
<div class="metrics">@CARDS@</div>
<div class="callout">These are deliberately constructed analytical queries. They are not claims about an Olist production dashboard, and multiple child records are not automatically bad data.</div>
<section class="section"><h2>One join, three views of the same payments</h2><p>The raw four-table left join yields <b>@NAIVE_ROWS@ rows</b> from @ORDERS@ orders. Grouping each child relation by order before joining preserves the selected order population and original payment sum.</p>@BARS@<p class="caption">Common zero baseline; full population, dataset monetary units. Additive sums use exact integer minor units. The bars are not a performance benchmark.</p><p><code>SUM(DISTINCT payment_value)</code> gives <b>@DISTINCT@</b> on the raw join, also wrong. Equal-valued payments can be separate legitimate facts.</p></section>
<section class="section"><h2>What the monthly checks actually establish</h2><p>The naive plan fails @FAILURES@ of @MONTHS@ nonempty purchase-month populations. Explicit preaggregation passes all @MONTHS@. Independently executed DuckDB joins match the audit predictions for all 26 populations and both plans: <b>52 plan comparisons</b>.</p><div class="callout">In this Olist study, row-count and payment-total checks catch those same @FAILURES@ months. There is no extra real-data detection claim. Purchase-month cohorts include their orders' child rows, not child event months; monthly counts reconstruct the full population.</div><table><thead><tr><th>Purchase month</th><th>Orders</th><th>Payment inflation</th><th>Naive gate</th></tr></thead><tbody>@ROWS@</tbody></table><p class="caption">Inflation = (joined payment sum − source payment sum) / source payment sum. Explicit preaggregation passes every listed cohort. The three passing sparse cohorts are not excluded.</p></section>
<section class="section"><div class="eyebrow">Controlled examples · Synthetic, MIT</div><h2>Both row count and total pass. Contributions fail.</h2><p>These fixtures are kept separate from Olist. Each is checked against executed SQL and per-order contribution counts.</p><div class="cases">@CASES@</div><p class="caption">Gross exposure sums absolute value × change in contribution count. Signed errors can cancel; exposure cannot. Even a repeated non-null zero is structurally unsafe when conservation is required.</p></section>
<section class="section"><h2>Evidence, not a universal certificate</h2><ul><li>Supported: declared root-key star equijoins, exact text keys, mixed left/inner joins, explicit null and decimal rules.</li><li>Not supported: arbitrary SQL, filters, key coercion, cyclic/range/chained-child joins or automatic repairs. A passing contract does not prove that source values are true or that keys mean the same entity.</li><li>Run IDs bind versions, contract, exact input fingerprints and witness policy. Attempts have separate real timestamps. Local hashes detect inconsistent evidence; they are not signatures or tamper-proof records.</li><li>Files and grouping state are held in memory. No warehouse-scale speed or memory claim is made. Preaggregation is an explicit user-selected plan, not an inferred business rule.</li></ul><p>Read the <a href="../README.md">project README</a>, <a href="../docs/method.md">method</a>, <a href="../docs/evidence.md">ledger and recovery limits</a>, <a href="../study/README.md">reproduction steps</a> and <a href="../docs/prior-art.md">prior art</a>.</p></section>
<section class="section"><h2>Sources and licensing</h2><p>Olist's <a href="https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce/">Brazilian E-Commerce Public Dataset</a>, from its <a href="https://github.com/olist/work-at-olist-data/tree/master/datasets">publisher-owned repository</a>. Data and derived Olist figures/charts: <a href="https://creativecommons.org/licenses/by-nc-sa/4.0/">CC BY-NC-SA 4.0</a>. Changes: selected columns, cohort partitions, constructed joins, aggregation and charts. No Olist endorsement. Code and synthetic fixtures: MIT.</p><p>No raw review text, raw CSVs or real order-key witnesses are included. Commercial use of the MIT engine does not grant commercial reuse of Olist-derived artifacts.</p><p class="caption">Pinned source commit: @COMMIT@. Full hashes and URLs: <a href="../study/source-manifest.json">manifest</a>. Aggregate evidence: <a href="../study/results/olist.json">Olist JSON</a> and <a href="../study/results/cancellation.json">synthetic JSON</a>.</p><p class="evidence">Olist aggregate JSON SHA-256: @HASH@</p></section><footer>Join Proof Lab · AI-assisted development, with reproducible tests and stated limits. No claim of algorithmic novelty, adoption or unaided authorship.</footer></main></body></html>
"""
    replacements = {
        "CARDS": "".join(cards),
        "BARS": "".join(bars),
        "ROWS": "".join(rows),
        "CASES": "".join(cases),
        "NAIVE_ROWS": f"{full['naive_sql']['output_rows']:,}",
        "ORDERS": f"{full['source_rows']['orders']:,}",
        "DISTINCT": money(full["naive_sql"]["distinct_payments_units"]),
        "FAILURES": str(failures),
        "MONTHS": str(len(months)),
        "COMMIT": html.escape(study["dataset_commit"]),
        "HASH": hashlib.sha256(raw).hexdigest(),
    }
    for key, value in replacements.items():
        template = template.replace("@" + key + "@", value)
    return template


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = HERE.parent / "report" / "index.html"
    content = render()
    if args.check:
        if target.read_text() != content:
            raise SystemExit("Report differs from its source evidence; regenerate")
    else:
        target.parent.mkdir(exist_ok=True)
        target.write_text(content)
