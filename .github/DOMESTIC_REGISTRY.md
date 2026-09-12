# Domestic and GHCR image publishing

The production workflow publishes each selected service image to both GHCR and a configurable domestic registry. The remote host pulls the domestic copy first and falls back to the matching GHCR tag if the domestic pull fails.

## Required GitHub Actions configuration

Create these repository variables under **Settings -> Secrets and variables -> Actions -> Variables**:

| Name | Example | Notes |
| --- | --- | --- |
| `CN_REGISTRY` | `registry.cn-hangzhou.aliyuncs.com` | Registry hostname only; do not include `https://` or a trailing slash. |
| `CN_REGISTRY_NAMESPACE` | `your-namespace` | Existing namespace/project in the domestic registry. |

Create these repository secrets under **Settings -> Secrets and variables -> Actions -> Secrets**:

| Name | Purpose |
| --- | --- |
| `CN_REGISTRY_USERNAME` | Registry account or robot-account username with push and pull access. |
| `CN_REGISTRY_PASSWORD` | Registry password or access token. |

Create these repositories in the configured namespace if the registry does not create repositories on first push:

- `engine_skeleton-backend`
- `engine_skeleton-frontend`

Use private repositories unless public access is explicitly required. Grant the configured account only push and pull access to this namespace.

## Published image names

For version `sha-0123456789ab`, the workflow publishes the same build to:

```text
ghcr.io/<owner>/engine_skeleton-backend:sha-0123456789ab
<CN_REGISTRY>/<CN_REGISTRY_NAMESPACE>/engine_skeleton-backend:sha-0123456789ab

ghcr.io/<owner>/engine_skeleton-frontend:sha-0123456789ab
<CN_REGISTRY>/<CN_REGISTRY_NAMESPACE>/engine_skeleton-frontend:sha-0123456789ab
```

The `latest` tag is also published on the default branch, but deployment uses the immutable commit-derived `sha-*` tag.

## Deployment behavior

1. Build and push the selected backend and/or frontend image to both registries.
2. Log the remote Docker host into both registries.
3. Try the domestic image with a 20-minute pull-attempt limit.
4. If domestic login or pull fails, switch that service to the matching GHCR image and retry.
5. Start only the selected Compose services.

Run one manual full deployment after configuring the variables and secrets so `.deploy-images.env` contains both service image entries.
