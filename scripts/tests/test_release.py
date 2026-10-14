"""Run the actual Bash orchestration with fake Docker/AWS; never needs cloud credentials."""
import json
import gzip
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
OLD = "a" * 40 + "-100-1"
NEW = "b" * 40 + "-101-1"
API = "sha256:" + "c" * 64
WEB = "sha256:" + "d" * 64
FAKE_DOCKER = r'''
import json, os, pathlib, shutil, sys
args = sys.argv[1:]
with open(os.environ["CALL_LOG"], "a") as stream:
    stream.write(json.dumps(args) + "\n")
failure = os.environ.get("FAIL_STAGE", "")
if args[0] in {"login", "load"}:
    sys.stdin.read()
elif args[0] == "create":
    print("test-container")
elif args[0] == "cp":
    shutil.copytree(os.environ["BUNDLE"], args[2], dirs_exist_ok=True)
elif args[0] == "volume":
    sys.exit(0 if os.environ.get("VOLUME_EXISTS") == "1" else 1)
elif args[0] == "run":
    if failure == "backup": sys.exit(1)
    print("consistent-state-backup")
elif args[0] == "pull" and failure == "download":
    sys.exit(1)
elif args[0] == "push" and failure == "push":
    sys.exit(1)
elif args[0] == "compose":
    release = pathlib.Path(args[args.index("-f") + 1]).parent.name
    # Last -f is followed by its path, then the subcommand.
    subcommand = args[max(i for i, arg in enumerate(args) if arg == "-f") + 2]
    if release == os.environ["FAILING_RELEASE"] and subcommand == failure:
        sys.exit(1)
    if os.environ.get("FAIL_ROLLBACK") == "1" and release != os.environ["FAILING_RELEASE"] and subcommand == "up":
        sys.exit(1)
'''


@unittest.skipUnless(os.name == "posix" and shutil.which("bash") and shutil.which("flock"),
                     "Linux Bash/flock integration runs in GitHub Actions")
class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "host"
        self.root.mkdir()
        self.envfile = self.root / ".env.deploy"
        self.envfile.write_text("APP_ENV=production\nSECRET=preserve-me\n")
        # This file represents existing persistent user data; orchestration must never remove it.
        self.data = self.root / "data-sentinel"
        self.data.write_text("existing-upload")
        self.bundle = self.base / "bundle"
        shutil.copytree(REPO / "deploy", self.bundle / "deploy")
        for file in ["compose.yaml", "compose.production.yaml"]:
            shutil.copy(REPO / file, self.bundle / file)
        config = self.base / "host.conf"
        config.write_text("AWS_REGION=ap-northeast-2\nECR_REGISTRY=123456789012.dkr.ecr.ap-northeast-2.amazonaws.com\nAPI_REPOSITORY=career-memory-api\nWEB_REPOSITORY=career-memory-web\n")
        bin_dir = self.base / "bin"
        bin_dir.mkdir()
        for name, body in [("docker", FAKE_DOCKER), ("aws", "print('temporary-token')")]:
            path = bin_dir / name
            path.write_text(f"#!{sys.executable}\n" + body)
            path.chmod(0o755)
        self.log = self.base / "calls.jsonl"
        self.env = {**os.environ, "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
                    "CAREER_MEMORY_ROOT": str(self.root), "CAREER_MEMORY_DEPLOY_CONFIG": str(config),
                    "CALL_LOG": str(self.log), "BUNDLE": str(self.bundle), "FAILING_RELEASE": NEW}

    def deploy(self, release=NEW, **env):
        return subprocess.run(["bash", str(REPO / "deploy/bootstrap-release.sh"), release, API, WEB],
                              env={**self.env, **env}, text=True, capture_output=True, timeout=20)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def seed(self):
        result = self.deploy(OLD)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.log.write_text("")

    def test_success_preserves_data_environment_and_pins_images(self):
        self.seed()
        result = self.deploy(VOLUME_EXISTS="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / "current").resolve().name, NEW)
        self.assertEqual((self.root / "previous").resolve().name, OLD)
        self.assertIn("SECRET=preserve-me", self.envfile.read_text())
        self.assertEqual(self.data.read_text(), "existing-upload")
        images = (self.root / "current/images.env").read_text()
        self.assertIn("@" + API, images)
        self.assertIn("@" + WEB, images)
        self.assertEqual(len(list((self.root / "backups").glob("*.tar.gz"))), 1)

    def test_all_failure_boundaries_keep_previous_release(self):
        self.seed()
        for stage in ["download", "config", "pull", "backup", "up", "exec"]:
            with self.subTest(stage=stage):
                self.log.write_text("")
                result = self.deploy(FAIL_STAGE=stage, VOLUME_EXISTS="1")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual((self.root / "current").resolve().name, OLD)
                calls = self.calls()
                old_ups = [c for c in calls if c[0] == "compose" and "up" in c and any(OLD + "/compose.yaml" in a for a in c)]
                if stage in {"backup", "up", "exec"}:
                    self.assertEqual(len(old_ups), 1, result.stderr)
                else:
                    self.assertFalse(any("stop" in c for c in calls))
                self.assertEqual(self.data.read_text(), "existing-upload")

    def test_first_deploy_failure_stops_service_without_removing_volume(self):
        result = self.deploy(FAIL_STAGE="up")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "current").exists())
        self.assertTrue(any(c[0] == "compose" and "stop" in c for c in self.calls()))
        self.assertFalse(any("down" in c or (c[:2] == ["volume", "rm"]) for c in self.calls()))

    def test_failed_rollback_is_reported_as_failure(self):
        self.seed()
        result = self.deploy(FAIL_STAGE="up", FAIL_ROLLBACK="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ROLLBACK FAILED", result.stderr)

    def test_host_lock_rejects_concurrent_deployment(self):
        import fcntl
        with (self.root / "deploy.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.deploy()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Another deployment", result.stderr)
        self.assertFalse(self.log.exists())

    def test_manual_rollback_uses_retained_release(self):
        self.seed()
        self.assertEqual(self.deploy().returncode, 0)
        result = self.deploy(OLD)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / "current").resolve().name, OLD)

    def test_release_id_cannot_be_reused_with_different_digest(self):
        self.seed()
        images = self.root / "releases" / OLD / "images.env"
        images.write_text("API_IMAGE=changed\n")
        result = self.deploy(OLD)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("different images", result.stderr)

    def test_invalid_input_never_reaches_docker(self):
        result = self.deploy("../../escape")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.log.exists())

    def publish(self, **env):
        fake_aws = self.base / "bin/aws"
        fake_aws.write_text(f"#!{sys.executable}\n" + '''
import os, sys
args = sys.argv[1:]
if args[0] == "sts": print("123456789012")
elif args[1] == "get-login-password": print("temporary-token")
elif args[1] == "describe-images":
    if os.environ.get("INVALID_DIGEST") == "1": print("None")
    else: print("sha256:" + ("c" if "career-memory-api" in args else "d") * 64)
''')
        with gzip.open(self.base / "images.tar.gz", "wb") as stream:
            stream.write(b"tested-image-archive")
        return subprocess.run(["bash", str(REPO / "deploy/publish-release.sh")], cwd=self.base,
                              env={**self.env, "RELEASE_ID": NEW, "GITHUB_SHA": "b" * 40,
                                   "AWS_REGION": "ap-northeast-2", "API_REPOSITORY": "career-memory-api",
                                   "WEB_REPOSITORY": "career-memory-web", "GITHUB_ENV": str(self.base / "output.env"),
                                   "GITHUB_STEP_SUMMARY": str(self.base / "summary"), **env},
                              text=True, capture_output=True, timeout=20)

    def test_publish_uses_tested_images_and_exports_resolved_digests(self):
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stderr)
        output = (self.base / "output.env").read_text()
        self.assertIn("API_DIGEST=" + API, output)
        self.assertIn("WEB_DIGEST=" + WEB, output)
        calls = self.calls()
        self.assertIn(["load"], calls)
        self.assertFalse(any("build" in c for c in calls))
        self.assertEqual(len([c for c in calls if c[0] == "push"]), 2)
        self.assertTrue(any(c[:2] == ["tag", "career-memory-api:" + "b" * 40] for c in calls))
        self.assertEqual(calls[-1][0], "logout")

    def test_publish_failure_cannot_export_deployable_digests(self):
        for env in [{"FAIL_STAGE": "push"}, {"INVALID_DIGEST": "1"}]:
            with self.subTest(env=env):
                result = self.publish(**env)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((self.base / "output.env").exists())
                self.assertEqual(self.calls()[-1][0], "logout")


if __name__ == "__main__":
    unittest.main()
