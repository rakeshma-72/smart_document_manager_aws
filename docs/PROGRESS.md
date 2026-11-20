# Project Progress: Smart Document Manager on AWS

Overall Status: **Project Completed (Phases 1-10 Complete)**

## Phase Checklist

- [x] **Phase 1: Setup & Foundations**
  - [x] Repository folder structure (`/docs`, `/infra`, `/backend`, `/frontend`, `/tests`, `/scripts`)
  - [x] `docs/PROGRESS.md` checklist created
  - [x] `docs/DECISIONS.md` architecture decision log initialized
  - [x] AWS billing alarm Terraform configuration (CloudWatch alarm & SNS topic at $10/month cap)
  - [x] Local setup checklist (AWS CLI, Terraform, Node.js, Python)
  - [x] `README.md` skeleton and `.env.example` template
  - [x] Terraform formatting and validation checks passed

- [x] **Phase 2: Storage and Hosting**
  - [x] Private S3 document storage bucket with server-side encryption (SSE-S3/AES256) and public access block
  - [x] S3 bucket for React static frontend hosting
  - [x] CloudFront distribution with Origin Access Control (OAC) for secure frontend delivery
  - [x] S3 CORS configuration for secure direct uploads from browser
  - [x] Deploy Hello World React app and verify CloudFront endpoint
  - [x] Frontend deployment helper scripts (`scripts/deploy-frontend.ps1`, `scripts/deploy-frontend.sh`)

- [x] **Phase 3: Authentication**
  - [x] Amazon Cognito User Pool with email sign-up/login and password policy
  - [x] Cognito User Pool Client (no client secret for SPA)
  - [x] React auth integration (Sign Up, Confirm, Sign In, Sign Out, session management)
  - [x] Protected routes in React app (redirect to login if unauthenticated)

- [x] **Phase 4: Upload API**
  - [x] API Gateway HTTP API (v2) with Cognito JWT Authorizer
  - [x] Pre-signed URL generation Lambda (`backend/upload-url`)
  - [x] DynamoDB `Documents` table (partition key `userId`, sort key `docId`) and GSI (`userId`, `createdAt`)
  - [x] Document list Lambda (`backend/list-docs`)
  - [x] React UI for drag-and-drop file upload, progress tracking, and document list table
  - [x] Unit test suite for backend Lambdas passing with 100% success

- [x] **Phase 5: Processing Pipeline**
  - [x] S3 object created event trigger configuration (`uploads/` prefix filter)
  - [x] Dead-Letter Queue (SQS DLQ) with 14-day retention and SSE encryption
  - [x] CloudWatch metric alarm on DLQ `ApproximateNumberOfMessagesVisible >= 1`
  - [x] Document processor Lambda (`backend/processor`) with dual-mode Textract extraction (sync for images, async for multi-page PDFs)
  - [x] Full extracted text persisted to S3 under `extracted-text/{userId}/{docId}/extracted.txt`
  - [x] DynamoDB lifecycle status management (`UPLOADED` -> `PROCESSING` -> `PROCESSED` or `FAILED`)
  - [x] Unit test suite updated (9 tests passing with 100% success)

- [x] **Phase 6: Summary and Tagging**
  - [x] Amazon Bedrock integration (`amazon.titan-text-lite-v1`) for 2-sentence executive summaries and topic tags
  - [x] Amazon Comprehend automatic fallback for Key Phrases and Entities if Bedrock access is unconfigured
  - [x] Saved summary, tag array, word count, and preview snippet into DynamoDB
  - [x] Rich UI display with tag badges, summary preview, and interactive `DocumentDetailModal`
  - [x] Expanded unit test coverage for Bedrock and Comprehend fallback (11 tests passing 100%)

- [x] **Phase 7: Search**
  - [x] Multi-tenant document search Lambda (`backend/search`) querying DynamoDB with partition key isolation
  - [x] API Gateway route `GET /documents/search?q={query}&tag={tag}` with Cognito JWT authorization
  - [x] Frontend search bar with query input, tag chip filtering, active filter pill, and instant clear
  - [x] Comprehensive `docs/COST.md` analyzing current Free Tier costs vs OpenSearch Serverless baseline costs (\$345–\$691/mo) and migration triggers
  - [x] Unit test suite expanded (14 tests passing with 100% success)

- [x] **Phase 8: Frontend Polish**
  - [x] Live lifecycle status badges with ping animations and smart auto-polling for in-flight processing documents
  - [x] Clean toast notification system for upload success and deletion confirmation
  - [x] Document detail modal with metadata chips, copy-to-clipboard extracted text, and safe confirmation deletion
  - [x] Backend delete Lambda (`backend/delete-doc`) purging both S3 binaries (`uploads/`, `extracted-text/`) and DynamoDB records
  - [x] Unit test suite expanded (17 tests passing with 100% success)

- [x] **Phase 9: CI/CD and Monitoring**
  - [x] GitHub Actions automated workflow (`.github/workflows/deploy.yml`) with Python tests, Vite build, and Terraform validation
  - [x] CloudWatch Operational Dashboard with API traffic, Lambda invocations/errors, processor p95 duration, DLQ depth, and DynamoDB metrics
  - [x] CloudWatch alarm on Lambda processor execution errors
  - [x] Operational SNS topic (`${project_name}-dev-operational-alerts`) for regional alarms

- [x] **Phase 10: Testing and Documentation**
  - [x] End-to-end integration test (`tests/integration/test_e2e_pipeline.py`) validating complete upload -> process -> search lifecycle
  - [x] Multi-tenant isolation test (`tests/integration/test_user_isolation.py`) proving User A cannot see, query, or delete User B's files
  - [x] Complete suite of 19 automated tests passing in 0.55 seconds
  - [x] System architecture documentation with 4 Mermaid diagrams in `docs/ARCHITECTURE.md`
  - [x] 5-minute presentation script in `docs/DEMO.md`
  - [x] Automated teardown scripts (`scripts/teardown.ps1`, `scripts/teardown.sh`) ensuring \$0.00 ongoing charges
  - [x] Comprehensive final `README.md` and 23 ADRs recorded in `docs/DECISIONS.md`
  - [ ] API Gateway REST/HTTP API with Cognito User Pool Authorizer
  - [ ] Pre-signed URL generation Lambda (`backend/upload-url`)
  - [ ] DynamoDB `Documents` table (partition key `userId`, sort key `docId`)
  - [ ] Document list Lambda (`backend/list-docs`)
  - [ ] React UI for file selection, upload progress, and document list table

- [ ] **Phase 5: Processing Pipeline**
  - [ ] S3 object created event trigger configuration
  - [ ] Dead-Letter Queue (SQS DLQ) and CloudWatch alarm for failed document processing
  - [ ] Document processor Lambda (`backend/processor`)
  - [ ] Amazon Textract integration (asynchronous for multi-page PDFs, synchronous for images)
  - [ ] DynamoDB status lifecycle updates (`UPLOADED` -> `PROCESSING` -> `PROCESSED` or `FAILED`)

- [ ] **Phase 6: Summary and Tagging**
  - [ ] Bedrock / Comprehend extraction step for key phrases, entities, and executive summary
  - [ ] Fallback handling for region/model quota availability
  - [ ] Save generated summary and tags into DynamoDB item
  - [ ] Display document summary and badge tags in React UI

- [ ] **Phase 7: Search**
  - [ ] Search Lambda (`backend/search`) querying DynamoDB by tags and document metadata
  - [ ] Frontend search bar with tag-based filtering and keyword match
  - [ ] Cost analysis and migration plan for OpenSearch Serverless documented in `docs/COST.md`

- [ ] **Phase 8: Frontend Polish**
  - [ ] Status badges (`UPLOADED`, `PROCESSING`, `PROCESSED`, `FAILED`) with auto-refresh/polling
  - [ ] Loading skeletons, toasts, and clear error boundaries
  - [ ] Document detail view modal / route
  - [ ] Delete document flow (removes S3 object and DynamoDB metadata)

- [ ] **Phase 9: CI/CD and Monitoring**
  - [ ] GitHub Actions workflow for linting, testing, and automated deploy
  - [ ] CloudWatch dashboard (API requests, Lambda durations/errors, S3 storage, DLQ depth)
  - [ ] Alarm notifications via SNS for Lambda errors and DLQ messages

- [ ] **Phase 10: Testing and Documentation**
  - [ ] Unit tests for backend Lambdas and frontend components
  - [ ] End-to-end integration test (upload -> processed -> searchable)
  - [ ] Multi-tenant isolation test (verify User A cannot access User B's documents)
  - [ ] `docs/ARCHITECTURE.md` with complete Mermaid diagrams
  - [ ] `docs/DEMO.md` 5-minute walkthrough script
  - [ ] `docs/COST.md` free tier vs paid usage breakdown
  - [ ] Final `README.md` and complete teardown script (`scripts/teardown.sh` / `.ps1`)
