"""CRDC Model Lab. Run: streamlit run dashboard/app.py."""

from pathlib import Path
import json
import sys

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from results import DATA, label, latest_experiments, load_snapshots, scores, year

st.set_page_config(page_title="CRDC · Model Lab", page_icon="📊", layout="wide")
st.markdown(
    """<style>
.stApp {background:#f6f8fb;color:#14293d}
.block-container {max-width:1280px;padding-top:2rem;padding-bottom:3rem}
h1,h2,h3 {letter-spacing:-.035em}
.hero {background:#132e44;color:#fff;padding:32px 36px;border-radius:18px;margin-bottom:24px}
.hero .eyebrow {color:#81d9cf;font-size:12px;letter-spacing:.18em;font-weight:700}
.hero h1 {color:#fff;font-size:42px;margin:12px 0 6px}
.hero p {color:#d5e2ed;max-width:760px;margin:0;font-size:17px;line-height:1.6}
[data-testid="stMetric"] {background:#fff;border:1px solid #dce5ed;border-radius:12px;padding:18px}
[data-testid="stMetricLabel"] {color:#52687b}
[data-testid="stMetricValue"] {color:#087f8c}
[data-testid="stTabs"] {margin-top:14px}
</style>""",
    unsafe_allow_html=True,
)
st.markdown(
    """<div class="hero"><div class="eyebrow">BREAK THROUGH TECH · CAPITAL ONE · CRDC</div>
<h1>Understand the signal.</h1><p>Explore how school characteristics relate to reported seclusion.
Compare models, inspect the data, and share the evidence behind each result.</p></div>""",
    unsafe_allow_html=True,
)

METRICS = {
    "pr_auc": "PR-AUC",
    "pr_auc_lift": "Lift over prevalence",
    "recall_at_top10": "Recall in top 10%",
    "roc_auc": "ROC-AUC",
    "brier": "Brier score",
}
COLORS = ["#087f8c", "#245d89", "#d59042", "#7d68a5", "#698b78", "#ba6471"]


def chart(fig, key):
    fig.update_layout(
        template="plotly_white",
        font=dict(family="Arial", size=14, color="#14293d"),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=15, t=35, b=20),
        legend_title_text="",
        colorway=COLORS,
    )
    st.plotly_chart(
        fig,
        use_container_width=True,
        key=key,
        config={
            "displaylogo": False,
            "toImageButtonOptions": {"format": "png", "scale": 2},
        },
    )


def metric_cards(row, baseline):
    for col, name, fmt in zip(
        st.columns(4),
        ["pr_auc", "pr_auc_lift", "recall_at_top10", "roc_auc"],
        [".3f", ".2f", ".1%", ".3f"],
    ):
        value = format(row[name], fmt) + ("×" if name == "pr_auc_lift" else "")
        delta = (
            f"{row[name]-baseline[name]:+.3f} vs no-skill"
            if baseline is not None
            else None
        )
        col.metric(METRICS[name], value, delta=delta)


def model_chart(frame, selected, key, metric="pr_auc"):
    frame = frame.sort_values(metric, ascending=metric != "brier").copy()
    frame["focus"] = frame.model.map(
        lambda m: "Selected" if m == selected else "Other models"
    )
    fig = px.bar(
        frame,
        x=metric,
        y="model",
        orientation="h",
        color="focus",
        color_discrete_map={"Selected": "#087f8c", "Other models": "#a8bccd"},
        text=metric,
        labels={metric: METRICS[metric], "model": "Model"},
        hover_data=["roc_auc", "recall_at_top10"],
    )
    fig.update_traces(
        texttemplate="%{text:.3f}", textposition="outside", cliponaxis=False
    )
    fig.update_layout(showlegend=False, height=350)
    chart(fig, key)


@st.fragment(run_every="30s")
def dashboard():
    snapshots, errors = load_snapshots()
    if errors:
        st.warning(
            f"{len(errors)} unreadable result file(s) skipped. Last valid results remain available."
        )
    if not snapshots:
        st.info(
            "No completed experiments have been published yet. Run the baseline or export an existing report folder."
        )
        return
    by_id = {s["snapshot_id"]: s for s in snapshots}
    pinned = st.query_params.get("snapshot")
    if pinned and pinned not in by_id:
        st.error(
            "This presentation snapshot is unavailable. Remove the snapshot parameter from the URL to browse current results."
        )
        return
    latest = latest_experiments(snapshots)
    choices = {s["experiment_id"]: s for s in latest}
    if pinned:
        active = by_id[pinned]
        st.info(f"Presentation pinned · {label(active)} · {pinned[:12]}")
        if st.button("Return to latest results"):
            for key in ("snapshot", "view", "evaluation", "model"):
                if key in st.query_params:
                    del st.query_params[key]
            st.rerun()
    else:
        default = next(
            (
                s["experiment_id"]
                for s in latest
                if len(s["info"]["train_years"]) == 3
                and s["evaluation"] == "forward_temporal"
            ),
            latest[0]["experiment_id"],
        )
        ids = list(choices)
        exp = st.selectbox(
            "Training experiment",
            ids,
            index=ids.index(default),
            format_func=lambda k: label(choices[k]),
            key="experiment",
        )
        active = choices[exp]
    info = active["info"]
    left, middle, right = st.columns([2, 2, 1])
    models = list(info["models"])
    initial = st.query_params.get("model", "M5")
    if initial not in models:
        initial = models[0]
    selected = left.selectbox(
        "Model to inspect",
        models,
        index=models.index(initial),
        format_func=lambda m: f'{m} · {info["models"][m]}',
        key=f'model_{active["experiment_id"]}',
    )
    modes = ["Temporal test", "District-grouped CV"]
    preferred = 1 if active["evaluation"] == "backward_temporal" else 0
    if pinned:
        preferred = 1 if st.query_params.get("evaluation") == "cv_mean" else 0
    mode = middle.selectbox(
        "Evaluation",
        modes,
        index=preferred,
        disabled=bool(pinned),
        key=f'eval_{active["experiment_id"]}_{bool(pinned)}',
    )
    field = "test" if mode == modes[0] else "cv_mean"
    if right.button(
        "Pin presentation",
        help="Preserve this completed result in the URL. New runs will not replace it.",
    ):
        st.query_params["snapshot"] = active["snapshot_id"]
        st.query_params["model"] = selected
        st.query_params["view"] = "Presentation"
        st.query_params["evaluation"] = field
        st.rerun()
    if pinned and st.query_params.get("evaluation") in ["test", "cv_mean"]:
        # Keep the pinned presentation's evaluation explicit, independently of widget defaults.
        field = st.query_params["evaluation"]
        mode = modes[0 if field == "test" else 1]
    frame = scores(active, field)
    row = frame.set_index("model").loc[selected]
    baseline = frame.set_index("model").loc["M0"] if "M0" in models else None
    timestamp = (
        pd.Timestamp(active["results_saved_at"])
        .tz_convert("America/Los_Angeles")
        .strftime("%b %d, %Y · %I:%M %p %Z")
    )
    st.caption(
        f'Results saved {timestamp} · Snapshot {active["snapshot_id"][:12]} · '
        + (
            "Pinned; will not change automatically."
            if pinned
            else "Checks for published results every 30 seconds."
        )
    )
    if active["evaluation"] == "backward_temporal" and field == "test":
        st.warning(
            "Backward-year test: this model trained on a newer year and scored an older year. Do not compare it as a forward temporal test."
        )
    if info.get("fast"):
        st.warning("Reduced-size exploratory run; not a full baseline evaluation.")
    st.caption(
        (
            "Test population: "
            + year(info["test_year"])
            + f' · {info["test_rows"]:,} schools · {info["test_positives"]:,} positives'
        )
        if field == "test"
        else f'{info["cv_folds"]}-fold district-grouped CV on training years · metrics are fold means'
    )
    views = ["Overview", "Compare models", "Data quality", "Presentation"]
    default_view = st.query_params.get("view", "Overview")
    view = st.radio(
        "Explore",
        views,
        index=views.index(default_view) if default_view in views else 0,
        horizontal=True,
        key=f"view_{bool(pinned)}",
        label_visibility="collapsed",
    )
    if view in ["Overview", "Presentation"]:
        st.subheader(
            "A clearer view of reported seclusion"
            if view == "Overview"
            else f"{selected} · The evidence at a glance"
        )
        metric_cards(row, baseline)
        c1, c2 = st.columns([1.4, 1])
        with c1:
            st.markdown("#### How the models compare")
            model_chart(frame, selected, "overview_models")
        with c2:
            st.markdown("#### What this result says")
            st.markdown(
                f"**{row.recall_at_top10:.1%} of positive schools** are captured in the highest-scored 10%."
            )
            st.markdown(
                f"**{row.pr_auc_lift:.2f}× the no-skill PR-AUC**, relative to outcome prevalence."
            )
            st.markdown(
                "The target is **whether a school reports any seclusion**, not the number of incidents or a causal staffing effect."
            )
            st.caption(
                "Uses school characteristics from the same year as the outcome. This is not a next-year forecast."
            )
        if view == "Presentation":
            st.info(
                "Use Pin presentation before presenting or sharing the URL. Charts can be downloaded as PNGs from their toolbar."
            )
        with st.expander("Model definitions and metric guide"):
            st.table(
                pd.DataFrame(
                    [
                        {"Model": m, "Definition": desc}
                        for m, desc in info["models"].items()
                    ]
                )
            )
            st.markdown(
                "**PR-AUC:** average precision; higher is better. **Lift:** PR-AUC / prevalence. "
                "**Recall in top 10%:** share of positive schools captured in the top-scored tenth. "
                "**ROC-AUC:** ranking discrimination. **Brier:** probability error; lower is better. "
                "CV lift is the mean of fold lifts, not the ratio of aggregate means."
            )
    elif view == "Compare models":
        st.subheader("Find the tradeoffs, not just the winner")
        chosen = st.multiselect(
            "Models to compare",
            models,
            default=models,
            key=f'compare_{active["experiment_id"]}',
        )
        metric = st.selectbox(
            "Comparison metric", list(METRICS), format_func=METRICS.get
        )
        if chosen:
            model_chart(
                frame[frame.model.isin(chosen)], selected, "comparison_models", metric
            )
            st.dataframe(
                frame[frame.model.isin(chosen)][["model", *METRICS]],
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.info("Select at least one model to display the comparison.")
        st.markdown("#### Training-year comparison · latest published forward tests")
        candidates = [
            s
            for s in latest
            if s["evaluation"] == "forward_temporal"
            and s["info"]["test_year"] == info["test_year"]
            and selected in s["info"]["models"]
            and not s["info"].get("fast")
            and s["info"].get("exclude_states", []) == info.get("exclude_states", [])
            and s["info"]["test_rows"] == info["test_rows"]
        ]
        rows = []
        for s in candidates:
            r = scores(s).set_index("model").loc[selected].to_dict()
            rows.append(
                {
                    "Training years": " + ".join(
                        year(y) for y in s["info"]["train_years"]
                    ),
                    **r,
                }
            )
        if rows:
            chart(
                px.bar(
                    pd.DataFrame(rows),
                    x=metric,
                    y="Training years",
                    orientation="h",
                    color_discrete_sequence=["#087f8c"],
                    labels={metric: METRICS[metric]},
                ),
                "year_comparison",
            )
            st.caption(
                "Same test-year label and row count; historical runs lack input hashes. Verify identical test data before interpreting small differences. This panel uses latest snapshots even when the inspected result is pinned."
            )
        if field == "test":
            st.markdown("#### Calibration · predicted vs observed")
            cal = pd.DataFrame(active["tables"]["calibration"])
            cal = cal[cal.model.isin(chosen) & cal["count"].gt(0)]
            if len(cal):
                fig = px.line(
                    cal,
                    x="mean_predicted",
                    y="observed_rate",
                    color="model",
                    markers=True,
                    hover_data=["count"],
                    labels={
                        "mean_predicted": "Mean predicted probability",
                        "observed_rate": "Observed positive share",
                    },
                    color_discrete_sequence=COLORS,
                )
                fig.add_trace(
                    go.Scatter(
                        x=[0, 1],
                        y=[0, 1],
                        mode="lines",
                        name="Perfect calibration",
                        line=dict(dash="dash", color="#9baaba"),
                    )
                )
                chart(fig, "calibration")
        if info["test_new_school_rows"] and field == "test":
            st.markdown("#### Schools absent from this training set")
            new = pd.DataFrame(active["tables"]["new_schools"])
            st.dataframe(
                new[new.model.isin(chosen)][["model", "n", "positives", *METRICS]],
                hide_index=True,
                use_container_width=True,
            )
            st.caption(
                "This cohort changes with the training years; its scores are not directly comparable across experiments."
            )
        context_path = DATA / "context.json"
        if context_path.exists():
            context = json.loads(context_path.read_text())
            common = [
                r
                for r in context["common_new_schools"]
                if r["snapshot_id"] == active["snapshot_id"]
            ]
            if common and selected == "M5" and field == "test":
                st.markdown("#### Fixed new-school cohort · November 4 comparison")
                st.caption(
                    "The same 2,241 schools / 128 positives, absent from all three older training datasets. Historical snapshot comparison; not recomputed for new runs."
                )
                st.dataframe(
                    pd.DataFrame(context["common_new_schools"]).drop(
                        columns=["snapshot_id"]
                    ),
                    hide_index=True,
                    use_container_width=True,
                )
    elif view == "Data quality":
        st.subheader("Understand which schools are represented")
        rows = []
        for code, steps in active["filters"].items():
            rows.extend(
                {"Year": year(code), "Filter": step.replace("_", " "), "Schools": n}
                for step, n in steps.items()
            )
        if rows:
            chart(
                px.bar(
                    pd.DataFrame(rows),
                    x="Filter",
                    y="Schools",
                    color="Year",
                    barmode="group",
                    color_discrete_sequence=COLORS,
                ),
                "filters",
            )
            st.caption(
                "Filter counts start from the loaded analysis file, not the full CRDC roster. Unknown outcomes are never counted as zero."
            )
        st.markdown("#### Missing student-group shares · test population")
        missing = pd.DataFrame(active["tables"]["missingness"])
        st.dataframe(
            missing[missing.model.eq(selected)][["subset", "n", "positives", *METRICS]],
            hide_index=True,
            use_container_width=True,
        )
        context_path = DATA / "context.json"
        if context_path.exists():
            context = json.loads(context_path.read_text())
            st.markdown("#### 2020–21 reporting gaps · fixed data audit")
            states = pd.DataFrame(context["state_missingness"]).sort_values(
                "missing_share", ascending=False
            )
            fig = px.bar(
                states.head(15),
                x="lea_state",
                y="missing_share",
                hover_data=["schools", "missing_outcome"],
                labels={
                    "lea_state": "State / territory",
                    "missing_share": "Schools with unknown outcome",
                },
                color_discrete_sequence=["#d59042"],
            )
            fig.update_yaxes(tickformat=".0%")
            chart(fig, "state_missingness")
            st.caption(
                "November 4, 2026 snapshot of the full 2020–21 cleaned roster; not a live audit of newly trained inputs. Missingness varies substantially by state."
            )
    st.divider()
    with st.expander("Provenance, limitations, and downloads"):
        st.write(active["provenance"])
        st.write(
            "State is an important predictor and may capture reporting differences. These results show associations, not evidence that changing staffing causes a change in seclusion. Training-year comparisons on the same test year are exploratory."
        )
        st.json(
            {
                k: info[k]
                for k in (
                    "train_years",
                    "test_year",
                    "seed",
                    "cv_folds",
                    "input_sha256",
                    "training_code_sha256",
                    "versions",
                )
                if k in info
            }
        )
        st.download_button(
            "Download selected metrics (CSV)",
            frame.to_csv(index=False),
            file_name=f'crdc-{active["snapshot_id"][:12]}-{field}.csv',
            mime="text/csv",
        )
        st.download_button(
            "Download complete result snapshot",
            json.dumps(active, indent=2),
            file_name=f'crdc-{active["snapshot_id"][:12]}.json',
            mime="application/json",
        )
    st.caption(
        "CRDC Model Lab · Research and presentation tool · No training runs are started by this app."
    )


dashboard()
