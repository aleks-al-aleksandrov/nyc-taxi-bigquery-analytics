# Redshift vs. BigQuery: a conceptual note

> **This is a reading note, not experience.** I have not built anything on
> Amazon Redshift. This page maps the BigQuery ideas used in this project to
> their nearest Redshift counterparts, based only on the official
> documentation linked below. Check the linked pages for current details.

## Physical layout

| Concern | BigQuery (used in this project) | Redshift (not used) |
|---|---|---|
| Prune data a query does not need | **Partitioning** splits a table into segments, for example one per day, and queries that filter on the partition column skip the rest. [Partitioned tables](https://cloud.google.com/bigquery/docs/partitioned-tables) | **Sort keys** order data on disk, and zone maps let scans skip blocks outside a range filter. [Sort keys](https://docs.aws.amazon.com/redshift/latest/dg/t_Sorting_data.html) |
| Co-locate rows with similar values | **Clustering** sorts storage blocks by up to four columns, so filters on them skip blocks. [Clustered tables](https://cloud.google.com/bigquery/docs/clustered-tables) | Also handled by sort keys (compound or interleaved). [Sort keys](https://docs.aws.amazon.com/redshift/latest/dg/t_Sorting_data.html) |
| Place data across compute for joins | No user setting; storage and compute are separate and BigQuery handles shuffles. [Storage overview](https://cloud.google.com/bigquery/docs/storage_overview) | **Distribution style / DISTKEY** (`AUTO`, `EVEN`, `KEY`, `ALL`) decides which node slice holds each row; a matching DISTKEY on both sides of a join avoids redistribution. [Distribution styles](https://docs.aws.amazon.com/redshift/latest/dg/c_choosing_dist_sort.html) |

The rough mapping: BigQuery partitioning and clustering do the same job as
Redshift sort keys, which is skipping data. DISTKEY has no BigQuery equivalent,
because it is about node placement and BigQuery does not expose that.

## Pricing model

| | BigQuery | Redshift |
|---|---|---|
| Main on-demand model | **Per byte scanned.** On-demand queries are billed by bytes processed, so pruning lowers cost directly, which is what this project measures. Capacity (slot-based) pricing is also available. [BigQuery pricing](https://cloud.google.com/bigquery/pricing) | **Per compute time.** Provisioned clusters are billed per node-hour, and Redshift Serverless per RPU-hour of compute used. Scanning fewer blocks makes queries faster but does not directly change the bill. [Redshift pricing](https://aws.amazon.com/redshift/pricing/), [Serverless billing](https://docs.aws.amazon.com/redshift/latest/mgmt/serverless-billing.html) |
| Exception | — | Redshift Spectrum queries over data in S3 are billed per byte scanned, closer to BigQuery on-demand. [Redshift pricing](https://aws.amazon.com/redshift/pricing/) |

## What this means for the study in this repo

The `bytes billed` column in [performance.md](performance.md) is a direct
cost proxy only on BigQuery on-demand pricing. On a provisioned Redshift
cluster the comparable metric would be query runtime and concurrency on a
fixed-cost cluster. I have not tested this.
