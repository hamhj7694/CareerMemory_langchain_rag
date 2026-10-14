"""Send one restricted command, then check its actual execution result (stdlib only)."""
import json
import os
import re
import subprocess
import sys
import time


def validate(env, *, digests=True):
    patterns = {
        "AWS_REGION": r"[a-z]{2}-[a-z]+-[0-9]+",
        "AWS_ROLE_ARN": r"arn:aws:iam::[0-9]{12}:role/[A-Za-z0-9_+=,.@/-]+",
        "API_REPOSITORY": r"[a-z0-9][a-z0-9/_-]+",
        "WEB_REPOSITORY": r"[a-z0-9][a-z0-9/_-]+",
        "EC2_INSTANCE_ID": r"i-[0-9a-f]{17}",
        "SSM_DOCUMENT_NAME": r"[A-Za-z0-9_-]{3,128}",
        "SSM_DOCUMENT_VERSION": r"[1-9][0-9]*",
        "RELEASE_ID": r"[0-9a-f]{40}-[0-9]+-[0-9]+",
    }
    if digests:
        patterns.update(API_DIGEST=r"sha256:[0-9a-f]{64}", WEB_DIGEST=r"sha256:[0-9a-f]{64}")
    for key, pattern in patterns.items():
        if not re.fullmatch(pattern, env.get(key, "")):
            raise ValueError(f"Missing or invalid deployment setting: {key}")


def aws(*args):
    result = subprocess.run(
        ["aws", *args, "--output", "json", "--cli-connect-timeout", "10", "--cli-read-timeout", "30"],
        text=True, capture_output=True, timeout=60,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout)


def deploy(env, call=aws, sleep=time.sleep, now=time.monotonic, timeout=2160):
    validate(env)
    response = call(
        "ssm", "send-command", "--instance-ids", env["EC2_INSTANCE_ID"],
        "--document-name", env["SSM_DOCUMENT_NAME"],
        "--document-version", env["SSM_DOCUMENT_VERSION"],
        "--timeout-seconds", "120", "--comment", f"Career Memory {env['RELEASE_ID']}",
        "--parameters", json.dumps({
            "ReleaseId": [env["RELEASE_ID"]],
            "ApiDigest": [env["API_DIGEST"]], "WebDigest": [env["WEB_DIGEST"]],
        }),
    )
    command_id = response["Command"]["CommandId"]
    print(f"SSM command: {command_id}", flush=True)
    summary = env.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write(f"\nSSM command: `{command_id}`\n")
    deadline = now() + timeout
    while now() < deadline:
        try:
            result = call("ssm", "get-command-invocation", "--command-id", command_id,
                          "--instance-id", env["EC2_INSTANCE_ID"])
        except RuntimeError as error:
            # Run Command is eventually consistent; only this known early error is retried.
            if "InvocationDoesNotExist" not in str(error):
                raise
            sleep(10)
            continue
        status = result["Status"]
        if status in {"Pending", "InProgress", "Delayed", "Cancelling"}:
            sleep(10)
            continue
        print(f"SSM status: {status}; exit code: {result.get('ResponseCode')}")
        print(result.get("StandardOutputContent", ""))
        print(result.get("StandardErrorContent", ""), file=sys.stderr)
        if status != "Success" or result.get("ResponseCode") != 0:
            raise RuntimeError("EC2 deployment failed. Check rollback result in SSM output.")
        return command_id
    # Do not terminate a host deployment halfway through backup/rollback.
    raise TimeoutError(f"SSM command {command_id} did not finish in time; inspect it before retrying.")


if __name__ == "__main__":
    if sys.argv[1:] == ["--validate-only"]:
        validate(os.environ, digests=False)
        print("Deployment settings validated")
    elif not sys.argv[1:]:
        deploy(os.environ)
    else:
        raise SystemExit("Usage: deploy-ssm.py [--validate-only]")
