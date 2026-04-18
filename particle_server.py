"""HUBERT Particle Simulator — Claude-powered text-to-particles server."""
import json
from pathlib import Path

import anthropic
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

BASE = Path(__file__).parent
UI_FILE = BASE / "particle_simulator.html"
CONFIG = json.loads((BASE / "jarvis_config.json").read_text())

client = anthropic.Anthropic(api_key=CONFIG["api_key"])

app = FastAPI(title="HUBERT Particle Simulator")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

SYSTEM = """You are a particle physics visualization expert. Given a text description of a particle effect,
return ONLY a valid JSON object with these exact fields — no markdown, no explanation, just raw JSON:

{
  "particle_count": <integer 500-8000>,
  "colors": [<array of 3-5 hex color strings>],
  "behavior": <one of: "orbit", "explosion", "flow", "swarm", "spiral", "nebula", "rain", "fire", "snow", "pulse", "vortex", "galaxy">,
  "speed": <float 0.1-5.0>,
  "gravity": <float -1.0 to 2.0, 0 = no gravity>,
  "spread": <float 0.5-5.0>,
  "size": <float 0.02-0.3>,
  "opacity": <float 0.3-1.0>,
  "trail": <boolean>,
  "mouse_interaction": <one of: "attract", "repel", "none", "orbit">,
  "emitter": <one of: "center", "edges", "random", "bottom", "top", "sphere">,
  "rotation_speed": <float 0.0-3.0>,
  "turbulence": <float 0.0-2.0>,
  "glow": <boolean>,
  "description": <one sentence describing the visual effect>
}

Interpret the user's prompt creatively and set parameters to best match the described effect."""


class PromptRequest(BaseModel):
    prompt: str


@app.get("/")
async def serve_ui():
    return FileResponse(str(UI_FILE), media_type="text/html")


def local_config(prompt: str) -> dict:
    """Keyword-based fallback config generator — no API required."""
    p = prompt.lower()
    cfg = {
        "particle_count": 3000, "colors": ["#00c8ff", "#7c3aed", "#ffffff"],
        "behavior": "orbit", "speed": 1.0, "gravity": 0.0, "spread": 3.0,
        "size": 0.10, "opacity": 0.8, "trail": False, "mouse_interaction": "attract",
        "emitter": "sphere", "rotation_speed": 0.3, "turbulence": 0.2, "glow": True,
        "description": prompt,
    }
    if any(w in p for w in ["fire", "flame", "lava", "hot", "burn"]):
        cfg.update({"colors": ["#ff4500","#ff8c00","#ffd700","#ff6347"],
                    "behavior": "fire", "emitter": "bottom", "gravity": -0.6,
                    "speed": 2.0, "turbulence": 0.8, "trail": True, "size": 0.10})
    elif any(w in p for w in ["snow", "snowflake", "winter", "blizzard"]):
        cfg.update({"colors": ["#e2e8f0","#bfdbfe","#ffffff","#dbeafe"],
                    "behavior": "snow", "emitter": "top", "gravity": 0.4,
                    "speed": 0.6, "turbulence": 0.3, "size": 0.08, "particle_count": 2000})
    elif any(w in p for w in ["rain", "storm", "drizzle", "water", "ocean", "wave"]):
        cfg.update({"colors": ["#0ea5e9","#38bdf8","#7dd3fc","#0284c7"],
                    "behavior": "rain", "emitter": "top", "gravity": 0.8,
                    "speed": 2.5, "turbulence": 0.1, "size": 0.07, "particle_count": 4000})
    elif any(w in p for w in ["galaxy", "space", "star", "cosmos", "universe", "milky"]):
        cfg.update({"colors": ["#e0e7ff","#a5b4fc","#818cf8","#fbbf24","#f9fafb"],
                    "behavior": "galaxy", "emitter": "sphere", "rotation_speed": 0.8,
                    "speed": 0.8, "particle_count": 5000, "size": 0.08, "spread": 4.0})
    elif any(w in p for w in ["explosion", "explode", "burst", "blast", "bang"]):
        cfg.update({"colors": ["#fbbf24","#f97316","#ef4444","#ffffff"],
                    "behavior": "explosion", "emitter": "center", "speed": 3.0,
                    "gravity": 0.3, "turbulence": 0.5, "particle_count": 2000})
    elif any(w in p for w in ["nebula", "cloud", "fog", "mist", "aurora"]):
        cfg.update({"colors": ["#7c3aed","#db2777","#0ea5e9","#10b981"],
                    "behavior": "nebula", "emitter": "sphere", "spread": 4.0,
                    "speed": 0.4, "particle_count": 4000, "size": 0.06, "opacity": 0.6})
    elif any(w in p for w in ["vortex", "tornado", "twister", "spin", "swirl", "spiral"]):
        cfg.update({"colors": ["#a78bfa","#818cf8","#c4b5fd","#e0e7ff"],
                    "behavior": "vortex", "emitter": "edges", "speed": 2.5,
                    "rotation_speed": 2.0, "turbulence": 0.3, "particle_count": 3500})
    elif any(w in p for w in ["matrix", "digital", "code", "cyber", "hack", "neon green"]):
        cfg.update({"colors": ["#22c55e","#4ade80","#86efac","#ffffff"],
                    "behavior": "rain", "emitter": "top", "speed": 3.0,
                    "gravity": 1.0, "turbulence": 0.0, "size": 0.03, "glow": True})
    elif any(w in p for w in ["lightning", "electric", "plasma", "arc", "bolt"]):
        cfg.update({"colors": ["#e0e7ff","#a5b4fc","#818cf8","#c7d2fe"],
                    "behavior": "pulse", "emitter": "sphere", "speed": 4.0,
                    "turbulence": 1.5, "size": 0.04, "glow": True, "particle_count": 2500})
    elif any(w in p for w in ["swarm", "bee", "flock", "swirl", "fluid"]):
        cfg.update({"colors": ["#fbbf24","#f59e0b","#d97706","#ffffff"],
                    "behavior": "swarm", "emitter": "random", "speed": 1.5,
                    "turbulence": 0.6, "spread": 3.5})
    elif any(w in p for w in ["rainbow", "colorful", "color", "prism", "spectrum"]):
        cfg.update({"colors": ["#ef4444","#f97316","#eab308","#22c55e","#3b82f6","#a855f7"],
                    "behavior": "orbit", "rotation_speed": 1.0, "spread": 3.0,
                    "particle_count": 4000, "glow": True})
    elif any(w in p for w in ["gold", "golden", "firefly", "fireflies", "sparkle"]):
        cfg.update({"colors": ["#fbbf24","#f59e0b","#fde68a","#fffbeb"],
                    "behavior": "swarm", "emitter": "sphere", "speed": 0.8,
                    "turbulence": 0.4, "glow": True, "size": 0.05})
    elif any(w in p for w in ["purple", "violet", "magenta", "pink"]):
        cfg.update({"colors": ["#a855f7","#d946ef","#e879f9","#f0abfc"],
                    "behavior": "orbit", "rotation_speed": 0.5})
    elif any(w in p for w in ["blue", "cyan", "ice", "crystal", "azure"]):
        cfg.update({"colors": ["#00c8ff","#38bdf8","#7dd3fc","#e0f2fe"],
                    "behavior": "orbit", "spread": 3.5})
    elif any(w in p for w in ["red", "crimson", "scarlet", "ruby"]):
        cfg.update({"colors": ["#ef4444","#f97316","#fca5a5","#fee2e2"],
                    "behavior": "pulse", "speed": 1.5})
    return cfg


@app.post("/generate-particles")
async def generate_particles(req: PromptRequest):
    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=SYSTEM,
            messages=[{"role": "user", "content": req.prompt}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        config = json.loads(raw)
        return JSONResponse(content={"ok": True, "config": config})
    except Exception:
        # Fallback: local keyword parser — always works, no API needed
        config = local_config(req.prompt)
        return JSONResponse(content={"ok": True, "config": config})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=7575, log_level="warning")
