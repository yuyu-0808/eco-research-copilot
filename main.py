"""Eco-Research Copilot · 多智能体投研咨询深度报告工作台

浅色 · 专业数据工具风 SaaS 前端。
运行方式：streamlit run main.py
"""
import os
import re
import threading
from datetime import datetime

import streamlit as st

from src.utils.config import Config
from src.utils.checkpoint import Checkpoint, PauseRequested
from src.orchestrator import ResearchOrchestrator
from src.ui.helpers import (
    PROJECTS_DIR,
    dashboard_metrics,
    current_round,
    derive_stages,
    fmt_duration,
    html_escape,
    list_projects,
    load_result,
    read_log,
    save_result,
)
from src.ui.charts import chart_to_spec, extract_headings, split_report, table_to_html

# ======================================================================
# 全局样式（设计系统）
# ======================================================================
CSS = r"""<style>
@import url("https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Sora:wght@500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap");

:root {
  --bg: #F4F5F7;
  --surface: #FFFFFF;
  --surface-2: #F7F8FA;
  --ink: #171C28;
  --text: #3C4352;
  --muted: #6A7180;
  --faint: #98A0AE;
  --border: #E6E8EC;
  --border-strong: #D2D6DC;
  --brand: #3A49C4;
  --brand-ink: #2C389C;
  --brand-soft: #ECEFFB;
  --brand-ring: rgba(58,73,196,.18);
  --gold: #B8963E;
  --success: #15875A;
  --success-soft: #E7F5EE;
  --warning: #C07E18;
  --warning-soft: #FBF1E2;
  --danger: #C84052;
  --danger-soft: #FBECEF;
  --shadow-sm: 0 1px 2px rgba(23,28,40,.05), 0 1px 3px rgba(23,28,40,.04);
  --shadow-md: 0 8px 24px rgba(23,28,40,.07), 0 2px 6px rgba(23,28,40,.05);
  --hero-a: rgba(58,73,196,.05);
  --hero-b: rgba(58,73,196,.035);
  --console-bg: #151A28;
  --console-fg: #C6CBE0;
  --console-agent: #8B93B8;
  --abstract-top: #F3F5FC;
  --abstract-bot: #F9FAFD;
  --abstract-border: #E2E6F4;
}

[data-theme="dark"] {
  --bg: #0E111A;
  --surface: #161A2C;
  --surface-2: #1C2138;
  --ink: #E6E9F2;
  --text: #C4CADE;
  --muted: #8B92AE;
  --faint: #5F6582;
  --border: #262C45;
  --border-strong: #353C5C;
  --brand: #5F6CDB;
  --brand-ink: #4A55C8;
  --brand-soft: rgba(95,108,219,.20);
  --brand-ring: rgba(95,108,219,.35);
  --gold: #C9A85B;
  --success: #2EB97E;
  --success-soft: rgba(46,185,126,.18);
  --warning: #E5A43A;
  --warning-soft: rgba(229,164,58,.18);
  --danger: #F06B7F;
  --danger-soft: rgba(240,107,127,.18);
  --shadow-sm: 0 1px 2px rgba(0,0,0,.4);
  --shadow-md: 0 8px 24px rgba(0,0,0,.5);
  --hero-a: rgba(110,120,238,.14);
  --hero-b: rgba(110,120,238,.08);
  --console-bg: #06080F;
  --console-fg: #D4D9EE;
  --console-agent: #5F6582;
  --abstract-top: rgba(110,120,238,.12);
  --abstract-bot: rgba(110,120,238,.04);
  --abstract-border: rgba(110,120,238,.28);
}

html, body, [class*="css"] { font-family: "Plus Jakarta Sans","PingFang SC","HarmonyOS Sans SC","Microsoft YaHei","Segoe UI",-apple-system,sans-serif; }

.stApp {
  background:
    radial-gradient(1200px 500px at 85% -10%, var(--hero-a), transparent 60%),
    radial-gradient(900px 420px at -10% 0%, var(--hero-b), transparent 55%),
    var(--bg);
  color: var(--text);
}

#MainMenu, footer { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stHeader"] svg, [data-testid="stHeader"] button { color: var(--ink) !important; fill: var(--ink) !important; }
/* 隐藏右上角 Deploy 按钮（Streamlit 默认一键部署入口，对内部/面试场景是干扰） */
[data-testid="stBaseButton-header"]:not([data-testid="stMainMenuButton"]) { display:none !important; }
/* Expander 箭头图标更精致 */
[data-testid="stExpander"] summary svg { width: 16px; height: 16px; color: var(--muted); }
/* Pipeline 窄屏处理（防止 flex 节点拥挤） */
@media (max-width: 760px){
  .pipeline { flex-direction: column; gap: 8px; }
  .pipeline .stage + .stage { margin-left: 0; }
  .pipeline .stage:not(:last-child)::after, .pipeline .stage:not(:last-child)::before { display:none; }
}

.block-container { max-width: 1180px; padding-top: 1.4rem; padding-bottom: 4rem; }

[data-testid="stSidebar"] { background: var(--surface); border-right: 1px solid var(--border); }
[data-testid="stSidebar"] > div:first-child { padding: 1.1rem 1rem; }
[data-testid="stSidebar"] .block-container { padding: 0.4rem 0.6rem; }

.brand { display:flex; align-items:center; gap:.72rem; padding:.2rem .45rem 1.2rem; margin-bottom:.75rem; border-bottom:1px solid var(--border); }
.brand-mark { width:38px; height:38px; border-radius:11px; background:linear-gradient(135deg,var(--brand),var(--brand-ink)); display:grid; place-items:center; color:#fff; box-shadow:0 4px 12px var(--brand-ring); font-weight:800; font-size:16px; }
.brand-name { font-weight:800; font-size:15px; color:var(--ink); letter-spacing:-.01em; line-height:1.2; }
.brand-sub { font-size:11px; color:var(--muted); margin-top:2px; letter-spacing:.01em; }

.side-label { font-size:11px; font-weight:700; letter-spacing:.09em; text-transform:uppercase; color:var(--faint); margin:1rem .65rem .45rem; }
[data-testid="stSidebar"] div[role="radiogroup"] { display:flex; flex-direction:column; gap:4px; }
[data-testid="stSidebar"] div[role="radiogroup"] label { display:flex; align-items:center; padding:.68rem .78rem; border-radius:11px; margin:0; font-weight:600; font-size:14px; color:var(--muted); cursor:pointer; transition:all .16s var(--ease); border:1px solid transparent; }
[data-testid="stSidebar"] div[role="radiogroup"] label > div > div > div:first-child { display:none !important; }
[data-testid="stSidebar"] div[role="radiogroup"] label [data-testid="stMarkdownContainer"] p { display:flex; align-items:center; margin:0; gap:.65rem; }
[data-testid="stSidebar"] div[role="radiogroup"] label:hover { background:var(--surface-2); color:var(--ink); }
[data-testid="stSidebar"] div[role="radiogroup"] label[data-selected="true"] { background:var(--brand-soft); color:var(--brand-ink); font-weight:700; }
[data-testid="stSidebar"] div[role="radiogroup"] label [data-testid="stMarkdownContainer"] p::before {
  content:""; display:inline-block; width:18px; height:18px; margin-right:10px; flex-shrink:0;
  background: currentColor;
  -webkit-mask: var(--nav-icon) center/contain no-repeat;
  mask: var(--nav-icon) center/contain no-repeat;
}
[data-testid="stSidebar"] div[role="radiogroup"] label:nth-child(1) [data-testid="stMarkdownContainer"] p { --nav-icon: url("data:image/svg+xml,%3Csvg%20xmlns%3D%27http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%27%20viewBox%3D%270%200%2024%2024%27%3E%3Cg%20fill%3D%27none%27%20stroke%3D%27black%27%20stroke-width%3D%271.8%27%20stroke-linecap%3D%27round%27%20stroke-linejoin%3D%27round%27%3E%3Crect%20x%3D%273%27%20y%3D%273%27%20width%3D%277%27%20height%3D%277%27%20rx%3D%271.5%27%2F%3E%3Crect%20x%3D%2714%27%20y%3D%273%27%20width%3D%277%27%20height%3D%277%27%20rx%3D%271.5%27%2F%3E%3Crect%20x%3D%273%27%20y%3D%2714%27%20width%3D%277%27%20height%3D%277%27%20rx%3D%271.5%27%2F%3E%3Crect%20x%3D%2714%27%20y%3D%2714%27%20width%3D%277%27%20height%3D%277%27%20rx%3D%271.5%27%2F%3E%3C%2Fg%3E%3C%2Fsvg%3E"); }
[data-testid="stSidebar"] div[role="radiogroup"] label:nth-child(2) [data-testid="stMarkdownContainer"] p { --nav-icon: url("data:image/svg+xml,%3Csvg%20xmlns%3D%27http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%27%20viewBox%3D%270%200%2024%2024%27%3E%3Cpath%20fill%3D%27none%27%20stroke%3D%27black%27%20stroke-width%3D%271.8%27%20stroke-linecap%3D%27round%27%20d%3D%27M12%205v14M5%2012h14%27%2F%3E%3C%2Fsvg%3E"); }
[data-testid="stSidebar"] div[role="radiogroup"] label:nth-child(3) [data-testid="stMarkdownContainer"] p { --nav-icon: url("data:image/svg+xml,%3Csvg%20xmlns%3D%27http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%27%20viewBox%3D%270%200%2024%2024%27%3E%3Cg%20fill%3D%27none%27%20stroke%3D%27black%27%20stroke-width%3D%271.8%27%20stroke-linecap%3D%27round%27%20stroke-linejoin%3D%27round%27%3E%3Ccircle%20cx%3D%2712%27%20cy%3D%2712%27%20r%3D%279%27%2F%3E%3Cpath%20d%3D%27M12%207v5l3%202%27%2F%3E%3C%2Fg%3E%3C%2Fsvg%3E"); }
[data-testid="stSidebar"] div[role="radiogroup"] label:nth-child(4) [data-testid="stMarkdownContainer"] p { --nav-icon: url("data:image/svg+xml,%3Csvg%20xmlns%3D%27http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%27%20viewBox%3D%270%200%2024%2024%27%3E%3Cg%20fill%3D%27none%27%20stroke%3D%27black%27%20stroke-width%3D%271.8%27%20stroke-linecap%3D%27round%27%20stroke-linejoin%3D%27round%27%3E%3Ccircle%20cx%3D%2712%27%20cy%3D%2712%27%20r%3D%273%27%2F%3E%3Cpath%20d%3D%27M19.4%2015a1.65%201.65%200%200%200%20.33%201.82l.06.06a2%202%200%201%201-2.83%202.83l-.06-.06a1.65%201.65%200%200%200-1.82-.33%201.65%201.65%200%200%200-1%201.51V21a2%202%200%201%201-4%200v-.09a1.65%201.65%200%200%200-1-1.51%201.65%201.65%200%200%200-1.82.33l-.06.06a2%202%200%201%201-2.83-2.83l.06-.06a1.65%201.65%200%200%200%20.33-1.82%201.65%201.65%200%200%200-1.51-1H3a2%202%200%201%201%200-4h.09a1.65%201.65%200%200%200%201.51-1%201.65%201.65%200%200%200-.33-1.82l-.06-.06a2%202%200%201%201%202.83-2.83l.06.06a1.65%201.65%200%200%200%201.82.33H9a1.65%201.65%200%200%200%201-1.51V3a2%202%200%201%201%204%200v.09a1.65%201.65%200%200%200%201%201.51%201.65%201.65%200%200%200%201.82-.33l.06-.06a2%202%200%201%201%202.83%202.83l-.06.06a1.65%201.65%200%200%200-.33%201.82V9a1.65%201.65%200%200%200%201.51%201H21a2%202%200%201%201%200%204h-.09a1.65%201.65%200%200%200-1.51%201z%27%2F%3E%3C%2Fg%3E%3C%2Fsvg%3E"); }
[data-testid="stSidebar"] div[role="radiogroup"] label:nth-child(5) [data-testid="stMarkdownContainer"] p { --nav-icon: url("data:image/svg+xml,%3Csvg%20xmlns%3D%27http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%27%20viewBox%3D%270%200%2024%2024%27%3E%3Cg%20fill%3D%27none%27%20stroke%3D%27black%27%20stroke-width%3D%271.8%27%20stroke-linecap%3D%27round%27%20stroke-linejoin%3D%27round%27%3E%3Cpath%20d%3D%27M14%203H7a2%202%200%200%200-2%202v14a2%202%200%200%200%202%202h10a2%202%200%200%200%202-2V8z%27%2F%3E%3Cpath%20d%3D%27M14%203v5h5%27%2F%3E%3Cpath%20d%3D%27M9%2013h6M9%2017h4%27%2F%3E%3C%2Fg%3E%3C%2Fsvg%3E"); }

.stButton > button, .stDownloadButton > button, [data-testid="stBaseButton-secondary"] {
  border-radius:10px; font-weight:600; font-size:14px;
  border:1px solid var(--border-strong); background:var(--surface); color:var(--text);
  padding:.5rem 1.1rem; transition:all .16s var(--ease); box-shadow:none;
}
.stButton > button:hover, .stDownloadButton > button:hover {
  border-color:var(--brand); color:var(--brand); background:var(--brand-soft); transform:translateY(-1px);
}
.stButton > button[kind="primary"], [data-testid="stBaseButton-primary"] {
  background:linear-gradient(135deg,var(--brand),var(--brand-ink)); color:#fff; border:none;
  box-shadow:0 6px 16px var(--brand-ring);
}
.stButton > button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover {
  filter:brightness(1.05); transform:translateY(-1px); box-shadow:0 8px 22px var(--brand-ring);
}

[data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea {
  border-radius:10px; border:1px solid var(--border-strong); background:var(--surface);
  color:var(--ink); padding:.55rem .8rem; font-size:15px;
}
[data-testid="stTextInput"] input:focus, [data-testid="stTextArea"] textarea:focus {
  border-color:var(--brand); box-shadow:0 0 0 3px var(--brand-ring);
}
[data-testid="stSelectbox"] > div > div, [data-testid="stNumberInput"] input {
  border-radius:10px; border-color:var(--border-strong);
}

[data-testid="stExpander"] { border:1px solid var(--border); border-radius:12px; background:var(--surface); box-shadow:var(--shadow-sm); }
[data-testid="stExpander"] summary { font-weight:700; color:var(--ink); }
[data-testid="stAlert"] { border-radius:12px; }
[data-testid="stVerticalBlockBorderWrapper"] {
  background:var(--surface); border:1px solid var(--border) !important;
  border-radius:14px; padding:.3rem .3rem; box-shadow:var(--shadow-sm);
  transition:all .2s var(--ease);
}
[data-testid="stVerticalBlockBorderWrapper"]:hover { border-color:var(--brand) !important; box-shadow:var(--shadow-md); }

.hero { padding:.5rem 0 1.1rem; }
.hero-eyebrow { display:inline-flex; align-items:center; gap:.45rem; font-size:11.5px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:var(--brand); background:var(--brand-soft); padding:.32rem .72rem; border-radius:999px; }
.hero-eyebrow .gem { width:6px; height:6px; border-radius:50%; background:var(--gold); }
.hero h1 { font-family:"Sora","PingFang SC","HarmonyOS Sans SC","Microsoft YaHei",sans-serif; font-size:clamp(1.9rem,3.4vw,2.7rem); font-weight:700; color:var(--ink); letter-spacing:-.02em; line-height:1.18; margin:.85rem 0 .6rem; }
.hero h1 em { font-style:normal; background:linear-gradient(120deg,var(--brand-ink),var(--brand)); -webkit-background-clip:text; background-clip:text; color:transparent; }
.hero p.sub { font-size:16px; color:var(--muted); max-width:58ch; line-height:1.7; margin:0; }

.capabilities { display:grid; grid-template-columns:repeat(3,1fr); margin-top:1.4rem; border-top:1px solid var(--border); border-bottom:1px solid var(--border); }
@media (max-width: 640px){ .capabilities{ grid-template-columns:1fr; } .cap{ border-left:none !important; border-top:1px solid var(--border); padding:.9rem 0 !important; } .cap:first-child{ border-top:none; } }
.cap { padding:1rem 1.15rem; border-left:1px solid var(--border); }
.cap:first-child { border-left:none; padding-left:0; }
.cap-title { font-size:13.5px; font-weight:700; color:var(--ink); display:flex; align-items:center; gap:.5rem; }
.cap-title::before { content:""; width:6px; height:6px; border-radius:50%; background:var(--brand); flex-shrink:0; }
.cap-desc { font-size:12.5px; color:var(--muted); margin-top:.32rem; line-height:1.55; }

.compare { display:grid; grid-template-columns:1fr auto 1fr; gap:12px; align-items:stretch; margin:1.5rem 0 .5rem; }
.compare-col { border-radius:14px; padding:1.05rem 1.2rem; border:1px solid var(--border); }
.compare-bad { background:var(--surface-2); }
.compare-good { background:var(--brand-soft); border-color:var(--brand); }
.compare-head { font-weight:700; font-size:13px; margin-bottom:.55rem; }
.compare-bad .compare-head { color:var(--muted); }
.compare-good .compare-head { color:var(--brand-ink); }
.compare ul { list-style:none; margin:0; padding:0; }
.compare li { font-size:13px; color:var(--text); padding:.22rem 0; }
.compare li .no { color:var(--danger); font-weight:700; margin-right:.3rem; }
.compare li .yes { color:var(--success); font-weight:700; margin-right:.3rem; }
.compare-vs { display:grid; place-items:center; font-weight:800; color:var(--faint); font-size:11px; letter-spacing:.06em; }

.kpi-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:14px; margin:4rem 0 .4rem; }
@media (max-width: 720px){ .kpi-grid{ grid-template-columns:repeat(2,1fr); } }
.kpi { background:var(--surface); border:1px solid var(--border); border-radius:14px; padding:1.05rem 1.15rem; box-shadow:var(--shadow-sm); transition:transform .2s var(--ease), box-shadow .2s var(--ease); }
.kpi:hover { transform:translateY(-2px); box-shadow:var(--shadow-md); }
.kpi .kpi-label { font-size:12px; color:var(--muted); font-weight:600; letter-spacing:.02em; }
.kpi .kpi-value { font-size:26px; font-weight:800; color:var(--ink); font-variant-numeric:tabular-nums; margin-top:.15rem; }
.kpi .kpi-value span.unit { font-size:14px; color:var(--muted); font-weight:600; margin-left:2px; }
.kpi .kpi-sub { font-size:12px; color:var(--faint); margin-top:.1rem; }

.sec-title { font-size:12.5px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); margin:1.6rem 0 .8rem; }
.sec-title::after { content:""; display:inline-block; width:22px; height:1px; background:var(--border-strong); margin-left:.6rem; vertical-align:middle; }

.pipeline { display:flex; align-items:stretch; margin:1.1rem 0 1.3rem; }
.pipeline .stage { flex:1; position:relative; background:var(--surface); border:1px solid var(--border); border-radius:14px; padding:.95rem .5rem; text-align:center; transition:all .25s var(--ease); }
.pipeline .stage + .stage { margin-left:28px; }
.pipeline .stage:not(:last-child)::after { content:""; position:absolute; right:-28px; top:50%; width:28px; height:2px; background:var(--border-strong); transform:translateY(-50%); }
.pipeline .stage:not(:last-child)::before { content:""; position:absolute; right:-29px; top:50%; transform:translateY(-50%) rotate(45deg); width:7px; height:7px; border-top:2px solid var(--border-strong); border-right:2px solid var(--border-strong); }
.pipeline .stage.done:not(:last-child)::after { background:var(--success); }
.pipeline .stage.done:not(:last-child)::before { border-color:var(--success); }
.stage .dot { width:40px; height:40px; margin:0 auto .55rem; border-radius:50%; display:grid; place-items:center; font-weight:700; font-size:13px; color:var(--muted); background:var(--surface-2); border:1.5px dashed var(--border-strong); }
.stage .name { font-size:13px; font-weight:700; color:var(--text); }
.stage .role { font-size:10.5px; color:var(--faint); margin-top:2px; }
.stage.active { border-color:var(--brand); box-shadow:0 0 0 3px var(--brand-ring); }
.stage.active .dot { background:var(--brand); color:#fff; border-style:solid; border-color:var(--brand); animation:pulse 1.6s infinite; }
.stage.done .dot { background:var(--success-soft); color:var(--success); border:1.5px solid var(--success); }
.stage.error { border-color:var(--danger); }
.stage.error .dot { background:var(--danger-soft); color:var(--danger); border-color:var(--danger); }
@keyframes pulse { 0%{box-shadow:0 0 0 0 var(--brand-ring);} 70%{box-shadow:0 0 0 10px transparent;} 100%{box-shadow:0 0 0 0 transparent;} }

.console { background:var(--console-bg); color:var(--console-fg); border-radius:12px; padding:1rem 1.15rem; font-family:"JetBrains Mono",Consolas,monospace; font-size:12px; line-height:1.7; max-height:280px; overflow:auto; }
.console .c-line { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.console .c-ok { color:#4ADE80; } .console .c-err { color:#FB7185; } .console .c-warn { color:#FBBF24; } .console .c-agent { color:var(--console-agent); }

.badge { display:inline-flex; align-items:center; gap:.3rem; font-size:11px; font-weight:700; padding:.2rem .55rem; border-radius:999px; }
.badge.ok { background:var(--success-soft); color:var(--success); }
.badge.part { background:var(--warning-soft); color:var(--warning); }
.badge.brand { background:var(--brand-soft); color:var(--brand-ink); }
.badge-grade-s { background:var(--success-soft); color:var(--success); }
.badge-grade-a { background:var(--brand-soft); color:var(--brand-ink); }
.badge-grade-b { background:var(--warning-soft); color:var(--warning); }
.chip { display:inline-flex; align-items:center; padding:.32rem .72rem; border-radius:999px; border:1px solid var(--border-strong); background:var(--surface); color:var(--text); font-size:12.5px; font-weight:600; margin:.15rem .25rem .15rem 0; }

.report-head { padding:.3rem 0 1rem; border-bottom:1px solid var(--border); margin-bottom:1.1rem; }
.report-title { font-family:"Sora","PingFang SC","HarmonyOS Sans SC","Microsoft YaHei",sans-serif; font-size:1.75rem; font-weight:700; color:var(--ink); line-height:1.3; }
.report-meta { color:var(--muted); font-size:13px; margin-top:.5rem; }
.abstract { background:linear-gradient(180deg,var(--abstract-top),var(--abstract-bot)); border:1px solid var(--abstract-border); border-left:3px solid var(--brand); border-radius:12px; padding:1.05rem 1.25rem; margin:.9rem 0 1.3rem; }
.abstract .ab-label { font-size:11px; font-weight:800; letter-spacing:.1em; text-transform:uppercase; color:var(--brand); margin-bottom:.4rem; }
.abstract .ab-text { font-size:14.5px; color:var(--text); line-height:1.8; }
.toc { display:flex; flex-wrap:wrap; gap:7px; margin:0 0 1.4rem; }
.toc .toc-item { font-size:12.5px; font-weight:600; color:var(--muted); padding:.3rem .7rem; border-radius:8px; background:var(--surface); border:1px solid var(--border); }
.report-table { width:100%; border-collapse:collapse; font-size:13.5px; margin:.4rem 0 1rem; }
.report-table th { background:var(--surface-2); text-align:left; padding:.6rem .8rem; border:1px solid var(--border); font-weight:700; color:var(--ink); }
.report-table td { padding:.55rem .8rem; border:1px solid var(--border); color:var(--text); }
.report-table tr:nth-child(even) td { background:var(--surface-2); }
.ref-item { font-size:13.5px; color:var(--text); padding:.55rem 0; border-bottom:1px dashed var(--border); }
.ref-item a { color:var(--brand); text-decoration:none; }
.ref-item a:hover { text-decoration:underline; }

.stMarkdown h2 { font-size:1.28rem; font-weight:800; color:var(--ink); margin-top:1.7rem; padding-left:.75rem; border-left:3px solid var(--brand); }
.stMarkdown h3 { font-size:1.06rem; font-weight:700; color:var(--ink); margin-top:1.2rem; }
.stMarkdown p { font-size:15px; color:var(--text); line-height:1.85; }

@media (prefers-reduced-motion: reduce){
  *,*::before,*::after { animation-duration:.01ms !important; transition-duration:.01ms !important; }
}
</style>"""


# ======================================================================
# HTML 片段构造函数
# ======================================================================
def brand_html():
    return f"""
    <div class="brand">
      <div class="brand-mark">E</div>
      <div>
        <div class="brand-name">Eco-Research</div>
        <div class="brand-sub">可信多智能体研究平台</div>
      </div>
    </div>
    """


def env_badge_html(ok: bool):
    cls = "ok" if ok else "part"
    txt = "API 就绪" if ok else "未配置密钥"
    return f'<span class="badge {cls}">{txt}</span>'


def hero_html():
    return """
    <div class="hero">
      <span class="hero-eyebrow"><span class="gem"></span> Multi-Agent · Trustworthy Research</span>
      <h1>输入课题，交付<em>可溯源、防幻觉</em>的专业研报</h1>
      <p class="sub">多智能体协作——只采信官方与权威信源、逐条溯源、质量门禁熔断，让每一份报告都经得起推敲。</p>
      <div class="capabilities">
        <div class="cap"><div class="cap-title">防幻觉熔断</div><div class="cap-desc">搜不到确凿证据就熔断，绝不编造数据</div></div>
        <div class="cap"><div class="cap-title">逐条溯源</div><div class="cap-desc">每条结论标注来源，可点击核查</div></div>
        <div class="cap"><div class="cap-title">权威信源</div><div class="cap-desc">优先采信政府与官方机构数据</div></div>
      </div>
    </div>
    """


def compare_html():
    return """
    <div class="compare">
      <div class="compare-col compare-bad">
        <div class="compare-head">传统 AI 调研</div>
        <ul>
          <li><span class="no">✕</span>一本正经地编造数据</li>
          <li><span class="no">✕</span>来源不明，无法核查</li>
          <li><span class="no">✕</span>幻觉严重，结论不可信</li>
        </ul>
      </div>
      <div class="compare-vs">VS</div>
      <div class="compare-col compare-good">
        <div class="compare-head">Eco-Research</div>
        <ul>
          <li><span class="yes">✓</span>只采信官方与权威信源</li>
          <li><span class="yes">✓</span>每条结论可点击溯源</li>
          <li><span class="yes">✓</span>搜不到证据就熔断</li>
        </ul>
      </div>
    </div>
    """


def kpi_html(m):
    avg = fmt_duration(m["avg_sec"]) if m["avg_sec"] > 0 else "—"
    cards = [
        ("累计项目", m["total"], "个", ""),
        ("完成报告", m["completed"], "份", ""),
        ("生成图表", m["charts"], "张", ""),
        ("生成表格", m["tables"], "张", ""),
        ("稽核通过率", m["qa_rate"], "%", f"共 {m['qa_total']} 次稽核"),
        ("平均耗时", avg, "", "单项目"),
    ]
    cells = []
    for label, value, unit, sub in cards:
        unit_html = f'<span class="unit">{unit}</span>' if unit else ""
        sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
        cells.append(
            f'<div class="kpi"><div class="kpi-label">{label}</div>'
            f'<div class="kpi-value">{value}{unit_html}</div>{sub_html}</div>'
        )
    return '<div class="kpi-grid">' + "".join(cells) + "</div>"


def pipeline_html(states, rnd, logs):
    stages = [
        ("01", "架构", "课题架构师 · 拆解课题"),
        ("02", "检索", "信源研究员 · 多源检索"),
        ("03", "稽核", "事实稽核官 · 防幻觉"),
        ("04", "撰写", "内容撰写师 · 建模撰文"),
        ("05", "渲染", "交付渲染官 · 交付"),
    ]
    icon = {"pending": "", "active": "", "done": "✓", "error": "!"}
    cells = []
    for i, (num, name, role) in enumerate(stages):
        s = states[i]
        cells.append(
            f'<div class="stage {s}"><div class="dot">{icon[s] or num}</div>'
            f'<div class="name">{name}</div><div class="role">{role}</div></div>'
        )
    board = '<div class="pipeline">' + "".join(cells) + "</div>"

    rnd_html = ""
    if rnd:
        rnd_html = (
            f'<div style="font-size:13px;color:var(--muted);margin:.4rem 0 .5rem;">'
            f'🔄 稽核循环 · 第 {rnd.group(1)} / {rnd.group(2)} 轮</div>'
        )

    lines = []
    for e in logs:
        agent = e.get("agent", "")
        action = e.get("action", "")
        details = (e.get("details") or "").replace("\n", " ")
        if len(details) > 92:
            details = details[:92] + "…"
        cls = {"SUCCESS": "c-ok", "FAILED": "c-err", "ERROR": "c-err", "WARNING": "c-warn"}.get(action, "")
        lines.append(
            f'<div class="c-line"><span class="c-agent">[{agent}]</span> '
            f'<span class="{cls}">{html_escape(details)}</span></div>'
        )
    console = '<div class="console">' + "".join(lines) + "</div>"
    return rnd_html + board + console


# ======================================================================
# 页面配置
# ======================================================================
st.set_page_config(
    page_title="Eco-Research Copilot",
    page_icon="🔮",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(CSS, unsafe_allow_html=True)


# ======================================================================
# 会话状态初始化
# ======================================================================
if "page" not in st.session_state:
    st.session_state["page"] = "overview"
if "report_data" not in st.session_state:
    st.session_state["report_data"] = None
if "topic_draft" not in st.session_state:
    st.session_state["topic_draft"] = ""
if "active_run" not in st.session_state:
    st.session_state["active_run"] = None


PAGE_LABELS = {
    "overview": "工作台",
    "new": "新建调研",
    "history": "项目历史",
    "settings": "设置",
    "report": "报告预览",
}


def nav_items():
    nav = [("overview", "工作台"), ("new", "新建调研"), ("history", "项目历史"), ("settings", "设置")]
    if st.session_state.get("report_data"):
        nav.append(("report", "报告预览"))
    return nav


def goto(page):
    st.session_state["page"] = page
    st.rerun()


def set_report(data, page="report"):
    st.session_state["report_data"] = data
    st.session_state["page"] = page
    st.rerun()


# ======================================================================
# 侧边栏：品牌 + 导航
# ======================================================================
with st.sidebar:
    st.markdown(brand_html(), unsafe_allow_html=True)

    ok = True
    try:
        Config.validate()
    except ValueError:
        ok = False
    st.markdown(
        f'<div style="padding:.1rem .35rem 1rem;margin-bottom:.4rem;border-bottom:1px solid var(--border);">{env_badge_html(ok)}</div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="side-label">导航</div>', unsafe_allow_html=True)
    nav = nav_items()
    labels = [label for _, label in nav]
    key_map = {label: key for key, label in nav}
    cur_label = next((label for key, label in nav if key == st.session_state["page"]), labels[0])

    # 同步：radio 实例化前把选中态对齐到当前 page（Streamlit 1.61 禁止 widget 实例化后再改其 session_state）
    if st.session_state.get("nav_radio") != cur_label:
        st.session_state["nav_radio"] = cur_label

    def _nav_change():
        st.session_state["page"] = key_map.get(st.session_state.get("nav_radio"), "overview")

    st.radio(
        "导航",
        labels,
        label_visibility="collapsed",
        key="nav_radio",
        on_change=_nav_change,
    )

    # 注入导航项 SVG 图标（细线条，颜色跟随 currentColor）
    st.sidebar.markdown(
        '<div style="margin-top:1.4rem;padding:.8rem .5rem 0;border-top:1px solid var(--border);font-size:11px;color:var(--faint);line-height:1.7;">'
        'Eco-Research Copilot · v2.0</div>',
        unsafe_allow_html=True,
    )


# ======================================================================
# 视图渲染
# ======================================================================
def render_overview():
    st.markdown(hero_html(), unsafe_allow_html=True)

    # 快速开始（紧跟副标题）
    st.markdown('<div class="sec-title">快速开始</div>', unsafe_allow_html=True)
    c_input, c_btn = st.columns([7, 2], vertical_alignment="bottom")
    with c_input:
        topic = st.text_input(
            "调研课题",
            key="ov_topic",
            placeholder="例如：2024年泰国新能源汽车渗透率、销量分析及政策影响",
            label_visibility="collapsed",
        )
    with c_btn:
        start = st.button("开始调研", type="primary", width="stretch", key="ov_start")
    if start and topic.strip():
        st.session_state["topic_draft"] = topic.strip()
        goto("new")

    # 数据区
    m = dashboard_metrics()
    st.markdown(kpi_html(m), unsafe_allow_html=True)

    # 最近项目
    projects = list_projects()[:4]
    st.markdown('<div class="sec-title">最近项目</div>', unsafe_allow_html=True)
    if not projects:
        st.info("暂无历史调研项目。在工作台点击「开始调研」即可发起你的第一份研报。")
    else:
        for p in projects:
            with st.container(border=True):
                c1, c2, c3 = st.columns([5, 2.5, 1.6])
                with c1:
                    st.markdown(f"**{html_escape(p['topic'])}**")
                    st.caption(f"{p['id']} · 耗时 {fmt_duration(p['duration'])}")
                with c2:
                    st.markdown(
                        f'<span class="badge {"ok" if p["status"]=="completed" else "part"}">'
                        f'{"已完成" if p["status"]=="completed" else "进行中/中断"}</span>&nbsp;'
                        f'<span class="badge brand">{p["n_charts"]} 图 · {p["n_tables"]} 表</span>',
                        unsafe_allow_html=True,
                    )
                with c3:
                    if p["has_result"]:
                        if st.button("查看", key=f"ov_view_{p['id']}", width="stretch"):
                            r = load_result(p["dir"])
                            set_report({"plan_data": r.get("plan_data", {}), "ai_data": r.get("ai_data", {}), "docx_path": r.get("docx_path", ""), "project_id": p["id"], "topic": p["topic"]})

    # 对比区（页底）
    st.markdown(compare_html(), unsafe_allow_html=True)


def _start_worker(project_id, project_dir, topic, resume=False):
    """后台启动流水线线程。线程只写 checkpoint 与日志，收尾由前端运行面板检测状态后处理。"""
    def _work():
        try:
            orchestrator = ResearchOrchestrator(project_name=project_id, resume=resume)
            orchestrator.run(topic)
        except PauseRequested:
            pass  # checkpoint 已置 paused，前端接管
        except Exception:
            pass  # checkpoint 已置 failed，前端接管

    threading.Thread(target=_work, daemon=True).start()


def _edit_intermediates(project_id, project_dir, state, ckpt):
    """暂停后展示并编辑中间产物（Step2：可编辑，保存后触发下游重跑）。"""
    stages = state.get("stages", {})
    plan_data = (stages.get("plan") or {}).get("data") or {}
    collect_data = (stages.get("collect") or {}).get("data") or {}
    analyze_data = (stages.get("analyze") or {}).get("data") or {}

    st.markdown('<div class="sec-title" style="margin-top:.4rem;">中间产物预览与编辑</div>', unsafe_allow_html=True)
    t1, t2, t3 = st.tabs(["① 调研提纲", "② 已校验情报（可编辑）", "③ 分析结果"])
    with t1:
        if plan_data:
            st.json(plan_data)
        else:
            st.caption("规划阶段尚未完成。")
    with t2:
        if collect_data:
            vc = collect_data.get("verified_context", "")
            st.caption(f"稽核轮次：第 {collect_data.get('round', '-')} 轮 / 共 {collect_data.get('max_rounds', '-')} 轮")
            vc_key = f"edit_vc_{project_id}"
            if vc_key not in st.session_state:
                st.session_state[vc_key] = vc
            st.text_area(
                "已校验情报（可直接修改，保存后将从分析阶段重新执行）",
                key=vc_key,
                height=240,
            )
            if st.button("💾 保存修改", key="btn_save_vc"):
                state = ckpt.load()
                if state.get("stages", {}).get("collect"):
                    state["stages"]["collect"]["data"]["verified_context"] = st.session_state[vc_key]
                    ckpt.save(state)
                ckpt.reset_from("analyze")  # 情报被人工修改，分析+排版需重跑
                st.toast("已保存，点击「继续调研」将从分析阶段重新执行")
                st.rerun()
        else:
            st.caption("检索稽核阶段尚未完成。")
    with t3:
        if analyze_data:
            st.json(analyze_data)
        else:
            st.caption("分析阶段尚未完成（或已因修改情报而待重跑）。")


def _render_running_fragment(project_id, project_dir, topic, ckpt):
    """运行中：fragment 定时轮询进度 + 暂停按钮，状态变化时 rerun 交由主流程接管。"""
    @st.fragment(run_every=1.0)
    def _panel():
        state = ckpt.load()
        entries = read_log(project_dir)
        st.markdown('<div class="sec-title">多智能体流水线</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div style="color:var(--muted);margin:0 0 .6rem;">课题：{html_escape(topic)}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            pipeline_html(derive_stages(entries), current_round(entries), entries[-10:]),
            unsafe_allow_html=True,
        )
        if state.get("status", "running") == "running":
            if st.button("⏸️ 暂停调研", key="btn_pause_run"):
                ckpt.request_pause()
                st.toast("暂停请求已发送，当前步骤完成后将暂停")
        else:
            st.rerun()  # 状态已变化，交给主流程接管

    _panel()


def _render_paused_panel(project_id, project_dir, topic, ckpt, state):
    """暂停中：展示进度 + 编辑中间产物 + 继续按钮（普通 widget，非 fragment）。"""
    entries = read_log(project_dir)
    st.markdown('<div class="sec-title">多智能体流水线</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div style="color:var(--muted);margin:0 0 .6rem;">课题：{html_escape(topic)}</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        pipeline_html(derive_stages(entries), current_round(entries), entries[-10:]),
        unsafe_allow_html=True,
    )
    st.info("⏸️ 调研已暂停，进度已保存。可编辑中间产物后继续。")
    _edit_intermediates(project_id, project_dir, state, ckpt)
    if st.button("▶️ 继续调研", key="btn_resume_run", type="primary"):
        ckpt.clear_pause()
        _start_worker(project_id, project_dir, topic, resume=True)
        st.toast("已继续，从断点恢复执行")
        st.rerun()


def _finalize_completed(project_id, project_dir, topic, state):
    """收尾：落盘结果 + 跳转报告页。"""
    plan_data = (state.get("stages", {}).get("plan") or {}).get("data") or {}
    ai_data = (state.get("stages", {}).get("analyze") or {}).get("data") or {}
    docx_path = ((state.get("stages", {}).get("format") or {}).get("data") or {}).get("docx_path", "")
    final_result = {"plan_data": plan_data, "ai_data": ai_data, "docx_path": docx_path}
    save_result(project_dir, project_id, topic, final_result)
    st.session_state["active_run"] = None
    st.session_state["report_data"] = {
        "plan_data": plan_data,
        "ai_data": ai_data,
        "docx_path": docx_path,
        "project_id": project_id,
        "topic": topic,
    }
    st.session_state["page"] = "report"
    st.rerun()


def _render_run_panel(active):
    """运行面板入口：按 checkpoint 状态分发到 running / paused / completed / failed。"""
    project_id = active["project_id"]
    project_dir = active["project_dir"]
    topic = active["topic"]
    ckpt = Checkpoint(project_dir)

    state = ckpt.load()
    status = state.get("status", "running")

    if status == "running":
        _render_running_fragment(project_id, project_dir, topic, ckpt)
    elif status == "paused":
        _render_paused_panel(project_id, project_dir, topic, ckpt, state)
    elif status == "completed":
        _finalize_completed(project_id, project_dir, topic, state)
    elif status == "failed":
        entries = read_log(project_dir)
        st.markdown('<div class="sec-title">多智能体流水线</div>', unsafe_allow_html=True)
        st.markdown(
            pipeline_html(derive_stages(entries), current_round(entries), entries[-10:]),
            unsafe_allow_html=True,
        )
        st.error("调研已中断，可返回项目历史查看日志，或重新发起。")
        if st.button("← 返回新建调研", key="btn_back_new"):
            st.session_state["active_run"] = None
            st.rerun()


def render_new():
    # 若有正在运行/暂停的任务，优先展示进度面板
    if st.session_state.get("active_run"):
        _render_run_panel(st.session_state["active_run"])
        return

    st.markdown('<div class="sec-title">新建调研</div>', unsafe_allow_html=True)
    st.markdown(
        '<h2 style="margin:0 0 .3rem;font-size:1.5rem;font-weight:800;color:var(--ink);">发起一次多智能体调研</h2>'
        '<p style="color:var(--muted);margin:0 0 1rem;">输入一个行业 / 市场 / 政策议题，系统将自动拆解、检索、稽核并产出报告。</p>',
        unsafe_allow_html=True,
    )

    # 环境自检
    try:
        Config.validate()
    except ValueError as e:
        st.error(str(e))

    topic = st.text_input(
        "调研课题",
        key="new_topic",
        value=st.session_state["topic_draft"],
        placeholder="输入你想调研的行业 / 市场 / 政策议题…",
    )

    examples = [
        "2024年泰国新能源汽车渗透率、销量分析及政策影响",
        "美国出口管制下中国企业数字化转型的战略响应",
        "中国AI大模型行业竞争格局与商业化趋势",
    ]
    st.markdown('<div style="font-size:12.5px;color:var(--muted);margin:.2rem 0 .3rem;">或选择一个示例：</div>', unsafe_allow_html=True)
    sel = st.pills("示例课题", examples, selection_mode="single", key="new_example", label_visibility="collapsed")

    # 高级设置：可直接修改模型 / 搜索引擎 / 轮数 / 稽核策略
    with st.expander("⚙️ 高级设置 · 模型 / 搜索引擎 / 稽核策略", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            Config.MODEL_NAME = st.text_input("模型名称", value=Config.MODEL_NAME)
            Config.SEARCH_PROVIDER = st.selectbox(
                "搜索引擎", ["tavily", "ddg"],
                index=0 if Config.SEARCH_PROVIDER == "tavily" else 1,
                format_func=lambda s: "Tavily（推荐，需密钥）" if s == "tavily" else "DuckDuckGo（可选代理）",
            )
        with c2:
            Config.MAX_COLLECT_ROUNDS = st.slider("检索轮数上限", 1, 5, int(Config.MAX_COLLECT_ROUNDS))
            Config.REQUIRE_STRICT_EVIDENCE = st.toggle("强制防幻觉验证（质量门禁）", value=bool(Config.REQUIRE_STRICT_EVIDENCE))
        Config.REPORT_MODE = st.radio(
            "报告正文模式",
            ["standard", "deep"],
            index=0 if Config.REPORT_MODE == "standard" else 1,
            format_func=lambda m: "标准模式（快，一次性生成）" if m == "standard" else "深度模式（分章生成，更充实、更慢）",
            horizontal=True,
        )
        st.caption("修改即时生效；API 密钥与「保存到 .env」请在左侧「设置」中管理。")

    launch = st.button("启动智能体调研", type="primary", width="stretch", key="new_launch")

    final_topic = (topic or "").strip() or (sel or "").strip()

    if launch:
        if not final_topic:
            st.warning("请先输入或选择一个调研课题。")
            return

        project_id = f"Project_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        project_dir = os.path.join(PROJECTS_DIR, project_id)
        os.makedirs(project_dir, exist_ok=True)

        # 后台启动流水线，进度由运行面板（fragment）轮询展示
        _start_worker(project_id, project_dir, final_topic, resume=False)
        st.session_state["active_run"] = {
            "project_id": project_id,
            "project_dir": project_dir,
            "topic": final_topic,
        }
        st.rerun()


_SOURCE_S = ["gov", "edu", "oecd", "un.org", "worldbank", "imf.org", "who.int", ".ac.cn", "stats", "mofcom", "ndrc", "nea.gov", "miit"]
_SOURCE_A = ["xinhua", "people.com", "caixin", "reuters", "bloomberg", "ft.com", "wsj.com", "eastmoney", "36kr", "ifeng", "sina.com", "163.com", "chinanews", "ce.cn", "yicai", "cls.cn"]


def source_grade(url):
    """根据域名启发式推断信源等级：S=官方/权威机构，A=权威媒体，B=一般信源。"""
    u = (url or "").lower()
    if any(k in u for k in _SOURCE_S):
        return "S", "官方信源"
    if any(k in u for k in _SOURCE_A):
        return "A", "权威信源"
    return "B", "一般信源"


def render_report():
    data = st.session_state["report_data"]
    ai_data = data.get("ai_data", {}) or {}
    docx_path = data.get("docx_path", "")
    plan_data = data.get("plan_data", {}) or {}

    title = ai_data.get("report_title", "调研报告")
    publish = ai_data.get("publish_date", "")
    core = ai_data.get("core_insights", "")

    st.markdown(
        f'<div class="report-head"><div class="report-title">{html_escape(title)}</div>'
        f'<div class="report-meta">发布日期：{html_escape(publish) or "—"} · 研究引擎：Eco-Research Copilot</div></div>',
        unsafe_allow_html=True,
    )

    if core:
        st.markdown(
            f'<div class="abstract"><div class="ab-label">摘要 · Core Insights</div>'
            f'<div class="ab-text">{html_escape(core)}</div></div>',
            unsafe_allow_html=True,
        )

    # 目录
    headings = extract_headings(ai_data.get("markdown_report", ""))
    if headings:
        toc = '<div class="toc">' + "".join(
            f'<span class="toc-item">{html_escape(h)}</span>' for h in headings
        ) + "</div>"
        st.markdown(toc, unsafe_allow_html=True)

    # 质量门禁清单
    requirements = plan_data.get("research_requirements", [])
    if requirements:
        with st.expander("🧭 调研需求清单 · 质量门禁（课题架构师产出）"):
            for i, r in enumerate(requirements, 1):
                st.markdown(f"**{i}. {html_escape(r.get('text', ''))}**" if isinstance(r, dict) else f"**{i}. {html_escape(str(r))}**")

    # 正文 + 图表穿插
    charts = ai_data.get("charts", []) or []
    tables = ai_data.get("tables", []) or []
    used_charts, used_tables = set(), set()

    for kind, text, idx in split_report(ai_data.get("markdown_report", "")):
        if kind == "text":
            txt = text.strip()
            if txt:
                st.markdown(txt)
        elif kind == "CHART":
            i = idx - 1
            if 0 <= i < len(charts):
                spec = chart_to_spec(charts[i])
                if spec:
                    st.vega_lite_chart(spec, width="stretch")
                    used_charts.add(i)
                else:
                    st.caption(charts[i].get("title", ""))
        elif kind == "TABLE":
            i = idx - 1
            if 0 <= i < len(tables):
                st.markdown(table_to_html(tables[i]), unsafe_allow_html=True)
                used_tables.add(i)

    # 未被引用的图表，作为补充数据兜底展示
    unused_charts = [c for i, c in enumerate(charts) if i not in used_charts]
    unused_tables = [t for i, t in enumerate(tables) if i not in used_tables]
    if unused_tables or unused_charts:
        st.markdown('<div class="sec-title">附 · 补充数据</div>', unsafe_allow_html=True)
        for t in unused_tables:
            st.markdown(table_to_html(t), unsafe_allow_html=True)
        for c in unused_charts:
            spec = chart_to_spec(c)
            if spec:
                st.vega_lite_chart(spec, width="stretch")

    # 参考文献
    refs = ai_data.get("references", []) or []
    if refs:
        st.markdown('<div class="sec-title">参考文献 · References</div>', unsafe_allow_html=True)
        for r in refs:
            idx = r.get("index", "")
            title = r.get("title", "") or ""
            url = r.get("url", "") or ""
            grade, grade_label = source_grade(url)
            grade_cls = {"S": "badge-grade-s", "A": "badge-grade-a", "B": "badge-grade-b"}[grade]
            grade_badge = f'<span class="badge {grade_cls}">{grade} · {grade_label}</span>'
            if url:
                st.markdown(
                    f'<div class="ref-item"><b>[{html_escape(idx)}]</b> '
                    f'<a href="{html_escape(url)}" target="_blank">{html_escape(title)}</a> '
                    f'{grade_badge}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div class="ref-item"><b>[{html_escape(idx)}]</b> {html_escape(title)} {grade_badge}</div>',
                    unsafe_allow_html=True,
                )

    # 下载
    st.markdown('<div class="sec-title">交付</div>', unsafe_allow_html=True)
    if docx_path and os.path.exists(docx_path):
        with open(docx_path, "rb") as f:
            st.download_button(
                "⬇ 下载企业级 Word 研报",
                data=f,
                file_name=f"{title}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                type="primary",
            )
    else:
        st.caption("未找到可下载的 Word 文件。")


def render_history():
    st.markdown('<div class="sec-title">项目历史</div>', unsafe_allow_html=True)
    st.markdown(
        '<h2 style="margin:0 0 .3rem;font-size:1.5rem;font-weight:800;color:var(--ink);">历史调研项目</h2>'
        '<p style="color:var(--muted);margin:0 0 1rem;">回看每一次调研的报告、图表与溯源数据。</p>',
        unsafe_allow_html=True,
    )

    projects = list_projects()
    if not projects:
        st.info("暂无历史调研项目。在工作台点击「开始调研」即可发起你的第一份研报。")
        return

    for p in projects:
        with st.container(border=True):
            c1, c2, c3 = st.columns([5, 3, 2])
            with c1:
                st.markdown(f"**{html_escape(p['topic'])}**")
                st.caption(f"{p['relative_time']} · 耗时 {fmt_duration(p['duration'])} · {p['n_events']} 条日志")
            with c2:
                status_badge = "ok" if p["status"] == "completed" else "part"
                status_txt = "已完成" if p["status"] == "completed" else "进行中/中断"
                qa_badge = "ok" if p["passed_qa"] else "part"
                qa_txt = "稽核通过" if p["passed_qa"] else "稽核未达标"
                st.markdown(
                    f'<span class="badge {status_badge}">{status_txt}</span>&nbsp;'
                    f'<span class="badge {qa_badge}">{qa_txt}</span>&nbsp;'
                    f'<span class="badge brand">{p["n_charts"]} 图 · {p["n_tables"]} 表</span>',
                    unsafe_allow_html=True,
                )
            with c3:
                if p["has_result"]:
                    if st.button("查看报告", key=f"his_view_{p['id']}", width="stretch"):
                        r = load_result(p["dir"])
                        if r:
                            set_report({
                                "plan_data": r.get("plan_data", {}),
                                "ai_data": r.get("ai_data", {}),
                                "docx_path": r.get("docx_path", ""),
                                "project_id": p["id"],
                                "topic": p["topic"],
                            })
                        else:
                            st.warning("该项目无完整结果数据，仅可下载 Word。")
                if p["has_docx"]:
                    docx = os.path.join(p["dir"], "05_final_report.docx")
                    with open(docx, "rb") as f:
                        st.download_button(
                            "下载 Word",
                            data=f,
                            file_name=f"{p['topic'][:30]}.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            key=f"his_dl_{p['id']}",
                            width="stretch",
                        )


def render_settings():
    st.markdown('<div class="sec-title">设置</div>', unsafe_allow_html=True)
    st.markdown(
        '<h2 style="margin:0 0 .3rem;font-size:1.5rem;font-weight:800;color:var(--ink);">运行配置</h2>'
        '<p style="color:var(--muted);margin:0 0 1rem;">调整大模型、搜索引擎与稽核策略。保存后写入 .env，重启应用生效。</p>',
        unsafe_allow_html=True,
    )

    Config.MODEL_NAME = st.text_input("模型名称", value=Config.MODEL_NAME)
    Config.BASE_URL = st.text_input("API Base URL", value=Config.BASE_URL)
    Config.SEARCH_PROVIDER = st.selectbox(
        "搜索引擎", ["tavily", "ddg"],
        index=0 if Config.SEARCH_PROVIDER == "tavily" else 1,
        format_func=lambda s: "Tavily（推荐，需密钥）" if s == "tavily" else "DuckDuckGo（可选代理）",
    )
    c1, c2 = st.columns(2)
    with c1:
        Config.API_RATE_LIMIT_SECONDS = int(st.number_input("API 调用最小间隔（秒）", min_value=0, value=int(Config.API_RATE_LIMIT_SECONDS)))
    with c2:
        Config.MAX_RETRY_WAIT_SECONDS = int(st.number_input("最大重试等待（秒）", min_value=0, value=int(Config.MAX_RETRY_WAIT_SECONDS)))
    Config.MAX_COLLECT_ROUNDS = st.slider("检索轮数上限", 1, 5, int(Config.MAX_COLLECT_ROUNDS))
    Config.REQUIRE_STRICT_EVIDENCE = st.toggle("强制防幻觉验证（质量门禁）", value=bool(Config.REQUIRE_STRICT_EVIDENCE))
    Config.REPORT_MODE = st.selectbox(
        "报告正文模式", ["standard", "deep"],
        index=0 if Config.REPORT_MODE == "standard" else 1,
        format_func=lambda m: "标准模式（快，一次性生成）" if m == "standard" else "深度模式（分章生成，更充实、更慢）",
    )

    st.markdown('<div class="sec-title">API 密钥</div>', unsafe_allow_html=True)
    ds_ok = bool(Config.DEEPSEEK_API_KEY)
    tv_ok = bool(Config.TAVILY_API_KEY)
    st.markdown(
        f'DEEPSEEK_API_KEY：<span class="badge {"ok" if ds_ok else "part"}">{"已配置" if ds_ok else "未配置"}</span>'
        f'&nbsp;&nbsp;TAVILY_API_KEY：<span class="badge {"ok" if tv_ok else "part"}">{"已配置" if tv_ok else "未配置"}</span>',
        unsafe_allow_html=True,
    )
    new_ds = st.text_input("重置 DEEPSEEK_API_KEY（留空保持）", type="password")
    new_tv = st.text_input("重置 TAVILY_API_KEY（留空保持）", type="password")

    if st.button("💾 保存设置到 .env", type="primary"):
        updates = {
            "MODEL_NAME": Config.MODEL_NAME,
            "BASE_URL": Config.BASE_URL,
            "SEARCH_PROVIDER": Config.SEARCH_PROVIDER,
            "API_RATE_LIMIT_SECONDS": str(int(Config.API_RATE_LIMIT_SECONDS)),
            "MAX_RETRY_WAIT_SECONDS": str(int(Config.MAX_RETRY_WAIT_SECONDS)),
            "MAX_COLLECT_ROUNDS": str(int(Config.MAX_COLLECT_ROUNDS)),
            "REQUIRE_STRICT_EVIDENCE": str(Config.REQUIRE_STRICT_EVIDENCE),
            "REPORT_MODE": Config.REPORT_MODE,
        }
        if new_ds.strip():
            updates["DEEPSEEK_API_KEY"] = new_ds.strip()
        if new_tv.strip():
            updates["TAVILY_API_KEY"] = new_tv.strip()
        try:
            update_env(updates)
            st.success("已保存到 .env，重启应用后生效。")
        except OSError as e:
            st.error(f"写入 .env 失败：{e}")


def update_env(updates: dict):
    """安全地把若干 KEY=VALUE 写入项目根目录 .env（保留其他行）。"""
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()

    result, updated = [], set()
    for line in lines:
        key = line.split("=", 1)[0].strip()
        if key in updates:
            result.append(f"{key}={updates[key]}")
            updated.add(key)
        else:
            result.append(line)
    for k, v in updates.items():
        if k not in updated:
            result.append(f"{k}={v}")

    with open(env_path, "w", encoding="utf-8") as f:
        f.write("\n".join(result) + "\n")


# ======================================================================
# 路由
# ======================================================================
page = st.session_state["page"]

if page == "overview":
    render_overview()
elif page == "new":
    render_new()
elif page == "report":
    render_report()
elif page == "history":
    render_history()
elif page == "settings":
    render_settings()
else:
    render_overview()
