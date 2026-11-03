"""MongoDB document schemas.

Documents are stored as plain dicts; these models validate data on the
way in (admin forms, contact form) and document the shape of each
collection. Media fields store Cloudinary public_ids; delivery URLs are
built at render time so transformations can change without migrations.
"""
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from utils.text import safe_http_url

Status = Literal["draft", "published"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(BaseModel):
    """Collection: users. Only ADMIN_EMAIL may ever exist here."""
    email: EmailStr
    password_hash: str
    password_version: int = 0
    created_at: datetime = Field(default_factory=utcnow)
    last_login_at: datetime | None = None


class OTP(BaseModel):
    """Collection: otps. TTL index on expires_at purges stale codes."""
    email: EmailStr
    code_hash: str
    attempts: int = 0
    expires_at: datetime
    created_at: datetime = Field(default_factory=utcnow)


class Project(BaseModel):
    """Collection: projects."""
    title: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=90)
    summary: str = Field(default="", max_length=300)
    description: str = ""  # markdown
    category: str = Field(default="", max_length=40)
    tags: list[str] = []
    tech_stack: list[str] = []
    thumbnail: str = ""  # cloudinary public_id
    screenshots: list[str] = []
    live_url: str = ""
    repo_url: str = ""
    embed_url: str = ""  # interactive preview rendered in a sandboxed iframe
    video_url: str = ""
    featured: bool = False
    order: int = 0
    status: Status = "draft"
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @field_validator("live_url", "repo_url", "embed_url", "video_url", mode="before")
    @classmethod
    def _http_only(cls, v):
        return safe_http_url(v)


class BlogPost(BaseModel):
    """Collection: posts. kind=vlog posts lead with an embedded video."""
    title: str = Field(min_length=1, max_length=160)
    slug: str = Field(min_length=1, max_length=90)
    kind: Literal["blog", "vlog"] = "blog"
    excerpt: str = Field(default="", max_length=400)
    content: str = ""  # markdown
    cover_image: str = ""  # cloudinary public_id
    video_url: str = ""
    tags: list[str] = []
    reading_time: int = 1
    status: Status = "draft"
    published_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @field_validator("video_url", mode="before")
    @classmethod
    def _http_only(cls, v):
        return safe_http_url(v)


class Message(BaseModel):
    """Collection: messages (contact form submissions)."""
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    subject: str = Field(default="", max_length=150)
    body: str = Field(min_length=5, max_length=5000)
    read: bool = False
    ip: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class SocialLinks(BaseModel):
    github: str = ""
    linkedin: str = ""
    twitter: str = ""
    youtube: str = ""
    email: str = ""

    @field_validator("github", "linkedin", "twitter", "youtube", mode="before")
    @classmethod
    def _http_only(cls, v):
        return safe_http_url(v)


class Profile(BaseModel):
    """Collection: settings, _id="profile". Drives the hero section."""
    name: str = "Your Name"
    headline: str = "Full-Stack Developer"
    bio: str = "Short bio goes here. Edit it from the admin dashboard."
    about: str = ""  # markdown
    avatar: str = ""  # cloudinary public_id
    location: str = ""
    resume_url: str = ""
    tech_stack: list[str] = ["Python", "FastAPI", "MongoDB", "JavaScript"]
    cta_label: str = "Get in touch"
    available_for_work: bool = True
    socials: SocialLinks = SocialLinks()

    @field_validator("resume_url", mode="before")
    @classmethod
    def _http_only(cls, v):
        return safe_http_url(v)
