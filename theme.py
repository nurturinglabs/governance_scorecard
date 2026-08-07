"""
theme.py — design tokens, global CSS, and shared visual helpers.

Single source for color/type/layout tokens used by every component. Score
coloring is derived from config.SCORE_BANDS so the heatmap, KPI strip, and
breakdown bars all agree on one palette — nothing below hardcodes a band color.
"""

from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

import config

_ICON_PATH = Path(__file__).resolve().parent / "icon.jpeg"


@st.cache_data
def _icon_data_uri() -> str:
    b64 = base64.b64encode(_ICON_PATH.read_bytes()).decode()
    return f"data:image/jpeg;base64,{b64}"

# --------------------------------------------------------------------------- #
# Design tokens — define once, everything references these. Band colors come
# from config.SCORE_BANDS, not duplicated here.
# --------------------------------------------------------------------------- #
NAVY = "#002147"           # header bar background (Oxford Blue)
GOLD = "#FFBA08"           # header title / context tags (Selective Yellow)
GOLD_TILE_BG = "rgba(242,194,78,.15)"
GOLD_TAG_BORDER = "rgba(242,194,78,.45)"
SUBTITLE_COLOR = "rgba(233,222,196,.75)"
ACCENT = "#185FA5"         # links, drill affordance, hover
THRESHOLD_COLOR = "#BA7517"

UP = "#1D9E75"
DOWN = "#C0492A"

PAGE_BG = "#ffffff"
CARD_BORDER = "#e6e9ef"
SUBTLE_FILL = "#f4f6f9"
TEXT_PRIMARY = "#1a2b3c"
TEXT_SECONDARY = "#5f6b7a"
TEXT_MUTED = "#8a94a3"

FONT_HEADING = "'Libre Franklin',system-ui,sans-serif"
FONT_BODY = "'Libre Franklin',system-ui,sans-serif"
FONT_MONO = "ui-monospace,SFMono-Regular,Menlo,monospace"

_CSS = f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Libre+Franklin:wght@400;500;600;700&display=swap');

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
                 padding:16px 20px;margin-bottom:18px;border-radius:12px;gap:12px;}}
  .gov-appheader .brand{{display:flex;align-items:center;gap:16px;}}
  .gov-appheader .brand-mark{{width:56px;height:56px;border-radius:11px;flex:none;
                              display:flex;align-items:center;justify-content:center;overflow:hidden;}}
  .gov-appheader .brand-mark img{{width:100%;height:100%;object-fit:cover;}}
  .gov-appheader .brand-divider{{width:2px;height:68px;flex:none;background:{GOLD};}}
  .gov-appheader h1{{font-family:{FONT_HEADING};font-size:28px;font-weight:600;
                     color:{GOLD};margin:0;letter-spacing:.2px;line-height:1;}}
  .gov-appheader .tagline{{font-size:14px;font-weight:400;color:{SUBTITLE_COLOR};margin-top:-6px;}}
  .gov-appheader .badges{{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end;}}
  .gov-appheader .badge{{font-size:12px;color:{GOLD};border:0.5px solid {GOLD_TAG_BORDER};
                        padding:3px 11px;border-radius:999px;white-space:nowrap;}}

  /* "Viewing" score-metric selector row */
  .gov-viewing-l{{font-size:12px;color:{TEXT_MUTED};}}

  /* segmented control (native widget) — flatten to the mockup's plain
     hairline-bordered pill group instead of Streamlit's default blue
     selection ring */
  div[data-testid="stSegmentedControl"] {{border-radius:8px;}}
  div[data-testid="stSegmentedControl"] label {{
    border-color:{CARD_BORDER} !important; box-shadow:none !important;
    background:transparent !important; font-size:13px; color:{TEXT_SECONDARY};}}
  div[data-testid="stSegmentedControl"] label:has(input:checked) {{
    background:{SUBTLE_FILL} !important; color:{TEXT_PRIMARY} !important; font-weight:500;}}

  /* page title (page 1 "All products" / page 2 product name) */
  .gov-page-title{{display:flex;align-items:baseline;gap:10px;margin:0 0 14px;}}
  .gov-page-name{{font-size:29px;font-weight:600;color:{TEXT_PRIMARY};letter-spacing:-.4px;}}
  .gov-page-sub{{font-size:13px;color:{TEXT_MUTED};}}

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

  /* KPI strip — one bordered card, columns divided by hairlines (no accent
     bars, no icon circles) */
  .gov-kpi-strip{{border:2px solid {CARD_BORDER};border-radius:12px;background:{PAGE_BG};
                 overflow:hidden;margin:.5rem 0 1.1rem;}}
  .gov-kpi-grid{{display:grid;grid-template-columns:repeat(4,1fr);}}
  .gov-kpi-cell{{padding:13px 16px;border-left:2px solid {CARD_BORDER};}}
  .gov-kpi-cell:first-child{{border-left:none;}}
  .gov-kpi-l{{font-size:11px;letter-spacing:.05em;text-transform:uppercase;
             color:{TEXT_MUTED};font-weight:500;}}
  .gov-kpi-v{{font-size:26px;font-weight:600;color:{TEXT_PRIMARY};
             font-variant-numeric:tabular-nums;letter-spacing:-.5px;margin-top:3px;}}
  .gov-kpi-s{{font-size:12px;color:{TEXT_SECONDARY};margin-top:2px;}}
  .gov-kpi-s.up{{color:{UP};}} .gov-kpi-s.down{{color:{DOWN};}}

  /* heatmap — the hero view on both pages: tight, flat, softer palette */
  .gov-hm-strip{{display:grid;gap:3px;align-items:center;width:100%;}}
  .gov-hm-wk{{font-size:11px;color:{TEXT_MUTED};text-align:center;}}
  .gov-hm-cell{{height:30px;border-radius:5px;display:flex;align-items:center;
               justify-content:center;font-size:13px;font-weight:600;
               font-variant-numeric:tabular-nums;}}
  .gov-hm-cell.gap{{background:repeating-linear-gradient(45deg,#eef1f5,#eef1f5 5px,#f7f9fc 5px,#f7f9fc 10px);}}
  .gov-hm-legend{{display:flex;gap:14px;margin:2px 0 10px;font-size:11px;color:{TEXT_SECONDARY};}}
  .gov-hm-legend i{{display:inline-block;width:11px;height:11px;border-radius:2px;margin-right:4px;vertical-align:-1px;}}

  /* products heatmap — clickable rows: right-aligned label + trailing chevron */
  .gov-hm-rowwrap{{display:flex;align-items:center;gap:4px;}}
  .gov-hm-chevron{{opacity:0;color:{TEXT_MUTED};font-size:15px;width:16px;flex:none;
                  text-align:center;transition:opacity .12s ease;}}
  div[data-testid="stHorizontalBlock"]:hover .gov-hm-chevron{{opacity:1;}}

  /* tables heatmap — terminal, two-line row label (name + gap) */
  .gov-hm-label2{{padding:2px 10px 2px 6px;overflow:hidden;}}
  .gov-hm-tname{{font-size:12.5px;font-family:{FONT_MONO};color:{TEXT_PRIMARY};
                white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
  .gov-hm-tsub{{font-size:11px;color:{TEXT_MUTED};white-space:nowrap;overflow:hidden;
               text-overflow:ellipsis;margin-top:1px;}}
  .gov-hm-tsub.flag{{color:{DOWN};}}

  /* row-label buttons on the products heatmap — link-styled, right-aligned,
     recolor to accent on row hover (not just button hover) */
  div[data-testid="stButton"] button[kind="tertiary"]{{
    justify-content:flex-start;text-align:left;font-size:13px;font-weight:500;
    color:{ACCENT};border:none;background:transparent;padding:4px 6px;}}
  div[data-testid="stHorizontalBlock"] div[data-testid="stButton"] button[kind="tertiary"]{{
    justify-content:flex-end;text-align:right;color:{TEXT_PRIMARY};min-height:30px;
    padding:2px 10px 2px 6px;}}
  div[data-testid="stHorizontalBlock"]:hover div[data-testid="stButton"] button[kind="tertiary"]{{
    color:{ACCENT};}}
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


def sparkline_svg(series: list[float], w: int = 58, h: int = 22) -> str:
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
            f"<polyline fill='none' stroke='{stroke}' stroke-width='1.6' points='{coords}'/></svg>")


def section_header(title: str, meta: str | None = None) -> str:
    """Small bold header row with optional right-aligned meta text."""
    meta_html = f"<span class='meta'>{meta}</span>" if meta else ""
    return f"<div class='gov-section'><span class='t'>{title}</span>{meta_html}</div>"


def page_title(title: str, sub: str | None = None) -> str:
    """Large page title (page 1 'All products' / page 2 product name), with
    an optional muted inline subtitle (e.g. table count)."""
    sub_html = f"<span class='gov-page-sub'>{sub}</span>" if sub else ""
    return f"<div class='gov-page-title'><span class='gov-page-name'>{title}</span>{sub_html}</div>"


def app_header(title: str, tagline: str | None = None, badges: list[str] | None = None) -> str:
    """Top-of-page brand bar: gold star mark + title/tagline, right-aligned
    pill badges (as-of date / threshold / rollup context). Shown once, above
    every page."""
    tagline_html = f"<div class='tagline'>{tagline}</div>" if tagline else ""
    badges_html = "".join(f"<span class='badge'>{b}</span>" for b in (badges or []))
    return (
        "<div class='gov-appheader'>"
        "<div class='brand'>"
        f"<div class='brand-mark'><img src='{_icon_data_uri()}' alt='logo'/></div>"
        "<div class='brand-divider'></div>"
        f"<div><h1>{title}</h1>{tagline_html}</div>"
        "</div>"
        f"<div class='badges'>{badges_html}</div>"
        "</div>")
