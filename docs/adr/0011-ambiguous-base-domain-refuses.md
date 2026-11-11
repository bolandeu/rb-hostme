# Ambiguous base domain refuses the deploy

When two servers claim a domain by their base domains — the same base domain on
both, or `shared.dev` beside `blog.shared.dev` for `new.blog.shared.dev` — hostme
stops with `InvalidArguments` (exit 2) and names both servers, instead of taking
the first match in list order. The server is chosen explicitly with `--server`;
the ambiguity stays as the registry has it.

## Considered options

- First match by list order (the old behaviour). No code, but the deploy lands on
  a server the user never chose, and the winner depends on the order of
  `servers.yaml`, which the user does not see.
- Refuse and name both servers. One rule for both cases, a clear error, and a
  deploy never goes to a surprise server.

## Consequences

`resolve_server` raises `InvalidArguments` for an ambiguous domain, so the agent
contract carries exit code 2 for this case. A user who wants an overlapping base
domain decides with `--server` at each deploy, or keeps the base domains apart.
