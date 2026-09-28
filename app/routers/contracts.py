# =============================================================================
# app/routers/contracts.py
# -----------------------------------------------------------------------------
# Contracts (PO payment-milestone tracker) endpoints. Mounted at
# /api/v1/contracts. Reads need any authenticated user; writes need ADMIN,
# MANAGER, PURCHASER or FINANCE — the same roles that can act on Purchase
# Orders, since a contract here tracks a customer PO's billing milestones.
#
#   GET    /                                list  (?q=&skip=&limit=)
#   GET    /kpis                            headline totals
#   POST   /                                create a contract
#   GET    /{id}                            get one contract with its milestones
#   PUT    /{id}                            edit a contract
#   DELETE /{id}                            delete a contract (and its milestones)
#   POST   /{id}/milestones                 add a milestone
#   PUT    /{id}/milestones/{milestone_id}  edit a milestone
#   DELETE /{id}/milestones/{milestone_id}  remove a milestone
# =============================================================================

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user, require_roles
from app.models.enums import UserRole
from app.schemas.contract import (
    ContractCreate,
    ContractKPIs,
    ContractListResponse,
    ContractMilestoneCreate,
    ContractResponse,
    ContractUpdate,
)
from app.services import contract_service as svc

router = APIRouter()

_write_roles = require_roles(UserRole.ADMIN, UserRole.MANAGER, UserRole.PURCHASER, UserRole.FINANCE)


@router.get("", response_model=ContractListResponse, summary="List contracts")
async def list_contracts(
    q: Optional[str] = Query(None, description="Search file ref, customer or PO number"),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await svc.list_contracts(db, search=q, skip=skip, limit=limit)


@router.get("/kpis", response_model=ContractKPIs, summary="Contract KPIs")
async def kpis(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    return await svc.get_kpis(db)


@router.post("", response_model=ContractResponse, status_code=status.HTTP_201_CREATED, summary="Create a contract")
async def create_contract(payload: ContractCreate, db: AsyncSession = Depends(get_db), user=Depends(_write_roles)):
    return await svc.create_contract(db, payload, user.id)


@router.get("/{contract_id}", response_model=ContractResponse, summary="Get a contract")
async def get_contract(contract_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    return await svc.get_contract(db, contract_id)


@router.put("/{contract_id}", response_model=ContractResponse, summary="Edit a contract")
async def update_contract(
    contract_id: uuid.UUID, payload: ContractUpdate, db: AsyncSession = Depends(get_db), user=Depends(_write_roles),
):
    return await svc.update_contract(db, contract_id, payload, user.id)


@router.delete("/{contract_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a contract")
async def delete_contract(contract_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(_write_roles)):
    await svc.delete_contract(db, contract_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{contract_id}/milestones", response_model=ContractResponse,
             status_code=status.HTTP_201_CREATED, summary="Add a milestone")
async def add_milestone(
    contract_id: uuid.UUID, payload: ContractMilestoneCreate,
    db: AsyncSession = Depends(get_db), user=Depends(_write_roles),
):
    return await svc.add_milestone(db, contract_id, payload, user.id)


@router.put("/{contract_id}/milestones/{milestone_id}", response_model=ContractResponse, summary="Edit a milestone")
async def update_milestone(
    contract_id: uuid.UUID, milestone_id: uuid.UUID, payload: ContractMilestoneCreate,
    db: AsyncSession = Depends(get_db), user=Depends(_write_roles),
):
    return await svc.update_milestone(db, contract_id, milestone_id, payload, user.id)


@router.delete("/{contract_id}/milestones/{milestone_id}", response_model=ContractResponse, summary="Remove a milestone")
async def delete_milestone(
    contract_id: uuid.UUID, milestone_id: uuid.UUID, db: AsyncSession = Depends(get_db), user=Depends(_write_roles),
):
    return await svc.delete_milestone(db, contract_id, milestone_id, user.id)
