# Future Secure MCP Tunnel Setup Checklist

1. Create tunnel in OpenAI Platform tunnel settings.
2. Associate tunnel with target ChatGPT workspace and Platform org.
3. Grant Tunnels Read/Manage/Use permissions.
4. Install/run tunnel-client (outbound only).
5. Configure MCP server URL/auth for tunnel.
6. Add custom MCP server in ChatGPT Plugins (Connection: Tunnel).
7. Verify health and a safe tool call.
8. Keep tunnel-client running during use.