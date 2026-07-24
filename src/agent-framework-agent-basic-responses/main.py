# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
import re
from contextlib import AbstractAsyncContextManager, AsyncExitStack
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from agent_framework import Agent, MCPStreamableHTTPTool
from agent_framework.foundry import FoundryChatClient
from agent_framework.observability import disable_instrumentation
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.ai.projects.models import CodeInterpreterTool
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Workaround: the Foundry toolbox MCP server does not implement the MCP `ping`
# method. Microsoft Agent Framework's MCPStreamableHTTPTool._ensure_connected()
# calls send_ping() on connect, which 500s and cancels the connect scope
# ("MCP server failed to initialize: Cancelled via cancel scope"). No-op the ping.
try:
    from mcp.client.session import ClientSession as _MCPClientSession

    try:
        from mcp.types import EmptyResult as _EmptyResult
    except Exception:  # pragma: no cover
        _EmptyResult = None

    async def _noop_send_ping(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return _EmptyResult() if _EmptyResult is not None else None

    _MCPClientSession.send_ping = _noop_send_ping  # type: ignore[assignment]
except Exception:  # pragma: no cover
    pass


class _EncryptedReasoningSafeFoundryChatClient(FoundryChatClient):
    """FoundryChatClient that does NOT implicitly opt into encrypted reasoning.

    agent-framework-openai's RawOpenAIChatClient._prepare_options appends
    ``include=["reasoning.encrypted_content"]`` on every *stateless* request
    (store=False and no previous_response_id/conversation). Non-reasoning models
    such as gpt-4.1 reject that with HTTP 400 "Encrypted content is not supported
    with this model", which aborts the whole turn (including any tool call).

    The FoundryAgent path (RawFoundryAgentChatClient._prepare_options) already
    strips this include unless the caller explicitly requested it; the plain
    FoundryChatClient path does not. Mirror that fix here so the chat client works
    with non-reasoning models on the latest library. A caller can still opt in by
    passing include=["reasoning.encrypted_content"] on a reasoning-capable model.
    """

    async def _prepare_options(self, messages, options, *args, **kwargs):  # type: ignore[override]
        caller_requested_encrypted_reasoning = "reasoning.encrypted_content" in (
            (options or {}).get("include") or []
        )
        run_options = await super()._prepare_options(messages, options, *args, **kwargs)
        if not caller_requested_encrypted_reasoning and isinstance(run_options.get("include"), list):
            include = [item for item in run_options["include"] if item != "reasoning.encrypted_content"]
            if include:
                run_options["include"] = include
            else:
                run_options.pop("include", None)
        return run_options


class _ToolboxAuth(httpx.Auth):
    """Injects a fresh Entra bearer token on every request to the toolbox."""

    def __init__(self, token_provider):
        self._token_provider = token_provider

    def auth_flow(self, request):
        request.headers["Authorization"] = f"Bearer {self._token_provider()}"
        yield request


# Guardrails appended to every toolbox-enabled agent's instructions. The model has
# been observed to (a) fabricate an ``authorization`` argument and stuff the
# ``USE_CONTAINER_ID=cntr_...`` value into it as a fake Bearer token, and (b) run a
# bare ``SHOW SCHEMAS`` instead of ``SHOW SCHEMAS FROM sample`` -> the toolbox
# returns "Function failed". These rules make the tool contract explicit.
_TOOLBOX_GUARDRAILS = (
    "\n\nRULES for starburst_toolbox: pass ONLY the SQL query. NEVER include an "
    "'authorization' argument, token, Bearer value, or container id (e.g. cntr_...) "
    "in the tool call \u2014 the toolbox handles its own authentication. The "
    "USE_CONTAINER_ID value is for the code interpreter ONLY; never send it to "
    "starburst_toolbox. Always fully-qualify schema discovery: use "
    "'SHOW SCHEMAS FROM sample' (never a bare 'SHOW SCHEMAS'), "
    "'SHOW TABLES FROM sample.<schema>', and 'DESCRIBE sample.<schema>.<table>'."
)


def _project_openai_base(project_endpoint: str) -> str:
    """The project-scoped OpenAI-compatible base URL used by FoundryChatClient.

    Containers must be created in THIS scope (not the account-level
    https://<account>/openai/v1) or the Code Interpreter tool resolves the
    container_id under the project and returns 404 'Container not found'.
    """
    return f"{project_endpoint.rstrip('/')}/openai/v1"


def _create_ci_container(openai_base: str, token: str, name: str = "hosted-agent-ci") -> str:
    """Create a Code Interpreter container (the 'container_id hack') and return its id.

    Pre-creating the container means the caller/agent knows the container_id up
    front and can enumerate + download the files the code interpreter writes to
    it via GET {openai_base}/containers/{id}/files[/{file_id}/content] — which the
    hosted-agent Responses output does NOT surface on its own.
    """
    resp = httpx.post(
        f"{openai_base}/containers",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"name": name},
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.json()["id"]


class _LazyAgent(AbstractAsyncContextManager):
    """Defers agent construction (and any blocking startup work such as creating
    a Code Interpreter container) to the FIRST REQUEST instead of server startup.

    The Foundry host (ResponsesHostServer) enters the agent's async context lazily
    via _ensure_agent_ready() on the first request, NOT at startup. Building the
    agent here (inside __aenter__) keeps the hosted /readiness probe fast: creating
    the container synchronously before server.run() blocks readiness under managed
    identity + private network and yields HTTP 424 session_not_ready.

    The wrapper is not a RawAgent/WorkflowAgent, so the host treats it like a normal
    Agent; run() and any other attribute access delegate to the built agent.
    """

    def __init__(self, factory):
        self._factory = factory
        self._agent = None
        self._stack: AsyncExitStack | None = None

    async def __aenter__(self):
        stack = AsyncExitStack()
        try:
            # Build off the event loop so the (potentially slow) container-create
            # network call doesn't stall other handlers.
            agent = await asyncio.to_thread(self._factory)
            if isinstance(agent, AbstractAsyncContextManager):
                await stack.enter_async_context(agent)
        except BaseException:
            await stack.aclose()
            raise
        self._agent = agent
        self._stack = stack
        return self

    async def __aexit__(self, *exc_info):
        stack, self._stack = self._stack, None
        self._agent = None
        if stack is not None:
            await stack.aclose()
        return False

    def run(self, *args, **kwargs):
        if self._agent is None:
            raise RuntimeError("_LazyAgent used before its async context was entered.")
        return self._agent.run(*args, **kwargs)

    def __getattr__(self, item):
        # Delegate everything else (e.g. name/metadata) to the built agent.
        agent = self.__dict__.get("_agent")
        if agent is not None:
            return getattr(agent, item)
        raise AttributeError(item)


class _ClientContainerAgent:
    """Option 2: the CLIENT (its own identity) pre-creates the Code Interpreter
    container and passes its id in each request as ``USE_CONTAINER_ID=cntr_...``.

    This agent reads that id per request and binds the Code Interpreter tool to
    it, so the deployed managed identity NEVER creates a container. That avoids
    the container-create RBAC 403 the managed identity hits (it lacks the
    container/agents write data action): here it only needs to USE the container,
    which its existing Responses access already covers.

    Not an async context manager (no MCP tools), so the host's _ensure_agent_ready
    is a no-op and run() is invoked directly for each request.
    """

    _CID_RE = re.compile(r"USE_CONTAINER_ID=(cntr_[A-Za-z0-9]+)")

    def __init__(self, client, base_dir):
        self._client = client
        self._base_dir = base_dir

    @classmethod
    def _extract_container_id(cls, messages):
        for msg in reversed(list(messages or [])):
            text = getattr(msg, "text", None) or ""
            match = cls._CID_RE.search(text)
            if match:
                return match.group(1)
        return None

    def _build_agent(self, container_id):
        tools = []
        if container_id:
            # String container => serializable + real SDK tool that executes
            # Python in the client-created container.
            tools.append(CodeInterpreterTool(container=container_id))
            instructions = (
                "You are a friendly assistant. Keep your answers brief.\n\n"
                "Use the code interpreter tool to execute Python and GENERATE FILES "
                f"(e.g. .pptx). Files you create are saved in container '{container_id}'. "
                "Always run code rather than doing arithmetic in your head."
            )
        else:
            instructions = "You are a friendly assistant. Keep your answers brief."
        return Agent(
            client=self._client,
            instructions=instructions + load_skills(self._base_dir),
            tools=tools,
            default_options={"store": False},
        )

    def run(self, *args, **kwargs):
        messages = kwargs.get("messages")
        if messages is None and args:
            messages = args[0]
        container_id = self._extract_container_id(messages)
        # Build a fresh agent bound to THIS request's client-supplied container.
        return self._build_agent(container_id).run(*args, **kwargs)


class _ClientContainerToolboxAgent(AbstractAsyncContextManager):
    """Combined: client-created CI container (per request) + Starburst toolbox MCP.

    Why a single agent needs two lifecycles:
    - The toolbox MCP tool must be connected ONCE via the host's
      _ensure_agent_ready() (which enters this agent's async context), so that an
      OAuth consent failure surfaces as an ``oauth_consent_request`` the host can
      relay to a UI. Hence this class is an async context manager and the toolbox
      tool lives on a base agent entered in __aenter__.
    - The Code Interpreter tool must be bound to a container the CLIENT created
      (passed per request as ``USE_CONTAINER_ID=cntr_...``) so the managed identity
      never creates a container (avoids the container-create RBAC 403). Hence the
      CI tool is injected PER REQUEST via Agent.run(tools=...).
    """

    _CID_RE = re.compile(r"USE_CONTAINER_ID=(cntr_[A-Za-z0-9]+)")

    def __init__(self, client, base_dir, toolbox_endpoint, get_token):
        self._client = client
        self._base_dir = base_dir
        self._toolbox_endpoint = toolbox_endpoint
        self._get_token = get_token
        self._base_agent = None
        self._toolbox_tool = None
        self._stack: AsyncExitStack | None = None

    async def __aenter__(self):
        stack = AsyncExitStack()
        try:
            toolbox_http_client = httpx.AsyncClient(auth=_ToolboxAuth(self._get_token), timeout=120.0)
            toolbox_tool = MCPStreamableHTTPTool(
                name="starburst_toolbox",
                description="Starburst data tools exposed by the Foundry toolbox (schema discovery + queries).",
                url=self._toolbox_endpoint,
                http_client=toolbox_http_client,
                load_prompts=False,
            )
            instructions = (
                "You are a friendly assistant. Keep your answers brief.\n\n"
                "You have TWO tools:\n"
                "1. code_interpreter \u2014 run Python for calculations and to GENERATE FILES "
                "(e.g. .pptx). Files you create are saved in the provided container.\n"
                "2. starburst_toolbox \u2014 Starburst data tools (schema discovery + queries). "
                "Before querying an unknown table: SHOW SCHEMAS FROM sample; SHOW TABLES FROM "
                "sample.<schema>; DESCRIBE sample.<schema>.<table>.\n\n"
                "Always run code rather than doing arithmetic in your head."
                + _TOOLBOX_GUARDRAILS
            )
            base_agent = Agent(
                client=self._client,
                instructions=instructions + load_skills(self._base_dir),
                tools=[toolbox_tool],
                default_options={"store": False},
            )
            # Enter the base agent so the toolbox MCP connects now; a consent failure
            # propagates to the host, which relays it as oauth_consent_request.
            if isinstance(base_agent, AbstractAsyncContextManager):
                await stack.enter_async_context(base_agent)
        except BaseException:
            await stack.aclose()
            raise
        self._base_agent = base_agent
        self._toolbox_tool = toolbox_tool
        self._stack = stack
        return self

    async def __aexit__(self, *exc_info):
        stack, self._stack = self._stack, None
        self._base_agent = None
        self._toolbox_tool = None
        if stack is not None:
            await stack.aclose()
        return False

    @classmethod
    def _extract_container_id(cls, messages):
        for msg in reversed(list(messages or [])):
            text = getattr(msg, "text", None) or ""
            match = cls._CID_RE.search(text)
            if match:
                return match.group(1)
        return None

    def run(self, *args, **kwargs):
        if self._base_agent is None:
            raise RuntimeError("_ClientContainerToolboxAgent used before its context was entered.")
        messages = kwargs.get("messages")
        if messages is None and args:
            messages = args[0]
        container_id = self._extract_container_id(messages)
        # Per-request tools: the already-connected toolbox + the client's CI container.
        tools = [self._toolbox_tool]
        if container_id:
            tools.append(CodeInterpreterTool(container=container_id))
        return self._base_agent.run(*args, tools=tools, **kwargs)

    def __getattr__(self, item):
        agent = self.__dict__.get("_base_agent")
        if agent is not None:
            return getattr(agent, item)
        raise AttributeError(item)


def load_skills(base_dir: str) -> str:
    """Direct injection: read bundled SKILL.md files and return text to append
    to the agent's system instructions. No network/skills-API call is made."""
    skills_dir = Path(base_dir) / "skills"
    if not skills_dir.exists():
        return ""
    parts = []
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        text = skill_md.read_text(encoding="utf-8")
        # Strip YAML frontmatter (content between the leading --- fences)
        if text.startswith("---"):
            end = text.find("---", 3)
            if end != -1:
                text = text[end + 3:]
        parts.append(text.strip())
    if not parts:
        return ""
    skill_names = []
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        skill_names.append(skill_md.parent.name)
    # Observability hack: ask the model to emit a machine-readable marker whenever
    # it actually applies one of these bundled skills. The client (UI) parses and
    # strips the marker to surface a "skill referenced" badge -- otherwise skill
    # usage is invisible (skills are just injected instructions, not tool calls).
    marker_note = (
        "\n\n# Skill-usage marker (required)\n\n"
        "Whenever you APPLY one of the bundled skills above to fulfil a request, "
        "include a marker on its own line at the END of your reply, exactly:\n"
        "SKILL_USED: <skill-name>\n"
        f"Valid skill names: {', '.join(skill_names)}. "
        "Emit one marker line per skill you used. If you used no skill, emit nothing."
    )
    return (
        "\n\n# Available skills (bundled with this agent)\n\n"
        + "\n\n---\n\n".join(parts)
        + marker_note
    )


def main():
    model_name = os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME") or os.getenv("FOUNDRY_MODEL_NAME")
    if not model_name:
        raise RuntimeError(
            "Model deployment name is not configured. Set "
            "AZURE_AI_MODEL_DEPLOYMENT_NAME or FOUNDRY_MODEL_NAME."
        )

    credential = DefaultAzureCredential()
    client = _EncryptedReasoningSafeFoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=model_name,
        credential=credential,
    )

    # AGENT_TOOL_MODE selects which tool configuration this hosted agent runs with:
    #   "toolbox"              -> Starburst tools via the Foundry toolbox MCP (default).
    #   "code_interpreter"     -> Foundry Code Interpreter (container:auto), NO toolbox.
    #   "ci_container_toolbox" -> Code Interpreter with an explicit container_id
    #                             (the "container_id hack") + the Starburst toolbox MCP.
    #   "ci_client_container"  -> Code Interpreter bound to a container_id that the
    #                             CLIENT creates and passes per request. The managed
    #                             identity never creates a container (avoids RBAC 403).
    tool_mode = os.getenv("AGENT_TOOL_MODE", "toolbox").strip().lower()

    # Set by the ci_container_toolbox / ci_client_container branches to a custom
    # agent object; when non-None the common Agent(...) construction is skipped.
    lazy_agent = None

    if tool_mode == "ci_client_container":
        # Option 2: the client pre-creates the container (its own identity) and
        # passes USE_CONTAINER_ID=cntr_... in each request. The agent binds the CI
        # tool to that container per request -> the managed identity only USES the
        # container, never creates it (sidesteps the container-create RBAC 403).
        # CI_INCLUDE_TOOLBOX=1 also adds the Starburst toolbox (consent surfaces via
        # the host as oauth_consent_request; complete it in a UI).
        disable_instrumentation()
        base_dir = os.path.dirname(os.path.abspath(__file__))
        include_toolbox = os.getenv("CI_INCLUDE_TOOLBOX", "0").strip().lower() not in ("0", "false", "no")
        if include_toolbox:
            get_token = get_bearer_token_provider(credential, "https://ai.azure.com/.default")
            toolbox_endpoint = os.getenv(
                "TOOLBOX_MCP_ENDPOINT",
                "https://YOUR_FOUNDRY_ACCOUNT.services.ai.azure.com/api/projects/YOUR_PROJECT/toolboxes/your-toolbox/mcp?api-version=v1",
            )
            lazy_agent = _ClientContainerToolboxAgent(client, base_dir, toolbox_endpoint, get_token)
        else:
            lazy_agent = _ClientContainerAgent(client, base_dir)
    elif tool_mode == "ci_container_toolbox":
        # Combined route: hosted agent + Code Interpreter (OUTSIDE the toolbox,
        # with an explicit pre-created container_id) + Starburst MCP (IN the
        # toolbox). Deployed to Foundry, tested via code.
        #
        # container_id hack: we create a container so the caller knows its id and
        # can download CI-generated files directly from it (the hosted-agent
        # Responses output does not return container_file_citations).
        #
        # READINESS: the container is created LAZILY (on the first request) via
        # _LazyAgent, NOT at startup. Creating it synchronously before
        # server.run() blocks the hosted /readiness probe under managed identity +
        # private network -> HTTP 424 session_not_ready.
        disable_instrumentation()
        get_token = get_bearer_token_provider(credential, "https://ai.azure.com/.default")
        openai_base = _project_openai_base(os.environ["FOUNDRY_PROJECT_ENDPOINT"])
        include_toolbox = os.getenv("CI_INCLUDE_TOOLBOX", "1").strip().lower() not in ("0", "false", "no")
        base_dir = os.path.dirname(os.path.abspath(__file__))

        def _build_ci_container_agent():
            container_id = _create_ci_container(openai_base, get_token())
            print(f"[ci_container_toolbox] created container_id={container_id}", flush=True)
            # CI tool bound to OUR container_id (string container => serializable,
            # real SDK tool => actually executes Python in that container).
            tools = [CodeInterpreterTool(container=container_id)]
            if include_toolbox:
                toolbox_endpoint = os.getenv(
                    "TOOLBOX_MCP_ENDPOINT",
                    "https://YOUR_FOUNDRY_ACCOUNT.services.ai.azure.com/api/projects/YOUR_PROJECT/toolboxes/your-toolbox/mcp?api-version=v1",
                )
                toolbox_http_client = httpx.AsyncClient(auth=_ToolboxAuth(get_token), timeout=120.0)
                tools.append(
                    MCPStreamableHTTPTool(
                        name="starburst_toolbox",
                        description="Starburst data tools exposed by the Foundry toolbox (schema discovery + queries).",
                        url=toolbox_endpoint,
                        http_client=toolbox_http_client,
                        load_prompts=False,
                    )
                )
            base_instructions = (
                "You are a friendly assistant. Keep your answers brief.\n\n"
                "You have TWO tools:\n"
                "1. code_interpreter \u2014 run Python for calculations and to GENERATE FILES "
                f"(e.g. .pptx). Files you create are saved in container '{container_id}'.\n"
                "2. starburst_toolbox \u2014 Starburst data tools (schema discovery + queries).\n\n"
                "Always run code rather than doing arithmetic in your head. Whenever you "
                "create a file with the code interpreter, you MUST end your reply with "
                f"EXACTLY this line so the caller can download it:\n"
                f"CONTAINER_ID={container_id} FILE=<filename>"
                + _TOOLBOX_GUARDRAILS
            )
            return Agent(
                client=client,
                instructions=base_instructions + load_skills(base_dir),
                tools=tools,
                default_options={"store": False},
            )

        lazy_agent = _LazyAgent(_build_ci_container_agent)
    elif tool_mode == "code_interpreter":
        # Route #5/#6: hosted agent + Code Interpreter without a toolbox.
        #
        # IMPORTANT: use the REAL SDK tool from get_code_interpreter_tool(). A
        # plain-dict tool spec serializes cleanly but is NOT wired as an
        # executable tool -> the model only *pretends* to run code (verified: it
        # returns a wrong SHA-256 with no code_interpreter_call item). The real
        # tool object is what actually executes Python in the container:auto
        # sandbox.
        #
        # The real tool's `container` is an AutoCodeInterpreterToolParam that the
        # agent_framework observability layer tries to json.dumps() as a span
        # attribute, raising "Object of type AutoCodeInterpreterToolParam is not
        # JSON serializable". Execution and tracing are separate paths, so we
        # disable agent_framework instrumentation (the crashing tool-span path
        # early-returns when OBSERVABILITY_SETTINGS.ENABLED is False). Platform
        # (azure.ai.agentserver) telemetry is unaffected.
        disable_instrumentation()
        tools = [client.get_code_interpreter_tool()]
        base_instructions = (
            "You are a friendly assistant. Keep your answers brief.\n\n"
            "Use the code interpreter tool to execute Python for any calculation, "
            "data processing, or file generation. Always run code rather than doing "
            "arithmetic in your head."
        )
    else:
        # Starburst MCP tool consumed via a Foundry TOOLBOX (managed MCP endpoint) — the
        # documented hosted-agent path for OAuth-identity-passthrough MCP tools. A fresh
        # Entra bearer token is injected on every request via header_provider. tool_choice
        # is left unset => "auto": the model calls the tool only when relevant.
        get_token = get_bearer_token_provider(credential, "https://ai.azure.com/.default")
        # NOTE: do NOT use a FOUNDRY_-prefixed env var name — the platform reserves and
        # overwrites that prefix at runtime. Use a neutral name (TOOLBOX_MCP_ENDPOINT).
        toolbox_endpoint = os.getenv(
            "TOOLBOX_MCP_ENDPOINT",
            "https://YOUR_FOUNDRY_ACCOUNT.services.ai.azure.com/api/projects/YOUR_PROJECT/toolboxes/your-toolbox/mcp?api-version=v1",
        )
        # Use an httpx client with a long timeout (per the Foundry toolbox docs) and
        # bearer auth via httpx.Auth. load_prompts=False avoids the prompts/list 500
        # (the toolbox MCP server doesn't implement prompts/list).
        toolbox_http_client = httpx.AsyncClient(auth=_ToolboxAuth(get_token), timeout=120.0)
        tools = [
            MCPStreamableHTTPTool(
                name="starburst_toolbox",
                description="Starburst data tools exposed by the Foundry toolbox (schema discovery + queries).",
                url=toolbox_endpoint,
                http_client=toolbox_http_client,
                load_prompts=False,
            )
        ]
        base_instructions = (
            "You are a friendly assistant. Keep your answers brief.\n\n"
            "When answering data questions, use the 'starburst' MCP tool. Before querying an "
            "unknown table, discover the schema first:\n"
            "- SHOW SCHEMAS FROM sample\n"
            "- SHOW TABLES FROM sample.<schema>\n"
            "- DESCRIBE sample.<schema>.<table>\n"
            "Then build the final query using fully-qualified names."
            + _TOOLBOX_GUARDRAILS
        )

    skill_instructions = load_skills(os.path.dirname(os.path.abspath(__file__)))

    if lazy_agent is not None:
        # ci_container_toolbox: agent (and its container) is built on first request.
        agent = lazy_agent
    else:
        agent = Agent(
            client=client,
            instructions=base_instructions + skill_instructions,
            tools=tools,
            # History will be managed by the hosting infrastructure, thus there
            # is no need to store history by the service. Learn more at:
            # https://developers.openai.com/api/reference/resources/responses/methods/create
            default_options={"store": False},
        )

    server = ResponsesHostServer(agent)
    server.run()


if __name__ == "__main__":
    main()
