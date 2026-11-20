# Smart Document Manager: 5-Minute Demo Script

A guided, step-by-step walkthrough script for presenting this AWS serverless architecture to professors, hiring managers, or team leads.

---

## Demo Timing & Agenda

- **Minute 1: Problem & Architecture Overview** (AWS CloudFront, S3 OAC, Cognito, API Gateway, DynamoDB)
- **Minute 2: Secure Sign-Up & Authentication** (Cognito verification codes & JWT session)
- **Minute 3: Direct S3 Upload & Pre-Signed URLs** (Bypassing API Gateway size limits)
- **Minute 4: Serverless AI Pipeline** (Textract OCR, Bedrock/Comprehend summaries & topic tags)
- **Minute 5: Search, Deletion, and Budget Guardrails** (DynamoDB search, zero-leak isolation, $10 spend alarm)

---

## Step-by-Step Walkthrough

### 1. Opening & Architecture (0:00 - 1:00)
- **Action**: Open the application URL hosted on CloudFront HTTPS (`https://dXXXXXXXXX.cloudfront.net`).
- **Talking Points**:
  > *"Welcome to Smart Document Manager on AWS. This application enables users to securely upload PDFs and images, automatically extracts content using Amazon Textract, summarizes documents with generative AI, and allows instant querying. The entire system is built strictly serverless in `ap-southeast-2` with automated budget alarms capping our spend under \$10/month."*

---

### 2. Authentication & Multi-Tenancy (1:00 - 2:00)
- **Action**:
  1. Click **Sign Up**, enter your email (e.g., `alice@example.com`), and an 8-character password.
  2. Enter the 6-digit confirmation code received via email to verify the account.
  3. Sign in to enter the authenticated workspace.
- **Talking Points**:
  > *"Authentication is powered by Amazon Cognito User Pools without any client secret in the browser. Cognito issues signed JWT tokens that our API Gateway validates natively. Every user's data is strictly partitioned by their unique Cognito `sub` identifier at both the DynamoDB table and S3 bucket level."*

---

### 3. Pre-Signed URL Direct Upload (2:00 - 3:00)
- **Action**:
  1. Click **Upload Document**.
  2. Drag and drop a sample multi-page PDF or receipt image (`invoice_sample.pdf`).
  3. Watch the progress bar advance directly to 100%.
- **Talking Points**:
  > *"Notice how fast the upload completes. Rather than sending heavy multipart file bytes through our API Gateway—which costs more and has a 10MB limit—the client requests a short-lived pre-signed PUT URL from our Lambda and streams the file directly to our private, encrypted S3 bucket."*

---

### 4. Asynchronous Textract & Bedrock Intelligence (3:00 - 4:00)
- **Action**:
  1. Point out the live table status badge transitioning from **Uploaded** to **Extracting AI...** with animated pulse.
  2. Within seconds, watch the document settle into **Processed** automatically via client auto-polling.
  3. Point to the generated executive summary and topic tags (`#tax`, `#invoice`, `#financial`).
  4. Click **Details** to open the modal; review the full extracted text preview and click **Copy Text**.
- **Talking Points**:
  > *"When the file lands in S3, an `ObjectCreated` event triggers our processor Lambda. For images, we run synchronous Textract; for multi-page PDFs, we trigger asynchronous Textract jobs. Once extracted, Amazon Bedrock generates a concise 2-sentence executive summary and topical tags. If Bedrock foundation models are not enabled in a regional account, our code automatically falls back to Amazon Comprehend without dropping the request."*

---

## Screenshots to Take for the Demo

Prepare and capture these key high-resolution screenshots for presentations, slide decks, or documentation:

1. **Workspace Overview with Dark Mode**: Main library view displaying document cards, status badges, provider labels (`groq` / `Bedrock Nova`), and filter chips.
2. **Live Pipeline Tracker**: Document Details modal open showing the vertical stepper (`ValidateFile` -> `ExtractText` -> `Summarize` -> `DetectPII` -> `SaveResults` -> `ChunkText` -> `EmbedChunks`) with real-time timestamps and elapsed processing time.
3. **Auto-Classification & Key Fields**: Document Details modal showing an extracted invoice or contract with the type badge (`INVOICE`, `CONTRACT`) and the structured key fields grid (Amounts, Dates, Names) with zero PII exposure.
4. **Semantic vs Keyword Search**: Comparison of search results using the "Semantic" toggle, highlighting match score percentages (e.g. `94% match`), query snippet previews, and the type filter chips.
5. **Client-Side PDF Summary**: Generated PDF file viewed in browser showing the clean typography, metadata header, AI executive summary, key extracted fields, and tags without network transmission.
6. **"Ask Your Documents" RAG Response**: The Ask tab with an answered question, citing specific chunk snippets from authenticated user documents with source badges.
7. **Role-Based Admin Analytics Dashboard**: The Admin view displaying aggregated tenant charts (storage by anonymized user, status breakdown, avg/p95 latency, provider volume) accessed exclusively via Cognito Admin credentials.
8. **Secure Expiring Share Link & Audit Trail**: Active share link with download count/expiry parameters, alongside the immutable Activity tab showing pseudonymized IP audit records.
