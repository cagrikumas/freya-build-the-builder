import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { createBankWorker } from "../src/bank.js";
import { createFixtureStore } from "../src/fixtures.js";
import { SERVICES } from "../src/contract.js";

const fixture = JSON.parse(readFileSync(new URL("../fixtures/test-customers.json", import.meta.url), "utf8"));
const api = JSON.parse(readFileSync(new URL("../openapi.json", import.meta.url), "utf8"));
const store = createFixtureStore(fixture);
const origin = "https://contract-test.example";
function fields(entry) {
  if (entry.service === "cards.list") return { customerNo: entry.customerNo };
  if (entry.service === "contact.email.get") return { customerNo: entry.customerNo, intAddressInfoType: "E" };
  if (entry.service === "statement.pdf.send") return { customerNo: entry.customerNo,
    cardNumber: "ignored-test-selector", currencyType: "TL", statementDate: "05.10.2026", emailAddress: "fixture-test@example.invalid" };
  const data = { cardNumber: entry.selectors[0] };
  if (entry.selectors.length === 2) Object.assign(data, { newStatementWeek: entry.selectors[1], statementDay: 5 });
  return data;
}
function request(service, data, extras = {}) {
  return new Request(origin + "/voice/v1/" + service, { method: "POST", body: JSON.stringify({ data, ...extras }) });
}

function schemaErrors(value, schema, path = "$", errors = []) {
  if (schema.$ref) {
    schema = schema.$ref.slice(2).split("/").reduce((current, part) => current[part], api);
  }
  if (value === null && schema.nullable) return errors;
  if (schema.oneOf) {
    if (schema.oneOf.filter(candidate => schemaErrors(value, candidate, path, []).length === 0).length !== 1) errors.push(path + " oneOf");
    return errors;
  }
  const actual = value === null ? "null" : Array.isArray(value) ? "array" : typeof value;
  if (schema.type && !(schema.type === "integer" ? Number.isInteger(value) : schema.type === actual)) {
    errors.push(path + " type " + actual + ", expected " + schema.type); return errors;
  }
  if (schema.enum && !schema.enum.includes(value)) errors.push(path + " enum");
  if (schema.pattern && !new RegExp(schema.pattern).test(value)) errors.push(path + " pattern");
  if (actual === "object") {
    for (const key of schema.required ?? []) if (!Object.hasOwn(value, key)) errors.push(path + "." + key + " required");
    for (const [key, child] of Object.entries(value)) {
      if (schema.properties?.[key]) schemaErrors(child, schema.properties[key], path + "." + key, errors);
    }
  }
  if (actual === "array" && schema.items) value.forEach((child, i) => schemaErrors(child, schema.items, path + "[" + i + "]", errors));
  return errors;
}

test("all 617 released responses are exact through the real HTTP handler, including errors and delay", async () => {
  const waits = [];
  const worker = createBankWorker(fixture, { sleep: async milliseconds => waits.push(milliseconds) });
  for (const entry of store.entries()) {
    const response = await worker.fetch(request(entry.service, fields(entry)));
    assert.equal(response.status, entry.fixture.http, JSON.stringify(entry));
    assert.match(response.headers.get("content-type"), /application\/json/);
    const data = await response.json();
    assert.deepEqual(data, entry.fixture.response, entry.customerNo + " " + entry.service + " " + entry.selectors);
    assert.equal(Object.hasOwn(data, "delaySeconds"), false);
    const schema = api.paths["/voice/v1/" + entry.service].post.responses[String(entry.fixture.http)].content["application/json"].schema;
    assert.deepEqual(schemaErrors(data, schema), [], entry.customerNo + " " + entry.service);
  }
  assert.deepEqual(waits, [12000]);
});

test("numeric/string keys are equivalent and non-selector metadata is ignored", async () => {
  const worker = createBankWorker(fixture, { sleep: async () => {} });
  const customer = fixture.customers[0].customerNo;
  const a = await (await worker.fetch(request("cards.list", { customerNo: customer }))).json();
  const b = await (await worker.fetch(request("cards.list", { customerNo: Number(customer), aiFlow: "ignored" }, { call: null }))).json();
  assert.deepEqual(a, b);
  const entry = store.entries().find(row => row.service === "statement.week.decide");
  const data = fields(entry);
  const numeric = await (await worker.fetch(request(entry.service, { ...data, newStatementWeek: Number(data.newStatementWeek) }))).json();
  assert.deepEqual(numeric, entry.fixture.response);
  for (const kind of ["E", "P", "B"]) {
    const response = await worker.fetch(request("contact.email.get", { customerNo: customer, intAddressInfoType: kind }));
    assert.deepEqual(await response.json(), store.lookup(customer, "contact.email.get").response);
  }
  const req = request("cards.list", { customerNo: customer });
  req.headers.set("Authorization", "Bearer unused-test-token");
  assert.deepEqual(await (await worker.fetch(req)).json(), a);
});

test("unknown customer/card/week uses the documented service-specific error", async () => {
  const worker = createBankWorker(fixture);
  const expected = { "cards.list": [404, "FB_IVR_CHANNEL_102"], "cards.balance": [404, "FB_IVR_CHANNEL_120"],
    "statement.week.get": [404, "FB_IVR_CHANNEL_121"], "statement.week.decide": [400, "INVALID_ARGUMENTS_ERROR"],
    "statement.week.change": [400, "INVALID_ARGUMENTS_ERROR"], "contact.email.get": [400, "INVALID_ARGUMENTS_ERROR"],
    "statement.pdf.send": [404, "FB_IVR_CHANNEL_107"] };
  for (const service of Object.keys(SERVICES)) {
    const entry = store.entries().find(row => row.service === service);
    const data = fields(entry);
    if (SERVICES[service].customer) data.customerNo = "not-listed";
    else data.cardNumber = "not-listed";
    const response = await worker.fetch(request(service, data));
    const body = await response.json();
    assert.equal(response.status, expected[service][0]);
    assert.equal(body.result.returnCode, expected[service][1]);
    assert.equal(body.result.code, expected[service][1]);
    assert.equal(body.result.message, body.result.messageText);
    assert.equal(body.result.guid, body.result.details.guid);
    assert.equal(Object.hasOwn(body, "data"), false);
  }
  for (const service of ["statement.week.decide", "statement.week.change"]) {
    const entry = store.entries().find(row => row.service === service);
    const card = entry.selectors[0];
    const currentWeek = store.lookup(entry.customerNo, "statement.week.get", [card]).response.data.statementWeek;
    const response = await worker.fetch(request(service, { cardNumber: card, newStatementWeek: currentWeek, statementDay: 5 }));
    assert.equal(response.status, 400);
  }
});

test("missing and empty required fields return only INVALID_ARGUMENTS_ERROR envelopes", async () => {
  const worker = createBankWorker(fixture);
  for (const [service, contract] of Object.entries(SERVICES)) {
    const entry = store.entries().find(row => row.service === service);
    for (const field of contract.required) {
      for (const value of [undefined, null, "", "   ", {}, []]) {
        const data = { ...fields(entry), [field]: value };
        const response = await worker.fetch(request(service, data));
        const body = await response.json();
        assert.equal(response.status, 400, service + " " + field);
        assert.equal(body.result.returnCode, "INVALID_ARGUMENTS_ERROR");
        assert.equal(Object.hasOwn(body, "data"), false);
      }
    }
  }
  for (const body of ["not-json", "null", "[]", "{}", '{"data":null}']) {
    const response = await worker.fetch(new Request(origin + "/voice/v1/cards.list", { method: "POST", body }));
    assert.equal(response.status, 400);
  }
});

test("preview and repeated changes preserve the exact static test table", async () => {
  const worker = createBankWorker(fixture);
  const entry = store.entries().find(row => row.service === "statement.week.change");
  const get = () => worker.fetch(request("statement.week.get", { cardNumber: entry.selectors[0] }));
  const before = await (await get()).json();
  await worker.fetch(request("statement.week.decide", fields(entry)));
  assert.deepEqual(await (await get()).json(), before);
  for (let i = 0; i < 2; i++) {
    const change = await worker.fetch(request(entry.service, fields(entry)));
    assert.deepEqual(await change.json(), entry.fixture.response);
  }
  assert.deepEqual(await (await get()).json(), before);
});

test("published schema contains exactly the seven bank paths and uses the actual Worker origin", async () => {
  const worker = createBankWorker(fixture);
  const schema = await (await worker.fetch(new Request(origin + "/openapi.json"))).json();
  assert.deepEqual(schema.servers, [{ url: origin }]);
  assert.deepEqual(Object.keys(schema.paths).sort(), Object.keys(SERVICES).map(name => "/voice/v1/" + name).sort());
  for (const path of Object.keys(schema.paths)) assert.deepEqual(Object.keys(schema.paths[path]), ["post"]);
  assert.equal((await worker.fetch(new Request(origin + "/health"))).status, 200);
  assert.equal((await worker.fetch(new Request(origin + "/invented"))).status, 404);
  const wrongMethod = await worker.fetch(new Request(origin + "/voice/v1/cards.list"));
  assert.equal(wrongMethod.status, 405);
  assert.equal(wrongMethod.headers.get("allow"), "POST");
});
