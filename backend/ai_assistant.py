
import os
import time
import random
from typing import Literal

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from google import genai
from google.genai import types
from google.genai import errors

from backend.auth import get_current_user


router = APIRouter()


class AIRequest(BaseModel):
    task: Literal["explain", "fix", "generate", "optimize", "ask"]
    language: str = Field(default="Python", max_length=50)
    code: str = Field(default="", max_length=20000)
    message: str = Field(default="", max_length=4000)


@router.post("/ai/assistant")
async def ai_assistant(
    data: AIRequest,
    current_user=Depends(get_current_user),
):
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Gemini API key is not configured."
        )

    if getattr(current_user, "guest", False):
        raise HTTPException(
            status_code=403,
            detail="AI Assistant is available to registered users only."
        )

    if not data.code.strip() and not data.message.strip():
        raise HTTPException(
            status_code=400,
            detail="Please provide code or a message."
        )

    instructions = {
        "explain": "Explain the provided code step by step in simple language.",
        "fix": "Find errors in the code, explain the problems, and provide corrected code.",
        "generate": "Generate clean, working code according to the user's requirements.",
        "optimize": "Improve the code for readability, efficiency, and performance.",
        "ask": "Answer the user's programming question clearly with examples where useful."
    }

    prompt = f"""
Task: {instructions[data.task]}

Programming Language: {data.language}

User's Instructions:
{data.message}

Code:
{data.code}

Provide a clear and useful programming response.
Use code blocks whenever providing code.
"""

    client = genai.Client(api_key=api_key)

    config = types.GenerateContentConfig(
        temperature=0.3,
        max_output_tokens=4096,
        system_instruction=(
            "You are CodeTogether AI, an expert programming assistant. "
            "Help users understand, debug, generate and optimize code. "
            "Give accurate, beginner-friendly explanations."
        )
    )

    def generate():
        try:
            first_chunk = None
            stream_iterator = None
            empty_response = object()

            # Retry temporary Gemini 503 errors
            for attempt in range(3):
                try:
                    stream = client.models.generate_content_stream(
                        model="gemini-3.8-flash",
                        contents=prompt,
                        config=config
                    )

                    stream_iterator = iter(stream)
                    first_chunk = next(
                        stream_iterator,
                        empty_response
                    )

                    break

                except errors.ServerError as exc:
                    if (
                        getattr(exc, "code", None) != 503
                        or attempt == 2
                    ):
                        raise

                    delay = (2 ** attempt) + random.uniform(0, 1)

                    print(
                        f"Gemini 503 error. Retrying in {delay:.1f} seconds...",
                        flush=True
                    )

                    time.sleep(delay)

            # Send the first chunk
            if first_chunk is not empty_response and first_chunk.text:
                yield first_chunk.text

            # Send remaining chunks progressively
            for chunk in stream_iterator:
                if chunk.text:
                    yield chunk.text

        except Exception as exc:
            print(
                f"Gemini Streaming Error: {type(exc).__name__}: {exc}",
                flush=True
            )

            yield "\n\n[AI response interrupted. Please try again.]"

    return StreamingResponse(
        generate(),
        media_type="text/plain; charset=utf-8"
    )
