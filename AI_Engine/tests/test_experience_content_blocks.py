import unittest

from AI_Engine.knowledge_documents import (
    experience_content_blocks,
    sanitize_experience_content_blocks,
)


class ExperienceContentBlocksTests(unittest.TestCase):
    def test_empty_projection_fields_do_not_create_cards(self):
        self.assertEqual(experience_content_blocks({}), [])

    def test_internal_lineage_extension_is_not_projected_for_people(self):
        blocks = experience_content_blocks({
            "extensions": {
                "experience_unit_v2": {"unit_id": "UNIT-1"},
                "public_note": "사용자에게 보여 줄 정보",
            },
        })

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["data"]["value"], {"public_note": "사용자에게 보여 줄 정보"})

    def test_existing_internal_only_properties_block_is_hidden(self):
        visible = sanitize_experience_content_blocks([{
            "id": "core-extensions",
            "type": "properties",
            "origin": "system_projection",
            "data": {
                "title": "추가 정보",
                "value": {"experience_unit_v2": {"unit_id": "UNIT-1"}},
            },
        }])

        self.assertEqual(visible, [])


if __name__ == "__main__":
    unittest.main()
