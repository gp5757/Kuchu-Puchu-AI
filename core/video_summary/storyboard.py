"""
core/video_summary/storyboard.py
Generates a structured, pedagogical storyboard for the whiteboard video summary
using ultra-fast Groq LLMs (with Gemini fallback and resilient deterministic fallback).
"""

import os
import re
import json
from dotenv import load_dotenv

load_dotenv()


STORYBOARD_SYSTEM_PROMPT = """You are an expert whiteboard animator and master educational explainer (in the style of 3Blue1Brown, RSA Animate, and Khan Academy).
Your task is to transform a video/lecture summary into a compelling, narrated, step-by-step whiteboard animation storyboard.

Strict Requirements:
1. Divide the summary into 4 to 6 concise, chronological, high-impact scenes.
2. For each scene:
   - "scene_id": integer starting from 1
   - "header": 2 to 5 words conceptual scene title
   - "badge": short category label (e.g., "OVERVIEW", "STEP 1", "KEY MECHANISM", "DECISION", "TAKEAWAY")
   - "narration": 25 to 45 words of clear, spoken narration written for voiceover. Friendly, engaging, teacher tone. No citations or markdown in narration.
   - "key_point": one punchy 1-sentence highlight or core insight to feature on the whiteboard.
   - "bullet_points": 2 to 3 short bullet points (under 9 words each).
   - "doodle_type": choose the best visual doodle from: ["lightbulb", "flowchart", "gears", "target", "brain", "network", "rocket", "checklist"]
   - "accent_color": pick one vibrant sketch color from: ["#E06C53", "#2A9D8F", "#D4A017", "#457B9D", "#7E8B4E"]

Return ONLY a valid JSON object matching this schema:
{
  "title": "Short Video Title (Max 6 words)",
  "scenes": [
    {
      "scene_id": 1,
      "header": "Core Concept",
      "badge": "STEP 1",
      "narration": "Narration text...",
      "key_point": "Key takeaway sentence.",
      "bullet_points": ["First point", "Second point"],
      "doodle_type": "lightbulb",
      "accent_color": "#2A9D8F"
    }
  ]
}
Do NOT include markdown backticks around the JSON. Only return pure JSON.
"""


def _get_storyboard_llm():
    """
    Returns high-speed Groq LLM as primary (3-5s generation) with Gemini Flash fallback.
    Enforces strict 15s request_timeout so it never hangs.
    """
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        try:
            from langchain_groq import ChatGroq
            primary = ChatGroq(
                model="openai/gpt-oss-120b",
                api_key=groq_key,
                temperature=0.2,
                request_timeout=15,
                max_tokens=2500
            )
            fallback = ChatGroq(
                model="openai/gpt-oss-20b",
                api_key=groq_key,
                temperature=0.2,
                request_timeout=15,
                max_tokens=2500
            )
            return primary.with_fallbacks([fallback])
        except Exception as e:
            print(f"[storyboard] Warning: Failed to init ChatGroq: {e}")

    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                model="gemini-2.5-flash",
                api_key=gemini_key,
                temperature=0.2,
                timeout=15
            )
        except Exception as e:
            print(f"[storyboard] Warning: Failed to init ChatGoogleGenerativeAI: {e}")

    return None


def generate_storyboard(title: str, summary: str, action_items: str = "", key_decisions: str = "") -> dict:
    """
    Generates a structured storyboard dictionary from summary inputs.
    Falls back gracefully if LLMs are unavailable or return malformed JSON.
    """
    title = title or "Lecture Summary"
    summary_text = (summary or "").strip()
    if len(summary_text) < 30:
        return _build_fallback_storyboard(title, summary_text)

    llm = _get_storyboard_llm()
    if llm is None:
        return _build_fallback_storyboard(title, summary_text)

    user_prompt = f"""Video Title: {title}

Summary Content:
{summary_text[:4000]}

Key Action Items & Decisions:
{action_items[:800]}
{key_decisions[:800]}

Draft the whiteboard animation storyboard JSON now:"""

    try:
        from langchain_core.messages import SystemMessage, HumanMessage
        messages = [
            SystemMessage(content=STORYBOARD_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt)
        ]
        response = llm.invoke(messages)
        content = response.content if hasattr(response, "content") else str(response)

        # Robust JSON extraction: finds the outermost JSON object
        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            clean_json = json_match.group(0)
            data = json.loads(clean_json)
            if isinstance(data, dict) and "scenes" in data and len(data["scenes"]) >= 2:
                # Validate scene fields
                for idx, scene in enumerate(data["scenes"], 1):
                    scene["scene_id"] = idx
                    scene["header"] = scene.get("header") or f"Concept {idx}"
                    scene["badge"] = scene.get("badge") or f"PART {idx}"
                    scene["narration"] = scene.get("narration") or f"In this section, we examine key concept {idx}."
                    scene["key_point"] = scene.get("key_point") or "Important highlight from discussion."
                    if not isinstance(scene.get("bullet_points"), list):
                        scene["bullet_points"] = ["Core insight explored in depth.", "Practical application discussed."]
                    if scene.get("doodle_type") not in ["lightbulb", "flowchart", "gears", "target", "brain", "network", "rocket", "checklist"]:
                        scene["doodle_type"] = "lightbulb"
                    if not scene.get("accent_color"):
                        scene["accent_color"] = "#2A9D8F"
                return data
    except Exception as e:
        print(f"[storyboard] Error in LLM storyboard generation: {e}")

    return _build_fallback_storyboard(title, summary_text)


def _build_fallback_storyboard(title: str, summary_text: str) -> dict:
    """Builds a high quality deterministic storyboard directly from text paragraphs."""
    lines = [line.strip("- *# \t") for line in summary_text.splitlines() if len(line.strip("- *# \t")) > 20]
    
    scenes = []
    doodles = ["lightbulb", "brain", "flowchart", "target", "checklist"]
    colors = ["#2A9D8F", "#E06C53", "#457B9D", "#D4A017", "#7E8B4E"]
    badges = ["OVERVIEW", "KEY MECHANISM", "DEEP DIVE", "APPLICATION", "SUMMARY"]

    # Intro scene
    scenes.append({
        "scene_id": 1,
        "header": "Core Overview",
        "badge": "OVERVIEW",
        "narration": f"Welcome to the video summary for {title}. Here is a clear breakdown of the essential concepts and takeaways discussed.",
        "key_point": lines[0] if lines else f"Essential insights distilled from {title}.",
        "bullet_points": [
            "Comprehensive breakdown of core topics.",
            "Key explanations without fluff or repetition."
        ],
        "doodle_type": "lightbulb",
        "accent_color": "#2A9D8F"
    })

    # Middle scenes from summary paragraphs
    extracted_idx = 1
    for i in range(1, 4):
        if extracted_idx < len(lines):
            kp = lines[extracted_idx]
            extracted_idx += 1
            bullets = []
            if extracted_idx < len(lines):
                bullets.append(lines[extracted_idx][:60])
                extracted_idx += 1
            if extracted_idx < len(lines):
                bullets.append(lines[extracted_idx][:60])
                extracted_idx += 1
            if not bullets:
                bullets = ["Structured procedural logic.", "Verified takeaways and context."]

            scenes.append({
                "scene_id": len(scenes) + 1,
                "header": f"Key Principle {i}",
                "badge": badges[min(i, len(badges)-1)],
                "narration": f"Examining point {i}: {kp[:150]} This provides crucial clarity on the central workflow.",
                "key_point": kp[:120],
                "bullet_points": bullets[:2],
                "doodle_type": doodles[i % len(doodles)],
                "accent_color": colors[i % len(colors)]
            })

    # Conclusion scene
    scenes.append({
        "scene_id": len(scenes) + 1,
        "header": "Final Verdict & Takeaways",
        "badge": "VERDICT",
        "narration": "In summary, these key principles establish the foundation for practical implementation and decision making.",
        "key_point": "All strategic outcomes and action items successfully mapped.",
        "bullet_points": [
            "Action items and next steps outlined.",
            "Archival folio ready for review."
        ],
        "doodle_type": "checklist",
        "accent_color": "#7E8B4E"
    })

    return {
        "title": title[:40],
        "scenes": scenes
    }
