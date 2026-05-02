import boto3
import json
from botocore.config import Config

REGION    = "ap-south-1"
AGENT_ARN = "arn:aws:bedrock-agentcore:ap-south-1:767398019214:runtime/atomicAquaLangGraph_Agent-ADIW4YEOjJ"

# ── Change filename here for different files ──────────────────────────
FILENAME   = "jamming04_.gps"
S3_KEY     = f"logs/{FILENAME}"
SESSION_ID = "session-jamming04-gps-abc1234567890xx"   # must be 33+ chars

payload = {
    "s3_key":     S3_KEY,
    "filename":   FILENAME,
    "session_id": SESSION_ID
}

client = boto3.client(
    "bedrock-agentcore",
    region_name=REGION,
    config=Config(read_timeout=600, connect_timeout=60)
)

print(f"Processing: {FILENAME}")
print(f"Session ID: {SESSION_ID}")
print("Invoking agent (may take a few minutes)...")

response = client.invoke_agent_runtime(
    agentRuntimeArn=AGENT_ARN,
    qualifier="DEFAULT",
    payload=json.dumps(payload).encode("utf-8")
)

result = json.loads(response["response"].read())
# print("\nResult:", result)
print(f"\nSession ID to use for questions: {SESSION_ID}")