import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("deploy_ssm", Path(__file__).parents[1] / "deploy-ssm.py")
deploy_ssm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy_ssm)


class SsmDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.env = dict(
            AWS_REGION="ap-northeast-2", AWS_ROLE_ARN="arn:aws:iam::123456789012:role/deploy",
            API_REPOSITORY="career-memory-api", WEB_REPOSITORY="career-memory-web",
            EC2_INSTANCE_ID="i-0123456789abcdef0", SSM_DOCUMENT_NAME="CareerMemory-Deploy",
            SSM_DOCUMENT_VERSION="1", RELEASE_ID="a" * 40 + "-123-1",
            API_DIGEST="sha256:" + "b" * 64, WEB_DIGEST="sha256:" + "c" * 64,
        )

    def run_states(self, states):
        calls = []

        def call(*args):
            calls.append(args)
            if args[1] == "send-command":
                return {"Command": {"CommandId": "command-id"}}
            state = next(states)
            if isinstance(state, Exception):
                raise state
            return state

        result = deploy_ssm.deploy(self.env, call=call, sleep=lambda _: None)
        return result, calls

    def test_eventual_consistency_then_success(self):
        result, calls = self.run_states(iter([
            RuntimeError("InvocationDoesNotExist"), {"Status": "InProgress"},
            {"Status": "Success", "ResponseCode": 0},
        ]))
        self.assertEqual(result, "command-id")
        params = json.loads(calls[0][calls[0].index("--parameters") + 1])
        self.assertEqual(params["ApiDigest"], [self.env["API_DIGEST"]])
        self.assertEqual(calls[0][calls[0].index("--document-version") + 1], "1")

    def test_terminal_failures_and_nonzero_success_fail_the_job(self):
        for status, code in [("Failed", 1), ("TimedOut", -1), ("Cancelled", -1), ("Success", 1)]:
            with self.subTest(status=status), self.assertRaises(RuntimeError):
                self.run_states(iter([{"Status": status, "ResponseCode": code}]))

    def test_access_denied_is_not_retried_as_eventual_consistency(self):
        with self.assertRaisesRegex(RuntimeError, "AccessDenied"):
            self.run_states(iter([RuntimeError("AccessDenied")]))

    def test_timeout_is_failure_and_does_not_cancel_host_rollback(self):
        calls = []

        def call(*args):
            calls.append(args)
            return {"Command": {"CommandId": "command-id"}}

        with self.assertRaises(TimeoutError):
            deploy_ssm.deploy(self.env, call=call, timeout=0)
        self.assertEqual(len(calls), 1)

    def test_missing_and_injected_settings_are_rejected_before_aws(self):
        for key in self.env:
            for bad in ["", "value; touch /tmp/injected", "$(id)"]:
                with self.subTest(key=key), self.assertRaises(ValueError):
                    deploy_ssm.validate({**self.env, key: bad})


if __name__ == "__main__":
    unittest.main()
