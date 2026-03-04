from __future__ import annotations

import json
import logging

from ..state import ExperimentState
from .clients import NOVA_PRO_MODEL_ID, bedrock

logger = logging.getLogger(__name__)


def generate_procedure(state: ExperimentState) -> dict:
    """
    Node 1 — Calls Amazon Bedrock Nova Pro to convert the experiment into
    3–6 visual action scenes, each suitable for a 6-second video clip.
    """
    prompt = (
        f"You are an expert chemistry teacher for Class 12 students.\n"
        f"Convert the following chemistry lab experiment into visual action scenes: "
        f'"{state["experiment_name"]}".\n\n'
        f"Rules:\n"
        f"- Return ONLY a valid JSON array of strings.\n"
        f"- Convert the experiment into visual action scenes.\n"
        f"- Each scene must represent one continuous visual action.\n"
        f"- Do NOT include preparation or cleanup.\n"
        f"- Merge steps that occur in the same physical position into one scene.\n"
        f"- Each scene must be suitable for a 6-second video.\n"
        f"- Include 3–6 scenes depending on experiment complexity.\n"
        f"- Maintain a consistent lab environment, same student, same lighting, "
        f"same camera angle across all scenes.\n"
        f"- Do NOT include narration.\n"
        f"- No markdown, no extra text outside the JSON array.\n\n"
        f'Example: ["A student in a chemistry lab holds a glass tube over a Bunsen burner flame, '
        f'slowly rotating it as the glass begins to glow red.", '
        f'"The student gently bends the heated glass tube to form an angle."]'
    )

    try:
        logger.info("Calling Bedrock Nova Pro (%s) to generate procedure for: '%s'",
                    NOVA_PRO_MODEL_ID, state["experiment_name"])
        body = {
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {"maxTokens": 1024, "temperature": 0.3},
        }
        response = bedrock.invoke_model(
            modelId=NOVA_PRO_MODEL_ID,
            body=json.dumps(body),
        )
        result = json.loads(response["body"].read())
        text = result["output"]["message"]["content"][0]["text"].strip()
        steps: list[str] = json.loads(text)
        logger.info("Nova Pro returned %d steps for experiment: '%s'",
                    len(steps), state["experiment_name"])
        for i, step in enumerate(steps, 1):
            logger.info("  Step %d: %s", i, step)
        return {"procedure_steps": steps}

    except Exception as exc:
        logger.error("Node 1 (generate_procedure) failed: %s", exc, exc_info=True)
        return {"error": f"Node 1 (generate_procedure) failed: {exc}", "procedure_steps": []}
