import unittest
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from AI_Engine.api.conversation_experiences import (
    ConversationProposalApprove,
    ExperienceUnitApprove,
    approve_chat_experience_proposal,
    approve_experience_unit,
    get_experience_unit_spans,
)
from AI_Engine.api.analysis_runs import list_analysis_runs
from AI_Engine.database.connection import Base
from AI_Engine.database.models import (
    AnalysisRunRecord,
    AnalysisRunTarget,
    Conversation,
    Experience,
    Message,
    User,
)


class ExperienceUnitsApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_approve_unit_is_idempotent_and_links_run_to_experience(self):
        with self.Session() as database:
            user = User(
                id="USER-1", email="unit@example.com", display_name="Unit",
                password_hash="unused", account_type="simple",
            )
            conversation = Conversation(
                id="CONV-1", user_id=user.id, client_request_id=str(uuid4()),
                title="단위 승인", message_count=2, pending_proposal_count=1,
            )
            source_message = Message(
                id="MSG-SOURCE", conversation_id=conversation.id,
                client_request_id=str(uuid4()), sequence=1, role="user",
                status="completed", content="RAG 구조를 설계하고 호출을 줄였다.",
                requested_intent="auto",
            )
            run = AnalysisRunRecord(
                id="ANALYSIS-1", user_id=user.id, client_request_id=str(uuid4()),
                target_type="conversation_experience_units", input_type="conversation",
                input_payload={}, output_payload={"unit_ids": ["UNIT-1", "UNIT-2"]},
                source_ids=["source-MSG-SOURCE"], status="succeeded",
            )
            unit = {
                "unit_id": "UNIT-1", "analysis_run_id": run.id,
                "draft_id": "DRAFT-1", "domain": {"name": "AI"},
                "project": {"name": "Career Memory"}, "title": "RAG 구조 설계",
                "summary": "RAG 구조를 설계했다.", "actions": ["구조를 설계했다."],
                "results": ["호출을 줄였다."], "facts": [], "skills": ["RAG"],
                "source_ref_ids": ["source-MSG-SOURCE"],
                "source_refs": [{
                    "id": "source-MSG-SOURCE", "source_type": "message_text",
                    "message_id": source_message.id, "title": "대화 메시지 1",
                }],
                "field_citations": {}, "primary_span_ids": ["SPAN-1"],
                "context_span_ids": [], "field_span_ids": {}, "status": "pending",
                "saved_experience_id": None, "saved_at": None,
            }
            proposal = {
                "id": "PROPOSAL-1", "contract_version": "experience-units-v2",
                "version": 1, "status": "pending", "analysis_run_id": run.id,
                "source_snapshots": [{
                    "source_id": "source-MSG-SOURCE",
                    "message_id": source_message.id,
                    "text_hash": sha256(source_message.content.encode("utf-8")).hexdigest(),
                    "spans": [{
                        "id": "SPAN-1", "category": "unresolved",
                        "char_start": 0,
                        "char_end": len(source_message.content),
                    }],
                }],
                "units": [unit],
                "coverage": {"review_status": "pending", "failed_batch_ids": []},
            }
            assistant = Message(
                id="MSG-AI", conversation_id=conversation.id, sequence=2,
                role="assistant", status="completed", content="분석 완료",
                requested_intent="auto",
                actions=[{"type": "experience_units_proposal", "proposal": proposal}],
            )
            database.add_all([user, conversation, source_message, run, assistant])
            database.commit()

            spans = get_experience_unit_spans(
                conversation.id, assistant.id, current_user=user, database=database,
            )

            result = approve_experience_unit(
                conversation.id, assistant.id,
                ExperienceUnitApprove(version=1, unit_id="UNIT-1"),
                current_user=user, database=database,
            )
            replay = approve_experience_unit(
                conversation.id, assistant.id,
                ExperienceUnitApprove(version=1, unit_id="UNIT-1"),
                current_user=user, database=database,
            )
            unclaimed = list_analysis_runs(
                target_type="conversation_experience_units",
                unclaimed_only=True,
                include_payload=True,
                limit=20,
                current_user=user,
                database=database,
            )

            experience = database.scalar(select(Experience))
            link = database.scalar(select(AnalysisRunTarget))
            self.assertFalse(result["replayed"])
            self.assertEqual(spans["items"][0]["text"], "RAG 구조를 설계하고 호출을 줄였다.")
            self.assertTrue(replay["replayed"])
            self.assertEqual(database.query(Experience).count(), 1)
            self.assertEqual(link.unit_id, "UNIT-1")
            self.assertEqual(link.target_id, experience.id)
            self.assertEqual(run.target_id, experience.id)
            self.assertEqual(experience.extensions["experience_unit_v2"]["unit_id"], "UNIT-1")
            self.assertEqual(unclaimed["items"][0]["targets"][0]["unit_id"], "UNIT-1")

    def test_span_lookup_rejects_source_changed_after_analysis(self):
        with self.Session() as database:
            user = User(
                id="USER-HASH", email="hash@example.com", display_name="Hash",
                password_hash="unused", account_type="simple",
            )
            conversation = Conversation(
                id="CONV-HASH", user_id=user.id, client_request_id=str(uuid4()),
                title="해시 검증", message_count=2, pending_proposal_count=1,
            )
            source_message = Message(
                id="MSG-HASH-SOURCE", conversation_id=conversation.id, sequence=1,
                role="user", status="completed", content="분석 당시 원문",
                requested_intent="experience",
            )
            proposal = {
                "id": "PROPOSAL-HASH", "contract_version": "experience-units-v2",
                "version": 1, "status": "pending", "analysis_run_id": "RUN-HASH",
                "source_snapshots": [{
                    "source_id": "source-MSG-HASH-SOURCE",
                    "message_id": source_message.id,
                    "text_hash": sha256(source_message.content.encode("utf-8")).hexdigest(),
                    "spans": [{
                        "id": "SPAN-HASH", "category": "unresolved",
                        "char_start": 0, "char_end": len(source_message.content),
                    }],
                }],
                "units": [],
                "coverage": {"review_status": "pending", "failed_batch_ids": []},
            }
            assistant = Message(
                id="MSG-HASH-AI", conversation_id=conversation.id, sequence=2,
                role="assistant", status="completed", content="분석 완료",
                requested_intent="auto",
                actions=[{"type": "experience_units_proposal", "proposal": proposal}],
            )
            database.add_all([user, conversation, source_message, assistant])
            database.commit()
            source_message.content = "분석 뒤 변경된 원문"
            database.commit()

            with self.assertRaisesRegex(Exception, "원문이 분석 이후 변경") as raised:
                get_experience_unit_spans(
                    conversation.id, assistant.id, current_user=user, database=database,
                )
            self.assertEqual(raised.exception.status_code, 409)

    def test_legacy_index_contract_remains_approvable(self):
        with self.Session() as database:
            user = User(
                id="USER-OLD", email="old@example.com", display_name="Old",
                password_hash="unused", account_type="simple",
            )
            conversation = Conversation(
                id="CONV-OLD", user_id=user.id, client_request_id=str(uuid4()),
                title="기존 제안", message_count=1, pending_proposal_count=1,
            )
            proposal = {
                "id": "OLD-PROPOSAL", "version": 1,
                "type": "create_experiences", "status": "pending",
                "approved_experience_indexes": [],
                "payload": {"experiences": [{
                    "draft_id": "OLD-DRAFT", "domain": {"name": "기존 분류"},
                    "project": {"name": "기존 프로젝트"}, "title": "기존 경험",
                    "source_ref_ids": [], "source_refs": [],
                }]},
            }
            assistant = Message(
                id="MSG-OLD", conversation_id=conversation.id, sequence=1,
                role="assistant", status="completed", content="기존 분석",
                requested_intent="experience",
                actions=[{"type": "experience_proposal", "proposal": proposal}],
            )
            database.add_all([user, conversation, assistant])
            database.commit()

            result = approve_chat_experience_proposal(
                conversation.id, assistant.id,
                ConversationProposalApprove(
                    version=1, draft_id="OLD-DRAFT", experience_index=0,
                ),
                current_user=user, database=database,
            )

            self.assertFalse(result["replayed"])
            self.assertEqual(result["proposal"]["status"], "approved")
            self.assertEqual(database.query(Experience).count(), 1)


if __name__ == "__main__":
    unittest.main()
