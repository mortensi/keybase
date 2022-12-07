from typing import Optional, List
from redis_om import (JsonModel, Field)
from src.common.config import get_db
from src.common.utils import ShortUuidPk
from src.version.version import Version


class Document(JsonModel):
    name: str = Field(index=True, full_text_search=True)
    content: Optional[str] = Field(index=True, full_text_search=True)
    content_embedding: Optional[str]
    creation: int = Field(index=True, sortable=True)
    last: int = Field(index=True, sortable=True)
    tags: Optional[str] = Field(index=True)
    category: Optional[str] = Field(index=True)
    processable: int = Field(index=True)
    state: str = Field(index=True, default="draft")
    author: str = Field(index=True)
    owner: str = Field(index=True)
    versions: Optional[List[Version]]

    class Meta:
        database = get_db()
        global_key_prefix = "keybase"
        model_key_prefix = "json"
        index_name = "document_idx"
        primary_key_creator_cls = ShortUuidPk