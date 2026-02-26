from pydantic import BaseModel


class SearchResultItem(BaseModel):
    id: int
    title: str
    type: str
    category: str | None = None
    done: bool | None = None
    email: str | None = None
    relationship: str | None = None
    status: str | None = None


class SearchResponse(BaseModel):
    query: str
    total: int
    results: list[SearchResultItem]
