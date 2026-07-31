"""
theme.py — design tokens, global CSS, and shared visual helpers.

Single source for color/type/layout tokens used by every component. Score
coloring is derived from config.SCORE_BANDS so the heatmap, KPI cards, and
breakdown bars all agree on one palette — nothing below hardcodes a band color.
"""

from __future__ import annotations

import streamlit as st

import config

# --------------------------------------------------------------------------- #
# Design tokens (§3 of the polish spec) — define once, everything references
# these. Band colors come from config.SCORE_BANDS, not duplicated here.
# --------------------------------------------------------------------------- #
NAVY = "#003366"
GOLD = "#FFB500"
THRESHOLD_COLOR = "#BA7517"

UP = "#1D9E75"
DOWN = "#D85A30"

PAGE_BG = "#ffffff"
CARD_BORDER = "#e6e9ef"
SUBTLE_FILL = "#f4f6f9"
TEXT_PRIMARY = "#1a2b3c"
TEXT_SECONDARY = "#5f6b7a"
TEXT_MUTED = "#8a94a3"

FONT_HEADING = "'Oswald','Inter',system-ui,sans-serif"
FONT_BODY = "'Inter',system-ui,sans-serif"
FONT_MONO = "ui-monospace,SFMono-Regular,Menlo,monospace"

CONTENT_MAX_WIDTH = None  # None = use the full page width

_CSS = f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Oswald:wght@500;600&display=swap');

  /* hide Streamlit chrome */
  #MainMenu, header[data-testid="stHeader"], footer {{visibility:hidden; height:0;}}

  /* width + rhythm */
  .block-container{{max-width:100%; padding-top:1.4rem; padding-bottom:3rem;
                    padding-left:5%; padding-right:5%;}}

  /* fonts (fallback-safe) */
  html, body, [class*="css"]{{font-family:{FONT_BODY}; color:{TEXT_PRIMARY};}}
  h1,h2,h3,.gov-h{{font-family:{FONT_HEADING}; letter-spacing:.2px;}}
  .gov-mono{{font-family:{FONT_MONO};}}

  /* app header — top-of-page brand bar, shown on every page */
  .gov-appheader{{background:{NAVY};display:flex;align-items:center;justify-content:space-between;
                 padding:.85rem 1.3rem;margin-bottom:1.2rem;border-radius:10px;}}
  .gov-appheader .brand{{display:flex;align-items:center;gap:9px;}}
  .gov-appheader .brand i{{width:10px;height:10px;border-radius:2px;background:{GOLD};
                          display:inline-block;flex:none;}}
  .gov-appheader .brand h1{{font-family:{FONT_HEADING};font-size:21px;font-weight:600;
                            color:{GOLD};margin:0;letter-spacing:.3px;}}
  .gov-appheader .meta{{font-size:12px;color:{GOLD};opacity:.85;text-align:right;}}

  /* section header row */
  .gov-section{{display:flex;align-items:baseline;justify-content:space-between;
               margin:0.2rem 0 0.4rem;}}
  .gov-section .t{{font-size:14px;font-weight:600;color:{TEXT_PRIMARY};}}
  .gov-section .meta{{font-size:12px;color:{TEXT_MUTED};}}

  /* generic bordered card */
  .gov-card{{background:{PAGE_BG};border:1px solid {CARD_BORDER};border-radius:12px;
            padding:0.9rem 1.1rem;}}

  /* native st.container(border=True) restyled to match the .gov-card token */
  div[data-testid="stVerticalBlockBorderWrapper"] > div[data-testid="stVerticalBlock"] {{
    border:1px solid {CARD_BORDER} !important; border-radius:12px !important;
    padding:0.9rem 1.1rem !important; background:{PAGE_BG};
  }}

  /* KPI cards */
  .gov-kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:.5rem 0 1rem;}}
  .gov-kpi{{background:{PAGE_BG};border:1px solid {CARD_BORDER};border-radius:12px;padding:.85rem 1rem;}}
  .gov-kpi-l{{font-size:12px;color:{TEXT_SECONDARY};}}
  .gov-kpi-v{{font-size:26px;font-weight:600;line-height:1.25;color:{TEXT_PRIMARY};}}
  .gov-kpi-d{{font-size:12px;margin-top:2px;}}
  .gov-kpi-d.up{{color:{UP};}} .gov-kpi-d.down{{color:{DOWN};}}
  .gov-kpi-sub{{font-size:12px;color:{TEXT_MUTED};margin-top:2px;}}

  /* heatmap grid */
  .gov-hm{{display:grid;gap:2px;align-items:center;justify-content:start;}}
  .gov-hm-wk{{font-size:8px;color:{TEXT_MUTED};text-align:center;}}
  .gov-hm-corner{{}}
  .gov-hm-row{{font-size:11px;color:#3a4453;white-space:nowrap;overflow:hidden;
              text-overflow:ellipsis;padding-right:6px;}}
  .gov-hm-cell{{height:24px;width:100%;border-radius:3px;display:flex;align-items:center;
               justify-content:center;font-size:9px;}}
  .gov-hm-cell.gap{{background:repeating-linear-gradient(45deg,#eef1f5,#eef1f5 4px,#f7f9fc 4px,#f7f9fc 8px);}}
  .gov-hm-legend{{display:flex;gap:12px;margin:2px 0 8px;font-size:11px;color:{TEXT_SECONDARY};}}
  .gov-hm-legend i{{display:inline-block;width:11px;height:11px;border-radius:2px;margin-right:4px;vertical-align:-1px;}}

  /* page-1 product rows */
  .gov-row{{display:grid;grid-template-columns:1.6fr 70px 90px 60px 60px 60px;
           align-items:center;gap:10px;padding:10px 4px;border-top:1px solid {CARD_BORDER};font-size:13px;}}
  .gov-row .name{{font-weight:500;}}
  .gov-row .hdr{{font-size:11px;color:{TEXT_MUTED};border-top:none;padding-bottom:2px;}}
  .gov-scorebar{{height:8px;border-radius:4px;background:{SUBTLE_FILL};position:relative;}}
  .gov-scorebar > i{{display:block;height:100%;border-radius:4px;background:{NAVY};}}

  /* page-2 tables list */
  .gov-tbl{{width:100%;border-collapse:collapse;font-size:12px;}}
  .gov-tbl th{{font-size:11px;color:{TEXT_MUTED};font-weight:400;text-align:left;padding:6px 8px;}}
  .gov-tbl td{{padding:8px;border-top:1px solid {CARD_BORDER};white-space:nowrap;
              overflow:hidden;text-overflow:ellipsis;}}
  .gov-unowned{{color:{DOWN};}}

  /* breakdown / "biggest drag" card */
  .gov-drag{{background:#fcece7;border:1px solid #f0997b;border-radius:12px;padding:14px 16px;margin-top:.5rem;}}
  .gov-drag .t{{font-size:14px;font-weight:600;color:#993c1d;}}
  .gov-drag .bar{{height:8px;background:rgba(0,0,0,.08);border-radius:4px;display:block;}}
  .gov-drag .bar > i{{display:block;height:100%;border-radius:4px;}}
  .gov-bd-row{{display:grid;grid-template-columns:130px 1fr 56px;align-items:center;gap:10px;margin:7px 0;}}

  /* tertiary drill / back buttons */
  div[data-testid="stButton"] button[kind="tertiary"]{{color:{NAVY};}}
</style>
"""


def apply_theme() -> None:
    """Apply page-level theming. Call once, right after set_page_config."""
    st.markdown(_CSS, unsafe_allow_html=True)


def score_color(score: float | int | None) -> str:
    """Hex fill for a score, from config.SCORE_BANDS."""
    if score is None:
        return "#c9ced6"
    return config.band_for(score)["color"]


def score_text_color(score: float | int | None) -> str:
    if score is None:
        return TEXT_SECONDARY
    return config.band_for(score)["text"]


def ratio_color(ratio: float) -> str:
    """Traffic-light for a 0..1 attainment ratio (breakdown bars)."""
    if ratio >= 0.70:
        return UP
    if ratio >= 0.40:
        return "#EF9F27"
    return DOWN


def delta_str(delta: float | int | None) -> str | None:
    """Signed delta string ('+2' / '-3'), or None to hide (0/None both hide)."""
    if delta is None or round(delta) == 0:
        return None
    d = round(delta)
    return f"{d:+d}"


def delta_class(delta: float | int | None, inverse: bool = False) -> str:
    """'up' or 'down' CSS class for a delta, accounting for inverse metrics
    (e.g. fewer below-threshold tables is 'up' even though the number fell)."""
    good = (delta or 0) > 0
    if inverse:
        good = not good
    return "up" if good else "down"


def sparkline_svg(series: list[float], w: int = 60, h: int = 18) -> str:
    """Inline SVG sparkline; stroke colored by net direction."""
    pts = [p for p in series if p is not None]
    if len(pts) < 2:
        return f"<svg width='{w}' height='{h}' viewBox='0 0 {w} {h}'></svg>"
    lo, hi = min(pts), max(pts)
    rng = (hi - lo) or 1
    coords = " ".join(
        f"{i / (len(pts) - 1) * w:.1f},{h - (v - lo) / rng * (h - 2) - 1:.1f}"
        for i, v in enumerate(pts))
    stroke = UP if pts[-1] >= pts[0] else DOWN
    return (f"<svg width='{w}' height='{h}' viewBox='0 0 {w} {h}'>"
            f"<polyline fill='none' stroke='{stroke}' stroke-width='1.5' points='{coords}'/></svg>")


def section_header(title: str, meta: str | None = None) -> str:
    """Small bold header row with optional right-aligned meta text."""
    meta_html = f"<span class='meta'>{meta}</span>" if meta else ""
    return f"<div class='gov-section'><span class='t'>{title}</span>{meta_html}</div>"


def app_header(title: str, meta: str | None = None) -> str:
    """Top-of-page brand bar: gold accent mark + app title, right-aligned meta
    (as-of date / threshold / rollup context). Shown once, above every page."""
    meta_html = f"<span class='meta'>{meta}</span>" if meta else ""
    return (
        "<div class='gov-appheader'>"
        f"<div class='brand'><i></i><h1>{title}</h1></div>"
        f"{meta_html}</div>")
