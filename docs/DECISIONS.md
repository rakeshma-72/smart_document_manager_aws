# Architecture & Design Decisions Log

This log documents key technical, architectural, and infrastructure decisions in 1-2 concise lines to guide learning and maintainability.

---

### ADR 001: CloudWatch EstimatedCharges Alarm in us-east-1
- **Decision**: Define the billing alarm CloudWatch metric in `us-east-1` provider alias because AWS emits account-level `EstimatedCharges` billing metrics exclusively in North Virginia (`us-east-1`).
- **Rationale**: Metric data for `AWS/Billing` is not available in regional CloudWatch namespaces like `ap-south-1`.

### ADR 002: Modular Single-State Directory Structure for Terraform
- **Decision**: Keep root Terraform configurations in `/infra` with dedicated file scopes (`billing.tf`, `storage.tf`, `auth.tf`, `api.tf`, `processing.tf`) sharing a unified state.
- **Rationale**: Simplifies cross-resource references (e.g., S3 bucket ARNs in Lambda IAM policies) for a solo developer while keeping code organized.

### ADR 003: Pre-Signed S3 URLs for Direct Uploads
- **Decision**: Frontend requests a pre-signed PUT URL from API Gateway/Lambda and uploads directly to S3 instead of sending file payloads through API Gateway.
- **Rationale**: Avoids API Gateway payload size limits (10MB) and binary encoding overhead while lowering Lambda execution duration and cost.

### ADR 004: DynamoDB for Metadata & Search Before OpenSearch
- **Decision**: Store document metadata, statuses, and tags in DynamoDB with GSI / filter queries initially; defer OpenSearch Serverless until required.
- **Rationale**: OpenSearch Serverless has a minimum baseline cost of ~\$175/month (OCUs), violating our \$10/month budget cap, while DynamoDB stays within AWS Free Tier.

### ADR 005: SQS Dead-Letter Queue on Processor Lambda
- **Decision**: Attach an SQS DLQ with max receive count of 2 and an SNS alarm to the processing pipeline Lambda.
- **Rationale**: Prevents infinite retry loops and runaway compute charges if corrupt files or Textract parsing errors occur.


### ADR 006: CloudFront Origin Access Control (OAC) Over OAI
- **Decision**: Authenticate CloudFront to the frontend S3 bucket using modern Origin Access Control (OAC) rather than legacy Origin Access Identity (OAI).
- **Rationale**: OAC supports SigV4 request signing, encryption with SSE-KMS, and improved security posture.

### ADR 007: CloudFront Custom Error Response for SPA Routing
- **Decision**: Configure CloudFront custom error responses mapping HTTP 403 and 404 status codes back to `/index.html` with status 200.
- **Rationale**: Enables client-side React SPA routing without broken direct link refreshes or S3 object not found errors.

### ADR 008: Strict S3 Public Access Blocking & Server-Side Encryption
- **Decision**: Enable S3 Block Public Access on all buckets and enforce SSE-S3 (AES-256) encryption by default.
- **Rationale**: Zero data exposure to public internet; complies with AWS Well-Architected Security Pillar and incurs zero extra KMS costs.


### ADR 009: Lightweight amazon-cognito-identity-js Over AWS Amplify Monolith
- **Decision**: Integrate `amazon-cognito-identity-js` directly into custom React AuthContext rather than importing `@aws-amplify/auth` or the full Amplify UI framework.
- **Rationale**: Reduces client JS bundle footprint by >80%, avoids large peer dependency conflicts, and provides transparent control over JWT tokens.

### ADR 010: Email as Primary Username Attribute in Cognito
- **Decision**: Configure Cognito User Pool with `username_attributes = ["email"]` and `auto_verified_attributes = ["email"]`.
- **Rationale**: Eliminates unnecessary user friction remembering separate usernames while guaranteeing unique verified identity.


### ADR 011: API Gateway HTTP API (v2) with Native JWT Authorizer
- **Decision**: Use API Gateway HTTP API (v2) with direct Cognito JWT authorizer instead of legacy REST API Gateway.
- **Rationale**: Costs 70% less (\$1.00/million vs \$3.50/million), reduces latency by ~50%, and validates Cognito JWTs natively without requiring a custom Lambda authorizer.

### ADR 012: DynamoDB On-Demand Billing and Chronological GSI
- **Decision**: Configure DynamoDB in PAY_PER_REQUEST mode with a Global Secondary Index on (`userId`, `createdAt`).
- **Rationale**: Prevents idle capacity charges while staying in Free Tier (25 RCU/WCU); GSI enables single-query retrieval of user documents sorted newest first.

### ADR 013: Path-Based Multi-Tenant Storage Partitioning
- **Decision**: Scope all S3 object uploads strictly under `uploads/{userId}/{docId}/{fileName}` and enforce `sub` verification from Cognito JWT.
- **Rationale**: Guarantees zero cross-tenant data leakage at both API and object storage levels.


### ADR 014: Dual-Mode Textract Strategy (Sync Images, Async Multi-Page PDFs)
- **Decision**: Invoke synchronous `detect_document_text` for image files (`.png`, `.jpg`, `.tiff`) and asynchronous `start_document_text_detection` for multi-page PDFs.
- **Rationale**: Synchronous Textract rejects multi-page PDFs; async Textract reliably processes documents up to 3,000 pages within standard Lambda execution limits.

### ADR 015: SQS Dead-Letter Queue and DLQ Message Depth Alarm
- **Decision**: Route Lambda processing failures to a dedicated encrypted SQS DLQ with a 14-day retention period and a CloudWatch metric alarm on `ApproximateNumberOfMessagesVisible >= 1`.
- **Rationale**: Isolates corrupt files or transient provider failures without dropping data, preventing runaway retry loops and notifying the engineering team immediately.


### ADR 016: Dual-Tier Generative & NLP Summarization Architecture
- **Decision**: Primary summary and tag generation runs via Amazon Bedrock (Titan/Claude); if model access or quota fails, automatically fallback to Amazon Comprehend Key Phrases and Entities.
- **Rationale**: Prevents pipeline disruption if Bedrock model access has not been activated in the AWS account, ensuring documents always receive tags and summaries.

### ADR 017: Token & Payload Constraints on Foundation Model Invocations
- **Decision**: Truncate input text passed to Bedrock/Comprehend to 3,500 characters and limit output generation to 256 tokens with temperature 0.2.
- **Rationale**: Keeps model execution deterministic, rapid (<3 seconds), and minimizes token consumption to remain well under the \$10/month budget cap.


### ADR 018: DynamoDB FilterExpression Search Over OpenSearch Serverless
- **Decision**: Perform document title, summary, preview, and tag querying using DynamoDB partition-key queries with FilterExpressions rather than provisioning Amazon OpenSearch Serverless.
- **Rationale**: OpenSearch Serverless requires a minimum 2-4 OCU allocation (\$345–\$691/month), which instantly breaches our \$10 budget cap, whereas DynamoDB search operates at \$0 within Free Tier limits.


### ADR 019: Atomic Multi-Tier Document Deletion (S3 & DynamoDB)
- **Decision**: Execute document deletion by first deleting S3 upload and extracted-text artifacts, followed by removing the DynamoDB record with strict user-tenant ownership verification.
- **Rationale**: Prevents orphaned binary objects consuming S3 storage and eliminates cross-tenant deletion vulnerabilities by verifying JWT `sub` before invoking S3/DynamoDB actions.


### ADR 020: Consolidated CloudWatch Observability Dashboard
- **Decision**: Define a single CloudWatch dashboard covering API Gateway counts/errors, Lambda invocations/errors, processor p95 duration, DLQ depth, and DynamoDB consumed units.
- **Rationale**: Leverages the 3 free CloudWatch dashboards in AWS Free Tier to give full-stack visibility without paying for third-party monitoring agents.

### ADR 021: Multi-Stage GitHub Actions Pipeline with Safe Secrets Conditioning
- **Decision**: Run parallel unit tests, frontend build compilation, and Terraform syntax checks before attempting deploy steps guarded by secret presence checks.
- **Rationale**: Prevents pipeline crashes or broken state changes when secrets are missing in forks or PRs while guaranteeing zero unvalidated code reaches production.


### ADR 022: Isolated Test Fixture Guardrails (conftest.py)
- **Decision**: Inject mock AWS credential environment variables and patch `time.sleep` in root `tests/conftest.py`.
- **Rationale**: Prevents boto3 from hanging on EC2 instance metadata service (IMDSv2) network timeouts during offline/local testing, speeding execution by 50x (0.55s total).

### ADR 023: Version-Aware S3 Pre-Teardown Emptying
- **Decision**: Script S3 object and version marker purges via AWS CLI before invoking `terraform destroy`.
- **Rationale**: AWS S3 forbids deletion of non-empty versioned buckets; pre-emptively deleting object versions guarantees zero stranded resources and clean teardown execution.


### ADR 024: Migrate Bedrock Model from Deprecated Titan Text Lite to Nova Micro
- **Decision**: Replace `amazon.titan-text-lite-v1` with the regional inference profile `apac.amazon.nova-micro-v1:0` for generative document summarization.
- **Rationale**: Titan Text Lite reached End-of-Life in AWS Bedrock (`ResourceNotFoundException`); Nova Micro is active across APAC (`ap-southeast-2`), auto-granted across accounts, ~10x cheaper (\$0.035/1M input tokens), and faster.

### ADR 025: Replace Textract & Comprehend with Bedrock Multimodal & Local NLP
- **Decision**: Remove Amazon Textract and Amazon Comprehend from the document processing pipeline. Process PDFs and images directly via Amazon Bedrock Converse API using `apac.amazon.nova-lite-v1:0`, retain `apac.amazon.nova-micro-v1:0` for text-only files, replace Comprehend fallback with local keyword-frequency analysis, and replace Comprehend PII detection with a basic regex-based check.
- **Rationale**: The organization Service Control Policy (SCP `p-t4mrja8p`) explicitly denies `textract:*` and `comprehend:*` in the deployment account. Nova Lite multimodal vision/document support enables extracting text, summaries, and topic tags in a single API call, reducing latency, eliminating asynchronous polling loops, reducing IAM attack surface, and operating fully within organization policy. A 4 MB file size limit and 10,000 character length limit ensure predictable cost and runtime.

### ADR 026: Step Functions Orchestration Pipeline & Multi-Provider AI (Groq + Bedrock)
- **Decision**: Decompose the monolithic document processor Lambda into a modular AWS Step Functions state machine with 6 discrete micro-tasks: `ValidateFile`, `ExtractText`, `Summarize` (primary Groq `qwen/qwen3.8-27b` with PII pre-masking and Bedrock Nova Micro fallback), `DetectPII`, `SaveResults`, and `NotifyOnFailure`.
- **Rationale**: 
  1. **Fault Isolation & Retries**: Transient API hiccups or model rate limits can retry individual stages with exponential backoff rather than re-executing expensive extraction stages or timing out monolithic Lambdas.
  2. **Non-Retryable Validation**: Validation errors (unsupported extensions, file sizes > 4 MB) fail fast and route directly to `Catch` without wasteful retries.
  3. **Strict Payload Discipline**: State transitions pass strictly document IDs and S3 keys; extracted text resides in S3 (`extracted-text/{userId}/{docId}/extracted.txt`), ensuring the 256 KB state machine payload ceiling is never breached.
  4. **Idempotency**: Executions are named after `docId`, guaranteeing that duplicate S3 upload notifications are safely ignored without dual processing.
  5. **Zero Data Leakage**: Document text is never logged, never forwarded to SQS DLQ, and PII patterns (email, phone, SSN, credit cards) are masked before querying external LLM endpoints. Groq secrets reside in sensitive Terraform variables and are never surfaced to clients.

### ADR 027: Multi-Tenant RAG with S3 Vector Storage & In-Memory Cosine Similarity Over OpenSearch
- **Decision**: Implement the "Ask your documents" capability using pipeline-generated chunk embeddings stored directly in S3 (`embeddings/{userId}/{docId}/embeddings.json`) generated by Amazon Bedrock `amazon.titan-embed-text-v2:0` (1,024 dimensions). Execute vector similarity search via pure in-memory cosine similarity inside the `POST /ask` Lambda rather than provisioning Amazon OpenSearch Serverless.
- **Rationale**:
  1. **Cost & Budget Strictness**: Amazon OpenSearch Serverless requires a minimum baseline of 2 indexing OCUs and 2 search OCUs ($0.24/OCU-hour), yielding a fixed floor cost of ~$700/month (or ~$350/mo with minimal single-collection config), completely violating the project's $10/month hard ceiling.
  2. **Performance at Scale**: For typical user libraries (dozens to hundreds of documents, capped at 25 chunks per document), loading user-partitioned vectors from S3 into Lambda and calculating dot products in Python takes < 15ms.
  3. **Zero-Trust Multi-Tenant Isolation**: Vectors are strictly segregated under `s3://.../embeddings/{userId}/`. The `POST /ask` Lambda derives `userId` exclusively from the verified Cognito JWT authorizer claims (never request payloads) and paginates exclusively with `Prefix=embeddings/{userId}/`, ensuring complete cryptographic isolation between tenants.
  4. **Prompt Injection Defense**: Context passed to Groq (`qwen/qwen3.8-27b`) or fallback Nova Micro wraps document chunks with explicit untrusted boundaries and instructs the model to ignore directives embedded inside documents. PII is pre-masked prior to external LLM dispatch.
  5. **Throttling Model & Daily Quotas**: API Gateway route throttling (5 rps, burst 10) on `POST /ask` is route-wide across all callers to protect backend concurrency and Bedrock/Groq rate limits. To prevent noisy-neighbor abuse or runaway costs from an individual user, a per-user daily question cap (50 questions/day) is tracked atomically in DynamoDB, responding with HTTP 429 when exhausted.
  6. **Chunk Searchability Ceiling**: ChunkText caps splitting at the first 25 chunks (about 40,000 characters) per document. This ensures that S3 embedding payloads and in-memory cosine scans scale linearly with predictable latency.

### ADR 028: Server-Side Role Enforcement & Aggregated Admin Analytics
- **Decision**: Define Cognito groups `Admin` and `User` in Terraform without any client self-assignment mechanism. Restrict `GET /admin/stats` strictly on the server by inspecting the `cognito:groups` claim inside the verified JWT authorizer. Compile platform statistics via on-demand paginated DynamoDB scan and return aggregates only (counts, anonymized tenant storage, avg/p95 latency, provider distribution, daily Ask counts).
- **Rationale**:
  1. **Defense-in-Depth vs. Client Cosmetic Hiding**: Hiding the Admin tab in the frontend React UI is purely cosmetic. Enforcing the group check inside the Lambda handler guarantees that unprivileged tokens or forged headers receive HTTP 403 Forbidden.
  2. **Zero-Leakage Privacy Boundary**: Administrative dashboards must never expose tenant confidential text, summaries, file names, or user questions. Aggregating strictly numerical counts and anonymized IDs (`user-****1234`) preserves multi-tenant confidentiality.
  3. **On-Demand Paginated Scan vs. Pre-Aggregated Counters**: At development and small-to-medium scale (< 50,000 items), scanning DynamoDB with pagination is simpler, cost-effective ($0.00 within Free Tier), and self-healing against counter drift. Pre-aggregated counters (e.g. DynamoDB streams into atomic summary records) introduce distributed lock/event overhead and additional Lambda invocations which are unnecessary at this scale.
  4. **Usage Record Lifecycle (TTL)**: `USAGE#YYYY-MM-DD` records carry a DynamoDB `ttl` attribute set to expire 30 days after generation, ensuring operational telemetry does not indefinitely inflate storage costs.

### ADR 029: Token-Based Expiring Share Links & Best-Effort Audit Trail
- **Decision**: Implement expiring share links using a token lookup architecture: `POST /documents/{docId}/share` creates a 32-byte cryptographic token, stores only its SHA-256 hash in a dedicated DynamoDB `shares` table with TTL (1h, 24h, 7d), and returns the raw link once. The public route `GET /shared/{token}` hashes the incoming token, checks expiry/revocation/max-downloads atomically, and returns an HTTP 302 redirect to a fresh 60-second regional SigV4 S3 GET URL. All security and document lifecycle operations log immutable records to a DynamoDB `audit` table with 90-day TTL.
- **Rationale**:
  1. **Lambda Credential Expiration vs. Pre-signed S3 URLs**: Pre-signed URLs generated inside Lambda functions are signed with temporary IAM session credentials that expire within hours at most (max 12h session duration). Direct pre-signed S3 links cannot support 7-day share lifecycles. Generating short-lived 60-second S3 pre-signed URLs on-the-fly upon token resolution solves the session expiration problem securely.
  2. **SHA-256 Token Storage & Single-Use Disclosure**: The raw token is returned only once to the document creator and is never written to disk or database. Even if the DynamoDB shares table were compromised, stored hashes cannot be reversed into valid access URLs.
  3. **Probe Resistance with Identical 404s**: Any access failure (unknown token, expired link, revoked link, exhausted max downloads, deleted underlying document) returns the exact same generic HTTP 404 response ("Resource not found or link has expired"), preventing token enumeration, timing analysis, or document existence probing.
  4. **Atomic Download Counters**: Conditional expressions (`ConditionExpression: attribute_exists(tokenHash) AND revoked = :f AND downloadCount < :maxD`) ensure race-free enforcement of `maxDownloads` across concurrent requests.
  5. **Best-Effort Audit Trail Boundary**: Audit writes (`UPLOAD`, `VIEW`, `DELETE`, `SHARE_CREATE`, `SHARE_REVOKE`, `SHARE_ACCESS`, `ASK`, `ADMIN_STATS_VIEW`) are strictly best-effort and execute inside `try/except` blocks so audit storage issues never impede core document actions. IPs are stored as hashed IP (pseudonymized) using truncated SHA-256, and zero document text, questions, or raw tokens are ever logged.
  6. **Automated Lifecycle Expiration (TTL)**: Both `shares` and `audit` tables enable native DynamoDB TTL (expiration time for shares, 90-day retention for audit events), automatically purging expired items with zero operational overhead and zero consumed write units.

### ADR 030: Live Pipeline Progress Tracking in DynamoDB Document Item
- **Decision**: Store pipeline step status (`currentStep` string and `stepStatus` map with ISO timestamps) directly on the existing DynamoDB document item.
- **Rationale**: Eliminates the overhead of a separate execution tracking table while giving the frontend a single unified polling endpoint with zero extra cost.

### ADR 031: Combined Summarization and Auto-Classification in Single Prompt
- **Decision**: Extract `docType` (from a strict allow-list) and up to 6 `keyFields` (dates, amounts, orgs) in the exact same JSON schema and prompt invocation as the executive summary and topic tags.
- **Rationale**: Achieves automatic document classification and key-value extraction with zero additional LLM invocations or Bedrock runtime costs. PII pre-masking prevents sensitive entities from being stored in key fields.

### ADR 032: In-Lambda Semantic Search with Titan Embeddings V2
- **Decision**: Implement `mode=semantic` search in Lambda by generating a 1024-dim Titan vector for the query and computing cosine similarity against the caller's pre-computed S3 chunk vectors (`embeddings/{userId}/*`).
- **Rationale**: Provides semantic relevance with match percentage and best matching snippet previews while completely avoiding OpenSearch compute costs ($345+/mo). Multi-tenant isolation is guaranteed by strict S3 prefix scoping.

### ADR 033: Client-Side PDF Generation with jsPDF
- **Decision**: Render executive summary PDF exports entirely in the browser using `jspdf` without server round-trips.
- **Rationale**: 100% private, instant client-side download with zero network transfer, zero Lambda compute cost, and strict plain-text sanitization.



