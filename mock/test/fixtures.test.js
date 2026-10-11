import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { createFixtureStore } from "../src/fixtures.js";

const source = JSON.parse(readFileSync(new URL("../fixtures/test-customers.json", import.meta.url), "utf8"));

function sourceEntries() {
  const records = [];
  function walk(customerNo, service, value, selectors = []) {
    if (Object.hasOwn(value, "http")) records.push({ customerNo, service, selectors, fixture: value });
    else for (const key of Object.keys(value)) walk(customerNo, service, value[key], selectors.concat(key));
  }
  for (const customer of source.customers) {
    for (const [service, data] of Object.entries(customer.services)) walk(customer.customerNo, service, data);
  }
  return records;
}

test("every supplied response and status is indexed without changing its shape", () => {
  const store = createFixtureStore(source);
  assert.equal(store.customerNumbers().length, 34);
  assert.equal(store.serviceNames().length, 7);
  assert.equal(store.entries().length, 617);
  assert.deepEqual(store.entries(), sourceEntries());
  const statuses = new Map();
  for (const record of sourceEntries()) {
    assert.deepEqual(store.lookup(record.customerNo, record.service, record.selectors), record.fixture);
    statuses.set(record.fixture.http, (statuses.get(record.fixture.http) ?? 0) + 1);
  }
  assert.deepEqual(Object.fromEntries(statuses), { 200: 609, 404: 2, 500: 6 });
  const delayed = store.entries().filter(record => Object.hasOwn(record.fixture, "delaySeconds"));
  assert.equal(delayed.length, 1);
  assert.equal(delayed[0].fixture.delaySeconds, 12);
});

test("customer, card and requested-week keys are exact; absent data stays absent", () => {
  const store = createFixtureStore(source);
  const record = store.entries().find(record => record.service === "statement.week.decide");
  assert.equal(record.selectors.length, 2);
  assert.deepEqual(store.lookup(record.customerNo, record.service, record.selectors), record.fixture);
  assert.equal(store.lookup(record.customerNo, record.service, [record.selectors[0]]), undefined);
  assert.equal(store.lookup(record.customerNo, record.service, [record.selectors[0], "not-listed"]), undefined);
  assert.equal(store.lookup("not-listed", record.service, record.selectors), undefined);
  assert.equal(store.lookup(record.customerNo, "not-listed", []), undefined);
  assert.throws(() => store.lookup(record.customerNo, record.service, [1]), TypeError);
});

test("repeated lookups cannot mutate the source fixtures or invent side effects", () => {
  const input = structuredClone(source);
  const store = createFixtureStore(input);
  const record = store.entries().find(record => record.service === "statement.week.change");
  const before = store.lookup(record.customerNo, record.service, record.selectors);
  const response = store.lookup(record.customerNo, record.service, record.selectors);
  response.http = 599;
  response.response = { altered: true };
  input.customers.length = 0;
  const customer = store.customer(record.customerNo);
  customer.services = {};
  assert.deepEqual(store.lookup(record.customerNo, record.service, record.selectors), before);
  assert.equal(store.customerNumbers().length, 34);
});

test("malformed fixture input fails before serving any data", () => {
  assert.throws(() => createFixtureStore({}), TypeError);
  const duplicate = structuredClone(source);
  duplicate.customers.push(duplicate.customers[0]);
  assert.throws(() => createFixtureStore(duplicate), /Duplicate fixture customer/);
  for (const fixture of [{ http: "200" }, { http: 200, delaySeconds: -1 }]) {
    assert.throws(() => createFixtureStore({ customers: [{ customerNo: "fixture-only", services: { example: fixture } }] }), TypeError);
  }
});
