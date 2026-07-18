"""Filter API routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas import FilterExecuteRequest, FilterGenerateRequest, FilterResponse
from app.services.filter.registry import FilterRegistry
from app.services.llm.manager import llm_manager
from app.utils.exceptions import BadRequestException, NotFoundException

router = APIRouter(prefix="/filters", tags=["filters"])


@router.post("/generate", response_model=FilterResponse)
async def generate_filter(
    req: FilterGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate filter script from natural language description."""
    llm = llm_manager.get()
    registry = FilterRegistry(db, llm)

    # Check for similar existing script
    similar = await registry.find_similar(req.nl_description)
    if similar:
        return similar

    script = await registry.generate_and_save(req.name, req.nl_description)
    return script


@router.get("", response_model=list[FilterResponse])
async def list_filters(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all filter scripts."""
    registry = FilterRegistry(db, llm_manager.get())
    return await registry.list_all()


@router.get("/{script_id}", response_model=FilterResponse)
async def get_filter(
    script_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get filter script details."""
    from app.models.filter import FilterScript
    script = await db.get(FilterScript, script_id)
    if not script:
        raise NotFoundException(f"Filter script {script_id} not found")
    return script


@router.post("/{script_id}/execute")
async def execute_filter(
    script_id: int,
    req: FilterExecuteRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Execute a filter script and return results."""
    registry = FilterRegistry(db, llm_manager.get())
    try:
        result_df = await registry.execute(script_id, req.params if req else None)
        return {
            "count": len(result_df),
            "columns": result_df.columns.tolist(),
            "data": result_df.head(100).to_dict(orient="records"),
        }
    except ValueError as e:
        raise BadRequestException(str(e))


@router.delete("/{script_id}")
async def delete_filter(
    script_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a filter script."""
    from app.models.filter import FilterScript
    script = await db.get(FilterScript, script_id)
    if not script:
        raise NotFoundException(f"Filter script {script_id} not found")
    await db.delete(script)
    return {"status": "deleted"}
