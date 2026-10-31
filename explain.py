"""The LLM only phrases findings. Every number comes from SQL. Works offline via a template fallback."""
import os, json

def explain(facts: dict) -> str:
    fallback = (f"{facts['kind'].capitalize()}: {facts['pattern']} ran {facts['runs']:,} times for "
                f"{facts['users']} users, costing about ₹{facts['cost_rupees']:,}. Next step: {facts['fix']}.")
    if not os.getenv("ANTHROPIC_API_KEY"):
        return fallback
    try:
        import anthropic
        r = anthropic.Anthropic().messages.create(model="claude-sonnet-5-5", max_tokens=220, messages=[{"role": "user", "content":
            "You are a data platform cost analyst. Using ONLY these facts (do not invent numbers), write two plain sentences "
            "for a manager: what is wasteful and the one concrete next step.\nFacts: " + json.dumps(facts)}])
        return r.content[0].text.strip()
    except Exception:
        return fallback

def ticket(facts: dict) -> str:
    return (f"## Reduce repeated heavy query\n**Evidence:** `{facts['pattern']}` ran {facts['runs']:,} times by {facts['users']} users "
            f"(~₹{facts['cost_rupees']:,} in modelled cost).\n**Proposed change:** {facts['fix']}.\n"
            "**Success measure:** same report, measured median runtime before vs after (see Prove it).")
