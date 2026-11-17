
import os
import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

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

    try:
        client = genai.Client(api_key=api_key)

        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=4096,
                system_instruction=(
                    "You are CodeTogether AI, an expert programming assistant. "
                    "Help users understand, debug, generate and optimize code. "
                    "Give accurate, beginner-friendly explanations."
                )
            )
        )

        answer = response.text

        if not answer:
            raise HTTPException(
                status_code=502,
                detail="Gemini returned an empty response."
            )

        return {
            "success": True,
            "response": answer
        }

    except HTTPException:
        raise

    except Exception as exc:
        print(
            f"Gemini API Error: {type(exc).__name__}: {exc}",
            flush=True
        )
        raise HTTPException(
            status_code=502,
            detail="Unable to get a response from Gemini. Please try again."
        )
