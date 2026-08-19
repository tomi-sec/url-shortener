"""Pydantic request/response models for the API.

Pydantic's BaseModel requires type annotations on its fields - the one
place in this project that breaks from the rest of the portfolio's
no-type-hints style, because the framework itself needs the annotations
for validation and the generated OpenAPI docs.
"""

from pydantic import BaseModel, HttpUrl


class CreateLinkRequest(BaseModel):
    long_url: HttpUrl


class CreateLinkResponse(BaseModel):
    short_code: str
    long_url: str


class StatsResponse(BaseModel):
    short_code: str
    long_url: str
    click_count: int
    created_at: str
