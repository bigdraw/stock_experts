"""Book and Agent API routes."""

import json
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.database import get_db
from app.models.agent import Agent
from app.models.user import User
from app.schemas import AgentCreateRequest, AgentResponse
from app.services.book.analyzer import BookAnalyzer
from app.services.book.parser import BookParser
from app.services.llm.manager import llm_manager
from app.services.llm.provider import LLMMessage
from app.utils.exceptions import BadRequestException, NotFoundException

router = APIRouter(tags=["books & agents"])

UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# --- Books ---
@router.post("/books/upload")
async def upload_book(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
):
    """Upload a book file (PDF/EPUB/TXT)."""
    ext = Path(file.filename).suffix.lower()
    if ext not in (".pdf", ".epub", ".txt"):
        raise BadRequestException(f"Unsupported format: {ext}. Use PDF, EPUB, or TXT.")

    file_path = UPLOAD_DIR / f"{current_user.id}_{file.filename}"
    content = await file.read()
    file_path.write_bytes(content)

    return {"filename": file.filename, "path": str(file_path), "status": "uploaded"}


@router.post("/books/generate-agent")
async def generate_agent_from_book(
    file_path: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Analyze uploaded book and generate investment agent."""
    if not Path(file_path).exists():
        raise NotFoundException(f"File not found: {file_path}")

    parser = BookParser()
    content = parser.parse(file_path)

    llm = llm_manager.get()
    analyzer = BookAnalyzer(llm)
    agent_def = await analyzer.analyze(content)

    agent = Agent(
        name=agent_def.get("name", content.title),
        type="book_generated",
        description=agent_def.get("description", ""),
        system_prompt=agent_def.get("system_prompt", ""),
        config=json.dumps(agent_def.get("config", {})),
    )
    db.add(agent)
    await db.flush()
    await db.refresh(agent)
    return agent


class AgentFromTextRequest(BaseModel):
    """用户自定义文本（投资理念/公式/一大段认可的投资逻辑）→ 构造 agent（idea4）。"""

    title: str
    text: str = Field(..., min_length=20, description="投资理念/公式/逻辑文本")
    description: str | None = None


@router.post("/books/generate-agent-from-text", response_model=AgentResponse)
async def generate_agent_from_text(
    req: AgentFromTextRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """从用户粘贴的文本构造投资 agent（不依赖书籍文件）。

    复用 BookAnalyzer.analyze——把用户文本包成 BookContent（format='text'），
    走同一套分块+综合逻辑。适合用户直接写一段认可的投资理念/公式来造 agent。
    """
    from app.services.book.parser import BookContent

    llm = llm_manager.get()
    analyzer = BookAnalyzer(llm)
    content = BookContent(title=req.title, text=req.text, format="text")
    agent_def = await analyzer.analyze(content)

    agent = Agent(
        name=req.title,
        type="text_generated",
        description=req.description or agent_def.get("description", ""),
        system_prompt=agent_def.get("system_prompt", ""),
        config=json.dumps(agent_def.get("config", {})),
    )
    db.add(agent)
    await db.flush()
    await db.refresh(agent)
    return agent


# --- Agents ---
@router.post("/agents", response_model=AgentResponse)
async def create_agent(
    req: AgentCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create agent from natural language description."""
    llm = llm_manager.get()
    response = await llm.chat(
        [
            LLMMessage(
                role="system",
                content="""你是投资 Agent 定义专家。根据用户的自然语言描述，生成投资 Agent 的 system_prompt。
输出 JSON：{"system_prompt": "...", "config": {"style": "...", "risk_tolerance": "...", "holding_period": "..."}}
只输出 JSON。""",
            ),
            LLMMessage(role="user", content=req.nl_description),
        ]
    )
    try:
        agent_def = json.loads(response.content)
    except json.JSONDecodeError:
        agent_def = {"system_prompt": response.content, "config": {}}

    agent = Agent(
        name=req.name,
        type="manual",
        description=req.description or req.nl_description,
        system_prompt=agent_def.get("system_prompt", response.content),
        config=json.dumps(agent_def.get("config", {})),
    )
    db.add(agent)
    await db.flush()
    await db.refresh(agent)
    return agent


@router.get("/agents", response_model=list[AgentResponse])
async def list_agents(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all agents."""
    result = await db.execute(select(Agent).where(Agent.is_active))
    return result.scalars().all()


@router.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get agent details."""
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise NotFoundException(f"Agent {agent_id} not found")
    return agent


@router.delete("/agents/{agent_id}")
async def delete_agent(
    agent_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete (deactivate) an agent."""
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise NotFoundException(f"Agent {agent_id} not found")
    agent.is_active = False
    return {"status": "deleted"}
