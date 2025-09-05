import os
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Path
from pydantic import BaseModel, EmailStr
from dotenv import load_dotenv

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "container_postgresql")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "testuser")
DB_PASS = os.getenv("DB_PASSWORD", "testpass")
DB_NAME = os.getenv("DB_NAME", "testdb")
POOL_MIN = int(os.getenv("DB_POOL_MIN", "1"))
POOL_MAX = int(os.getenv("DB_POOL_MAX", "10"))

CONNINFO = (
    f"host={DB_HOST} port={DB_PORT} user={DB_USER} "
    f"password={DB_PASS} dbname={DB_NAME}"
)

# สร้าง Async pool ระดับโมดูล
pool = AsyncConnectionPool(
    CONNINFO,
    min_size=POOL_MIN,
    max_size=POOL_MAX,
    kwargs={"autocommit": True},
)

app = FastAPI(title="FastAPI + PostgreSQL (Async)", version="1.0.0")

class CreateUserBody(BaseModel):
    username: str
    email: EmailStr

@app.on_event("startup")
async def on_startup():
    # เปิด pool ล่วงหน้า ป้องกัน cold path latency
    await pool.open()

@app.on_event("shutdown")
async def on_shutdown():
    await pool.close()

@app.get("/")
async def root() -> Dict[str, Any]:
    return {"message": "Hello World from Python (FastAPI + PostgreSQL, async)"}

@app.post("/users", status_code=201)
async def create_user(body: CreateUserBody):
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO users (username, email) VALUES (%s, %s) RETURNING user_id;",
                    (body.username, body.email),
                )
                user_id = (await cur.fetchone())[0]
        return {"message": "User created successfully", "user_id": user_id}
    except psycopg.errors.UniqueViolation:
        # email ซ้ำ
        raise HTTPException(status_code=409, detail="Email already exists")
    except Exception:
        raise HTTPException(status_code=500, detail="Database error")

@app.get("/users/{user_id}")
async def get_user(user_id: int = Path(..., ge=1)):
    try:
        async with pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT user_id, username, email FROM users WHERE user_id = %s;",
                    (user_id,),
                )
                row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        return row
    except Exception:
        raise HTTPException(status_code=500, detail="Database error")
