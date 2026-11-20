# Smart Document Manager: System Architecture

An enterprise-grade, serverless document management and intelligence platform deployed on AWS in `ap-southeast-2` (Sydney) operating under a \$10/month budget cap.

---

## 1. High-Level Component Architecture

```mermaid
flowchart TD
    User["Web Browser / Client (React SPA)"]
    CF["Amazon CloudFront CDN (HTTPS)"]
    S3Web["S3 Bucket: Static Frontend (OAC Protected)"]
    Cognito["Amazon Cognito User Pool & JWT Auth"]
    APIGW["Amazon API Gateway HTTP API v2"]
    
    subgraph Compute & Logic ["Serverless Compute (Python 3.12 Lambdas)"]
        UploadURL["Lambda: upload-url"]
        ListDocs["Lambda: list-docs"]
        SearchDoc["Lambda: search"]
        DeleteDoc["Lambda: delete-doc"]
        AskDoc["Lambda: ask (Cognito JWT + In-Memory RAG)"]
        AdminStats["Lambda: admin-stats (Server-Enforced Admin Role)"]
    end

    subgraph Storage & Persistence ["Encrypted Storage Tier"]
        S3Docs["S3 Bucket: Private Documents (AES-256)"]
        DDB["Amazon DynamoDB (On-Demand Metadata Table)"]
        DLQ["Amazon SQS Dead-Letter Queue (DLQ)"]
    end

    subgraph Intelligence ["AI & Machine Learning Services"]
        Groq["Groq API (qwen/qwen3.8-27b)"]
        BedrockLite["Amazon Bedrock Nova Lite (Multimodal PDF/OCR)"]
        BedrockMicro["Amazon Bedrock Nova Micro (Summarization Fallback)"]
        BedrockTitan["Amazon Bedrock Titan Embeddings V2 (1024-dim)"]
    end

    subgraph Pipeline ["Step Functions Execution Pipeline"]
        Trigger["Pipeline Trigger Lambda"]
        SFN["AWS Step Functions State Machine"]
        V["1. ValidateFile"]
        E["2. ExtractText"]
        S["3. Summarize (Groq / Nova Micro)"]
        D["4. DetectPII (Regex)"]
        W["5. SaveResults"]
        C["6. ChunkText (~500 tokens)"]
        EM["7. EmbedChunks (Titan Embed V2)"]
        F["Failure Catch: NotifyOnFailure"]
    end

    subgraph Monitoring ["Observability & Guardrails"]
        CWAlarms["CloudWatch Alarms (SFN ExecutionsFailed, DLQ Depth)"]
        CWDashboard["CloudWatch Operational Dashboard"]
        SNSTopic["Amazon SNS Topic Alerts"]
    end

    User -->|1. Request SPA Assets| CF
    CF -->|Fetch Static HTML/JS| S3Web
    User -->|2. Authenticate| Cognito
    User -->|3. API Calls with JWT| APIGW
    APIGW -->|Validate Token| Cognito
    APIGW --> UploadURL
    APIGW --> ListDocs
    APIGW --> SearchDoc
    APIGW --> DeleteDoc
    
    UploadURL -->|Pre-sign PUT| S3Docs
    UploadURL -->|Record Pending Upload| DDB
    User -->|4. Direct S3 Upload| S3Docs
    
    S3Docs -->|5. ObjectCreated Trigger| Trigger
    Trigger -->|StartExecution (name=docId)| SFN
    SFN --> V --> E --> S --> D --> W
    E -->|Multimodal Extraction| BedrockLite
    S -->|Masked PII Prompt| Groq
    S -.->|Fallback| BedrockMicro
    E -->|Write Extracted Text| S3Docs
    W -->|Update Status PROCESSED| DDB

    SFN -. Catch Any Error .-> F
    F -->|Set status FAILED| DDB
    F -->|Publish Error IDs Only| DLQ
    
    DLQ & SFN --> CWAlarms
    CWAlarms --> SNSTopic
    APIGW & SFN & DDB --> CWDashboard
```

---

## 2. Document Ingestion & Asynchronous Processing Sequence

```mermaid
sequenceDiagram
    autonumber
    actor User as User (React Client)
    participant APIGW as API Gateway (HTTP v2)
    participant UploadLambda as Lambda (upload-url)
    participant S3 as Amazon S3 (Documents)
    participant Trigger as Lambda (pipeline-trigger)
    participant SFN as Step Functions Pipeline
    participant Bedrock as Amazon Bedrock (Nova Lite/Micro)
    participant Groq as Groq API (qwen/qwen3.8-27b)
    participant DDB as Amazon DynamoDB

    User->>APIGW: POST /documents/upload-url (JWT + fileName + contentType)
    APIGW->>UploadLambda: Validate JWT and pass claims
    UploadLambda->>S3: Generate pre-signed PUT URL (valid 300s)
    UploadLambda->>DDB: PutItem (status='UPLOADED', userId, docId)
    UploadLambda-->>User: Return {uploadUrl, docId, s3Key}
    
    User->>S3: Direct PUT document to pre-signed S3 URL
    S3-->>User: 200 OK (Upload Complete)
    
    S3-)Trigger: Event s3:ObjectCreated (uploads/{userId}/{docId}/file)
    Trigger->>SFN: StartExecution (name=docId)
    
    SFN->>DDB: ValidateFile: Update status='PROCESSING'
    SFN->>Bedrock: ExtractText: Nova Lite Converse API (PDF / Image)
    SFN->>S3: ExtractText: Save to extracted-text/{userId}/{docId}/extracted.txt
    SFN->>Groq: Summarize: Mask PII -> Query qwen/qwen3.8-27b (JSON mode)
    Note over SFN,Groq: If Groq fails, fallback to Bedrock Nova Micro
    SFN->>SFN: DetectPII: Regex pattern scan (Email, Phone, SSN, Card)
    SFN->>DDB: SaveResults: Update status='PROCESSED', summary, tags, piiEntities

    User->>APIGW: GET /documents (Auto-poll every 4s)
    APIGW-->>User: Return updated document library with AI metadata
```

---

## 3. Multi-Tenant Zero-Trust Isolation Architecture

```mermaid
flowchart LR
    subgraph TenantA ["User A Context (Alice)"]
        TokenA["Cognito JWT: sub = 'user-aaa-111'"]
        S3PrefixA["s3://bucket/uploads/user-aaa-111/*"]
        DDBPartitionA["DynamoDB Partition: userId = 'user-aaa-111'"]
    end

    subgraph SecurityGate ["API Gateway & Lambda Authorizer"]
        JWTVerify["Enforce sub == Partition Key"]
    end

    subgraph TenantB ["User B Context (Bob)"]
        TokenB["Cognito JWT: sub = 'user-bbb-222'"]
        S3PrefixB["s3://bucket/uploads/user-bbb-222/*"]
        DDBPartitionB["DynamoDB Partition: userId = 'user-bbb-222'"]
    end

    TokenA --> JWTVerify
    TokenB --> JWTVerify
    JWTVerify -->|Alice only queries| DDBPartitionA
    JWTVerify -->|Alice pre-signed PUT restricted to| S3PrefixA
    JWTVerify -->|Bob only queries| DDBPartitionB
    JWTVerify -->|Bob pre-signed PUT restricted to| S3PrefixB
```

---

## 4. "Ask Your Documents" RAG Sequence & Isolation

```mermaid
sequenceDiagram
    autonumber
    actor User as Authenticated User
    participant Web as React Frontend (Ask Tab)
    participant APIGW as API Gateway (POST /ask)
    participant JWT as Cognito JWT Authorizer
    participant Lambda as Ask Lambda
    participant BedrockEmbed as Bedrock (Titan Embed V2)
    participant DDB as DynamoDB (DocumentsTable)
    participant S3 as S3 (Embeddings Partition)
    participant LLM as Groq (Fallback: Nova Micro)

    User->>Web: Type natural question & click Ask
    Web->>APIGW: POST /ask (Bearer idToken, { question })
    APIGW->>JWT: Validate signature, issuer, expiration
    JWT-->>APIGW: Authorized (Claims: sub = user-123)
    APIGW->>Lambda: Invoke with requestContext.authorizer.jwt.claims
    Lambda->>BedrockEmbed: InvokeModel (embed question -> 1024-dim vector)
    BedrockEmbed-->>Lambda: Question vector
    Lambda->>DDB: Query documents where userId = 'user-123'
    DDB-->>Lambda: User document metadata map (docId -> fileName)
    Lambda->>S3: List & GET embeddings strictly under prefix 'embeddings/user-123/'
    S3-->>Lambda: User's document chunk vectors
    Note over Lambda: In-memory cosine similarity ranking. Top 4 chunks selected. Context assembled with untrusted delimiters & PII masked.
    Lambda->>LLM: Dispatch context + question (Untrusted system prompt)
    LLM-->>Lambda: Synthesized answer
    Lambda-->>APIGW: 200 OK { answer, sources: [{ docId, fileName, snippet, similarity }], provider }
    APIGW-->>Web: Render answer card & clickable source chips
    Web-->>User: Display answer with citations
```

---

## 5. Expiring Share Links & Public Resolution Flow (Phase 4)

```mermaid
sequenceDiagram
    autonumber
    actor Owner as Document Owner
    actor Recipient as External Recipient
    participant Web as Web App Frontend
    participant APIGW as API Gateway HTTP API
    participant ShareCreate as Lambda: share-create
    participant ShareAccess as Lambda: share-access (Public)
    participant DDB_Shares as DynamoDB (Shares Table)
    participant DDB_Docs as DynamoDB (Documents Table)
    participant DDB_Audit as DynamoDB (Audit Table)
    participant S3 as S3 (Documents Bucket)

    Note over Owner, ShareCreate: Link Creation Flow (Authenticated)
    Owner->>Web: Click "Create Share Link" (1h, 24h, 7d, optional maxDownloads)
    Web->>APIGW: POST /documents/{docId}/share (Cognito JWT)
    APIGW->>ShareCreate: Invoke (JWT sub verified)
    ShareCreate->>DDB_Docs: Verify ownership (userId == sub)
    ShareCreate->>ShareCreate: Generate random 32-byte token & compute SHA-256 hash
    ShareCreate->>DDB_Shares: PutItem (tokenHash, shareId, docId, ownerId, expiresAt, maxDownloads, ttl)
    ShareCreate->>DDB_Audit: Log SHARE_CREATE event (best effort)
    ShareCreate-->>Web: 201 Created { shareUrl, rawToken, expiresAt } (Token shown ONCE)
    Web-->>Owner: Display shareable URL & copy button

    Note over Recipient, S3: Public Download Flow (No Cognito Required)
    Recipient->>APIGW: GET /shared/{token}
    APIGW->>ShareAccess: Invoke (No Authorizer, Strict Rate Throttled)
    ShareAccess->>ShareAccess: Compute SHA-256(token) (never log raw token)
    ShareAccess->>DDB_Shares: GetItem(tokenHash)
    alt Token Missing, Expired, Revoked, or maxDownloads Exceeded
        ShareAccess->>DDB_Audit: Log access failure (generic reason)
        ShareAccess-->>APIGW: 404 Generic Not Found ("Resource not found or link has expired")
        APIGW-->>Recipient: Identical 404 (Probe-resistant)
    else Valid Token
        ShareAccess->>DDB_Shares: Conditional Update: Increment downloadCount
        ShareAccess->>DDB_Docs: GetItem(ownerId, docId) -> fetch s3Key, fileName
        ShareAccess->>S3: Generate 60-second regional SigV4 presigned GET URL (attachment header)
        ShareAccess->>DDB_Audit: Log SHARE_ACCESS event with hashed IP (pseudonymized)
        ShareAccess-->>APIGW: 302 Found (Location: Presigned S3 URL)
        APIGW-->>Recipient: 302 Redirect to S3
        Recipient->>S3: Download document directly via short-lived regional URL
    end
```

---

## 6. Fault Tolerance, Dead-Letter Queue & Billing Protection

```mermaid
flowchart TD
    ProcessTrigger["S3 Ingestion Event"] --> ProcessorFunc["Processor Lambda"]
    ProcessorFunc -->|Transient Failure or Corrupt File| Retry["Lambda Max Retries (2x)"]
    Retry -->|Persistent Error| WriteDLQ["Route to SQS Dead-Letter Queue (DLQ)"]
    WriteDLQ --> DLQAlarm["CloudWatch Alarm: DLQ Visible Messages >= 1"]
    
    SpendMetric["CloudWatch Metric: EstimatedCharges (us-east-1)"] --> SpendAlarm["CloudWatch Alarm: Spend >= $10"]
    
    DLQAlarm --> AlertSNS["Amazon SNS: Operational Alerts"]
    SpendAlarm --> AlertSNS
    AlertSNS --> EmailNotify["Email Alert to Engineer"]
```
