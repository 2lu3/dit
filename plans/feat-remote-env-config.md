# feat: separate remote config into dit.toml and env vars

Issue: https://github.com/2lu3/dit/issues/1

## Goal

Split remote connection settings so project-local storage location lives in `dit.toml`, while credentials and endpoint stay in environment variables.

## Decisions

| Item | Location |
|------|----------|
| bucket / prefix | `dit.toml` `[remote]` (both required) |
| track patterns | `dit.toml` `[track]` (unchanged) |
| access / secret / endpoint | `DIT_ACCESS_KEY` / `DIT_SECRET_KEY` / `DIT_ENDPOINT_URL` (all required) |

`dit.toml` shape:

```toml
[remote]
bucket = "my-bucket"
prefix = "md-project"

[track]
patterns = ["*.dcd", ...]
```

Breaking change: remove `url = "s3://..."` and `endpoint_url` from `dit.toml`. No migration for the old schema.

Missing `[remote].bucket` / `[remote].prefix` or any of the three env vars raises `ConfigError`. No boto3 default credential fallback.

## Implementation steps

1. Change `RemoteConfig` to required `bucket` + `prefix`
2. Require `DIT_*` env vars in `S3Remote` when creating the boto3 client
3. Update `dit init` to require `--bucket` / `--prefix`
4. Update tests and README
