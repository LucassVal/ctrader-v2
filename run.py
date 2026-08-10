"""
PROPOSITO: T26
SPEC: S0
ROADMAP: 0.0
"""

from __future__ import annotations

import logging
import signal
import subprocess
import sys
import time
from pathlib import Path

from utils.health import write_heartbeat as _write_heartbeat
from utils.logger import get_logger

ROOT = Path(__file__).resolve().parent
STATUS_DIR = ROOT / "status"
STATUS_DIR.mkdir(parents=True, exist_ok=True)

logger = get_logger(__name__, "RUN")

PROCESSES = {
    "f0": {
        "script": "-m f0_collector.orc_coleta",
        "priority": "normal",
        "restart_on_crash": True,
    },
    "f4": {
        "script": "-m f4_executor.orc_execucao",
        "priority": "critical",
        "restart_on_crash": False,  # humano intervem
    },
    # Fix 2026-07-30 (avaliacao mestra §1.2): apontavam p/ f1_analyzer.py,
    # f2_fusion.py, f3_validator.py — arquivos MORTOS que nem existem no disco.
    # F1-F3 nunca engatavam no boot central. Agora usam os pacotes reais.
    "f1": {
        "script": "-m f1_analyzer.orc_analise",
        "priority": "normal",
        "restart_on_crash": True,
    },
    "f2": {
        "script": "-m f2_fusao.orc_fusao",
        "priority": "normal",
        "restart_on_crash": True,
    },
    "f3": {
        "script": "-m f3_validacao.orc_validacao",
        "priority": "normal",
        "restart_on_crash": True,
    },
    "f5": {
        "script": "-m f5_mar.orc_mar",
        "priority": "normal",
        "restart_on_crash": True,
    },
    # dashboard streamlit legado REMOVIDO — UI oficial: 10.0_ui_dash (API :7744 + React :5173)
}

shutdown_flag = False


def _handle_signal(signum, frame):
    global shutdown_flag
    logger.info("Sinal recebido: %s. Encerrando orquestrador...", signum)
    shutdown_flag = True


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ---------------------------------------------------------------------------
# gerenciamento de processos


# ---------------------------------------------------------------------------
# gerenciamento de processos
# ---------------------------------------------------------------------------

def _start_process(name: str, config: dict) -> subprocess.Popen | None:
    script = config["script"]
    launcher = config.get("launcher", [sys.executable])

    cmd = [*launcher, script]

    logger.info("Iniciando %s: %s", name, " ".join(cmd))
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        _write_heartbeat(name)
        return proc
    except Exception as e:
        logger.error("Falha ao iniciar %s: %s", name, e)
        return None


def _read_output(proc: subprocess.Popen, name: str):
    """Le stdout em modo nao-bloqueante."""
    if proc.stdout and proc.stdout.readable():
        line = proc.stdout.readline()
        if line:
            logger.info("[%s] %s", name, line.rstrip())


def run():
    """Loop principal do orquestrador."""
    logger.info("=== ORQUESTRADOR INICIADO ===")

    procs: dict[str, subprocess.Popen | None] = {}

    # inicia F4 primeiro (critico)
    if "f4" in PROCESSES:
        procs["f4"] = _start_process("f4", PROCESSES["f4"])
        time.sleep(1)

    # inicia resto
    for name in PROCESSES:
        if name == "f4" or name == "dashboard":
            continue
        procs[name] = _start_process(name, PROCESSES[name])

    # dashboard por ultimo
    if "dashboard" in PROCESSES:
        time.sleep(2)
        procs["dashboard"] = _start_process("dashboard", PROCESSES["dashboard"])

    last_heartbeat_check = time.monotonic()

    while not shutdown_flag:
        # heartbeat check a cada 10s
        now = time.monotonic()
        if now - last_heartbeat_check >= 10:
            for name, proc in list(procs.items()):
                if proc is None:
                    continue
                poll = proc.poll()
                if poll is not None:
                    # processo morreu
                    logger.error("%s encerrou (exit=%d)", name, poll)
                    cfg = PROCESSES.get(name, {})
                    if cfg.get("restart_on_crash", False):
                        logger.info("Reiniciando %s...", name)
                        procs[name] = _start_process(name, cfg)
                    elif cfg.get("priority") == "critical":
                        logger.critical("F4 CRASHOU! ALERTA HUMANO!")
                else:
                    # ainda rodando — verifica heartbeat
                    from utils.health import read_heartbeat
                    age = read_heartbeat(name)
                    alive = age is not None and age <= 15
                    if not alive:
                        logger.error("%s sem heartbeat ha >15s", name)
            last_heartbeat_check = now

        # le stdout de cada processo
        for name, proc in list(procs.items()):
            if proc:
                _read_output(proc, name)

        time.sleep(2)

    # -------- encerramento --------
    logger.info("Encerrando todos os processos...")
    for name, proc in procs.items():
        if proc and proc.poll() is None:
            logger.info("Terminando %s...", name)
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    logger.info("=== ORQUESTRADOR ENCERRADO ===")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] run: %(message)s",
    )
    run()


if __name__ == "__main__":
    main()
