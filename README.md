# Smart Document Manager on AWS

[![CI/CD Pipeline](https://github.com/your-username/awsfinalproject/actions/workflows/deploy.yml/badge.svg)](https://github.com/your-username/awsfinalproject/actions)
[![AWS Region](https://img.shields.io/badge/AWS%20Region-ap--southeast--2%20(Sydney)-orange.svg)](https://aws.amazon.com/)
[![Monthly Budget](https://img.shields.io/badge/Monthly%20Budget%20Cap-%2410%20USD-success.svg)](docs/COST.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A production-grade, serverless, multi-tenant document management and intelligence platform deployed on AWS. Users securely authenticate via Amazon Cognito, upload PDFs and images via pre-signed S3 URLs, extract text with Amazon Bedrock Nova Lite (multimodal), generate executive summaries and topic tags with Amazon Bedrock Nova Lite/Micro, run basic regex-based PII detection, and query their private document library.

---

## Architecture Overview

```
+---------------------------------------------------------------------------------------------------+
|                                            CLIENT TIER                                            |
|                  React SPA (Vite + Tailwind CSS) on S3 distributed via CloudFront                 |
+---------------------------------------------------------------------------------------------------+
        |                                       |                                    |
        | 1. Authenticate (JWT)                  | 2. Request Upload URL (300s TTL)   | 4. Direct PUT Upload
        v                                       v                                    v
+-----------------------+               +-----------------------+            +-----------------------+
|  Amazon Cognito       |               | Amazon API Gateway    |            |   Amazon S3           |
|  User Pool & Client   |               | HTTP API (v2) + Auth  |            | (AES-256 Encrypted)   |
+-----------------------+               +-----------------------+            +-----------------------+
                                                |                                    |
                                                v                                    | 5. s3:ObjectCreated
                                        +-----------------------+                    v
                                        | Python 3.12 Lambdas:  |            +-----------------------+
                                        | upload-url / list     |            |  Processor Lambda     |
                                        | search / delete-doc   |            |  (DLQ on failure)     |
                                        +-----------------------+            +-----------------------+
                                                |                                    |
                                                v                                    +--------+
                                        +-----------------------+                    |        |
                                        | Amazon DynamoDB       |<-------------------+        |
                                        | (Encrypted Metadata)  |                             |
                                        +-----------------------+                             v
                                                                                     +-----------------------+
                                                                                     | Amazon Bedrock        |
                                                                                     | Nova Lite / Micro     |
                                                                                     +-----------------------+
```

---

## Key Features & Highlights

1. **Pre-Signed S3 Uploads**: Files stream directly from browser to S3, bypassing API Gateway payload size limits (10MB) and slashing Lambda execution costs.
2. **Step Functions Workflow Pipeline**: Modular state machine executing `ValidateFile` -> `ExtractText` -> `Summarize` (Groq `qwen/qwen3.8-27b` with Bedrock Nova Micro fallback) -> `DetectPII` -> `SaveResults` -> `ChunkText` -> `EmbedChunks` with automated retries and Catch routing to DLQ.
3. **"Ask Your Documents" RAG Intelligence**: Natural-language question answering across personal documents using Amazon Bedrock Titan Text Embeddings V2 (`amazon.titan-embed-text-v2:0`) and in-memory cosine similarity ranking, synthesized with prompt-injection-safe Groq / Nova Micro completions and source citations.
   - **Chunk Indexing Limit**: To maintain sub-second response times and predictable S3 vector storage, only the first ~25 chunks (about 40,000 characters) of each document are indexed and searchable.
   - **Rate Limiting & Daily Quota**: API Gateway enforces a route-wide throttle on `POST /ask` (5 requests/sec, burst 10) across all callers, while DynamoDB tracks a per-user daily quota (50 questions/day, returning HTTP 429 when exceeded). Quota increments only upon successful answer generation.
4. **Live Pipeline Tracker & Auto-Classification**: Real-time vertical stepper tracking each pipeline stage (`ValidateFile`, `ExtractText`, `Summarize`, `DetectPII`, `SaveResults`, `ChunkText`, `EmbedChunks`) with elapsed execution timings, automatic document classification (`invoice`, `resume`, `report`, `contract`, `notes`, `letter`, `other`), and structured key field extraction (up to 6 label/value pairs, sanitized against PII).
5. **Semantic Search with Titan Embeddings**: Multi-tenant semantic document retrieval (`GET /documents/search?mode=semantic`) using Bedrock Titan Embeddings V2 with cosine similarity ranking, threshold filtering, match percentages, best matching snippet preview, and seamless fallback to keyword search with user notification.
6. **Client-Side PDF Summary Export**: One-click summary export using `jspdf`, generating branded document executive summaries with metadata, key fields, and tags entirely in-browser with zero network calls.
7. **Role-Based Access Control & Admin Analytics**: Cognito User Groups (`Admin` and `User`). Admin membership is enforced strictly server-side in Lambda (`cognito:groups` JWT claim check). An Admin Analytics Dashboard (`GET /admin/stats`) aggregates tenant metrics (documents by status, storage per anonymized user, avg/p95 latency, provider breakdown, 14-day Ask query volume) with zero exposure of document content or user questions.
8. **Expiring Share Links & Short-Lived Redirects**: Token-based secure document sharing (`POST /documents/{docId}/share`). Generates a 32-byte URL-safe cryptographic token, storing only its SHA-256 hash in DynamoDB with configurable expiry (1h, 24h, 7d) and optional download caps. Resolves via public route `GET /shared/{token}` into a 60-second regional SigV4 pre-signed S3 download redirect. All link access failures return an identical generic HTTP 404 to resist probing attacks.
9. **Activity & Security Audit Trail**: Best-effort immutable audit logger (`GET /audit` and DynamoDB `audit` table) recording lifecycle operations (`UPLOAD`, `VIEW`, `DELETE`, `SHARE_CREATE`, `SHARE_REVOKE`, `SHARE_ACCESS`, `ASK`, `ADMIN_STATS_VIEW`) with hashed IP (pseudonymized) using 16-character SHA-256 and automated 90-day DynamoDB TTL expiration.
10. **Resilient Local NLP & PII Detection**: Automated local keyword frequency fallback when models are unreachable, and a regex-based basic PII detector (Email, Phone, SSN, Credit Card) with pre-masking before external AI calls.
11. **Zero-Trust Multi-Tenant Isolation**: Tenant partitions are enforced at both S3 (`uploads/{userId}/...`, `chunks/{userId}/...`, `embeddings/{userId}/...`) and DynamoDB (`userId` partition key) levels, verified by automated security tests.
12. **Budget Protection**: Configured with automated CloudWatch alarms (or AWS Budgets) capping monthly spend at \$10.00 USD. Baseline idle cost is **\$0.00/month**.

---

## Prerequisites & Setup Checklist

- [x] **Node.js**: v18+ (tested on Node.js v25.9, npm v11.12)
- [x] **Python**: v3.11+ / v3.12 with `pip`
- [x] **Terraform**: v1.5+ (tested on HashiCorp Terraform v1.16.6)
- [ ] **AWS CLI v2**: Configured with credentials and target region:
  ```powershell
  aws configure
  # Default region name: ap-southeast-2
  ```

---

## Quickstart Deployment

### 1. Provision AWS Infrastructure
```powershell
cd infra
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your billing notification email

terraform init
terraform apply -auto-approve
```

### 2. Configure Frontend Client
Copy outputted resource identifiers into `frontend/.env`:
```env
VITE_AWS_REGION=ap-southeast-2
VITE_COGNITO_USER_POOL_ID=<OUTPUT_COGNITO_USER_POOL_ID>
VITE_COGNITO_CLIENT_ID=<OUTPUT_COGNITO_CLIENT_ID>
VITE_API_BASE_URL=<OUTPUT_API_ENDPOINT>
```

### 3. Deploy Frontend Web App
```powershell
cd ..
./scripts/deploy-frontend.ps1
```
Open the outputted CloudFront distribution URL (`app_url`) in any browser.

---

## Administrator Setup & Role Assignment

Self-signup users have standard user privileges. To promote your account to the `Admin` group:

1. **Find your Cognito username**:
   ```powershell
   aws cognito-idp list-users `
     --region ap-southeast-2 `
     --user-pool-id <YOUR_USER_POOL_ID> `
     --query "Users[].[Username, Attributes[?Name=='email'].Value | [0]]" `
     --output table
   ```
   *(Note: In Cognito User Pools with email sign-in, the internal `Username` is typically a UUID or your email address).*

2. **Add user to the Admin group**:
   ```powershell
   aws cognito-idp admin-add-user-to-group `
     --region ap-southeast-2 `
     --user-pool-id <YOUR_USER_POOL_ID> `
     --username "<COGNITO_USERNAME_FROM_STEP_1>" `
     --group-name "Admin"
   ```

3. **Sign out and sign in**:
   Cognito ID tokens are immutable. You must sign out of the frontend and sign back in to issue a fresh JWT token containing the `cognito:groups: ["Admin"]` claim.

> [!NOTE]
> **DynamoDB TTL Retention**: The `USAGE#` question telemetry records carry a 30-day Time-To-Live (`ttl`) timestamp. DynamoDB TTL deletion is handled asynchronously by AWS in the background and is not instant (items are typically removed within 48 hours of expiration).

---

## Running Automated Tests

Our test suite covers backend Lambdas, multi-tenant security isolation, and end-to-end processing:

```powershell
# Run all unit and integration tests (19 test cases)
python -m pytest tests/ -v
```

### Test Suite Structure:
- `tests/unit/test_upload_url.py`: Pre-signed URL generation and MIME-type validation.
- `tests/unit/test_list_docs.py`: DynamoDB GSI retrieval.
- `tests/unit/test_processor.py`: Textract extraction, Bedrock summarization, Comprehend fallback, and DLQ errors.
- `tests/unit/test_search.py`: DynamoDB keyword and tag filtering.
- `tests/unit/test_delete_doc.py`: S3 object and DynamoDB item deletion.
- `tests/integration/test_e2e_pipeline.py`: Full ingestion cycle (Upload -> S3 -> Textract -> Bedrock -> Search).
- `tests/integration/test_user_isolation.py`: Proof that User A cannot see, query, or delete User B's files.

---

## Project Documentation Directory

- [**docs/ARCHITECTURE.md**](docs/ARCHITECTURE.md): Comprehensive Mermaid diagrams detailing ingestion flows and multi-tenant security gates.
- [**docs/DECISIONS.md**](docs/DECISIONS.md): 21 Architectural Decision Records (ADRs) explaining key tradeoffs in 1-2 lines.
- [**docs/COST.md**](docs/COST.md): Free Tier limits, cost breakdown, and analysis proving why OpenSearch Serverless baseline costs (\$345+/mo) exceed our \$10 budget.
- [**docs/DEMO.md**](docs/DEMO.md): 5-minute presentation script with step-by-step click path.
- [**docs/PROGRESS.md**](docs/PROGRESS.md): 10-phase project milestone tracker.

---

## Clean Teardown

To destroy all deployed resources and guarantee **\$0.00 ongoing charges**:

```powershell
./scripts/teardown.ps1
```
*(On Linux/macOS, run `./scripts/teardown.sh`)*
