from dataclasses import dataclass, field
from typing import Optional, Collection, Any

from bson import ObjectId


@dataclass
class Question:
    question: str
    answer: str
    image: Optional[str]
    _id: ObjectId = field(default_factory=ObjectId)

    def __str__(self):
        return self.question


@dataclass
class ServerConfig:
    _id: int
    leaderboardChannel: Optional[int] = None
    leaderRole: Optional[int] = None


@dataclass
class ServerData:
    config: ServerConfig
    currentQuestion: Optional[Question]
    Scores: Collection[Any]