"""확정 경험 검색 문서와 Chroma retriever 동기화를 검증한다."""

from __future__ import annotations

import gc
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from langchain_core.embeddings import Embeddings
from pydantic import ValidationError

from AI_Engine.job_analysis_ai import (
    JobAnalysisAI,
    JobAnalysisAIInputError,
    build_experience_search_documents,
    create_experience_retriever,
    sync_experience_vector_store,
)
from AI_Engine.schemas import ExperienceSearchDocument


class KeywordEmbeddings(Embeddings):
    """외부 API 없이 키워드 방향만 구분하는 테스트 임베딩."""

    def __init__(self) -> None:
        self.embedded_document_count = 0
        self.embedded_query_count = 0

    @staticmethod
    def _vector(text: str) -> list[float]:
        return [
            float("퍼널" in text or "전환율" in text),
            float("협업" in text or "커뮤니케이션" in text),
            float("사용자 조사" in text),
            0.01,
        ]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.embedded_document_count += len(texts)
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        self.embedded_query_count += 1
        return self._vector(text)


def confirmed_experience(
    experience_id: str,
    *,
    title: str,
    summary: str,
    evidence_id: str,
):
    return {
        "id": experience_id,
        "status": "confirmed",
        "domainName": "직장 경험",
        "projectName": "서비스 개선",
        "title": title,
        "summary": summary,
        "situation": "",
        "actions": [],
        "results": [],
        "role": "서비스 기획",
        "skills": [],
        "facts": [],
        "evidenceIds": [evidence_id],
    }


class ExperienceSearchDocumentTests(unittest.TestCase):
    def test_frontend_experience_becomes_search_document(self) -> None:
        documents = build_experience_search_documents(
            [
                confirmed_experience(
                    "experience-1",
                    title="지원 전환율 개선",
                    summary="지원 퍼널을 분석해 완료율을 높였습니다.",
                    evidence_id="evidence-1",
                )
            ]
        )

        self.assertEqual(len(documents), 1)
        document = documents[0]
        self.assertEqual(document.id, "experience-1")
        self.assertIn("[경험 분류]\n직장 경험", document.page_content)
        self.assertIn("[요약]", document.page_content)
        self.assertEqual(
            document.metadata["experience_id"],
            "experience-1",
        )
        self.assertIn(
            "evidence-1",
            document.metadata["evidence_ids_json"],
        )
        self.assertEqual(len(document.metadata["content_hash"]), 64)

    def test_draft_experience_is_rejected(self) -> None:
        experience = confirmed_experience(
            "experience-draft",
            title="초안",
            summary="아직 확정하지 않은 내용",
            evidence_id="evidence-1",
        )
        experience["status"] = "draft"

        with self.assertRaises(JobAnalysisAIInputError):
            build_experience_search_documents([experience])

    def test_experience_without_evidence_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            ExperienceSearchDocument(
                experience_id="experience-1",
                title="지원 전환율 개선",
                evidence_ids=[],
            )


class ExperienceChromaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.embeddings = KeywordEmbeddings()
        self.collection_name = f"career_memory_{uuid4().hex}"
        self.temp_directory = tempfile.TemporaryDirectory(
            ignore_cleanup_errors=True
        )
        self.persist_directory = str(
            Path(self.temp_directory.name) / "chroma"
        )
        self.experiences = [
            confirmed_experience(
                "experience-funnel",
                title="지원 전환율 개선",
                summary="지원 퍼널을 분석해 전환율을 높였습니다.",
                evidence_id="evidence-funnel",
            ),
            confirmed_experience(
                "experience-collaboration",
                title="협업 프로세스 개선",
                summary="개발·디자인 조직의 커뮤니케이션을 개선했습니다.",
                evidence_id="evidence-collaboration",
            ),
        ]

    def tearDown(self) -> None:
        gc.collect()
        self.temp_directory.cleanup()

    def test_retriever_returns_relevant_confirmed_experience(self) -> None:
        retriever = create_experience_retriever(
            self.experiences,
            persist_directory=self.persist_directory,
            embeddings=self.embeddings,
            collection_name=self.collection_name,
            search_k=1,
        )

        documents = retriever.invoke("퍼널 분석과 전환율 개선")

        self.assertEqual(len(documents), 1)
        self.assertEqual(
            documents[0].metadata["experience_id"],
            "experience-funnel",
        )
        normalized_candidates = JobAnalysisAI._normalize_candidates(
            documents
        )
        self.assertEqual(
            normalized_candidates[0]["evidence_ids"],
            ["evidence-funnel"],
        )
        self.assertEqual(self.embeddings.embedded_query_count, 1)

    def test_same_content_is_not_embedded_twice(self) -> None:
        first_store = sync_experience_vector_store(
            self.experiences,
            persist_directory=self.persist_directory,
            embeddings=self.embeddings,
            collection_name=self.collection_name,
        )
        self.assertEqual(first_store._collection.count(), 2)
        first_embedding_count = self.embeddings.embedded_document_count

        second_store = sync_experience_vector_store(
            self.experiences,
            persist_directory=self.persist_directory,
            embeddings=self.embeddings,
            collection_name=self.collection_name,
        )

        self.assertEqual(second_store._collection.count(), 2)
        self.assertEqual(
            self.embeddings.embedded_document_count,
            first_embedding_count,
        )

    def test_changed_and_deleted_experiences_are_synchronized(self) -> None:
        sync_experience_vector_store(
            self.experiences,
            persist_directory=self.persist_directory,
            embeddings=self.embeddings,
            collection_name=self.collection_name,
        )
        initial_embedding_count = self.embeddings.embedded_document_count
        changed_experience = confirmed_experience(
            "experience-funnel",
            title="지원 전환율 개선",
            summary="지원 퍼널을 다시 설계해 전환율을 18% 높였습니다.",
            evidence_id="evidence-funnel",
        )

        vector_db = sync_experience_vector_store(
            [changed_experience],
            persist_directory=self.persist_directory,
            embeddings=self.embeddings,
            collection_name=self.collection_name,
        )

        stored = vector_db.get(include=["metadatas"])
        self.assertEqual(stored["ids"], ["experience-funnel"])
        self.assertEqual(
            self.embeddings.embedded_document_count,
            initial_embedding_count + 1,
        )


if __name__ == "__main__":
    unittest.main()
