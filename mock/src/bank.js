import { createFixtureStore } from "./fixtures.js";
import { SERVICES } from "./contract.js";
import openapi from "../openapi.json" with { type: "json" };

const pause = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
const nonempty = value => (typeof value === "string" && value.trim() !== "") ||
  (typeof value === "number" && Number.isFinite(value));

function errorResponse(status, code, message, type = "ERROR") {
  const guid = crypto.randomUUID().replaceAll("-", "");
  return Response.json({ result: {
    guid, returnCode: code, messageText: message, code, message, type,
    details: { guid, rootCause: status === 404 ? "NotFoundException" : "InvalidArgumentsException", errorOrigin: "mock-worker" },
  } }, { status });
}

function invalid(message) {
  return errorResponse(400, "INVALID_ARGUMENTS_ERROR", message);
}

export function createBankWorker(document, { sleep = pause } = {}) {
  const store = createFixtureStore(document);
  const cardFixtures = new Map();
  for (const entry of store.entries()) {
    if (!SERVICES[entry.service] || SERVICES[entry.service].customer) continue;
    const key = JSON.stringify([entry.service, ...entry.selectors]);
    if (cardFixtures.has(key)) throw new TypeError("Ambiguous card fixture key: " + key);
    cardFixtures.set(key, entry.fixture);
  }

  return {
    async fetch(request) {
      const url = new URL(request.url);
      if (url.pathname === "/health" && request.method === "GET") {
        return Response.json({ status: "ok", ready: true });
      }
      if (url.pathname === "/openapi.json" && request.method === "GET") {
        return Response.json({ ...openapi, servers: [{ url: url.origin }] });
      }
      const prefix = "/voice/v1/";
      const service = url.pathname.startsWith(prefix) ? url.pathname.slice(prefix.length) : "";
      const contract = Object.hasOwn(SERVICES, service) ? SERVICES[service] : undefined;
      if (!contract) return Response.json({ error: "Not found" }, { status: 404 });
      if (request.method !== "POST") {
        return Response.json({ error: "Method not allowed" }, { status: 405, headers: { Allow: "POST" } });
      }
      let body;
      try { body = await request.json(); }
      catch { return invalid("request body must be valid JSON"); }
      if (!object(body) || !object(body.data)) return invalid("data cannot be empty");
      const data = body.data;
      for (const field of contract.required) {
        if (!nonempty(data[field])) {
          return invalid(field === "cardNumber" ? "card number cannot be empty" : field + " cannot be empty");
        }
      }
      // The released test environment ignores token/headers/call/aiFlow and
      // selects solely by the keys listed in test-customers.md. Do not enforce
      // production-only authorization or invent post-write customer state.
      const fixture = contract.customer
        ? store.lookup(String(data.customerNo), service)
        : cardFixtures.get(JSON.stringify([service, ...contract.selectors.map(field => String(data[field]))]));
      if (!fixture) {
        if (contract.notFound) return errorResponse(404, ...contract.notFound, "WARNING");
        return invalid("No test response for the supplied service arguments");
      }
      if (fixture.delaySeconds !== undefined) await sleep(fixture.delaySeconds * 1000);
      return Response.json(fixture.response, { status: fixture.http });
    },
  };
}
