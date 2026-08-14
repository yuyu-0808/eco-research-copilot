import json
import os
import streamlit as st
from datetime import datetime

class AgentLogger:
    def __init__(self, project_name: str):
        self.project_name = project_name
        self.root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.project_dir = os.path.join(self.root_dir, "projects", project_name)
        os.makedirs(self.project_dir, exist_ok=True)
        self.log_file = os.path.join(self.project_dir, "run_log.jsonl")

    def log_event(self, agent_name: str, action: str, details: str, status: str = "IN_PROGRESS"):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "agent": agent_name,
            "action": action,
            "status": status,
            "details": details
        }
        
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            
        status_icon = "✅" if status == "SUCCESS" else "❌" if status == "FAILED" else "⏳"
        log_str = f"[{status_icon} {agent_name}] {action}"
        print(log_str)
        
        # 🔥 神奇的 UI 联动：把后端日志强行推给前端网页的 Status 框！
        # 统一用 st.write 而非 st.success/st.error，保证在 st.status 块内能实时流式渲染
        try:
            # 去除长文本换行，让网页显示更清爽
            safe_details = details.replace("\n", " ")[:80] + "..." if len(details) > 80 else details
            if status == "SUCCESS":
                st.write(f"✅ **{agent_name}** · {safe_details}")
            elif status == "FAILED":
                st.write(f"❌ **{agent_name}** · {safe_details}")
            else:
                st.write(f"⏳ **{agent_name}** · {safe_details}")
        except:
            # 兼容非 Streamlit 环境
            pass