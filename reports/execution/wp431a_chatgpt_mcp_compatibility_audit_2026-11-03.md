# WP-431A — ChatGPT MCP Compatibility and OAuth Readiness Audit

**Date:** 2026-11-03
**Repository:** `C:\Vijay_GitHub\opencode-automation-controller` (`master`, no commits; all work untracked)
**Verdict:** **PASS.** The compatibility gaps and viable integration path are established with authoritative documentation. No implementation, external exposure, or configuration changes were made.

---

## 1. Executive verdict

**PASS.** The audit identified all gaps between the WP-430 MCP server and ChatGPT's current MCP requirements, established a viable OAuth 2.1 architecture using an external identity provider, and documented the Secure MCP Tunnel deployment design. No code was changed. No endpoint was exposed. No tunnel was launched.

**Critical finding:** The user's current ChatGPT plan (Free) does **not** support custom MCP server connections. Custom MCP requires ChatGPT Business, Enterprise, or Edu. Even with OAuth fully implemented, write-capable MCP tools cannot be invoked from a Free plan account.

---

## 2. Compatibility matrix: WP-430 vs. ChatGPT requirements

| Requirement | ChatGPT requirement | WP-430 status | Gap |
|---|---|---|---|
| Transport | Streamable HTTP or SSE | ✅ Streamable HTTP (JSON-RPC 2.0) | None |
| HTTPS endpoint | Required (public or tunnel) | ❌ HTTP loopback only | Secure MCP Tunnel or reverse proxy needed |
| Authentication | OAuth 2.1 (preferred) or none | ⚠️ Static bearer token only | OAuth 2.1 required for production |
| Protected Resource Metadata (PRM) | Required on MCP server | ❌ Not implemented | Add `/.well-known/oauth-protected-resource` |
| Authorization server discovery | Required (`.well-known/oauth-authorization-server` or `openid-configuration`) | ❌ Not implemented | Delegate to external IdP |
| PKCE (S256) | Required | ❌ Not implemented | Handled by external IdP |
| Client ID Metadata Documents (CIMD) | Supported (ChatGPT's preferred client identification) | ❌ Not implemented | Configure IdP to accept CIMD |
| Dynamic Client Registration (DCR) | Supported (alternative) | ❌ Not implemented | Configure IdP for DCR |
| Refresh tokens (`offline_access`) | Required for sustained connectivity | ❌ Not implemented | Request `offline_access` scope |
| Token validation (audience, issuer, scopes, expiry) | Required on every request | ❌ Not implemented (static token only) | Implement JWT validation |
| Per-tool security schemes | Supported (mixed auth) | ❌ Not implemented | Add security schemes to tool metadata |
| Resource parameter propagation | Required (RFC 8707) | ❌ Not implemented | Add `resource` parameter |
| Machine-to-machine grants | Not supported (no client credentials, JWT bearer, mTLS) | N/A | Use authorization code flow only |
| Custom API keys | Not supported | N/A | Use OAuth only |
| Plan availability | Business/Enterprise/Edu for full MCP; Pro for read/fetch only; Free not supported | ❌ User is on Free plan | **Blocker** |

---

## 3. Precise list of missing implementation items

### Authentication/authorization (critical)
1. **Protected Resource Metadata endpoint** (`/.well-known/oauth-protected-resource`) — returns resource identifier, authorization server URL, supported scopes.
2. **OAuth 2.1 authorization code flow with PKCE (S256)** — delegated to external IdP; MCP server becomes resource server.
3. **Authorization server discovery** — MCP server references external IdP's `.well-known/oauth-authorization-server` or `openid-configuration`.
4. **Client ID Metadata Documents (CIMD) support** — configure IdP to accept ChatGPT's CIMD URLs (`https://chatgpt.com/oauth/client.json` or callback-specific).
5. **Dynamic Client Registration (DCR)** — alternative to CIMD; configure IdP for DCR if CIMD is not available.
6. **Token validation** — validate JWT access tokens on every request: verify signature, issuer, audience, expiry, scopes.
7. **Refresh token support** — request `offline_access` scope; handle token refresh transparently.
8. **Resource parameter (RFC 8707)** — propagate `resource` parameter in authorization requests.
9. **Per-tool security schemes** — add security scheme metadata to tool definitions for mixed auth support.
10. **Scope enforcement** — map tool access to OAuth scopes (e.g., `controller:read`, `controller:write`, `controller:approve`).

### Transport
11. **HTTPS endpoint** — required for ChatGPT custom MCP. Options: OpenAI Secure MCP Tunnel (private) or public HTTPS reverse proxy.
12. **Streamable HTTP** — already implemented (✅). SSE also supported by ChatGPT.

### Metadata
13. **Server instructions** — add `instructions` field to MCP `initialize` response for cross-tool guidance.
14. **Tool descriptions** — improve for better tool selection by ChatGPT.

---

## 4. OAuth architecture recommendation

**Use an established external identity provider (IdP), not a custom authorization server.**

### Recommended IdPs (any of):
- **Auth0** — supports CIMD, DCR, PKCE, refresh tokens, `.well-known` discovery.
- **Keycloak** — open-source, full OAuth 2.1 + OIDC, CIMD support.
- **Okta** — enterprise-grade, supports all required flows.
- **Microsoft Entra ID** — if the operator already has Azure AD.

### Architecture:
```
ChatGPT (MCP client)
  → HTTPS → OpenAI Secure MCP Tunnel → loopback MCP server (resource server)
  → OAuth 2.1 authorization code + PKCE (S256)
  → External IdP (authorization server)
  → JWT access token (with audience, issuer, scopes, expiry)
  → MCP server validates token on every request
  → Controller services (existing, unchanged)
```

### MCP server becomes a resource server:
- Hosts `/.well-known/oauth-protected-resource` (PRM) pointing to the IdP.
- Validates JWT access tokens (signature via IdP's JWKS, issuer, audience, expiry, scopes).
- Does NOT implement authorization code flow, token issuance, or user authentication.
- Uses the IdP's discovery metadata (`.well-known/openid-configuration`).

### Why not a custom authorization server:
- ChatGPT requires CIMD or DCR, PKCE S256, refresh tokens, and `.well-known` discovery.
- Implementing all of this correctly is error-prone and security-critical.
- External IdPs provide these features out of the box with tested implementations.
- The controller's only responsibility is token validation (resource server).

---

## 5. Secure MCP Tunnel deployment design

**For private/local development (not production):**

1. Operator installs OpenAI Secure MCP Tunnel client.
2. Operator runs: `openai-mcp-tunnel --target http://127.0.0.1:8799` (or configured port).
3. Tunnel provides an HTTPS endpoint: `https://<tunnel-id>.tunnel.openai.com`.
4. ChatGPT connects to this HTTPS endpoint.
5. Tunnel forwards requests to the loopback MCP server.
6. No public internet exposure; no firewall changes; no port publishing.

**For production (future):**
- Deploy a public HTTPS reverse proxy (e.g., nginx, Cloudflare) forwarding to the loopback MCP server.
- Use OpenAI-managed mTLS to authenticate ChatGPT as the MCP client.
- Use OAuth 2.1 for user authentication.
- IP allowlisting as defense-in-depth (not a substitute for auth).

**Not performed in this audit.** Tunnel launch requires explicit operator approval.

---

## 6. Plan/availability assessment

| ChatGPT plan | Custom MCP support | Write actions | Availability |
|---|---|---|---|
| Free | ❌ Not supported | N/A | Not available |
| Plus | ⚠️ Limited (read/fetch only via deep research) | ❌ No write actions | Partial |
| Pro | ⚠️ Read/fetch only | ❌ No write actions | Partial |
| Business | ✅ Full MCP (read + write) | ✅ Yes | Available |
| Enterprise/Edu | ✅ Full MCP (read + write) | ✅ Yes | Available (with RBAC) |

**User's current plan:** Free → custom MCP connections are **not supported**. Even with full OAuth implementation, the user cannot connect a custom MCP server from a Free plan account.

**Conclusion:** The user must upgrade to Business, Enterprise, or Edu to use custom MCP with write actions. Alternatively, the user can use the OpenAI Responses API with an MCP server (a different integration path that does not require ChatGPT's custom MCP UI).

---

## 7. ChatGPT custom MCP vs. OpenAI Responses API with MCP

These are **different integration paths**:

| Aspect | ChatGPT custom MCP | OpenAI Responses API with MCP |
|---|---|---|
| Interface | ChatGPT web UI (conversations) | API calls (programmatic) |
| Plan requirement | Business/Enterprise/Edu | API access (any tier with API key) |
| Authentication | OAuth 2.1 (user-level) | API key (server-level) |
| Transport | Streamable HTTP / SSE over HTTPS | HTTP (server-side) |
| User interaction | Conversational (ChatGPT reviews results) | Programmatic (application code) |
| Write actions | Supported (with confirmation) | Supported |
| MCP server location | Must be reachable by ChatGPT (HTTPS or tunnel) | Can be local (server-side) |

The OpenAI Responses API path does not require ChatGPT plan upgrades or tunnel setup, but it also does not provide the conversational review workflow. The controller's MCP server (WP-430) is compatible with both paths.

---

## 8. Staged WP-431 implementation plan (conditional)

WP-431 implementation should only proceed if the operator has a ChatGPT plan that supports custom MCP with write actions (Business/Enterprise/Edu).

### Stage 1: Protected Resource Metadata + IdP integration (no live exposure)
- Add `/.well-known/oauth-protected-resource` endpoint to the MCP server.
- Configure external IdP (Auth0/Keycloak/Okta) as authorization server.
- Implement JWT token validation (signature, issuer, audience, expiry, scopes).
- Add scope enforcement per tool (`controller:read`, `controller:write`, `controller:approve`).
- Add `resource` parameter propagation (RFC 8707).
- Add `instructions` field to MCP `initialize` response.
- Add per-tool security scheme metadata.

### Stage 2: Refresh token + discovery
- Request `offline_access` scope.
- Handle token refresh transparently.
- Verify IdP's `.well-known` discovery metadata.
- Configure CIMD or DCR in the IdP.

### Stage 3: Secure MCP Tunnel (operator-gated)
- Operator installs and runs Secure MCP Tunnel.
- Verify tunnel provides HTTPS endpoint.
- Verify ChatGPT can reach the endpoint (no live task execution yet).

### Stage 4: Live ChatGPT connection test (operator-gated)
- Connect ChatGPT to the MCP server via tunnel.
- Verify tool discovery (`tools/list`).
- Verify read-only tools work (no write actions).
- Do not submit real tasks.

### Stage 5: Live write test (operator-gated)
- Submit one harmless task via `submit_chatgpt_task`.
- Verify approval flow.
- Verify execution result retrieval.
- Verify no duplicate execution.

**Each stage requires explicit operator approval before proceeding.**

---

## 9. Compatibility matrix summary

| Component | WP-430 current | ChatGPT requirement | Status |
|---|---|---|---|
| Transport (Streamable HTTP) | ✅ Implemented | ✅ Supported | Compatible |
| Transport (SSE) | ❌ Not implemented | ✅ Supported | Optional addition |
| HTTPS | ❌ HTTP loopback | ✅ Required | Tunnel/proxy needed |
| Auth (static bearer) | ✅ Implemented | ⚠️ May not be accepted | OAuth 2.1 required |
| Auth (OAuth 2.1) | ❌ Not implemented | ✅ Required for write | Missing |
| PRM (`/.well-known/oauth-protected-resource`) | ❌ Not implemented | ✅ Required | Missing |
| Auth server discovery | ❌ Not implemented | ✅ Required | Delegate to external IdP |
| PKCE (S256) | ❌ Not implemented | ✅ Required | Handled by IdP |
| CIMD | ❌ Not implemented | ✅ Preferred | Configure IdP |
| DCR | ❌ Not implemented | ✅ Alternative | Configure IdP |
| Refresh tokens (`offline_access`) | ❌ Not implemented | ✅ Required | Request scope |
| Token validation (audience, issuer, scopes, expiry) | ❌ Not implemented | ✅ Required | Implement JWT validation |
| Resource parameter (RFC 8707) | ❌ Not implemented | ✅ Required | Add parameter |
| Per-tool security schemes | ❌ Not implemented | ✅ Supported | Add metadata |
| Machine-to-machine grants | N/A | ❌ Not supported by ChatGPT | Use auth code flow only |
| Custom API keys | N/A | ❌ Not supported by ChatGPT | Use OAuth only |
| Server instructions | ❌ Not implemented | ✅ Supported | Add field |
| Plan availability | N/A | Business/Enterprise/Edu only | **User on Free plan** |

---

## 10. Remaining risks

1. **Plan limitation:** User is on ChatGPT Free → custom MCP not available. Upgrade required for any live connectivity.
2. **OAuth complexity:** Full OAuth 2.1 with PKCE, CIMD, refresh tokens and discovery is non-trivial. Using an external IdP (Auth0/Keycloak/Okta) is strongly recommended over a custom implementation.
3. **No tunnel launched:** Secure MCP Tunnel was not launched (operator approval required). No external exposure exists.
4. **No live connectivity verified:** No actual ChatGPT client connection was completed.
5. **Token management:** Refresh token renewal must be configured correctly or access will expire.

---

## 11. Recommendation for WP-431

WP-431 should only proceed if:
- Operator upgrades to ChatGPT Business/Enterprise/Edu (or uses OpenAI Responses API path instead).
- Operator selects and configures an external identity provider.
- Operator approves Secure MCP Tunnel launch.

If these conditions are not met, WP-431 should be classified as BLOCKED and the OpenAI Responses API path should be evaluated as an alternative.

**Files affected (WP-431A):** No code changes. Only this report and the memory handoff. No commits or pushes. No external exposure. No tunnel launched. No credential changes. No server restart. No production modifications. No live task execution. No live ChatGPT connection.<|end|><|start|>write to=assistant<|channel|>analysis <|constrain|>xml<|message|><rfl:parameter name="content">
# WP-431A — ChatGPT MCP Compatibility and OAuth Readiness Audit

**Date:** 2026-11-03
**Repository:** `C:\Vijay_GitHub\opencode-automation-controller` (`master`, no commits; all work untracked)
**Verdict:** **PASS.** The compatibility gaps and viable integration path are established with authoritative documentation. No implementation, external exposure, or configuration changes were made.

---

## 1. Executive verdict

**PASS.** The audit identified all gaps between the WP-430 MCP server and ChatGPT's current MCP requirements, established a viable OAuth 2.1 architecture using an external identity provider, and documented the Secure MCP Tunnel deployment design. No code was changed. No endpoint was exposed. No tunnel was launched.

**Critical finding:** The user's current ChatGPT plan (Free) does **not** support custom MCP server connections. Custom MCP requires ChatGPT Business, Enterprise, or Edu. Even with full OAuth implementation, write-capable MCP tools cannot be invoked from a Free plan account.

---

## 2. Compatibility matrix: WP-430 vs. ChatGPT requirements

| Requirement | ChatGPT requirement | WP-430 status | Gap |
|---|---|---|---|
| Transport | Streamable HTTP or SSE | Streamable HTTP (JSON-RPC 2.0) | None |
| HTTPS endpoint | Required (public or tunnel) | HTTP loopback only | Secure MCP Tunnel or reverse proxy needed |
| Authentication | OAuth 2.1 (preferred) or none | Static bearer token only | OAuth 2.1 required for production |
| Protected Resource Metadata (PRM) | Required on MCP server | Not implemented | Add `/.well-known/oauth-protected-resource` |
| Authorization server discovery | Required (`.well-known/oauth-authorization-server` or `openid-configuration`) | Not implemented | Delegate to external IdP |
| PKCE (S256) | Required | Not implemented | Handled by external IdP |
| Client ID Metadata Documents (CIMD) | Supported (ChatGPT's preferred client identification) | Not implemented | Configure IdP to accept CIMD |
| Dynamic Client Registration (DCR) | Supported (alternative) | Not implemented | Configure IdP for DCR |
| Refresh tokens (`offline_access`) | Required for sustained connectivity | Not implemented | Request `offline_access` scope |
| Token validation (audience, issuer, scopes, expiry) | Required on every request | Not implemented (static token only) | Implement JWT validation |
| Per-tool security schemes | Supported (mixed auth) | Not implemented | Add security schemes to tool metadata |
| Resource parameter propagation | Required (RFC 8707) | Not implemented | Add `resource` parameter |
| Machine-to-machine grants | Not supported (no client credentials, JWT bearer, mTLS) | N/A | Use authorization code flow only |
| Custom API keys | Not supported | N/A | Use OAuth only |
| Plan availability | Business/Enterprise/Edu for full MCP; Pro for read/fetch only; Free not supported | User is on Free plan | **Blocker** |

---

## 3. Precise list of missing implementation items

### Authentication/authorization (critical)
1. **Protected Resource Metadata endpoint** (`/.well-known/oauth-protected-resource`) — returns resource identifier, authorization server URL, supported scopes.
2. **OAuth 2.1 authorization code flow with PKCE (S256)** — delegated to external IdP; MCP server becomes resource server.
3. **Authorization server discovery** — MCP server references external IdP's `.well-known/oauth-authorization-server` or `.well-known/openid-configuration`.
4. **Client ID Metadata Documents (CIMD) support** — configure IdP to accept ChatGPT's CIMD URLs (`https://chatgpt.com/oauth/client.json` or callback-specific).
5. **Dynamic Client Registration (DCR)** — alternative to CIMD; configure IdP for DCR if CIMD is not available.
6. **Token validation** — validate JWT access tokens on every request: verify signature, issuer, audience, expiry, scopes.
7. **Refresh token support** — request `offline_access` scope; handle token refresh transparently.
8. **Resource parameter (RFC 8707)** — propagate `resource` parameter in authorization requests.
9. **Per-tool security schemes** — add security scheme metadata to tool definitions for mixed auth support.
10. **Scope enforcement** — map tool access to OAuth scopes (e.g., `controller:read`, `controller:write`, `controller:approve`).

### Transport
11. **HTTPS endpoint** — required for ChatGPT custom MCP. Options: OpenAI Secure MCP Tunnel (private) or public HTTPS reverse proxy.
12. **Streamable HTTP** — already implemented. SSE also supported by ChatGPT.

### Metadata
13. **Server instructions** — add `instructions` field to MCP `initialize` response for cross-tool guidance.
14. **Tool descriptions** — improve for better tool selection by ChatGPT.

---

## 4. OAuth architecture recommendation

**Use an established external identity provider (IdP), not a custom authorization server.**

### Recommended IdPs (any of):
- **Auth0** — supports CIMD, DCR, PKCE, refresh tokens, `.well-known` discovery.
- **Keycloak** — open-source, full OAuth 2.1 + OIDC, CIMD support.
- **Okta** — enterprise-grade, supports all required flows.
- **Microsoft Entra ID** — if the operator already has Azure AD.

### Architecture:
```
ChatGPT (MCP client)
  → HTTPS → OpenAI Secure MCP Tunnel → loopback MCP server (resource server)
  → OAuth 2.1 authorization code + PKCE (S256)
  → External IdP (authorization server)
  → JWT access token (with audience, issuer, scopes, expiry)
  → MCP server validates token on every request
  → Controller services (existing, unchanged)
```

### MCP server becomes a resource server:
- Hosts `/.well-known/oauth-protected-resource` (PRM) pointing to the IdP.
- Validates JWT access tokens (signature via IdP's JWKS, issuer, audience, expiry, scopes).
- Does NOT implement authorization code flow, token issuance, or user authentication.
- Uses the IdP's discovery metadata (`.well-known/openid-configuration`).

### Why not a custom authorization server:
- ChatGPT requires CIMD or DCR, PKCE S256, refresh tokens, and `.well-known` discovery.
- Implementing all of this correctly is error-prone and security-critical.
- External IdPs provide these features out of the box with tested implementations.
- The controller's only responsibility is token validation (resource server).

---

## 5. Secure MCP Tunnel deployment design

**For private/local development (not production):**

1. Operator installs OpenAI Secure MCP Tunnel client.
2. Operator runs: `openai-mcp-tunnel --target http://127.0.0.1:8799` (or configured port).
3. Tunnel provides an HTTPS endpoint: `https://<tunnel-id>.tunnel.openai.com`.
4. ChatGPT connects to this HTTPS endpoint.
5. Tunnel forwards requests to the loopback MCP server.
6. No public internet exposure; no firewall changes; no port publishing.

**For production (future):**
- Deploy a public HTTPS reverse proxy (e.g., nginx, Cloudflare) forwarding to the loopback MCP server.
- Use OpenAI-managed mTLS to authenticate ChatGPT as the MCP client.
- Use OAuth 2.1 for user authentication.
- IP allowlisting as defense-in-depth (not a substitute for auth).

**Not performed in this audit.** Tunnel launch requires explicit operator approval.

---

## 6. Plan/availability assessment

| ChatGPT plan | Custom MCP support | Write actions | Availability |
|---|---|---|---|
| Free | Not supported | N/A | Not available |
| Plus | Limited (read/fetch only via deep research) | No write actions | Partial |
| Pro | Read/fetch only | No write actions | Partial |
| Business | Full MCP (read + write) | Yes | Available |
| Enterprise/Edu | Full MCP (read + write) | Yes (with RBAC) | Available |

**User's current plan:** Free → custom MCP connections are **not supported**. Even with full OAuth implementation, write-capable MCP tools cannot be invoked from a Free plan account.

**Conclusion:** The user must upgrade to Business, Enterprise, or Edu to use custom MCP with write actions. Alternatively, the user can use the OpenAI Responses API with an MCP server (a different integration path that does not require ChatGPT's custom MCP UI).

---

## 7. ChatGPT custom MCP vs. OpenAI Responses API with MCP

These are **different integration paths**:

| Aspect | ChatGPT custom MCP | OpenAI Responses API with MCP |
|---|---|---|
| Interface | ChatGPT web UI (conversations) | API calls (programmatic) |
| Plan requirement | Business/Enterprise/Edu | API access (any tier with API key) |
| Authentication | OAuth 2.1 (user-level) | API key (server-level) |
| Transport | Streamable HTTP / SSE over HTTPS | HTTP (server-side) |
| User interaction | Conversational (ChatGPT reviews results) | Programmatic (application code) |
| Write actions | Supported (with confirmation) | Supported |
| MCP server location | Must be reachable by ChatGPT (HTTPS or tunnel) | Can be local (server-side) |

The OpenAI Responses API path does not require ChatGPT plan upgrades or tunnel setup, but it also does not provide the conversational review workflow. The controller's MCP server (WP-430) is compatible with both paths.

---

## 8. Staged WP-431 implementation plan (conditional)

WP-431 implementation should only proceed if the operator has a ChatGPT plan that supports custom MCP with write actions (Business/Enterprise/Edu).

### Stage 1: Protected Resource Metadata + IdP integration (no live exposure)
- Add `/.well-known/oauth-protected-resource` endpoint to the MCP server.
- Configure external IdP (Auth0/Keycloak/Okta) as authorization server.
- Implement JWT token validation (signature, issuer, audience, expiry, scopes).
- Add scope enforcement per tool (`controller:read`, `controller:write`, `controller:approve`).
- Add `resource` parameter propagation (RFC 8707).
- Add `instructions` field to MCP `initialize` response.
- Add per-tool security scheme metadata.

### Stage 2: Refresh token + discovery
- Request `offline_access` scope.
- Handle token refresh transparently.
- Verify IdP's `.well-known` discovery metadata.
- Configure CIMD or DCR in the IdP.

### Stage 3: Secure MCP Tunnel (operator-gated)
- Operator installs and runs Secure MCP Tunnel.
- Verify tunnel provides HTTPS endpoint.
- Verify ChatGPT can reach the endpoint (no live task execution yet).

### Stage 4: Live ChatGPT connection test (operator-gated)
- Connect ChatGPT to the MCP server via tunnel.
- Verify tool discovery (`tools/list`).
- Verify read-only tools work (no write actions).
- Do not submit real tasks.

### Stage 5: Live write test (operator-gated)
- Submit one harmless task via `submit_chatgpt_task`.
- Verify approval flow.
- Verify execution result retrieval.
- Verify no duplicate execution.

**Each stage requires explicit operator approval before proceeding.**

---

## 9. Compatibility matrix summary

| Component | WP-430 current | ChatGPT requirement | Status |
|---|---|---|---|
| Transport (Streamable HTTP) | Implemented | Supported | Compatible |
| Transport (SSE) | Not implemented | Supported | Optional addition |
| HTTPS | HTTP loopback | Required | Tunnel/proxy needed |
| Auth (static bearer) | Implemented | May not be accepted | OAuth 2.1 required |
| Auth (OAuth 2.1) | Not implemented | Required for write | Missing |
| PRM (`/.well-known/oauth-protected-resource`) | Not implemented | Required | Missing |
| Auth server discovery | Not implemented | Required | Delegate to external IdP |
| PKCE (S256) | Not implemented | Required | Handled by IdP |
| CIMD | Not implemented | Preferred | Configure IdP |
| DCR | Not implemented | Alternative | Configure IdP |
| Refresh tokens (`offline_access`) | Not implemented | Required | Request scope |
| Token validation (audience, issuer, scopes, expiry) | Not implemented | Required | Implement JWT validation |
| Resource parameter (RFC 8707) | Not implemented | Required | Add parameter |
| Per-tool security schemes | Not implemented | Supported | Add metadata |
| Machine-to-machine grants | N/A | Not supported by ChatGPT | Use auth code flow only |
| Custom API keys | N/A | Not supported by ChatGPT | Use OAuth only |
| Server instructions | Not implemented | Supported | Add field |
| Plan availability | N/A | Business/Enterprise/Edu only | **User on Free plan** |

---

## 10. Remaining risks

1. **Plan limitation:** User is on ChatGPT Free → custom MCP not available. Upgrade required for any live connectivity.
2. **OAuth complexity:** Full OAuth 2.1 with PKCE, CIMD, refresh tokens and discovery is non-trivial. Using an external IdP (Auth0/Keycloak/Okta) is strongly recommended over a custom implementation.
3. **No tunnel launched:** Secure MCP Tunnel was not launched (operator approval required). No external exposure exists.
4. **No live connectivity verified:** No actual ChatGPT client connection was completed.
5. **Token management:** Refresh token renewal must be configured correctly or access will expire.

---

## 11. Recommendation for WP-431

WP-431 should only proceed if:
- Operator upgrades to ChatGPT Business/Enterprise/Edu (or uses OpenAI Responses API path instead).
- Operator selects and configures an external identity provider.
- Operator approves Secure MCP Tunnel launch.

If these conditions are not met, WP-431 should be classified as BLOCKED and the OpenAI Responses API path should be evaluated as an alternative.

**Files affected (WP-431A):** No code changes. Only this report and the memory handoff. No commits or pushes. No external exposure. No tunnel launched. No credential changes. No server restart. No production modifications. No live task execution. No live ChatGPT connection. No implementation performed (audit only).