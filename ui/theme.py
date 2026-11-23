"""The look and feel of the app: colours, cards, sidebar and small display helpers."""
from html import escape

import streamlit as st

DARK_SIDEBAR = True

BASE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

:root {
  --navy: #0F2A4A; --blue: #1F4E8C; --teal: #1B998B;
  --bg: #F5F7FA; --card: #FFFFFF; --line: #E3E8EF; --text: #1B2733; --muted: #5B6B7B;
}

.stApp, .stApp p, .stApp li, .stApp label, .stApp h1, .stApp h2, .stApp h3, .stApp h4,
.stApp button, .stApp input, .stApp textarea, .stApp td, .stApp th {
  font-family: 'Inter', 'Segoe UI', -apple-system, Roboto, Arial, sans-serif;
}

.block-container { padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1400px; }
header[data-testid="stHeader"] { background: transparent; }
footer { visibility: hidden; }
.element-container:has(> .stMarkdown style) { display: none; }

h1 { color: var(--navy); font-weight: 700; font-size: 1.85rem; letter-spacing: -0.015em;
     padding-bottom: .5rem; margin-bottom: .6rem; border-bottom: 1px solid var(--line); }
h2, h3 { color: var(--navy); font-weight: 600; letter-spacing: -0.01em; }
[data-testid="stCaptionContainer"] { color: var(--muted); }
hr { border-color: var(--line); }

/* KPI cards */
[data-testid="stMetric"] {
  background: var(--card); border: 1px solid var(--line); border-left: 4px solid var(--blue);
  border-radius: 10px; padding: 14px 16px; box-shadow: 0 1px 2px rgba(16,24,40,.05);
}
[data-testid="stMetricLabel"] p { color: var(--muted); font-size: .76rem; font-weight: 600;
  text-transform: uppercase; letter-spacing: .04em; }
[data-testid="stMetricValue"] { color: var(--navy); font-weight: 700; font-size: 1.6rem; }

/* Tabs */
.stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid var(--line); }
.stTabs [data-baseweb="tab"] { height: 44px; padding: 0 16px; font-weight: 600; color: var(--muted);
  border-radius: 8px 8px 0 0; }
.stTabs [aria-selected="true"] { color: var(--blue); }

/* Buttons */
.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button {
  border-radius: 8px; font-weight: 600; padding: .45rem 1.1rem; border: 1px solid var(--line);
  box-shadow: 0 1px 2px rgba(16,24,40,.06);
}
.stButton > button:hover, .stDownloadButton > button:hover { border-color: var(--blue); color: var(--blue); }
button[kind="primary"], button[data-testid="stBaseButton-primary"],
[data-testid="stFormSubmitButton"] > button[kind="primary"] { color: #fff !important; border-color: var(--blue); }
button[kind="primary"]:hover, button[data-testid="stBaseButton-primary"]:hover { filter: brightness(1.1); color: #fff !important; }

/* Containers */
[data-testid="stExpander"] { border: 1px solid var(--line); border-radius: 10px; background: var(--card); }
[data-testid="stExpander"] summary { font-weight: 600; }
[data-testid="stForm"] { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 1rem; }
[data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
[data-testid="stAlert"] { border-radius: 10px; }
.stTextInput input, .stNumberInput input, .stTextArea textarea, .stDateInput input { border-radius: 8px; }
div[data-baseweb="select"] > div { border-radius: 8px; }
[data-testid="stChatMessage"] { background: var(--card); border: 1px solid var(--line); border-radius: 12px; }

/* Welcome banner and chips */
.hero { background: linear-gradient(120deg, #0F2A4A 0%, #1F4E8C 100%); border-radius: 14px;
  padding: 26px 30px; margin-bottom: 18px; box-shadow: 0 4px 14px rgba(15,42,74,.18); }
.hero h2 { color: #fff !important; margin: 0 0 6px 0; font-size: 1.55rem; font-weight: 700; border: none; padding: 0; }
.hero p { color: #D6E3F5 !important; margin: 0 0 14px 0; font-size: .95rem; }
.chip { display: inline-block; padding: 3px 11px; border-radius: 999px; font-size: .75rem; font-weight: 600;
  margin: 0 8px 4px 0; border: 1px solid transparent; }
.chip.ok { background: #E3F4E8; color: #1B6B34; }
.chip.warn { background: #FFF3D6; color: #8A5A00; }
.chip.bad { background: #FBE3E3; color: #9B1C1C; }
.chip.info { background: #E6EEF9; color: #1F4E8C; }
.chip.neutral { background: #EEF1F5; color: #4A5A6A; }
.hero .chip { color: #fff; border-color: rgba(255,255,255,.28); background: rgba(255,255,255,.16); }
.hero .chip.ok { background: rgba(76,175,80,.35); }
.hero .chip.warn { background: rgba(255,193,7,.30); }
.hero .chip.bad { background: rgba(244,67,54,.40); }

/* Progress tracker */
.stepper { display: flex; background: var(--card); border: 1px solid var(--line); border-radius: 12px;
  padding: 16px 10px; margin: 6px 0 4px 0; }
.step { flex: 1; text-align: center; position: relative; }
.step:not(:last-child)::after { content: ""; position: absolute; top: 15px; left: calc(50% + 18px);
  right: calc(-50% + 18px); height: 2px; background: var(--line); }
.step.done:not(:last-child)::after { background: var(--teal); }
.dot { width: 30px; height: 30px; border-radius: 50%; margin: 0 auto 6px auto; display: flex;
  align-items: center; justify-content: center; font-weight: 700; font-size: .85rem;
  background: #EEF1F5; color: #6B7A8A; border: 2px solid var(--line); }
.step.done .dot { background: var(--teal); color: #fff; border-color: var(--teal); }
.step.current .dot { background: #fff; color: var(--blue); border-color: var(--blue); box-shadow: 0 0 0 4px rgba(31,78,140,.12); }
.lbl { font-size: .78rem; color: var(--muted); font-weight: 500; line-height: 1.25; padding: 0 4px; }
.step.done .lbl, .step.current .lbl { color: var(--navy); font-weight: 600; }
"""

SIDEBAR_CSS = """
section[data-testid="stSidebar"] { background: linear-gradient(180deg, #0F2A4A 0%, #14385F 100%); border-right: none; }
section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"] { border-radius: 8px; margin: 1px 6px; }
section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"] span { color: #D6E0EE; font-weight: 500; }
section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"]:hover { background: rgba(255,255,255,.08); }
section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-current="page"] { background: rgba(255,255,255,.16); }
section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-current="page"] span { color: #FFFFFF; font-weight: 600; }
section[data-testid="stSidebar"] [data-testid="stNavSectionHeader"] span { color: #8FA6C4; font-size: .7rem;
  text-transform: uppercase; letter-spacing: .08em; font-weight: 600; }
section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p { color: #D6E0EE; }
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h1,
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h2,
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3 { color: #FFFFFF; border: none; }
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] { color: #9FB6D3; }
section[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,.15); }
"""


def apply_theme() -> None:
    css = BASE_CSS + (SIDEBAR_CSS if DARK_SIDEBAR else "")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def chip(text: str, kind: str = "neutral") -> str:
    return f'<span class="chip {escape(kind)}">{escape(str(text))}</span>'


def risk_chip(level: str) -> str:
    return chip(level, {"Low": "ok", "Medium": "warn", "High": "bad"}.get(level, "neutral"))


def hero(title: str, subtitle: str, chips=()) -> None:
    chips_html = "".join(chip(text, kind) for text, kind in chips)
    html = (f'<div class="hero"><h2>{escape(title)}</h2><p>{escape(subtitle)}</p>'
            f'<div>{chips_html}</div></div>')
    st.markdown(html, unsafe_allow_html=True)


def stepper_html(steps) -> str:
    items, current_taken = [], False
    for number, (label, done) in enumerate(steps, start=1):
        if done:
            state, mark = "done", "✓"
        elif not current_taken:
            state, mark, current_taken = "current", str(number), True
        else:
            state, mark = "todo", str(number)
        items.append(f'<div class="step {state}"><div class="dot">{mark}</div>'
                     f'<div class="lbl">{escape(label)}</div></div>')
    return f'<div class="stepper">{"".join(items)}</div>'


def stepper(steps) -> None:
    st.markdown(stepper_html(steps), unsafe_allow_html=True)
