# core/markdown_renderer.py — Pure markdown rendering for EchoMind memory archives.
#
# Zero database or agent dependency: every render function receives plain
# Python objects (lists, dicts, dataclasses) and returns a markdown string.
# This means the renderer can be tested independently, reused across
# different agent frameworks, and extended to PDF/JSON/HTML in the future.

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional


# ── Lightweight data objects (Step 2: data-source decoupling) ─────────

@dataclass
class KnowledgeRow:
    content: str
    trust_score: float
    epistemic_mode: str = ""
    cognitive_pos: str = ""
    domain: str = "general"


@dataclass
class ExperienceRow:
    summary: str
    frequency: int = 1
    success: bool = False


@dataclass
class TaskRow:
    title: str
    status: str


@dataclass
class MemoryArchive:
    """All the data needed to render a complete markdown memory archive.

    The caller (memory_agent._query_archive_data) is responsible for
    populating this object from the SQLite store; the renderer only
    reads its fields.
    """
    version: str = ""
    generated_at: str = ""
    autoreflection_score: int = 0
    autoreflection_summary: str = ""
    stats: dict = field(default_factory=dict)
    user_prefs: dict = field(default_factory=dict)
    user_habits: dict = field(default_factory=dict)
    user_history: list = field(default_factory=list)
    knowledge: List[KnowledgeRow] = field(default_factory=list)
    experience: List[ExperienceRow] = field(default_factory=list)
    tasks: List[TaskRow] = field(default_factory=list)
    papers: list = field(default_factory=list)
    reflection_confidence: float = 0.0
    reflection_insights: str = ""
    reflection_knowledge: str = ""


# ── Pure render functions (Step 1: moved out of memory_agent.py) ─────

def render_header(data: MemoryArchive) -> str:
    rows = []
    for t in ("knowledge", "experience", "task", "context", "user", "paper"):
        s = data.stats.get(t, {})
        rows.append(f"| {t} | {s.get('active', 0)} | {s.get('stale', 0)} | {s.get('archived', 0)} |")
    return f"""# 🧠 EchoMind Memory Archive

> EchoMind v{data.version} | Generated {data.generated_at}
> **Self-Reflection Score: {data.autoreflection_score}/4**

## 📊 Memory Health

| Type | Active | Stale | Archived |
|------|--------|-------|----------|
{chr(10).join(rows)}
"""


def render_user_profile(prefs: dict, habits: dict, history: list) -> str:
    pref_rows = "\n".join(
        f"| {k} | {v} |" for k, v in prefs.items()
        if isinstance(v, (str, int, float, bool))
    )
    habit_rows = "\n".join(f"- {k}: {v}" for k, v in habits.items())
    history_rows = "\n".join(
        f"- {h.get('timestamp', '')}: {h.get('action', '')}"
        f"{' [' + str(h.get('project', '')) + ' @ ' + str(h.get('platform', '')) + ']' if h.get('project') or h.get('platform') else ''}"
        for h in history[-10:]
    )
    return f"""## 👤 User Profile

### Preferences
| Dimension | Value |
|-----------|-------|
{pref_rows or '| — | — |'}

### Habits
{habit_rows or '- —'}

### Recent Activity (last 10)
{history_rows or '- —'}
"""


def _format_trust(score) -> str:
    """Safely format a trust score. Handles None / non-numeric values that
    may leak in from raw metadata (e.g. the string "high") without crashing
    the whole archive render (V8-5)."""
    try:
        return f"{float(score):.2f}"
    except (TypeError, ValueError):
        return "—"


def render_knowledge(items: List[KnowledgeRow]) -> str:
    if not items:
        return "## 📚 Knowledge\n\n(empty)\n"
    known_modes = {"user_provided", "reasoned", "fuzzy", "referenced", "unknown"}
    buckets: dict = {m: [] for m in known_modes}
    for item in items:
        mode = item.epistemic_mode or "unknown"
        # V8-6 fix: any unrecognized epistemic_mode value used to land in a
        # never-rendered bucket and silently drop the entry. Fold unknown
        # values into "unknown" so nothing disappears from the archive.
        if mode not in known_modes:
            mode = "unknown"
        buckets[mode].append(item)
    labels = {
        "user_provided": "✅ User Confirmed",
        "reasoned": "🧠 Reasoned",
        "fuzzy": "⚠️ Unverified",
        "referenced": "📎 Referenced",
        "unknown": "❓ Unknown",
    }
    parts = ["## 📚 Knowledge"]
    for mode, label in labels.items():
        rows = buckets.get(mode, [])
        if not rows:
            continue
        parts.append(f"\n### {label} ({len(rows)})")
        parts.append("| Knowledge | Trust | Cognitive Pos | Domain |")
        parts.append("|-----------|------:|:---:|--------|")
        for r in rows:
            cnt = (r.content or "")[:80].replace("|", "\\|")
            cog_map = {"nok": "⚡ nok", "fok": "🔽 fok", "exo": "📖 exo"}
            cog_icon = cog_map.get(r.cognitive_pos, r.cognitive_pos or "—")
            parts.append(f"| {cnt} | {_format_trust(r.trust_score)} | {cog_icon} | {r.domain} |")
    return "\n".join(parts)


def render_experience(items: List[ExperienceRow]) -> str:
    if not items:
        return "## 💡 Experience\n\n(empty)\n"
    succ, fail = [], []
    for e in items:
        (succ if e.success else fail).append(e)
    parts = ["## 💡 Experience"]
    for tag, lst in [("✅ Success", succ), ("❌ Failure", fail)]:
        if not lst:
            continue
        parts.append(f"\n### {tag} ({len(lst)})")
        parts.append("| Summary | Freq |")
        parts.append("|---------|-----:|")
        for e in lst[:30]:
            parts.append(f"| {(e.summary or '')[:100]} | {e.frequency} |")
    return "\n".join(parts)


def render_tasks(items: List[TaskRow]) -> str:
    if not items:
        return "## 🗂️ Tasks\n\n(empty)\n"
    # V8-7 fix: the engine only ever records task-level status "pending"
    # (steps carry their own status), so the old hardcoded "✅ Completed"
    # section was unreachable dead code. Render statuses generically so any
    # status value (including a future "completed") displays correctly.
    by_status: dict = {}
    for t in items:
        by_status.setdefault(t.status or "pending", []).append(t)
    labels = {"pending": "🚧 In Progress", "completed": "✅ Completed"}
    parts = ["## 🗂️ Tasks"]
    for status, group in by_status.items():
        label = labels.get(status, f"📌 {status}")
        parts.append(f"\n### {label} ({len(group)})")
        for t in group[:20]:
            mark = "[x]" if status == "completed" else "[ ]"
            parts.append(f"- {mark} {t.title}" + ("" if status in ("pending", "completed") else f" ({t.status})"))
    return "\n".join(parts)


def render_context(stats: dict) -> str:
    ctx = stats.get("context", {})
    return f"""## 💬 Context

| Active | Stale | Archived |
|--------|-------|----------|
| {ctx.get('active', 0)} | {ctx.get('stale', 0)} | {ctx.get('archived', 0)} |
"""


def render_research(papers: list) -> str:
    if not papers:
        return "## 📄 Research\n\n(empty)\n"
    parts = ["## 📄 Research"]
    parts.append("| Title | Domain | Year |")
    parts.append("|-------|--------|-----:|")
    for p in papers[:20]:
        parts.append(f"| {p.title[:80]} | {p.domain} | {p.year or ''} |")
    return "\n".join(parts)


def render_reflection(confidence: float, insights: str, knowledge: str) -> str:
    if not confidence:
        return "## 🪞 Reflection\n\n(no reflections yet)\n"
    return f"""## 🪞 Latest Reflection (confidence {confidence:.2f})

**Key Insights**
{insights[:300] or '- —'}

**New Knowledge**
{knowledge[:300] or '- —'}
"""


def render_autoreflection(score: int, summary: str) -> str:
    if not summary:
        return "## 🔍 Self-Reflection Score\n\n(unavailable)\n"
    return f"""## 🔍 Self-Reflection Score

**{score}/4**

{summary}
"""


def render_full_archive(data: MemoryArchive) -> str:
    """Produce the complete memory.md document.

    All data must be populated on `data` before calling.
    """
    sections = [
        render_header(data),
        render_user_profile(data.user_prefs, data.user_habits, data.user_history),
        render_knowledge(data.knowledge),
        render_experience(data.experience),
        render_tasks(data.tasks),
        render_context(data.stats),
        render_research(data.papers),
        render_reflection(data.reflection_confidence,
                          data.reflection_insights,
                          data.reflection_knowledge),
        render_autoreflection(data.autoreflection_score,
                              data.autoreflection_summary),
    ]
    return "\n\n---\n\n".join(sections)