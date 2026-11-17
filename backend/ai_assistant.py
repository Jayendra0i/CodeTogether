


from typing import Literal

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from backend.rule_based_ai import process_ai_request




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
    

    if not data.code.strip() and not data.message.strip():
        raise HTTPException(
            status_code=400,
            detail="Please provide code or a message."
        )

    try:
        answer = process_ai_request(
            task=data.task,
            language=data.language,
            code=data.code,
            message=data.message
        )

        return StreamingResponse(
            iter([answer]),
            media_type="text/plain; charset=utf-8"
        )

    except Exception as exc:
        print(
            f"CodeTogether AI Error: {type(exc).__name__}: {exc}",
            flush=True
        )

        raise HTTPException(
            status_code=500,
            detail="CodeTogether AI could not process your request."
        )
