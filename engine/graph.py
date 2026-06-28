"""FlowGraphBuilder — generates Mermaid flowchart TD from a FlowDef."""
from engine.v3_models import FlowDef

_STEP_STYLES: dict[str, str] = {
    "browser_navigate":   "fill:#4A90D9,color:#fff",
    "browser_fill":       "fill:#4A90D9,color:#fff",
    "browser_click":      "fill:#4A90D9,color:#fff",
    "browser_screenshot": "fill:#4A90D9,color:#fff",
    "browser_extract":    "fill:#4A90D9,color:#fff",
    "gmail_watch":        "fill:#34A853,color:#fff",
    "notify_email":       "fill:#34A853,color:#fff",
    "llm_decide":         "fill:#9C27B0,color:#fff",
    "claude_complete":    "fill:#9C27B0,color:#fff",
    "claude_extract":     "fill:#9C27B0,color:#fff",
    "human_pause":        "fill:#FF9800,color:#fff",
    "captcha_detect":     "fill:#FF5722,color:#fff",
    "captcha_execute":    "fill:#FF5722,color:#fff",
    "block":              "fill:#607D8B,color:#fff",
    "condition":          "fill:#795548,color:#fff",
    "wait":               "fill:#9E9E9E,color:#fff",
    "python_run":         "fill:#00BCD4,color:#fff",
    "store_get":          "fill:#78909C,color:#fff",
    "store_set":          "fill:#78909C,color:#fff",
}
_DEFAULT_STYLE = "fill:#E0E0E0,color:#333"


class FlowGraphBuilder:
    def __init__(self, flow: FlowDef):
        self.flow = flow

    def to_mermaid(self) -> str:
        lines:  list[str] = ["flowchart TD"]
        styles: list[str] = []
        step_ids = {s.step_id for s in self.flow.steps}
        needs_end_node = False

        # Node declarations
        for step in self.flow.steps:
            sid   = step.step_id
            label = sid.replace("_", " ").title()
            stype = step.type
            if stype in ("llm_decide", "condition"):
                lines.append(f'    {sid}{{"{label}"}}')
            elif stype == "human_pause":
                lines.append(f'    {sid}[/"{label}"/]')
            else:
                lines.append(f'    {sid}["{label}"]')
            style = _STEP_STYLES.get(stype, _DEFAULT_STYLE)
            styles.append(f"    style {sid} {style}")

        # Edge declarations
        for i, step in enumerate(self.flow.steps):
            sid       = step.step_id
            has_choice_edges = False

            for choice, target in step.on_choice.items():
                clean = target.replace("skip_to:", "").strip()
                if clean == "__end__":
                    lines.append(f'    {sid} -->|"{choice}"| END(( ))')
                    needs_end_node = True
                elif clean in step_ids:
                    lines.append(f'    {sid} -->|"{choice}"| {clean}')
                has_choice_edges = True

            if step.on_timeout and step.on_timeout in step_ids:
                lines.append(f'    {sid} -.->|"timeout"| {step.on_timeout}')

            if step.on_error and step.on_error in step_ids:
                lines.append(f'    {sid} -.->|"error"| {step.on_error}')

            # Implicit fallthrough when no on_choice is defined
            if not has_choice_edges and i + 1 < len(self.flow.steps):
                next_sid = self.flow.steps[i + 1].step_id
                lines.append(f"    {sid} --> {next_sid}")

        lines.append("")
        lines.extend(styles)

        if needs_end_node:
            lines.append("    style END fill:#333,color:#fff,stroke-width:2px")

        return "\n".join(lines)
