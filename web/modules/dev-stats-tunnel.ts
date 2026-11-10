import { defineNuxtModule, logger } from "@nuxt/kit";
import { spawn, type ChildProcess } from "node:child_process";
import { connect } from "node:net";

// Opt-in local forward of the VPS stats-server. Default dev talks to the
// public site over HTTPS (see nuxt.config). Enable with NUXT_USE_TUNNEL=1
// and NUXT_STATS_PROXY=http://127.0.0.1:18765.
const LOCAL_PORT = 18765;
const REMOTE_HOST = "root@85.192.30.108";
const REMOTE_BIND = "127.0.0.1:8765";

function portOpen(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = connect({ port, host: "127.0.0.1" }, () => {
      socket.end();
      resolve(true);
    });
    socket.on("error", () => resolve(false));
  });
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

export default defineNuxtModule({
  meta: { name: "kfm-dev-stats-tunnel" },
  async setup(_options, nuxt) {
    if (!nuxt.options.dev) return;
    if (process.env.NUXT_USE_TUNNEL !== "1") return;
    if (process.env.NUXT_NO_TUNNEL === "1") return;

    const proxy = process.env.NUXT_STATS_PROXY || `http://127.0.0.1:${LOCAL_PORT}`;
    if (!proxy.includes(`:${LOCAL_PORT}`)) {
      logger.warn(
        `stats-tunnel: NUXT_USE_TUNNEL=1 but proxy is ${proxy} (expected :${LOCAL_PORT})`,
      );
      return;
    }

    let child: ChildProcess | null = null;
    let owned = false;

    const kill = () => {
      if (!child || child.killed) return;
      child.kill();
      child = null;
    };

    process.once("exit", kill);
    process.once("SIGINT", kill);
    process.once("SIGTERM", kill);
    nuxt.hook("close", kill);

    if (await portOpen(LOCAL_PORT)) {
      logger.info(`stats-tunnel: :${LOCAL_PORT} already open, reusing`);
      return;
    }

    logger.info(
      `stats-tunnel: ssh -N -L ${LOCAL_PORT}:${REMOTE_BIND} ${REMOTE_HOST}`,
    );
    child = spawn(
      "ssh",
      [
        "-N",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "ServerAliveInterval=30",
        "-L",
        `${LOCAL_PORT}:${REMOTE_BIND}`,
        REMOTE_HOST,
      ],
      {
        stdio: "inherit",
        windowsHide: true,
      },
    );
    owned = true;

    child.on("exit", (code, signal) => {
      if (!owned) return;
      child = null;
      if (code && code !== 0) {
        logger.error(
          `stats-tunnel: ssh exited (${code ?? signal}). Check SSH keys/agent.`,
        );
      }
    });

    for (let i = 0; i < 40; i += 1) {
      if (await portOpen(LOCAL_PORT)) {
        logger.success(`stats-tunnel: listening on :${LOCAL_PORT}`);
        return;
      }
      if (!child) break;
      await sleep(250);
    }

    logger.warn(
      `stats-tunnel: :${LOCAL_PORT} not open yet — ssh may be waiting for a passphrase, or auth failed`,
    );
  },
});
