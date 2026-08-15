import json
import os
from datetime import datetime

class AgentLogger:
    def __init__(self, project_name: str):
        self.project_name = project_name
        self.root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.project_dir = os.path.join(self.root_dir, "projects", project_name)
        os.makedirs(self.project_dir, exist_ok=True)
        self.log_file = os.path.join(self.project_dir, "run_log.jsonl")

    def log_event(self, agent_name: str, action: str, details: str, status: str = None):
        # 调用点习惯把级别（SUCCESS/WARNING/…）作为第二个位置参数传入，
        # 此处将其落到 status 字段，保证存储与图标正确；未显式传入时回退到 action。
        status = action if status is None else status
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