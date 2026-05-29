from fastapi import APIRouter, HTTPException, status
from typing import List, Dict, Any
from ...service import nodes
from nodes import get_nodes_summary, get_node_details

router = APIRouter()

@router.get("", response_model=List[Dict[str, Any]])
async def get_all_nodes_summary():
    """Returns basic card summaries for the worker array."""
    try:
        return await get_nodes_summary()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed getting cluster map summary: {str(e)}"
        )

@router.get("/{node_id}", response_model=Dict[str, Any])
async def get_single_node_details(node_id: str):
    """Returns heavy hardware specifics for an isolated modal query."""
    try:
        details = await get_node_details(node_id)
        if not details:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Requested worker node '{node_id}' is invalid or not whitelisted."
            )
        return details
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed pulling system details for {node_id}: {str(e)}"
        )