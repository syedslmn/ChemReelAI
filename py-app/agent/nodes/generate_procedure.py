from __future__ import annotations

import json
import logging

from ..state import ExperimentState
from .clients import NOVA_PRO_MODEL_ID, bedrock

logger = logging.getLogger(__name__)


def generate_procedure(state: ExperimentState) -> dict:
    """
    Node 1 — Calls Amazon Bedrock Nova Pro to produce an ordered list of
    procedure steps for the given chemistry experiment.

    Returns up to 8 steps, each short enough to describe a 6-second action.
    """
    prompt = (
        f"You are an expert chemistry teacher for Class 12 students.\n"
        f"Write a clear, step-by-step laboratory procedure for the experiment: "
        f'"{state["experiment_name"]}".\n\n'
        f"Rules:\n"
        f"- Return ONLY a valid JSON array of strings.\n"
        f"- Each string is one distinct step.\n"
        f"- Each step must describe a single observable action that can be "
        f"illustrated in a 6-second video clip.\n"
        f"- Maximum 8 steps.\n"
        f"- No markdown, no extra text outside the JSON array.\n\n"
        f'Example: ["Fill the burette with 0.1M NaOH.", '
        f'"Add 3 drops of phenolphthalein to the flask."]'
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
        return {"procedure_steps": steps}

    except Exception as exc:
        logger.error("Node 1 (generate_procedure) failed: %s", exc, exc_info=True)
        return {"error": f"Node 1 (generate_procedure) failed: {exc}", "procedure_steps": []}
