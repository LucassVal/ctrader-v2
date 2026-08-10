"""
PROPOSITO: T2
SPEC: S1.1
ROADMAP: 1.5
"""

from __future__ import annotations

import contextlib
import json
import logging
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from typing import Any

import yaml

from utils.logger import get_logger

logger = get_logger(__name__, "MCP")

# ---------------------------------------------------------------------------
# estado global
# ---------------------------------------------------------------------------

_mcp_url: str = ""
_mcp_headers: dict[str, str] = {}
_mcp_timeout: float = 5.0
_mcp_session_id: str = ""
_mcp_initialized: bool = False
_session_override_token: str | None = None

# ---------------------------------------------------------------------------
# Session lifecycle (SSOT — usado por orc_coleta, backfill, dashboard health)
# MCP expira sessoes em ~7-8 min server-side independente de atividade.
# ---------------------------------------------------------------------------
_last_handshake: float = 0.0
SESSION_MAX_AGE: float = 300.0  # 5 min — renova com folga antes dos ~7-8 min do server

# ---------------------------------------------------------------------------
# Gateway throttle + cache (ROADMAP 1.5)
# ---------------------------------------------------------------------------
_throttle_tokens: float = 50.0
_throttle_max: float = 50.0
_throttle_rate: float = 50.0
_throttle_last: float = 0.0
_request_cache: dict[str, tuple[float, Any]] = {}
_CACHE_TTL_LIVE: float = 1.0
_CACHE_TTL_HISTORIC: float = 30.0

MUTANT_TOOLS = {"create_order", "close_position", "cancel_order", "amend_order", "amend_position"}
HISTORIC_TOOLS = {"get_trendbars", "get_order_history", "get_deals", "get_symbols"}


def _throttle_wait() -> None:
    global _throttle_tokens, _throttle_last
    now = time.monotonic()
    elapsed = now - _throttle_last
    _throttle_tokens = min(_throttle_max, _throttle_tokens + elapsed * _throttle_rate)
    _throttle_last = now
    if _throttle_tokens < 1.0:
        wait = (1.0 - _throttle_tokens) / _throttle_rate
        time.sleep(wait)
        _throttle_tokens = 0.0
    else:
        _throttle_tokens -= 1.0


def _cache_key(tool: str, args: dict[str, Any]) -> str:
    return f"{tool}:{json.dumps(args, sort_keys=True, default=str)}"


def _cache_get(tool: str, args: dict[str, Any]) -> Any | None:
    entry = _request_cache.get(_cache_key(tool, args))
    if entry is None:
        return None
    expiry, result = entry
    if time.monotonic() < expiry:
        return result
    del _request_cache[_cache_key(tool, args)]
    return None


def _cache_set(tool: str, args: dict[str, Any], result: Any, ttl: float) -> None:
    key = _cache_key(tool, args)
    _request_cache[key] = (time.monotonic() + ttl, result)
    if len(_request_cache) > 100:
        now = time.monotonic()
        for k in list(_request_cache):
            if _request_cache[k][0] < now:
                del _request_cache[k]

# ---------------------------------------------------------------------------
# parser SSE
# ---------------------------------------------------------------------------


def _parse_sse_body(body: str) -> dict[str, Any]:
    """Extrai JSON de resposta SSE (event: ... data: {...})."""
    for line in body.split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            return json.loads(line[6:])
    return json.loads(body)


# ---------------------------------------------------------------------------
# init + handshake
# ---------------------------------------------------------------------------


def init_client(config_path: str = "config.yaml", force: bool = False) -> None:
    """Carrega config, inicializa cliente MCP e faz handshake.

    Keep-alive (ROADMAP D.10): se ja inicializado, reusa sessao — nao refaz handshake.
    force=True: reseta estado e refaz handshake completo (reconexao apos session expiry).

    Se set_session_token() setou um override (login manual do dashboard), ele
    prevalece sobre auth_token do config.yaml — nunca persistido em disco.
    """
    global _mcp_url, _mcp_headers, _mcp_timeout, _mcp_initialized, _mcp_session_id

    if force:
        logger.info("MCP force-reconnect: resetando sessao")
        _mcp_initialized = False
        _mcp_session_id = ""
        _mcp_url = ""

    if _mcp_initialized and _mcp_url:
        logger.debug("MCP ja inicializado - reusando sessao (keep-alive)")
        return

    with open(config_path) as f:
        config = yaml.safe_load(f)

    mcp_cfg = config["mcp"]
    _mcp_url = mcp_cfg["url"]
    token = _session_override_token or mcp_cfg["auth_token"]
    # Expande ${VAR} env vars (ex: ${CTRADER_TOKEN})
    import os as _os
    import re as _re
    token = _re.sub(r'\$\{(\w+)\}', lambda m: _os.environ.get(m.group(1), m.group(0)), token)
    _mcp_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        mcp_cfg["auth_header"]: token,
    }
    _mcp_timeout = mcp_cfg.get("timeout_seconds", 5.0)

    logger.info("MCP Client inicializado: %s (token=%s)",
                _mcp_url, "sessao manual" if _session_override_token else "config.yaml")
    _initialize_mcp()


def set_session_token(token: str | None) -> None:
    """Login manual (dashboard): define token de sessao SO EM MEMORIA (processo atual).
    Nunca escrito em config.yaml nem em disco. None limpa o override (volta ao config.yaml).
    Forca handshake novo na proxima init_client() (derruba o keep-alive atual)."""
    global _session_override_token, _mcp_initialized, _mcp_url
    _session_override_token = token.strip() if token else None
    _mcp_initialized = False
    _mcp_url = ""


def has_session_token() -> bool:
    """True se um token manual (login dashboard) esta ativo nesta sessao do processo."""
    return _session_override_token is not None


def try_session_token(token: str, config_path: str = "config.yaml") -> dict[str, Any]:
    """Login manual atomico: so aplica o override se o handshake com o token
    NOVO for bem-sucedido. Falha = restaura o estado anterior (nunca deixa a
    sessao "meio trocada" com um token nao-validado)."""
    global _session_override_token, _mcp_initialized, _mcp_url, _mcp_headers

    saved = (_session_override_token, _mcp_initialized, _mcp_url, dict(_mcp_headers))
    set_session_token(token)
    try:
        init_client(config_path)
        return call_tool("get_version", {})
    except Exception:
        _session_override_token, _mcp_initialized, _mcp_url = saved[0], saved[1], saved[2]
        _mcp_headers = saved[3]
        raise


def get_client() -> dict[str, Any]:
    """Retorna config do cliente para uso externo."""
    return {"url": _mcp_url, "headers": _mcp_headers, "timeout": _mcp_timeout}


def _initialize_mcp() -> None:
    """Handshake MCP: initialize  session  initialized."""
    global _mcp_initialized, _mcp_session_id, _mcp_headers

    init_payload = {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "hermes-ctrader-v2", "version": "1.0"},
        },
        "id": 0,
    }

    data = json.dumps(init_payload).encode("utf-8")
    req = urllib.request.Request(_mcp_url, data=data, headers=_mcp_headers, method="POST")

    try:
        try:
            with urllib.request.urlopen(req, timeout=_mcp_timeout) as resp:
                body = resp.read().decode("utf-8")
                sid = resp.headers.get("mcp-session-id", "")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            sid = e.headers.get("mcp-session-id", "")

        result = _parse_sse_body(body)
        if "error" in result:
            err = result["error"]
            if isinstance(err, dict):
                raise MCPMethodError("initialize", err.get("code", -1), err.get("message", ""))
            else:
                logger.error("MCP devolveu erro como string: %s", str(err)[:200])
                raise MCPMethodError("initialize", -1, str(err))

        server_info = result.get("result", {})
        _mcp_session_id = sid
        if sid:
            _mcp_headers["mcp-session-id"] = sid

        logger.info("MCP handshake OK. %s v%s session=%s",
                    server_info.get("serverInfo", {}).get("name", "?"),
                    server_info.get("protocolVersion", "?"),
                    sid[:16] if sid else "none")

        # notificacao initialized
        notif = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        notif_data = json.dumps(notif).encode("utf-8")
        notif_req = urllib.request.Request(_mcp_url, data=notif_data, headers=_mcp_headers, method="POST")
        with contextlib.suppress(urllib.error.HTTPError):
            urllib.request.urlopen(notif_req, timeout=_mcp_timeout)

        _mcp_initialized = True
        touch_handshake()  # registra timestamp da sessao fresca

    except MCPMethodError:
        raise
    except Exception as e:
        logger.error("MCP initialize erro: %s", e)
        raise MCPConnectionError(f"Handshake falhou: {e}") from e


def ensure_session_fresh(config_path: str = "config.yaml") -> bool:
    """Reconecta proativamente se sessao MCP esta proxima de expirar.

    cTrader MCP expira sessoes em ~7-8 min independente de atividade.
    Renova a cada SESSION_MAX_AGE (5 min) para evitar \"Session not found\".
    SSOT — usado por orc_coleta (F0 live), backfill, e dashboard health.

    Returns True se sessao OK (nao precisou renovar ou renovou com sucesso).
    """
    global _last_handshake
    now = time.monotonic()
    if now - _last_handshake > SESSION_MAX_AGE:
        logger.info("Renovando sessao MCP (idade: %.0fs > %ds)...",
                     now - _last_handshake, SESSION_MAX_AGE)
        try:
            _mcp_initialized = False
            _mcp_session_id = ""
            _mcp_url = ""
            init_client(config_path, force=True)
            _last_handshake = time.monotonic()
            return True
        except Exception as e:
            logger.error("Falha ao renovar sessao: %s", e)
            return False
    return True


def get_session_age() -> float:
    """Idade da sessao MCP em segundos (0 se nunca inicializada)."""
    if _last_handshake == 0.0:
        return 0.0
    return time.monotonic() - _last_handshake


def touch_handshake() -> None:
    """Registra timestamp do handshake (chamado apos init_client bem-sucedido)."""
    global _last_handshake
    _last_handshake = time.monotonic()


# ---------------------------------------------------------------------------
# chamada MCP (tools/call)
# ---------------------------------------------------------------------------


def call_tool(tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Chama tool MCP via tools/call com throttle+cache (ROADMAP 1.5)."""
    if not _mcp_url:
        raise MCPConnectionError("Cliente nao inicializado. Rode init_client().")

    args = arguments or {}

    # Mutant: sem cache, throttle leve
    if tool_name in MUTANT_TOOLS:
        _throttle_wait()
        return _call_tool_raw(tool_name, args)

    # Cache TTL
    is_historic = tool_name in HISTORIC_TOOLS
    ttl = _CACHE_TTL_HISTORIC if is_historic else _CACHE_TTL_LIVE
    cached = _cache_get(tool_name, args)
    if cached is not None:
        return cached

    # Throttle adaptativo
    global _throttle_rate
    old_rate = _throttle_rate
    if is_historic:
        _throttle_rate = 5.0
    _throttle_wait()
    if is_historic:
        _throttle_rate = old_rate

    result = _call_tool_raw(tool_name, args)
    _cache_set(tool_name, args, result, ttl)
    return result


def _call_tool_raw(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Chamada HTTP pura (sem cache/throttle)."""

    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments or {},
        },
        "id": int(time.monotonic() * 1000) % 100000,
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(_mcp_url, data=data, headers=_mcp_headers, method="POST")

    try:
        try:
            with urllib.request.urlopen(req, timeout=_mcp_timeout) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")

        result = _parse_sse_body(body)

        if "error" in result:
            err = result["error"]
            logger.error("MCP erro: %s (tool=%s)", err.get("message", str(err)), tool_name)
            raise MCPMethodError(tool_name, err.get("code", -1), err.get("message", ""))

        # tools/call retorna {content: [{type: "text", text: "..."}]}
        content = result.get("result", {}).get("content", [])
        if content and isinstance(content, list) and len(content) > 0:
            text = content[0].get("text", "")
            if text:
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return {"text": text}

        return result.get("result", result)

    except urllib.error.URLError as e:
        raise MCPConnectionError(str(e)) from e
    except json.JSONDecodeError as e:
        raise MCPProtocolError(str(e)) from e


# ---------------------------------------------------------------------------
# 16 TOOLS (nomes oficiais do cTrader MCP)
# ---------------------------------------------------------------------------

# ===== ACCOUNT =====

def get_balance() -> dict[str, Any]:
    """Saldo, equity, margem livre."""
    return call_tool("get_balance")


def get_assets() -> list[dict[str, Any]]:
    """Moedas disponiveis na conta."""
    return call_tool("get_assets")


# ===== SYMBOLS / MARKET DATA =====

# Cache: symbolName  symbolId (Remote HTTP usa inteiro, no string)
_symbol_cache: dict[str, int] = {}
_symbol_cache_loaded = False
# Cache estendido: symbolName  metadata completo
_symbol_meta_cache: dict[str, dict[str, Any]] = {}

# Idempotency -- UUID por sesso para evitar ordens duplicadas
import uuid as _uuid_module

_IDEMPOTENCY_PREFIX: str = f"sess-{_uuid_module.uuid4().hex[:8]}"


def _load_symbol_cache() -> dict[str, int]:
    """Carrega mapping symbolNamesymbolId + metadata via get_symbols(). Cache 1/sesso."""
    global _symbol_cache, _symbol_meta_cache, _symbol_cache_loaded
    if _symbol_cache_loaded and _symbol_cache:
        return _symbol_cache
    try:
        symbols = call_tool("get_symbols", {})
        # Remote HTTP pode retornar {"symbols": [...]} ou lista direta
        if isinstance(symbols, dict):
            symbols = symbols.get("symbols", [])
        if isinstance(symbols, list):
            for s in symbols:
                if isinstance(s, dict):
                    name = s.get("symbolName", "")
                    sid = s.get("symbolId", 0)
                    if name and sid:
                        _symbol_cache[name] = int(sid)
                        _symbol_meta_cache[name] = {
                            "symbolId": int(sid),
                            "pipDigits": s.get("pipDigits", 5),
                            "lotSize": s.get("lotSize", 100000),
                            "volumeStep": s.get("volumeStep", 1000),
                            "minVolume": s.get("minVolume", 1000),
                            "baseAssetId": s.get("baseAssetId"),
                            "quoteAssetId": s.get("quoteAssetId"),
                            "symbolCategoryId": s.get("symbolCategoryId"),
                            "description": s.get("description", ""),
                        }
        _symbol_cache_loaded = True
        logger.info("Symbol cache: %d smbolos + metadata", len(_symbol_cache))
    except Exception as e:
        logger.error("Falha ao carregar symbol cache: %s", e)
    return _symbol_cache


def resolve_symbol(name: str) -> int:
    """Converte symbolName (ex: 'EURUSD')  symbolId (int)."""
    cache = _load_symbol_cache()
    sid = cache.get(name)
    if sid is None:
        raise MCPMethodError("get_spot_prices", -32602, f"Smbolo no encontrado: {name}")
    return sid


def get_symbols(query: str | None = None) -> list[dict[str, Any]]:
    """Lista ou busca smbolos. Atualiza cache automtico."""
    global _symbol_cache, _symbol_cache_loaded
    args: dict[str, Any] = {}
    if query:
        args["query"] = query
    result = call_tool("get_symbols", args)
    # Remote HTTP pode retornar {"symbols": [...]}
    if isinstance(result, dict):
        result = result.get("symbols", [])
    # Atualiza cache com os resultados
    if isinstance(result, list):
        for s in result:
            if isinstance(s, dict):
                name = s.get("symbolName", "")
                sid = s.get("symbolId", 0)
                if name and sid:
                    _symbol_cache[name] = int(sid)
        _symbol_cache_loaded = True
    return result


# Periodos aceitos pelo MCP remoto -- enum literal do inputSchema de get_trendbars.
# NAO existe M_10 no servidor: scalp de 10min e incoletavel, usar M_15.
# Aceita tanto o formato interno ("m5") quanto o do MCP ("M_5").
_PERIOD_MAP: dict[str, str] = {
    "m1": "M_1", "m5": "M_5", "m15": "M_15", "m30": "M_30",
    "h1": "H_1", "h4": "H_4", "d1": "D_1", "w1": "W_1", "mn1": "MN_1",
}


def _timeframe_to_period(tf: str) -> str:
    """Converte timeframe (m5 ou M_5) para periodo do MCP (M_5).

    SEM FALLBACK (R51 FAIL-FAST + R-NO-SILENT-FAIL). Timeframe desconhecido
    levanta erro em vez de virar outro periodo em silencio.

    O fallback removido mapeava M10 -> M_15 e QUALQUER entrada invalida -> M_5,
    escondendo que a estrategia "S2 M10" nunca existiu no servidor: toda coleta
    dita M10 vinha, na verdade, em M_15. Ver specs/ROADMAP.md.
    """
    key = tf.strip().lower().replace("_", "")
    period = _PERIOD_MAP.get(key)
    if period is None:
        raise MCPError(
            f"[ERRO] mcp_client._timeframe_to_period: timeframe '{tf}' nao existe "
            f"no MCP. Validos: {sorted(_PERIOD_MAP)}. "
            f"Nao ha M_10 -- scalp de 10min deve usar M_15."
        )
    return period


def _lots_to_cents(lots: float, lot_size: int = 100000) -> int:
    """Converte lots  cents (Remote HTTP). 1 lot forex = 10,000,000 cents."""
    return int(lots * lot_size * 100)


def _price_to_pipettes(price: float, symbol: str) -> int:
    """Converte preo display  pipettes (Remote HTTP).
    Ex: EURUSD 1.0850 com pipDigits=5  108500."""
    pip_digits = 5  # fallback; idealmente lido de get_symbols()
    return int(price * (10 ** pip_digits))


def _pipettes_to_price(pipettes: int, symbol: str) -> float:
    """Converte pipettes  preo display."""
    pip_digits = 5
    return pipettes / (10 ** pip_digits)


def volume_compliant(symbol: str, lots: float) -> int:
    """Arredonda volume para o volumeStep do smbolo (cents).
    Evita rejeio @Positive do Remote MCP.
    Retorna volume em cents j arredondado.
    """
    meta = _symbol_meta_cache.get(symbol, {})
    step = meta.get("volumeStep", 1000)
    min_vol = meta.get("minVolume", 1000)
    raw_cents = _lots_to_cents(lots)
    compliant = max(min_vol, ((raw_cents + step - 1) // step) * step)
    return int(compliant)


def get_idempotency_label(tag: str = "") -> str:
    """Label idempotente da sesso: 'sess-XXXXXXXX-<tag>'."""
    return f"{_IDEMPOTENCY_PREFIX}-{tag}" if tag else _IDEMPOTENCY_PREFIX


def get_spot_prices(symbol: str) -> dict[str, Any]:
    """Cotacao ao vivo. Remote HTTP: symbolId array. Desembrulha prices[0]."""
    sid = resolve_symbol(symbol)
    result = call_tool("get_spot_prices", {"symbolId": [sid]})
    # MCP retorna {prices: [{symbolId, bid, ask, ...}]}
    prices = result.get("prices", [])
    if prices and isinstance(prices, list):
        return prices[0]
    return result


# Minutos por periodo -- usado para derivar a janela from/to quando o caller
# passa so count (contrato REAL do servidor exige fromTimestamp; ver S1.1).
_PERIOD_MINUTES = {
    "M_1": 1, "M_5": 5, "M_15": 15, "M_30": 30,
    "H_1": 60, "H_4": 240, "D_1": 1440, "W_1": 10080, "MN_1": 43200,
}
_JANELA_MAX_MIN = 720 * 60  # cap do servidor: 720h (30 dias) por requisicao


def get_trendbars(
    symbol: str,
    timeframe: str,
    count: int = 100,
    from_timestamp: str | None = None,
    to_timestamp: str | None = None,
) -> list[dict[str, Any]]:
    """Candles historicos. Contrato MEDIDO (S1.1, ROADMAP 1.0):
    - fromTimestamp+toTimestamp OBRIGATORIOS (string ISO-8601) -- sem eles o
      backend responde HTTP 400 `fromTimestamp: must not be null` SEMPRE;
    - janela max 720h (30d) por requisicao; count max 1000 (default 100 trunca);
    - retorno = as N barras mais recentes da janela (a ultima e a barra FORMANDO).
    Sem from/to explicitos, deriva janela: count x periodo x3 (margem p/ fds),
    capada em 720h, terminando em agora (UTC).
    """
    sid = resolve_symbol(symbol)
    period = _timeframe_to_period(timeframe)
    if count > 1000:
        raise MCPError(
            f"[ERRO] mcp_client.get_trendbars: count={count} excede o teto de 1000 "
            f"do servidor. Paginar com janelas from/to (<=720h cada)."
        )
    now = datetime.now(UTC)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    if to_timestamp is None:
        to_timestamp = now.strftime(fmt)
    if from_timestamp is None:
        lookback_min = min(_PERIOD_MINUTES[period] * count * 3, _JANELA_MAX_MIN)
        from_timestamp = (now - timedelta(minutes=lookback_min)).strftime(fmt)
    result = call_tool("get_trendbars", {
        "symbolId": sid,
        "period": period,
        "fromTimestamp": from_timestamp,
        "toTimestamp": to_timestamp,
        "count": count,
    })
    # servidor devolve {"trendbars": [...]} -- callers esperam lista
    if isinstance(result, dict):
        return result.get("trendbars", [])
    return result


# ===== POSITIONS / ORDERS =====

def get_positions(symbol: str | None = None) -> list[dict[str, Any]]:
    """Posicoes abertas + ordens pendentes."""
    args: dict[str, Any] = {}
    if symbol:
        args["symbol"] = symbol
    return call_tool("get_positions", args)


def get_position_details(position_id: str) -> dict[str, Any]:
    """Detalhes da posicao com ordens e deals relacionados."""
    return call_tool("get_position_details", {"positionId": position_id})


def get_pending_orders() -> list[dict[str, Any]]:
    """Ordens pendentes."""
    return call_tool("get_pending_orders")


def _days_window(days: int, quem: str) -> tuple[str, str]:
    """Converte days -> (fromTimestamp, toTimestamp) ISO. Cap 720h do servidor."""
    if days > 30:
        raise MCPError(
            f"[ERRO] mcp_client.{quem}: days={days} excede a janela de 720h (30d) "
            f"do servidor. Paginar em janelas de 30d."
        )
    now = datetime.now(UTC)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return (now - timedelta(days=days)).strftime(fmt), now.strftime(fmt)


def get_order_history(days: int = 7) -> list[dict[str, Any]]:
    """Historico de ordens. Contrato real (G10): fromTimestamp+toTimestamp
    obrigatorios -- o antigo `{"days": N}` respondia 400 sempre."""
    frm, to = _days_window(days, "get_order_history")
    result = call_tool("get_order_history", {"fromTimestamp": frm, "toTimestamp": to})
    if isinstance(result, dict):
        return result.get("orders", result.get("orderHistory", []))
    return result


def get_deals(days: int = 7) -> list[dict[str, Any]]:
    """Historico de deals/trades. Contrato real (G10): fromTimestamp+toTimestamp
    obrigatorios; `days` nem existe no schema (props: from/to/maxRows)."""
    frm, to = _days_window(days, "get_deals")
    result = call_tool("get_deals", {"fromTimestamp": frm, "toTimestamp": to})
    if isinstance(result, dict):
        return result.get("deals", [])
    return result


# ===== TRADING MUTATIONS =====

def create_order(
    symbol: str,
    side: str,
    volume: float,
    order_type: str = "MARKET",
    sl: float | None = None,
    tp: float | None = None,
    limit_price: float | None = None,
    stop_price: float | None = None,
) -> dict[str, Any]:
    """Cria ordem. Remote HTTP: symbolId, volume cents, MARKETrelativeStopLoss."""
    sid = resolve_symbol(symbol)
    compliant_vol = volume_compliant(symbol, volume)
    args: dict[str, Any] = {
        "symbolId": sid,
        "tradeSide": side.upper(),
        "volume": compliant_vol,
        "orderType": order_type.upper(),
        "label": get_idempotency_label(symbol.lower()),
        "comment": f"NC-V44 F4 {side.upper()} {symbol}",
    }
    if order_type.upper() == "MARKET":
        if sl is not None:
            args["relativeStopLoss"] = int(abs(sl))
        if tp is not None:
            args["relativeTakeProfit"] = int(abs(tp))
    else:
        # LIMIT, STOP, STOP_LIMIT aceitam absoluto (convertido a pipettes)
        if sl is not None:
            args["stopLoss"] = _price_to_pipettes(sl, symbol)
        if tp is not None:
            args["takeProfit"] = _price_to_pipettes(tp, symbol)
    if limit_price is not None:
        args["limitPrice"] = limit_price
    if stop_price is not None:
        args["stopPrice"] = stop_price
    return call_tool("create_order", args)


def close_position(position_id: str, volume: float | None = None) -> dict[str, Any]:
    """Fecha posicao. Remote HTTP: volume OBRIGATORIO (cents)."""
    args: dict[str, Any] = {"positionId": position_id}
    if volume is not None:
        args["volume"] = _lots_to_cents(volume)
    return call_tool("close_position", args)


def amend_position(position_id: str, sl: float | None = None, tp: float | None = None) -> dict[str, Any]:
    """Modifica SL/TP. Q-R10: SEMPRE enviar AMBOS. Preos em display  convertidos a pipettes."""
    if sl is None or tp is None:
        positions = get_positions()
        for pos in positions:
            if str(pos.get("positionId")) == str(position_id):
                if sl is None:
                    sl = pos.get("stopLoss")
                if tp is None:
                    tp = pos.get("takeProfit")
                break
    args: dict[str, Any] = {"positionId": position_id}
    sym = _resolve_sym(position_id)
    if sl is not None:
        args["stopLoss"] = _price_to_pipettes(sl, sym)
    if tp is not None:
        args["takeProfit"] = _price_to_pipettes(tp, sym)
    return call_tool("amend_position", args)


def _resolve_sym(position_id: str) -> str:
    """Resolve symbolName a partir do position_id (fallback: 'EURUSD')."""
    try:
        positions = get_positions()
        for p in positions:
            if str(p.get("positionId")) == str(position_id):
                return p.get("symbolName", "EURUSD")
    except Exception:
        pass
    return "EURUSD"


def cancel_order(order_id: str) -> dict[str, Any]:
    """Cancela ordem pendente."""
    return call_tool("cancel_order", {"orderId": order_id})


def amend_order(order_id: str, price: float | None = None, volume: int | None = None,
                sl: float | None = None, tp: float | None = None) -> dict[str, Any]:
    """Modifica ordem pendente."""
    args: dict[str, Any] = {"orderId": order_id}
    if price is not None:
        args["price"] = price
    if volume is not None:
        args["volume"] = volume
    if sl is not None:
        args["stopLoss"] = sl
    if tp is not None:
        args["takeProfit"] = tp
    return call_tool("amend_order", args)


# ===== UTILS =====

def get_version() -> dict[str, Any]:
    """Versao do servico MCP."""
    return call_tool("get_version")


# ---------------------------------------------------------------------------
# excecoes
# ---------------------------------------------------------------------------


class MCPError(Exception):
    """Base para erros MCP."""


class MCPConnectionError(MCPError):
    """Falha de conexao/rede."""


class MCPTimeoutError(MCPError):
    """Timeout na chamada MCP."""


class MCPMethodError(MCPError):
    """Erro retornado pelo tool (ex: simbolo invalido)."""

    def __init__(self, method: str, code: int, message: str):
        self.method = method
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {method}: {message}")


class MCPProtocolError(MCPError):
    """Resposta invalida (SSE/JSON)."""


# ---------------------------------------------------------------------------
# entrypoint
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    init_client()
    info = get_balance()
    print(json.dumps(info, indent=2))
