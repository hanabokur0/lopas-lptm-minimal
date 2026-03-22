function clamp01(x) {
  if (typeof x !== "number" || Number.isNaN(x)) return 0;
  return Math.max(0, Math.min(1, x));
}

function computeBasePST(doq, cci, hgd, trs) {
  const pst =
    0.30 * clamp01(doq) +
    0.25 * clamp01(cci) +
    0.20 * clamp01(hgd) +
    0.25 * clamp01(trs);

  return clamp01(pst);
}

function computePSTDynamics(prevPrevPst, prevPst, currPst) {
  const deltaPrev = prevPst - prevPrevPst;
  const deltaCurr = currPst - prevPst;
  const delta2 = deltaCurr - deltaPrev;

  return {
    pst: currPst,
    delta_pst: deltaCurr,
    delta2_pst: delta2,
  };
}

function classifyTransition(snapshot) {
  const pst = snapshot.pst;
  const d1 = snapshot.delta_pst;
  const d2 = snapshot.delta2_pst;

  if (pst >= 0.82 && d1 > 0.03) {
    return "breakout";
  }

  if (pst >= 0.65 && d1 > 0.01 && d2 >= 0) {
    return "phase_rising";
  }

  if (pst >= 0.58 && pst <= 0.72 && Math.abs(d1) < 0.01 && Math.abs(d2) < 0.01) {
    return "cob_oscillation";
  }

  if (pst >= 0.65 && d1 < 0 && d2 < 0) {
    return "false_peak";
  }

  return "stable_or_noise";
}

function applyHysteresis(snapshot, prevLayer) {
  const pst = snapshot.pst;
  const transition = classifyTransition(snapshot);

  if (prevLayer === "L1") {
    if (transition === "phase_rising" || transition === "breakout") {
      return "L2";
    }
    return "L1";
  }

  if (prevLayer === "L2") {
    if (transition === "breakout") {
      return "L3";
    }
    if (pst < 0.58 && transition === "stable_or_noise") {
      return "L1";
    }
    return "L2";
  }

  if (prevLayer === "L3") {
    if (pst < 0.76 && snapshot.delta_pst < 0) {
      return "L2";
    }
    return "L3";
  }

  return prevLayer;
}

function jsonResponse(data, status) {
  return new Response(JSON.stringify(data, null, 2), {
    status: status || 200,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "access-control-allow-origin": "*",
      "access-control-allow-methods": "GET, POST, OPTIONS",
      "access-control-allow-headers": "content-type",
    },
  });
}

function validateBody(body) {
  const errors = [];

  ["doq", "cci", "hgd", "trs"].forEach(function (key) {
    const value = body[key];
    if (typeof value !== "number" || Number.isNaN(value)) {
      errors.push(key + " must be a number");
    }
  });

  if (
    body.prev_layer !== undefined &&
    body.prev_layer !== "L1" &&
    body.prev_layer !== "L2" &&
    body.prev_layer !== "L3"
  ) {
    errors.push("prev_layer must be one of L1, L2, L3");
  }

  return errors;
}

export default {
  async fetch(request) {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: {
          "access-control-allow-origin": "*",
          "access-control-allow-methods": "GET, POST, OPTIONS",
          "access-control-allow-headers": "content-type",
        },
      });
    }

    if (request.method === "GET" && url.pathname === "/") {
      return jsonResponse({
        name: "lopas-lptm-eval",
        version: "v0.1",
        endpoints: ["GET /", "POST /v1/eval"],
      });
    }

    if (request.method === "POST" && url.pathname === "/v1/eval") {
      let body;

      try {
        body = await request.json();
      } catch (e) {
        return jsonResponse({ error: "Invalid JSON body" }, 400);
      }

      const errors = validateBody(body);
      if (errors.length > 0) {
        return jsonResponse({ error: "Validation failed", details: errors }, 400);
      }

      const doq = clamp01(body.doq);
      const cci = clamp01(body.cci);
      const hgd = clamp01(body.hgd);
      const trs = clamp01(body.trs);

      const currPst = computeBasePST(doq, cci, hgd, trs);
      const prevPst =
        typeof body.prev_pst === "number" ? clamp01(body.prev_pst) : currPst;
      const prevPrevPst =
        typeof body.prev_prev_pst === "number" ? clamp01(body.prev_prev_pst) : prevPst;
      const prevLayer = body.prev_layer || "L1";

      const snapshot = computePSTDynamics(prevPrevPst, prevPst, currPst);
      const transition = classifyTransition(snapshot);
      const layer = applyHysteresis(snapshot, prevLayer);

      return jsonResponse({
        pst: snapshot.pst,
        delta_pst: snapshot.delta_pst,
        delta2_pst: snapshot.delta2_pst,
        transition: transition,
        layer: layer,
        inputs: {
          doq: doq,
          cci: cci,
          hgd: hgd,
          trs: trs,
          prev_pst: prevPst,
          prev_prev_pst: prevPrevPst,
          prev_layer: prevLayer,
        },
      });
    }

    return jsonResponse({ error: "Not found" }, 404);
  },
};
