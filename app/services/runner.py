# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Agent execution — one helper that runs an ADK agent and returns typed output.

Every agent in the crew has an `output_schema`, so each call is a single turn
returning structured JSON. Wrapping that once here keeps the orchestrator
readable and gives us one place to handle failure.
"""

from __future__ import annotations

import json
import logging
import uuid

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types

logger = logging.getLogger(__name__)

APP_NAME = "sceneroom"


async def run_agent_state(agent, prompt: str) -> dict:
    """Run an agent (or a workflow of them) and return the session state.

    `run_agent` returns the *last* thing said, which is the wrong thing for a
    LoopAgent: the final speaker is the critic, while the artefact we want is
    the reviser's output from an earlier turn. Every agent writes to its
    `output_key`, so the accumulated state is where a multi-agent result lives.
    """
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    user_id = "sceneroom"
    session_id = f"s-{uuid.uuid4().hex[:12]}"
    await runner.session_service.create_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )

    message = types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
    try:
        async for _ in runner.run_async(
            user_id=user_id, session_id=session_id, new_message=message
        ):
            pass
    except Exception as exc:
        logger.error("Workflow %s failed: %s", getattr(agent, "name", agent), exc)
        return {}

    session = await runner.session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    state = dict(session.state or {})
    # output_schema agents store their result as a JSON string.
    for key, value in list(state.items()):
        if isinstance(value, str) and value.strip().startswith("{"):
            try:
                state[key] = json.loads(value)
            except json.JSONDecodeError:
                pass
    return state


async def run_agent(agent: LlmAgent, prompt: str) -> dict:
    """Run a single-turn structured agent and return its parsed output.

    Returns an empty dict on failure — callers must degrade gracefully rather
    than crash the request. A failed check is reported as unverifiable, never
    silently as a pass.
    """
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    user_id = "sceneroom"
    session_id = f"s-{uuid.uuid4().hex[:12]}"
    await runner.session_service.create_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )

    message = types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
    final_text = ""
    try:
        async for event in runner.run_async(
            user_id=user_id, session_id=session_id, new_message=message
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        final_text = part.text
    except Exception as exc:
        logger.error("Agent %s failed: %s", agent.name, exc)
        return {}

    if not final_text:
        return {}
    try:
        return json.loads(final_text)
    except json.JSONDecodeError:
        # Models occasionally wrap JSON in prose or fences despite a schema.
        start, end = final_text.find("{"), final_text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(final_text[start : end + 1])
            except json.JSONDecodeError:
                pass
        logger.warning("Agent %s returned unparseable output", agent.name)
        return {}
