# Cost Analysis & Optimization Guide

**Project**: Smart Document Manager on AWS  
**Target Region**: `ap-southeast-2` (Sydney)  
**Monthly Budget Cap**: \$10.00 USD  
**CloudWatch Spend Alarm**: Configured at \$10.00 USD (`EstimatedCharges` metric in `us-east-1`)

---

## 1. Current Architecture Cost Breakdown

Our serverless architecture is deliberately designed to operate entirely within or near the **AWS Free Tier**, with on-demand scaling and zero baseline idle costs:

| Service | Free Tier Allowance | Our Projected Usage | Estimated Monthly Cost |
| :--- | :--- | :--- | :--- |
| **CloudFront** | 1 TB egress/mo + 10M requests | ~2 GB transfer, ~15,000 requests | **\$0.00** |
| **S3 Storage** | 5 GB standard + 20,000 GETs | ~100 MB docs & static assets | **\$0.00** |
| **Cognito User Pools** | 50,000 Monthly Active Users (MAUs) | ~50 MAUs | **\$0.00** |
| **API Gateway (HTTP v2)** | 1,000,000 requests/mo (12 mo) | ~10,000 requests | **\$0.00** |
| **AWS Step Functions** | 4,000 state transitions/mo free | ~1,000 transitions/mo (5 steps/doc) | **\$0.00** |
| **AWS Lambda** | 1,000,000 invocations + 3.2M sec compute | ~5,000 micro-invocations (256MB) | **\$0.00** |
| **DynamoDB** | 25 GB storage + 25 RCU / 25 WCU | ~20 MB storage, On-Demand mode (`documents`, `shares`, `audit` tables with TTL) | **\$0.00** |
| **Amazon SQS (DLQ)** | 1,000,000 requests/mo | < 1,000 messages | **\$0.00** |
| **CloudWatch** | 10 alarms + 5 GB log ingestion | Operational alarm + DLQ, ~200 MB logs | **\$0.00** |
| **Amazon Bedrock (Nova Lite)** | \$0.06 / 1M input tokens, \$0.024 / 1K input images | ~150 multimodal PDF/image docs | **~\$0.05** |
| **Amazon Bedrock (Titan Embed V2)** | \$0.02 / 1M input tokens *(approximate, verify on the AWS pricing page)* | Document chunking & RAG embedding generation | **<\$0.01** |
| **Groq API (`qwen/qwen3.8-27b`)** | Free tier / Pay-per-token | Document summarization & RAG QA synthesis | **\$0.00** / negligible |
| **Amazon Bedrock (Nova Micro)** | \$0.035 / 1M input tokens, \$0.14 / 1M output tokens | Plain text doc summarization & RAG fallback | **<\$0.01** |
| **Local Regex PII Check** | In-process execution within Lambda | Text pattern matching (0 extra API calls) | **\$0.00** |
| **Total Estimated Spend** | &mdash; | &mdash; | **<\$0.50 / month** |

---

## 2. OpenSearch Serverless: Cost Analysis & Why We Omitted It

> [!NOTE]
> All OpenSearch Serverless pricing figures below are **approximate, verify on the AWS pricing page** before architectural provisioning.

### The Cost Reality of Amazon OpenSearch Serverless
Amazon OpenSearch Serverless measures compute capacity in **OpenSearch Compute Units (OCUs)**.
- **Hourly Rate**: ~\$0.24 per OCU-hour *(approximate, verify on the AWS pricing page)*.
- **Minimum Allocation Rules**:
  - OpenSearch Serverless collections require a minimum of **2 OCUs for Indexing** (for data ingestion and replica resilience) and **2 OCUs for Search** (to ensure high availability).
  - Even with minimum baseline settings (1 indexing OCU + 1 search OCU in development mode), the collection cannot scale below 2 OCUs while active.

### Minimum Monthly Cost Calculation:
$$\text{Baseline Cost} = 2 \text{ OCUs} \times \$0.24/\text{hour} \times 24 \text{ hours/day} \times 30 \text{ days} \approx \mathbf{\$345.60 / \text{month}}$$
*(Production HA with 4 OCUs: $4 \times \$0.24 \times 720 \approx \mathbf{\$691.20 / \text{month}}$ &mdash; approximate, verify on the AWS pricing page)*

### Why OpenSearch Breaks the \$10 Budget:
1. OpenSearch Serverless would exhaust our entire \$10 monthly budget within **21 hours** of provisioning.
2. Even an idle collection with 0 queries charges for standby compute capacity.
3. Therefore, building OpenSearch Serverless upfront violates our budget requirements.

---

## 3. OpenSearch Migration Path (When and How to Upgrade)

### When to Migrate:
- When document volume exceeds **50,000+ items** where DynamoDB FilterExpressions become inefficient.
- When requirements mandate **fuzzy matching, phonetic typo tolerance, BM25 relevance scoring**, or **k-NN vector semantic search** across embeddings.
- When an enterprise budget (> \$400/month) is approved.

### Target Architecture for Upgrade:
```
+------------------+       DynamoDB Streams        +-----------------------+
| Amazon DynamoDB  | ----------------------------> | OpenSearch Sync Lambda|
| (Primary Record) |                               +-----------------------+
+------------------+                                           |
                                                               v SigV4
+------------------+        OpenSearch Query       +-----------------------+
|  Search Lambda   | ----------------------------> | OpenSearch Serverless |
| (API Gateway GW) |                               | Vector / Search Index |
+------------------+                               +-----------------------+
```

### Migration Implementation Steps:
1. **Enable DynamoDB Streams**: Turn on `NEW_AND_OLD_IMAGES` on the `documents` table.
2. **Provision OpenSearch Serverless Collection**: Type `SEARCH` with vector engine enabled.
3. **Deploy Streaming Ingestion Lambda**: Triggered by DynamoDB stream events to transform and bulk-index documents into OpenSearch.
4. **Update Search Lambda**: Route full-text search queries via AWS SigV4 signed requests directly to the OpenSearch endpoint.
