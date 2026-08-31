/**
 * Preload for cursor-agent under corporate TLS inspection.
 * Missing Thales Devices CA V4 root makes default Node verify fail;
 * NODE_TLS_REJECT_UNAUTHORIZED=0 is ignored by the agent stack.
 *
 * Usage:
 *   node -r ./scripts/cursor_agent_tls_bypass.cjs <agent-index.js> ...
 */
"use strict";

process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";

try {
  const tls = require("tls");
  const wrap = (orig) =>
    function patchedConnect(...args) {
      if (args[0] && typeof args[0] === "object") {
        args[0].rejectUnauthorized = false;
      } else if (typeof args[1] === "object" && args[1] !== null) {
        args[1].rejectUnauthorized = false;
      }
      return orig.apply(this, args);
    };
  if (typeof tls.connect === "function") {
    tls.connect = wrap(tls.connect.bind(tls));
  }
} catch (_) {
  /* ignore */
}

try {
  const https = require("https");
  if (https.globalAgent) {
    https.globalAgent.options.rejectUnauthorized = false;
  }
  const Agent = https.Agent;
  https.Agent = function PatchedAgent(options) {
    options = Object.assign({}, options || {}, { rejectUnauthorized: false });
    return new Agent(options);
  };
  https.Agent.prototype = Agent.prototype;
} catch (_) {
  /* ignore */
}

try {
  const undici = require("undici");
  if (undici && undici.Agent && undici.setGlobalDispatcher) {
    undici.setGlobalDispatcher(
      new undici.Agent({ connect: { rejectUnauthorized: false } })
    );
  }
} catch (_) {
  /* undici may be bundled differently — ignore */
}
