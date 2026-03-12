"""수집된 Threads 포스트(post) 데이터 모델."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ThreadPost:
    """수집된 Threads 포스트(post) 데이터.

    text에는 본문 + 작성자 self-reply가 합쳐져 있다.
    replies 필드에 개별 self-reply 텍스트를 보관한다.
    """

    post_id: str
    author: str
    text: str
    url: str
    saved_at: datetime
    media_urls: list[str] = field(default_factory=list)
    replies: list[str] = field(default_factory=list)
    reply_count: int = 0
    link_contents: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        """직렬화(serialization)용 딕셔너리로 변환한다."""
        return {
            "post_id": self.post_id,
            "author": self.author,
            "text": self.text,
            "url": self.url,
            "saved_at": self.saved_at.isoformat(),
            "media_urls": self.media_urls,
            "replies": self.replies,
            "reply_count": self.reply_count,
            "link_contents": self.link_contents,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ThreadPost":
        """딕셔너리에서 ThreadPost를 역직렬화(deserialization)한다."""
        return cls(
            post_id=d["post_id"],
            author=d["author"],
            text=d["text"],
            url=d["url"],
            saved_at=datetime.fromisoformat(d["saved_at"]),
            media_urls=d.get("media_urls", []),
            replies=d.get("replies", []),
            reply_count=d.get("reply_count", 0),
            link_contents=d.get("link_contents", []),
        )
