# Bedrock Agent – CentralIntegrationAgent

Action-oriented AI agent that invokes the ExecuteIntegration tool via the Integration Hub API. Created and wired automatically in **DataPlaneStack** (no manual IDs).

## Deployment

Bedrock Agent and Alias are created when you deploy DataPlaneStack. IDs are wired via CDK (no context flags or manual copy-paste).

```powershell
cdk deploy DataPlaneStack
```

## Prepare agent

After deploy, if alias creation failed:
1. Open AWS Console → Amazon Bedrock → Agents → CentralIntegrationAgent
2. Click **Prepare**
3. Once prepare completes, the alias is usable

## Outputs

Agent ID and Alias ID are exported from DataPlaneStack:

```powershell
aws cloudformation describe-stacks --stack-name DataPlaneStack --query "Stacks[0].Outputs"
```

- `BedrockAgentId` → Agent ID
- `BedrockAgentAliasId` → Agent Alias ID (prod)

## Invocation

```python
import boto3

bedrock_client = boto3.client("bedrock-agent-runtime")

response = bedrock_client.invoke_agent(
    agentId="<from BedrockAgentId output>",
    agentAliasId="<from BedrockAgentAliasId output>",
    sessionId="test-session",
    inputText="Ask Licensee B for receipt for transaction 123",
)

# Consume response stream
event_stream = response["completion"]
for event in event_stream:
    if "chunk" in event:
        print(event["chunk"]["bytes"].decode(), end="")
```

## Files

- `agent-system-prompt.txt` – Agent instructions
- `tool-schema.json` – ExecuteIntegration tool schema
- `list-operations-schema.json` – ListOperations tool schema (sourceVendor?, targetVendor?, isActive?)
