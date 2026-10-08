"""경량 기술 온톨로지의 보수적인 초기 seed 정의."""

from __future__ import annotations

from dataclasses import dataclass


ONTOLOGY_VERSION = "career-ontology-v1"


@dataclass(frozen=True)
class SkillDefinition:
    id: str
    canonical_name: str
    aliases: tuple[str, ...] = ()
    related_skill_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class RelationDefinition:
    source_concept_id: str
    relation_type: str
    target_concept_id: str
    matching_policy: str = "explicit_only"


# 미등록 표현은 이 목록의 가장 가까운 기술로 추정하지 않는다.
SKILL_REGISTRY: tuple[SkillDefinition, ...] = (
    SkillDefinition("skill-python", "Python", ("파이썬",)),
    SkillDefinition(
        "skill-fastapi",
        "FastAPI",
        ("Fast API", "패스트API", "패스트 API", "페스트API", "페스트 API"),
        ("skill-python", "skill-rest-api"),
    ),
    SkillDefinition(
        "skill-rest-api",
        "REST API",
        ("RESTful API", "레스트 API", "레스트API"),
        ("skill-fastapi", "skill-flask", "skill-django"),
    ),
    SkillDefinition(
        "skill-javascript",
        "JavaScript",
        ("Javascript", "JS", "자바스크립트"),
        ("skill-typescript",),
    ),
    SkillDefinition(
        "skill-typescript",
        "TypeScript",
        ("Typescript", "TS", "타입스크립트"),
        ("skill-javascript",),
    ),
    SkillDefinition("skill-react", "React", ("React.js", "ReactJS", "리액트")),
    SkillDefinition(
        "skill-flask",
        "Flask",
        ("플라스크",),
        ("skill-python", "skill-rest-api"),
    ),
    SkillDefinition(
        "skill-django",
        "Django",
        ("장고",),
        ("skill-python", "skill-rest-api"),
    ),
    SkillDefinition(
        "skill-nodejs",
        "Node.js",
        ("NodeJS", "Node JS", "노드JS", "노드.js"),
        ("skill-javascript", "skill-typescript"),
    ),
    SkillDefinition(
        "skill-python-web-framework",
        "Python Web Framework",
        ("Python 웹 프레임워크", "파이썬 웹 프레임워크"),
    ),
)


ONTOLOGY_RELATIONS: tuple[RelationDefinition, ...] = tuple(
    relation
    for framework_id in ("skill-fastapi", "skill-flask", "skill-django")
    for relation in (
        RelationDefinition(
            framework_id,
            "narrower_than",
            "skill-python-web-framework",
        ),
        RelationDefinition(
            "skill-python-web-framework",
            "broader_than",
            framework_id,
        ),
    )
)


__all__ = [
    "ONTOLOGY_RELATIONS",
    "ONTOLOGY_VERSION",
    "RelationDefinition",
    "SKILL_REGISTRY",
    "SkillDefinition",
]
