"""Guest text should retain career evidence while dropping direct identifiers."""

import unittest

from AI_Engine.privacy import redact_guest_text


class GuestPrivacyTests(unittest.TestCase):
    def test_portfolio_contact_details_are_removed_without_losing_projects(self):
        source = (
            "# 함형준 | AI 애플리케이션 · 솔루션 엔지니어\n"
            "**Email** · hamhj7694@example.com\n"
            "**GitHub** · hamhj7694\n"
            "**Phone** · 010-5616-7694\n"
            "**Location** · 서울특별시 동작구\n"
            "Career Memory에서 RAG를 구현하고 처리시간을 65.30% 줄였습니다.\n"
            "CSR에서는 사건 브리핑을 구현했습니다."
        )

        result = redact_guest_text(source)

        for private_value in (
            "함형준", "hamhj7694", "010-5616-7694", "서울특별시 동작구"
        ):
            self.assertNotIn(private_value, result)
        self.assertIn("AI 애플리케이션 · 솔루션 엔지니어", result)
        self.assertIn("Career Memory에서 RAG를 구현하고 처리시간을 65.30% 줄였습니다.", result)
        self.assertIn("CSR에서는 사건 브리핑을 구현했습니다.", result)
        self.assertEqual(len(source), len(result))

    def test_inline_contact_and_resident_number_are_removed(self):
        source = "연락은 tester@example.com, 010 1234 5678로 주세요. 주민번호 900101-1234567."
        result = redact_guest_text(source)
        self.assertNotIn("tester@example.com", result)
        self.assertNotIn("010 1234 5678", result)
        self.assertNotIn("900101-1234567", result)
        self.assertIn("연락은", result)


if __name__ == "__main__":
    unittest.main()
