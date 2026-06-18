import asyncio
import base64
import html
import importlib
import inspect
import mimetypes
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st

import src.story_agent as story_agent_module
from src.story_email import get_email_mode
from src.story_mcp import check_gmail_mcp_for_parent_decision
from src.story_storage import log_email_status
from src.story_storage import load_child_profile, save_child_profile

story_agent_module = importlib.reload(story_agent_module)
apply_parent_decision = story_agent_module.apply_parent_decision
generate_story_draft = story_agent_module.generate_story_draft
send_approved_story_now = story_agent_module.send_approved_story_now


st.set_page_config(
    page_title="Daily Story Agent",
    page_icon=None,
    layout="wide",
)

st.markdown(
    """
<style>
  :root {
    --page: #102b2f;
    --surface: #fff8ec;
    --surface-2: #f7dca4;
    --surface-3: #d8edf0;
    --ink: #142126;
    --muted: #52616a;
    --soft: #f3ead6;
    --line: rgba(50, 85, 83, 0.22);
    --teal: #17686e;
    --teal-dark: #0e464d;
    --coral: #d86c59;
    --gold: #e8aa3c;
    --sky: #7ab9c5;
    --rose: #f2b3a7;
    --shadow: 0 20px 54px rgba(10, 31, 36, 0.2);
  }

  * { font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
  .stApp {
    background:
      radial-gradient(circle at 8% 8%, rgba(232, 170, 60, 0.24) 0 12rem, transparent 12.2rem),
      radial-gradient(circle at 92% 16%, rgba(216, 108, 89, 0.2) 0 11rem, transparent 11.2rem),
      linear-gradient(145deg, #12343a 0%, #1f5b5a 42%, #f3d99a 42.2%, #f7efe1 100%);
    color: var(--ink);
  }
  .stApp::before {
    content: "";
    position: fixed;
    inset: 0;
    pointer-events: none;
    background-image: linear-gradient(135deg, rgba(255, 248, 236, 0.13) 25%, transparent 25%),
      linear-gradient(225deg, rgba(255, 248, 236, 0.1) 25%, transparent 25%);
    background-size: 34px 34px;
    mask-image: linear-gradient(to bottom, black 0%, transparent 65%);
  }
  [data-testid="stHeader"] { background: transparent; }
  [data-testid="stMainBlockContainer"] {
    max-width: 1240px;
    padding-top: 0.9rem;
    padding-bottom: 3rem;
  }
  h1, h2, h3 {
    color: var(--ink);
    letter-spacing: 0;
  }
  h1 {
    font-size: 2rem;
    line-height: 1.15;
    margin-bottom: 0.25rem;
  }
  h2, h3 { margin-top: 0; }
  p, label, span, div { color: var(--ink); }
  .app-kicker {
    color: #ffe2a4;
    font-size: 0.78rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-bottom: 0.35rem;
  }
  .app-header {
    position: relative;
    overflow: hidden;
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 1.1rem;
    align-items: center;
    background:
      linear-gradient(135deg, rgba(13, 62, 69, 0.98), rgba(23, 104, 110, 0.94) 55%, rgba(216, 108, 89, 0.92)),
      linear-gradient(90deg, rgba(232, 170, 60, 0.32), rgba(122, 185, 197, 0.24));
    border: 1px solid rgba(255, 248, 236, 0.26);
    border-radius: 8px;
    box-shadow: var(--shadow);
    padding: clamp(1.35rem, 2.4vw, 2.1rem);
    margin-bottom: 1.35rem;
  }
  .app-header::after {
    content: "";
    position: absolute;
    right: -2rem;
    top: -2rem;
    width: 42%;
    height: 100%;
    background:
      repeating-linear-gradient(135deg, rgba(255, 248, 236, 0.18) 0 2px, transparent 2px 16px);
    opacity: 0.9;
  }
  .app-header > * { position: relative; z-index: 1; }
  .app-header h1 {
    color: #fff8ec;
    max-width: 760px;
  }
  .app-subtitle {
    color: rgba(255, 248, 236, 0.86);
    max-width: 780px;
    line-height: 1.55;
    margin: 0.15rem 0 0;
  }
  .hero-motif {
    width: min(17vw, 170px);
    min-width: 118px;
    aspect-ratio: 1.12;
    position: relative;
    justify-self: end;
    filter: drop-shadow(0 18px 28px rgba(5, 25, 28, 0.28));
  }
  .hero-motif::before,
  .hero-motif::after {
    content: "";
    position: absolute;
    bottom: 12%;
    width: 48%;
    height: 62%;
    background: linear-gradient(160deg, #fff8ec, #f7dca4);
    border: 2px solid rgba(14, 70, 77, 0.24);
  }
  .hero-motif::before {
    left: 4%;
    border-radius: 8px 3px 3px 8px;
    transform: rotate(-8deg);
  }
  .hero-motif::after {
    right: 4%;
    border-radius: 3px 8px 8px 3px;
    transform: rotate(8deg);
  }
  .hero-star {
    position: absolute;
    inset: 8% auto auto 38%;
    width: 25%;
    aspect-ratio: 1;
    background: var(--gold);
    clip-path: polygon(50% 0%, 61% 35%, 98% 35%, 68% 56%, 79% 91%, 50% 70%, 21% 91%, 32% 56%, 2% 35%, 39% 35%);
    z-index: 2;
  }
  .hero-line {
    position: absolute;
    z-index: 3;
    left: 23%;
    right: 23%;
    height: 3px;
    border-radius: 999px;
    background: rgba(14, 70, 77, 0.22);
  }
  .hero-line.one { bottom: 41%; transform: rotate(-4deg); }
  .hero-line.two { bottom: 31%; transform: rotate(4deg); }
  .kid-sky {
    position: absolute;
    inset: 0;
    pointer-events: none;
    overflow: hidden;
  }
  .kid-balloon {
    position: absolute;
    top: 18%;
    width: 2.45rem;
    height: 3.1rem;
    border-radius: 52% 52% 48% 48%;
    box-shadow: inset -8px -10px 0 rgba(20, 33, 38, 0.1), 0 12px 20px rgba(10, 31, 36, 0.14);
  }
  .kid-balloon::after {
    content: "";
    position: absolute;
    left: 50%;
    top: 100%;
    width: 1px;
    height: 3.4rem;
    background: rgba(255, 248, 236, 0.58);
  }
  .kid-balloon.one {
    right: 24%;
    background: #f7dca4;
    transform: rotate(-8deg);
  }
  .kid-balloon.two {
    right: 18%;
    top: 30%;
    background: #f2b3a7;
    transform: rotate(7deg);
  }
  .kid-spark {
    position: absolute;
    width: 1.4rem;
    aspect-ratio: 1;
    background: #fff1c7;
    clip-path: polygon(50% 0%, 62% 35%, 98% 35%, 68% 56%, 79% 91%, 50% 70%, 21% 91%, 32% 56%, 2% 35%, 39% 35%);
    opacity: 0.9;
  }
  .kid-spark.one { left: 58%; top: 20%; transform: rotate(14deg); }
  .kid-spark.two { right: 8%; bottom: 18%; width: 1rem; transform: rotate(-18deg); }
  .kid-rainbow {
    position: absolute;
    right: 8%;
    bottom: -2.8rem;
    width: 10rem;
    height: 5rem;
    border-radius: 10rem 10rem 0 0;
    background:
      radial-gradient(ellipse at center bottom, transparent 0 36%, #fff8ec 36% 43%, #7ab9c5 43% 52%, #e8aa3c 52% 61%, #d86c59 61% 70%, transparent 70%);
    opacity: 0.92;
  }
  .kid-play-strip {
    position: relative;
    min-height: 54px;
    margin: -0.55rem 0 0.75rem;
    overflow: hidden;
    border-radius: 8px;
    background:
      linear-gradient(135deg, rgba(255, 248, 236, 0.86), rgba(216, 237, 240, 0.72)),
      repeating-linear-gradient(90deg, rgba(14, 70, 77, 0.05) 0 10px, transparent 10px 20px);
    border: 1px solid rgba(14, 70, 77, 0.12);
    box-shadow: 0 12px 26px rgba(10, 31, 36, 0.12);
  }
  .toy-block {
    position: absolute;
    bottom: 12px;
    width: 30px;
    height: 30px;
    border-radius: 8px;
    box-shadow: inset -6px -7px 0 rgba(20, 33, 38, 0.1), 0 10px 18px rgba(10, 31, 36, 0.12);
  }
  .toy-block.one { left: 24px; background: #d86c59; transform: rotate(-7deg); }
  .toy-block.two { left: 62px; background: #e8aa3c; transform: rotate(4deg); }
  .toy-block.three { left: 100px; background: #7ab9c5; transform: rotate(-3deg); }
  .play-cloud {
    position: absolute;
    right: 34px;
    top: 14px;
    width: 76px;
    height: 24px;
    border-radius: 999px;
    background: rgba(255, 248, 236, 0.95);
    box-shadow:
      -24px 8px 0 -6px rgba(255, 248, 236, 0.95),
      24px 8px 0 -8px rgba(255, 248, 236, 0.95),
      0 10px 18px rgba(10, 31, 36, 0.1);
  }
  .play-pencil {
    position: absolute;
    left: 170px;
    top: 23px;
    width: min(34vw, 420px);
    height: 11px;
    border-radius: 999px;
    background: linear-gradient(90deg, #17686e 0 78%, #f7dca4 78% 90%, #d86c59 90%);
    transform: rotate(-2deg);
    opacity: 0.88;
  }
  .play-sparkle {
    position: absolute;
    width: 20px;
    aspect-ratio: 1;
    background: #e8aa3c;
    clip-path: polygon(50% 0%, 61% 35%, 98% 35%, 68% 56%, 79% 91%, 50% 70%, 21% 91%, 32% 56%, 2% 35%, 39% 35%);
  }
  .play-sparkle.one { right: 160px; top: 16px; transform: rotate(18deg); }
  .play-sparkle.two { right: 220px; bottom: 16px; width: 15px; transform: rotate(-18deg); }
  .panel {
    background: rgba(255, 248, 236, 0.92);
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 1rem;
  }
  .panel-title {
    display: inline-block;
    position: relative;
    font-size: 0.82rem;
    font-weight: 800;
    letter-spacing: 0.06em;
    color: #fff8ec;
    background: rgba(14, 70, 77, 0.84);
    border: 1px solid rgba(255, 248, 236, 0.2);
    border-radius: 999px;
    padding: 0.36rem 0.72rem;
    text-transform: uppercase;
    margin: 0.12rem 0 0.55rem;
  }
  .panel-title::after {
    content: "";
    position: absolute;
    right: -0.55rem;
    top: -0.35rem;
    width: 0.9rem;
    aspect-ratio: 1;
    background: var(--gold);
    clip-path: polygon(50% 0%, 61% 35%, 98% 35%, 68% 56%, 79% 91%, 50% 70%, 21% 91%, 32% 56%, 2% 35%, 39% 35%);
  }
  .section {
    border-top: 1px solid var(--line);
    padding-top: 0.62rem;
    margin-top: 0.62rem;
  }
  .profile-shell {
    background:
      linear-gradient(180deg, rgba(255, 248, 236, 0.96), rgba(255, 241, 199, 0.84)),
      radial-gradient(circle at 92% 8%, rgba(122, 185, 197, 0.3), transparent 34%);
    border: 1px solid rgba(14, 70, 77, 0.18);
    border-radius: 8px;
    padding: 0.72rem;
    box-shadow: 0 16px 34px rgba(10, 31, 36, 0.13);
    margin-bottom: 0.72rem;
    text-align: center;
  }
  .profile-shell .panel-title {
    margin-bottom: 0.35rem;
  }
  .profile-mini-copy {
    color: var(--muted);
    font-size: 0.78rem;
    line-height: 1.35;
    margin: 0 auto 0.55rem;
    max-width: 16rem;
  }
  .profile-section-label {
    display: flex;
    align-items: center;
    gap: 0.38rem;
    color: var(--teal-dark);
    font-size: 0.72rem;
    font-weight: 850;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    margin: 0.56rem 0 0.2rem;
  }
  .profile-section-label::before {
    content: "";
    width: 0.62rem;
    aspect-ratio: 1;
    border-radius: 3px;
    background: var(--coral);
    box-shadow: 0.42rem 0.2rem 0 var(--gold);
  }
  .profile-form-wrap [data-testid="stForm"] {
    background: transparent;
    border: 0;
    box-shadow: none;
    padding: 0;
  }
  .status {
    display: inline-block;
    border: 1px solid var(--line);
    border-radius: 999px;
    padding: 0.28rem 0.78rem;
    color: #0c3b40;
    background: #d8edf0;
    font-size: 0.82rem;
    font-weight: 700;
    box-shadow: 0 8px 18px rgba(47, 89, 68, 0.08);
  }
  .chip-row {
    display: flex;
    flex-wrap: wrap;
    gap: 0.45rem;
    margin: 0.8rem 0 1rem;
  }
  .chip {
    border: 1px solid rgba(14, 70, 77, 0.14);
    background: linear-gradient(135deg, #fff1c7, #d8edf0);
    border-radius: 999px;
    padding: 0.34rem 0.68rem;
    color: #45525d;
    font-size: 0.78rem;
    font-weight: 720;
  }
  .story-box {
    position: relative;
    background:
      linear-gradient(90deg, rgba(232, 170, 60, 0.18), transparent 26%),
      var(--surface);
    border: 1px solid rgba(47, 89, 68, 0.16);
    border-radius: 8px;
    padding: clamp(1.2rem, 2vw, 2rem);
    line-height: 1.72;
    color: var(--ink);
    box-shadow: var(--shadow);
  }
  .story-box::after {
    content: "";
    position: absolute;
    right: 1rem;
    top: 1rem;
    width: 4.2rem;
    height: 2.6rem;
    border-radius: 999px;
    background: rgba(216, 237, 240, 0.72);
    box-shadow:
      -1.3rem 0.45rem 0 -0.55rem rgba(216, 237, 240, 0.86),
      1.2rem 0.55rem 0 -0.65rem rgba(216, 237, 240, 0.86);
    pointer-events: none;
  }
  .story-box::before {
    content: "";
    position: absolute;
    inset: 0.7rem;
    border: 1px solid rgba(182, 135, 50, 0.12);
    border-radius: 8px;
    pointer-events: none;
  }
  .story-box h2 {
    position: relative;
    font-size: 1.6rem;
    margin: 0 0 0.8rem;
    color: var(--teal-dark);
  }
  .story-layout {
    position: relative;
    display: grid;
    grid-template-columns: minmax(150px, 0.28fr) minmax(0, 1fr);
    gap: clamp(1rem, 2vw, 1.45rem);
    align-items: start;
  }
  .story-layout.no-image {
    grid-template-columns: 1fr;
  }
  .story-illustration {
    margin: 0;
    max-width: 230px;
    border-radius: 8px;
    overflow: hidden;
    background: linear-gradient(135deg, #d8edf0, #fff1c7);
    border: 1px solid rgba(14, 70, 77, 0.15);
    box-shadow: 0 14px 28px rgba(10, 31, 36, 0.14);
  }
  .story-illustration img {
    display: block;
    width: 100%;
    aspect-ratio: 1;
    object-fit: cover;
  }
  .illustration-status {
    position: relative;
    color: var(--muted);
    font-size: 0.82rem;
    margin-bottom: 0.65rem;
  }
  .story-text {
    position: relative;
    font-size: 1.03rem;
    line-height: 1.78;
  }
  .parent-note {
    position: relative;
    border-top: 1px solid var(--line);
    margin-top: 1.1rem;
    padding-top: 0.85rem;
    color: var(--muted);
    font-size: 0.93rem;
  }
  .empty-state {
    min-height: 430px;
    border: 1px dashed rgba(255, 248, 236, 0.55);
    border-radius: 8px;
    background:
      linear-gradient(135deg, rgba(14, 70, 77, 0.94), rgba(216, 108, 89, 0.82)),
      repeating-linear-gradient(135deg, rgba(255, 248, 236, 0.14) 0 2px, transparent 2px 18px);
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;
    padding: 2rem;
    box-shadow: inset 0 0 0 10px rgba(255, 248, 236, 0.08), var(--shadow);
  }
  .empty-state::before {
    content: "";
    position: absolute;
    top: 2.2rem;
    right: 2.3rem;
    width: 5.4rem;
    height: 5.4rem;
    border-radius: 50%;
    background:
      radial-gradient(circle at 34% 34%, #fff8ec 0 10%, transparent 10.5%),
      radial-gradient(circle, #e8aa3c 0 52%, transparent 53%);
    box-shadow: 0 0 0 10px rgba(232, 170, 60, 0.18);
  }
  .empty-state::after {
    content: "";
    position: absolute;
    left: 2.1rem;
    bottom: 2.1rem;
    width: 6.6rem;
    height: 4.6rem;
    background:
      linear-gradient(160deg, #fff8ec 0 48%, #f7dca4 48% 100%);
    border: 2px solid rgba(255, 248, 236, 0.42);
    border-radius: 8px;
    transform: rotate(-8deg);
    box-shadow: 3.4rem 0.7rem 0 -0.2rem rgba(216, 108, 89, 0.78);
  }
  .empty-state h2 {
    font-size: 1.55rem;
    margin-bottom: 0.35rem;
    color: #fff8ec;
  }
  .empty-state p {
    color: rgba(255, 248, 236, 0.82);
    max-width: 420px;
    margin: 0 auto;
  }
  .decision-band {
    background: linear-gradient(135deg, #ffe7a6, #d8edf0);
    border: 1px solid rgba(216, 108, 89, 0.28);
    border-radius: 8px;
    padding: 1rem;
    margin-top: 1rem;
    box-shadow: 0 12px 28px rgba(45, 61, 49, 0.08);
  }
  .decision-title {
    font-size: 1rem;
    font-weight: 800;
    margin-bottom: 0.25rem;
  }
  .decision-copy {
    color: var(--muted);
    margin-bottom: 0.8rem;
  }
  [data-testid="stMetric"] {
    background: rgba(255, 248, 236, 0.88);
    border: 1px solid rgba(23, 104, 110, 0.16);
    border-radius: 8px;
    padding: 0.65rem 0.75rem;
    box-shadow: 0 10px 22px rgba(45, 61, 49, 0.06);
  }
  [data-testid="stMetricLabel"] p {
    color: var(--muted);
    font-size: 0.75rem;
    font-weight: 750;
  }
  [data-testid="stMetricValue"] {
    color: var(--ink);
    font-size: 1.02rem;
    font-weight: 820;
  }
  .stButton > button,
  .stFormSubmitButton > button {
    min-height: 2.25rem;
    border-radius: 8px !important;
    font-weight: 750 !important;
    border: 1px solid var(--line) !important;
  }
  button[data-testid="baseButton-primary"] {
    background: linear-gradient(135deg, var(--coral), #b9493e) !important;
    border-color: var(--coral) !important;
    color: #ffffff !important;
    box-shadow: 0 12px 24px rgba(216, 108, 89, 0.28) !important;
  }
  button[data-testid="baseButton-primary"]:hover {
    background: #b9493e !important;
    border-color: #b9493e !important;
  }
  button[data-testid="baseButton-secondary"] {
    background: #fff8ec !important;
    color: var(--ink) !important;
  }
  button[data-testid="baseButton-secondary"]:hover {
    border-color: var(--teal) !important;
    color: var(--teal-dark) !important;
  }
  [data-testid="stTextInput"] input,
  [data-testid="stTextArea"] textarea,
  [data-testid="stSelectbox"] div[data-baseweb="select"] > div,
  [data-testid="stNumberInput"] input {
    background: rgba(255, 248, 236, 0.98) !important;
    border-color: rgba(23, 104, 110, 0.24) !important;
    color: var(--ink) !important;
    border-radius: 8px !important;
  }
  [data-testid="stTextInput"] input:focus,
  [data-testid="stTextArea"] textarea:focus,
  [data-testid="stNumberInput"] input:focus {
    border-color: var(--coral) !important;
    box-shadow: 0 0 0 2px rgba(216, 108, 89, 0.12) !important;
  }
  [data-testid="stTextInput"],
  [data-testid="stTextArea"],
  [data-testid="stSelectbox"],
  [data-testid="stNumberInput"] {
    margin-bottom: -0.35rem;
  }
  [data-testid="stTextInput"] input,
  [data-testid="stNumberInput"] input {
    min-height: 2.1rem !important;
  }
  [data-testid="stTextArea"] textarea {
    min-height: 3rem !important;
    max-height: 3.8rem !important;
  }
  [data-testid="stSelectbox"] div[data-baseweb="select"] > div {
    min-height: 2.1rem !important;
  }
  [data-testid="stForm"] label p,
  [data-testid="stForm"] label {
    font-size: 0.82rem !important;
  }
  [data-testid="stForm"] {
    background: linear-gradient(180deg, rgba(255, 248, 236, 0.95), rgba(255, 241, 199, 0.82));
    border: 1px solid rgba(14, 70, 77, 0.16);
    border-radius: 8px;
    padding: 0.72rem;
    box-shadow: 0 14px 30px rgba(45, 61, 49, 0.08);
  }
  [data-testid="stAlert"] {
    border-radius: 8px;
  }
  [data-testid="stCaptionContainer"] {
    margin-bottom: -0.35rem;
  }
  @media (max-width: 900px) {
    [data-testid="stMainBlockContainer"] { padding-left: 1rem; padding-right: 1rem; }
    .app-header { grid-template-columns: 1fr; }
    .hero-motif { display: none; }
    .kid-play-strip { min-height: 58px; }
    .play-pencil { left: 150px; width: 38vw; }
    .play-cloud { right: 18px; transform: scale(0.78); transform-origin: right top; }
    .toy-block { width: 30px; height: 30px; bottom: 14px; }
    .toy-block.two { left: 58px; }
    .toy-block.three { left: 92px; }
    h1 { font-size: 1.65rem; }
    .story-layout { grid-template-columns: 1fr; }
    .story-illustration { max-width: 260px; }
    .story-illustration img { max-height: 260px; }
  }
</style>
""",
    unsafe_allow_html=True,
)


def _split_csv(value):
    if isinstance(value, list):
        value = ", ".join(value)
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _profile_validation_errors(profile):
    errors = []
    required_text_fields = {
        "Child name": profile.get("child_name"),
        "Gender": profile.get("gender"),
        "Interests": profile.get("interests"),
        "Favorite character types": profile.get("favorite_characters"),
        "Parent goals": profile.get("parent_goals"),
        "Topics to avoid": profile.get("topics_to_avoid"),
        "Parent email": profile.get("parent_email"),
        "Preferred story time": profile.get("preferred_story_time"),
    }
    for label, value in required_text_fields.items():
        if isinstance(value, list):
            is_missing = not any(str(item).strip() for item in value)
        else:
            is_missing = not str(value or "").strip()
        if is_missing:
            errors.append(f"{label} is required.")

    parent_email = str(profile.get("parent_email", "")).strip()
    if parent_email and ("@" not in parent_email or "." not in parent_email.split("@")[-1]):
        errors.append("Parent email must be a valid email address.")

    return errors


def _image_src_from_path(image_path):
    path = Path(image_path or "")
    if not path.exists():
        return ""
    mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _story_illustration_html(state):
    image_path = state.get("illustration_path")
    image_url = state.get("illustration_url")
    image_status = state.get("illustration_status", "")
    image_source = state.get("illustration_result", {}).get("source", "")

    status_html = ""
    if image_status:
        status_text = image_status.replace("_", " ").title()
        if image_source:
            status_text = f"{status_text} via {image_source.replace('_', ' ')}"
        status_html = f'<div class="illustration-status">Illustration: {html.escape(status_text)}</div>'

    image_src = ""
    if image_path and Path(image_path).exists():
        image_src = _image_src_from_path(image_path)
    if image_url:
        image_src = image_url

    if image_src:
        return (
            status_html
            + '<figure class="story-illustration">'
            + f'<img src="{html.escape(image_src, quote=True)}" alt="Story illustration" />'
            + '</figure>'
        )

    if image_status == "failed":
        reason = state.get("illustration_error") or "No image was returned."
        return status_html + f'<div class="illustration-status">Illustration failed: {html.escape(reason)}</div>'
    if image_status == "skipped":
        return status_html + '<div class="illustration-status">Illustration was skipped.</div>'
    if image_status:
        return status_html + '<div class="illustration-status">Illustration completed, but no image was returned.</div>'
    return ""


def _render_html(markup):
    if hasattr(st, "html"):
        st.html(markup)
    else:
        st.markdown(markup, unsafe_allow_html=True)


def _apply_approval(state, include_audio):
    return send_approved_story_now(state, include_audio=include_audio)


def _approval_error_state(state, exc):
    result = {
        "status": "failed",
        "message": f"{type(exc).__name__}: {exc}",
        "story_id": state.get("story_id", ""),
        "stage": "approve_and_send",
    }
    log_email_status(result)
    return {
        **state,
        "status": "email_failed",
        "email_status": "failed",
        "email_result": result,
    }


if "story_state" not in st.session_state:
    st.session_state.story_state = None
if "include_audio_option" not in st.session_state:
    st.session_state.include_audio_option = False

_render_html(
    """
<div class="app-header">
  <div class="kid-sky" aria-hidden="true">
    <span class="kid-balloon one"></span>
    <span class="kid-balloon two"></span>
    <span class="kid-spark one"></span>
    <span class="kid-spark two"></span>
    <span class="kid-rainbow"></span>
  </div>
  <div>
    <div class="app-kicker">Parent approval workflow</div>
    <h1>Daily Personalized Children's Story Agent</h1>
    <p class="app-subtitle">
      Create one thoughtful story at a time, check it against your child's profile and recent history,
      then pause for approval before anything is sent.
    </p>
  </div>
  <div class="hero-motif" aria-hidden="true">
    <span class="hero-star"></span>
    <span class="hero-line one"></span>
    <span class="hero-line two"></span>
  </div>
</div>
""",
)

_render_html(
    """
<div class="kid-play-strip" aria-hidden="true">
  <span class="toy-block one"></span>
  <span class="toy-block two"></span>
  <span class="toy-block three"></span>
  <span class="play-pencil"></span>
  <span class="play-cloud"></span>
  <span class="play-sparkle one"></span>
  <span class="play-sparkle two"></span>
</div>
""",
)

email_mode = get_email_mode()
email_mode_label = email_mode.replace("_", " ").title()

left, right = st.columns([0.28, 0.72], gap="large")

with left:
    profile = load_child_profile("demo-child")
    _render_html(
        """
<div class="profile-shell">
  <div class="panel-title">Child Profile</div>
  <p class="profile-mini-copy">Keep the profile short and specific so each story feels personal.</p>
</div>
"""
    )

    with st.form("profile_form"):
        _render_html('<div class="profile-section-label">Basics</div>')
        child_name = st.text_input("Child name *", value=profile.get("child_name", ""))
        age = st.number_input("Age *", min_value=2, max_value=12, value=int(profile.get("age", 6)))
        gender_options = ["girl", "boy", "prefer not to say"]
        saved_gender = profile.get("gender", "prefer not to say")
        gender = st.selectbox(
            "Gender *",
            gender_options,
            index=gender_options.index(saved_gender) if saved_gender in gender_options else 2,
        )
        reading_level = st.selectbox(
            "Reading level *",
            ["beginner", "early reader", "independent reader"],
            index=["beginner", "early reader", "independent reader"].index(
                profile.get("reading_level", "beginner")
                if profile.get("reading_level", "beginner") in ["beginner", "early reader", "independent reader"]
                else "beginner"
            ),
        )
        _render_html('<div class="profile-section-label">Story Ingredients</div>')
        interests = st.text_area("Interests *", value=", ".join(profile.get("interests", [])), height=54)
        favorite_characters = st.text_area(
            "Favorite character types *",
            value=", ".join(profile.get("favorite_characters", [])),
            help="Use character types or inspirations. For example, Elsa will be treated as a snow princess rather than a copyrighted character name.",
            height=54,
        )
        _render_html('<div class="profile-section-label">Parent Guidance</div>')
        parent_goals = st.text_area("Parent goals *", value=", ".join(profile.get("parent_goals", [])), height=54)
        topics_to_avoid = st.text_area("Topics to avoid *", value=", ".join(profile.get("topics_to_avoid", [])), height=54)
        parent_email = st.text_input("Parent email *", value=profile.get("parent_email", ""))
        preferred_story_time = st.text_input(
            "Preferred story time *",
            value=profile.get("preferred_story_time", "8:30 PM"),
        )

        saved = st.form_submit_button("Save Profile", use_container_width=True)
        if saved:
            profile_payload = {
                "child_id": "demo-child",
                "child_name": child_name.strip(),
                "age": int(age),
                "gender": gender,
                "reading_level": reading_level,
                "interests": _split_csv(interests),
                "favorite_characters": _split_csv(favorite_characters),
                "parent_goals": _split_csv(parent_goals),
                "topics_to_avoid": _split_csv(topics_to_avoid),
                "parent_email": parent_email.strip(),
                "preferred_story_time": preferred_story_time.strip(),
            }
            errors = _profile_validation_errors(profile_payload)
            if errors:
                st.error(" ".join(errors))
            else:
                save_child_profile(profile_payload)
                st.success("Profile saved.")
    selected_theme = st.selectbox(
        "Theme *",
        [
            "",
            "kindness",
            "confidence",
            "patience",
            "sharing",
            "bedtime routine",
            "school courage",
            "screen-time balance",
        ],
        help="Required for this demo run.",
    )
    include_audio_option = st.checkbox(
        "Include audio narration",
        value=st.session_state.include_audio_option,
        help="If selected, ElevenLabs creates an MP3 version and attaches it to the email after approval.",
    )
    st.session_state.include_audio_option = include_audio_option
    if st.button("Generate Today's Story", type="primary", use_container_width=True):
        current_profile = load_child_profile("demo-child")
        profile_errors = _profile_validation_errors(current_profile)
        if not selected_theme:
            st.error("Theme is required.")
        elif profile_errors:
            st.error("Save a complete child profile first. " + " ".join(profile_errors))
        else:
            with st.spinner("The agent is loading profile, checking history, choosing a theme, and drafting a story..."):
                st.session_state.story_state = generate_story_draft(
                    "demo-child",
                    selected_theme=selected_theme,
                )
            st.rerun()

with right:
    state = st.session_state.story_state
    if not state:
        _render_html(
            """
<div class="empty-state">
  <div>
    <h2>Story review will appear here</h2>
    <p>Save the child profile, choose an optional theme, and generate today's story.
    The agent will stop here for parent review before sending.</p>
  </div>
</div>
""",
        )
    else:
        status_label = state.get("status", "unknown").replace("_", " ").title()
        _render_html(f'<span class="status">{html.escape(status_label)}</span>')

        meta_cols = st.columns(4)
        meta_cols[0].metric("Theme", state.get("selected_theme", ""))
        meta_cols[1].metric("Retries", state.get("retry_count", 0))
        meta_cols[2].metric("Email", state.get("email_status", "pending"))
        meta_cols[3].metric("Story ID", state.get("story_id", ""))

        if state.get("validation_issues"):
            st.warning("Validation notes: " + " ".join(state["validation_issues"]))
        if state.get("generation_source") == "local_fallback":
            st.warning("The AI provider could not generate this draft, so a local fallback story was used. Check the Nebius API key and model name in `.env`.")
        if state.get("approval_reason"):
            st.info(state["approval_reason"])

        chips = [
            f"Theme: {state.get('selected_theme', 'auto')}",
            f"Gender: {state.get('child_profile', {}).get('gender', '')}",
            f"Reading level: {state.get('child_profile', {}).get('reading_level', '')}",
            f"Setting: {state.get('setting', '')}",
            f"Characters: {', '.join(state.get('characters', [])[:3])}",
        ]
        chip_html = "".join(f'<span class="chip">{html.escape(chip)}</span>' for chip in chips if chip.strip(": "))
        story_title = html.escape(state.get("story_title", "Today's Story"))
        story_text = html.escape(state.get("story_text", "")).replace("\n", "<br>")
        parent_note = html.escape(state.get("parent_note", ""))
        illustration_html = _story_illustration_html(state)
        story_layout_class = "story-layout" if illustration_html else "story-layout no-image"

        _render_html(
            f"""
<div class="chip-row">{chip_html}</div>
""",
        )
        _render_html(
            f"""
<div class="story-box">
  <h2>{story_title}</h2>
  <div class="{story_layout_class}">
    {illustration_html}
    <div class="story-copy">
      <div class="story-text">{story_text}</div>
    </div>
  </div>
  <div class="parent-note"><strong>Parent note:</strong> {parent_note}</div>
</div>
""",
        )

        if state.get("status") == "awaiting_parent_approval":
            _render_html(
                """
<div class="decision-band">
  <div class="decision-title">Parent decision required</div>
  <div class="decision-copy">Approve the story, request a revision, or skip today's email.</div>
</div>
""",
            )
            include_audio = st.session_state.get("include_audio_option", False)
            if include_audio:
                st.info("Audio narration will be attached when you approve and send.")

            approve_col, reject_col = st.columns(2)
            with approve_col:
                if st.button("Approve and Send", type="primary", use_container_width=True):
                    with st.spinner("Generating the required illustration, then preparing PDF, optional audio, and email..."):
                        try:
                            st.session_state.story_state = _apply_approval(state, include_audio)
                        except Exception as exc:
                            st.session_state.story_state = _approval_error_state(state, exc)
                    st.rerun()
            with reject_col:
                if st.button("Reject / Skip Today", use_container_width=True):
                    st.session_state.story_state = apply_parent_decision(state, "reject")
                    st.rerun()

            with st.form("revision_form"):
                feedback = st.text_area(
                    "Revision feedback",
                    placeholder="Example: Make it shorter and include soccer.",
                )
                revise = st.form_submit_button("Request Revision", use_container_width=True)
                if revise:
                    if not feedback.strip():
                        st.error("Please add revision feedback.")
                    else:
                        with st.spinner("Revising story and validating again..."):
                            st.session_state.story_state = apply_parent_decision(state, "revise", feedback.strip())
                        st.rerun()

            if os.getenv("STORY_AGENT_MCP_URL"):
                if st.button("Check Gmail MCP for Approval Reply", use_container_width=True):
                    with st.spinner("Calling existing Gmail MCP tools..."):
                        decision = asyncio.run(check_gmail_mcp_for_parent_decision(state["story_id"]))
                    if decision:
                        st.session_state.story_state = apply_parent_decision(
                            state,
                            decision["decision"],
                            decision.get("feedback", ""),
                        )
                        st.rerun()
                    else:
                        st.info("No Gmail approval reply found yet.")

        elif state.get("status") == "completed":
            result = state.get("email_result", {})
            st.success(result.get("message", "Story workflow completed."))
            if state.get("story_pdf_path"):
                st.info(f"PDF attached: {state['story_pdf_path']}")
            if state.get("audio_path"):
                st.info(f"Audio attached: {state['audio_path']}")
            elif state.get("audio_status") == "skipped":
                st.warning("Audio narration was requested, but ElevenLabs is not configured.")
            elif state.get("audio_status") == "failed":
                reason = state.get("audio_result", {}).get("reason", "ElevenLabs audio generation failed.")
                st.warning(f"Audio narration failed, but the email was still sent: {reason}")
            st.json(result)
        elif state.get("status") == "rejected_by_parent":
            st.warning("Story was rejected by the parent. No email was sent.")
        elif state.get("status") == "email_failed":
            st.error(state.get("email_result", {}).get("message", "Email failed."))
