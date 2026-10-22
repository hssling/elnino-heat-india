"""Paper C figures (journal format): Figure_1-3 and Supplementary Figure_S1 as 600-dpi RGB TIF (LZW, no alpha, one layer) plus PNG review copies.

    python papers/C/figures/make_figures.py

Inputs are the CSVs written by models/C (papers/C/figures/data/), which are also the editable
figure sources, plus GADM 4.1 state boundaries (pipeline.boundaries)
dissolved to the 34 analysis units of pipeline/reference/state_frame.csv.
"""
import io
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import TwoSlopeNorm  # noqa: E402
from PIL import Image  # noqa: E402

FIG = Path(__file__).resolve().parent
ROOT = FIG.parents[2]
DATA = FIG / "data"
sys.path.insert(0, str(ROOT))

MM = 1 / 25.4
DPI = 600
# Okabe-Ito colour-blind-safe palette
OI = {"blue": "#0072B2", "orange": "#E69F00", "green": "#009E73", "vermillion": "#D55E00",
      "sky": "#56B4E9", "purple": "#CC79A7", "grey": "#7F7F7F", "black": "#000000"}
plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    "font.size": 8, "axes.titlesize": 8, "axes.labelsize": 8, "xtick.labelsize": 7, "ytick.labelsize": 7,
    "legend.fontsize": 7, "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
    "axes.spines.top": False, "axes.spines.right": False, "savefig.facecolor": "white",
})
MINUS = "\u2212"


def save(fig, n) -> None:
    """Save Figure_n.tif (RGB, LZW, 600 dpi, no alpha) and Figure_n.png (RGB, 300 dpi review copy)."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, facecolor="white", bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)
    buf.seek(0)
    with Image.open(buf) as im:
        rgb = im.convert("RGB")
    rgb.save(FIG / f"Figure_{n}.tif", format="TIFF", compression="tiff_lzw", dpi=(DPI, DPI))
    w, h = rgb.size
    rgb.resize((w // 2, h // 2), Image.LANCZOS).save(FIG / f"Figure_{n}.png", format="PNG", dpi=(DPI // 2, DPI // 2))
    print(f"Figure_{n}: {w}x{h} px at {DPI} dpi")


def signed(x, d=1):
    s = f"{x:+.{d}f}"
    return s.replace("-", MINUS)


# ----------------------------------------------------------------------------- Figure 1
def figure1():
    d = pd.read_csv(DATA / "fig1_data.csv")
    fig, (a, b) = plt.subplots(2, 1, figsize=(174 * MM, 110 * MM), sharex=True,
                               gridspec_kw={"height_ratios": [1.4, 1], "hspace": 0.12})
    dec = d["el_nino_decaying"].astype(str).str.lower().eq("true")
    for ax in (a, b):
        for y in d.loc[dec, "year"]:
            ax.axvspan(y - 0.5, y + 0.5, color=OI["orange"], alpha=0.18, lw=0)
    a.bar(d["year"], d["rate_per_10m"], width=0.7, color=OI["blue"])
    a.set_ylabel("Recorded heat/sun-stroke deaths\nper 10 million population")
    a.axvline(2013.5, color=OI["grey"], lw=0.6, ls=":")
    a.text(2013.35, a.get_ylim()[1] * 0.99, "Cause label 'Heat Stroke' to 2013,\n'Heat/Sun Stroke' from 2014",
           fontsize=6, va="top", ha="right", color=OI["grey"])
    a.text(0.005, 1.02, "(a)", transform=a.transAxes, fontweight="bold")
    from matplotlib.patches import Patch
    a.legend(handles=[Patch(color=OI["orange"], alpha=0.35, label="El Ni\u00f1o-decaying year")],
             loc="upper left", frameon=False, bbox_to_anchor=(0.04, 1.0))
    b.plot(d["year"], d["oni_djf_prev"], color=OI["black"], lw=1, marker="o", ms=2.5)
    for v in (0.5, -0.5):
        b.axhline(v, color=OI["grey"], lw=0.6, ls="--")
    b.axhline(0, color=OI["grey"], lw=0.4)
    b.set_ylabel("Preceding-winter ONI (\u00b0C)")
    b.set_xlabel("Year")
    b.text(0.005, 1.02, "(b)", transform=b.transAxes, fontweight="bold")
    b.set_xticks(range(2001, 2025, 2))
    b.set_xlim(2000.4, 2024.6)
    b.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.1f}".replace("-", MINUS)))
    save(fig, 1)


# ----------------------------------------------------------------------------- Figure 2
def unit_geometries():
    from pipeline.boundaries import load
    st = load("state")
    frame = pd.read_csv(ROOT / "pipeline" / "reference" / "state_frame.csv")
    m = frame.assign(gid=frame["gid1_members"].str.split("|")).explode("gid")[["unit_id", "gid"]]
    g = st.merge(m, left_on="state_id", right_on="gid", how="inner")
    return g.dissolve(by="unit_id", as_index=False)[["unit_id", "geometry"]]


def figureS1():
    """Supplementary Figure S1 (ruling P20; was Figure 2): uniform unit-specific IRR map."""
    d = pd.read_csv(DATA / "figS1_unit_irr.csv")
    g = unit_geometries().merge(d, on="unit_id", how="left")
    lo, hi = min(0.8, d["irr"].min()), max(1.25, d["irr"].max())
    norm = TwoSlopeNorm(vmin=lo, vcenter=1.0, vmax=hi)
    fig, ax = plt.subplots(figsize=(84 * MM, 100 * MM))
    g.plot(column="irr", cmap="RdBu_r", norm=norm, edgecolor="white", linewidth=0.2, ax=ax)
    small = {"DL": "Delhi", "CH": "Chandigarh", "PY": "Puducherry", "GA": "Goa", "DNH_DD": "DNH & DD",
             "LD": "Lakshadweep"}
    gp = g.to_crs(3857)
    cent = gp.geometry.representative_point().to_crs(4326)
    for uid, lab in small.items():
        i = g.index[g["unit_id"] == uid]
        if len(i):
            p = cent.loc[i[0]]
            val = float(g.loc[i[0], "irr"])
            ax.plot(p.x, p.y, marker="o", ms=3, color=plt.get_cmap("RdBu_r")(float(norm(val))), mec="black",
                    mew=0.3)
            left = uid in ("LD", "DNH_DD", "GA")
            ax.annotate(f"{lab} {val:.2f}", (p.x, p.y), xytext=(-4 if left else 4, 0), textcoords="offset points",
                        fontsize=5, va="center", ha="right" if left else "left")
    ax.set_axis_off()
    ax.set_aspect("equal")
    sm = plt.cm.ScalarMappable(cmap="RdBu_r", norm=norm)
    cb = fig.colorbar(sm, ax=ax, orientation="horizontal", fraction=0.04, pad=0.02)
    cb.set_label("IRR per 1 \u00b0C of the El Ni\u00f1o term (unit-specific)")
    cb.ax.tick_params(labelsize=6)
    save(fig, "S1")


# ----------------------------------------------------------------------------- Figure 3
def figure2():
    """Figure 2 (was Figure 3): per-fold MALE."""
    d = pd.read_csv(DATA / "fig2_per_fold.csv", dtype={"split_id": str, "label": str, "withheld": str})
    cols = {"A": OI["grey"], "B": OI["sky"], "C": OI["vermillion"]}
    marks = {"A": "o", "B": "s", "C": "D"}
    names = {"A": "A: trend and reporting", "B": "B: A + local climate", "C": "C: B + El Ni\u00f1o and Dipole"}
    fig, (a, b) = plt.subplots(1, 2, figsize=(174 * MM, 80 * MM), gridspec_kw={"width_ratios": [7, 10], "wspace": 0.25},
                               sharey=True)
    for ax, v, title in ((a, "LOEO", "(a) Leave-one-El Ni\u00f1o-out"), (b, "rolling", "(b) Rolling origin")):
        s = d[d["validation"] == v].copy()
        labels = list(dict.fromkeys(s.sort_values("split_id", key=lambda c: c.astype(int))["label"]))
        x = {lab: i for i, lab in enumerate(labels)}
        for k, m in enumerate("ABC"):
            t = s[s["model"] == m]
            ax.plot([x[l] + (k - 1) * 0.18 for l in t["label"]], t["male"], ls="none", marker=marks[m], ms=3.5,
                    color=cols[m], label=names[m])
        ax.set_xticks(range(len(labels)))
        # LOEO folds are labelled by the years withheld (ruling P23, M1); two lines avoid overlap
        wh = dict(zip(s["label"], s["withheld"]))
        short = [wh[l].replace("\u2013", "\u2013\n") if v == "LOEO" else l for l in labels]
        ax.set_xticklabels(short, fontsize=6.5)
        ax.set_title(title, loc="left", fontweight="bold")
        ax.set_xlabel("Years withheld" if v == "LOEO" else "Predicted year")
    a.set_ylabel("Mean absolute log error")
    a.legend(frameon=False, loc="upper left")
    save(fig, 2)


# ----------------------------------------------------------------------------- Figure 4
def figure3():
    """Figure 3 (was Figure 4): early warning 2027 by unit."""
    d = pd.read_csv(DATA / "fig3_ew2027.csv")
    nat = pd.read_csv(DATA / "fig3_ew2027_national.csv")
    sc = {"s15": ("+1.5 \u00b0C", OI["sky"]), "s20": ("+2.0 \u00b0C", OI["blue"]), "s25": ("+2.5 \u00b0C", OI["vermillion"])}
    if "obs" in set(d["scenario"]):
        sc["obs"] = ("observed", OI["black"])
    order = d[d["scenario"] == "s20"].sort_values("rank_s20")["unit_name"].tolist()
    y = {u: i for i, u in enumerate(order)}
    fig, ax = plt.subplots(figsize=(163 * MM, 150 * MM))
    offs = np.linspace(-0.25, 0.25, len(sc))
    for k, (s, (lab, col)) in enumerate(sc.items()):
        t = d[d["scenario"] == s]
        yy = [y[u] + offs[k] for u in t["unit_name"]]
        ax.errorbar(t["excess_mean"], yy, xerr=[t["excess_mean"] - t["excess_lo"], t["excess_hi"] - t["excess_mean"]],
                    fmt="o", ms=2.2, lw=0.6, color=col, label=f"ONI {lab}")
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels(order, fontsize=6)
    ax.invert_yaxis()
    ax.axvline(0, color=OI["grey"], lw=0.5)
    ax.set_xlabel("Expected excess recorded heat/sun-stroke deaths in 2027 (relative to ONI 0)")
    ax.legend(frameon=False, loc="lower right", title="Preceding-winter ONI", title_fontsize=7)
    txt = ["National total, mean (nominal 95% interval)"]
    for s, (lab, _) in sc.items():
        r = nat[nat["scenario"] == s].iloc[0]
        txt.append(f"ONI {lab}: {r['excess_mean']:,.0f} ({r['excess_lo']:,.0f}\u2013{r['excess_hi']:,.0f})")
    ax.text(0.98, 0.30, "\n".join(txt), transform=ax.transAxes, ha="right", va="bottom", fontsize=6.5,
            bbox=dict(boxstyle="round,pad=0.4", fc="white", ec=OI["grey"], lw=0.5))
    save(fig, 3)


def main():
    figure1()
    figure2()
    figure3()
    figureS1()


if __name__ == "__main__":
    main()
